"""Reproducible fixture checks and opt-in model evaluation; never mixes the two."""

import argparse
from dataclasses import asdict
from itertools import product
import json
from math import ceil
import os
from pathlib import Path
from random import Random
from statistics import mean, median, stdev
import subprocess
import sys
import time
import uuid

from .benchmark_tasks import ALL_TASKS, MULTI_TASKS, TASKS, Task
from .benchmark_large import LARGE_TASK_IDS, large_tasks
from .cli import load_env, model_connection
from .model_pool import ModelPool
from .models import ChatModel, Model
from .runtime import Agent, Limits
from .store import Store
from .tools import Policy, test_subprocess_env


def materialize(root: Path, files: dict[str, str]):
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def acceptance(workspace: Path, verifier: Path) -> dict:
    """The verifier is outside the model's workspace. This is not an OS sandbox."""
    env = test_subprocess_env()
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
            "requests": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0,
            "usage_estimated": False, "seconds": 0.0,
            "model_errors": 0, "model_retries": 0, "tool_errors": 0, "failed_verifications": 0,
            "delegate_calls": 0, "compactions": 0, "truncations": 0, "stalled": 0})
        if row.get("skipped"):
            group["skipped"] += 1
        else:
            group["attempted"] += 1
            group["passed" if row["success"] else "failed"] += 1
            group["stalled"] += row.get("agent_status") == "stalled"
        for key in ("requests", "input_tokens", "output_tokens", "cached_tokens"):
            group[key] += row.get("usage", {}).get(key, 0)
        group["usage_estimated"] |= row.get("usage", {}).get("estimated", False)
        for key in ("model_errors", "model_retries", "tool_errors", "failed_verifications",
                    "delegate_calls", "compactions", "truncations"):
            group[key] += row.get("diagnostics", {}).get(key, 0)
        group["seconds"] += row.get("seconds", 0.0)
    for group in groups.values():
        group["success_rate"] = group["passed"] / group["attempted"] if group["attempted"] else None
        group["cache_hit_ratio"] = group["cached_tokens"] / group["input_tokens"] if group["input_tokens"] else None
        group["seconds"] = round(group["seconds"], 3)
    return groups


def repeat_statistics(cases: list[dict], repeats: int) -> dict:
    rows = [row for row in cases if not row.get("skipped")]
    variants = {}
    outcomes = {}

    def distribution(values):
        values = sorted(values)
        return {"median": median(values) if values else None,
                "p90": values[ceil(0.9 * len(values)) - 1] if values else None}

    for variant in dict.fromkeys(row["variant"] for row in rows):
        selected = [row for row in rows if row["variant"] == variant]
        tasks, rounds = {}, {}
        for row in selected:
            task, repeat, success = row["task"], row.get("repeat", 1), bool(row["success"])
            tasks.setdefault(task, []).append(success)
            rounds.setdefault(repeat, []).append(success)
            outcomes[task, variant, repeat] = success
        pass_at_1 = [mean(rounds[index]) for index in sorted(rounds)]
        usage = [row["usage"] for row in selected if "usage" in row]
        variants[variant] = {
            "task_success_rates": {task: {"success_rate": mean(values), "runs": len(values)} for task, values in tasks.items()},
            "pass_at_1": {"by_round": {str(index): mean(values) for index, values in sorted(rounds.items())},
                          "mean": mean(pass_at_1), "stdev": stdev(pass_at_1) if len(pass_at_1) > 1 else None},
            "requests": distribution(item["requests"] for item in usage),
            "tokens": distribution(item["input_tokens"] + item["output_tokens"] for item in usage),
            "seconds": distribution(row["seconds"] for row in selected if "seconds" in row),
        }

    paired = []
    for task in sorted({row["task"] for row in rows}):
        keys = list(product((task,), ("delegate", "no-delegate"), range(1, repeats + 1)))
        if all(key in outcomes for key in keys):
            paired.append(mean(outcomes[key] for key in keys[:repeats]) - mean(outcomes[key] for key in keys[repeats:]))
    return {"variants": variants, "paired": {"tasks": len(paired), "pairs": len(paired) * repeats,
            "success_rate_delta": mean(paired) if paired else None, "bootstrap_95ci": bootstrap_interval(paired)}}


def bootstrap_interval(deltas: list[float]) -> list[float] | None:
    if not deltas:
        return None
    random = Random(0)
    samples = sorted(mean(random.choices(deltas, k=len(deltas))) for _ in range(1000))
    return [samples[24], samples[974]]


def compare_reports(baseline: dict, treatment: dict, *, baseline_variant=None, treatment_variant=None) -> dict:
    def index(report, variant):
        rows = {}
        for row in report["cases"]:
            model = row.get("model", report.get("model"))
            if not model or row.get("skipped") or "usage" not in row or (variant and row.get("variant") != variant):
                continue
            key = model, row["task"], row.get("repeat", 1)
            if key in rows:
                raise ValueError("每份报告中同一模型、任务和轮次必须只有一个有效变体")
            rows[key] = row
        return rows

    def token_count(row):
        return row["usage"]["input_tokens"] + row["usage"]["output_tokens"]

    before, after = index(baseline, baseline_variant), index(treatment, treatment_variant)
    groups = {}
    for model, task, repeat in sorted(before.keys() & after.keys()):
        key = model, task, repeat
        groups.setdefault(model, []).append((before[key], after[key]))

    by_model = {}
    for model, pairs in groups.items():
        by_task = {}
        for left, right in pairs:
            by_task.setdefault(left["task"], []).append(int(right["success"]) - int(left["success"]))
        task_deltas = [mean(deltas) for deltas in by_task.values()]
        by_model[model] = {
            "tasks": len(by_task),
            "pairs": len(pairs),
            "success_rate_delta": mean(task_deltas),
            "bootstrap_95ci": bootstrap_interval(task_deltas),
            "request_delta_median": median(right["usage"]["requests"] - left["usage"]["requests"]
                                           for left, right in pairs),
            "token_delta_median": median(token_count(right) - token_count(left) for left, right in pairs),
        }
    return {"by_model": by_model, "baseline_unpaired": len(before.keys() - after.keys()),
            "treatment_unpaired": len(after.keys() - before.keys())}


def diagnostics(store: Store) -> dict:
    """Summarize failure evidence without exporting raw messages or tool output."""
    result = {"model_errors": 0, "model_retries": 0, "tool_errors": 0, "failed_verifications": 0,
              "delegate_calls": 0, "compactions": 0, "truncations": 0,
              "model_access_denied": False, "quota_exhausted": False, "tool_error_counts": {}}
    estimate_errors = []
    for session in store.sessions():
        if session["parent_id"] is not None:
            result["delegate_calls"] += 1
        estimate = None
        for event in store.events(session["id"], expand=False):
            kind, data = event["kind"], event["data"]
            if kind == "model_request":
                estimate = data.get("estimated_input")
            elif kind == "usage" and estimate is not None:
                actual = data.get("input_tokens", 0)
                if actual > 0 and not data.get("estimated"):
                    estimate_errors.append(abs(estimate - actual) / actual)
                estimate = None
            elif kind == "model_error":
                result["model_errors"] += 1
                result["model_access_denied"] |= bool(data.get("access_denied"))
                result["quota_exhausted"] |= bool(data.get("quota_exhausted"))
            elif kind == "model_retry":
                result["model_retries"] += 1
            elif kind == "model_truncated":
                result["truncations"] += 1
            elif kind == "context_compacted":
                result["compactions"] += 1
            elif kind == "tool_finished" and not data["result"].get("ok"):
                result["tool_errors"] += 1
                name = data["name"]
                result["tool_error_counts"][name] = result["tool_error_counts"].get(name, 0) + 1
            elif kind == "verification" and not data["passed"]:
                result["failed_verifications"] += 1
    result["estimate_error"] = sum(estimate_errors) / len(estimate_errors) if estimate_errors else None
    return result


def run_case(task: Task, variant: str, output: Path, directory: Path, model: Model | None, limits: Limits,
             disabled_tools: tuple[str, ...]) -> dict:
    started = time.monotonic()
    workspace, verifier, baseline = prepare_case(task, directory)
    row = {"task": task.id, "variant": variant, "workspace": str(workspace.relative_to(output)), "baseline": baseline}
    # The initial fixture must fail a requirement assertion, not fail to import or run.
    if baseline["passed"] or "AssertionError" not in baseline["output"]:
        row.update({"success": False, "invalid_fixture": True, "seconds": time.monotonic() - started})
        return row
    if model is None:
        materialize(workspace, task.reference)
    else:
        store = Store(directory / "state.sqlite3")
        try:
            result = Agent(model, workspace, store, Policy(allow_write=True, allow_exec=True), limits,
                           enable_delegate=variant == "delegate", disabled_tools=disabled_tools).run(task.prompt)
            evidence = diagnostics(store)
        finally:
            store.close()
        row.update({"session_id": result.session_id, "agent_status": result.status,
                    "agent_verification": result.verification, "changed_files": result.changed_files,
                    "usage": result.usage, "model_access_denied": evidence["model_access_denied"],
                    "diagnostics": evidence})
        input_tokens = result.usage["input_tokens"]
        row["cache_hit_ratio"] = result.usage["cached_tokens"] / input_tokens if input_tokens else None
    checked = acceptance(workspace, verifier)
    row.update({"acceptance": checked, "success": checked["passed"], "seconds": time.monotonic() - started})
    return row


def run_suite(tasks: tuple[Task, ...], output: Path, *, model: Model | None = None,
              limits: Limits | None = None, variants: tuple[str, ...] = ("delegate",),
              total_requests: int | None = None, total_tokens: int | None = None, disabled_tools: tuple[str, ...] = (),
              repeats: int = 1) -> dict:
    if not tasks:
        raise ValueError("评测任务不能为空")
    if repeats < 1 or (model is None and repeats != 1):
        raise ValueError("重复次数必须为正整数，且仅适用于真实模型评测")
    limits = limits or Limits(max_requests=12, max_tokens=24000, max_seconds=180)
    if model is not None:
        if total_requests is None or total_tokens is None or min(total_requests, total_tokens) < 1:
            raise ValueError("真实模型评测必须明确总请求和 Token 预算")
        if not variants or len(set(variants)) != len(variants) or set(variants) - {"delegate", "no-delegate"}:
            raise ValueError("无效的消融选项")
        slots = len(variants) * repeats
        if total_requests < limits.max_requests * slots or total_tokens < limits.max_tokens * slots:
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
    if disabled_tools:
        report["disabled_tools"] = list(disabled_tools)
    if model is not None:
        report["repeats"] = repeats

    pool = model if isinstance(model, ModelPool) else None
    variants = variants if model is not None else ("reference",)

    def save(rows):
        report["cases"].extend(rows)
        report["summary"] = summarize(report["cases"])
        if pool is not None:
            by_model = {}
            for row in report["cases"]:
                if row["model"] is not None:
                    by_model.setdefault(row["model"], []).append(row)
            report["summary_by_model"] = {name: summarize(entries) for name, entries in by_model.items()}
            report["model"] = next(iter(by_model)) if len(by_model) == 1 else None
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    used_requests = used_tokens = 0
    access_denied = False

    def blocked(slots):
        if access_denied:
            return "model_access_denied"
        if model is not None and (total_requests - used_requests < limits.max_requests * slots
                                  or total_tokens - used_tokens < limits.max_tokens * slots):
            return "total_budget"
        return None

    for repeat, task in product(range(1, repeats + 1), tasks):
        tried = set()
        while True:
            reason = blocked(len(variants))
            chosen = None
            if pool is not None and reason is None:
                chosen = pool.choose(limits.max_tokens * len(variants), excluded=tried)
                if chosen is None:
                    reason = "quota_exhausted"
                else:
                    pool.pin(chosen)

            rows = []
            for variant in variants:
                skipped = reason or ("model_quota_exhausted" if pool and pool.quota_exhausted else blocked(1))
                if skipped:
                    row = {"task": task.id, "variant": variant, "skipped": skipped}
                else:
                    directory = output / task.id / variant
                    if repeats > 1:
                        directory /= f"r{repeat}-{chosen}" if chosen else f"r{repeat}"
                    elif chosen:
                        directory /= chosen
                    row = run_case(task, variant, output, directory, model, limits, disabled_tools)
                    access_denied = row.get("model_access_denied", False)
                    usage = row.get("usage", {})
                    used_requests += usage.get("requests", 0)
                    used_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    if pool and pool.quota_exhausted:
                        row["skipped"] = "model_quota_exhausted"
                if pool is not None:
                    row["model"] = chosen
                    if chosen is not None and pool.adapters[chosen].reasoning_effort is not None:
                        row["reasoning_effort"] = pool.adapters[chosen].reasoning_effort
                if repeats > 1:
                    row["repeat"] = repeat
                rows.append(row)

            retry_pair = chosen is not None and pool.quota_exhausted
            if retry_pair:
                for row in rows:
                    row.setdefault("skipped", "incomplete_model_pair")
                tried.add(chosen)
            save(rows)
            if not retry_pair:
                break
    if model is not None:
        names = report["summary_by_model"] if pool is not None else (model.name,)
        report["statistics_by_model"] = {
            name: repeat_statistics([row for row in report["cases"] if row.get("model", model.name) == name], repeats)
            for name in names}
        report["statistics_method"] = "pass@1 by round; sample standard deviation; nearest-rank P90; paired bootstrap resamples tasks (seed 0)"
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["compare"]:
        parser = argparse.ArgumentParser(prog="codeharness.benchmark compare", description="比较两份真实评测报告")
        parser.add_argument("--baseline", required=True, type=Path)
        parser.add_argument("--treatment", required=True, type=Path)
        parser.add_argument("--baseline-variant", choices=("delegate", "no-delegate"))
        parser.add_argument("--treatment-variant", choices=("delegate", "no-delegate"))
        args = parser.parse_args(argv[1:])
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            treatment = json.loads(args.treatment.read_text(encoding="utf-8"))
            result = compare_reports(baseline, treatment, baseline_variant=args.baseline_variant,
                                     treatment_variant=args.treatment_variant)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except (ValueError, OSError, TypeError, KeyError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2

    parser = argparse.ArgumentParser(description="CodeHarness 独立验收与消融评测")
    parser.add_argument("--mode", choices=("fixtures", "model"), default="fixtures")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--suite", choices=("core", "full", "multi", "large"), default="core",
                           help="core=5 个基础任务；full=12 个基础任务；multi=3 个多模块任务；large=4 个大仓库任务")
    selection.add_argument("--task", action="append", choices=tuple(task.id for task in ALL_TASKS) + LARGE_TASK_IDS,
                           help="仅运行指定任务，可重复指定多个任务")
    parser.add_argument("--variants", choices=("delegate", "no-delegate", "both"), default="delegate")
    parser.add_argument("--repeats", type=int, default=1, help="真实模型评测的重复轮数")
    parser.add_argument("--disable-tool", action="append", default=[], metavar="NAME", help="禁用一个工具，可重复")
    parser.add_argument("--output", type=Path, help="新建报告目录；默认 .codeharness/benchmarks/<id>")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--model-pool", type=Path)
    parser.add_argument("--models", help="覆盖模型池顺序，使用逗号分隔")
    parser.add_argument("--reasoning-effort", help="模型支持时设置推理强度，例如 low")
    parser.add_argument("--base-url")
    parser.add_argument("--allow-exec", action="store_true", help="同意真实模型修改并在本机执行评测代码")
    parser.add_argument("--max-requests", type=int, default=12)
    parser.add_argument("--max-tokens", type=int, default=24000)
    parser.add_argument("--output-tokens", type=int, default=Limits.output_tokens, help="单次模型输出上限")
    parser.add_argument("--context-chars", type=int, default=Limits.context_chars, help="压缩上下文的字符阈值")
    parser.add_argument("--max-seconds", type=int, default=180)
    parser.add_argument("--total-requests", type=int)
    parser.add_argument("--total-tokens", type=int)
    args = parser.parse_args(argv)
    try:
        model = None
        if args.models and not args.model_pool:
            raise ValueError("--models 需要配合 --model-pool")
        if args.mode == "model":
            if not args.allow_exec:
                raise ValueError("真实模型评测需要 --allow-exec；测试会在本机执行项目代码")
            env = {**load_env(args.env_file), **os.environ}
            if args.model_pool:
                if args.model or args.base_url:
                    raise ValueError("--model-pool 使用池配置中的模型和接口地址")
                model = ModelPool(args.model_pool, env=env, order=args.models, reasoning_effort=args.reasoning_effort)
            else:
                name = args.model or env.get("CODEHARNESS_MODEL") or env.get("OPENAI_MODEL")
                url, key = model_connection(env, args.base_url)
                if not name or not url or name == "offline-demo":
                    raise ValueError("请配置实际模型名与接口地址；离线演示不能作为真实模型评测")
                model = ChatModel(name, url, key, reasoning_effort=args.reasoning_effort)
        elif args.model_pool:
            raise ValueError("模型池只用于真实模型评测")
        output = args.output or Path(".codeharness/benchmarks") / uuid.uuid4().hex[:10]
        variants = ("delegate", "no-delegate") if args.variants == "both" else (args.variants,)
        suite_map = {"core": TASKS[:5], "full": TASKS, "multi": MULTI_TASKS}
        if args.task:
            candidates = ALL_TASKS + (large_tasks() if set(args.task).intersection(LARGE_TASK_IDS) else ())
            by_id = {task.id: task for task in candidates}
            tasks = tuple(by_id[name] for name in dict.fromkeys(args.task))
        else:
            tasks = large_tasks() if args.suite == "large" else suite_map[args.suite]
        report = run_suite(tasks, output, model=model,
            limits=Limits(max_requests=args.max_requests, max_tokens=args.max_tokens,
                          output_tokens=args.output_tokens, context_chars=args.context_chars, max_seconds=args.max_seconds),
            variants=variants, total_requests=args.total_requests, total_tokens=args.total_tokens,
            disabled_tools=tuple(args.disable_tool), repeats=args.repeats)
        print(json.dumps({"mode": report["mode"], "report": str(output.resolve() / "report.json"),
                          "summary": report["summary"]}, ensure_ascii=False, indent=2))
        rows = report["cases"]
        if args.model_pool:
            rows = {(row["task"], row["variant"], row.get("repeat", 1)): row for row in rows}.values()
        return 0 if all(row.get("success", False) and not row.get("skipped") for row in rows) else 2
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
