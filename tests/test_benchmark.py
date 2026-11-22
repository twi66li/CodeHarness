from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from codeharness.benchmark import acceptance, diagnostics, main, run_suite
from codeharness.benchmark_tasks import MULTI_TASKS, TASKS
from codeharness.demo import DemoModel
from codeharness.models import ModelError
from codeharness.runtime import Limits
from codeharness.store import Store


class TextOnlyModel:
    name = "test-double"

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        return DemoModel.text("完成")


class PatchModel:
    name = "scripted-test-double"

    def complete(self, messages, tools, max_tokens, *, timeout=None):
        results = [m for m in messages if m["role"] == "tool"]
        if not results:
            return DemoModel.call("read_file", {"path": "pricing.py"})
        if len(results) == 1:
            read = json.loads(results[-1]["content"])["output"]
            return DemoModel.call("edit_file", {"path": "pricing.py", "old_text": "return total - rate",
                "new_text": "return total * (1 - rate)", "expected_sha256": read["sha256"]})
        return DemoModel.text("完成")


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_disables_patch_tool_for_the_actual_case(self):
        offered = set()

        class InspectTools(TextOnlyModel):
            def complete(self, messages, tools, max_tokens, *, timeout=None):
                offered.update(tool["function"]["name"] for tool in tools)
                return super().complete(messages, tools, max_tokens, timeout=timeout)

        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:1], Path(temp) / "bench", model=InspectTools(),
                               total_requests=12, total_tokens=24000, disabled_tools=("apply_patch",))
        self.assertNotIn("apply_patch", offered)
        self.assertIn("edit_file", offered)
        self.assertEqual(report["disabled_tools"], ["apply_patch"])

    def test_estimate_error_uses_only_measured_pairs_with_estimates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "state.sqlite3")
            try:
                sid = store.create(root, "fixture")
                for request, usage in (({}, {"input_tokens": 1}),
                                       ({"estimated_input": 90}, {"input_tokens": 100}),
                                       ({"estimated_input": 120}, {"input_tokens": 100}),
                                       ({"estimated_input": 500}, {"input_tokens": 1, "estimated": True})):
                    store.append(sid, "model_request", request)
                    store.append(sid, "usage", usage)
                self.assertAlmostEqual(diagnostics(store)["estimate_error"], 0.15)
            finally:
                store.close()

    def test_report_counts_cached_input_tokens(self):
        class CachedModel(TextOnlyModel):
            def complete(self, *args, **kwargs):
                reply = super().complete(*args, **kwargs)
                reply.input_tokens = 20
                reply.cached_tokens = 8
                return reply

        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:1], Path(temp) / "bench", model=CachedModel(),
                               total_requests=12, total_tokens=24000)
        self.assertEqual(report["cases"][0]["cache_hit_ratio"], 0.4)
        self.assertEqual(report["summary"]["delegate"]["cached_tokens"], 8)
        self.assertEqual(report["summary"]["delegate"]["cache_hit_ratio"], 0.4)

    def test_model_cli_reads_dashscope_file_with_multiline_model_list(self):
        with tempfile.TemporaryDirectory() as temp, patch("os.environ", {}), \
                patch("codeharness.benchmark.ChatModel") as model, \
                patch("codeharness.benchmark.run_suite") as run, redirect_stdout(StringIO()):
            env_file = Path(temp) / ".env"
            env_file.write_text(
                "MODEL='[\n    \"glm-5.3\",\n    \"qwen3.8-flash\"\n]'\n"
                "DASHSCOPE_BASE_URL=https://fixture.invalid/v1\n"
                "DASHSCOPE_API_KEY='fake-dashscope-key'\n",
                encoding="utf-8",
            )
            run.return_value = {"mode": "model_evaluation", "summary": {}, "cases": [{"success": True}]}
            self.assertEqual(main([
                "--mode", "model", "--task", "discount", "--model", "glm-5.3",
                "--env-file", str(env_file), "--allow-exec", "--output-tokens", "4096", "--reasoning-effort", "low",
                "--total-requests", "12", "--total-tokens", "24000",
            ]), 0)
            model.assert_called_once_with("glm-5.3", "https://fixture.invalid/v1", "fake-dashscope-key",
                                          reasoning_effort="low")
            self.assertEqual(run.call_args.kwargs["limits"].output_tokens, 4096)
            self.assertNotIn("DASHSCOPE_API_KEY", os.environ)

    def test_cli_can_select_single_task_without_running_model(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(StringIO()) as printed:
            output = Path(temp) / "bench"
            self.assertEqual(main(["--mode", "fixtures", "--task", "discount", "--output", str(output)]), 0)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["task_count"], 1)
            self.assertEqual(report["cases"][0]["task"], "discount")
            self.assertEqual(report["summary"]["reference"]["requests"], 0)
            self.assertEqual(json.loads(printed.getvalue())["mode"], "reference_fixture_validation")

    def test_acceptance_does_not_inherit_dashscope_credentials(self):
        with patch("os.environ", {**os.environ, "DASHSCOPE_API_KEY": "FAKE_FIXTURE_KEY"}), \
                patch("codeharness.benchmark.subprocess.run") as launch:
            launch.return_value = subprocess.CompletedProcess([], 0, "", "")
            self.assertTrue(acceptance(Path.cwd(), Path("acceptance.py"))["passed"])
            self.assertNotIn("DASHSCOPE_API_KEY", launch.call_args.kwargs["env"])

    def test_diagnostics_summarize_model_retry_and_tool_error(self):
        class ErrorModel(TextOnlyModel):
            calls = 0

            def complete(self, messages, tools, max_tokens, *, timeout=None):
                self.calls += 1
                if self.calls == 1:
                    raise ModelError("HTTP 429", retryable=True, retry_after=0)
                if self.calls == 2:
                    return DemoModel.call("read_file", {"path": "missing.py"})
                return DemoModel.text("结束")

        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:1], Path(temp) / "bench", model=ErrorModel(),
                               limits=Limits(max_requests=3, max_tokens=30000),
                               total_requests=3, total_tokens=30000)
        evidence = report["cases"][0]["diagnostics"]
        self.assertEqual(evidence["model_errors"], 1)
        self.assertEqual(evidence["model_retries"], 1)
        self.assertEqual(evidence["tool_error_counts"], {"read_file": 1})
        self.assertEqual(report["summary"]["delegate"]["tool_errors"], 1)

    def test_all_reference_fixtures_have_failing_baseline_and_passing_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "bench"
            report = run_suite(TASKS, output)
            self.assertEqual(report["mode"], "reference_fixture_validation")
            self.assertEqual(len(TASKS), 12)
            self.assertEqual(report["summary"]["reference"]["passed"], 12)
            self.assertEqual(report["summary"]["reference"]["requests"], 0)
            for row in report["cases"]:
                self.assertFalse(row["baseline"]["passed"])
                self.assertTrue(row["acceptance"]["passed"])
                workspace = output / row["workspace"]
                self.assertFalse((workspace / "acceptance.py").exists())
                public = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                                        cwd=workspace, capture_output=True, timeout=15)
                self.assertEqual(public.returncode, 0, (row["task"], public.stdout, public.stderr))
            self.assertEqual(json.loads((output / "report.json").read_text(encoding="utf-8")), report)

    def test_multi_module_fixtures_have_failing_baseline_and_passing_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "multi"
            report = run_suite(MULTI_TASKS, output)
            self.assertEqual(len(MULTI_TASKS), 3)
            self.assertEqual(report["summary"]["reference"]["passed"], 3)
            for task, row in zip(MULTI_TASKS, report["cases"]):
                self.assertGreaterEqual(len(task.files), 10)
                self.assertFalse(row["baseline"]["passed"])
                self.assertTrue(row["acceptance"]["passed"])
                workspace = output / row["workspace"]
                public = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                                        cwd=workspace, capture_output=True, timeout=15)
                self.assertEqual(public.returncode, 0, (row["task"], public.stdout, public.stderr))

    def test_diagnostics_count_delegate_calls(self):
        class DelegateOnceModel:
            name = "delegate-test-double"

            def complete(self, messages, tools, max_tokens, *, timeout=None):
                names = {t["function"]["name"] for t in tools}
                if "delegate" not in names:
                    return DemoModel.text("子任务调查结束")
                has_tool = any(m["role"] == "tool" for m in messages)
                if not has_tool:
                    return DemoModel.call("delegate", {"task": "只读检查"})
                return DemoModel.text("主任务结束")

        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:1], Path(temp) / "bench", model=DelegateOnceModel(),
                               limits=Limits(max_requests=4, max_tokens=30000),
                               total_requests=4, total_tokens=30000)
        self.assertEqual(report["cases"][0]["diagnostics"]["delegate_calls"], 1)
        self.assertEqual(report["summary"]["delegate"]["delegate_calls"], 1)

    def test_independent_success_is_not_agent_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:1], Path(temp) / "bench", model=PatchModel(),
                               limits=Limits(max_requests=3, max_tokens=30000),
                               total_requests=3, total_tokens=30000)
        row = report["cases"][0]
        self.assertTrue(row["success"])
        self.assertEqual(row["agent_status"], "unverified")
        self.assertEqual(row["usage"]["requests"], 3)

    def test_paired_comparison_and_aggregate_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:2], Path(temp) / "bench", model=TextOnlyModel(),
                               limits=Limits(max_requests=1, max_tokens=10000),
                               variants=("delegate", "no-delegate"), total_requests=2, total_tokens=20000)
        self.assertEqual(len(report["cases"]), 4)
        self.assertEqual([row["agent_status"] for row in report["cases"][:2]], ["completed", "completed"])
        self.assertFalse(any(row["success"] for row in report["cases"][:2]))
        self.assertEqual([row["skipped"] for row in report["cases"][2:]], ["total_budget", "total_budget"])
        self.assertEqual(report["summary"]["delegate"]["requests"], 1)
        self.assertEqual(report["summary"]["no-delegate"]["requests"], 1)

    def test_model_evaluation_requires_aggregate_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "bench"
            with self.assertRaisesRegex(ValueError, "总请求"):
                run_suite(TASKS[:1], output, model=TextOnlyModel())
            self.assertFalse(output.exists())

    def test_denied_model_access_stops_entire_suite(self):
        class DeniedModel(TextOnlyModel):
            calls = 0

            def complete(self, messages, tools, max_tokens, *, timeout=None):
                self.calls += 1
                raise ModelError("HTTP 401", access_denied=True)

        model = DeniedModel()
        with tempfile.TemporaryDirectory() as temp:
            report = run_suite(TASKS[:2], Path(temp) / "bench", model=model,
                               limits=Limits(max_requests=1, max_tokens=10000),
                               variants=("delegate", "no-delegate"), total_requests=4, total_tokens=40000)
        self.assertEqual(model.calls, 1)
        self.assertTrue(report["cases"][0]["model_access_denied"])
        self.assertEqual([row["skipped"] for row in report["cases"][1:]], ["model_access_denied"] * 3)


if __name__ == "__main__":
    unittest.main()
