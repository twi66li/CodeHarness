from contextlib import contextmanager, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from codeharness.cli import isolated_workspace, load_env, main, model_connection
from codeharness.demo import DemoModel, create_demo
from codeharness.models import ChatModel, ModelError
from codeharness.store import Store


PROJECT = Path(__file__).resolve().parents[1]


@contextmanager
def server_for(respond):
    if os.environ.get("CODEHARNESS_SKIP_LOOPBACK") == "1":
        raise unittest.SkipTest("当前环境明确禁止本地回环连接；使用模拟传输测试覆盖协议逻辑")
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            status, response = respond(self.path, self.headers, payload)
            encoded = json.dumps(response, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def completion(message, reason="stop"):
    return {"choices": [{"message": message, "finish_reason": reason}],
            "usage": {"prompt_tokens": 123, "completion_tokens": 45}}


class TransportTests(unittest.TestCase):
    def test_mock_transport_preserves_reasoning_and_remaining_timeout(self):
        message = DemoModel.call("list_files", {}).message
        message["reasoning_content"] = "fixture reasoning"
        wire = json.dumps(completion(message, "tool_calls")).encode("utf-8")
        with patch("codeharness.models.urlopen", return_value=BytesIO(wire)) as opener:
            model = ChatModel("test", "https://fixture.invalid/v1", "FAKE_TEST_CREDENTIAL")
            reply = model.complete([{"role": "user", "content": "检查"}], [], 100, timeout=7)
        self.assertEqual(reply.message, message)
        self.assertEqual(opener.call_args.kwargs["timeout"], 7)
        next_wire = json.dumps(completion({"role": "assistant", "content": "done"})).encode("utf-8")
        with patch("codeharness.models.urlopen", return_value=BytesIO(next_wire)) as opener:
            model.complete([reply.message], [], 100)
        payload = json.loads(opener.call_args.args[0].data)
        self.assertEqual(payload["messages"][0]["reasoning_content"], "fixture reasoning")

    def test_mock_transport_retryable_http_errors_are_sanitized(self):
        for status, retryable in ((429, True), (503, True), (401, False), (400, False)):
            with self.subTest(status=status), patch("codeharness.models.urlopen", side_effect=HTTPError(
                    "https://fixture.invalid/v1", status, "FAKE_TEST_CREDENTIAL", {"Retry-After": "2"}, None)):
                with self.assertRaises(ModelError) as caught:
                    ChatModel("test", "https://fixture.invalid/v1", "FAKE_TEST_CREDENTIAL").complete([], [], 100)
                self.assertEqual(caught.exception.retryable, retryable)
                self.assertEqual(caught.exception.retry_after, 2)
                self.assertIn(str(status), str(caught.exception))
                self.assertNotIn("FAKE_TEST_CREDENTIAL", str(caught.exception))

    def test_mock_transport_strips_extra_tool_call_fields_and_extracts_safe_error_tag(self):
        message = DemoModel.call("list_files", {}).message
        message["tool_calls"][0]["index"] = 0
        message["tool_calls"][0]["extra"] = "drop-me"
        wire = json.dumps(completion(message, "tool_calls")).encode("utf-8")
        with patch("codeharness.models.urlopen", return_value=BytesIO(wire)):
            reply = ChatModel("test", "https://fixture.invalid/v1", "FAKE_KEY").complete([], [], 100)
        self.assertEqual(set(reply.message["tool_calls"][0].keys()), {"id", "type", "function"})

        body = BytesIO(json.dumps({"error": {"code": "rate_limit_exceeded", "message": "echo FAKE_KEY"}}).encode())
        with patch("codeharness.models.urlopen", side_effect=HTTPError(
                "https://fixture.invalid/v1", 429, "Too Many Requests", {}, body)):
            with self.assertRaises(ModelError) as caught:
                ChatModel("test", "https://fixture.invalid/v1", "FAKE_KEY").complete([], [], 100)
        self.assertIn("rate_limit_exceeded", str(caught.exception))
        self.assertNotIn("FAKE_KEY", str(caught.exception))
        self.assertFalse(caught.exception.consume_output_budget)

    def test_mock_transport_permission_error_is_not_retryable(self):
        with patch("codeharness.models.urlopen", side_effect=URLError(PermissionError("denied"))):
            with self.assertRaises(ModelError) as caught:
                ChatModel("test", "https://fixture.invalid/v1", "fake").complete([], [], 100)
        self.assertFalse(caught.exception.retryable)

    def test_mock_transport_rejects_incomplete_or_duplicate_tool_calls(self):
        message = DemoModel.call("list_files", {}).message
        message["tool_calls"] *= 2
        for wire, expected in ((completion(message, "length"), "不完整"),
                               (completion(message, "tool_calls"), "缺少有效")):
            with self.subTest(expected=expected), patch("codeharness.models.urlopen",
                    return_value=BytesIO(json.dumps(wire).encode("utf-8"))):
                with self.assertRaisesRegex(ModelError, expected):
                    ChatModel("test", "https://fixture.invalid/v1", "fake").complete([], [], 100)

    def test_chat_transport_preserves_tool_call_ids_and_usage(self):
        expected = DemoModel.call("read_file", {"path": "a.py"}).message
        seen = []
        def respond(path, headers, payload):
            seen.append((path, headers.get("Authorization"), payload))
            return 200, completion(expected, "tool_calls")
        with server_for(respond) as base:
            reply = ChatModel("test-model", base, "FAKE_TEST_CREDENTIAL").complete(
                [{"role": "user", "content": "检查代码"}], [{"type": "function", "function": {"name": "read_file"}}], 512)
        self.assertEqual(reply.message, expected)
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.estimated), (123, 45, False))
        self.assertEqual(seen[0][0], "/v1/chat/completions")
        self.assertEqual(seen[0][1], "Bearer FAKE_TEST_CREDENTIAL")
        self.assertEqual(seen[0][2]["max_tokens"], 512)

    def test_provider_error_body_does_not_leak_credentials(self):
        def respond(path, headers, payload):
            return 401, {"error": "echo FAKE_TEST_CREDENTIAL"}
        with server_for(respond) as base:
            with self.assertRaises(ModelError) as caught:
                ChatModel("model", base, "FAKE_TEST_CREDENTIAL").complete([], [], 100)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("FAKE_TEST_CREDENTIAL", str(caught.exception))

    def test_truncated_model_output_is_not_executed(self):
        def respond(path, headers, payload):
            return 200, completion(DemoModel.call("write_file", {"path": "x.py"}).message, "length")
        with server_for(respond) as base:
            with self.assertRaisesRegex(ModelError, "不完整"):
                ChatModel("model", base, "fake").complete([], [], 100)

    def test_duplicate_tool_ids_rejected(self):
        message = DemoModel.call("list_files", {}).message
        message["tool_calls"] *= 2
        def respond(path, headers, payload):
            return 200, completion(message, "tool_calls")
        with server_for(respond) as base:
            with self.assertRaisesRegex(ModelError, "缺少有效"):
                ChatModel("model", base, "fake").complete([], [], 100)


class CliTests(unittest.TestCase):
    def test_cli_mock_transport_runs_complete_tool_loop(self):
        captured = []

        def respond(request, timeout):
            payload = json.loads(request.data)
            self.assertEqual(payload["reasoning_effort"], "low")
            captured.append(payload)
            if len(captured) == 1:
                message = DemoModel.call("list_files", {}).message
                message["tool_calls"][0]["id"] = "mock-wire-call"
                message["reasoning_content"] = "fixture reasoning"
                response = completion(message, "tool_calls")
            else:
                self.assertEqual(payload["messages"][-1]["tool_call_id"], "mock-wire-call")
                self.assertEqual(payload["messages"][-2]["reasoning_content"], "fixture reasoning")
                response = completion({"role": "assistant", "content": "已检查工作区"})
            return BytesIO(json.dumps(response).encode("utf-8"))

        with tempfile.TemporaryDirectory() as temp, \
                patch("os.environ", {**os.environ, "CODEHARNESS_API_KEY": "FAKE_TEST_CREDENTIAL"}), \
                patch("codeharness.models.urlopen", side_effect=respond), redirect_stdout(StringIO()) as output:
            code = main(["run", "检查仓库", "--workspace", temp, "--model", "mock-model",
                         "--base-url", "https://fixture.invalid/v1", "--reasoning-effort", "low", "--json"])
            self.assertEqual(code, 0, output.getvalue())
            result = json.loads(output.getvalue())
            self.assertEqual((result["status"], result["usage"]["requests"]), ("completed", 2))
            store = Store(Path(result["store"]))
            try:
                self.assertNotIn("FAKE_TEST_CREDENTIAL", json.dumps(store.events(result["session_id"])))
            finally:
                store.close()
        self.assertEqual(len(captured), 2)

    def test_cli_runs_http_tool_loop_and_keeps_credential_out_of_events(self):
        captured = []
        tool_id = "wire-call-1"
        def respond(path, headers, payload):
            captured.append(payload)
            if len(captured) == 1:
                message = DemoModel.call("list_files", {}).message
                message["tool_calls"][0]["id"] = tool_id
                return 200, completion(message, "tool_calls")
            self.assertEqual(payload["messages"][-1]["role"], "tool")
            self.assertEqual(payload["messages"][-1]["tool_call_id"], tool_id)
            return 200, completion({"role": "assistant", "content": "已检查工作区"})
        with tempfile.TemporaryDirectory() as temp, server_for(respond) as base:
            root = Path(temp)
            environment = dict(os.environ)
            environment["CODEHARNESS_API_KEY"] = "FAKE_TEST_CREDENTIAL"
            environment["PYTHONIOENCODING"] = "utf-8"
            process = subprocess.run([sys.executable, "-m", "codeharness", "run", "检查仓库", "--workspace", str(root),
                "--model", "wire-model", "--base-url", base, "--json"], cwd=PROJECT, env=environment,
                capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
            result = json.loads(process.stdout)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["usage"]["requests"], 2)
            store = Store(root / ".codeharness" / "state.sqlite3")
            try:
                events = json.dumps(store.events(result["session_id"]), ensure_ascii=False)
                self.assertNotIn("FAKE_TEST_CREDENTIAL", events)
            finally:
                store.close()

    def test_missing_model_configuration_has_actionable_error(self):
        environment = {key: value for key, value in os.environ.items()
                       if not key.upper().startswith(("CODEHARNESS_", "OPENAI_"))}
        environment["PYTHONIOENCODING"] = "utf-8"
        with tempfile.TemporaryDirectory() as temp:
            process = subprocess.run([sys.executable, "-m", "codeharness", "run", "检查", "--workspace", temp, "--json"],
                cwd=PROJECT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(process.returncode, 2)
        self.assertIn("demo", json.loads(process.stdout)["error"])

    def test_git_isolation_keeps_original_worktree_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / ".gitignore").write_text(".codeharness/\n", encoding="utf-8")
            (root / "a.py").write_text("original", encoding="utf-8")
            commands = [["git", "init", "-q"], ["git", "add", ".gitignore", "a.py"],
                        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                         "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]]
            for command in commands:
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            isolated = isolated_workspace(root)
            (isolated / "a.py").write_text("changed", encoding="utf-8")
            self.assertEqual((root / "a.py").read_text(encoding="utf-8"), "original")
            self.assertNotEqual(isolated, root)

    def test_cli_isolate_works_without_gitignore_and_stays_clean_on_dirty_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = (Path(temp) / "repo").resolve()
            create_demo(root)
            for command in [["git", "init", "-q"], ["git", "add", "."],
                            ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                             "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]]:
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            for _ in range(2):
                proc = subprocess.run([
                    sys.executable, "-m", "codeharness", "run", "修复折扣", "--workspace", str(root),
                    "--model", "offline-demo", "--isolate", "--allow-write", "--allow-exec", "--json",
                ], cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
                self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "verified")
                self.assertNotEqual(Path(payload["workspace"]).resolve(), root)
            self.assertIn("sum(prices) - discount", (root / "basket.py").read_text(encoding="utf-8"))

            dirty_root = (Path(temp) / "dirty_repo").resolve()
            create_demo(dirty_root)
            for command in [["git", "init", "-q"], ["git", "add", "."],
                            ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                             "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]]:
                subprocess.run(command, cwd=dirty_root, check=True, capture_output=True)
            (dirty_root / "uncommitted.py").write_text("dirty", encoding="utf-8")
            failed = subprocess.run([
                sys.executable, "-m", "codeharness", "run", "修复折扣", "--workspace", str(dirty_root),
                "--model", "offline-demo", "--isolate", "--json",
            ], cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(failed.returncode, 2)
            self.assertFalse((dirty_root / ".codeharness").exists())

    def test_load_env_does_not_mutate_os_environ(self):
        key = "CODEHARNESS_TEST_SECRET_DO_NOT_LEAK"
        os.environ.pop(key, None)
        with tempfile.TemporaryDirectory() as temp:
            env_file = Path(temp) / ".env"
            env_file.write_text(
                f"{key}='secret-value'  # inline comment\n"
                "SECOND_KEY=\"val2\" # second comment\n"
                "PLAIN_KEY=plain # trailing comment\n",
                encoding="utf-8",
            )
            loaded = load_env(env_file)
        self.assertEqual(loaded[key], "secret-value")
        self.assertEqual(loaded["SECOND_KEY"], "val2")
        self.assertEqual(loaded["PLAIN_KEY"], "plain")
        self.assertNotIn(key, os.environ)

    def test_explicit_base_url_does_not_use_dashscope_credentials(self):
        env = {"DASHSCOPE_BASE_URL": "https://dashscope.invalid/v1", "DASHSCOPE_API_KEY": "fake-key"}
        self.assertEqual(model_connection(env, "https://custom.invalid/v1"), ("https://custom.invalid/v1", ""))


if __name__ == "__main__":
    unittest.main()
