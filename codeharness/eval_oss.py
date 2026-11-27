"""Real open-source GitHub Issue/PR benchmark (Fix with F2P/P2P + Review with LLM-as-a-Judge)."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

from .cli import build_model, load_env
from .models import Model
from .runtime import Agent, Limits
from .store import Store
from .tools import Policy

TASKS_FILE = Path(__file__).with_name("eval_oss_tasks.json")
PYTEST_NODE_RE = re.compile(r"^(\S+::\S+.*?)\s+(PASSED|FAILED|ERROR)\b")

REVIEW_PROMPT = """请以资深代码审查专家的身份，审查下面这个真实开源 PR 的代码变更（git diff）。
你可以在工作区只读查看相关源码以核实上下文，但**禁止修改任何文件**。

审查节奏与要求：
1. 最多使用 2～4 轮只读工具（可同轮并行读取多个相关文件）核实 diff 上下文与调用方，**切勿遍历整个仓库或反复分页读取无关代码**，核实完立即收尾。
2. 仔细审查 diff 中的真实代码缺陷：逻辑错误、边界/空值/类型漏洞、异常处理或递归深度问题、格式化错误、API 向后兼容性破坏与回归风险。
3. 不要报告纯代码风格、命名偏好或文档措辞；对于有明确代码依据的真实缺陷或高风险边界问题，请全部准确列出（若确实完全无缺陷再返回 `[]`）。

最终请**严格只输出一个 JSON 代码块**，格式如下：
```json
[
  {
    "file": "相对文件路径",
    "line": "涉及行号或函数名",
    "severity": "high | medium | low",
    "issue": "具体缺陷描述、触发条件与影响"
  }
]
```
"""

JUDGE_PROMPT = """你是一个严格、客观的代码审查评测裁判（LLM-as-a-Judge）。
给定：
1. 一个真实开源 PR 的变更 diff；
2. 该 PR 事后被真实 Bug Fix 所证实的 Ground Truth 缺陷列表；
3. 待评测代码审查 Agent 输出的 findings 列表。

请你逐条评判 Agent 的每一条 finding：
- 如果该 finding 准确命中了某条 Ground Truth（核心根因与影响位置一致），设 `is_true_positive=true` 并填入 `matched_gt_index`（从 0 开始）。
- 如果该 finding 未命中 Ground Truth，但在给定 diff 中确实指出了一个明确、可复现的真实代码缺陷/边界错误/回归风险（而非代码风格、注释建议、过度假设或误报），也可以设 `is_true_positive=true`、`matched_gt_index=null`，并在 `reason` 中给出代码依据。
- 如果该 finding 是误报、臆测、风格吹毛求疵或与代码事实不符，必须设 `is_true_positive=false`、`matched_gt_index=null`。

请严格只输出一个 JSON 对象，格式如下：
```json
{
  "verdicts": [
    {
      "finding_index": 0,
      "is_true_positive": true,
      "matched_gt_index": 0,
      "reason": "简明客观的判定依据"
    }
  ]
}
```
"""


def load_manifest(path: Path = TASKS_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_repo(cache_dir: Path, name: str, url: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo = cache_dir / name
    if not (repo / ".git").exists():
        subprocess.run(["git", "clone", "--quiet", url, str(repo)], check=True)
    return repo


def split_commit_patches(repo: Path, fix_commit: str) -> tuple[str, list[str], list[str], bytes, bytes]:
    full_sha = subprocess.check_output(["git", "rev-parse", fix_commit], cwd=repo, text=True).strip()
    base_sha = subprocess.check_output(["git", "rev-parse", f"{full_sha}^"], cwd=repo, text=True).strip()
    files = subprocess.check_output(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", full_sha],
        cwd=repo, text=True, encoding="utf-8", errors="replace",
    ).splitlines()
    src_files = [f for f in files if f.startswith("src/") and f.endswith(".py")]
    test_files = [f for f in files if f.startswith(("tests/", "testing/")) and f.endswith(".py")]
    test_patch = subprocess.check_output(["git", "diff", base_sha, full_sha, "--", *test_files], cwd=repo)
    gold_patch = subprocess.check_output(["git", "diff", base_sha, full_sha, "--", *src_files], cwd=repo)
    return base_sha, src_files, test_files, test_patch, gold_patch


def parse_pytest_nodes(stdout: str) -> tuple[list[str], list[str]]:
    passed, failed = [], []
    for line in stdout.splitlines():
        match = PYTEST_NODE_RE.match(line)
        if not match:
            continue
        node, status = match.group(1), match.group(2)
        if status == "PASSED":
            passed.append(node)
        else:
            failed.append(node)
    return passed, failed


def run_pytest(workspace: Path, test_files: list[str], python_exe: str = sys.executable,
               timeout: int = 60) -> tuple[int, list[str], list[str], str]:
    env = dict(os.environ)
    src_dir = workspace / "src"
    env["PYTHONPATH"] = str(src_dir) if src_dir.is_dir() else str(workspace)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [python_exe, "-m", "pytest", *test_files, "-vv", "--tb=short", "-p", "no:cacheprovider"],
            cwd=workspace, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return -1, [], [], "pytest timed out"
    passed, failed = parse_pytest_nodes(proc.stdout)
    return proc.returncode, passed, failed, (proc.stdout + proc.stderr)[-4000:]


def extract_json_payload(text: str):
    fenced = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    candidates = [*fenced, text]
    for raw in candidates:
        raw = raw.strip()
        if not raw:
            continue
        try:
            return json.loads(raw)
        except ValueError:
            pairs = sorted(
                ((raw.find(o), o, c) for o, c in (("{", "}"), ("[", "]")) if raw.find(o) != -1),
                key=lambda item: item[0],
            )
            for start, _, close_ch in pairs:
                end = raw.rfind(close_ch)
                if end > start:
                    try:
                        return json.loads(raw[start:end + 1])
                    except ValueError:
                        continue
    return None


def compute_review_metrics(cases: list[dict]) -> dict:
    total_findings = sum(len(c.get("findings", [])) for c in cases)
    total_tp = sum(c.get("true_positives", 0) for c in cases)
    total_gt = sum(len(c.get("ground_truth", [])) for c in cases)
    total_gt_hit = sum(c.get("gt_hits", 0) for c in cases)
    precision = total_tp / total_findings if total_findings else 0.0
    recall = total_gt_hit / total_gt if total_gt else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "tasks": len(cases),
        "total_findings": total_findings,
        "true_positives": total_tp,
        "false_positives": total_findings - total_tp,
        "total_ground_truth": total_gt,
        "ground_truth_hits": total_gt_hit,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def validate_manifest(manifest: dict, cache_dir: Path, python_exe: str = sys.executable,
                      task_ids: set[str] | None = None) -> dict:
    repos = {name: ensure_repo(cache_dir, name, url) for name, url in manifest["repos"].items()}
    fix_results = []
    for task in manifest["fix_tasks"]:
        if task_ids and task["id"] not in task_ids:
            continue
        repo = repos[task["repo"]]
        base_sha, src_files, test_files, test_patch, gold_patch = split_commit_patches(repo, task["fix_commit"])
        with tempfile.TemporaryDirectory() as td:
            wt = Path(td) / "wt"
            subprocess.run(["git", "worktree", "add", "--detach", "--quiet", str(wt), base_sha], cwd=repo, check=True)
            try:
                subprocess.run(["git", "apply", "--whitespace=nowarn"], input=test_patch, cwd=wt, check=True)
                _, p1, f1, _ = run_pytest(wt, test_files, python_exe=python_exe)
                subprocess.run(["git", "apply", "--whitespace=nowarn"], input=gold_patch, cwd=wt, check=True)
                rc2, p2, f2, tail = run_pytest(wt, test_files, python_exe=python_exe)
                valid = bool(f1) and not f2 and rc2 == 0 and set(f1).issubset(p2) and set(p1).issubset(p2)
                fix_results.append({
                    "id": task["id"], "repo": task["repo"], "valid": valid,
                    "fail_to_pass": len(f1), "pass_to_pass": len(p1),
                    "after_passed": len(p2), "after_failed": len(f2),
                    "error": "" if valid else tail[-500:],
                })
            finally:
                subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=repo, capture_output=True)

    review_results = []
    for task in manifest["review_tasks"]:
        if task_ids and task["id"] not in task_ids:
            continue
        repo = repos[task["repo"]]
        full = subprocess.check_output(["git", "rev-parse", task["pr_commit"]], cwd=repo, text=True).strip()
        diff = subprocess.check_output(
            ["git", "diff", f"{full}^", full, "--", "*.py"],
            cwd=repo, text=True, encoding="utf-8", errors="replace",
        )
        review_results.append({
            "id": task["id"], "repo": task["repo"], "valid": bool(diff.strip()),
            "diff_lines": len(diff.splitlines()), "gt_count": len(task["ground_truth"]),
        })

    return {
        "mode": "oss_manifest_validation",
        "fix_valid": sum(1 for r in fix_results if r["valid"]),
        "fix_total": len(fix_results),
        "total_fail_to_pass": sum(r["fail_to_pass"] for r in fix_results),
        "total_pass_to_pass": sum(r["pass_to_pass"] for r in fix_results),
        "review_valid": sum(1 for r in review_results if r["valid"]),
        "review_total": len(review_results),
        "fix_results": fix_results,
        "review_results": review_results,
    }


def evaluate_fix_task(task: dict, repo: Path, model: Model, case_dir: Path, *,
                      limits: Limits, python_exe: str, tool_profile: str,
                      enable_bash: bool) -> dict:
    base_sha, src_files, test_files, test_patch, _ = split_commit_patches(repo, task["fix_commit"])
    case_dir.mkdir(parents=True, exist_ok=True)
    # 1. Measure baseline F2P and P2P in a throwaway worktree so test_patch never leaks into Agent's workspace.
    with tempfile.TemporaryDirectory() as td:
        probe = Path(td) / "probe"
        subprocess.run(["git", "worktree", "add", "--detach", "--quiet", str(probe), base_sha], cwd=repo, check=True)
        try:
            subprocess.run(["git", "apply", "--whitespace=nowarn"], input=test_patch, cwd=probe, check=True)
            _, baseline_p2p, baseline_f2p, _ = run_pytest(probe, test_files, python_exe=python_exe)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(probe)], cwd=repo, capture_output=True)

    wt = (case_dir / "repo").resolve()
    subprocess.run(["git", "worktree", "add", "--detach", "--quiet", str(wt), base_sha], cwd=repo, check=True)
    store = Store(case_dir / "state.sqlite3")
    prev_pypath = os.environ.get("PYTHONPATH")
    try:
        os.environ["PYTHONPATH"] = str(wt / "src")
        prompt = (
            f"仓库：{task['repo']}\n"
            f"标题：{task['title']}\n\n"
            f"问题描述：\n{task['problem_statement']}\n\n"
            f"要求：\n"
            f"1. 仅修改必要的源码实现，定位根因并修复问题，避免破坏现有行为。\n"
            f"2. 可运行已有测试验证（测试路径参考：{', '.join(test_files)}，支持 pytest）。\n"
            f"3. 完成后简要总结修改内容与测试结果。"
        )
        policy = Policy(allow_write=True, allow_exec=True, pass_env=("PYTHONPATH",))
        started = time.monotonic()
        agent = Agent(model, wt, store, policy, limits,
                      enable_delegate=False, enable_bash=enable_bash, tool_profile=tool_profile)
        try:
            res = agent.run(prompt)
        finally:
            agent.close()
        seconds = round(time.monotonic() - started, 3)

        agent_diff = subprocess.check_output(
            ["git", "diff", "HEAD"], cwd=wt, text=True, encoding="utf-8", errors="replace"
        )
        # Apply hidden test_patch externally and evaluate F2P + P2P.
        apply_proc = subprocess.run(["git", "apply", "--whitespace=nowarn"], input=test_patch, cwd=wt, capture_output=True)
        if apply_proc.returncode != 0:
            # If agent edited the same test file, restore test files to base before applying hidden test_patch.
            subprocess.run(["git", "checkout", "HEAD", "--", *test_files], cwd=wt, check=True)
            subprocess.run(["git", "apply", "--whitespace=nowarn"], input=test_patch, cwd=wt, check=True)
        rc, after_passed, after_failed, tail = run_pytest(wt, test_files, python_exe=python_exe)
        passed_set = set(after_passed)
        f2p_passed = [n for n in baseline_f2p if n in passed_set]
        p2p_passed = [n for n in baseline_p2p if n in passed_set]
        resolved = bool(baseline_f2p) and len(f2p_passed) == len(baseline_f2p) and len(p2p_passed) == len(baseline_p2p) and not after_failed and rc == 0
        return {
            "id": task["id"],
            "repo": task["repo"],
            "fix_commit": task["fix_commit"],
            "base_commit": base_sha,
            "resolved": resolved,
            "agent_status": res.status,
            "fail_to_pass_passed": len(f2p_passed),
            "fail_to_pass_total": len(baseline_f2p),
            "pass_to_pass_passed": len(p2p_passed),
            "pass_to_pass_total": len(baseline_p2p),
            "after_failed": after_failed[:20],
            "changed_files": res.changed_files,
            "diff_lines": len(agent_diff.splitlines()),
            "usage": res.usage,
            "seconds": seconds,
            "session_id": res.session_id,
            "pytest_tail": "" if resolved else tail[-1000:],
        }
    finally:
        if prev_pypath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = prev_pypath
        store.close()
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=repo, capture_output=True)


def _complete_with_retry(model: Model, messages: list[dict], max_tokens: int, *, attempts: int = 3):
    from .models import ModelError
    curr_tokens = max_tokens
    use_stream = bool(getattr(model, "supports_stream", False))
    for attempt in range(1, attempts + 1):
        try:
            if use_stream:
                return model.complete(messages, [], curr_tokens, timeout=90, on_delta=lambda _k, _c: None)
            return model.complete(messages, [], curr_tokens, timeout=90)
        except ModelError as exc:
            if exc.truncated and curr_tokens < 8192 and attempt < attempts:
                curr_tokens = min(curr_tokens * 2, 8192)
                continue
            if not exc.retryable or attempt >= attempts:
                raise
            delay = exc.retry_after if exc.retry_after is not None else 2.0 * (2 ** (attempt - 1))
            time.sleep(min(delay, 10.0))


def evaluate_review_task(task: dict, repo: Path, reviewer_model: Model, judge_model: Model,
                         case_dir: Path, *, limits: Limits) -> dict:
    full_sha = subprocess.check_output(["git", "rev-parse", task["pr_commit"]], cwd=repo, text=True).strip()
    diff_text = subprocess.check_output(
        ["git", "diff", f"{full_sha}^", full_sha, "--", "*.py"],
        cwd=repo, text=True, encoding="utf-8", errors="replace",
    )
    case_dir.mkdir(parents=True, exist_ok=True)
    wt = (case_dir / "repo").resolve()
    subprocess.run(["git", "worktree", "add", "--detach", "--quiet", str(wt), full_sha], cwd=repo, check=True)
    store = Store(case_dir / "state.sqlite3")
    try:
        prompt = (
            f"{REVIEW_PROMPT}\n"
            f"仓库：{task['repo']}\n"
            f"PR 标题：{task['title']}\n\n"
            f"PR Diff：\n```diff\n{diff_text[:18000]}\n```"
        )
        started = time.monotonic()
        agent = Agent(reviewer_model, wt, store, Policy(readonly=True), limits,
                      enable_delegate=False, enable_bash=False, tool_profile="default")
        try:
            res = agent.run(prompt, readonly=False)
        finally:
            agent.close()

        answer_text = res.answer
        finalize_usage = {"input_tokens": 0, "output_tokens": 0}
        # Budget-aware wrap-up: distill collected tool evidence into a clean tool-free request
        # (no tool_calls/tool roles in messages when tools=[], avoiding provider 400/502 errors).
        if res.status == "budget_exhausted" or extract_json_payload(answer_text) is None:
            evidence_parts = []
            for ev in store.events(res.session_id, expand=False):
                if ev["kind"] == "tool_finished":
                    data = ev["data"]
                    if data.get("result", {}).get("ok"):
                        snippet = json.dumps(data["result"], ensure_ascii=False)[:1200]
                        evidence_parts.append(f"[{data['name']}] {snippet}")
            evidence_text = "\n\n".join(evidence_parts[-4:])[:4000]
            from .models import ModelError
            wrap = None
            for diff_cap, ev_cap in ((5000, 2500), (2500, 0)):
                ev_part = f"\n\n已读取的源码上下文：\n{evidence_text[:ev_cap]}" if ev_cap and evidence_text else ""
                wrap_messages = [
                    {"role": "system", "content": (
                        "你是资深代码审查专家。探索阶段已结束，请不要调用工具。"
                        "请基于给定的 PR Diff 和已读取的源码证据，直接输出结构化 JSON 数组报告所有高置信度的逻辑缺陷、边界漏洞、异常处理问题或兼容性风险。"
                        "格式：[{\"file\": \"...\", \"line\": \"...\", \"severity\": \"high|medium|low\", \"issue\": \"...\"}]。"
                    )},
                    {"role": "user", "content": (
                        f"仓库：{task['repo']}\nPR 标题：{task['title']}\n\n"
                        f"PR Diff：\n```diff\n{diff_text[:diff_cap]}\n```"
                        f"{ev_part}\n\n"
                        "请严格只输出一个 JSON 数组代码块。"
                    )},
                ]
                try:
                    wrap = _complete_with_retry(reviewer_model, wrap_messages, 4096, attempts=3)
                    break
                except ModelError as exc:
                    print(f"    [wrap retry diff={diff_cap}] {exc}", flush=True)
                    if ev_cap == 0:
                        wrap = None
            if wrap is not None:
                answer_text = wrap.message.get("content", "") or answer_text
                finalize_usage = {"input_tokens": wrap.input_tokens, "output_tokens": wrap.output_tokens}

        seconds = round(time.monotonic() - started, 3)

        parsed = extract_json_payload(answer_text)
        findings = [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []

        judge_usage = {"input_tokens": 0, "output_tokens": 0}
        verdicts = []
        if findings:
            from .models import ModelError
            judge_reply = None
            for diff_cap in (4000, 1200, 0):
                diff_part = f"\n\nPR Diff 节选：\n```diff\n{diff_text[:diff_cap]}\n```" if diff_cap else ""
                judge_user = (
                    f"PR 标题：{task['title']}\n\n"
                    f"Ground Truth 真实缺陷：\n{json.dumps(task['ground_truth'], ensure_ascii=False, indent=2)}\n\n"
                    f"Agent 审查 Findings：\n{json.dumps(findings, ensure_ascii=False, indent=2)}"
                    f"{diff_part}"
                )
                try:
                    judge_reply = _complete_with_retry(
                        judge_model,
                        [{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": judge_user}],
                        2048, attempts=3,
                    )
                    break
                except ModelError:
                    if diff_cap == 0:
                        raise
            judge_usage = {"input_tokens": judge_reply.input_tokens, "output_tokens": judge_reply.output_tokens}
            judge_json = extract_json_payload(judge_reply.message.get("content", ""))
            if isinstance(judge_json, dict) and isinstance(judge_json.get("verdicts"), list):
                verdicts = [v for v in judge_json["verdicts"] if isinstance(v, dict)]

        tp_indices = {v.get("finding_index") for v in verdicts if v.get("is_true_positive")}
        gt_hits = {
            v.get("matched_gt_index") for v in verdicts
            if v.get("is_true_positive") and isinstance(v.get("matched_gt_index"), int)
            and 0 <= v["matched_gt_index"] < len(task["ground_truth"])
        }
        merged_usage = dict(res.usage)
        merged_usage["input_tokens"] = merged_usage.get("input_tokens", 0) + finalize_usage["input_tokens"]
        merged_usage["output_tokens"] = merged_usage.get("output_tokens", 0) + finalize_usage["output_tokens"]
        return {
            "id": task["id"],
            "repo": task["repo"],
            "pr_commit": task["pr_commit"],
            "agent_status": res.status,
            "findings": findings,
            "ground_truth": task["ground_truth"],
            "verdicts": verdicts,
            "true_positives": len([i for i in tp_indices if isinstance(i, int) and 0 <= i < len(findings)]),
            "gt_hits": len(gt_hits),
            "usage": merged_usage,
            "judge_usage": judge_usage,
            "seconds": seconds,
            "session_id": res.session_id,
        }
    finally:
        store.close()
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=repo, capture_output=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CodeHarness 真实开源 Issue/PR 评测套件")
    p.add_argument("mode", choices=["validate", "run-fix", "run-review", "run-all"])
    p.add_argument("--manifest", type=Path, default=TASKS_FILE)
    p.add_argument("--cache-dir", type=Path, default=Path(".codeharness/oss_repos"))
    p.add_argument("--output", type=Path)
    p.add_argument("--task", action="append", default=[], help="仅运行指定任务 ID，可重复")
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--model")
    p.add_argument("--judge-model")
    p.add_argument("--provider", choices=["openai", "anthropic"], default="openai")
    p.add_argument("--base-url")
    p.add_argument("--reasoning-effort")
    p.add_argument("--tool-profile", choices=["default", "pi"], default="default")
    p.add_argument("--enable-bash", action="store_true")
    p.add_argument("--fix-requests", type=int, default=30)
    p.add_argument("--fix-tokens", type=int, default=200000)
    p.add_argument("--review-requests", type=int, default=16)
    p.add_argument("--review-tokens", type=int, default=80000)
    p.add_argument("--output-tokens", type=int, default=4096)
    p.add_argument("--total-tokens", type=int, default=28000000)
    args = p.parse_args(argv)

    manifest = load_manifest(args.manifest)
    task_filter = set(args.task) if args.task else None

    if args.mode == "validate":
        report = validate_manifest(manifest, args.cache_dir, python_exe=sys.executable, task_ids=task_filter)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        ok = report["fix_valid"] == report["fix_total"] and report["review_valid"] == report["review_total"]
        return 0 if ok else 2

    env = {**load_env(args.env_file), **os.environ}
    model_name = args.model or env.get("CODEHARNESS_MODEL") or env.get("OPENAI_MODEL")
    judge_name = args.judge_model or model_name
    model = build_model(model_name or "", provider=args.provider, env=env, base_url=args.base_url,
                        timeout=120, reasoning_effort=args.reasoning_effort)
    judge_model = build_model(judge_name or "", provider=args.provider, env=env, base_url=args.base_url,
                              timeout=120, reasoning_effort=args.reasoning_effort)
    repos = {name: ensure_repo(args.cache_dir, name, url) for name, url in manifest["repos"].items()}

    out_dir = args.output or Path(".codeharness/benchmarks") / f"oss-{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "report.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["mode"] = args.mode
        report.setdefault("fix_cases", [])
        report.setdefault("review_cases", [])
        spent_tokens = int(report.get("spent_tokens", 0))
    else:
        report = {"mode": args.mode, "model": model.name, "judge_model": judge_model.name,
                  "tool_profile": args.tool_profile, "enable_bash": args.enable_bash,
                  "total_tokens_budget": args.total_tokens, "fix_cases": [], "review_cases": []}
        spent_tokens = 0
    done_fix = {c["id"] for c in report["fix_cases"]}
    done_review = {c["id"] for c in report["review_cases"]}

    if args.mode in {"run-fix", "run-all"}:
        fix_limits = Limits(max_requests=args.fix_requests, max_tokens=args.fix_tokens,
                            output_tokens=args.output_tokens, context_chars=48000, max_seconds=300)
        for task in manifest["fix_tasks"]:
            if (task_filter and task["id"] not in task_filter) or task["id"] in done_fix:
                continue
            if spent_tokens + args.fix_tokens > args.total_tokens:
                print(f"[SKIP fix] {task['id']} 超出总预算", flush=True)
                break
            print(f"[RUN fix] {task['id']} ({task['repo']}) ...", flush=True)
            row = evaluate_fix_task(task, repos[task["repo"]], model, out_dir / "fix" / task["id"],
                                    limits=fix_limits, python_exe=sys.executable,
                                    tool_profile=args.tool_profile, enable_bash=args.enable_bash)
            spent_tokens += row["usage"]["input_tokens"] + row["usage"]["output_tokens"]
            report["fix_cases"].append(row)
            report["spent_tokens"] = spent_tokens
            print(f"  -> resolved={row['resolved']} F2P={row['fail_to_pass_passed']}/{row['fail_to_pass_total']} "
                  f"P2P={row['pass_to_pass_passed']}/{row['pass_to_pass_total']} "
                  f"status={row['agent_status']} req={row['usage']['requests']} "
                  f"tok={row['usage']['input_tokens']+row['usage']['output_tokens']} ({row['seconds']}s)", flush=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.mode in {"run-review", "run-all"}:
        review_limits = Limits(max_requests=args.review_requests, max_tokens=args.review_tokens,
                               output_tokens=args.output_tokens, context_chars=48000, max_seconds=300)
        for task in manifest["review_tasks"]:
            if (task_filter and task["id"] not in task_filter) or task["id"] in done_review:
                continue
            if spent_tokens + args.review_tokens > args.total_tokens:
                print(f"[SKIP review] {task['id']} 超出总预算", flush=True)
                break
            print(f"[RUN review] {task['id']} ({task['repo']}) ...", flush=True)
            row = evaluate_review_task(task, repos[task["repo"]], model, judge_model,
                                       out_dir / "review" / task["id"], limits=review_limits)
            spent_tokens += (row["usage"]["input_tokens"] + row["usage"]["output_tokens"]
                             + row["judge_usage"]["input_tokens"] + row["judge_usage"]["output_tokens"])
            report["review_cases"].append(row)
            report["spent_tokens"] = spent_tokens
            print(f"  -> findings={len(row['findings'])} TP={row['true_positives']} "
                  f"GT_hit={row['gt_hits']}/{len(row['ground_truth'])} "
                  f"tok={row['usage']['input_tokens']+row['usage']['output_tokens']} ({row['seconds']}s)", flush=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    report["spent_tokens"] = spent_tokens
    if report["fix_cases"]:
        report["fix_summary"] = {
            "resolved": sum(1 for c in report["fix_cases"] if c["resolved"]),
            "total": len(report["fix_cases"]),
            "fail_to_pass_passed": sum(c["fail_to_pass_passed"] for c in report["fix_cases"]),
            "fail_to_pass_total": sum(c["fail_to_pass_total"] for c in report["fix_cases"]),
            "pass_to_pass_passed": sum(c["pass_to_pass_passed"] for c in report["fix_cases"]),
            "pass_to_pass_total": sum(c["pass_to_pass_total"] for c in report["fix_cases"]),
        }
    if report["review_cases"]:
        report["review_summary"] = compute_review_metrics(report["review_cases"])

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== SUMMARY ===")
    print(json.dumps({k: v for k, v in report.items() if k not in {"fix_cases", "review_cases"}},
                     ensure_ascii=False, indent=2))
    print(f"Report saved to: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
