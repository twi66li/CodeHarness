"""Offline regression for CodeHarness. Never calls a real model.

Runs: git facts, full unittest, reference fixtures (full + multi), deterministic demo
with and without delegation. Writes logs and summary.json under
.codeharness/regress/<tag>-<timestamp>/ (ignored by Git).

    python scripts/regress.py --tag s0
    python scripts/regress.py --tag s1 --compare .codeharness/regress/s0-xxxx/summary.json
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DEMO_TASK = "修复购物篮百分比折扣计算，并运行现有测试验证。"
NO_DELEGATE_DEMO = """
import json, sys
from pathlib import Path
from codeharness.demo import DemoModel, create_demo
from codeharness.runtime import Agent, Limits
from codeharness.store import Store
from codeharness.tools import Policy
workspace, database = Path(sys.argv[1]), Path(sys.argv[2])
create_demo(workspace)
store = Store(database)
try:
    result = Agent(DemoModel(), workspace, store, Policy(allow_write=True, allow_exec=True), Limits(),
                   enable_delegate=False).run(sys.argv[3])
    print(json.dumps({"status": result.status, "verification": result.verification,
                      "changed_files": result.changed_files, "usage": result.usage}, ensure_ascii=False))
finally:
    store.close()
"""


def run(cmd, log: Path, env=None):
    started = time.monotonic()
    try:
        process = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=1800)
        code, text = process.returncode, process.stdout + ("\n" if process.stdout and process.stderr else "") + process.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        code, text = -1, f"{type(exc).__name__}: {exc}"
    log.write_text(text, encoding="utf-8")
    return code, text, round(time.monotonic() - started, 2)


def git(*args):
    try:
        process = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30)
        return process.stdout.strip() if process.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def parse_unittest(text: str, code: int) -> dict:
    ran = re.search(r"^Ran (\d+) tests? in ([\d.]+)s", text, re.M)
    final = re.findall(r"^(OK|FAILED)(?: \((.*)\))?\s*$", text, re.M)
    counts = {}
    if final:
        for item in (final[-1][1] or "").split(","):
            key, _, value = item.strip().partition("=")
            if value.isdigit():
                counts[key] = int(value)
    return {
        "exit_code": code,
        "ok": bool(final) and final[-1][0] == "OK" and code == 0,
        "ran": int(ran.group(1)) if ran else None,
        "seconds": float(ran.group(2)) if ran else None,
        "failures": counts.get("failures", 0),
        "errors": counts.get("errors", 0),
        "skipped": counts.get("skipped", 0),
        "skipped_tests": [f"{m[0]}: {m[2].strip()}" for m in
                          re.findall(r"^(test\w+) \(([^)]+)\).*?\.\.\. skipped (.*)$", text, re.M)],
        "failed_tests": re.findall(r"^(?:FAIL|ERROR): (\S+ \([^)]+\))", text, re.M),
    }


def parse_json(text: str):
    start = text.find("{")
    try:
        return json.loads(text[start:]) if start >= 0 else None
    except ValueError:
        return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CodeHarness 离线回归（不调用真实模型）")
    parser.add_argument("--tag", default="regress", help="本次回归标签，例如 s0、s1")
    parser.add_argument("--skip-loopback", action="store_true", help="设置 CODEHARNESS_SKIP_LOOPBACK=1")
    parser.add_argument("--temp", type=Path, help="测试临时目录；Windows 默认 <系统盘>\\cht，规避 worktree 路径长度限制")
    parser.add_argument("--compare", type=Path, help="与之前的 summary.json 对比")
    args = parser.parse_args(argv)

    out = ROOT / ".codeharness" / "regress" / f"{args.tag}-{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=False)
    temp = args.temp or (Path(os.environ.get("SystemDrive", "C:") + "\\cht") if os.name == "nt" else None)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if temp:
        temp.mkdir(parents=True, exist_ok=True)
        env.update(TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp))
    if args.skip_loopback:
        env["CODEHARNESS_SKIP_LOOPBACK"] = "1"

    summary = {
        "tag": args.tag, "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "skip_loopback": args.skip_loopback, "temp": str(temp) if temp else None,
        "git": {"head": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
                "origin_main": git("rev-parse", "origin/main"), "status": git("status", "--short", "--branch")},
    }
    print(f"[regress] 输出目录：{out}", flush=True)

    print("[regress] 单元测试 ...", flush=True)
    code, text, _ = run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                        out / "unittest.log", env)
    summary["unittest"] = parse_unittest(text, code)

    summary["fixtures"] = {}
    for suite in ("full", "multi"):
        print(f"[regress] 参考夹具 {suite} ...", flush=True)
        target = out / f"fixtures-{suite}"
        code, _, seconds = run([sys.executable, "-B", "-m", "codeharness.benchmark", "--mode", "fixtures",
                                "--suite", suite, "--output", str(target)], out / f"fixtures-{suite}.log", env)
        report = target / "report.json"
        ref = json.loads(report.read_text(encoding="utf-8")).get("summary", {}).get("reference", {}) if report.exists() else {}
        summary["fixtures"][suite] = {"exit_code": code, "attempted": ref.get("attempted"),
                                      "passed": ref.get("passed"), "seconds": seconds}

    summary["demo"] = {}
    print("[regress] 离线 demo（启用委派）...", flush=True)
    _, text, seconds = run([sys.executable, "-B", "-m", "codeharness", "demo", "--directory", str(out / "demo-delegate"),
                            "--store", str(out / "demo-delegate.sqlite3"), "--json"], out / "demo-delegate.log", env)
    data = parse_json(text) or {}
    summary["demo"]["delegate"] = {"status": data.get("status"), "verification": data.get("verification"),
                                   "requests": (data.get("usage") or {}).get("requests"), "seconds": seconds}
    print("[regress] 离线 demo（禁用委派）...", flush=True)
    _, text, seconds = run([sys.executable, "-B", "-c", NO_DELEGATE_DEMO, str(out / "demo-no-delegate"),
                            str(out / "demo-no-delegate.sqlite3"), DEMO_TASK], out / "demo-no-delegate.log", env)
    data = parse_json(text) or {}
    summary["demo"]["no_delegate"] = {"status": data.get("status"), "verification": data.get("verification"),
                                      "requests": (data.get("usage") or {}).get("requests"), "seconds": seconds}

    unit = summary["unittest"]
    summary["passed"] = (unit["ok"]
                         and all(f["attempted"] and f["passed"] == f["attempted"] for f in summary["fixtures"].values())
                         and all(d["status"] == "verified" for d in summary["demo"].values()))
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\n===== 回归结果 =====")
    print(f"HEAD {summary['git']['head']}  分支 {summary['git']['branch']}  origin/main {summary['git']['origin_main']}")
    print(f"单元测试：ran={unit['ran']} failures={unit['failures']} errors={unit['errors']} skipped={unit['skipped']}"
          f" -> {'OK' if unit['ok'] else 'FAILED'}")
    for name in unit["skipped_tests"]:
        print(f"  跳过 {name}")
    for name in unit["failed_tests"]:
        print(f"  失败 {name}")
    for suite, item in summary["fixtures"].items():
        print(f"夹具 {suite}：{item['passed']}/{item['attempted']}（{item['seconds']}s）")
    for variant, item in summary["demo"].items():
        print(f"demo {variant}：{item['status']}，{item['requests']} 次请求")
    print(f"总体：{'通过' if summary['passed'] else '未通过'}；summary：{out / 'summary.json'}")

    if args.compare:
        old = json.loads(args.compare.read_text(encoding="utf-8"))
        print("\n===== 与基线对比 =====")
        pairs = [("单元测试 ran", old["unittest"]["ran"], unit["ran"]),
                 ("单元测试 skipped", old["unittest"]["skipped"], unit["skipped"])]
        pairs += [(f"夹具 {s} passed", old["fixtures"][s]["passed"], summary["fixtures"][s]["passed"])
                  for s in summary["fixtures"] if s in old.get("fixtures", {})]
        pairs += [(f"demo {v} requests", old["demo"][v]["requests"], summary["demo"][v]["requests"])
                  for v in summary["demo"] if v in old.get("demo", {})]
        for label, before, after in pairs:
            print(f"{label}: {before} -> {after}{'' if before == after else '  ← 变化'}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
