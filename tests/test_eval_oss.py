import unittest

from codeharness.eval_oss import compute_review_metrics, extract_json_payload, load_manifest, parse_pytest_nodes


class EvalOssTests(unittest.TestCase):
    def test_manifest_has_12_fix_and_8_review_unique_tasks(self):
        manifest = load_manifest()
        fix_ids = [t["id"] for t in manifest["fix_tasks"]]
        review_ids = [t["id"] for t in manifest["review_tasks"]]
        self.assertEqual(len(fix_ids), 12)
        self.assertEqual(len(review_ids), 8)
        self.assertEqual(len(set(fix_ids)), 12)
        self.assertEqual(len(set(review_ids)), 8)

    def test_parse_pytest_nodes_splits_passed_and_failed(self):
        sample = (
            "testing/test_a.py::test_ok PASSED [ 50%]\n"
            "testing/test_a.py::test_bug[case-1] FAILED [100%]\n"
            "1 failed, 1 passed in 0.12s\n"
        )
        passed, failed = parse_pytest_nodes(sample)
        self.assertEqual(passed, ["testing/test_a.py::test_ok"])
        self.assertEqual(failed, ["testing/test_a.py::test_bug[case-1]"])

    def test_extract_json_payload_handles_fenced_and_prose_wrapped_json(self):
        self.assertEqual(extract_json_payload('分析如下：\n```json\n[{"file": "a.py"}]\n```'), [{"file": "a.py"}])
        self.assertEqual(extract_json_payload('Result: {"verdicts": [{"is_true_positive": true}]}'),
                         {"verdicts": [{"is_true_positive": True}]})

    def test_compute_review_metrics_precision_recall_f1(self):
        cases = [
            {"findings": [{"a": 1}, {"a": 2}, {"a": 3}], "ground_truth": [{"g": 1}], "true_positives": 2, "gt_hits": 1},
            {"findings": [{"a": 4}], "ground_truth": [{"g": 2}], "true_positives": 1, "gt_hits": 0},
        ]
        m = compute_review_metrics(cases)
        self.assertEqual(m["total_findings"], 4)
        self.assertEqual(m["true_positives"], 3)
        self.assertEqual(m["false_positives"], 1)
        self.assertAlmostEqual(m["precision"], 0.75)
        self.assertAlmostEqual(m["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
