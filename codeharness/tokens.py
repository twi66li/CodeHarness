"""Small token estimator shared by transport, quota and runtime budgets."""

import json
from math import ceil


def estimate(text: str) -> int:
    ascii_count = sum(char.isascii() for char in text)
    return (ascii_count + 3) // 4 + len(text) - ascii_count


def estimate_json(value) -> int:
    return estimate(json.dumps(value, ensure_ascii=False))


class Calibrator:
    def __init__(self):
        self.ratio = 1.0

    def adjust(self, estimate: int) -> int:
        return ceil(estimate * self.ratio)

    def observe(self, estimate: int, actual: int):
        if estimate > 0 and actual > 0:
            sample = min(3.0, max(0.5, actual / estimate))
            self.ratio = 0.7 * self.ratio + 0.3 * sample
