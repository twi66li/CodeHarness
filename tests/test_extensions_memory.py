from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest

from codeharness.cli import run_chat
from codeharness.extensions import ExtensionHost
from codeharness.memory import LocalMemoryStore
from codeharness.models import Reply
from codeharness.runtime import Agent, Limits
from codeharness.store import Store
from codeharness.tools import Policy, ToolError


class SequenceModel:
    name = "seq-model"

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        self.seen.append(messages)
        return Reply(self.replies.pop(0), input_tokens=80, output_tokens=20)


class ExtensionAndMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        self.store = Store(self.workspace / ".codeharness" / "state.sqlite3")
        self.now = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
        self.memory = LocalMemoryStore(self.workspace / ".codeharness" / "memory", now_fn=lambda: self.now)

    def tearDown(self):
        self.memory.close()
        self.store.close()
        self.temp.cleanup()

    def test_extension_api_supports_new_setup_and_legacy_register_plugins(self):
        repo_root = Path(__file__).resolve().parents[1]
        legacy_plugin = repo_root / "examples" / "line_count.py"
        guard_plugin = repo_root / "examples" / "bash_guard.py"

        model = SequenceModel([
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "line_count", "arguments": '{"path":"app.py"}'}},
                {"id": "c2", "type": "function", "function": {"name": "bash", "arguments": '{"command":"rm -rf /tmp/demo"}'}}]},
            {"role": "assistant", "content": "已处理"},
        ])
        agent = Agent(model, self.workspace, self.store, Policy(allow_write=True, allow_exec=True),
                      plugins=[legacy_plugin, guard_plugin], enable_bash=True)
        try:
            result = agent.run("统计行数并测试拦截")
        finally:
            agent.close()

        self.assertEqual(result.status, "completed")
        events = [e["data"] for e in self.store.events(result.session_id) if e["kind"] == "tool_finished"]
        by_name = {row["name"]: row["result"] for row in events}
        self.assertTrue(by_name["line_count"]["ok"])
        self.assertEqual(by_name["line_count"]["output"]["lines"], 1)
        self.assertFalse(by_name["bash"]["ok"])
        self.assertIn("bash_guard 拦截", by_name["bash"]["error"])

    def test_discover_workspace_extension_with_custom_command_and_hook(self):
        ext_dir = self.workspace / ".codeharness" / "extensions"
        ext_dir.mkdir(parents=True)
        (ext_dir / "hello_ext.py").write_text(
            "def setup(api):\n"
            "    api.register_command('ping', '健康检查', lambda args, ctx: f'pong:{args}')\n"
            "    api.on('before_context', lambda ev: {'insert_at': len(ev['messages']), 'message': {'role': 'user', 'content': '[ext-tag]'}})\n",
            encoding="utf-8",
        )
        model = SequenceModel([{"role": "assistant", "content": "ok"}])
        self.assertNotIn("ping", Agent(model, self.workspace, self.store).commands())
        agent = Agent(model, self.workspace, self.store, Policy(allow_write=True, allow_exec=True),
                      discover_extensions=True)
        try:
            cmds = agent.commands()
            self.assertIn("ping", cmds)
            self.assertEqual(cmds["ping"].handler("v2", {}), "pong:v2")
            result = agent.run("你好")
            self.assertEqual(result.status, "completed")
            sent = model.seen[-1]
            self.assertTrue(any(m.get("content") == "[ext-tag]" for m in sent))
        finally:
            agent.close()

    def test_memory_l1_l2_l3_ttl_fts_and_markdown_editability(self):
        # L1 pins
        p1 = self.memory.pin("s1", "只使用 Python 标准库")
        self.assertEqual(len(self.memory.list_pins("s1")), 1)

        # L2 short-term with TTL and FTS5 search
        s1 = self.memory.save_short("修复订单折扣四舍五入精度问题", ttl_days=3, tags=("billing", "decimal"))
        s2 = self.memory.save_short("搭建本地日志追踪", ttl_days=10, tags=("trace",))
        hits = self.memory.search_short("折扣 精度")
        self.assertEqual([h["id"] for h in hits], [s1["id"]])

        # Advance time 5 days -> s1 expires, s2 survives
        self.now += timedelta(days=5)
        self.assertEqual([h["id"] for h in self.memory.list_short()], [s2["id"]])

        # L3 long-term Markdown + index + direct human edit
        l1 = self.memory.save_long("feedback", "禁止改公共接口", "未经确认不要改对外函数签名")
        index_text = (self.workspace / ".codeharness" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
        self.assertIn(l1["id"], index_text)
        md_file = self.workspace / ".codeharness" / "memory" / "feedback.md"
        md_file.write_text(md_file.read_text(encoding="utf-8").replace("对外函数签名", "公开 CLI 参数"), encoding="utf-8")
        long_hits = self.memory.search_long("公开 CLI")
        self.assertEqual(len(long_hits), 1)
        self.assertIn("公开 CLI 参数", long_hits[0]["content"])

        self.assertTrue(self.memory.unpin("s1", p1["id"]))
        self.assertTrue(self.memory.delete_long(l1["id"]))

    def test_memory_extension_preserves_system_prefix_and_survives_compact_and_autosaves_l2(self):
        self.memory.save_long("user", "语言偏好", "全部回复使用简洁中文")
        model = SequenceModel([
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "m1", "type": "function", "function": {"name": "memory_pin", "arguments": '{"content":"禁止删除 app.py"}'}}]},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "w1", "type": "function", "function": {"name": "write_file", "arguments": '{"path":"note.py","content":"X = 2\\n"}'}}]},
            {"role": "assistant", "content": "已记录置顶并创建 note.py"},
            {"role": "assistant", "content": "压缩后继续"},
        ])
        agent = Agent(model, self.workspace, self.store, Policy(allow_write=True, allow_exec=True),
                      enable_memory=True, memory_backend=self.memory)
        try:
            r1 = agent.run("帮我记下不能删 app.py，并新建 note.py")
            self.assertEqual(r1.status, "unverified")
            # System message must remain identical across requests (prefix cache safe)
            sys0 = model.seen[0][0]["content"]
            for req_msgs in model.seen:
                self.assertEqual(req_msgs[0]["content"], sys0)
            # L2 auto-saved summary at session_end because note.py was changed
            shorts = self.memory.list_short()
            self.assertTrue(any("note.py" in item["content"] for item in shorts))

            # Manual compact preserves L1 pin both in compact summary and in next request recall block
            info = agent.compact(r1.session_id)
            self.assertTrue(info["compacted"])
            r2 = agent.run("继续", session_id=r1.session_id)
            self.assertEqual(r2.status, "unverified")
            last_sent = model.seen[-1]
            self.assertEqual(last_sent[0]["content"], sys0)
            self.assertTrue(any("禁止删除 app.py" in m.get("content", "") for m in last_sent if m["role"] == "user"))
        finally:
            agent.close()

    def test_chat_slash_commands_for_memory_extension(self):
        model = SequenceModel([{"role": "assistant", "content": "收到"}])
        policy = Policy(allow_write=True, allow_exec=True)
        agent = Agent(model, self.workspace, self.store, policy, Limits(max_requests=10),
                      enable_bash=True, enable_memory=True, memory_backend=self.memory)
        inputs = iter([
            "/help",
            "第一句",
            "/pin 输出保持简洁",
            "/remember feedback 测试策略: 先跑最小测试",
            "/memory",
            "/exit",
        ])
        out = io.StringIO()
        try:
            code = run_chat(agent, self.workspace, self.store, policy, stream=False,
                            input_fn=lambda prompt="": next(inputs), output=out)
        finally:
            agent.close()
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("/memory", text)
        self.assertIn("已置顶 L1", text)
        self.assertIn("已写入 L3 长期记忆", text)
        self.assertIn("输出保持简洁", text)
        self.assertIn("测试策略", text)

    def test_model_cannot_mutate_memory_without_write_permission(self):
        from codeharness.context import Context
        agent = Agent(SequenceModel([]), self.workspace, self.store, Policy(),
                      enable_memory=True, memory_backend=self.memory)
        registry = agent._registry("session", Context(self.workspace), False, float("inf"))
        for name, args in (
            ("memory_pin", {"content": "pin"}),
            ("memory_save", {"scope": "long", "content": "change"}),
            ("memory_forget", {"scope": "long", "item_id": "missing"}),
        ):
            with self.assertRaisesRegex(ToolError, "权限被拒绝"):
                registry.invoke(name, args)


if __name__ == "__main__":
    unittest.main()
