import json
from pathlib import Path
import tempfile
import unittest

from codeharness.context import Context
from codeharness.demo import DemoModel, create_demo
from codeharness.models import ModelError
from codeharness.runtime import Agent, Limits
from codeharness.store import Store
from codeharness.tools import Policy, Registry, ToolError, Workspace, digest, register_workspace_tools


class ScriptModel:
    name = "script-test"

    def __init__(self, *steps):
        self.steps = iter(steps)
        self.requests = []

    def complete(self, messages, tools, max_tokens):
        self.requests.append({"messages": messages, "tools": tools, "max_tokens": max_tokens})
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
        with self.assertRaises(FileExistsError):
            self.registry.invoke("write_file", {"path": "a.py", "content": "changed"})
        self.assertEqual((self.root / "a.py").read_text(encoding="utf-8"), "original")


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

    def test_unverified_changes_cannot_be_reported_as_verified(self):
        model = ScriptModel(DemoModel.call("write_file", {"path": "a.py", "content": "pass"}),
                            DemoModel.text("全部验证通过"))
        result = self.agent(model).run("实现功能")
        self.assertEqual(result.status, "unverified")
        self.assertEqual(result.verification, "not_run")

    def test_failed_tests_are_authoritative_even_when_model_claims_success(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_failure.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n def test_fail(self): self.fail('broken')\n", encoding="utf-8")
        model = ScriptModel(DemoModel.call("write_file", {"path": "a.py", "content": "pass"}),
                            DemoModel.call("run_tests", {}), DemoModel.text("成功"))
        result = self.agent(model).run("实现功能")
        self.assertEqual((result.status, result.verification), ("unverified", "failed"))

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

    def test_actual_model_inputs_can_be_reconstructed(self):
        model = ScriptModel(DemoModel.call("list_files", {}), DemoModel.text("完成"))
        result = self.agent(model).run("列出文件")
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

    def test_skill_body_is_loaded_only_when_requested(self):
        directory = self.root / ".codeharness" / "skills" / "verify"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            "---\ndescription: 验证方法\n---\nUNIQUE_SKILL_BODY", encoding="utf-8")
        def first(messages, tools):
            self.assertNotIn("UNIQUE_SKILL_BODY", messages[0]["content"])
            self.assertIn("验证方法", messages[0]["content"])
            return DemoModel.call("load_skill", {"name": "verify"})
        def second(messages, tools):
            self.assertIn("UNIQUE_SKILL_BODY", messages[0]["content"])
            return DemoModel.text("完成")
        self.agent(ScriptModel(first, second)).run("检查仓库")

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
        users = [m["content"] for m in prepared if m["role"] == "user"]
        self.assertEqual(users, ["不要修改公共接口", "另外保留兼容性"])
        calls = {c["id"] for m in prepared for c in m.get("tool_calls", [])}
        results = {m["tool_call_id"] for m in prepared if m["role"] == "tool"}
        self.assertEqual(calls, results)
        self.assertLess(len(json.dumps(prepared)), len(json.dumps(messages)))


if __name__ == "__main__":
    unittest.main()
