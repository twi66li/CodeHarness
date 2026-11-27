import argparse
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .demo import DemoModel, create_demo
from .model_pool import ModelPool
from .models import AnthropicModel, ChatModel
from .runtime import Agent, Limits
from .sandbox import DockerExecutor
from .store import Store
from .tools import Policy, shell_command, test_subprocess_env


def load_env(path: Path | None) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if path is None:
        return loaded
    lines = iter(path.read_text(encoding="utf-8-sig").splitlines())
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not name.strip().isidentifier():
            raise ValueError("环境配置文件应每行使用 NAME=value 格式")
        value = value.strip()
        if value.startswith(("'", '"')):
            quote = value[0]
            rest = value[1:]
            closing = rest.rfind(quote)
            if closing != -1 and (not rest[closing + 1:].strip() or rest[closing + 1:].lstrip().startswith("#")):
                value = rest[:closing]
            else:
                parts = [rest]
                while True:
                    continuation = next(lines, None)
                    if continuation is None:
                        raise ValueError("环境配置文件中有未闭合的引号")
                    parts.append(continuation)
                    tail = continuation.rstrip()
                    if tail.endswith(quote):
                        parts[-1] = tail[:-1]
                        break
                    idx = continuation.rfind(quote)
                    if idx != -1 and continuation[idx + 1:].lstrip().startswith("#"):
                        parts[-1] = continuation[:idx]
                        break
                value = "\n".join(parts)
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        loaded[name.strip()] = value
    return loaded


def model_connection(env: dict[str, str], base_url: str | None, provider: str = "openai") -> tuple[str | None, str]:
    if provider == "anthropic":
        url = base_url or env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        return url, env.get("ANTHROPIC_API_KEY", "")
    url = base_url or env.get("CODEHARNESS_BASE_URL") or env.get("OPENAI_BASE_URL")
    if url:
        return url, env.get("CODEHARNESS_API_KEY") or env.get("OPENAI_API_KEY", "")
    return env.get("DASHSCOPE_BASE_URL"), env.get("DASHSCOPE_API_KEY", "")


def build_model(model_name: str, *, provider: str, env: dict[str, str], base_url: str | None,
                timeout: float, reasoning_effort: str | None):
    if model_name == "offline-demo":
        return DemoModel()
    url, key = model_connection(env, base_url, provider=provider)
    if not model_name or not url:
        raise ValueError("请设置模型名与接口地址。可先运行 python -m codeharness demo 检查离线流程。")
    if provider == "anthropic":
        return AnthropicModel(model_name, url, key, timeout=timeout)
    return ChatModel(model_name, url, key, timeout=timeout, reasoning_effort=reasoning_effort)


def isolated_workspace(workspace: Path) -> Path:
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=workspace,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode or Path(result.stdout.strip()).resolve() != workspace:
        raise ValueError("--isolate 要求 workspace 是 Git 仓库根目录")
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=workspace,
                            capture_output=True, text=True, encoding="utf-8", check=True)
    dirty = [line for line in status.stdout.splitlines()
             if line.strip() and not (line == "?? .codeharness" or line.startswith("?? .codeharness/"))]
    if dirty:
        raise ValueError("隔离工作区从 HEAD 创建，请先提交或保存当前改动")
    destination = workspace / ".codeharness" / "worktrees" / uuid.uuid4().hex[:10]
    result = subprocess.run(["git", "worktree", "add", "--detach", str(destination), "HEAD"],
                            cwd=workspace, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise ValueError("无法创建隔离工作区：" + result.stderr[:400])
    return destination.resolve()


def trace_timeline(events):
    fields = {
        "model_request": ("turn", "attempt", "model", "max_tokens"),
        "usage": ("turn", "input_tokens", "output_tokens", "cached_tokens", "duration_ms"),
        "model_error": ("turn", "attempt", "retryable", "quota_exhausted", "preflight", "duration_ms"),
        "model_retry": ("turn", "next_attempt", "delay_seconds"),
        "model_truncated": ("turn", "attempt", "max_tokens", "duration_ms"),
        "context_compacted": ("original_messages", "sent_messages"),
        "tool_started": ("turn", "name", "call_id"),
        "tool_finished": ("turn", "name", "call_id", "duration_ms"),
        "verification": ("passed",),
        "result": ("status", "verification"),
    }
    for event in events:
        kind, data = event["kind"], event["data"]
        if kind not in fields:
            continue
        details = {key: data[key] for key in fields[kind] if key in data}
        if kind == "tool_finished":
            details["ok"] = data["result"].get("ok")
            if data["name"] == "delegate" and details["ok"]:
                child = data["result"].get("output", {})
                if "session_id" in child:
                    details["child_session"] = child["session_id"]
                    details["child_status"] = child["status"]
        yield {**event, "data": details}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="CodeHarness：Python 编码 Agent 运行时")
    commands = root.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", type=Path, default=Path.cwd(), help="目标仓库目录")
    common.add_argument("--store", type=Path, help="会话数据库；默认 workspace/.codeharness/state.sqlite3")
    common.add_argument("--json", action="store_true", help="仅输出机器可读 JSON")
    execution = argparse.ArgumentParser(add_help=False)
    execution.add_argument("--env-file", type=Path, help="显式读取本地 NAME=value 配置，环境变量优先")
    execution.add_argument("--model", help="也可设置 CODEHARNESS_MODEL 或 OPENAI_MODEL")
    execution.add_argument("--provider", choices=["openai", "anthropic"], default="openai",
                           help="模型协议：openai（Chat Completions 兼容）或 anthropic（原生 Messages）")
    execution.add_argument("--model-pool", type=Path, help="模型额度和台账配置 JSON")
    execution.add_argument("--models", help="覆盖模型池顺序，使用逗号分隔")
    execution.add_argument("--reasoning-effort", help="模型支持时设置推理强度，例如 low")
    execution.add_argument("--base-url", help="兼容 Chat Completions 的地址，包含 /v1 等前缀")
    execution.add_argument("--allow-write", action="store_true", help="授权修改工作区文件")
    execution.add_argument("--allow-exec", action="store_true", help="授权在本机执行项目测试（不是 OS 沙箱）")
    execution.add_argument("--pass-env", action="append", default=[], metavar="NAME", help="显式传给测试的进程变量，可重复")
    execution.add_argument("--max-requests", type=int, default=24, help="主任务和子任务共享的请求总上限")
    execution.add_argument("--max-tokens", type=int, default=60000, help="Token 预算；请求前估计，响应后以 usage 校正")
    execution.add_argument("--output-tokens", type=int, default=2048, help="单次模型输出上限")
    execution.add_argument("--context-chars", type=int, default=28000, help="开始压缩旧回合的字符阈值")
    execution.add_argument("--max-seconds", type=int, default=600, help="任务时间预算，在调用边界检查")
    execution.add_argument("--model-attempts", type=int, default=3, help="每轮模型最多尝试次数（含首次，重试计入总预算）")
    execution.add_argument("--no-delegate", action="store_true", help="禁用只读任务委派，便于消融分析")
    execution.add_argument("--disable-tool", action="append", default=[], metavar="NAME", help="禁用一个工具，可重复")
    execution.add_argument("--enable-bash", action="store_true", help="启用工作区 bash 终端命令工具（需要执行权限）")
    execution.add_argument("--sandbox", choices=["local", "docker"], default="local",
                           help="测试与 bash 执行环境：local（本机进程）或 docker（断网限资源容器沙箱）")
    execution.add_argument("--sandbox-image", default="python:3.12-slim",
                           help="Docker 沙箱镜像，默认 python:3.12-slim")
    execution.add_argument("--tool-profile", choices=["default", "pi"], default="default",
                           help="工具集模式：default 为完整受控工具集，pi 为精简 4 工具模式")
    execution.add_argument("--enable-memory", action="store_true", help="启用 L1/L2/L3 三层会话记忆扩展")
    execution.add_argument("--plugin", type=Path, action="append", default=[], help="加载可信 Python 扩展（本机权限）")
    run = commands.add_parser("run", parents=[common, execution], help="开始一个仓库任务")
    run.add_argument("task")
    run.add_argument("--isolate", action="store_true", help="在独立 Git worktree 修改，保留产物供检查")
    resume = commands.add_parser("resume", parents=[common, execution], help="恢复会话并检查工作区变化")
    resume.add_argument("session_id")
    resume.add_argument("--message", default="继续原任务；先检查中断状态和当前工作区。")
    # Argparse shares inherited Action objects, including their mutable defaults.
    chat = commands.add_parser("chat", parents=[common, deepcopy(execution)], help="本地交互开发模式（默认流式输出与 bash，免逐次确认）")
    chat.set_defaults(max_requests=200, max_tokens=500000, max_seconds=1800)
    chat.add_argument("--session", dest="session_id", help="继续已有会话 ID")
    chat.add_argument("--no-bash", action="store_true", help="在交互模式中禁用 bash 工具")
    chat.add_argument("--no-stream", action="store_true", help="关闭流式输出，等待整轮完整返回")
    chat.add_argument("--no-memory", action="store_true", help="在交互模式中禁用三层记忆扩展")
    chat.add_argument("--discover-extensions", action="store_true", help="加载工作区中信任的 .codeharness/extensions/*.py")
    chat.add_argument("--confirm", action="store_true", help="开启写文件与执行命令前的交互确认")
    demo = commands.add_parser("demo", parents=[common], help="离线演示完整调用链；不调用真实模型")
    demo.add_argument("--directory", type=Path, help="演示目录，必须尚不存在")
    commands.add_parser("sessions", parents=[common], help="列出主任务和子任务")
    trace = commands.add_parser("trace", parents=[common], help="查看会话事件、模型输入与工具证据")
    trace.add_argument("session_id")
    trace.add_argument("--timeline", action="store_true", help="仅显示请求、工具、压缩、验证和结果的时间线")
    return root


def _tool_preview(name: str, arguments) -> str:
    if not isinstance(arguments, dict):
        return ""
    if name == "bash" and isinstance(arguments.get("command"), str):
        cmd = arguments["command"].strip().replace("\n", " ")
        return cmd[:100] + ("..." if len(cmd) > 100 else "")
    for key in ("path", "query", "name", "task", "artifact_id"):
        if isinstance(arguments.get(key), str) and arguments[key]:
            return arguments[key][:80]
    return ""


def run_chat(agent: Agent, workspace: Path, store: Store, policy: Policy, *,
             session_id: str | None = None, stream: bool = True,
             input_fn=input, output=None, switch_model=None) -> int:
    out = output or sys.stdout
    sid = session_id
    state = {"mode": None, "printed": False}

    def emit(text: str = "", *, end: str = "\n"):
        print(text, end=end, file=out, flush=True)

    def end_stream_line():
        if state["mode"] is not None:
            emit("")
            state["mode"] = None

    def on_delta(kind: str, chunk: str):
        if kind == "reasoning":
            if state["mode"] != "reasoning":
                end_stream_line()
                emit("[思考] ", end="")
                state["mode"] = "reasoning"
            emit(chunk, end="")
        elif kind == "text":
            if state["mode"] == "reasoning":
                emit("")
            state["mode"] = "text"
            state["printed"] = True
            emit(chunk, end="")

    def observe(kind: str, data: dict):
        if kind == "tool":
            end_stream_line()
            preview = _tool_preview(data["name"], data.get("arguments"))
            detail = f" {preview}" if preview else ""
            emit(f"[工具] {data['name']}{detail}")
        elif kind == "model_switch":
            end_stream_line()
            emit(f"[切换模型] {data['previous']} → {data['model']}")

    agent.observe = observe
    agent.on_delta = on_delta if stream else None

    emit(f"CodeHarness 交互模式 | 工作区：{workspace} | 模型：{agent.model.name}")
    sandbox_label = (f"docker ({agent.executor.image})" if isinstance(agent.executor, DockerExecutor)
                     else (agent.executor.mode if agent.executor else "local"))
    emit(f"工具模式：{agent.tool_profile} | bash：{'开' if agent.enable_bash else '关'} | 沙箱：{sandbox_label} | 输入 /help 查看命令，/exit 退出")
    if sid:
        emit(f"继续会话：{sid}")

    while True:
        try:
            raw = input_fn("\n> ")
        except EOFError:
            emit("")
            break
        except KeyboardInterrupt:
            emit("\n已取消输入。输入 /exit 退出。")
            continue
        line = raw.strip()
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            break
        if line == "/help":
            emit("命令：/help 帮助 | /tools 工具 | /session 会话 | /compact [重点] 压缩 | "
                 "/tree 会话树 | /fork [回合] [备注] 分叉 | /switch <ID> 切分支 | /model [名] 换模型 | !命令 | /exit 退出")
            ext_cmds = agent.commands()
            if ext_cmds:
                emit("扩展命令：" + " | ".join(f"/{cmd.name} {cmd.description}" for cmd in ext_cmds.values()))
            continue
        if line == "/tools":
            emit(f"工具模式：{agent.tool_profile}（bash={'开' if agent.enable_bash else '关'}）")
            emit("已启用：" + ", ".join(agent.tool_names()))
            continue
        if line == "/session":
            if not sid:
                emit(f"尚未开始会话 | 工作区：{workspace} | 模型：{agent.model.name}")
            else:
                usage = store.usage(sid)
                emit(f"会话：{sid} | 工作区：{workspace} | 模型：{agent.model.name}")
                emit("用量：" + json.dumps(usage, ensure_ascii=False))
            continue
        if line == "/tree":
            if not sid:
                emit("尚未开始会话，暂无会话树。")
                continue
            tree = store.session_tree(sid)
            emit("=== 会话分支树 ===")
            for node in tree["branches"]:
                indent = "  " * node["depth"]
                mark = "* " if node["current"] else "  "
                origin = f" (from ev:{node['from_event_id']})" if node["from_event_id"] else ""
                label = f" [{node['label']}]" if node["label"] else ""
                emit(f"{mark}{indent}{node['id']}  {node['model']}  {node['status']}{origin}{label}")
            emit("=== 当前分支回合 ===")
            for turn in tree["turns"]:
                emit(f"  #{turn['turn']} [ev:{turn['event_id']}] {turn['user']} -> {turn['assistant']}")
            if not tree["turns"]:
                emit("  （暂无已完成回合）")
            continue
        if line == "/fork" or line.startswith("/fork "):
            if not sid:
                emit("尚未开始会话，无法分叉。")
                continue
            rest = line[len("/fork"):].strip()
            cutoff = None
            label = ""
            if rest:
                parts = rest.split(None, 1)
                head = parts[0]
                tail = parts[1] if len(parts) == 2 else ""
                turns = store.turns(sid)
                if head.startswith("ev:") and head[3:].isdigit():
                    cutoff = int(head[3:])
                    label = tail
                elif head.lstrip("#").isdigit():
                    idx = int(head.lstrip("#"))
                    if not 1 <= idx <= len(turns):
                        emit(f"回合号超出范围（1～{len(turns)}）。")
                        continue
                    cutoff = turns[idx - 1]["event_id"]
                    label = tail
                else:
                    label = rest
            try:
                old_sid = sid
                new_sid = store.fork(sid, up_to_event_id=cutoff, label=label)
                agent.copy_session_pins(old_sid, new_sid)
                sid = new_sid
                emit(f"已分叉并切换到新分支：{sid}" + (f" [{label}]" if label else ""))
            except ValueError as exc:
                emit(f"分叉失败：{exc}")
            continue
        if line == "/switch" or line.startswith("/switch "):
            target = line[len("/switch"):].strip()
            if not target:
                emit("用法：/switch <会话ID>")
                continue
            try:
                row = store.session(target)
                if Path(row["workspace"]).resolve() != workspace.resolve():
                    emit("目标会话不属于当前工作区。")
                    continue
                if row["parent_id"] is not None:
                    emit("不能切换到只读子任务会话。")
                    continue
                sid = target
                emit(f"已切换到分支：{sid}")
            except ValueError as exc:
                emit(str(exc))
            continue
        if line == "/model" or line.startswith("/model "):
            spec = line[len("/model"):].strip()
            if not spec:
                proto = "anthropic" if isinstance(agent.model, AnthropicModel) else "openai"
                emit(f"当前模型：{agent.model.name}（协议：{proto}）")
                continue
            if switch_model is None or isinstance(agent.model, ModelPool):
                emit("当前模式未配置模型热切换，模型池继续按配置运行。")
                continue
            try:
                previous = agent.model.name
                agent.model = switch_model(spec)
                emit(f"已切换模型：{previous} → {agent.model.name}")
            except ValueError as exc:
                emit(f"切换模型失败：{exc}")
            continue
        if line == "/compact" or line.startswith("/compact "):
            if not sid:
                emit("尚未开始会话，无需压缩。")
                continue
            note = line[len("/compact"):].strip()
            info = agent.compact(sid, note=note)
            if info["compacted"]:
                emit(f"已压缩：{info['before_messages']} → {info['after_messages']} 条消息，"
                     f"{info['before_chars']} → {info['after_chars']} 字符")
            else:
                emit(f"当前仅 {info['before_messages']} 条消息，暂无需压缩。")
            continue
        if line.startswith("/"):
            parts = line[1:].split(None, 1)
            cmd_name = parts[0].lower() if parts else ""
            cmd_args = parts[1] if len(parts) == 2 else ""
            ext_cmd = agent.commands().get(cmd_name)
            if ext_cmd is not None:
                reply_text = ext_cmd.handler(cmd_args, {"session_id": sid, "workspace": workspace, "agent": agent})
                if reply_text:
                    emit(str(reply_text))
                continue
            emit(f"未知命令：/{cmd_name}。输入 /help 查看可用命令。")
            continue
        if line.startswith("!"):
            command = line[1:].strip()
            if not command:
                continue
            try:
                proc = subprocess.run(shell_command(command), cwd=workspace,
                                      env=test_subprocess_env(policy.pass_env),
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace", timeout=60)
                if proc.stdout:
                    emit(proc.stdout.rstrip("\n"))
                emit(f"[本地命令退出码：{proc.returncode}]")
            except subprocess.TimeoutExpired:
                emit("[本地命令超时：60 秒]")
            except KeyboardInterrupt:
                emit("\n[已中断本地命令]")
            continue

        state["mode"] = None
        state["printed"] = False
        result = agent.run(line, session_id=sid)
        sid = result.session_id
        end_stream_line()
        if not state["printed"] or result.status in {"error", "cancelled", "timeout", "stalled"}:
            emit(result.answer)
        changes = ", ".join(result.changed_files) or "无"
        usage = result.usage
        emit(f"[{result.status} | 改动：{changes} | 请求：{usage['requests']} | "
             f"tokens：in={usage['input_tokens']} out={usage['output_tokens']}]")

    if sid:
        emit(f"会话已保存：{sid}（可用 codeharness chat --session {sid} 继续）")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = None
    try:
        workspace = args.workspace.resolve()
        if not workspace.is_dir():
            raise ValueError("工作区不存在")
        database = args.store or workspace / ".codeharness" / "state.sqlite3"
        if args.command == "sessions":
            store = Store(database.resolve())
            rows = store.sessions()
            if args.json:
                print(json.dumps(rows, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row['id']}  {row['status']:18}  {row['model']}  parent={row['parent_id'] or '-'}")
            return 0
        if args.command == "trace":
            store = Store(database.resolve())
            store.session(args.session_id)
            events = store.events(args.session_id, expand=not args.timeline)
            if args.timeline:
                events = list(trace_timeline(events))
            if args.json:
                print(json.dumps(events, ensure_ascii=False, indent=2))
            elif args.timeline:
                for event in events:
                    details = " ".join(f"{key}={value}" for key, value in event["data"].items())
                    print(f"{event['time']}  {event['kind']}  {details}")
            else:
                for event in events:
                    print(json.dumps(event, ensure_ascii=False))
            return 0
        if args.command == "demo":
            workspace = (args.directory or workspace / ".codeharness" / "demos" / uuid.uuid4().hex[:10]).resolve()
            create_demo(workspace)
            model = DemoModel()
            policy = Policy(allow_write=True, allow_exec=True)
            limits = Limits()
            plugins = []
            task = "修复购物篮百分比折扣计算，并运行现有测试验证。"
            sid = None
            enable_bash = False
            tool_profile = "default"
            executor = None
            env = {}
            provider = "openai"
            if not args.json:
                print("离线演示：使用确定性适配器，不调用 AI，不产生真实模型评测成绩。")
        else:
            env = {**load_env(args.env_file), **os.environ}
            provider = args.provider
            model_name = args.model or env.get("CODEHARNESS_MODEL") or (
                env.get("ANTHROPIC_MODEL") if provider == "anthropic" else env.get("OPENAI_MODEL"))
            sid = getattr(args, "session_id", None) if args.command in {"resume", "chat"} else None
            if sid:
                store = Store(database.resolve())
                row = store.session(sid)
                if args.command == "chat" and row["parent_id"] is not None:
                    raise ValueError("不能用交互模式恢复只读子任务")
                workspace = Path(row["workspace"])
                model_name = model_name or row["model"]
            limits = Limits(args.max_requests, args.max_tokens, args.output_tokens, args.context_chars, args.max_seconds,
                            args.model_attempts)
            if args.models and not args.model_pool:
                raise ValueError("--models 需要配合 --model-pool")
            if args.model_pool:
                if args.model or args.base_url:
                    raise ValueError("--model-pool 使用池配置中的模型和接口地址")
                if provider != "openai":
                    raise ValueError("--model-pool 当前仅支持 openai 协议")
                model = ModelPool(args.model_pool, env=env, order=args.models,
                                  reasoning_effort=args.reasoning_effort, switch_mid_session=True)
            else:
                model = build_model(model_name or "", provider=provider, env=env, base_url=args.base_url,
                                    timeout=min(60, args.max_seconds), reasoning_effort=args.reasoning_effort)
            if args.command == "run" and args.isolate:
                workspace = isolated_workspace(workspace)
            def confirm(name, arguments):
                if not sys.stdin.isatty():
                    return False
                target = arguments.get("command") if name == "bash" else arguments.get("path", "当前工作区")
                return input(f"允许 {name} 操作 {target}？输入 yes 确认：").strip().lower() == "yes"
            for name in args.pass_env:
                if name.upper().endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")):
                    print(f"警告：测试代码可读取显式放行的环境变量 {name}。", file=sys.stderr)
            if args.command == "chat":
                allow_write = True if not args.confirm else args.allow_write
                allow_exec = True if not args.confirm else args.allow_exec
                policy = Policy(allow_write, allow_exec, confirm=confirm if args.confirm else None,
                                pass_env=tuple(args.pass_env))
                enable_bash = not args.no_bash
            else:
                policy = Policy(args.allow_write, args.allow_exec, confirm=confirm, pass_env=tuple(args.pass_env))
                enable_bash = args.enable_bash or args.tool_profile == "pi"
            tool_profile = args.tool_profile
            executor = DockerExecutor(args.sandbox_image) if args.sandbox == "docker" else None
            plugins = args.plugin
            task = args.message if args.command == "resume" else getattr(args, "task", "")

        if store is None:
            store = Store(database.resolve())

        if args.command == "chat":
            active_provider = provider

            def switch_model(spec: str):
                nonlocal active_provider
                target_provider = active_provider
                target_name = spec
                if ":" in spec:
                    prefix, rest = spec.split(":", 1)
                    if prefix in {"openai", "anthropic"} and rest.strip():
                        target_provider, target_name = prefix, rest.strip()
                target_url = args.base_url if target_provider == provider else None
                target = build_model(target_name, provider=target_provider, env=env, base_url=target_url,
                                     timeout=min(60, args.max_seconds), reasoning_effort=args.reasoning_effort)
                active_provider = target_provider
                return target

            agent = Agent(model, workspace, store, policy, limits, plugins,
                          enable_delegate=not getattr(args, "no_delegate", False),
                          disabled_tools=getattr(args, "disable_tool", ()),
                          enable_bash=enable_bash, tool_profile=tool_profile,
                          enable_memory=not args.no_memory, discover_extensions=args.discover_extensions,
                          executor=executor)
            try:
                return run_chat(agent, workspace, store, policy, session_id=sid, stream=not args.no_stream,
                                switch_model=switch_model)
            finally:
                agent.close()

        def observe(kind, data):
            if args.json:
                return
            if kind == "session":
                print(f"[{'只读子任务' if data['readonly'] else '会话'}] {data['id']}", flush=True)
            elif kind == "tool":
                print(f"[{data['session_id']}] {data['name']}", flush=True)
            elif kind == "model_switch":
                print(f"切换模型：{data['previous']} → {data['model']}", flush=True)

        agent = Agent(model, workspace, store, policy, limits, plugins, observe,
                      enable_delegate=not getattr(args, "no_delegate", False),
                      disabled_tools=getattr(args, "disable_tool", ()),
                      enable_bash=enable_bash, tool_profile=tool_profile,
                      enable_memory=getattr(args, "enable_memory", False),
                      executor=executor)
        try:
            result = agent.run(task, session_id=sid)
        finally:
            agent.close()
        output = {**asdict(result), "workspace": str(workspace), "store": str(store.path)}
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"\n{result.answer}\n")
            print(f"状态：{result.status}；验证：{result.verification}；会话：{result.session_id}")
            print(f"改动：{', '.join(result.changed_files) or '无'}")
            print(f"工作区：{workspace}\n会话库：{store.path}")
            print("用量：" + json.dumps(result.usage, ensure_ascii=False))
        return 0 if result.status in {"completed", "verified"} else 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"错误：{exc}", file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
