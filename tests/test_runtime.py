from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codeharness.cli import main as cli
from codeharness.context import Context
from codeharness.demo import DemoModel, create_demo
from codeharness.models import ModelError
from codeharness.runtime import Agent, Limits
from codeharness.store import Store
from codeharness.tools import Policy, Registry, Tool, ToolError, Workspace, digest, parameters, register_workspace_tools


class ScriptModel:
    name = "script-test"

    def __init__(self, *steps):
        self.steps = iter(steps)
        self.requests = []
        self.timeouts = []

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        self.requests.append({"messages": messages, "tools": tools, "max_tokens": max_tokens})
        self.timeouts.append(timeout)
        step = next(self.steps)
        return step(messages, tools) if callable(step) else step


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.workspace = Workspace(self.root)
        self.registry = Registry(self.workspace, Policy(allow_write=True, allow_exec=True))
        register_workspace_tools(self.registry)

    def tearDown(self):
        self.temp.cleanup()

    def test_cannot_read_outside_workspace(self):
        (self.root.parent / "secret.txt").write_text("private", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "超出"):
            self.registry.invoke("read_file", {"path": "../secret.txt"})

    def test_hidden_credentials_are_not_searchable(self):
        (self.root / ".env").write_text("SECRET=value", encoding="utf-8")
        self.assertEqual(self.registry.invoke("search", {"query": "SECRET"})["matches"], [])
        with self.assertRaisesRegex(ToolError, "保护"):
            self.workspace.path(".env")

    def test_symlink_cannot_escape_workspace(self):
        outside = self.root.parent / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            (self.root / "link.txt").symlink_to(outside)
        except OSError:
            self.skipTest("本机未授权创建符号链接")
        with self.assertRaises(ToolError):
            self.registry.invoke("read_file", {"path": "link.txt"})

    def test_stale_edit_rejected_without_touching_file(self):
        file = self.root / "a.py"
        file.write_text("old", encoding="utf-8")
        expected = self.registry.invoke("read_file", {"path": "a.py"})["sha256"]
        file.write_text("new external content", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "已变化"):
            self.registry.invoke("edit_file", {"path": "a.py", "old_text": "old", "new_text": "fixed",
                                                "expected_sha256": expected})
        self.assertEqual(file.read_text(encoding="utf-8"), "new external content")

    def test_denied_write_does_not_create_file(self):
        self.registry.policy = Policy()
        with self.assertRaisesRegex(ToolError, "权限被拒绝"):
            self.registry.invoke("write_file", {"path": "a.py", "content": "changed"})
        self.assertFalse((self.root / "a.py").exists())

    def test_readonly_policy_still_denies_registered_write(self):
        self.registry.policy = Policy(allow_write=True, allow_exec=True, readonly=True)
        with self.assertRaisesRegex(ToolError, "只读"):
            self.registry.invoke("write_file", {"path": "a.py", "content": "changed"})

    def test_hooks_can_block_and_observe(self):
        self.registry.before.append(lambda name, args: "blocked by hook" if name == "write_file" else None)
        with self.assertRaisesRegex(ToolError, "blocked by hook"):
            self.registry.invoke("write_file", {"path": "a.py", "content": "x"})
        observed = []
        self.registry.after.append(lambda name, args, result: observed.append(name))
        self.registry.invoke("list_files", {})
        self.assertEqual(observed, ["list_files"])

    def test_empty_test_suite_cannot_verify_task(self):
        (self.root / "tests").mkdir()
        result = self.registry.invoke("run_tests", {})
        self.assertFalse(result["passed"])

    def test_create_does_not_overwrite_existing_file(self):
        (self.root / "a.py").write_text("original", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "edit_file") as caught:
            self.registry.invoke("write_file", {"path": "a.py", "content": "changed"})
        self.assertNotIn(str(self.root), str(caught.exception))
        self.assertEqual((self.root / "a.py").read_text(encoding="utf-8"), "original")

    def test_write_and_edit_report_nonblocking_python_syntax_feedback(self):
        created = self.registry.invoke("write_file", {"path": "broken.py", "content": "def f(:\n    pass\n"})
        self.assertFalse(created["syntax_valid"])
        self.assertEqual(created["syntax_error"]["line"], 1)
        fixed = self.registry.invoke("edit_file", {
            "path": "broken.py", "old_text": "def f(:", "new_text": "def f():",
            "expected_sha256": created["sha256"],
        })
        self.assertTrue(fixed["syntax_valid"])

    def test_search_glob_supports_zero_depth_double_star(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("needle = 1\n", encoding="utf-8")
        (self.root / "src" / "sub").mkdir()
        (self.root / "src" / "sub" / "mod.py").write_text("needle = 2\n", encoding="utf-8")
        res = self.registry.invoke("search", {"query": "needle", "glob": "src/**/*.py"})
        self.assertEqual([m["path"] for m in res["matches"]], ["src/main.py", "src/sub/mod.py"])

    def test_edit_file_supports_crlf_and_bom_multiline(self):
        file = self.root / "win.py"
        original = "\ufeffdef f():\r\n    a = 1\r\n    return a\r\n".encode("utf-8")
        file.write_bytes(original)
        read = self.registry.invoke("read_file", {"path": "win.py"})
        self.registry.invoke("edit_file", {
            "path": "win.py",
            "old_text": "def f():\n    a = 1",
            "new_text": "def f():\n    a = 2",
            "expected_sha256": read["sha256"],
        })
        updated = file.read_bytes()
        self.assertTrue(updated.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"    a = 2\r\n", updated)
        self.assertNotIn(b"\n", updated.replace(b"\r\n", b""))

    def test_read_file_rejects_directory_and_missing_file(self):
        (self.root / "sub").mkdir()
        with self.assertRaisesRegex(ToolError, "不是文件"):
            self.registry.invoke("read_file", {"path": "sub"})
        with self.assertRaisesRegex(ToolError, "不存在"):
            self.registry.invoke("read_file", {"path": "missing.py"})

    def test_registry_validates_extended_json_schema_types(self):
        self.registry.register(Tool("ext", "扩展参数测试", parameters({
            "flag": {"type": "boolean"},
            "count": {"type": "integer"},
            "ratio": {"type": "number"},
            "items": {"type": "array"},
            "meta": {"type": "object"},
        }, ["flag", "count", "ratio", "items", "meta"]), lambda **kw: kw))
        out = self.registry.invoke("ext", {
            "flag": True, "count": 2, "ratio": 0.5, "items": ["a"], "meta": {"k": 1}})
        self.assertTrue(out["flag"])
        with self.assertRaisesRegex(ToolError, "count"):
            self.registry.invoke("ext", {
                "flag": True, "count": True, "ratio": 0.5, "items": [], "meta": {}})
        with self.assertRaisesRegex(ToolError, "ratio"):
            self.registry.invoke("ext", {
                "flag": True, "count": 1, "ratio": False, "items": [], "meta": {}})

    def test_snapshot_cache_tracks_write_and_delete(self):
        self.registry.invoke("write_file", {"path": "a.py", "content": "one"})
        first = self.workspace.snapshot()
        self.assertEqual(first["a.py"], digest(b"one"))
        self.registry.invoke("edit_file", {
            "path": "a.py", "old_text": "one", "new_text": "two", "expected_sha256": first["a.py"]})
        second = self.workspace.snapshot()
        self.assertEqual(second["a.py"], digest(b"two"))
        (self.root / "a.py").unlink()
        self.assertEqual(self.workspace.snapshot(), {})
        self.assertEqual(self.workspace._digest_cache, {})

    def test_search_glob_and_syntax_diagnostics(self):
        (self.root / "sub").mkdir()
        (self.root / "sub" / "a.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "a.py").write_text("value =\n", encoding="utf-8")
        (self.root / "a.txt").write_text("value", encoding="utf-8")
        matches = self.registry.invoke("search", {"query": "value", "glob": "**/*.py"})["matches"]
        self.assertEqual({m["path"] for m in matches}, {"a.py", "sub/a.py"})
        self.assertTrue(self.registry.invoke("check_syntax", {"path": "sub/a.py"})["valid"])
        invalid = self.registry.invoke("check_syntax", {"path": "a.py"})
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["line"], 1)

    def test_unittest_single_file(self):
        (self.root / "tests").mkdir()
        for name, value in (("test_ok.py", "True"), ("test_fail.py", "False")):
            (self.root / "tests" / name).write_text(
                f"import unittest\nclass T(unittest.TestCase):\n def test_value(self): self.assertTrue({value})\n",
                encoding="utf-8")
        selected = self.registry.invoke("run_tests", {"path": "tests/test_ok.py"})
        self.assertTrue(selected["passed"])
        self.assertFalse(self.registry.invoke("run_tests", {"path": "tests"})["passed"])

    def test_tests_use_remaining_deadline(self):
        (self.root / "tests").mkdir()
        registry = Registry(self.workspace, Policy(allow_exec=True))
        register_workspace_tools(registry, deadline=12.0)
        with patch("os.environ", {**os.environ, "DASHSCOPE_API_KEY": "FAKE_FIXTURE_KEY"}), \
                patch("codeharness.tools.time.monotonic", return_value=10.0), \
                patch("codeharness.tools.subprocess.Popen") as launch:
            process = launch.return_value
            process.returncode = 0
            process.communicate.return_value = (b"Ran 1 test\nOK\n", None)
            self.assertTrue(registry.invoke("run_tests", {})["passed"])
            process.communicate.assert_called_once_with(timeout=2.0)
            self.assertNotIn("DASHSCOPE_API_KEY", launch.call_args.kwargs["env"])

    def test_git_tools_are_unavailable_in_plain_directories(self):
        self.assertTrue({"git_status", "git_diff"}.isdisjoint(self.registry.tools))

    def test_git_evidence_is_read_only_and_excludes_protected_paths(self):
        (self.root / "a.py").write_text("before = 1\n", encoding="utf-8")
        (self.root / ".env").write_text("FIXTURE_ONLY=before\n", encoding="utf-8")
        commands = [["git", "init", "-q"], ["git", "add", "-f", "a.py", ".env"],
                    ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                     "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]]
        for command in commands:
            subprocess.run(command, cwd=self.root, check=True, capture_output=True)
        (self.root / "a.py").write_text("after = 2\n", encoding="utf-8")
        (self.root / ".env").write_text("FIXTURE_ONLY=after\n", encoding="utf-8")
        (self.root / "new.py").write_text("pass\n", encoding="utf-8")
        registry = Registry(self.workspace, Policy(readonly=True))
        register_workspace_tools(registry)
        status = registry.invoke("git_status", {})
        self.assertEqual({e["path"] for e in status["entries"]}, {"a.py", "new.py"})
        diff = registry.invoke("git_diff", {})
        self.assertEqual(diff["files"], ["a.py"])
        self.assertIn("after = 2", diff["diff"])
        self.assertNotIn("FIXTURE_ONLY", diff["diff"])
        self.assertEqual((self.root / "a.py").read_text(encoding="utf-8"), "after = 2\n")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.store_path = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.store_path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def agent(self, model, **kwargs):
        return Agent(model, self.root, self.store, Policy(allow_write=True, allow_exec=True), **kwargs)

    def test_demo_executes_real_patch_and_real_tests(self):
        workspace = self.root / "demo"
        create_demo(workspace)
        result = Agent(DemoModel(), workspace, self.store, Policy(True, True)).run("修复折扣")
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.changed_files, ["basket.py"])
        self.assertIn("* (1 - discount)", (workspace / "basket.py").read_text(encoding="utf-8"))
        self.assertEqual(result.usage["requests"], 8)
        children = [s for s in self.store.sessions() if s["parent_id"] == result.session_id]
        self.assertEqual(len(children), 1)
        checks = [e["data"]["passed"] for e in self.store.events(result.session_id) if e["kind"] == "verification"]
        self.assertEqual(checks, [False, True])

    def test_demo_without_delegate_has_same_result_with_no_child(self):
        workspace = self.root / "demo"
        create_demo(workspace)
        result = Agent(DemoModel(), workspace, self.store, Policy(True, True), enable_delegate=False).run("修复折扣")
        self.assertEqual((result.status, result.changed_files), ("verified", ["basket.py"]))
        self.assertEqual(result.usage["requests"], 5)
        self.assertEqual(len(self.store.sessions()), 1)

    def test_unverified_changes_cannot_be_reported_as_verified(self):
        model = ScriptModel(DemoModel.call("write_file", {"path": "a.py", "content": "pass"}),
                            DemoModel.text("全部验证通过"))
        result = self.agent(model).run("实现功能")
        self.assertEqual(result.status, "unverified")
        self.assertEqual(result.verification, "not_run")

    def test_truncation_discards_reply_and_retries_with_more_output_budget(self):
        def truncate(messages, tools):
            raise ModelError("truncated reply", truncated=True, usage=(120, 40))

        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n", encoding="utf-8")
        model = ScriptModel(truncate, DemoModel.call("write_file", {"path": "a.py", "content": "pass"}),
                            DemoModel.call("run_tests", {}), DemoModel.text("完成"))
        result = self.agent(model, limits=Limits(max_requests=4, model_attempts=1)).run("实现功能")
        self.assertEqual((result.status, result.usage["requests"]), ("verified", 4))
        self.assertEqual([r["max_tokens"] for r in model.requests], [2048, 4096, 2048, 2048])
        self.assertIn("截断", model.requests[1]["messages"][-1]["content"])
        events = self.store.events(result.session_id)
        truncated = [e["data"] for e in events if e["kind"] == "model_truncated"]
        first_usage = next(e["data"] for e in events if e["kind"] == "usage")
        self.assertEqual(truncated, [{"attempt": 1, "max_tokens": 2048}])
        self.assertEqual((first_usage["input_tokens"], first_usage["output_tokens"], first_usage["estimated"]),
                         (120, 40, False))

    def test_repeated_truncation_stops_and_records_each_usage_once(self):
        def truncate(messages, tools):
            raise ModelError("truncated reply", truncated=True, usage=(10, 5))

        model = ScriptModel(truncate, truncate, truncate)
        result = self.agent(model).run("实现功能")
        self.assertEqual((result.status, result.answer), ("error", "模型输出连续被截断"))
        self.assertEqual((result.usage["requests"], result.usage["input_tokens"], result.usage["output_tokens"]),
                         (3, 30, 15))

    def test_legacy_events_can_be_listed_traced_and_resumed_through_truncation(self):
        sid = self.store.create(self.root, "legacy-model")
        self.store.append(sid, "baseline", {"files": {}})
        self.store.append(sid, "message", {"role": "system", "content": "legacy system"})
        self.store.append(sid, "skill_loaded", {"name": "old", "instructions": "legacy skill body"})
        self.store.append(sid, "model_request", {"model": "legacy-model", "messages": [], "tools": [], "max_tokens": 64})
        self.store.append(sid, "usage", {"input_tokens": 12, "output_tokens": 2})
        self.store.status(sid, "error")
        common = ["--store", str(self.store_path), "--json"]
        with redirect_stdout(StringIO()) as sessions:
            self.assertEqual(cli(["sessions", *common]), 0)
        self.assertEqual(json.loads(sessions.getvalue())[0]["id"], sid)
        with redirect_stdout(StringIO()) as trace:
            self.assertEqual(cli(["trace", sid, *common]), 0)
        self.assertTrue(any(e["kind"] == "model_request" for e in json.loads(trace.getvalue())))

        def truncate(messages, tools):
            self.assertIn("legacy skill body", messages[0]["content"])
            raise ModelError("truncated reply", truncated=True, usage=(20, 10))

        model = ScriptModel(truncate, DemoModel.text("已恢复"))
        with patch("codeharness.cli.ChatModel", return_value=model), redirect_stdout(StringIO()) as resumed:
            self.assertEqual(cli(["resume", sid, *common, "--base-url", "https://fixture.invalid/v1"]), 0)
        result = json.loads(resumed.getvalue())
        self.assertEqual((result["session_id"], result["status"], result["usage"]["requests"]), (sid, "completed", 3))
        self.assertEqual(result["usage"]["cached_tokens"], 0)

    def test_consecutive_identical_reads_warn_then_stall(self):
        (self.root / "a.py").write_text("x = 1", encoding="utf-8")
        model = ScriptModel(*(DemoModel.call("read_file", {"path": "a.py"}) for _ in range(5)))
        result = self.agent(model).run("调查文件")
        self.assertEqual((result.status, result.usage["requests"]), ("stalled", 5))
        self.assertIn("重复相同操作 3 次", model.requests[3]["messages"][-1]["content"])
        warnings = [e for e in self.store.events(result.session_id) if e["kind"] == "tool_stall_warning"]
        self.assertEqual(len(warnings), 1)

    def test_stall_counter_continues_on_resume_without_duplicate_warning(self):
        (self.root / "a.py").write_text("x = 1", encoding="utf-8")
        first = ScriptModel(*(DemoModel.call("read_file", {"path": "a.py"}) for _ in range(3)))
        initial = self.agent(first, limits=Limits(max_requests=3)).run("调查文件")
        again = ScriptModel(*(DemoModel.call("read_file", {"path": "a.py"}) for _ in range(2)))
        resumed = self.agent(again).run("继续调查", session_id=initial.session_id)
        self.assertEqual((resumed.status, resumed.usage["requests"]), ("stalled", 5))
        warnings = [e for e in self.store.events(initial.session_id) if e["kind"] == "tool_stall_warning"]
        self.assertEqual(len(warnings), 1)

    def test_stall_warning_for_identical_errors_from_different_tools(self):
        model = ScriptModel(
            DemoModel.call("read_file", {"path": "../private.py"}),
            DemoModel.call("list_files", {"path": "../private.py"}),
            DemoModel.call("read_file", {"path": "../private.py"}),
            DemoModel.call("list_files", {"path": "../private.py"}),
            DemoModel.text("已定位原因"),
        )
        result = self.agent(model).run("调查文件")
        self.assertEqual(result.status, "completed")
        self.assertIn("连续 4 次返回相同错误", model.requests[4]["messages"][-1]["content"])

    def test_changed_file_and_intervening_edits_reset_stall_detection(self):
        path = self.root / "a.py"
        path.write_text("x = 1", encoding="utf-8")

        def edit(messages, tools):
            previous = json.loads(messages[-1]["content"])["output"]
            return DemoModel.call("edit_file", {"path": "a.py", "old_text": "x = 1", "new_text": "x = 2",
                                                "expected_sha256": previous["sha256"]})

        reads = [DemoModel.call("read_file", {"path": "a.py"}) for _ in range(4)]
        model = ScriptModel(*reads[:2], edit, *reads[2:], DemoModel.text("完成"))
        result = self.agent(model).run("修改文件")
        self.assertEqual(result.status, "unverified")
        self.assertEqual(path.read_text(encoding="utf-8"), "x = 2")
        self.assertFalse(any(e["kind"] == "tool_stall_warning" for e in self.store.events(result.session_id)))

    def test_failed_tests_are_authoritative_even_when_model_claims_success(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_failure.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n def test_fail(self): self.fail('broken')\n", encoding="utf-8")
        model = ScriptModel(DemoModel.call("write_file", {"path": "a.py", "content": "pass"}),
                            DemoModel.call("run_tests", {}), DemoModel.text("成功"))
        result = self.agent(model).run("实现功能")
        self.assertEqual((result.status, result.verification), ("unverified", "failed"))

    def test_verification_checks_current_content_even_if_metadata_is_unchanged(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n",
            encoding="utf-8")
        file = self.root / "a.py"

        def finish(messages, tools):
            stat = file.stat()
            file.write_bytes(b"x = 2\n")
            os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            return DemoModel.text("完成")

        model = ScriptModel(DemoModel.call("write_file", {"path": "a.py", "content": "x = 1\n"}),
                            DemoModel.call("run_tests", {}), finish)
        result = self.agent(model).run("实现功能")
        self.assertEqual((result.status, result.verification), ("unverified", "stale"))

    def test_budget_is_shared_with_readonly_child(self):
        model = ScriptModel(DemoModel.call("delegate", {"task": "列出文件"}),
                            DemoModel.call("list_files", {}), DemoModel.text("没有文件"))
        result = self.agent(model, limits=Limits(max_requests=3)).run("检查仓库")
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(len(model.requests), 3)
        self.assertEqual(result.usage["requests"], 3)

    def test_child_has_no_write_execute_or_recursive_delegate_tools(self):
        def inspect(messages, tools):
            names = {tool["function"]["name"] for tool in tools}
            self.assertFalse({"write_file", "edit_file", "run_tests", "delegate"} & names)
            return DemoModel.call("write_file", {"path": "illegal.py", "content": "x"})
        model = ScriptModel(DemoModel.call("delegate", {"task": "尝试写入"}), inspect,
                            DemoModel.text("权限已阻止"), DemoModel.text("结束"))
        result = self.agent(model).run("检查权限")
        self.assertEqual(result.status, "completed")
        self.assertFalse((self.root / "illegal.py").exists())
        children = [s for s in self.store.sessions() if s["parent_id"] == result.session_id]
        self.assertEqual([s["status"] for s in children], ["completed"])

    def test_actual_model_inputs_can_be_reconstructed(self):
        model = ScriptModel(DemoModel.call("list_files", {}), DemoModel.text("完成"))
        result = self.agent(model).run("列出文件")
        self.assertEqual(result.status, "completed")
        requests = [e["data"] for e in self.store.events(result.session_id) if e["kind"] == "model_request"]
        self.assertEqual(len(requests), len(model.requests))
        for sent, saved in zip(model.requests, requests):
            self.assertEqual(sent, {k: saved[k] for k in ("messages", "tools", "max_tokens")})

    def test_resume_does_not_replay_uncertain_write(self):
        sid = self.store.create(self.root, "script-test")
        self.store.append(sid, "baseline", {"files": {}})
        self.store.append(sid, "checkpoint", {"files": {}})
        self.store.append(sid, "message", {"role": "system", "content": Context(self.root).system()})
        self.store.append(sid, "message", {"role": "user", "content": "创建文件一次"})
        call = DemoModel.call("write_file", {"path": "once.py", "content": "once"}).message
        self.store.append(sid, "message", call)
        self.store.append(sid, "tool_started", {"call_id": call["tool_calls"][0]["id"], "name": "write_file"})
        (self.root / "once.py").write_text("once", encoding="utf-8")
        self.store.close()
        self.store = Store(self.store_path)

        def check_recovery(messages, tools):
            self.assertTrue(any(m["role"] == "tool" and "不确定" in m["content"] for m in messages))
            self.assertTrue(any(m["role"] == "user" and "once.py" in m["content"] for m in messages))
            return DemoModel.text("检查后保留已有文件")
        result = self.agent(ScriptModel(check_recovery)).run("继续", session_id=sid)
        self.assertEqual(result.status, "unverified")
        self.assertEqual((self.root / "once.py").read_text(encoding="utf-8"), "once")
        self.assertEqual(result.changed_files, ["once.py"])

    def test_recorded_tool_result_repaired_without_running_tool_again(self):
        sid = self.store.create(self.root, "script-test")
        call = DemoModel.call("write_file", {"path": "never.py", "content": "never"}).message
        self.store.append(sid, "message", call)
        cid = call["tool_calls"][0]["id"]
        result = {"ok": True, "output": {"path": "already.py"}}
        self.store.append(sid, "tool_finished", {"call_id": cid, "result": result})
        self.store.repair_pending(sid)
        self.store.repair_pending(sid)
        tools = [m for m in self.store.messages(sid) if m["role"] == "tool"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(json.loads(tools[0]["content"]), result)
        self.assertFalse((self.root / "never.py").exists())

    def test_model_failure_is_persisted_and_resumable(self):
        def fail(messages, tools):
            raise ModelError("test transport failed")
        result = self.agent(ScriptModel(fail)).run("检查仓库")
        self.assertEqual(result.status, "error")
        resumed = self.agent(ScriptModel(DemoModel.text("已恢复"))).run("继续", session_id=result.session_id)
        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.usage["requests"], 2)

    def test_model_retry_counts_attempts_and_unknown_usage(self):
        def transient(messages, tools):
            raise ModelError("HTTP 429", retryable=True, retry_after=0)
        model = ScriptModel(transient, DemoModel.text("恢复"))
        with patch("codeharness.runtime.time.sleep") as sleep:
            result = self.agent(model, limits=Limits(max_seconds=5)).run("检查")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.usage["requests"], 2)
        self.assertTrue(result.usage["estimated"])
        self.assertTrue(all(0 < value <= 5 for value in model.timeouts))
        sleep.assert_called_once_with(0)
        events = self.store.events(result.session_id)
        self.assertEqual(len([e for e in events if e["kind"] == "model_retry"]), 1)
        self.assertEqual(len([e for e in events if e["kind"] == "usage" and e["data"].get("failed_attempt")]), 1)

    def test_retry_never_exceeds_request_budget(self):
        def transient(messages, tools):
            raise ModelError("HTTP 503", retryable=True, retry_after=0)
        model = ScriptModel(transient, DemoModel.text("不应发送"))
        with patch("codeharness.runtime.time.sleep") as sleep:
            result = self.agent(model, limits=Limits(max_requests=1)).run("检查")
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(result.usage["requests"], 1)
        sleep.assert_not_called()

    def test_rate_limit_retry_does_not_burn_output_token_budget(self):
        def limited(messages, tools):
            raise ModelError("HTTP 429", retryable=True, retry_after=0, consume_output_budget=False)
        model = ScriptModel(limited, limited, DemoModel.text("恢复成功"))
        with patch("codeharness.runtime.time.sleep"):
            result = self.agent(model, limits=Limits(max_requests=4, max_tokens=2000, output_tokens=1500)).run("检查")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.usage["requests"], 3)
        self.assertEqual(result.usage["output_tokens"], 30)

    def test_retry_never_exceeds_estimated_token_budget(self):
        def transient(messages, tools):
            raise ModelError("HTTP 503", retryable=True, retry_after=0)
        model = ScriptModel(transient, DemoModel.text("不应发送"))
        limits = Limits(output_tokens=256)
        agent = self.agent(model, limits=limits)
        context = Context(self.root, limits.context_chars)
        messages = [{"role": "system", "content": context.system()}, {"role": "user", "content": "检查"}]
        schemas = agent._registry("unused", context, False, 0).schemas()
        limits.max_tokens = len(json.dumps([messages, schemas], ensure_ascii=False)) // 3 + 1 + 256
        with patch("codeharness.runtime.time.sleep") as sleep:
            result = agent.run("检查")
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(result.usage["requests"], 1)
        self.assertEqual(result.usage["input_tokens"] + result.usage["output_tokens"], limits.max_tokens)
        sleep.assert_not_called()

    def test_retry_does_not_wait_past_deadline(self):
        def transient(messages, tools):
            raise ModelError("HTTP 429", retryable=True, retry_after=60)
        with patch("codeharness.runtime.time.sleep") as sleep:
            result = self.agent(ScriptModel(transient), limits=Limits(max_seconds=5)).run("检查")
        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.usage["requests"], 1)
        sleep.assert_not_called()

    def test_retry_attempt_limit(self):
        def transient(messages, tools):
            raise ModelError("HTTP 502", retryable=True, retry_after=0)
        with patch("codeharness.runtime.time.sleep") as sleep:
            result = self.agent(ScriptModel(transient, transient), limits=Limits(model_attempts=2)).run("检查")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.usage["requests"], 2)
        sleep.assert_called_once()

    def test_access_denied_in_child_stops_root_tool_batch(self):
        delegated = DemoModel.call("delegate", {"task": "检查项目"})
        delegated.message["tool_calls"] += DemoModel.call("write_file", {"path": "later.py", "content": "pass"}).message["tool_calls"]

        def denied(messages, tools):
            raise ModelError("HTTP 401", access_denied=True)

        model = ScriptModel(delegated, denied, DemoModel.text("不应发送"))
        result = self.agent(model).run("检查项目")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.usage["requests"], 2)
        self.assertFalse((self.root / "later.py").exists())

    def test_failed_test_invocation_invalidates_previous_verification(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_ok.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n", encoding="utf-8")
        model = ScriptModel(DemoModel.call("write_file", {"path": "a.py", "content": "pass\n"}),
                            DemoModel.call("run_tests", {}), DemoModel.call("run_tests", {"path": "missing"}),
                            DemoModel.text("完成"))
        result = self.agent(model).run("实现功能")
        self.assertEqual((result.status, result.verification), ("unverified", "failed"))

    def test_skill_body_is_loaded_only_when_requested(self):
        directory = self.root / ".codeharness" / "skills" / "verify"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_bytes(
            "\ufeff---\ndescription: 验证方法\n---\nUNIQUE_SKILL_BODY".encode("utf-8"))
        systems = []

        def first(messages, tools):
            self.assertNotIn("UNIQUE_SKILL_BODY", messages[0]["content"])
            self.assertIn("验证方法", messages[0]["content"])
            systems.append(messages[0])
            reply = DemoModel.call("load_skill", {"name": "verify"})
            reply.message["tool_calls"].extend(DemoModel.call("list_files", {}).message["tool_calls"])
            return reply
        def second(messages, tools):
            self.assertEqual(messages[0], systems[0])
            self.assertEqual([message["role"] for message in messages[-3:]], ["tool", "tool", "user"])
            self.assertNotIn("UNIQUE_SKILL_BODY", messages[-3]["content"])
            self.assertIn("UNIQUE_SKILL_BODY", messages[-1]["content"])
            return DemoModel.text("完成")
        result = self.agent(ScriptModel(first, second)).run("检查仓库")
        self.assertEqual(result.status, "completed", result.answer)

    def test_readonly_tools_do_not_write_intermediate_checkpoints(self):
        (self.root / "a.py").write_text("x = 1\n", encoding="utf-8")
        model = ScriptModel(DemoModel.call("list_files", {}),
                            DemoModel.call("read_file", {"path": "a.py"}),
                            DemoModel.text("完成"))
        result = self.agent(model).run("只读检查")
        checkpoints = [e for e in self.store.events(result.session_id) if e["kind"] == "checkpoint"]
        self.assertEqual(len(checkpoints), 1)

    def test_repair_pending_distinguishes_unstarted_and_interrupted_calls(self):
        sid = self.store.create(self.root, "script-test")
        c1 = DemoModel.call("write_file", {"path": "a.py", "content": "1"}).message["tool_calls"][0]
        c2 = DemoModel.call("write_file", {"path": "b.py", "content": "2"}).message["tool_calls"][0]
        self.store.append(sid, "message", {"role": "assistant", "content": "", "tool_calls": [c1, c2]})
        self.store.append(sid, "tool_started", {"call_id": c1["id"], "name": "write_file"})
        self.store.repair_pending(sid)
        tools = {m["tool_call_id"]: json.loads(m["content"]) for m in self.store.messages(sid) if m["role"] == "tool"}
        self.assertIn("不确定", tools[c1["id"]]["error"])
        self.assertIn("尚未执行", tools[c2["id"]]["error"])
        reconciled = {e["data"]["call_id"]: e["data"] for e in self.store.events(sid) if e["kind"] == "tool_reconciled"}
        self.assertTrue(reconciled[c1["id"]]["started"])
        self.assertFalse(reconciled[c2["id"]]["started"])

    def test_resume_without_checkpoint_falls_back_to_baseline(self):
        sid = self.store.create(self.root, "script-test")
        self.store.append(sid, "baseline", {"files": {}})
        self.store.append(sid, "message", {"role": "system", "content": Context(self.root).system()})
        self.store.append(sid, "message", {"role": "user", "content": "检查"})
        (self.root / "external.py").write_text("added", encoding="utf-8")
        def check(messages, tools):
            self.assertTrue(any(m["role"] == "user" and "external.py" in m["content"] for m in messages))
            return DemoModel.text("已感知外部改动")
        result = self.agent(ScriptModel(check)).run("继续", session_id=sid)
        self.assertEqual(result.status, "unverified")
        self.assertEqual(result.changed_files, ["external.py"])

    def test_low_remaining_token_budget_stops_as_budget_exhausted(self):
        model = ScriptModel(DemoModel.text("不应调用"))
        result = self.agent(model, limits=Limits(max_tokens=300, output_tokens=2048)).run("检查")
        self.assertEqual(result.status, "budget_exhausted")
        self.assertEqual(len(model.requests), 0)

    def test_timeout_inside_tool_loop_reports_timeout_status(self):
        c1 = DemoModel.call("list_files", {}).message["tool_calls"][0]
        c2 = DemoModel.call("list_files", {}).message["tool_calls"][0]
        batch = DemoModel.text("")
        batch.message = {"role": "assistant", "content": "", "tool_calls": [c1, c2]}
        clock = [0.0]
        def observe(kind, data):
            if kind == "tool":
                clock[0] = 11.0
        with patch("codeharness.runtime.time.monotonic", side_effect=lambda: clock[0]):
            result = self.agent(ScriptModel(batch), limits=Limits(max_seconds=10), observe=observe).run("批量读取")
        self.assertEqual(result.status, "timeout")
        started = [e["data"]["call_id"] for e in self.store.events(result.session_id) if e["kind"] == "tool_started"]
        self.assertEqual(started, [c1["id"]])

    def test_plugin_unexpected_error_does_not_leave_session_running(self):
        bad_runtime = Path(self.temp.name) / "boom_plugin.py"
        bad_runtime.write_text(
            "from codeharness.tools import Tool, parameters\n"
            "def register(r):\n"
            "    r.register(Tool('boom', 'boom', parameters({}), lambda: (_ for _ in ()).throw(RuntimeError('kapow'))))\n",
            encoding="utf-8",
        )
        def after_boom(messages, tools):
            payload = json.loads(messages[-1]["content"])
            self.assertFalse(payload["ok"])
            self.assertIn("RuntimeError: kapow", payload["error"])
            return DemoModel.text("已处理插件异常")
        result = self.agent(ScriptModel(DemoModel.call("boom", {}), after_boom), plugins=[bad_runtime]).run("调用插件")
        self.assertEqual(result.status, "completed")

        bad_load = Path(self.temp.name) / "broken_load.py"
        bad_load.write_text("def not_register(): pass\n", encoding="utf-8")
        failed = self.agent(ScriptModel(), plugins=[bad_load]).run("加载坏插件")
        self.assertEqual(failed.status, "error")
        self.assertEqual(self.store.session(failed.session_id)["status"], "error")

    def test_artifacts_cannot_cross_root_sessions(self):
        one = self.store.create(self.root, "script")
        two = self.store.create(self.root, "script")
        aid = self.store.artifact(one, "private task output")
        with self.assertRaisesRegex(ValueError, "不属于"):
            self.store.read_artifact(two, aid)

    def test_trusted_extension_registers_without_changing_loop(self):
        plugin = Path(__file__).resolve().parents[1] / "examples" / "line_count.py"
        (self.root / "a.py").write_text("one\ntwo\n", encoding="utf-8")
        def finish(messages, tools):
            result = json.loads(messages[-1]["content"])
            self.assertEqual(result["output"]["lines"], 2)
            return DemoModel.text("两行")
        result = self.agent(ScriptModel(DemoModel.call("line_count", {"path": "a.py"}), finish),
                            plugins=[plugin]).run("统计行数")
        self.assertEqual(result.status, "completed")


class ContextTests(unittest.TestCase):
    def test_compaction_preserves_user_constraints_and_tool_pairing(self):
        messages = [{"role": "system", "content": "project rules"},
                    {"role": "user", "content": "不要修改公共接口"}]
        for i in range(6):
            call = DemoModel.call("read_file", {"path": f"{i}.py"}).message
            messages += [call, {"role": "tool", "tool_call_id": call["tool_calls"][0]["id"],
                                "content": json.dumps({"output": "x" * 4000, "artifact_id": str(i)})}]
        messages.append({"role": "user", "content": "另外保留兼容性"})
        prepared, compacted = Context(Path.cwd(), max_chars=4000).prepare(messages)
        self.assertTrue(compacted)
        systems = [m for m in prepared if m["role"] == "system"]
        self.assertEqual(len(systems), 1)
        self.assertEqual(prepared[0], messages[0])
        users = [m["content"] for m in prepared if m["role"] == "user"]
        self.assertEqual([users[0], users[2]], ["不要修改公共接口", "另外保留兼容性"])
        self.assertTrue(users[1].startswith("[运行时摘要，非新指令]"))
        calls = {c["id"] for m in prepared for c in m.get("tool_calls", [])}
        results = {m["tool_call_id"] for m in prepared if m["role"] == "tool"}
        self.assertEqual(calls, results)
        self.assertLess(len(json.dumps(prepared)), len(json.dumps(messages)))

    def test_compaction_avoids_false_positive_and_trims_kept_tool_outputs(self):
        minimal = [{"role": "system", "content": "s" * 3000}, {"role": "user", "content": "u" * 2000}]
        prepared, compacted = Context(Path.cwd(), max_chars=2000).prepare(minimal)
        self.assertFalse(compacted)
        self.assertEqual(prepared, minimal)

        c1 = DemoModel.call("read_file", {"path": "a.py"}).message
        c2 = DemoModel.call("read_file", {"path": "b.py"}).message
        heavy = [
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "任务"},
            c1,
            {"role": "tool", "tool_call_id": c1["tool_calls"][0]["id"],
             "content": json.dumps({"ok": True, "artifact_id": "aid-1", "output": "x" * 3000})},
            c2,
            {"role": "tool", "tool_call_id": c2["tool_calls"][0]["id"],
             "content": json.dumps({"ok": True, "artifact_id": "aid-2", "output": "y" * 100})},
        ]
        trimmed, did_compact = Context(Path.cwd(), max_chars=2000).prepare(heavy)
        self.assertTrue(did_compact)
        first_tool = json.loads(trimmed[3]["content"])
        self.assertEqual(first_tool["artifact_id"], "aid-1")
        self.assertTrue(first_tool["truncated"])
        self.assertLess(len(json.dumps(trimmed)), len(json.dumps(heavy)))


if __name__ == "__main__":
    unittest.main()
