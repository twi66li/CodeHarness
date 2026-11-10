"""The runtime depends on this one model interface, not a provider SDK."""

from dataclasses import dataclass
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ModelError(RuntimeError):
    pass


@dataclass
class Reply:
    message: dict
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False


class Model(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int) -> Reply: ...


class ChatModel:
    """OpenAI-compatible Chat Completions. Credentials never enter the trace."""

    def __init__(self, model: str, base_url: str, api_key: str, timeout: float = 60):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("模型地址必须是 http(s) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("请通过 API_KEY 提供凭据，模型地址不能包含凭据或查询参数")
        self.name = model
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int) -> Reply:
        payload = {"model": self.name, "messages": messages, "max_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as exc:
            # Provider bodies and URLs can contain credentials; do not persist them.
            raise ModelError(f"模型接口返回 HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ModelError("模型接口连接失败或超时；请检查地址、代理及服务状态") from None
        except (ValueError, UnicodeError):
            raise ModelError("模型接口返回了无效 JSON") from None
        try:
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ModelError("模型输出达到单次上限，未接受不完整的回答或工具调用")
            message = choice["message"]
            clean = {"role": "assistant", "content": message.get("content") or ""}
            calls = message.get("tool_calls") or []
            if calls:
                seen = set()
                for call in calls:
                    if call["type"] != "function" or not call["id"] or call["id"] in seen:
                        raise ValueError("invalid tool call")
                    seen.add(call["id"])
                    if not isinstance(call["function"]["arguments"], str):
                        raise ValueError("invalid arguments")
                clean["tool_calls"] = calls
            usage = data.get("usage") or {}
            estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
            return Reply(
                clean,
                int(usage.get("prompt_tokens", len(json.dumps(messages, ensure_ascii=False)) // 3 + 1)),
                int(usage.get("completion_tokens", len(json.dumps(clean, ensure_ascii=False)) // 3 + 1)),
                estimated,
            )
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("模型响应缺少有效的 message、tool_calls 或 usage") from None
