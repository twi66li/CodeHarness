import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codeharness.cli import main, model_connection, parser, run_chat
from codeharness.memory import LocalMemoryStore
from codeharness.models import AnthropicModel, ModelError, Reply
from codeharness.runtime import Agent, Limits
from codeharness.store import Store
from codeharness.tools import Policy


class FakeResponse:
    def __init__(self, body: bytes | list[str]):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        assert isinstance(self._body, bytes)
        return self._body

    def __iter__(self):
        assert isinstance(self._body, list)
        return iter(line.encode("utf-8") for line in self._body)


class StubModel:
    def __init__(self, name: str, replies: list[dict]):
        self.name = name
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        self.seen.append(messages)
        return Reply(self.replies.pop(0), input_tokens=50, output_tokens=15)


class V3TreeAndAnthropicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "demo.py").write_text("X = 1\n", encoding="utf-8")
        self.store = Store(self.workspace / ".codeharness" / "state.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_anthropic_model_non_streaming_conversion_and_reply(self):
        model = AnthropicModel("claude-sonnet-4", "https://api.anthropic.com", "ak-secret")
        response_json = {
            "content": [
                {"type": "thinking", "thinking": "先检查文件"},
                {"type": "text", "text": "正在读取"},
                {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "demo.py"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 120, "output_tokens": 35, "cache_read_input_tokens": 60},
        }
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "看下 demo.py"},
            {"role": "assistant", "content": "好的", "tool_calls": [
                {"id": "c0", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"demo.py"}'}}]},
            {"role": "tool", "tool_call_id": "c0", "content": '{"ok":true}'},
            {"role": "user", "content": "再看一次"},
        ]
        tools = [{"type": "function", "function": {
            "name": "read_file", "description": "读文件", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]

        with patch("codeharness.models.urlopen", return_value=FakeResponse(json.dumps(response_json).encode("utf-8"))) as mock_open:
            reply = model.complete(messages, tools, 512)

        req = mock_open.call_args[0][0]
        self.assertTrue(req.full_url.endswith("/v1/messages"))
        self.assertEqual(req.headers["X-api-key"], "ak-secret")
        sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent["system"], "系统提示")
        self.assertEqual(sent["tools"][0]["input_schema"]["type"], "object")
        # Consecutive tool_result + user text should be grouped cleanly under user role
        self.assertEqual(sent["messages"][-1]["role"], "user")
        self.assertEqual(sent["messages"][-1]["content"][0]["type"], "tool_result")
        self.assertEqual(reply.message["reasoning_content"], "先检查文件")
        self.assertEqual(reply.message["content"], "正在读取")
        self.assertEqual(reply.message["tool_calls"][0]["id"], "tu_1")
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.cached_tokens), (180, 35, 60))

    def test_anthropic_model_sse_streaming_and_truncation(self):
        model = AnthropicModel("claude-sonnet-4", "https://proxy.example/v1", "ak-test")
        sse = [
            "event: message_start\n",
            'data: {"type":"message_start","message":{"usage":{"input_tokens":88,"cache_read_input_tokens":44}}}\n',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}\n',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"想清楚"}}\n',
            'data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}\n',
            'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"答复"}}\n',
            'data: {"type":"content_block_start","index":2,"content_block":{"type":"tool_use","id":"tu_9","name":"bash"}}\n',
            'data: {"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"{\\"command\\":"}}\n',
            'data: {"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"\\"echo ok\\"}"}}\n',
            'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":21}}\n',
            'data: {"type":"message_stop"}\n',
        ]
        deltas = []
        with patch("codeharness.models.urlopen", return_value=FakeResponse(sse)) as mock_open:
            reply = model.complete([{"role": "user", "content": "hi"}], [], 256,
                                   on_delta=lambda k, c: deltas.append((k, c)))
        self.assertTrue(mock_open.call_args[0][0].full_url.endswith("/v1/messages"))
        self.assertEqual(deltas, [("reasoning", "想清楚"), ("text", "答复")])
        self.assertEqual(reply.message["tool_calls"][0]["function"]["name"], "bash")
        self.assertEqual(json.loads(reply.message["tool_calls"][0]["function"]["arguments"]), {"command": "echo ok"})
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.cached_tokens), (132, 21, 44))

        for interrupted in (sse[:-1], sse[:-2] + ['data: {"type":"error","error":{"type":"overloaded_error"}}\n']):
            with patch("codeharness.models.urlopen", return_value=FakeResponse(interrupted)):
                with self.assertRaises(ModelError) as ctx:
                    model.complete([{"role": "user", "content": "hi"}], [], 256, on_delta=lambda *_: None)
                self.assertTrue(ctx.exception.retryable)

        trunc_sse = [
            'data: {"type":"message_start","message":{"usage":{"input_tokens":30}}}\n',
            'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"},"usage":{"output_tokens":16}}\n',
        ]
        with patch("codeharness.models.urlopen", return_value=FakeResponse(trunc_sse)):
            with self.assertRaises(ModelError) as ctx:
                model.complete([{"role": "user", "content": "hi"}], [], 16, on_delta=lambda k, c: None)
        self.assertTrue(ctx.exception.truncated)
        self.assertEqual(ctx.exception.usage, (30, 16))

    def test_store_fork_and_session_tree_branching(self):
        model = StubModel("m1", [
            {"role": "assistant", "content": "第1轮结论"},
            {"role": "assistant", "content": "第2轮走偏了"},
            {"role": "assistant", "content": "分叉后的新方案"},
        ])
        agent = Agent(model, self.workspace, self.store, Policy(allow_write=True, allow_exec=True))
        r1 = agent.run("需求A")
        r2 = agent.run("需求B（误操作）", session_id=r1.session_id)
        turns = self.store.turns(r2.session_id)
        self.assertEqual(len(turns), 2)

        # Fork from turn #1 (before the bad turn #2)
        branch_sid = self.store.fork(r2.session_id, up_to_event_id=turns[0]["event_id"], label="重试方案")
        r3 = agent.run("换个更好的方案", session_id=branch_sid)
        self.assertEqual(r3.status, "completed")

        # Verify forked branch never saw turn #2's bad messages
        branch_sent = model.seen[-1]
        self.assertFalse(any("需求B" in str(m.get("content", "")) for m in branch_sent))
        self.assertTrue(any("第1轮结论" in str(m.get("content", "")) for m in branch_sent))

        tree = self.store.session_tree(branch_sid)
        self.assertEqual(tree["root"], r1.session_id)
        self.assertEqual([b["id"] for b in tree["branches"]], [r1.session_id, branch_sid])
        self.assertEqual(tree["branches"][1]["label"], "重试方案")

    def test_fork_preserves_unresolved_write_evidence_and_limits_artifacts(self):
        sid = self.store.create(self.workspace, "m")
        self.store.append(sid, "message", {"role": "system", "content": "system"})
        first = self.store.events(sid)[-1]["id"]
        with self.assertRaisesRegex(ValueError, "早于工作区基线"):
            self.store.fork(sid, first)
        self.store.append(sid, "baseline", {"files": {}})
        self.store.append(sid, "message", {"role": "assistant", "content": "", "tool_calls": [
            {"id": "pending", "function": {"name": "write_file", "arguments": "{}"}}]})
        self.store.append(sid, "tool_started", {"call_id": "pending", "effect": "write"})
        cutoff = self.store.events(sid)[-1]["id"]
        self.store.artifact(sid, "out of branch")
        branch = self.store.fork(sid, cutoff)
        repaired = next(msg for msg in self.store.messages(branch) if msg["role"] == "tool")
        self.assertIn("副作用尚不确定", repaired["content"])
        artifacts = self.store.db.execute("SELECT content FROM artifacts WHERE root_id=?", (branch,)).fetchall()
        self.assertEqual(artifacts, [])

    def test_fork_before_first_request_copies_pins(self):
        model = StubModel("m", [{"role": "assistant", "content": "done"}])
        agent = Agent(model, self.workspace, self.store)
        sid = agent.run("first").session_id
        mem = LocalMemoryStore(self.workspace / ".codeharness" / "memory")
        try:
            mem.pin(sid, "keep this")
        finally:
            mem.close()
        agent = Agent(model, self.workspace, self.store, enable_memory=True)
        inputs = iter(["/fork", "/exit"])
        try:
            run_chat(agent, self.workspace, self.store, agent.policy, session_id=sid,
                     input_fn=lambda _: next(inputs), output=io.StringIO())
        finally:
            agent.close()
        branch = next(node["id"] for node in self.store.session_tree(sid)["branches"] if node["id"] != sid)
        mem = LocalMemoryStore(self.workspace / ".codeharness" / "memory")
        try:
            self.assertEqual([pin["content"] for pin in mem.list_pins(branch)], ["keep this"])
        finally:
            mem.close()

    def test_chat_tree_fork_switch_and_model_hot_swap(self):
        m1 = StubModel("fast-model", [
            {"role": "assistant", "content": "轮1完成"},
            {"role": "assistant", "content": "轮2完成"},
        ])
        m2 = StubModel("strong-model", [
            {"role": "assistant", "content": "强模型分叉完成"},
        ])
        policy = Policy(allow_write=True, allow_exec=True)
        agent = Agent(m1, self.workspace, self.store, policy, Limits(max_requests=20),
                      enable_bash=True, enable_memory=False)
        inputs = iter([
            "第一步",
            "第二步",
            "/tree",
            "/fork 1 新方向",
            "/model strong-model",
            "在分叉上继续",
            "/tree",
            "/exit",
        ])
        out = io.StringIO()
        code = run_chat(agent, self.workspace, self.store, policy, stream=False,
                        input_fn=lambda prompt="": next(inputs), output=out,
                        switch_model=lambda spec: m2 if spec == "strong-model" else m1)
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("已分叉并切换到新分支：", text)
        self.assertIn("已切换模型：fast-model → strong-model", text)
        self.assertIn("强模型分叉完成", text)
        self.assertIn("新方向", text)

    def test_cli_provider_flag(self):
        args = parser().parse_args(["chat", "--provider", "anthropic", "--model", "claude-sonnet-4"])
        self.assertEqual(args.provider, "anthropic")
        self.assertEqual(args.model, "claude-sonnet-4")

    def test_cli_switch_keeps_provider_address_and_key_paired(self):
        def check_switch(_agent, *_args, switch_model, **_kwargs):
            anthropic = switch_model("anthropic:first")
            same_provider = switch_model("next")
            self.assertEqual(same_provider.url, "https://anthropic.example/v1/messages")
            self.assertEqual(same_provider.api_key, "anthropic-key")
            self.assertIsInstance(anthropic, AnthropicModel)
            opened = switch_model("openai:back")
            self.assertEqual(opened.url, "https://openai.example/v1/chat/completions")
            self.assertEqual(opened.api_key, "openai-key")
            return 0

        env = {"ANTHROPIC_BASE_URL": "https://anthropic.example", "ANTHROPIC_API_KEY": "anthropic-key",
               "CODEHARNESS_API_KEY": "openai-key"}
        with patch.dict("codeharness.cli.os.environ", env, clear=True), patch("codeharness.cli.run_chat", check_switch):
            status = main(["chat", "--workspace", str(self.workspace), "--model", "initial",
                           "--base-url", "https://openai.example/v1"])
        self.assertEqual(status, 0)
        self.assertEqual(model_connection({"CODEHARNESS_API_KEY": "openai-key"}, None, "anthropic")[1], "")


if __name__ == "__main__":
    unittest.main()
