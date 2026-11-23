import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .demo import DemoModel, create_demo
from .model_pool import ModelPool
from .models import ChatModel
from .runtime import Agent, Limits
from .store import Store
from .tools import Policy


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


def model_connection(env: dict[str, str], base_url: str | None) -> tuple[str | None, str]:
    url = base_url or env.get("CODEHARNESS_BASE_URL") or env.get("OPENAI_BASE_URL")
    if url:
        return url, env.get("CODEHARNESS_API_KEY") or env.get("OPENAI_API_KEY", "")
    return env.get("DASHSCOPE_BASE_URL"), env.get("DASHSCOPE_API_KEY", "")


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
        "model_request": ("model", "max_tokens"),
        "model_error": ("attempt", "retryable", "quota_exhausted", "preflight"),
        "model_retry": ("next_attempt", "delay_seconds"),
        "model_truncated": ("attempt", "max_tokens"),
        "context_compacted": ("original_messages", "sent_messages"),
        "tool_started": ("name", "call_id"),
        "tool_finished": ("name", "call_id"),
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
    execution.add_argument("--plugin", type=Path, action="append", default=[], help="加载可信 Python 扩展（本机权限）")
    run = commands.add_parser("run", parents=[common, execution], help="开始一个仓库任务")
    run.add_argument("task")
    run.add_argument("--isolate", action="store_true", help="在独立 Git worktree 修改，保留产物供检查")
    resume = commands.add_parser("resume", parents=[common, execution], help="恢复会话并检查工作区变化")
    resume.add_argument("session_id")
    resume.add_argument("--message", default="继续原任务；先检查中断状态和当前工作区。")
    demo = commands.add_parser("demo", parents=[common], help="离线演示完整调用链；不调用真实模型")
    demo.add_argument("--directory", type=Path, help="演示目录，必须尚不存在")
    commands.add_parser("sessions", parents=[common], help="列出主任务和子任务")
    trace = commands.add_parser("trace", parents=[common], help="查看会话事件、模型输入与工具证据")
    trace.add_argument("session_id")
    trace.add_argument("--timeline", action="store_true", help="仅显示请求、工具、压缩、验证和结果的时间线")
    return root


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
            if not args.json:
                print("离线演示：使用确定性适配器，不调用 AI，不产生真实模型评测成绩。")
        else:
            env = {**load_env(args.env_file), **os.environ}
            model_name = args.model or env.get("CODEHARNESS_MODEL") or env.get("OPENAI_MODEL")
            sid = args.session_id if args.command == "resume" else None
            if sid:
                store = Store(database.resolve())
                row = store.session(sid)
                workspace = Path(row["workspace"])
                model_name = model_name or row["model"]
            limits = Limits(args.max_requests, args.max_tokens, args.output_tokens, args.context_chars, args.max_seconds,
                            args.model_attempts)
            if args.models and not args.model_pool:
                raise ValueError("--models 需要配合 --model-pool")
            if args.model_pool:
                if args.model or args.base_url:
                    raise ValueError("--model-pool 使用池配置中的模型和接口地址")
                model = ModelPool(args.model_pool, env=env, order=args.models,
                                  reasoning_effort=args.reasoning_effort, switch_mid_session=True)
            elif model_name == "offline-demo":
                model = DemoModel()
            else:
                base_url, key = model_connection(env, args.base_url)
                if not model_name or not base_url:
                    raise ValueError("请设置模型名与接口地址。可先运行 python -m codeharness demo 检查离线流程。")
                model = ChatModel(model_name, base_url, key, timeout=min(60, args.max_seconds),
                                  reasoning_effort=args.reasoning_effort)
            if args.command == "run" and args.isolate:
                workspace = isolated_workspace(workspace)
            def confirm(name, arguments):
                if not sys.stdin.isatty():
                    return False
                target = arguments.get("path", "当前工作区")
                return input(f"允许 {name} 操作 {target}？输入 yes 确认：").strip().lower() == "yes"
            for name in args.pass_env:
                if name.upper().endswith(("_KEY", "_TOKEN", "_SECRET", "_PASSWORD")):
                    print(f"警告：测试代码可读取显式放行的环境变量 {name}。", file=sys.stderr)
            policy = Policy(args.allow_write, args.allow_exec, confirm=confirm, pass_env=tuple(args.pass_env))
            plugins = args.plugin
            task = args.message if sid else args.task

        if store is None:
            store = Store(database.resolve())

        def observe(kind, data):
            if args.json:
                return
            if kind == "session":
                print(f"[{'只读子任务' if data['readonly'] else '会话'}] {data['id']}", flush=True)
            elif kind == "tool":
                print(f"[{data['session_id']}] {data['name']}", flush=True)
            elif kind == "model_switch":
                print(f"切换模型：{data['previous']} → {data['model']}", flush=True)

        result = Agent(model, workspace, store, policy, limits, plugins, observe,
                       enable_delegate=not getattr(args, "no_delegate", False),
                       disabled_tools=getattr(args, "disable_tool", ())).run(task, session_id=sid)
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
