"""One execution loop is shared by the main agent and read-only workers."""

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from typing import Callable

from .context import Context
from .models import Model, ModelError, Reply
from .store import Store
from .tools import Policy, Registry, Tool, ToolError, Workspace, integer, parameters, register_workspace_tools, string


@dataclass
class Limits:
    max_requests: int = 24
    max_tokens: int = 60000
    output_tokens: int = 2048
    context_chars: int = 28000
    max_seconds: int = 600
    model_attempts: int = 3

    def __post_init__(self):
        if min(self.max_requests, self.max_tokens, self.output_tokens, self.max_seconds, self.model_attempts) < 1:
            raise ValueError("预算和超时必须大于 0")
        if self.context_chars < 2000:
            raise ValueError("上下文字符预算不能小于 2000")


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
    status: str = "budget_exhausted"
    answer: str = "已达到任务预算。可增加预算后恢复会话。"


class Agent:
    def __init__(self, model: Model, workspace: Path, store: Store, policy: Policy | None = None,
                 limits: Limits | None = None, plugins: list[Path] | None = None,
                 observe: Callable | None = None, enable_delegate: bool = True):
        self.model = model
        self.workspace = Workspace(workspace)
        self.store = store
        self.policy = policy or Policy()
        self.limits = limits or Limits()
        self.plugins = plugins or []
        self.observe = observe or (lambda kind, data: None)
        self.enable_delegate = enable_delegate
        self._model_access_error = None

    def _registry(self, sid: str, context: Context, readonly: bool, deadline: float) -> Registry:
        policy = Policy(readonly=True) if readonly else self.policy
        registry = Registry(self.workspace, policy)
        register_workspace_tools(registry, deadline=deadline)
        if readonly:
            registry.tools = {name: tool for name, tool in registry.tools.items() if tool.effect == "read"}

        def load_skill(name):
            result = context.load_skill(name)
            self.store.append(sid, "skill_loaded", result)
            return {"name": result["name"], "loaded": True, "chars": len(result["instructions"])}

        def read_artifact(artifact_id, offset=0, chars=4000):
            if offset < 0 or not 1 <= chars <= 6000:
                raise ToolError("offset 必须非负，chars 应在 1 到 6000 之间")
            text = self.store.read_artifact(sid, artifact_id)
            return {"artifact_id": artifact_id, "offset": offset,
                    "content": text[offset:offset + chars], "total_chars": len(text)}

        registry.register(Tool("load_skill", "按名称加载已列出的 Skill 工作方法。", parameters({
            "name": string("Skill 目录名")}, ["name"]), load_skill))
        registry.register(Tool("read_artifact", "分页读取本任务已保存的完整工具输出。", parameters({
            "artifact_id": string("工具结果中的产物 ID"), "offset": integer("字符偏移，默认 0"),
            "chars": integer("读取字符数，默认 4000，上限 6000")}, ["artifact_id"]), read_artifact))

        if not readonly:
            if self.enable_delegate:
                def delegate(task):
                    child = self.run(task, parent_id=sid, readonly=True, deadline=deadline)
                    return {"session_id": child.session_id, "status": child.status,
                            "summary": child.answer[:6000], "usage": child.usage}

                registry.register(Tool("delegate", "委派只读代码探索；独立上下文，共享总预算，最多 6 次模型请求。", parameters({
                    "task": string("明确的调查目标与需要返回的证据")}, ["task"]), delegate, "delegate"))
            for index, path in enumerate(self.plugins):
                spec = importlib.util.spec_from_file_location(f"codeharness_extension_{index}", path)
                if not spec or not spec.loader:
                    raise ValueError(f"无法加载扩展：{path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.register(registry)
        return registry

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
            events = self.store.events(sid)
            checkpoints = [e["data"] for e in events if e["kind"] == "checkpoint"]
            baselines = [e["data"] for e in events if e["kind"] == "baseline"]
            previous = checkpoints[-1]["files"] if checkpoints else (baselines[0]["files"] if baselines else snapshot)
            changed = sorted(p for p in previous.keys() | snapshot.keys() if previous.get(p) != snapshot.get(p))
            if changed:
                self.store.append(sid, "message", {"role": "user", "content":
                    "恢复检查：以下文件与上次检查点不同，继续前重新读取：" + json.dumps(changed, ensure_ascii=False)})
            self.store.append(sid, "message", {"role": "user", "content": task})
        else:
            sid = self.store.create(self.workspace.root, self.model.name, parent_id)
            self.store.append(sid, "message", {"role": "system", "content": context.system(readonly)})
            self.store.append(sid, "message", {"role": "user", "content": task})
            self.store.append(sid, "baseline", {"files": snapshot})
        self.store.status(sid, "running")
        self.observe("session", {"id": sid, "readonly": readonly})
        baseline = next(e["data"]["files"] for e in self.store.events(sid) if e["kind"] == "baseline")
        return sid, readonly, baseline

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
        while True:
            if self._model_access_error:
                state.status, state.answer = "error", self._model_access_error
                return None
            usage = self.store.usage(sid)
            if not self._can_request(state, usage) or self._timed_out(state):
                return None
            messages = self.store.messages(sid)
            loaded = {e["data"]["name"]: e["data"]["instructions"] for e in self.store.events(sid)
                      if e["kind"] == "skill_loaded"}
            if loaded:
                messages[0] = dict(messages[0])
                messages[0]["content"] += "\n\n已加载 Skills：\n" + "\n".join(loaded.values())
            prepared, compacted = context.prepare(messages)
            schemas = registry.schemas()
            estimated_input = len(json.dumps([prepared, schemas], ensure_ascii=False)) // 3 + 1
            remaining = self.limits.max_tokens - usage["input_tokens"] - usage["output_tokens"] - estimated_input
            min_output = min(256, self.limits.output_tokens)
            if remaining < min_output:
                return None
            output_tokens = min(self.limits.output_tokens, remaining)
            if compacted:
                self.store.append(sid, "context_compacted", {"original_messages": len(messages),
                    "sent_messages": len(prepared), "strategy": "keep_user_constraints_and_recent_turns"})
            prepare_attempt = getattr(self.model, "prepare_attempt", None)
            if prepare_attempt is not None:
                previous_model = self.model.name
                prepare_attempt(estimated_input + output_tokens)
                if self.model.name != previous_model:
                    self.observe("model_switch", {"previous": previous_model, "model": self.model.name})
            seconds_left = state.deadline - time.monotonic()
            if self._timed_out(state, seconds_left=seconds_left):
                return None
            # Each physical model attempt counts towards the shared budget.
            self.store.append(sid, "model_request", {"model": self.model.name,
                "messages": prepared, "tools": schemas, "max_tokens": output_tokens,
                "remaining_seconds": seconds_left})
            state.local_requests += 1
            try:
                reply = self.model.complete(prepared, schemas, output_tokens, timeout=seconds_left)
            except ModelError as exc:
                if not self._retry(state, exc, estimated_input, output_tokens, min_output):
                    return None
                continue
            state.failed_attempts = 0
            self.store.append(sid, "usage", {"input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens, "estimated": reply.estimated})
            self.store.append(sid, "message", reply.message)
            return None if self._timed_out(state) else reply

    def _retry(self, state: LoopState, exc: ModelError, estimated_input: int, output_tokens: int,
               min_output: int) -> bool:
        sid = state.sid
        state.failed_attempts += 1
        if exc.access_denied:
            self._model_access_error = str(exc)
        self.store.append(sid, "model_error", {"attempt": state.failed_attempts, "error": str(exc),
            "retryable": exc.retryable, "access_denied": exc.access_denied})
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
        for call in calls:
            if self._timed_out(state):
                return True
            name, cid = call["function"]["name"], call["id"]
            tool = registry.tools.get(name)
            self.store.append(sid, "tool_started", {"call_id": cid, "name": name})
            self.observe("tool", {"session_id": sid, "name": name})
            run_tests_snapshot = None
            try:
                args = json.loads(call["function"]["arguments"])
                output = registry.invoke(name, args)
                full = json.dumps({"ok": True, "output": output}, ensure_ascii=False)
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
            except (ToolError, ValueError, TypeError, OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
                result = {"ok": False, "error": str(exc)[:1000]}
            except Exception as exc:
                result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:1000]}
            if name == "run_tests" and tool and not result["ok"]:
                run_tests_snapshot = self.workspace.snapshot(use_cache=False)
                self.store.append(sid, "verification", {"passed": False, "files": run_tests_snapshot,
                    "artifact_id": None})
            self.store.append(sid, "tool_finished", {"call_id": cid, "name": name, "result": result})
            self.store.append(sid, "message", {"role": "tool", "tool_call_id": cid,
                "content": json.dumps(result, ensure_ascii=False)})
            if tool and tool.effect in {"write", "execute"}:
                snap = run_tests_snapshot if run_tests_snapshot is not None else self.workspace.snapshot(
                    use_cache=(tool.effect == "write"))
                self.store.append(sid, "checkpoint", {"files": snap})
            if self._model_access_error:
                state.status, state.answer = "error", self._model_access_error
                return True
            if self._timed_out(state):
                return True
        return False

    def _finalize(self, state: LoopState, baseline: dict) -> Result:
        sid = state.sid
        status, answer = state.status, state.answer
        current = self.workspace.snapshot(use_cache=False)
        changes = sorted(p for p in baseline.keys() | current.keys() if baseline.get(p) != current.get(p))
        checks = [e["data"] for e in self.store.events(sid) if e["kind"] == "verification"]
        verification = "not_run"
        if checks:
            verification = "passed" if checks[-1]["passed"] else "failed"
            if checks[-1]["files"] != current:
                verification = "stale"
        if status == "completed" and changes:
            status = "verified" if verification == "passed" else "unverified"
        self.store.append(sid, "checkpoint", {"files": current})
        self.store.append(sid, "result", {"status": status, "answer": answer, "verification": verification,
            "changed_files": changes})
        self.store.status(sid, status)
        return Result(sid, status, answer, verification, changes, self.store.usage(sid))
