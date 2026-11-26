"""One execution loop is shared by the main agent and read-only workers."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from typing import Callable

from .context import Context
from .models import Model, ModelError, Reply
from .store import Store
from .tokens import Calibrator, estimate_json
from .tools import Policy, Registry, Tool, ToolError, Workspace, integer, parameters, register_workspace_tools, string


@dataclass
class Limits:
    max_requests: int = 24
    max_tokens: int = 60000
    output_tokens: int = 2048
    context_chars: int = 28000
    max_seconds: int = 600
    model_attempts: int = 3
    truncation_retries: int = 2

    def __post_init__(self):
        if min(self.max_requests, self.max_tokens, self.output_tokens, self.max_seconds, self.model_attempts) < 1:
            raise ValueError("预算和超时必须大于 0")
        if self.context_chars < 2000:
            raise ValueError("上下文字符预算不能小于 2000")
        if self.truncation_retries < 0:
            raise ValueError("截断重试次数不能为负数")


@dataclass
class Result:
    session_id: str
    status: str
    answer: str
    verification: str
    changed_files: list[str]
    usage: dict


@dataclass
class LoopState:
    sid: str
    readonly: bool
    deadline: float
    local_requests: int = 0
    failed_attempts: int = 0
    truncations: int = 0
    recent_tools: list[tuple[str, str | None]] = field(default_factory=list)
    stall_warnings: set[tuple[str, str]] = field(default_factory=set)
    calibrator: Calibrator = field(default_factory=Calibrator)
    messages: list[dict] = field(default_factory=list)
    legacy_skills: dict[str, str] = field(default_factory=dict)
    event_cursor: int = 0
    status: str = "budget_exhausted"
    answer: str = "已达到任务预算。可增加预算后恢复会话。"


class Agent:
    def __init__(self, model: Model, workspace: Path, store: Store, policy: Policy | None = None,
                 limits: Limits | None = None, plugins: list[Path] | None = None,
                 observe: Callable | None = None, enable_delegate: bool = True, *, disabled_tools=(),
                 enable_bash: bool = False, tool_profile: str = "default", on_delta: Callable | None = None):
        if tool_profile not in {"default", "pi"}:
            raise ValueError("tool_profile 必须是 default 或 pi")
        self.model = model
        self.workspace = Workspace(workspace)
        self.store = store
        self.policy = policy or Policy()
        self.limits = limits or Limits()
        self.plugins = plugins or []
        self.observe = observe or (lambda kind, data: None)
        self.enable_delegate = enable_delegate
        self.disabled_tools = frozenset(disabled_tools)
        self.enable_bash = enable_bash
        self.tool_profile = tool_profile
        self.on_delta = on_delta
        self._model_access_error = None

    def _registry(self, sid: str, context: Context, readonly: bool, deadline: float) -> Registry:
        policy = Policy(readonly=True) if readonly else self.policy
        registry = Registry(self.workspace, policy)
        register_workspace_tools(registry, deadline=deadline, enable_bash=self.enable_bash,
                                 tool_profile=self.tool_profile)
        if readonly:
            registry.tools = {name: tool for name, tool in registry.tools.items() if tool.effect == "read"}

        if context.skills and self.tool_profile != "pi":
            def load_skill(name):
                result = context.load_skill(name)
                self.store.append(sid, "skill_loaded", {**result, "delivery": "message"})
                return {"name": result["name"], "loaded": True, "chars": len(result["instructions"])}

            registry.register(Tool("load_skill", "按名称加载已列出的 Skill 工作方法。", parameters({
                "name": string("Skill 目录名")}, ["name"]), load_skill))

        def read_artifact(artifact_id, offset=0, chars=4000):
            if offset < 0 or not 1 <= chars <= 6000:
                raise ToolError("offset 必须非负，chars 应在 1 到 6000 之间")
            text = self.store.read_artifact(sid, artifact_id)
            return {"artifact_id": artifact_id, "offset": offset,
                    "content": text[offset:offset + chars], "total_chars": len(text)}

        if self.tool_profile != "pi":
            registry.register(Tool("read_artifact", "分页读取本任务已保存的完整工具输出。", parameters({
                "artifact_id": string("工具结果中的产物 ID"), "offset": integer("字符偏移，默认 0"),
                "chars": integer("读取字符数，默认 4000，上限 6000")}, ["artifact_id"]), read_artifact))

        if not readonly:
            if self.enable_delegate and self.tool_profile != "pi":
                def delegate(task):
                    child = self.run(task, parent_id=sid, readonly=True, deadline=deadline)
                    return {"session_id": child.session_id, "status": child.status,
                            "summary": child.answer[:6000], "usage": child.usage}

                registry.register(Tool("delegate", "把一条独立的只读调查交给子任务。若要比较多份同名实现、追踪多条调用链"
                                       "或分页调查大型模块，优先委派其中一个明确的问题，再用结论定位并修改。"
                                       "子任务有独立上下文，共享总预算，最多 6 次模型请求。", parameters({
                    "task": string("仅委派一个调查目标，要求返回活跃文件路径、函数或测试证据及简要结论")}, ["task"]),
                    delegate, "delegate"))
            if self.tool_profile != "pi":
                for index, path in enumerate(self.plugins):
                    spec = importlib.util.spec_from_file_location(f"codeharness_extension_{index}", path)
                    if not spec or not spec.loader:
                        raise ValueError(f"无法加载扩展：{path}")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.register(registry)
        for name in self.disabled_tools:
            registry.tools.pop(name, None)
        return registry

    def tool_names(self) -> list[str]:
        context = Context(self.workspace.root, self.limits.context_chars)
        return list(self._registry("preview", context, False, time.monotonic() + 60).tools)

    def compact(self, sid: str, note: str = "") -> dict:
        context = Context(self.workspace.root, self.limits.context_chars)
        state = LoopState(sid, False, time.monotonic() + 60)
        self._sync_messages(state)
        before_count = len(state.messages)
        before_chars = len(json.dumps(state.messages, ensure_ascii=False))
        compacted, changed = context.compact_now(state.messages, note=note)
        if not changed:
            return {"compacted": False, "before_messages": before_count, "after_messages": before_count,
                    "before_chars": before_chars, "after_chars": before_chars}
        after_chars = len(json.dumps(compacted, ensure_ascii=False))
        self.store.append(sid, "compact_checkpoint", {"messages": compacted, "note": note})
        self.store.append(sid, "context_compacted", {"original_messages": before_count,
            "sent_messages": len(compacted), "strategy": "manual_compact"})
        return {"compacted": True, "before_messages": before_count, "after_messages": len(compacted),
                "before_chars": before_chars, "after_chars": after_chars}

    def run(self, task: str, session_id: str | None = None, parent_id: str | None = None,
            readonly: bool = False, deadline: float | None = None) -> Result:
        if not task.strip():
            raise ValueError("任务不能为空")
        if parent_id is None:
            self._model_access_error = None
        deadline = deadline or time.monotonic() + self.limits.max_seconds
        context = Context(self.workspace.root, self.limits.context_chars)
        sid, readonly, baseline = self._open_session(task, session_id, parent_id, readonly, context)
        state = LoopState(sid, readonly, deadline)
        if session_id:
            self._publish_skills(sid)
            self._restore_detectors(state)
        try:
            registry = self._registry(sid, context, readonly, deadline)
            while (reply := self._next_request(state, registry, context)) is not None:
                calls = reply.message.get("tool_calls", [])
                if not calls:
                    state.status = "completed"
                    state.answer = reply.message.get("content", "") or "模型已结束本轮任务。"
                    break
                if self._execute_calls(state, registry, calls):
                    break
        except KeyboardInterrupt:
            state.status = "cancelled"
            state.answer = "任务已中断，运行记录已保存。恢复前会检查未完成工具调用。"
        except Exception as exc:
            state.status, state.answer = "error", str(exc)
        return self._finalize(state, baseline)

    def _open_session(self, task: str, session_id: str | None, parent_id: str | None,
                      readonly: bool, context: Context) -> tuple[str, bool, dict]:
        snapshot = self.workspace.snapshot(use_cache=False)
        if session_id:
            session = self.store.session(session_id)
            if Path(session["workspace"]).resolve() != self.workspace.root:
                raise ValueError("恢复时的工作区与原会话不一致")
            readonly = bool(session["parent_id"])
            sid = session_id
            self.store.repair_pending(sid)
            events = self.store.events(sid, expand=False)
            baselines = [e["data"] for e in events if e["kind"] == "baseline"]
            previous = self.store.files_at(sid)
            if previous is None:
                previous = baselines[0]["files"] if baselines else snapshot
            changed = sorted(p for p in previous.keys() | snapshot.keys() if previous.get(p) != snapshot.get(p))
            if changed:
                self.store.append(sid, "message", {"role": "user", "content":
                    "恢复检查：以下文件与上次检查点不同，继续前重新读取：" + json.dumps(changed, ensure_ascii=False)})
            self.store.append(sid, "message", {"role": "user", "content": task})
        else:
            sid = self.store.create(self.workspace.root, self.model.name, parent_id)
            self.store.append(sid, "message", {"role": "system", "content": context.system(
                readonly, tool_profile=self.tool_profile, enable_bash=self.enable_bash)})
            self.store.append(sid, "message", {"role": "user", "content": task})
            self._save_snapshot(sid, "baseline", snapshot)
        self.store.status(sid, "running")
        self.observe("session", {"id": sid, "readonly": readonly})
        baseline = next(e["data"]["files"] for e in self.store.events(sid, expand=False) if e["kind"] == "baseline")
        return sid, readonly, baseline

    def _save_snapshot(self, sid: str, kind: str, files: dict):
        self.store.append(sid, kind, {"files": files})
        if len(files) > 20000:
            self.store.append(sid, "workspace_warning", {"files": len(files),
                "message": "快照超过 20000 个文件。请缩小工作区或用 .gitignore 排除生成物。"})

    def _publish_skills(self, sid: str):
        events = self.store.events(sid, expand=False)
        published = {e["data"]["name"] for e in events if e["kind"] == "skill_injected" or
                     (e["kind"] == "skill_loaded" and e["data"].get("delivery") != "message")}
        for event in events:
            if event["kind"] != "skill_loaded" or event["data"].get("delivery") != "message":
                continue
            data = event["data"]
            name = data["name"]
            if name not in published:
                message = {"role": "user", "content": f"[已加载 Skill：{name}]\n" + data["instructions"]}
                self.store.append(sid, "skill_injected", {"name": name, "message": message})
                published.add(name)

    @staticmethod
    def _tool_signature(name: str, args, outcome: dict) -> str:
        packed = json.dumps([name, args, outcome], ensure_ascii=False, sort_keys=True)
        return sha256(packed.encode("utf-8")).hexdigest()

    def _restore_detectors(self, state: LoopState):
        events = self.store.events(state.sid, expand=False)
        self._sync_messages(state, events)
        finished = [event["data"] for event in events if event["kind"] == "tool_finished"][-5:]
        legacy_ids = {row["call_id"] for row in finished if "signature" not in row}
        legacy_args = {}
        pending_estimate = None
        for event in events:
            data = event["data"]
            if event["kind"] == "model_request":
                pending_estimate = data.get("raw_estimated_input")
            elif event["kind"] == "usage" and pending_estimate is not None:
                if not data.get("estimated"):
                    state.calibrator.observe(pending_estimate, data["input_tokens"])
                pending_estimate = None
            elif event["kind"] == "model_truncated":
                state.truncations += 1
            elif event["kind"] == "tool_stall_warning":
                state.stall_warnings.add((data["kind"], data["key"]))
            elif event["kind"] == "message" and data.get("role") == "assistant":
                state.truncations = 0
                for call in data.get("tool_calls", []):
                    if call["id"] not in legacy_ids:
                        continue
                    raw = call["function"]["arguments"]
                    try:
                        legacy_args[call["id"]] = json.loads(raw)
                    except (TypeError, ValueError):
                        legacy_args[call["id"]] = raw
        for row in finished:
            result = row["result"]
            signature = row.get("signature")
            if not signature:
                outcome = {key: value for key, value in result.items() if key != "artifact_id"}
                if result.get("truncated") and result.get("artifact_id"):
                    try:
                        outcome = json.loads(self.store.read_artifact(state.sid, result["artifact_id"]))
                    except ValueError:
                        pass
                signature = self._tool_signature(row["name"], legacy_args.get(row["call_id"]), outcome)
            state.recent_tools.append((signature, result.get("error")))

    def _sync_messages(self, state: LoopState, events: list[dict] | None = None):
        if events is None:
            events = self.store.events(state.sid, after=state.event_cursor, expand=False)
        for event in events:
            data = event["data"]
            if event["kind"] == "compact_checkpoint":
                state.messages = [dict(message) for message in data["messages"]]
            elif event["kind"] == "message":
                state.messages.append(data)
            elif event["kind"] == "skill_injected":
                state.messages.append(data["message"])
            elif event["kind"] == "skill_loaded" and data.get("delivery") != "message":
                state.legacy_skills[data["name"]] = data["instructions"]
            state.event_cursor = event["id"]

    def _can_request(self, state: LoopState, usage: dict) -> bool:
        return usage["requests"] < self.limits.max_requests and (not state.readonly or state.local_requests < 6)

    @staticmethod
    def _timed_out(state: LoopState, message="已达到任务时间上限。", *, seconds_left=None) -> bool:
        if seconds_left is None:
            seconds_left = state.deadline - time.monotonic()
        if seconds_left > 0:
            return False
        state.status, state.answer = "timeout", message
        return True

    def _next_request(self, state: LoopState, registry: Registry, context: Context) -> Reply | None:
        sid = state.sid
        retry_output_cap = min(2 * self.limits.output_tokens, 8192)
        output_cap = retry_output_cap if state.truncations == 1 else self.limits.output_tokens
        while True:
            if self._model_access_error:
                state.status, state.answer = "error", self._model_access_error
                return None
            usage = self.store.usage(sid)
            if not self._can_request(state, usage) or self._timed_out(state):
                return None
            self._sync_messages(state)
            messages = state.messages
            if state.legacy_skills:
                messages = list(messages)
                messages[0] = dict(messages[0])
                messages[0]["content"] += "\n\n已加载 Skills：\n" + "\n".join(state.legacy_skills.values())
            prepared, compacted = context.prepare(messages)
            schemas = registry.schemas()
            raw_estimate = estimate_json([prepared, schemas])
            estimated_input = state.calibrator.adjust(raw_estimate)
            remaining = self.limits.max_tokens - usage["input_tokens"] - usage["output_tokens"] - estimated_input
            min_output = min(256, self.limits.output_tokens)
            if remaining < min_output:
                return None
            output_tokens = min(output_cap, remaining)
            output_cap = self.limits.output_tokens
            if compacted:
                self.store.append(sid, "context_compacted", {"original_messages": len(messages),
                    "sent_messages": len(prepared), "strategy": "keep_user_constraints_and_recent_turns"})
            prepare_attempt = getattr(self.model, "prepare_attempt", None)
            if prepare_attempt is not None:
                previous_model = self.model.name
                try:
                    prepare_attempt(estimated_input, output_tokens)
                except ModelError as exc:
                    self.store.append(sid, "model_error", {"attempt": 0, "error": str(exc),
                        "retryable": exc.retryable, "access_denied": exc.access_denied,
                        "quota_exhausted": exc.quota_exhausted, "preflight": True})
                    raise
                if self.model.name != previous_model:
                    self.observe("model_switch", {"previous": previous_model, "model": self.model.name})
            seconds_left = state.deadline - time.monotonic()
            if self._timed_out(state, seconds_left=seconds_left):
                return None
            # Each physical model attempt counts towards the shared budget.
            self.store.append(sid, "model_request", {"model": self.model.name,
                "messages": prepared, "tools": schemas, "max_tokens": output_tokens,
                "estimated_input": estimated_input, "raw_estimated_input": raw_estimate,
                "remaining_seconds": seconds_left})
            state.local_requests += 1
            try:
                if self.on_delta is not None and not state.readonly and getattr(self.model, "supports_stream", False):
                    reply = self.model.complete(prepared, schemas, output_tokens,
                                                timeout=seconds_left, on_delta=self.on_delta)
                else:
                    reply = self.model.complete(prepared, schemas, output_tokens, timeout=seconds_left)
            except ModelError as exc:
                if exc.truncated:
                    if exc.usage is not None:
                        state.calibrator.observe(raw_estimate, exc.usage[0])
                    if not self._recover_truncation(state, exc, estimated_input, output_tokens):
                        return None
                    if state.truncations == 1:
                        output_cap = retry_output_cap
                    continue
                if not self._retry(state, exc, estimated_input, output_tokens, min_output):
                    return None
                continue
            state.failed_attempts = 0
            state.truncations = 0
            if not reply.estimated:
                state.calibrator.observe(raw_estimate, reply.input_tokens)
            self.store.append(sid, "usage", {"input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens, "estimated": reply.estimated, "cached_tokens": reply.cached_tokens})
            self.store.append(sid, "message", reply.message)
            return None if self._timed_out(state) else reply

    def _recover_truncation(self, state: LoopState, exc: ModelError, estimated_input: int, output_tokens: int) -> bool:
        state.truncations += 1
        input_use, output_use = exc.usage or (estimated_input, output_tokens)
        self.store.append(state.sid, "usage", {"input_tokens": input_use, "output_tokens": output_use,
            "estimated": exc.usage is None, "failed_attempt": True})
        self.store.append(state.sid, "model_truncated", {"attempt": state.truncations, "max_tokens": output_tokens})
        if self._timed_out(state):
            return False
        if state.truncations > self.limits.truncation_retries:
            state.status, state.answer = "error", "模型输出连续被截断"
            return False
        self.store.append(state.sid, "message", {"role": "user", "content":
            "上一次回复达到单次输出上限被截断，已丢弃。请使用当前可用的编辑工具分多次修改，每次只改一处。"})
        return True

    def _retry(self, state: LoopState, exc: ModelError, estimated_input: int, output_tokens: int,
               min_output: int) -> bool:
        sid = state.sid
        state.failed_attempts += 1
        if exc.access_denied:
            self._model_access_error = str(exc)
        self.store.append(sid, "model_error", {"attempt": state.failed_attempts, "error": str(exc),
            "retryable": exc.retryable, "access_denied": exc.access_denied, "quota_exhausted": exc.quota_exhausted})
        # Reserve output only when a provider may have generated tokens.
        input_use, output_use = (estimated_input, output_tokens) if exc.consume_output_budget else (0, 0)
        self.store.append(sid, "usage", {"input_tokens": input_use, "output_tokens": output_use,
            "estimated": True, "failed_attempt": True})
        if self._timed_out(state):
            return False
        if exc.access_denied or not exc.retryable or state.failed_attempts >= self.limits.model_attempts:
            raise exc
        usage = self.store.usage(sid)
        if (not self._can_request(state, usage)
                or self.limits.max_tokens - usage["input_tokens"] - usage["output_tokens"] < estimated_input + min_output):
            return False
        delay = exc.retry_after if exc.retry_after is not None else 0.5 * 2 ** (state.failed_attempts - 1)
        if self._timed_out(state, "剩余任务时间不足以等待模型重试。",
                           seconds_left=state.deadline - time.monotonic() - delay):
            return False
        self.store.append(sid, "model_retry", {"next_attempt": state.failed_attempts + 1, "delay_seconds": delay})
        time.sleep(delay)
        return True

    def _execute_calls(self, state: LoopState, registry: Registry, calls: list[dict]) -> bool:
        sid = state.sid
        warnings = []
        loaded_skill = False
        parallel = len(calls) > 1 and not (registry.before or registry.after) and all(
            (tool := registry.tools.get(call["function"]["name"])) is not None
            and tool.effect == "read" and tool.parallel_safe for call in calls)
        outcomes = []
        if parallel:
            scheduled = []
            for call in calls:
                if self._timed_out(state):
                    break
                self._start_call(sid, registry, call)
                scheduled.append(call)
            calls = scheduled
            with ThreadPoolExecutor(max_workers=4) as executor:
                outcomes = list(executor.map(lambda call: self._invoke_call(registry, call), calls))

        for index, call in enumerate(calls):
            if parallel:
                args, outcome = outcomes[index]
            else:
                if self._timed_out(state):
                    return True
                self._start_call(sid, registry, call)
                args, outcome = self._invoke_call(registry, call)
            signature, result = self._record_call(state, registry, call, args, outcome)
            loaded_skill |= call["function"]["name"] == "load_skill" and result["ok"]
            if self._model_access_error:
                state.status, state.answer = "error", self._model_access_error
                return True
            if self._timed_out(state):
                if parallel:
                    continue
                return True
            if self._track_stall(state, signature, result.get("error"), warnings):
                state.status, state.answer = "stalled", "工具已连续 5 次返回相同结果，任务已停止。"
                if not parallel:
                    self.store.repair_pending(sid)
                    break
        for kind, key, message in warnings:
            self.store.append(sid, "tool_stall_warning", {"kind": kind, "key": key})
            self.store.append(sid, "message", {"role": "user", "content": message})
        if loaded_skill:
            self._publish_skills(sid)
        return state.status in {"stalled", "timeout"}

    def _start_call(self, sid: str, registry: Registry, call: dict):
        name = call["function"]["name"]
        tool = registry.tools.get(name)
        raw_args = call["function"].get("arguments")
        try:
            parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except ValueError:
            parsed_args = None
        self.store.append(sid, "tool_started", {"call_id": call["id"], "name": name,
            "effect": tool.effect if tool is not None else None})
        self.observe("tool", {"session_id": sid, "name": name, "arguments": parsed_args})

    @staticmethod
    def _tool_failure(exc: Exception) -> dict:
        expected = isinstance(exc, (ToolError, ValueError, TypeError, OSError, subprocess.TimeoutExpired))
        message = str(exc) if expected else f"{type(exc).__name__}: {exc}"
        return {"ok": False, "error": message[:1000]}

    def _invoke_call(self, registry: Registry, call: dict) -> tuple:
        args = call["function"]["arguments"]
        try:
            args = json.loads(args)
            return args, {"ok": True, "output": registry.invoke(call["function"]["name"], args)}
        except Exception as exc:
            return args, self._tool_failure(exc)

    def _record_call(self, state: LoopState, registry: Registry, call: dict, args, outcome: dict) -> tuple:
        sid = state.sid
        name, cid = call["function"]["name"], call["id"]
        tool = registry.tools.get(name)
        run_tests_snapshot = None
        result = outcome
        if outcome["ok"]:
            try:
                output = outcome["output"]
                full = json.dumps(outcome, ensure_ascii=False)
                aid = self.store.artifact(sid, full)
                result = {"ok": True, "artifact_id": aid}
                if len(full) > 6500:
                    result.update({"preview": full[:6000], "truncated": True})
                else:
                    result["output"] = output
                if name == "run_tests":
                    run_tests_snapshot = self.workspace.snapshot(use_cache=False)
                    self.store.append(sid, "verification", {"passed": output["passed"],
                        "files": run_tests_snapshot, "artifact_id": aid})
            except Exception as exc:
                result = self._tool_failure(exc)
        if name == "run_tests" and tool and not result["ok"]:
            run_tests_snapshot = self.workspace.snapshot(use_cache=False)
            self.store.append(sid, "verification", {"passed": False, "files": run_tests_snapshot, "artifact_id": None})
        signature = self._tool_signature(name, args, json.loads(full) if result["ok"] else result)
        self.store.append(sid, "tool_finished", {"call_id": cid, "name": name, "result": result, "signature": signature})
        self.store.append(sid, "message", {"role": "tool", "tool_call_id": cid,
            "content": json.dumps(result, ensure_ascii=False)})
        if tool and tool.effect in {"write", "execute"}:
            files = run_tests_snapshot if run_tests_snapshot is not None else self.workspace.snapshot(use_cache=(tool.effect == "write"))
            self._save_snapshot(sid, "checkpoint", files)
        return signature, result

    @staticmethod
    def _track_stall(state: LoopState, signature: str, error: str | None, warnings: list) -> bool:
        recent = state.recent_tools
        recent.append((signature, error))
        del recent[:-5]

        def warn(kind, key, message):
            if (kind, key) not in state.stall_warnings:
                warnings.append((kind, key, message))
                state.stall_warnings.add((kind, key))

        if len(recent) >= 3 and all(item[0] == signature for item in recent[-3:]):
            warn("signature", signature, "你已重复相同操作 3 次且结果相同，请换一种方法或说明阻塞原因。")
        if error and len(recent) >= 4 and all(item[1] == error for item in recent[-4:]):
            warn("error", error, "工具连续 4 次返回相同错误，请换一种方法或说明阻塞原因。")
        return len(recent) == 5 and all(item[0] == signature for item in recent)

    def _finalize(self, state: LoopState, baseline: dict) -> Result:
        sid = state.sid
        status, answer = state.status, state.answer
        current = self.workspace.snapshot(use_cache=False)
        changes = sorted(p for p in baseline.keys() | current.keys() if baseline.get(p) != current.get(p))
        checks = [e["data"] for e in self.store.events(sid, expand=False) if e["kind"] == "verification"]
        verification = "not_run"
        if checks:
            verification = "passed" if checks[-1]["passed"] else "failed"
            if checks[-1]["files"] != current:
                verification = "stale"
        if status == "completed" and changes:
            status = "verified" if verification == "passed" else "unverified"
        self._save_snapshot(sid, "checkpoint", current)
        self.store.append(sid, "result", {"status": status, "answer": answer, "verification": verification,
            "changed_files": changes})
        self.store.status(sid, status)
        return Result(sid, status, answer, verification, changes, self.store.usage(sid))
