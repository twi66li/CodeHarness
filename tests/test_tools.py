from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codeharness.benchmark import acceptance
from codeharness.cli import main as cli
from codeharness.demo import DemoModel
from codeharness.tools import Policy, Registry, ToolError, Workspace, register_workspace_tools


class RunTestsModel:
    name = "fixture"

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        if any(message["role"] == "tool" for message in messages):
            return DemoModel.text("完成")
        return DemoModel.call("run_tests", {})


class ToolTests(unittest.TestCase):
    def test_cli_pass_env_changes_only_explicit_test_environment(self):
        for pass_token in (False, True):
            with self.subTest(pass_token=pass_token), tempfile.TemporaryDirectory() as temp:
                tests = Path(temp) / "tests"
                tests.mkdir()
                (tests / "test_environment.py").write_text(
                    "import os, unittest\nclass T(unittest.TestCase):\n def test_environment(self):\n"
                    f"  self.assertEqual(os.environ.get('FOO_TOKEN'), {('fixture-value' if pass_token else None)!r})\n"
                    "  self.assertNotIn('OTHER_SECRET', os.environ)\n", encoding="utf-8")
                extras = ["--pass-env", "FOO_TOKEN"] if pass_token else []
                env = {**os.environ, "FOO_TOKEN": "fixture-value", "OTHER_SECRET": "never-inherited"}
                with patch("os.environ", env), patch("codeharness.cli.ChatModel", return_value=RunTestsModel()), \
                        redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(cli(["run", "验证项目", "--workspace", temp, "--allow-exec", "--json",
                                          "--model", "fixture", "--base-url", "https://fixture.invalid/v1", *extras]), 0)
                self.assertEqual(json.loads(output.getvalue())["verification"], "passed")
                self.assertEqual("FOO_TOKEN" in stderr.getvalue(), pass_token)
                self.assertNotIn("fixture-value", stderr.getvalue())

    def test_acceptance_inherits_the_same_restricted_environment(self):
        with tempfile.TemporaryDirectory() as temp, patch("os.environ", {**os.environ, "GITHUB_TOKEN": "fixture"}):
            root = Path(temp)
            verifier = root / "check.py"
            verifier.write_text("import os\nassert 'GITHUB_TOKEN' not in os.environ\n", encoding="utf-8")
            self.assertTrue(acceptance(root, verifier)["passed"])

    def test_private_files_are_absent_from_list_and_rejected_by_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            protected_names = ("tls.PEM", "secret.key", "identity.p12", "id_ed25519-backup", "id_rsa", ".netrc",
                               ".pypirc", ".npmrc", ".git-credentials")
            for name in (*protected_names, "public.py"):
                (root / name).write_text("fixture", encoding="utf-8")
            registry = Registry(Workspace(root), Policy())
            register_workspace_tools(registry)
            self.assertEqual([path.name for path in registry.workspace.files()], ["public.py"])
            for name in protected_names:
                with self.subTest(name=name), self.assertRaisesRegex(ToolError, "受保护"):
                    registry.invoke("read_file", {"path": name})
