import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from .demo import DemoModel, create_demo
from .models import ChatModel
from .runtime import Agent, Limits
from .store import Store
from .tools import Policy


def load_env(path: Path | None):
    if path is None:
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not name.strip().isidentifier():
            raise ValueError("环境配置文件应每行使用 NAME=value 格式")
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def isolated_workspace(workspace: Path) -> Path:
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=workspace,
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode or Path(result.stdout.strip()).resolve() != workspace:
        raise ValueError("--isolate 要求 workspace 是 Git 仓库根目录")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=workspace, capture_output=True,
                            text=True, encoding="utf-8", check=True)
    if status.stdout.strip():
        raise ValueError("隔离工作区从 HEAD 创建，请先提交或保存当前改动")
    destination = workspace / ".codeharness" / "worktrees" / uuid.uuid4().hex[:10]
    result = subprocess.run(["git", "worktree", "add", "--detach", str(destination), "HEAD"],
                            cwd=workspace, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise ValueError("无法创建隔离工作区：" + result.stderr[:400])
    return destination.resolve()


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
    execution.add_argument("--base-url", help="兼容 Chat Completions 的地址，包含 /v1 等前缀")
    execution.add_argument("--allow-write", action="store_true", help="授权修改工作区文件")
    execution.add_argument("--allow-exec", action="store_true", help="授权在本机执行项目测试（不是 OS 沙箱）")
    execution.add_argument("--max-requests", type=int, default=24, help="主任务和子任务共享的请求总上限")
    execution.add_argument("--max-tokens", type=int, default=60000, help="Token 预算；请求前估计，响应后以 usage 校正")
    execution.add_argument("--output-tokens", type=int, default=2048, help="单次模型输出上限")
    execution.add_argument("--context-chars", type=int, default=28000, help="开始压缩旧回合的字符阈值")
    execution.add_argument("--max-seconds", type=int, default=600, help="任务时间预算，在调用边界检查")
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
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = None
    try:
        workspace = args.workspace.resolve()
        if not workspace.is_dir():
            raise ValueError("工作区不存在")
        database = args.store or workspace / ".codeharness" / "state.sqlite3"
        store = Store(database.resolve())
        if args.command == "sessions":
            rows = store.sessions()
            if args.json:
                print(json.dumps(rows, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row['id']}  {row['status']:18}  {row['model']}  parent={row['parent_id'] or '-'}")
            return 0
        if args.command == "trace":
            store.session(args.session_id)
            events = store.events(args.session_id)
            if args.json:
                print(json.dumps(events, ensure_ascii=False, indent=2))
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
            load_env(args.env_file)
            model_name = args.model or os.environ.get("CODEHARNESS_MODEL") or os.environ.get("OPENAI_MODEL")
            sid = args.session_id if args.command == "resume" else None
            if sid:
                row = store.session(sid)
                workspace = Path(row["workspace"])
                model_name = model_name or row["model"]
            if model_name == "offline-demo":
                model = DemoModel()
            else:
                base_url = args.base_url or os.environ.get("CODEHARNESS_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
                key = os.environ.get("CODEHARNESS_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
                if not model_name or not base_url:
                    raise ValueError("请设置模型名与接口地址。可先运行 python -m codeharness demo 检查离线流程。")
                model = ChatModel(model_name, base_url, key, timeout=min(60, args.max_seconds))
            if args.command == "run" and args.isolate:
                workspace = isolated_workspace(workspace)
            def confirm(name, arguments):
                if not sys.stdin.isatty():
                    return False
                target = arguments.get("path", "当前工作区")
                return input(f"允许 {name} 操作 {target}？输入 yes 确认：").strip().lower() == "yes"
            policy = Policy(args.allow_write, args.allow_exec, confirm=confirm)
            limits = Limits(args.max_requests, args.max_tokens, args.output_tokens, args.context_chars, args.max_seconds)
            plugins = args.plugin
            task = args.message if sid else args.task

        def observe(kind, data):
            if args.json:
                return
            if kind == "session":
                print(f"[{'只读子任务' if data['readonly'] else '会话'}] {data['id']}", flush=True)
            elif kind == "tool":
                print(f"[{data['session_id']}] {data['name']}", flush=True)

        result = Agent(model, workspace, store, policy, limits, plugins, observe).run(task, session_id=sid)
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
