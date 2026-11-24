from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
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
    def test_unified_patch_updates_multiple_hunks_files_and_preserves_text_format(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.py").write_bytes(b"\xef\xbb\xbfalpha = 1\r\nbeta = 2\r\ngamma = 3\r\n")
            (root / "old.txt").write_text("remove me\n", encoding="utf-8", newline="\n")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            result = registry.invoke("apply_patch", {"patch": (
                "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-alpha = 1\n+alpha = 10\n"
                "@@ -3 +3 @@\n-gamma = 3\n+gamma = 30\n"
                "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+added = 1\n"
                "--- a/old.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-remove me\n"
            )})
            self.assertEqual((root / "a.py").read_bytes(), b"\xef\xbb\xbfalpha = 10\r\nbeta = 2\r\ngamma = 30\r\n")
            self.assertEqual((root / "new.py").read_text(encoding="utf-8"), "added = 1\n")
            self.assertFalse((root / "old.txt").exists())
            self.assertEqual([item["path"] for item in result["files"]], ["a.py", "new.py", "old.txt"])
            self.assertTrue(result["files"][0]["syntax_valid"])

    def test_unified_patch_validates_every_file_before_any_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("a.txt", "b.txt", ".env"):
                (root / name).write_text("original\n", encoding="utf-8", newline="\n")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            first = "--- a.txt\n+++ a.txt\n@@ -1 +1 @@\n-original\n+changed\n"
            for target, old in (("b.txt", "does not match"), ("../outside.txt", "original"), (".env", "original")):
                rest = f"--- {target}\n+++ {target}\n@@ -1 +1 @@\n-{old}\n+changed\n"
                with self.subTest(target=target), self.assertRaises(ToolError):
                    registry.invoke("apply_patch", {"patch": first + rest})
                self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "original\n")
            registry.policy = Policy(allow_write=True, readonly=True)
            with self.assertRaisesRegex(ToolError, "只读"):
                registry.invoke("apply_patch", {"patch": first})

    def test_unified_patch_accepts_unprefixed_empty_context_line(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "a.txt"
            path.write_text("first\n\nold\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            registry.invoke("apply_patch", {"patch": "--- a.txt\n+++ a.txt\n@@ -1,3 +1,3 @@\n first\n\n-old\n+new\n"})
            self.assertEqual(path.read_text(encoding="utf-8"), "first\n\nnew\n")

    def test_unified_patch_supports_multiple_exact_match_hunks_without_line_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "a.txt", root / "b.txt"
            first.write_text("old heading\nunchanged\nold ending\n", encoding="utf-8")
            second.write_text("old\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            patch_text = ("--- a/a.txt\n+++ b/a.txt\n@@\n-old heading\n+heading\n@@\n-old ending\n+ending\n"
                          "--- a/b.txt\n+++ b/b.txt\n@@\n-old\n+new\n*** End Patch\n")
            registry.invoke("apply_patch", {"patch": patch_text})
            self.assertEqual(first.read_text(encoding="utf-8"), "heading\nunchanged\nending\n")
            self.assertEqual(second.read_text(encoding="utf-8"), "new\n")

    def test_unified_patch_accepts_missing_new_header_between_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "a.sql", root / "b.sql"
            first.write_text("old a\n", encoding="utf-8")
            second.write_text("old b\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            registry.invoke("apply_patch", {"patch": (
                "--- a/a.sql\n+++ b/a.sql\n@@\n-old a\n+new a\n"
                "--- a/b.sql\n@@\n-old b\n+new b\n"
            )})
            self.assertEqual(first.read_text(encoding="utf-8"), "new a\n")
            self.assertEqual(second.read_text(encoding="utf-8"), "new b\n")

    def test_unified_patch_accepts_end_markers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "a.txt"
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            for marker in ("*** End Patch", "--- End Patch"):
                with self.subTest(marker=marker):
                    path.write_text("old\n", encoding="utf-8")
                    registry.invoke("apply_patch", {"patch": (
                        f"--- a.txt\n+++ a.txt\n@@\n-old\n+new\n{marker}\n"
                    )})
                    self.assertEqual(path.read_text(encoding="utf-8"), "new\n")

    def test_unified_patch_preserves_sql_comment_removal_at_hunk_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "query.sql"
            path.write_text("-- comment\nkeep\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            registry.invoke("apply_patch", {"patch": (
                "--- query.sql\n+++ query.sql\n@@\n--- comment\n@@\n-keep\n+updated\n"
            )})
            self.assertEqual(path.read_text(encoding="utf-8"), "updated\n")

    def test_openai_patch_updates_adds_and_deletes_without_partial_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            updated, deleted, added = (root / name for name in ("update.py", "old.bin", "new.py"))
            updated.write_bytes(b"\xef\xbb\xbfx = 1\r\n")
            deleted.write_bytes(b"\xffold")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            begin = "*** Begin Patch\n"
            update = "*** Update File: update.py\n@@\n-x = 1\n+x = 2\n"
            with self.assertRaisesRegex(ToolError, "Move to"):
                registry.invoke("apply_patch", {"patch": begin + update + "*** Move to: other.py\n*** End Patch\n"})
            with self.assertRaisesRegex(ToolError, "超出工作区"):
                registry.invoke("apply_patch", {"patch": begin + update + "*** Delete File: ../outside\n*** End Patch\n"})
            self.assertEqual(updated.read_bytes(), b"\xef\xbb\xbfx = 1\r\n")
            registry.invoke("apply_patch", {"patch": (
                begin + update + "*** Add File: new.py\n+y = 3\n*** Delete File: old.bin\n*** End Patch\n"
            )})
            self.assertEqual(updated.read_bytes(), b"\xef\xbb\xbfx = 2\r\n")
            self.assertEqual(added.read_bytes(), b"y = 3\n")
            self.assertFalse(deleted.exists())

    def test_unified_patch_tolerates_wrong_counts_but_requires_position_for_pure_insert(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "a.txt"
            path.write_text("old\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            header = "--- a.txt\n+++ a.txt\n"
            with self.assertRaisesRegex(ToolError, "纯插入"):
                registry.invoke("apply_patch", {"patch": header + "@@\n+new\n"})
            for marker in ("@@ -1,20 +1,20 @@", "@@ -1,0 +1,0 @@", "@@ 修改标题 @@"):
                with self.subTest(marker=marker):
                    path.write_text("old\n", encoding="utf-8")
                    registry.invoke("apply_patch", {"patch": header + marker + "\n-old\n+new\n"})
                    self.assertEqual(path.read_text(encoding="utf-8"), "new\n")

    def test_unified_patch_uses_nearest_line_hint_and_rejects_ties(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "a.txt"
            original = "old\nkeep\nold\n"
            path.write_text(original, encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            with self.assertRaisesRegex(ToolError, "a.txt.*第 1.*1, 3.*edit_file"):
                registry.invoke("apply_patch", {"patch": "--- a.txt\n+++ a.txt\n@@ -2 +2 @@\n-old\n+new\n"})
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            registry.invoke("apply_patch", {"patch": "--- a.txt\n+++ a.txt\n@@ -3 +3 @@\n-old\n+new\n"})
            self.assertEqual(path.read_text(encoding="utf-8"), "old\nkeep\nnew\n")

    def test_unified_patch_exclusively_creates_and_rolls_back_without_hard_links(self):
        create = "--- /dev/null\n+++ new.txt\n@@ -0,0 +1 @@\n+created\n"
        edit = "--- old.txt\n+++ old.txt\n@@ -1 +1 @@\n-old\n+new\n"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old, new = root / "old.txt", root / "new.txt"
            old.write_text("old\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            with patch("codeharness.tools.os.link", side_effect=OSError("hard links unavailable")):
                with patch("codeharness.tools.os.replace", side_effect=PermissionError("locked")):
                    with self.assertRaises(PermissionError):
                        registry.invoke("apply_patch", {"patch": create + edit})
                self.assertFalse(new.exists())
                self.assertEqual(old.read_text(encoding="utf-8"), "old\n")
                registry.invoke("apply_patch", {"patch": create})
            self.assertEqual(new.read_text(encoding="utf-8"), "created\n")

    def test_unified_patch_reverts_earlier_files_if_a_later_replace_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, b = root / "a.txt", root / "b.txt"
            for path in (a, b):
                path.write_text("original\n", encoding="utf-8", newline="\n")
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            original_replace = os.replace

            def replace(source, dest):
                if dest == b:
                    raise PermissionError("fixture lock")
                return original_replace(source, dest)

            patch_text = "".join(f"--- {name}\n+++ {name}\n@@ -1 +1 @@\n-original\n+changed\n" for name in (a.name, b.name))
            with patch("codeharness.tools.os.replace", side_effect=replace), self.assertRaises(PermissionError):
                registry.invoke("apply_patch", {"patch": patch_text})
            self.assertEqual([path.read_text(encoding="utf-8") for path in (a, b)], ["original\n"] * 2)

    def test_cli_disable_tool_omits_patch_from_model_schema(self):
        offered = set()

        class InspectTools:
            name = "fixture"

            def complete(self, messages, tools, max_tokens, *, timeout=None):
                offered.update(tool["function"]["name"] for tool in tools)
                return DemoModel.text("完成")

        with tempfile.TemporaryDirectory() as temp, patch("codeharness.cli.ChatModel", return_value=InspectTools()), \
                redirect_stdout(StringIO()):
            self.assertEqual(cli(["run", "查看工具", "--workspace", temp, "--model", "fixture", "--json",
                                  "--base-url", "https://fixture.invalid/v1", "--disable-tool", "apply_patch"]), 0)
        self.assertNotIn("apply_patch", offered)
        self.assertIn("edit_file", offered)

    def test_git_ignored_files_are_absent_from_list_snapshot_and_search(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            (root / ".gitignore").write_text("outputs/\n", encoding="utf-8")
            (root / "outputs").mkdir()
            (root / "outputs" / "generated.py").write_text("target = 100", encoding="utf-8")
            (root / "visible.py").write_text("target = 12", encoding="utf-8")
            workspace = Workspace(root)
            registry = Registry(workspace, Policy())
            register_workspace_tools(registry)
            self.assertEqual(registry.invoke("list_files", {})["files"], [".gitignore", "visible.py"])
            self.assertEqual(set(workspace.snapshot()), {".gitignore", "visible.py"})
            matches = registry.invoke("search", {"query": "target"})["matches"]
            self.assertEqual([row["path"] for row in matches], ["visible.py"])

    def test_regex_glob_and_limit_are_consistent_without_ripgrep(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "dist").mkdir()
            (root / "dist" / "out.py").write_text("item_99", encoding="utf-8")
            (root / "notes.txt").write_text("item_88", encoding="utf-8")
            (root / "a.py").write_text("item_01\nother\nITEM_02\n", encoding="utf-8")
            registry = Registry(Workspace(root), Policy())
            register_workspace_tools(registry)
            args = {"query": r"item_\d+", "regex": True, "glob": "*.py", "max_results": 1}
            expected = {"matches": [{"path": "a.py", "line": 1, "text": "item_01"}], "truncated": True}
            self.assertEqual(registry.invoke("search", args), expected)
            with patch("codeharness.tools.shutil.which", return_value=None):
                self.assertEqual(registry.invoke("search", args), expected)

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
