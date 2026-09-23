import unittest

from python.spike_core.capability_ledger import native_capability_ledger
from python.spike_core.pi_release_qualification import (
    REQUIRED_PI_WORKFLOWS,
    qualify_pi_release,
)


_BENCHMARK_IDS = {
    workflow_id: f"benchmark-{index}"
    for index, workflow_id in enumerate(REQUIRED_PI_WORKFLOWS)
}


def _runtime_report(*, include_benchmarks=False):
    report = {
        "contract": "spike/release-runtime-qualification/v1",
        "status": "passed",
        "summary": {"total": 1, "passed": 1, "failed": 0},
        "source_snapshot_digest": "same",
        "packaged_snapshot_digest": "same",
    }
    if include_benchmarks:
        report["source"] = {"benchmarks": _benchmark_report()}
    return report


def _normalized_runtime_report():
    report = _runtime_report()
    benchmark = _benchmark_report()
    report["source"] = {
        "benchmarks": {
            "contract": benchmark["contract"],
            "status": benchmark["status"],
            "summary": benchmark["summary"],
            "cases": benchmark["benchmarks"],
        }
    }
    return report


def _benchmark_report(*, skipped=0, omit=None):
    records = [
        {"name": benchmark_id, "status": "passed"}
        for benchmark_id in _BENCHMARK_IDS.values()
        if benchmark_id != omit
    ]
    records.extend(
        {"name": f"skipped-{index}", "status": "skipped"}
        for index in range(skipped)
    )
    return {
        "contract": "spike/solver-benchmark-report/v1",
        "status": "passed",
        "summary": {"total": len(records), "passed": len(records) - skipped, "failed": 0, "skipped": skipped},
        "benchmarks": records,
    }


def _validated_ledger():
    return {
        "workflows": [
            {
                "id": workflow_id,
                "native_owner": f"spike.native.test_{index}",
                "release_state": "validated",
                "validation_state": "validated",
                "validation_evidence": [f"fixture-{index}"],
                "release_qualification": {
                    "evidence_id": f"fixture-evidence-{index}",
                    "profile_id": f"fixture-profile-{index}",
                    "artifact_uri": f"pi/fixture-evidence-{index}.json",
                    "sha256": f"{index + 1:064x}",
                },
                "release_benchmarks": [_BENCHMARK_IDS[workflow_id]],
            }
            for index, workflow_id in enumerate(REQUIRED_PI_WORKFLOWS)
        ],
    }


class PiReleaseQualificationTests(unittest.TestCase):
    def test_current_capability_ledger_blocks_deployable_pi_claim(self):
        report = qualify_pi_release(_runtime_report(), _benchmark_report(), native_capability_ledger())
        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["deployable"])
        self.assertIn("workflow.pi.ac_rlcg", report["blocked_checks"])
        self.assertIn("workflow.circuit.field_circuit_cosimulation", report["blocked_checks"])
        check = next(item for item in report["checks"] if item["id"] == "workflow.pi.ac_rlcg")
        self.assertTrue(check["evidence"]["blocking_reasons"])
        self.assertIn("Release state", check["detail"])

    def test_missing_runtime_qualification_blocks_release(self):
        report = qualify_pi_release(None, _benchmark_report(), _validated_ledger())
        self.assertIn("runtime.packaged_parity", report["blocked_checks"])

    def test_all_validated_workflows_and_gates_pass(self):
        report = qualify_pi_release(_runtime_report(), _benchmark_report(), _validated_ledger())
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["deployable"])
        self.assertEqual(report["summary"]["blocked"], 0)
        workflow_checks = [item for item in report["checks"] if item["id"].startswith("workflow.")]
        self.assertTrue(all(item["evidence"]["blocking_reasons"] == [] for item in workflow_checks))

    def test_skipped_benchmark_blocks_release(self):
        report = qualify_pi_release(_runtime_report(), _benchmark_report(skipped=1), _validated_ledger())
        self.assertIn("validation.native_benchmarks", report["blocked_checks"])

    def test_missing_workflow_specific_benchmark_blocks_that_workflow(self):
        missing = _BENCHMARK_IDS["pi.ac_rlcg"]
        report = qualify_pi_release(
            _runtime_report(),
            _benchmark_report(omit=missing),
            _validated_ledger(),
        )
        self.assertIn("workflow.pi.ac_rlcg", report["blocked_checks"])
        check = next(item for item in report["checks"] if item["id"] == "workflow.pi.ac_rlcg")
        self.assertIn(missing, check["detail"])

    def test_qualified_runtime_benchmarks_are_used_when_no_override_is_given(self):
        report = qualify_pi_release(
            _runtime_report(include_benchmarks=True),
            None,
            _validated_ledger(),
        )
        self.assertEqual(report["status"], "passed")
        check = next(item for item in report["checks"] if item["id"] == "validation.native_benchmarks")
        self.assertEqual(check["evidence"]["source"], "qualified_runtime_snapshot")

    def test_normalized_runtime_cases_satisfy_workflow_benchmark_evidence(self):
        report = qualify_pi_release(
            _normalized_runtime_report(),
            None,
            _validated_ledger(),
        )
        self.assertEqual(report["status"], "passed")
        workflow_checks = [item for item in report["checks"] if item["id"].startswith("workflow.")]
        self.assertTrue(all(
            all(status == "passed" for status in item["evidence"]["benchmark_status"].values())
            for item in workflow_checks
        ))


if __name__ == "__main__":
    unittest.main()
