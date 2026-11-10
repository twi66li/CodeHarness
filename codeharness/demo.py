"""Deterministic integration fixture. This adapter does NOT call an AI model."""

import json
from pathlib import Path
import uuid

from .models import Reply


BUGGY = "def total(prices, discount):\n    return sum(prices) - discount\n"
TEST = '''import unittest
from basket import total

class BasketTests(unittest.TestCase):
    def test_percentage_discount(self):
        self.assertAlmostEqual(total([100, 50], 0.2), 120)

    def test_no_discount(self):
        self.assertEqual(total([10, 20], 0), 30)
'''


def create_demo(path: Path):
    # A demo always gets a new directory; it never replaces an existing project.
    path.mkdir(parents=True, exist_ok=False)
    (path / "basket.py").write_text(BUGGY, encoding="utf-8")
    (path / "tests").mkdir()
    (path / "tests" / "test_basket.py").write_text(TEST, encoding="utf-8")


class DemoModel:
    name = "offline-demo"

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int) -> Reply:
        available = {tool["function"]["name"] for tool in tools}
        outputs = []
        for message in messages:
            if message["role"] == "tool":
                outputs.append(json.loads(message["content"]))
        if "delegate" not in available:
            if not outputs:
                return self.call("read_file", {"path": "basket.py"})
            return self.text("basket.py 的 total 将百分比折扣直接相减；应对总价乘以 (1 - discount)。")
        calls = [call["function"]["name"] for m in messages for call in m.get("tool_calls", [])]
        if not calls:
            return self.call("delegate", {"task": "只读检查 basket.py，指出折扣计算问题并给出文件依据。"})
        if calls[-1] == "delegate":
            return self.call("read_file", {"path": "basket.py"})
        if calls[-1] == "read_file":
            return self.call("run_tests", {})
        if calls[-1] == "run_tests" and "edit_file" not in calls:
            read = next(o["output"] for o in outputs if o.get("ok") and "sha256" in o.get("output", {}))
            return self.call("edit_file", {"path": "basket.py", "old_text": "return sum(prices) - discount",
                "new_text": "return sum(prices) * (1 - discount)", "expected_sha256": read["sha256"]})
        if calls[-1] == "edit_file":
            return self.call("run_tests", {})
        passed = outputs[-1].get("output", {}).get("passed", False)
        return self.text("已修复 basket.py 的折扣计算，两个测试通过。" if passed else "验证未通过，请检查工具返回。")

    @staticmethod
    def call(name: str, arguments: dict) -> Reply:
        return Reply({"role": "assistant", "content": "", "tool_calls": [{
            "id": uuid.uuid4().hex[:16], "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}]}, 100, 40, True)

    @staticmethod
    def text(content: str) -> Reply:
        return Reply({"role": "assistant", "content": content}, 100, 30, True)
