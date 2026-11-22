import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


S0 = "1a912f53c6749ba38d9b37e68a1eb129434e6151"
PROJECT = Path(__file__).resolve().parents[1]
RUNNER = """
import json, statistics, sys, time
from pathlib import Path
from codeharness.demo import DemoModel
from codeharness.runtime import Agent, Limits
from codeharness.store import Store

class MeteredStore(Store):
    spent = 0.0

    def _measure(self, run, *args, **kwargs):
        started = time.perf_counter()
        try:
            return run(*args, **kwargs)
        finally:
            self.spent += time.perf_counter() - started

    def append(self, *args, **kwargs):
        return self._measure(super().append, *args, **kwargs)

    def events(self, *args, **kwargs):
        return self._measure(super().events, *args, **kwargs)

    def usage(self, *args, **kwargs):
        return self._measure(super().usage, *args, **kwargs)

    def artifact(self, *args, **kwargs):
        return self._measure(super().artifact, *args, **kwargs)

class Workload:
    name = 'scale-fixture'

    def __init__(self, store):
        self.store = store
        self.samples = []

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        self.samples.append(self.store.spent)
        self.store.spent = 0.0
        turn = len(self.samples)
        if turn > 300:
            return DemoModel.text('done')
        return DemoModel.call('read_file', {'path': 'data.txt', 'start_line': turn, 'lines': 8})

root = Path(sys.argv[1])
root.mkdir()
workspace = root / 'repo'
workspace.mkdir()
(workspace / 'AGENTS.md').write_text('Stable context. ' * 600, encoding='utf-8')
(workspace / 'data.txt').write_text(''.join(f'{idx:04d} ' + 'x' * 60 + '\\n' for idx in range(320)), encoding='utf-8')
database = root / 'state.sqlite3'
store = MeteredStore(database)
try:
    model = Workload(store)
    result = Agent(model, workspace, store, limits=Limits(max_requests=301, max_tokens=10_000_000,
        output_tokens=64, context_chars=12000, max_seconds=180), enable_delegate=False).run('Read 300 windows')
    assert (result.status, result.usage['requests']) == ('completed', 301), result
finally:
    store.close()
early = statistics.median(model.samples[5:15])
late = statistics.median(model.samples[290:300])
print(json.dumps({'db_bytes': database.stat().st_size, 'early_ms': early * 1000, 'late_ms': late * 1000}))
"""


@unittest.skipUnless(os.environ.get("CODEHARNESS_SCALE_TESTS") == "1", "设置 CODEHARNESS_SCALE_TESTS=1 运行规模测试")
class ScaleTests(unittest.TestCase):
    def test_storage_size_and_late_round_latency_against_frozen_s0(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = root / "baseline"
            paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", S0, "codeharness"],
                                            cwd=PROJECT, text=True).splitlines()
            self.assertIn("codeharness/store.py", paths)
            for name in paths:
                target = baseline / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(["git", "show", f"{S0}:{name}"], cwd=PROJECT))
            results = {}
            for name, source in (("s0", baseline), ("current", PROJECT)):
                run = subprocess.run([sys.executable, "-B", "-c", RUNNER, str(root / name)], cwd=source,
                                     capture_output=True, text=True, encoding="utf-8", timeout=180)
                self.assertEqual(run.returncode, 0, run.stderr)
                results[name] = json.loads(run.stdout)
        print(json.dumps(results, indent=2))
        self.assertLessEqual(results["current"]["db_bytes"], 0.5 * results["s0"]["db_bytes"], results)
        self.assertLessEqual(results["current"]["late_ms"], 2 * results["current"]["early_ms"], results)
