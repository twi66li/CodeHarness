"""Reproducible fixture checks and opt-in model evaluation; never mixes the two."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .benchmark_tasks import ALL_TASKS, MULTI_TASKS, TASKS, Task
from .cli import load_env, model_connection
from .models import ChatModel, Model
from .runtime import Agent, Limits
from .store import Store
from .tools import Policy


def materialize(root: Path, files: dict[str, str]):
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def acceptance(workspace: Path, verifier: Path) -> dict:
    """The verifier is outside the model's workspace. This is not an OS sandbox."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("CODEHARNESS_", "OPENAI_", "DASHSCOPE_"))}
    try:
        process = subprocess.run([sys.executable, "-I", "-B", str(verifier), str(workspace)],
            cwd=workspace, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    except subprocess.TimeoutExpired:
        return {"passed": False, "exit_code": None, "output": "独立验收超时"}
    except OSError:
        return {"passed": False, "exit_code": None, "output": "无法启动独立验收"}
    return {"passed": process.returncode == 0, "exit_code": process.returncode,
            "output": (process.stdout + process.stderr)[-3000:]}


def prepare_case(task: Task, directory: Path) -> tuple[Path, Path, dict]:
    workspace = directory / "repo"
    workspace.mkdir(parents=True, exist_ok=False)
    materialize(workspace, task.files)
    verifier = directory / "acceptance.py"
    verifier.write_text("import sys\nsys.path.insert(0, sys.argv[1])\n" + task.acceptance, encoding="utf-8")
    baseline = acceptance(workspace, verifier)
    return workspace, verifier, baseline


def summarize(cases: list[dict]) -> dict:
    groups = {}
    for row in cases:
        group = groups.setdefault(row["variant"], {"attempted": 0, "passed": 0, "failed": 0, "skipped": 0,
            "requests": 0, "input_tokens": 0, "output_tokens": 0, "usage_estimated": False, "seconds": 0.0,
            "model_errors": 0, "model_retries": 0, "tool_errors": 0, "failed_verifications": 0,
            "delegate_calls": 0, "compactions": 0})
        if row.get("skipped"):
            group["skipped"] += 1
            continue
        group["attempted"] += 1
        group["passed" if row["success"] else "failed"] += 1
        for key in ("requests", "input_tokens", "output_tokens"):
            group[key] += row.get("usage", {}).get(key, 0)
        group["usage_estimated"] |= row.get("usage", {}).get("estimated", False)
        for key in ("model_errors", "model_retries", "tool_errors", "failed_verifications",
                    "delegate_calls", "compactions"):
            group[key] += row.get("diagnostics", {}).get(key, 0)
        group["seconds"] += row.get("seconds", 0.0)
    for group in groups.values():
        group["success_rate"] = group["passed"] / group["attempted"] if group["attempted"] else None
        group["seconds"] = round(group["seconds"], 3)
    return groups


def diagnostics(store: Store) -> dict:
    """Summarize failure evidence without exporting raw messages or tool output."""
    result = {"model_errors": 0, "model_retries": 0, "tool_errors": 0, "failed_verifications": 0,
              "delegate_calls": 0, "compactions": 0, "model_access_denied": False, "tool_error_counts": {}}
    for session in store.sessions():
        if session["parent_id"] is not None:
            result["delegate_calls"] += 1
        for event in store.events(session["id"]):
            kind, data = event["kind"], event["data"]
            if kind == "model_error":
                result["model_errors"] += 1
                result["model_access_denied"] |= bool(data.get("access_denied"))
            elif kind == "model_retry":
                result["model_retries"] += 1
            elif kind == "context_compacted":
                result["compactions"] += 1
            elif kind == "tool_finished" and not data["result"].get("ok"):
                result["tool_errors"] += 1
                name = data["name"]
                result["tool_error_counts"][name] = result["tool_error_counts"].get(name, 0) + 1
            elif kind == "verification" and not data["passed"]:
                result["failed_verifications"] += 1
    return result


def run_suite(tasks: tuple[Task, ...], output: Path, *, model: Model | None = None,
              limits: Limits | None = None, variants: tuple[str, ...] = ("delegate",),
              total_requests: int | None = None, total_tokens: int | None = None) -> dict:
    if not tasks:
        raise ValueError("评测任务不能为空")
    limits = limits or Limits(max_requests=12, max_tokens=24000, max_seconds=180)
    if model is not None:
        if total_requests is None or total_tokens is None or min(total_requests, total_tokens) < 1:
            raise ValueError("真实模型评测必须明确总请求和 Token 预算")
        if not variants or len(set(variants)) != len(variants) or set(variants) - {"delegate", "no-delegate"}:
            raise ValueError("无效的消融选项")
        if total_requests < limits.max_requests * len(variants) or total_tokens < limits.max_tokens * len(variants):
            raise ValueError("总预算不足以完整运行至少一组固定预算的任务")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"mode": "model_evaluation" if model is not None else "reference_fixture_validation",
              "model": model.name if model is not None else None, "task_count": len(tasks),
              "limits_per_case": asdict(limits) if model is not None else None,
              "budget": {"requests": total_requests, "tokens": total_tokens} if model is not None else None,
              "cases": [], "summary": {}}
    if isinstance(model, ChatModel) and model.reasoning_effort is not None:
        report["reasoning_effort"] = model.reasoning_effort

    def save(row):
        report["cases"].append(row)
        report["summary"] = summarize(report["cases"])
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    used_requests = used_tokens = 0
    access_denied = False
    for task in tasks:
        if access_denied:
            for variant in variants:
                save({"task": task.id, "variant": variant, "skipped": "model_access_denied"})
            continue
        if model is not None and (total_requests - used_requests < limits.max_requests * len(variants)
                                  or total_tokens - used_tokens < limits.max_tokens * len(variants)):
            for variant in variants:
                save({"task": task.id, "variant": variant, "skipped": "total_budget"})
            continue
        for variant in (variants if model is not None else ("reference",)):
            if access_denied:
                save({"task": task.id, "variant": variant, "skipped": "model_access_denied"})
                continue
            # A provider can report more tokens than the pre-request estimate.
            if model is not None and (total_requests - used_requests < limits.max_requests
                                      or total_tokens - used_tokens < limits.max_tokens):
                save({"task": task.id, "variant": variant, "skipped": "total_budget"})
                continue
            started = time.monotonic()
            directory = output / task.id / variant
            workspace, verifier, baseline = prepare_case(task, directory)
            row = {"task": task.id, "variant": variant, "workspace": str(workspace.relative_to(output)),
                   "baseline": baseline}
            # The initial fixture must fail a requirement assertion, not fail to import or run.
            if baseline["passed"] or "AssertionError" not in baseline["output"]:
                row.update({"success": False, "invalid_fixture": True, "seconds": time.monotonic() - started})
                save(row)
                continue
            if model is None:
                materialize(workspace, task.reference)
            else:
                store = Store(directory / "state.sqlite3")
                try:
                    result = Agent(model, workspace, store, Policy(allow_write=True, allow_exec=True), limits,
                                   enable_delegate=variant == "delegate").run(task.prompt)
                    evidence = diagnostics(store)
                    access_denied = evidence["model_access_denied"]
                finally:
                    store.close()
                row.update({"session_id": result.session_id, "agent_status": result.status,
                            "agent_verification": result.verification, "changed_files": result.changed_files,
                            "usage": result.usage, "model_access_denied": access_denied, "diagnostics": evidence})
                used_requests += result.usage["requests"]
                used_tokens += result.usage["input_tokens"] + result.usage["output_tokens"]
            checked = acceptance(workspace, verifier)
            row.update({"acceptance": checked, "success": checked["passed"], "seconds": time.monotonic() - started})
            save(row)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CodeHarness 独立验收与消融评测")
    parser.add_argument("--mode", choices=("fixtures", "model"), default="fixtures")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--suite", choices=("core", "full", "multi"), default="core",
                           help="core=5 个基础任务；full=12 个基础任务；multi=3 个 11 文件多模块后端任务")
    selection.add_argument("--task", choices=tuple(task.id for task in ALL_TASKS), help="仅运行一个指定任务，适合低预算联调")
    parser.add_argument("--variants", choices=("delegate", "no-delegate", "both"), default="delegate")
    parser.add_argument("--output", type=Path, help="新建报告目录；默认 .codeharness/benchmarks/<id>")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--reasoning-effort", help="模型支持时设置推理强度，例如 low")
    parser.add_argument("--base-url")
    parser.add_argument("--allow-exec", action="store_true", help="同意真实模型修改并在本机执行评测代码")
    parser.add_argument("--max-requests", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=24000)
    parser.add_argument("--output-tokens", type=int, default=Limits.output_tokens, help="单次模型输出上限")
    parser.add_argument("--max-seconds", type=int, default=180)
    parser.add_argument("--total-requests", type=int)
    parser.add_argument("--total-tokens", type=int)
    args = parser.parse_args(argv)
    try:
        model = None
        if args.mode == "model":
            if not args.allow_exec:
                raise ValueError("真实模型评测需要 --allow-exec；测试会在本机执行项目代码")
            env = {**load_env(args.env_file), **os.environ}
            name = args.model or env.get("CODEHARNESS_MODEL") or env.get("OPENAI_MODEL")
            url, key = model_connection(env, args.base_url)
            if not name or not url or name == "offline-demo":
                raise ValueError("请配置实际模型名与接口地址；离线演示不能作为真实模型评测")
            model = ChatModel(name, url, key, reasoning_effort=args.reasoning_effort)
        output = args.output or Path(".codeharness/benchmarks") / uuid.uuid4().hex[:10]
        variants = ("delegate", "no-delegate") if args.variants == "both" else (args.variants,)
        suite_map = {"core": TASKS[:5], "full": TASKS, "multi": MULTI_TASKS}
        tasks = tuple(task for task in ALL_TASKS if task.id == args.task) if args.task else suite_map[args.suite]
        report = run_suite(tasks, output, model=model,
            limits=Limits(max_requests=args.max_requests, max_tokens=args.max_tokens,
                          output_tokens=args.output_tokens, max_seconds=args.max_seconds),
            variants=variants, total_requests=args.total_requests, total_tokens=args.total_tokens)
        print(json.dumps({"mode": report["mode"], "report": str(output.resolve() / "report.json"),
                          "summary": report["summary"]}, ensure_ascii=False, indent=2))
        return 0 if all(row.get("success", False) for row in report["cases"]) else 2
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
