"""The runtime depends on this one model interface, not a provider SDK."""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .tokens import estimate_json


class ModelError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, retry_after: float | None = None,
                 access_denied: bool = False, consume_output_budget: bool = True,
                 status: int | None = None, code: str | None = None, quota_exhausted: bool = False,
                 truncated: bool = False, usage: tuple[int, int] | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after
        self.access_denied = access_denied
        self.consume_output_budget = consume_output_budget
        self.status = status
        self.code = code
        self.quota_exhausted = quota_exhausted
        self.truncated = truncated
        self.usage = usage


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
        if (isinstance(value, str) and 1 <= len(value) <= 64 and value.isascii()
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
    cached_tokens: int = 0


class Model(Protocol):
    name: str

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 *, timeout: float | None = None) -> Reply: ...


class ChatModel:
    """OpenAI-compatible Chat Completions. Credentials never enter the trace."""

    supports_stream = True

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

    def _parse_reply(self, message: dict, finish_reason: str | None, usage: dict,
                     messages: list[dict], tools: list[dict]) -> Reply:
        if finish_reason == "length":
            counts = None
            try:
                input_use, output_use = int(usage["prompt_tokens"]), int(usage["completion_tokens"])
                if min(input_use, output_use) >= 0:
                    counts = (input_use, output_use)
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
            raise ModelError("模型输出达到单次上限，未接受不完整的回答或工具调用",
                             truncated=True, usage=counts)
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
        estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
        input_tokens = int(usage["prompt_tokens"]) if "prompt_tokens" in usage else estimate_json([messages, tools])
        output_tokens = int(usage["completion_tokens"]) if "completion_tokens" in usage else estimate_json(clean)
        if min(input_tokens, output_tokens) < 0:
            raise ValueError("invalid usage")
        details = usage.get("prompt_tokens_details")
        cached_tokens = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
        if type(cached_tokens) is not int or cached_tokens < 0:
            cached_tokens = 0
        return Reply(clean, input_tokens, output_tokens, estimated, cached_tokens)

    def _read_stream(self, response, on_delta) -> tuple[dict, str | None, dict]:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        calls_by_index: dict[int, dict] = {}
        finish_reason: str | None = None
        usage: dict = {}
        saw_chunk = False
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            if not isinstance(chunk, dict):
                raise ValueError("invalid stream chunk")
            saw_chunk = True
            if isinstance(chunk.get("usage"), dict) and chunk["usage"]:
                usage = chunk["usage"]
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                raise ValueError("invalid delta")
            reasoning = delta.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                reasoning_parts.append(reasoning)
                on_delta("reasoning", reasoning)
            text = delta.get("content")
            if isinstance(text, str) and text:
                content_parts.append(text)
                on_delta("text", text)
            for item in delta.get("tool_calls") or []:
                idx = item.get("index", len(calls_by_index))
                entry = calls_by_index.setdefault(idx, {
                    "id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                if isinstance(item.get("id"), str) and item["id"]:
                    entry["id"] = item["id"]
                if isinstance(item.get("type"), str) and item["type"]:
                    entry["type"] = item["type"]
                fn = item.get("function")
                if isinstance(fn, dict):
                    if isinstance(fn.get("name"), str) and fn["name"]:
                        entry["function"]["name"] += fn["name"]
                    if isinstance(fn.get("arguments"), str) and fn["arguments"]:
                        entry["function"]["arguments"] += fn["arguments"]
        if not saw_chunk or finish_reason is None:
            raise ModelError("模型流提前结束，未接受不完整的回答或工具调用", retryable=True)
        message: dict = {"role": "assistant", "content": "".join(content_parts)}
        if reasoning_parts:
            message["reasoning_content"] = "".join(reasoning_parts)
        if calls_by_index:
            message["tool_calls"] = [calls_by_index[i] for i in sorted(calls_by_index)]
        return message, finish_reason, usage

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 *, timeout: float | None = None, on_delta=None) -> Reply:
        payload = {"model": self.name, "messages": messages, "max_tokens": max_tokens}
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if on_delta is not None:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        request = Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urlopen(request, timeout=min(self.timeout, timeout) if timeout is not None else self.timeout) as response:
                if on_delta is not None:
                    message, finish_reason, usage = self._read_stream(response, on_delta)
                else:
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
                             consume_output_budget=exc.code >= 500, status=exc.code,
                             code=tag[2:-1] if tag else None) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            denied = isinstance(reason, PermissionError)
            timed_out = isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
            raise ModelError("模型接口连接失败或超时；请检查地址、代理及服务状态", retryable=not denied,
                             access_denied=denied, consume_output_budget=timed_out) from None
        except (ValueError, UnicodeError):
            raise ModelError("模型接口返回了无效 JSON") from None
        try:
            if on_delta is None:
                choice = data["choices"][0]
                message = choice["message"]
                finish_reason = choice.get("finish_reason")
                usage = data.get("usage") or {}
            return self._parse_reply(message, finish_reason, usage, messages, tools)
        except ModelError:
            raise
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("模型响应缺少有效的 message、tool_calls 或 usage") from None


class AnthropicModel:
    """Native Anthropic Messages API (/v1/messages) over stdlib urllib, normalized to Reply."""

    supports_stream = True
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, model: str, base_url: str, api_key: str, timeout: float = 60):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("模型地址必须是 http(s) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("请通过 API_KEY 提供凭据，模型地址不能包含凭据或查询参数")
        self.name = model
        trimmed = base_url.rstrip("/")
        self.url = trimmed + ("/messages" if trimmed.endswith("/v1") else "/v1/messages")
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def _convert_request(messages: list[dict], tools: list[dict]) -> tuple[str | None, list[dict], list[dict]]:
        system_parts: list[str] = []
        converted: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "system":
                text = str(msg.get("content", "")).strip()
                if text:
                    system_parts.append(text)
                continue
            if role == "user":
                block = {"type": "text", "text": str(msg.get("content", ""))}
                if converted and converted[-1]["role"] == "user":
                    converted[-1]["content"].append(block)
                else:
                    converted.append({"role": "user", "content": [block]})
                continue
            if role == "assistant":
                blocks: list[dict] = []
                text = msg.get("content") or ""
                if text:
                    blocks.append({"type": "text", "text": str(text)})
                for call in msg.get("tool_calls") or []:
                    fn = call["function"]
                    try:
                        parsed_input = json.loads(fn["arguments"])
                    except (TypeError, ValueError):
                        parsed_input = {}
                    if not isinstance(parsed_input, dict):
                        parsed_input = {"value": parsed_input}
                    blocks.append({"type": "tool_use", "id": call["id"], "name": fn["name"], "input": parsed_input})
                converted.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
                continue
            if role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": str(msg.get("content", "")),
                }
                if converted and converted[-1]["role"] == "user":
                    converted[-1]["content"].append(block)
                else:
                    converted.append({"role": "user", "content": [block]})
        for message in converted:
            if message["role"] == "user":
                message["content"].sort(key=lambda block: block["type"] != "tool_result")
        anthropic_tools = []
        for tool in tools:
            fn = tool["function"]
            anthropic_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return ("\n\n".join(system_parts) if system_parts else None), converted, anthropic_tools

    @staticmethod
    def _build_reply(text_parts: list[str], reasoning_parts: list[str], tool_uses: list[dict],
                     stop_reason: str | None, usage: dict, messages: list[dict], tools: list[dict]) -> Reply:
        input_raw = usage.get("input_tokens")
        output_raw = usage.get("output_tokens")
        cached = usage.get("cache_read_input_tokens", 0)
        cache_created = usage.get("cache_creation_input_tokens", 0)
        if type(cached) is not int or cached < 0:
            cached = 0
        if type(cache_created) is not int or cache_created < 0:
            cache_created = 0
        if isinstance(input_raw, int) and input_raw >= 0:
            input_raw += cached + cache_created
        if stop_reason == "max_tokens":
            counts = None
            if isinstance(input_raw, int) and isinstance(output_raw, int) and min(input_raw, output_raw) >= 0:
                counts = (input_raw, output_raw)
            raise ModelError("模型输出达到单次上限，未接受不完整的回答或工具调用",
                             truncated=True, usage=counts)
        clean: dict = {"role": "assistant", "content": "".join(text_parts)}
        if reasoning_parts:
            clean["reasoning_content"] = "".join(reasoning_parts)
        if tool_uses:
            seen = set()
            cleaned_calls = []
            for item in tool_uses:
                cid, name = item.get("id"), item.get("name")
                if not isinstance(cid, str) or not cid or cid in seen or not isinstance(name, str) or not name:
                    raise ValueError("invalid tool_use")
                seen.add(cid)
                raw_args = item.get("arguments")
                if raw_args is None:
                    raw_args = json.dumps(item.get("input") or {}, ensure_ascii=False)
                cleaned_calls.append({
                    "id": cid, "type": "function",
                    "function": {"name": name, "arguments": raw_args},
                })
            clean["tool_calls"] = cleaned_calls
        estimated = not (isinstance(input_raw, int) and isinstance(output_raw, int))
        input_tokens = input_raw if isinstance(input_raw, int) else estimate_json([messages, tools])
        output_tokens = output_raw if isinstance(output_raw, int) else estimate_json(clean)
        if min(input_tokens, output_tokens) < 0:
            raise ValueError("invalid usage")
        return Reply(clean, input_tokens, output_tokens, estimated, cached)

    def _read_stream(self, response, on_delta) -> tuple[list[str], list[str], list[dict], str | None, dict]:
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        blocks: dict[int, dict] = {}
        stop_reason: str | None = None
        usage: dict = {}
        stopped = False
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            event = json.loads(payload)
            if not isinstance(event, dict):
                raise ValueError("invalid anthropic stream chunk")
            kind = event.get("type")
            if kind == "error":
                detail = event.get("error")
                code = detail.get("type") if isinstance(detail, dict) else None
                raise ModelError("Anthropic 流返回错误，未接受不完整的回答或工具调用",
                                 retryable=code in ("overloaded_error", "rate_limit_error", "api_error"))
            if kind == "message_stop":
                stopped = True
                break
            if kind == "message_start":
                msg_usage = (event.get("message") or {}).get("usage")
                if isinstance(msg_usage, dict):
                    usage.update(msg_usage)
            elif kind == "content_block_start":
                idx = event.get("index", len(blocks))
                block = event.get("content_block") or {}
                if block.get("type") == "tool_use":
                    blocks[idx] = {"id": block.get("id", ""), "name": block.get("name", ""), "parts": []}
                elif block.get("type") == "text" and block.get("text"):
                    text_parts.append(block["text"])
                    on_delta("text", block["text"])
                elif block.get("type") == "thinking" and block.get("thinking"):
                    reasoning_parts.append(block["thinking"])
                    on_delta("reasoning", block["thinking"])
            elif kind == "content_block_delta":
                idx = event.get("index")
                delta = event.get("delta") or {}
                dtype = delta.get("type")
                if dtype == "text_delta" and isinstance(delta.get("text"), str):
                    text_parts.append(delta["text"])
                    on_delta("text", delta["text"])
                elif dtype == "thinking_delta" and isinstance(delta.get("thinking"), str):
                    reasoning_parts.append(delta["thinking"])
                    on_delta("reasoning", delta["thinking"])
                elif dtype == "input_json_delta" and idx in blocks and isinstance(delta.get("partial_json"), str):
                    blocks[idx]["parts"].append(delta["partial_json"])
            elif kind == "message_delta":
                delta = event.get("delta") or {}
                if delta.get("stop_reason") is not None:
                    stop_reason = delta["stop_reason"]
                if isinstance(event.get("usage"), dict):
                    usage.update(event["usage"])
        if not stopped and stop_reason != "max_tokens":
            raise ModelError("模型流提前结束，未接受不完整的回答或工具调用", retryable=True)
        tool_uses = [{"id": b["id"], "name": b["name"], "arguments": "".join(b["parts"]) or "{}"}
                     for _, b in sorted(blocks.items())]
        return text_parts, reasoning_parts, tool_uses, stop_reason, usage

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 *, timeout: float | None = None, on_delta=None) -> Reply:
        system_text, converted_messages, converted_tools = self._convert_request(messages, tools)
        payload: dict = {"model": self.name, "messages": converted_messages, "max_tokens": max_tokens}
        if system_text:
            payload["system"] = system_text
        if converted_tools:
            payload["tools"] = converted_tools
        if on_delta is not None:
            payload["stream"] = True
        request = Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.ANTHROPIC_VERSION,
            },
        )
        try:
            with urlopen(request, timeout=min(self.timeout, timeout) if timeout is not None else self.timeout) as response:
                if on_delta is not None:
                    text_parts, reasoning_parts, tool_uses, stop_reason, usage = self._read_stream(response, on_delta)
                else:
                    data = json.load(response)
        except HTTPError as exc:
            try:
                body = exc.read(4096) if exc.fp is not None else b""
                tag = safe_error_tag(body, self.api_key)
            except (OSError, AttributeError):
                tag = ""
            raise ModelError(f"模型接口返回 HTTP {exc.code}{tag}", retryable=exc.code in {429, 500, 502, 503, 504},
                             retry_after=retry_delay(exc.headers.get("Retry-After") if exc.headers else None),
                             access_denied=exc.code in {401, 403},
                             consume_output_budget=exc.code >= 500, status=exc.code,
                             code=tag[2:-1] if tag else None) from None
        except (URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            denied = isinstance(reason, PermissionError)
            timed_out = isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)
            raise ModelError("模型接口连接失败或超时；请检查地址、代理及服务状态", retryable=not denied,
                             access_denied=denied, consume_output_budget=timed_out) from None
        except (ValueError, UnicodeError):
            raise ModelError("模型接口返回了无效 JSON") from None
        try:
            if on_delta is None:
                text_parts, reasoning_parts, tool_uses = [], [], []
                for block in data["content"]:
                    btype = block.get("type")
                    if btype == "text" and isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                    elif btype == "thinking" and isinstance(block.get("thinking"), str):
                        reasoning_parts.append(block["thinking"])
                    elif btype == "tool_use":
                        tool_uses.append(block)
                stop_reason = data.get("stop_reason")
                usage = data.get("usage") or {}
            return self._build_reply(text_parts, reasoning_parts, tool_uses, stop_reason, usage, messages, tools)
        except ModelError:
            raise
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError("模型响应缺少有效的 content、tool_use 或 usage") from None
