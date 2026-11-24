import ast
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from codeharness.tools import Policy, Registry, Workspace, register_workspace_tools


FIXTURES = Path(__file__).parent / "fixtures" / "real_patches"


class RealPatchTests(unittest.TestCase):
    def test_all_real_patches_apply_and_leave_valid_python(self):
        metadata_files = sorted(FIXTURES.glob("*/meta.json"))
        self.assertEqual(len(metadata_files), 27)
        checked = 0
        for metadata in metadata_files:
            with self.subTest(case=metadata.parent.name), TemporaryDirectory() as temp:
                case = json.loads(metadata.read_text(encoding="utf-8"))
                self.assertIsNone(case["skip_reason"])
                root = Path(temp)
                shutil.copytree(metadata.parent / "files", root, dirs_exist_ok=True)
                registry = Registry(Workspace(root), Policy(allow_write=True))
                register_workspace_tools(registry)
                patch = (metadata.parent / "patch.diff").read_text(encoding="utf-8")
                result = registry.invoke("apply_patch", {"patch": patch})
                for change in result["files"]:
                    path = root / change["path"]
                    if path.suffix == ".py" and change["after_sha256"] is not None:
                        ast.parse(path.read_bytes(), filename=change["path"])
                        checked += 1
        self.assertEqual(checked, 80)


if __name__ == "__main__":
    unittest.main()
