"""Generate deterministic, larger variants of the business benchmark repositories."""

import ast
from pathlib import PurePosixPath
from random import Random

from .benchmark_tasks import MULTI_TASKS, TASKS, Task


BASE_TASKS = (*MULTI_TASKS, next(task for task in TASKS if task.id == "invoice"))
LARGE_TASK_IDS = tuple(f"large-{task.id}" for task in BASE_TASKS)
HISTORICAL_CASES = {
    "order-pipeline": ("app/coupons.py", "profile.discount_cents(100, None), 0"),
    "rbac-gateway": ("app/policies.py", "profile.evaluate(set(), [], 'orders', 'read'), False"),
    "ledger-reconcile": ("app/reconcile.py", "profile.reconcile({}, [{'ref': 'external', 'amount': 1}]), []"),
    "invoice": ("money.py", "profile.cents(Decimal('1.239')), Decimal('1.23')"),
}


def batch_rules(random: Random) -> tuple[str, list[int]]:
    functions, names, adjustments = [], [], []
    for number in range(84):
        name = f"batch_rule_{number:03d}"
        threshold = random.randrange(100, 1000)
        adjustment = random.randrange(1, 100)
        names.append(name)
        adjustments.append(adjustment)
        functions.append(
            f"def {name}(record):\n"
            "    amount = record['amount']\n"
            "    if record.get('cancelled'):\n"
            "        return 0\n"
            f"    if amount < {threshold}:\n"
            "        return amount\n"
            "    if record.get('priority'):\n"
            f"        return amount + {adjustment}\n"
            f"    return amount - {adjustment}\n\n\n"
        )
    return (
        "\n\n\n" + "".join(functions)
        + "BATCH_RULES = (\n" + "".join(f"    {name},\n" for name in names) + ")\n\n\n"
        + "def batch_adjustments(record):\n    return [rule(record) for rule in BATCH_RULES]\n",
        adjustments,
    )


def insert_batch_rules(source: str, rules: str) -> str:
    imports_end = max((node.end_lineno for node in ast.parse(source).body
                       if isinstance(node, (ast.Import, ast.ImportFrom))), default=0)
    lines = source.splitlines(keepends=True)
    return "".join(lines[:imports_end]) + rules + "\n\n" + "".join(lines[imports_end:])


def large_tasks(seed: int = 20261123) -> tuple[Task, ...]:
    result = []
    for index, task in enumerate(BASE_TASKS):
        random = Random(seed + index)
        files = dict(task.files)
        reference = dict(task.reference)
        modules = sorted(reference)
        long_modules = []
        for path in modules[:2]:
            rules, adjustments = batch_rules(random)
            files[path] = insert_batch_rules(files[path], rules)
            reference[path] = insert_batch_rules(reference[path], rules)
            long_modules.append((path.removesuffix(".py").replace("/", "."), adjustments))

        files["historical/__init__.py"] = "\"\"\"Historical rule profiles used by regression tests.\"\"\"\n"
        historical_path, historical_assertion = HISTORICAL_CASES[task.id]
        historical_import = ""
        for number in range(96):
            path = modules[number % len(modules)]
            stem = PurePosixPath(path).stem
            module_name = f"{stem}_{number:03d}"
            if path == historical_path and not historical_import:
                historical_import = module_name
            records = "".join(
                f"    'historical_{case:02d}': ({random.randrange(1000)}, 'archived profile for {stem} "
                f"and replay window {random.randrange(1_000_000):06d}'),\n" for case in range(40)
            )
            files[f"historical/{module_name}.py"] = (
                f"\"\"\"Historical {stem} rule profile {number}.\"\"\"\n\n{task.files[path]}\nRULES = {{\n{records}}}\n\n"
                "def lookup(name):\n    return RULES.get(name)\n"
            )
        imports = "".join(f"from {module} import batch_adjustments as rules_{index}\n"
                          for index, (module, _) in enumerate(long_modules))
        profiles = "".join(f"            (rules_{index}, {adjustments!r}),\n"
                           for index, (_, adjustments) in enumerate(long_modules))
        files["tests/test_batch_profiles.py"] = (
            "from decimal import Decimal\n"
            "import unittest\n"
            + imports + f"from historical import {historical_import} as profile\n\n\n"
            "class BatchProfiles(unittest.TestCase):\n"
            "    def test_historical_behavior(self):\n"
            f"        self.assertEqual({historical_assertion})\n"
            "        self.assertEqual(profile.lookup('historical_00'), profile.RULES['historical_00'])\n\n"
            "    def test_batch_adjustments(self):\n"
            "        for rules, offsets in (\n" + profiles + "        ):\n"
            "            self.assertEqual(rules({'amount': 10, 'cancelled': True}), [0] * len(offsets))\n"
            "            self.assertEqual(rules({'amount': 10}), [10] * len(offsets))\n"
            "            self.assertEqual(rules({'amount': 1000}), [1000 - offset for offset in offsets])\n"
            "            self.assertEqual(rules({'amount': 1000, 'priority': True}), [1000 + offset for offset in offsets])\n"
        )
        if task.id == "invoice":
            prompt = "发票总价必须包含运费并使用 Decimal。保留现有总价与分币舍入接口，两处均使用 ROUND_HALF_UP，负金额也适用。"
        else:
            prompt = f"修复以下业务规则，并运行测试确认现有行为保持正常：{task.prompt.split('：', 1)[1]}"
        result.append(Task(LARGE_TASK_IDS[index], prompt, files, reference, task.acceptance))
    return tuple(result)
