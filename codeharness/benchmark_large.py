"""Generate deterministic, larger variants of the business benchmark repositories."""

from pathlib import PurePosixPath
from random import Random

from .benchmark_tasks import MULTI_TASKS, TASKS, Task


BASE_TASKS = (*MULTI_TASKS, next(task for task in TASKS if task.id == "invoice"))
LARGE_TASK_IDS = tuple(f"large-{task.id}" for task in BASE_TASKS)


def large_tasks(seed: int = 20261123) -> tuple[Task, ...]:
    result = []
    for index, task in enumerate(BASE_TASKS):
        random = Random(seed + index)
        files = dict(task.files)
        reference = dict(task.reference)
        modules = sorted(reference)
        for path in modules[:2]:
            stem = PurePosixPath(path).stem
            prefix = "".join(
                f"# {stem} compatibility fixture {number:04d} retains historical route and replay ordering "
                f"for batch key {random.randrange(1_000_000):06d}.\n" for number in range(950)
            ) + "\n"
            files[path] = prefix + files[path]
            reference[path] = prefix + reference[path]

        files["historical/__init__.py"] = "\"\"\"Historical rule profiles used by regression tests.\"\"\"\n"
        for number in range(96):
            stem = PurePosixPath(modules[number % len(modules)]).stem
            records = "".join(
                f"    'historical_{case:02d}': ({random.randrange(1000)}, 'archived profile for {stem} "
                f"and replay window {random.randrange(1_000_000):06d}'),\n" for case in range(28)
            )
            files[f"historical/{stem}_{number:03d}.py"] = (
                f"\"\"\"Historical {stem} rule profile {number}.\"\"\"\n\nRULES = {{\n{records}}}\n\n"
                "def lookup(name):\n    return RULES.get(name)\n"
            )
        first, last = (PurePosixPath(modules[number % len(modules)]).stem + f"_{number:03d}" for number in (0, 95))
        files["tests/test_historical_profiles.py"] = (
            f"from historical import {first}, {last}\nimport unittest\n\n\n"
            "class HistoricalProfiles(unittest.TestCase):\n"
            "    def test_known_profile_still_loads(self):\n"
            f"        for profile in ({first}, {last}):\n"
            "            self.assertEqual(len(profile.RULES), 28)\n"
            "            self.assertEqual(profile.lookup('historical_00'), profile.RULES['historical_00'])\n"
            "            self.assertIsNone(profile.lookup('missing'))\n"
        )
        prompt = task.prompt + "\n仓库包含同名历史实现和较长的业务模块。沿现有入口定位实际调用，保留已有回归行为。"
        result.append(Task(LARGE_TASK_IDS[index], prompt, files, reference, task.acceptance))
    return tuple(result)
