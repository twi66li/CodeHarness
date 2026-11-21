"""The runtime depends on this one model interface, not a provider SDK."""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ModelError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, retry_after: float | None = None,
                 access_denied: bool = False, consume_output_budget: bool = True):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
        self.access_denied = access_denied
        self.consume_output_budget = consume_output_budget


def safe_error_tag(body: bytes, api_key: str) -> str:
    """Extract only an ASCII error type/code token; never persist raw provider messages."""
    try:
        data = json.loads(body[:4096].decode("utf-8", errors="ignore"))
    except ValueError:
        return ""
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return ""
    for field in ("code", "type"):
        value = error.get(field)
        if (isinstance(value, str) and 1 <= len(value) <= 64
                and all(ch.isalnum() or ch in "_.-" for ch in value)
                and (not api_key or api_key not in value)):
            return f" ({value})"
    return ""


def retry_delay(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        if value.isdigit():
            return float(int(value))
        when = parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass
class Reply:
    message: dict
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False


class Model(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 *, timeout: float | None = None) -> Reply: ...


class ChatModel:
    """OpenAI-compatible Chat Completions. Credentials never enter the trace."""

    def __init__(self, model: str, base_url: str, api_key: str, timeout: float = 60,
                 *, reasoning_effort: str | None = None):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("模型地址必须是 http(s) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("请通过 API_KEY 提供凭据，模型地址不能包含凭据或查询参数")
        self.name = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 *, timeout: float | None = None) -> Reply:
        payload = {"model": self.name, "messages": messages, "max_tokens": max_tokens}
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urlopen(request, timeout=min(self.timeout, timeout) if timeout is not None else self.timeout) as response:
                data = json.load(response)
        except HTTPError as exc:
            # Provider bodies and URLs can contain credentials; only extract a safe ASCII error tag.
            try:
                body = exc.read(4096) if exc.fp is not None else b""
                tag = safe_error_tag(body, self.api_key)
            except (OSError, AttributeError):
                tag = ""
            raise ModelError(f"模型接口返回 HTTP {exc.code}{tag}", retryable=exc.code in {429, 500, 502, 503, 504},
                             retry_after=retry_delay(exc.headers.get("Retry-After") if exc.headers else None),
                             access_denied=exc.code in {401, 403},
                             consume_output_budget=exc.code >= 500) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            denied = isinstance(reason, PermissionError)
            timed_out = isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
            raise ModelError("模型接口连接失败或超时；请检查地址、代理及服务状态", retryable=not denied,
                             access_denied=denied, consume_output_budget=timed_out) from None
        except (ValueError, UnicodeError):
            raise ModelError("模型接口返回了无效 JSON") from None
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ModelError("模型输出达到单次上限，未接受不完整的回答或工具调用")
            message = choice["message"]
            clean = {"role": "assistant", "content": message.get("content") or ""}
            if not isinstance(clean["content"], str):
                raise ValueError("invalid content")
            if isinstance(message.get("reasoning_content"), str):
                clean["reasoning_content"] = message["reasoning_content"]
            calls = message.get("tool_calls") or []
            if calls:
                seen = set()
                cleaned_calls = []
                for call in calls:
                    if (call["type"] != "function" or not isinstance(call["id"], str)
                            or not call["id"] or call["id"] in seen):
                        raise ValueError("invalid tool call")
                    seen.add(call["id"])
                    fn = call["function"]
                    if not isinstance(fn["arguments"], str) or not isinstance(fn["name"], str) or not fn["name"]:
                        raise ValueError("invalid arguments")
                    cleaned_calls.append({
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": fn["name"], "arguments": fn["arguments"]},
                    })
                clean["tool_calls"] = cleaned_calls
            usage = data.get("usage") or {}
            estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
            input_tokens = int(usage.get("prompt_tokens", len(json.dumps([messages, tools], ensure_ascii=False)) // 3 + 1))
            output_tokens = int(usage.get("completion_tokens", len(json.dumps(clean, ensure_ascii=False)) // 3 + 1))
            if min(input_tokens, output_tokens) < 0:
                raise ValueError("invalid usage")
            return Reply(clean, input_tokens, output_tokens, estimated)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("模型响应缺少有效的 message、tool_calls 或 usage") from None
