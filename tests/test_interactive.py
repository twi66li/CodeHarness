import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from codeharness.cli import parser, run_chat
from codeharness.context import Context
from codeharness.models import ChatModel, ModelError, Reply
from codeharness.runtime import Agent, Limits
from codeharness.store import Store
from codeharness.tools import Policy, Registry, ToolError, Workspace, register_workspace_tools


class FakeStreamResponse:
    def __init__(self, lines: list[str]):
        self._raw = [line.encode("utf-8") for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._raw)


class StreamingStubModel:
    name = "stub-stream"
    supports_stream = True

    def __init__(self, steps):
        self.steps = list(steps)
        self.seen_messages = []

    def complete(self, messages, tools, max_tokens, *, timeout=None, on_delta=None):
        self.seen_messages.append(messages)
        step = self.steps.pop(0)
        if on_delta is not None:
            for kind, chunk in step.get("deltas", []):
                on_delta(kind, chunk)
        return Reply(step["message"], input_tokens=100, output_tokens=20)


class InteractiveV1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        (self.workspace / "hello.txt").write_text("hello world\n", encoding="utf-8")
        self.store = Store(self.workspace / ".codeharness" / "state.sqlite3")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_bash_tool_default_off_and_executes_when_enabled(self):
        ws = Workspace(self.workspace)
        reg_default = Registry(ws, Policy(allow_exec=True))
        register_workspace_tools(reg_default)
        self.assertNotIn("bash", reg_default.tools)

        reg_bash = Registry(ws, Policy(allow_exec=True))
        register_workspace_tools(reg_bash, enable_bash=True)
        self.assertIn("bash", reg_bash.tools)
        out = reg_bash.invoke("bash", {"command": 'python -c "print(12345)"'})
        self.assertEqual(out["exit_code"], 0)
        self.assertIn("12345", out["output"])

        with self.assertRaises(ToolError):
            reg_bash.invoke("bash", {"command": "   "})

        reg_denied = Registry(ws, Policy(allow_exec=False))
        register_workspace_tools(reg_denied, enable_bash=True)
        with self.assertRaises(ToolError):
            reg_denied.invoke("bash", {"command": "echo hi"})

    def test_pi_tool_profile_and_readonly_isolation(self):
        ws = Workspace(self.workspace)
        reg = Registry(ws, Policy(allow_write=True, allow_exec=True))
        register_workspace_tools(reg, enable_bash=True, tool_profile="pi")
        self.assertEqual(set(reg.tools), {"read_file", "write_file", "edit_file", "bash"})

        model = StreamingStubModel([])
        agent = Agent(model, self.workspace, self.store, Policy(allow_write=True, allow_exec=True),
                      enable_bash=True, tool_profile="pi")
        self.assertEqual(set(agent.tool_names()), {"read_file", "write_file", "edit_file", "bash"})

        readonly_reg = agent._registry("sid", context=Context(self.workspace),
                                       readonly=True, deadline=9999999999.0)
        self.assertNotIn("bash", readonly_reg.tools)
        self.assertNotIn("edit_file", readonly_reg.tools)

    def test_chat_model_sse_streaming_text_reasoning_and_tool_calls(self):
        model = ChatModel("test-model", "https://example.invalid/v1", "sk-test")
        sse_lines = [
            'data: {"choices":[{"delta":{"reasoning_content":"先想"}}]}\n',
            'data: {"choices":[{"delta":{"reasoning_content":"一下"}}]}\n',
            'data: {"choices":[{"delta":{"content":"你好"}}]}\n',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","type":"function","function":{"name":"ba","arguments":"{\\"command\\":"}}]}}]}\n',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"sh","arguments":"\\"echo ok\\"}"}}]}}]}\n',
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":42,"completion_tokens":13,"prompt_tokens_details":{"cached_tokens":20}}}\n',
            "data: [DONE]\n",
        ]
        deltas = []
        with patch("codeharness.models.urlopen", return_value=FakeStreamResponse(sse_lines)) as mock_open:
            reply = model.complete([{"role": "user", "content": "hi"}], [], 256,
                                   on_delta=lambda kind, chunk: deltas.append((kind, chunk)))
        body = json.loads(mock_open.call_args[0][0].data.decode("utf-8"))
        self.assertTrue(body["stream"])
        self.assertEqual(body["stream_options"], {"include_usage": True})
        self.assertEqual(deltas, [("reasoning", "先想"), ("reasoning", "一下"), ("text", "你好")])
        self.assertEqual(reply.message["reasoning_content"], "先想一下")
        self.assertEqual(reply.message["content"], "你好")
        self.assertEqual(reply.message["tool_calls"][0]["function"]["name"], "bash")
        self.assertEqual(json.loads(reply.message["tool_calls"][0]["function"]["arguments"]), {"command": "echo ok"})
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.cached_tokens), (42, 13, 20))

        with patch("codeharness.models.urlopen", return_value=FakeStreamResponse(sse_lines[:5])):
            with self.assertRaisesRegex(ModelError, "提前结束"):
                model.complete([{"role": "user", "content": "hi"}], [], 256, on_delta=lambda *_: None)

    def test_chat_model_sse_truncation_raises_truncated_error(self):
        model = ChatModel("test-model", "https://example.invalid/v1", "sk-test")
        sse_lines = [
            'data: {"choices":[{"delta":{"content":"半截"}}]}\n',
            'data: {"choices":[{"delta":{},"finish_reason":"length"}],"usage":{"prompt_tokens":10,"completion_tokens":5}}\n',
            "data: [DONE]\n",
        ]
        with patch("codeharness.models.urlopen", return_value=FakeStreamResponse(sse_lines)):
            with self.assertRaises(ModelError) as ctx:
                model.complete([{"role": "user", "content": "hi"}], [], 16, on_delta=lambda k, c: None)
        self.assertTrue(ctx.exception.truncated)
        self.assertEqual(ctx.exception.usage, (10, 5))

    def test_manual_compact_reduces_next_request_context(self):
        steps = [
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t1", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"hello.txt"}'}}]}},
            {"message": {"role": "assistant", "content": "第1轮完成"}},
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                {"id": "t2", "type": "function", "function": {"name": "read_file", "arguments": '{"path":"hello.txt"}'}}]}},
            {"message": {"role": "assistant", "content": "第2轮完成"}},
            {"message": {"role": "assistant", "content": "压缩后继续"}},
        ]
        model = StreamingStubModel(steps)
        agent = Agent(model, self.workspace, self.store, Policy(allow_write=True, allow_exec=True),
                      enable_bash=True, tool_profile="pi")
        r1 = agent.run("先看文件")
        r2 = agent.run("再看一次", session_id=r1.session_id)
        info = agent.compact(r2.session_id, note="保留关键结论")
        self.assertTrue(info["compacted"])
        self.assertLess(info["after_messages"], info["before_messages"])

        r3 = agent.run("总结一下", session_id=r2.session_id)
        self.assertEqual(r3.status, "completed")
        sent = model.seen_messages[-1]
        self.assertTrue(any("[手动压缩摘要" in m.get("content", "") and "保留关键结论" in m.get("content", "")
                            for m in sent if m["role"] == "user"))

    def test_run_chat_repl_commands_and_streaming_flow(self):
        steps = [
            {
                "deltas": [("reasoning", "查一下文件"), ("text", "我先用 bash 看看")],
                "message": {"role": "assistant", "content": "我先用 bash 看看", "reasoning_content": "查一下文件",
                            "tool_calls": [{"id": "b1", "type": "function",
                                            "function": {"name": "bash",
                                                         "arguments": json.dumps({"command": 'python -c "print(777)"'})}}]},
            },
            {
                "deltas": [("text", "输出是 777。")],
                "message": {"role": "assistant", "content": "输出是 777。"},
            },
        ]
        model = StreamingStubModel(steps)
        policy = Policy(allow_write=True, allow_exec=True)
        agent = Agent(model, self.workspace, self.store, policy, Limits(max_requests=20),
                      enable_bash=True, tool_profile="pi")
        inputs = iter([
            "/help",
            "/tools",
            '!python -c "print(999)"',
            "帮我跑个命令",
            "/session",
            "/exit",
        ])
        out = io.StringIO()
        code = run_chat(agent, self.workspace, self.store, policy, stream=True,
                        input_fn=lambda prompt="": next(inputs), output=out)
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("工具模式：pi（bash=开）", text)
        self.assertIn("999", text)
        self.assertIn("[思考] 查一下文件", text)
        self.assertIn("[工具] bash", text)
        self.assertIn("输出是 777。", text)
        self.assertIn("会话已保存：", text)

    def test_cli_chat_defaults_and_flags(self):
        cli = parser()
        args = cli.parse_args(["chat", "--tool-profile", "pi"])
        self.assertEqual(args.command, "chat")
        self.assertEqual(args.tool_profile, "pi")
        self.assertFalse(args.no_bash)
        self.assertFalse(args.confirm)
        self.assertEqual(args.max_requests, 200)
        for command in ("run", "resume"):
            prior = cli.parse_args([command, "x"])
            self.assertEqual((prior.max_requests, prior.max_tokens, prior.max_seconds), (24, 60000, 600))


if __name__ == "__main__":
    unittest.main()
