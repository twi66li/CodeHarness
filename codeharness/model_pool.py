"""Model selection and a shared, append-only token ledger."""

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from .models import ChatModel, ModelError, Reply


@dataclass(frozen=True)
class Quota:
    tokens: int
    expires: date
    reasoning_effort: str | None


class ModelPool:
    def __init__(self, config: Path, *, env: dict[str, str] | None = None, order: str | None = None,
                 reasoning_effort: str | None = None, switch_mid_session: bool = False, now=None):
        settings = json.loads(config.read_text(encoding="utf-8-sig"))
        try:
            self.as_of = datetime.fromisoformat(settings["quota_as_of"])
            self.zone = datetime.fromisoformat("2000-01-01T00:00:00" + settings.get("timezone_offset", "+08:00")).tzinfo
            if self.as_of.tzinfo is None or self.zone is None:
                raise ValueError("额度快照与时区需包含 UTC 偏移")
            self.ledger = config.parent / settings["ledger"]
            self.margin = float(settings.get("safety_margin", 0.1))
            self.error_codes = {code.casefold() for code in settings.get("quota_error_codes", [])}
            self.quotas = {}
            for entry in settings["models"]:
                name = entry["name"]
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or name in self.quotas:
                    raise ValueError("模型名称不合法或重复")
                tokens = min(entry["quota_tokens"], entry.get("cap_tokens", entry["quota_tokens"]))
                if type(tokens) is not int or tokens < 0:
                    raise ValueError("模型额度必须是非负整数")
                self.quotas[name] = Quota(tokens, date.fromisoformat(entry["expires"]), entry.get("reasoning_effort"))
            self.order = tuple(name.strip() for name in order.split(",")) if order else tuple(self.quotas)
            if (not self.order or len(self.order) != len(set(self.order)) or not 0 <= self.margin <= 1
                    or any(name not in self.quotas for name in self.order)):
                raise ValueError("模型池顺序或安全余量无效")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("模型池配置缺少字段或类型无效") from exc
        self.now = now or (lambda: datetime.now(self.zone))
        self.name = self.choose(0) or self.order[0]
        self.switch_mid_session = switch_mid_session
        self.quota_exhausted = False
        self.adapters = {}
        if env is not None:
            url = env.get(settings.get("base_url_env", "DASHSCOPE_BASE_URL"))
            key = env.get(settings.get("api_key_env", "DASHSCOPE_API_KEY"))
            if not url or not key:
                raise ValueError("模型池需要配置接口地址和 API Key")
            self.adapters = {name: ChatModel(name, url, key,
                reasoning_effort=reasoning_effort if reasoning_effort is not None else self.quotas[name].reasoning_effort)
                for name in self.order}

    def records(self) -> list[dict]:
        try:
            data = self.ledger.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        return [json.loads(line) for line in data.splitlines() if line.strip()]

    def record(self, name: str, input_tokens: int, output_tokens: int, *, estimated: bool = False,
               kind: str = "usage", when: datetime | None = None, source: str | None = None):
        if name not in self.quotas:
            raise ValueError("模型未出现在额度配置中")
        entry = {"time": (when or self.now()).isoformat(), "model": name, "input_tokens": input_tokens,
                 "output_tokens": output_tokens, "estimated": estimated, "kind": kind}
        if source is not None:
            entry["source"] = source
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def status(self) -> list[dict]:
        used = dict.fromkeys(self.order, 0)
        exhausted = set()
        for row in self.records():
            name = row["model"]
            if name not in used or datetime.fromisoformat(row["time"]) <= self.as_of:
                continue
            used[name] += row["input_tokens"] + row["output_tokens"]
            if row["kind"] == "exhausted":
                exhausted.add(name)
        today = self.now().astimezone(self.zone).date()
        rows = []
        for name in self.order:
            quota = self.quotas[name]
            left = max(0, quota.tokens - used[name])
            state = "expired" if today >= quota.expires else "exhausted" if name in exhausted or not left else "available"
            rows.append({"model": name, "quota_tokens": quota.tokens, "used_tokens": used[name],
                         "remaining_tokens": left, "expires": quota.expires.isoformat(), "status": state})
        return rows

    def choose(self, required: int, *, excluded=()) -> str | None:
        return next((row["model"] for row in self.status()
                     if row["model"] not in excluded and row["status"] == "available"
                     and row["remaining_tokens"] >= required * (1 + self.margin)), None)

    def pin(self, name: str):
        self.name = name
        self.switch_mid_session = False
        self.quota_exhausted = False

    def import_report(self, report: Path, name: str):
        raw = report.read_bytes()
        source = sha256(raw).hexdigest()
        if any(row.get("source") == source and row["model"] == name for row in self.records()):
            return
        data = json.loads(raw)
        if data.get("mode") != "model_evaluation":
            raise ValueError("只能导入真实模型评测报告")
        rows = [row["usage"] for row in data["cases"] if "usage" in row and
                row.get("model", data.get("model")) == name]
        if not rows:
            raise ValueError("报告中没有该模型的用量")
        self.record(name, sum(row["input_tokens"] for row in rows), sum(row["output_tokens"] for row in rows),
                    estimated=any(row.get("estimated", False) for row in rows), kind="imported", source=source,
                    when=datetime.fromtimestamp(report.stat().st_mtime, self.zone))

    def prepare_attempt(self, required: int):
        excluded = () if self.switch_mid_session else set(self.order) - {self.name}
        name = self.choose(required, excluded=excluded)
        if name is None:
            self.quota_exhausted = True
            balances = ", ".join(f"{row['model']}={row['remaining_tokens']}（{row['expires']}）" for row in self.status())
            raise ModelError(f"模型额度不足：{balances}", quota_exhausted=True, consume_output_budget=False)
        self.name = name

    def complete(self, messages: list[dict], tools: list[dict], max_tokens: int,
                 *, timeout: float | None = None) -> Reply:
        estimated_input = len(json.dumps([messages, tools], ensure_ascii=False)) // 3 + 1
        try:
            reply = self.adapters[self.name].complete(messages, tools, max_tokens, timeout=timeout)
        except ModelError as exc:
            input_tokens, output_tokens = (estimated_input, max_tokens) if exc.consume_output_budget else (0, 0)
            self.record(self.name, input_tokens, output_tokens, estimated=True)
            code = (exc.code or "").casefold()
            depleted = (exc.status == 403 and (code in self.error_codes
                        or any(part in code for part in ("quota", "freetier", "allocation")))) \
                or (exc.status == 429 and code in self.error_codes)
            if not depleted:
                raise
            self.record(self.name, 0, 0, kind="exhausted")
            self.quota_exhausted = True
            retryable = self.switch_mid_session and self.choose(estimated_input + max_tokens) is not None
            raise ModelError(str(exc), retryable=retryable, retry_after=0 if retryable else None,
                             status=exc.status, code=exc.code, quota_exhausted=True,
                             consume_output_budget=exc.consume_output_budget) from None
        self.record(self.name, reply.input_tokens, reply.output_tokens, estimated=reply.estimated)
        return reply


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CodeHarness 模型额度台账")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=Path(".codeharness/models.json"))
    sub.add_parser("status", parents=[common], help="显示额度、用量和到期状态")
    record = sub.add_parser("record", parents=[common], help="导入已有评测报告的用量")
    record.add_argument("--report", type=Path, required=True)
    record.add_argument("--model", required=True)
    mark = sub.add_parser("mark-exhausted", parents=[common], help="手动标记额度已耗尽")
    mark.add_argument("name")
    args = parser.parse_args(argv)
    try:
        pool = ModelPool(args.config)
        if args.command == "record":
            pool.import_report(args.report, args.model)
        elif args.command == "mark-exhausted":
            pool.record(args.name, 0, 0, kind="exhausted")
        print(json.dumps(pool.status(), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"模型台账错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
