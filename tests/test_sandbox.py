from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from codeharness.cli import main, trace_timeline
from codeharness.demo import DemoModel
from codeharness.models import ModelError
from codeharness.runtime import Agent, Limits
from codeharness.sandbox import DockerExecutor
from codeharness.store import Store
from codeharness.tools import Policy, Registry, ToolError, Workspace, register_workspace_tools


class ScriptModel:
    name = "script-sandbox"

    def __init__(self, *steps):
        self.steps = iter(steps)

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        step = next(self.steps)
        return step(messages, tools) if callable(step) else step


class DockerSandboxTests(unittest.TestCase):
    def test_docker_command_enforces_isolation_and_clean_env(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            executor = DockerExecutor("python:3.12-slim", memory="256m", cpus="0.5", pids_limit=32)
            host_env = {
                "PATH": r"C:\Windows\System32",
                "HOME": r"C:\Users\secret",
                "OPENAI_API_KEY": "sk-secret",
                "CUSTOM_FLAG": "enabled",
            }
            cmd = executor.build_command(
                ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
                root, host_env, "codeharness-test123", pass_env=("CUSTOM_FLAG",),
            )
            self.assertEqual(cmd[:5], ["docker", "run", "--rm", "--init", "--name"])
            self.assertIn("--network", cmd)
            self.assertEqual(cmd[cmd.index("--network") + 1], "none")
            self.assertEqual(cmd[cmd.index("--memory") + 1], "256m")
            self.assertEqual(cmd[cmd.index("--cpus") + 1], "0.5")
            self.assertEqual(cmd[cmd.index("--pids-limit") + 1], "32")
            self.assertIn("--read-only", cmd)
            self.assertIn("--cap-drop", cmd)
            self.assertEqual(cmd[cmd.index("--cap-drop") + 1], "ALL")
            self.assertIn("no-new-privileges", cmd)
            self.assertIn(f"{root}:/workspace:rw", cmd)
            env_pairs = [cmd[i + 1] for i, token in enumerate(cmd) if token == "-e"]
            self.assertIn("HOME=/tmp", env_pairs)
            self.assertIn("PYTHONDONTWRITEBYTECODE=1", env_pairs)
            self.assertIn("PYTHONIOENCODING=utf-8", env_pairs)
            self.assertIn("CUSTOM_FLAG=enabled", env_pairs)
            self.assertFalse(any(pair.startswith("PATH=") for pair in env_pairs))
            self.assertFalse(any("sk-secret" in pair for pair in env_pairs))
            self.assertEqual(cmd[-7:], ["python:3.12-slim", "python", "-m", "unittest", "discover", "-s", "tests", "-v"][-7:])

    def test_docker_executor_rejects_invalid_config(self):
        with self.assertRaises(ValueError):
            DockerExecutor("bad image")
        with self.assertRaises(ValueError):
            DockerExecutor("python:3.12-slim", pids_limit=0)
        with self.assertRaises(ValueError):
            DockerExecutor("python:3.12-slim", cpus="abc")

    def test_run_tests_and_bash_route_through_docker_executor_with_posix_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            (root / "tests").mkdir(parents=True)
            (root / "tests" / "test_ok.py").write_text("pass\n", encoding="utf-8")
            workspace = Workspace(root)
            registry = Registry(workspace, Policy(allow_exec=True, pass_env=("ALLOWED_VAR",)))
            register_workspace_tools(registry, enable_bash=True, executor=DockerExecutor("python:3.12-slim"))

            with patch("codeharness.sandbox.subprocess.Popen") as launch:
                proc = launch.return_value
                proc.returncode = 0
                proc.communicate.return_value = (b"Ran 1 test\nOK\n", None)
                res = registry.invoke("run_tests", {"path": "tests/test_ok.py"})
                self.assertTrue(res["passed"])
                self.assertEqual(res["sandbox"], "docker")
                argv = launch.call_args.args[0]
                self.assertEqual(argv[-7:], ["python", "-m", "unittest", "discover", "-s", "tests", "-p", "test_ok.py", "-v"][-7:])
                self.assertIn("python", argv)

                proc.communicate.return_value = (b"hello\n", None)
                bash_res = registry.invoke("bash", {"command": "echo hello"})
                self.assertEqual(bash_res["sandbox"], "docker")
                self.assertEqual(bash_res["output"], "hello\n")
                bash_argv = launch.call_args.args[0]
                self.assertEqual(bash_argv[-3:], ["sh", "-c", "echo hello"])

    def test_docker_timeout_forces_container_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executor = DockerExecutor("python:3.12-slim")
            with patch("codeharness.sandbox.subprocess.Popen") as launch, \
                    patch("codeharness.sandbox.subprocess.run") as cleanup:
                proc = launch.return_value
                proc.communicate.side_effect = [subprocess.TimeoutExpired("docker", 1), (b"", None)]
                with self.assertRaises(subprocess.TimeoutExpired):
                    executor.run_shell("sleep 99", root, {}, timeout=1.0)
                cleanup.assert_called_once()
                cleanup_cmd = cleanup.call_args.args[0]
                self.assertEqual(cleanup_cmd[:3], ["docker", "rm", "-f"])
                self.assertTrue(cleanup_cmd[3].startswith("codeharness-"))
                proc.kill.assert_called_once()

    def test_missing_docker_binary_raises_tool_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = Workspace(root)
            registry = Registry(workspace, Policy(allow_exec=True))
            register_workspace_tools(registry, enable_bash=True, executor=DockerExecutor())
            with patch("codeharness.sandbox.subprocess.Popen", side_effect=FileNotFoundError("docker")):
                with self.assertRaisesRegex(ToolError, "docker"):
                    registry.invoke("bash", {"command": "echo hi"})

    def test_cli_accepts_sandbox_flags_and_passes_docker_executor(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            captured = {}

            class DummyAgent:
                def __init__(self, *args, **kwargs):
                    captured["executor"] = kwargs.get("executor")

                def run(self, task, session_id=None):
                    from codeharness.runtime import Result
                    return Result("sid1", "completed", "ok", "not_run", [], {"requests": 0, "input_tokens": 0, "output_tokens": 0})

                def close(self):
                    pass

            with patch("codeharness.cli.Agent", DummyAgent), redirect_stdout(StringIO()):
                code = main(["run", "测试", "--workspace", str(root), "--model", "offline-demo",
                             "--sandbox", "docker", "--sandbox-image", "python:3.11-slim", "--json"])
            self.assertEqual(code, 0)
            self.assertIsInstance(captured["executor"], DockerExecutor)
            self.assertEqual(captured["executor"].image, "python:3.11-slim")


class ObservabilityTraceTests(unittest.TestCase):
    def test_turn_attempt_and_duration_ms_correlate_retries_tools_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            (root / "a.py").write_text("x = 1\n", encoding="utf-8")
            (root / "b.py").write_text("y = 2\n", encoding="utf-8")
            store = Store(Path(temp) / "state.sqlite3")
            try:
                def transient(messages, tools):
                    raise ModelError("HTTP 429", retryable=True, retry_after=0, consume_output_budget=False)

                batch = DemoModel.call("read_file", {"path": "a.py"})
                batch.message["tool_calls"] += DemoModel.call("read_file", {"path": "b.py"}).message["tool_calls"]
                model = ScriptModel(transient, batch, DemoModel.text("第一轮结束"))
                with patch("codeharness.runtime.time.sleep"):
                    first = Agent(model, root, store, Policy(True, True)).run("检查两个文件")
                self.assertEqual(first.status, "completed")

                resumed = Agent(ScriptModel(DemoModel.text("恢复完成")), root, store, Policy(True, True)).run(
                    "继续", session_id=first.session_id)
                self.assertEqual(resumed.status, "completed")

                events = store.events(first.session_id, expand=False)
                reqs = [e["data"] for e in events if e["kind"] == "model_request"]
                self.assertEqual([(r["turn"], r["attempt"]) for r in reqs], [(1, 1), (1, 2), (2, 1), (3, 1)])

                errors = [e["data"] for e in events if e["kind"] == "model_error"]
                self.assertEqual(errors[0]["turn"], 1)
                self.assertIsInstance(errors[0]["duration_ms"], int)
                self.assertGreaterEqual(errors[0]["duration_ms"], 0)

                retries = [e["data"] for e in events if e["kind"] == "model_retry"]
                self.assertEqual(retries[0]["turn"], 1)

                usages = [e["data"] for e in events if e["kind"] == "usage" and not e["data"].get("failed_attempt")]
                self.assertEqual([u["turn"] for u in usages], [1, 2, 3])
                self.assertTrue(all(isinstance(u["duration_ms"], int) and u["duration_ms"] >= 0 for u in usages))

                started = [e["data"] for e in events if e["kind"] == "tool_started"]
                finished = [e["data"] for e in events if e["kind"] == "tool_finished"]
                self.assertEqual([t["turn"] for t in started], [1, 1])
                self.assertEqual([t["turn"] for t in finished], [1, 1])
                self.assertTrue(all(isinstance(t["duration_ms"], int) and t["duration_ms"] >= 0 for t in finished))

                timeline = list(trace_timeline(events))
                kinds = [item["kind"] for item in timeline]
                self.assertIn("usage", kinds)
                first_usage = next(item["data"] for item in timeline if item["kind"] == "usage" and "duration_ms" in item["data"])
                self.assertEqual(first_usage["turn"], 1)
                self.assertIn("duration_ms", first_usage)
                first_tool = next(item["data"] for item in timeline if item["kind"] == "tool_finished")
                self.assertEqual(first_tool["turn"], 1)
                self.assertIn("duration_ms", first_tool)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
