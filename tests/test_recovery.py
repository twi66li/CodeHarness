"""Exercise persisted state after the worker process exits without cleanup."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from codeharness.demo import DemoModel
from codeharness.runtime import Agent
from codeharness.store import Store
from codeharness.tools import Policy


CRASH = r"""
import json
import os
from pathlib import Path
import sys
from codeharness.store import Store

root = Path(sys.argv[1])
db = Path(sys.argv[2])
stage = int(sys.argv[3])
store = Store(db)
sid = store.create(root, 'crash-fixture')
store.append(sid, 'message', {'role': 'system', 'content': 'fixture'})
store.append(sid, 'message', {'role': 'user', 'content': '创建 once.py'})
store.append(sid, 'baseline', {'files': {}})
store.append(sid, 'message', {'role': 'assistant', 'content': '', 'tool_calls': [
    {'id': 'crash-call', 'type': 'function', 'function': {'name': 'write_file',
    'arguments': json.dumps({'path': 'once.py', 'content': 'once'})}}]})
if stage >= 1:
    store.append(sid, 'tool_started', {'call_id': 'crash-call', 'name': 'write_file'})
if stage >= 2:
    (root / 'once.py').write_text('once', encoding='utf-8')
if stage >= 3:
    store.append(sid, 'tool_finished', {'call_id': 'crash-call', 'name': 'write_file',
                                      'result': {'ok': True, 'output': {'path': 'once.py'}}})
os._exit(19)
"""

PARALLEL_CRASH = r"""
import os, sys
from pathlib import Path
from codeharness.demo import DemoModel
from codeharness.runtime import Agent
from codeharness.store import Store

class CrashStore(Store):
    def append(self, sid, kind, data):
        super().append(sid, kind, data)
        if kind == 'tool_finished':
            os._exit(29)

class ParallelModel:
    name = 'fixture'

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        result = DemoModel.call('read_file', {'path': 'a.txt'})
        result.message['tool_calls'] += DemoModel.call('read_file', {'path': 'b.txt'}).message['tool_calls']
        return result

root = Path(sys.argv[1])
Agent(ParallelModel(), root, CrashStore(Path(sys.argv[2]))).run('Read both files')
"""


class RecoveryModel:
    name = "recovery-test-double"

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        return DemoModel.text("检查结束")


class RecoveryTests(unittest.TestCase):
    def test_parallel_read_crash_recovers_recorded_and_uncertain_results(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            for name in ("a.txt", "b.txt"):
                (root / name).write_text("fixture", encoding="utf-8")
            db = Path(temp) / "state.sqlite3"
            process = subprocess.run([sys.executable, "-B", "-c", PARALLEL_CRASH, str(root), str(db)],
                                     cwd=project, capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 29, process.stderr)
            store = Store(db)
            try:
                sid = store.sessions()[0]["id"]
                result = Agent(RecoveryModel(), root, store).run("继续", session_id=sid)
                messages = [json.loads(m["content"]) for m in store.messages(sid) if m["role"] == "tool"]
                self.assertEqual(result.status, "completed")
                self.assertEqual(len(messages), 2)
                self.assertTrue(messages[0]["ok"])
                self.assertIn("安全地重新执行", messages[1]["error"])
                self.assertEqual(sum(e["kind"] == "tool_started" for e in store.events(sid)), 2)
            finally:
                store.close()

    def test_recover_real_process_crashes_at_tool_boundaries(self):
        project = Path(__file__).resolve().parents[1]
        for stage in range(4):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / "repo"
                root.mkdir()
                db = Path(temp) / "state.sqlite3"
                process = subprocess.run([sys.executable, "-B", "-c", CRASH, str(root), str(db), str(stage)],
                                         cwd=project, capture_output=True, timeout=15)
                self.assertEqual(process.returncode, 19, process.stderr)
                store = Store(db)
                try:
                    sid = store.sessions()[0]["id"]
                    result = Agent(RecoveryModel(), root, store, Policy(True, True)).run("继续", session_id=sid)
                    store.repair_pending(sid)  # Idempotent after a subsequent recovery.
                    events = store.events(sid)
                    tool_messages = [e["data"] for e in events if e["kind"] == "message" and e["data"]["role"] == "tool"]
                    self.assertEqual(len(tool_messages), 1)
                    response = json.loads(tool_messages[0]["content"])
                    if stage == 0:
                        self.assertIn("尚未执行", response["error"])
                    elif stage < 3:
                        self.assertIn("不确定", response["error"])
                    else:
                        self.assertTrue(response["ok"])
                    self.assertEqual((root / "once.py").exists(), stage >= 2)
                    if stage >= 2:
                        self.assertEqual((root / "once.py").read_text(encoding="utf-8"), "once")
                    self.assertEqual(result.changed_files, ["once.py"] if stage >= 2 else [])
                    self.assertEqual(result.status, "unverified" if stage >= 2 else "completed")
                    self.assertEqual(len([e for e in events if e["kind"] == "tool_started"]), int(stage >= 1))
                finally:
                    store.close()


if __name__ == "__main__":
    unittest.main()
