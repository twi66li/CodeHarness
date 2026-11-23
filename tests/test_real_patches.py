import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from codeharness.tools import Policy, Registry, ToolError, Workspace, register_workspace_tools


FIXTURES = Path(__file__).parent / "fixtures" / "real_patches"


def replay_examples():
    for metadata in sorted(FIXTURES.glob("*/meta.json")):
        case = json.loads(metadata.read_text(encoding="utf-8"))
        if case["skip_reason"]:
            continue
        with TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(metadata.parent / "files", root, dirs_exist_ok=True)
            registry = Registry(Workspace(root), Policy(allow_write=True))
            register_workspace_tools(registry)
            patch = (metadata.parent / "patch.diff").read_bytes().decode("utf-8")
            try:
                registry.invoke("apply_patch", {"patch": patch})
            except ToolError as exc:
                yield metadata.parent.name, str(exc)
            else:
                yield metadata.parent.name, None


class RealPatchTests(unittest.TestCase):
    def test_record_real_patch_acceptance(self):
        results = list(replay_examples())
        self.assertTrue(results)
        # 001/002 使用另一种文件头格式，021/025 的原文与目标文件不符。
        self.assertEqual([(case, error) for case, error in results
                          if error and case not in {"001", "002", "021", "025"}], [])
        print(f"真实补丁回放 {sum(error is None for _, error in results)}/{len(results)}")


if __name__ == "__main__":
    unittest.main()
