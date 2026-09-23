from pathlib import Path
import unittest
from unittest.mock import patch

from python.spikes.wave1_benchmark import (
    CASE_CONTRACT,
    REPORT_CONTRACT,
    THREAD_COUNTS,
    _peak_working_set_bytes,
    _worker,
    run_wave1_benchmarks,
    wave1_cases,
)


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "build-spikes-hybrid" / "spikes_c_api.dll"


class Wave1BenchmarkTests(unittest.TestCase):
    def test_versioned_corpus_has_scale_failure_and_converter_classes(self):
        cases = wave1_cases()
        self.assertEqual(len(cases), 5)
        self.assertEqual(len({case.case_id for case in cases}), len(cases))
        self.assertEqual({case.size_class for case in cases}, {"small", "medium", "large"})
        self.assertTrue(any(case.expected_failure for case in cases))
        self.assertTrue(any(case.category == "switching_converter" for case in cases))
        self.assertTrue(all(case.to_dict()["contract"] == CASE_CONTRACT for case in cases))

    def test_peak_memory_probe_is_explicit_even_when_unavailable(self):
        peak, scope = _peak_working_set_bytes()
        self.assertTrue(peak is None or peak > 0)
        self.assertTrue(scope)

    @unittest.skipUnless(LIBRARY.is_file(), "owned C ABI library is unavailable")
    def test_expected_failure_is_bounded_and_counts_as_qualified(self):
        result = _worker(
            LIBRARY, "robustness.singular_expected_failure", threads=1,
            repetitions=1,
        )
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["observations"][0]["status"], "singular")
        self.assertTrue(result["observations"][0]["expected_failure_observed"])
        self.assertIsNotNone(result["peak_working_set_bytes"])

    @unittest.skipUnless(LIBRARY.is_file(), "owned C ABI library is unavailable")
    def test_converter_records_dead_time_parasitics_and_model_limits(self):
        result = _worker(
            LIBRARY, "converter.deadtime_parasitic_buck", threads=1,
            repetitions=0,
        )
        observation = result["observations"][0]
        self.assertEqual(result["status"], "passed")
        self.assertGreater(observation["dead_time_s"]["high_to_low"], 0)
        self.assertIn("inductor_dcr_ohm", observation["parasitics"])
        self.assertGreaterEqual(len(observation["model_limits"]), 4)

    @unittest.skipUnless(LIBRARY.is_file(), "owned C ABI library is unavailable")
    def test_report_fails_closed_when_any_thread_route_fails(self):
        def fake_launch(_library, case, threads, _repetitions, _timeout):
            failed = case.case_id == "sparse.large_ladder" and threads == 4
            return {
                "contract": "spikes/wave1-worker-result/v1",
                "case_id": case.case_id,
                "threads": threads,
                "status": "failed" if failed else "passed",
                "peak_working_set_bytes": 1024,
            }

        with patch("python.spikes.wave1_benchmark._launch_worker", side_effect=fake_launch):
            report = run_wave1_benchmarks(LIBRARY, repetitions=1)
        self.assertEqual(report["contract"], REPORT_CONTRACT)
        self.assertEqual(report["status"], "failed")
        self.assertFalse(report["accuracy_gate_passed"])
        self.assertFalse(report["performance_claim_eligible"])
        medium = next(item for item in report["cases"] if item["case"]["case_id"] == "sparse.medium_ladder")
        self.assertEqual([run["threads"] for run in medium["thread_runs"]], list(THREAD_COUNTS))


if __name__ == "__main__":
    unittest.main()
