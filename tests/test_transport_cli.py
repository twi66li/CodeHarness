from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from codeharness.cli import isolated_workspace
from codeharness.demo import DemoModel
from codeharness.models import ChatModel, ModelError
from codeharness.store import Store


PROJECT = Path(__file__).resolve().parents[1]


@contextmanager
def server_for(respond):
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
            with self.assertRaises(ModelError):
                ChatModel("model", base, "fake").complete([], [], 100)


class CliTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
