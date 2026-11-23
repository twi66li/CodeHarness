from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from codeharness.benchmark import diagnostics, main as benchmark
from codeharness.cli import main as cli
from codeharness import model_pool
from codeharness.store import Store


def settings(names=("first", "second")):
    return {"quota_as_of": "2000-01-01T00:00:00+08:00", "ledger": "quota-ledger.jsonl",
            "models": [{"name": name, "quota_tokens": 50000, "expires": "2099-01-01"} for name in names]}


ENV = {"DASHSCOPE_BASE_URL": "https://fixture.invalid/v1", "DASHSCOPE_API_KEY": "fake"}


def quota_denial(url):
    return HTTPError(url, 403, "denied", {}, BytesIO(b'{"error":{"code":"FreeTierQuotaExhausted"}}'))


def reply():
    return BytesIO(json.dumps({"choices": [{"message": {"content": "done"}}],
                               "usage": {"prompt_tokens": 8, "completion_tokens": 2}}).encode())


class ModelPoolTests(unittest.TestCase):
    def test_run_switch_counts_each_actual_model_request(self):
        sent = []

        def respond(request, timeout):
            model = json.loads(request.data)["model"]
            sent.append(model)
            if model == "first":
                raise quota_denial(request.full_url)
            return reply()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "repo"
            workspace.mkdir()
            config = root / "pool.json"
            config.write_text(json.dumps(settings()), encoding="utf-8")
            store = root / "state.sqlite3"
            with patch("os.environ", ENV), patch("codeharness.models.urlopen", side_effect=respond), \
                    redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()):
                code = cli(["run", "检查工作区", "--workspace", str(workspace), "--store", str(store), "--json",
                            "--model-pool", str(config), "--max-requests", "2"])
            self.assertEqual(code, 0, output.getvalue())
            result = json.loads(output.getvalue())
            with redirect_stdout(StringIO()) as trace:
                self.assertEqual(cli(["trace", result["session_id"], "--store", str(store), "--json"]), 0)

        requests = [event["data"]["model"] for event in json.loads(trace.getvalue())
                    if event["kind"] == "model_request"]
        self.assertEqual(sent, ["first", "second"])
        self.assertEqual(requests, sent)
        self.assertEqual(result["usage"]["requests"], 2)
        self.assertEqual(result["usage"]["input_tokens"], 8)
        self.assertEqual(result["usage"]["output_tokens"], 2)

    def test_benchmark_restarts_entire_pair_on_quota_denial(self):
        sent = []

        def respond(request, timeout):
            sent.append(json.loads(request.data)["model"])
            if sent == ["first", "first"]:
                raise quota_denial(request.full_url)
            return reply()

        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "pool.json"
            config.write_text(json.dumps(settings()), encoding="utf-8")
            output = Path(temp) / "bench"
            with patch("os.environ", ENV), patch("codeharness.models.urlopen", side_effect=respond), \
                    redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(benchmark([
                    "--mode", "model", "--task", "discount", "--variants", "both", "--allow-exec",
                    "--model-pool", str(config), "--max-requests", "1", "--max-tokens", "10000",
                    "--total-requests", "4", "--total-tokens", "40000", "--output", str(output),
                ]), 2)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))

        self.assertEqual(sent, ["first", "first", "second", "second"])
        self.assertEqual([(row["model"], row["variant"], row.get("skipped")) for row in report["cases"]], [
            ("first", "delegate", "incomplete_model_pair"), ("first", "no-delegate", "model_quota_exhausted"),
            ("second", "delegate", None), ("second", "no-delegate", None),
        ])
        self.assertEqual(report["summary_by_model"]["first"]["delegate"]["requests"], 1)
        self.assertEqual(report["summary_by_model"]["first"]["delegate"]["attempted"], 0)

    def test_ledger_import_is_idempotent_and_respects_snapshot_cap_and_expiry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "pool.json"
            data = settings()
            data["models"][0].update(expires="2027-01-01")
            data["models"][1].update(cap_tokens=30000)
            config.write_text(json.dumps(data), encoding="utf-8")
            report = root / "old.json"
            report.write_text(json.dumps({
                "model": "second", "mode": "model_evaluation",
                "cases": [{"usage": {"input_tokens": 24, "output_tokens": 6, "estimated": True}}],
            }), encoding="utf-8")
            now = lambda: datetime.fromisoformat("2026-12-31T16:00:00+00:00")
            args = ["record", "--report", str(report), "--model", "second", "--config", str(config)]
            with redirect_stdout(StringIO()):
                self.assertEqual(model_pool.main(args), 0)
                self.assertEqual(model_pool.main(args), 0)
            rows = model_pool.ModelPool(config, now=now).status()
            self.assertEqual((rows[0]["status"], rows[1]["remaining_tokens"]), ("expired", 29970))
            data["quota_as_of"] = "2027-01-01T00:00:00+08:00"
            config.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(model_pool.ModelPool(config, now=now).status()[1]["remaining_tokens"], 30000)

    def test_run_distinguishes_local_quota_generic_throttle_and_auth_denial(self):
        for case, status, cap, expected in (("local", 0, 30, ["second"]),
                                            ("throttled", 429, 50000, ["first", "first"]),
                                            ("denied", 403, 50000, ["first"])):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                sent = []

                def respond(request, timeout):
                    sent.append(json.loads(request.data)["model"])
                    if status and len(sent) == 1:
                        body = BytesIO(b'{"error":{"code":"OtherProviderError"}}')
                        raise HTTPError(request.full_url, status, "error", {"Retry-After": "0"}, body)
                    return reply()

                config = Path(temp) / ".codeharness" / "models.json"
                config.parent.mkdir()
                data = settings()
                data["models"][0]["cap_tokens"] = cap
                config.write_text(json.dumps(data), encoding="utf-8")
                with patch("os.environ", ENV), patch("codeharness.models.urlopen", side_effect=respond), \
                        redirect_stdout(StringIO()) as output:
                    code = cli(["run", "检查工作区", "--workspace", temp, "--model-pool", str(config), "--json"])
                self.assertEqual(code, 2 if case == "denied" else 0, output.getvalue())
                self.assertEqual(sent, expected)

    def test_benchmark_writes_skips_when_no_model_has_a_full_pair_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "pool.json"
            data = settings()
            for entry in data["models"]:
                entry["quota_tokens"] = 5000
            config.write_text(json.dumps(data), encoding="utf-8")
            output = Path(temp) / "bench"
            with patch("os.environ", ENV), patch("codeharness.models.urlopen") as call, redirect_stdout(StringIO()):
                self.assertEqual(benchmark([
                    "--mode", "model", "--task", "discount", "--variants", "both", "--allow-exec",
                    "--model-pool", str(config), "--max-requests", "1", "--max-tokens", "10000",
                    "--total-requests", "2", "--total-tokens", "20000", "--output", str(output),
                ]), 2)
                call.assert_not_called()
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual([row["skipped"] for row in report["cases"]], ["quota_exhausted"] * 2)

    def test_run_records_local_quota_error_without_physical_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "repo"
            workspace.mkdir()
            config = root / "pool.json"
            data = settings(("first",))
            data["models"][0]["quota_tokens"] = 1
            config.write_text(json.dumps(data), encoding="utf-8")
            store_path = root / "state.sqlite3"
            with patch("os.environ", ENV), patch("codeharness.models.urlopen") as call, redirect_stdout(StringIO()) as output:
                code = cli(["run", "检查工作区", "--workspace", str(workspace), "--store", str(store_path),
                            "--model-pool", str(config), "--json"])
            call.assert_not_called()
            result = json.loads(output.getvalue())
            self.assertEqual((code, result["status"], result["usage"]["requests"]), (2, "error", 0))
            store = Store(store_path)
            try:
                errors = [event["data"] for event in store.events(result["session_id"])
                          if event["kind"] == "model_error"]
                evidence = diagnostics(store)
            finally:
                store.close()
            self.assertEqual(len(errors), 1)
            self.assertTrue(errors[0]["preflight"])
            self.assertTrue(errors[0]["quota_exhausted"])
            self.assertEqual(evidence["model_errors"], 1)
            self.assertTrue(evidence["quota_exhausted"])
