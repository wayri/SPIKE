"""Focused tests for the bounded PI batch report normalization contract."""

from __future__ import annotations

import unittest

from python.spike_core.batch_report import BatchReportError, normalize_pi_batch_report


def _result(mode: str, *, status: str = "completed", summary=None, networks=None, issues=None):
    return {
        "contract": "spike/analysis-result/v1",
        "status": status,
        "mode": mode,
        "model_status": "approximate",
        "summary": {"net_names": [f"{mode.upper()}_NET"], **(summary or {})},
        "networks": networks or {},
        "issues": issues or [],
        "provenance": {"solver": f"spike.{mode}", "formulation": mode},
    }


class BatchReportTests(unittest.TestCase):
    def test_normalizes_mixed_dc_ac_and_transient_jobs(self):
        batch = {
            "contract": "spike/analysis-batch-result/v1",
            "status": "completed",
            "results": [
                {"index": 0, "id": "dc", "result": _result("dc", summary={"max_voltage_drop_v": 0.012, "total_power_loss_w": 1.25})},
                {"index": 1, "id": "ac", "result": _result("ac", networks={"parasitics": [{"impedance": [{"magnitude_ohm": 0.02}, {"magnitude_ohm": 0.12}]}]})},
                {"index": 2, "id": "tran", "result": _result("transient", summary={"peak_voltage_v": 12.3, "saved_frames": 42})},
            ],
        }

        report = normalize_pi_batch_report(batch)

        self.assertEqual(report["contract"], "spike/pi-batch-report-data/v1")
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["totals"]["dc_jobs"], 1)
        self.assertEqual(report["totals"]["ac_jobs"], 1)
        self.assertEqual(report["totals"]["transient_jobs"], 1)
        self.assertEqual(report["totals"]["total_power_loss_w"], 1.25)
        self.assertEqual(report["jobs"][1]["metrics"]["impedance_min_ohm"], 0.02)
        self.assertEqual(report["jobs"][1]["metrics"]["impedance_max_ohm"], 0.12)
        self.assertEqual(report["jobs"][2]["metrics"]["saved_frames"], 42.0)

    def test_retains_blocked_and_failed_jobs_as_reportable_issues(self):
        batch = {
            "contract": "spike/analysis-batch-result/v1",
            "status": "failed",
            "results": [
                {"index": 0, "id": "blocked", "result": _result("dc", status="blocked", issues=[{"code": "SPIKE-BE-VAL-1", "severity": "error", "message": "No source."}])},
                {"index": 1, "id": "failed", "error": "Worker exited unexpectedly"},
            ],
        }

        report = normalize_pi_batch_report(batch)

        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["totals"]["blocked"], 1)
        self.assertEqual(report["totals"]["failed"], 1)
        self.assertEqual(report["jobs"][1]["mode"], "unknown")
        self.assertEqual(report["issues"][1]["code"], "SPIKE-REPORT-BATCH-JOB-FAILED")

    def test_fails_closed_for_malformed_input(self):
        with self.assertRaises(BatchReportError):
            normalize_pi_batch_report({"contract": "spike/analysis-batch-result/v1", "results": []})
        with self.assertRaises(BatchReportError):
            normalize_pi_batch_report({
                "contract": "spike/analysis-batch-result/v1",
                "results": [{"id": "invalid", "result": _result("dc", summary={"max_voltage_drop_v": float("nan")})}],
            })
        with self.assertRaises(BatchReportError):
            normalize_pi_batch_report({
                "contract": "spike/analysis-batch-result/v1",
                "results": [{"id": "invalid", "result": _result("rf")}],
            })


if __name__ == "__main__":
    unittest.main()
