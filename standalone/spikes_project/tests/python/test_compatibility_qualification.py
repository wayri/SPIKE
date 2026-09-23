"""Real native evidence tests; never substitute a reference engine for C++."""
import os
import unittest

from python.spikes.compatibility_qualification import run_deck_qualification, _compare_vectors


class DeckQualificationTests(unittest.TestCase):
    def test_reference_interpolation_and_coverage(self):
        report = _compare_vectors([0, .5, 1], [0, 1, 2], [.1, 1], [.2, 2], 1e-12)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["compared_points"], 2)
        self.assertEqual(report["excluded_native_times_s"], [0])
        self.assertEqual(_compare_vectors([0, 1, 2], [0, 1, 2], [0, 1], [0, 1], 1e-12)["status"], "failed")
        self.assertEqual(_compare_vectors([0], [2], [0], [1], .1)["status"], "failed")

    def test_invalid_reference_trace_rejected(self):
        for times, values in (([], []), ([0, 0], [1, 1]), ([0], [float("nan")]), ([0, 1], [1])):
            with self.subTest(times=times), self.assertRaises(ValueError):
                _compare_vectors([0], [0], times, values, 1e-6)

    def test_repetition_bounds(self):
        for value in (True, 0, 21, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                run_deck_qualification("does-not-exist", repetitions=value)

    @unittest.skipUnless(os.environ.get("SPIKES_TEST_LIBRARY") and os.environ.get("SPIKES_TEST_NGSPICE"),
                         "SPIKES_TEST_LIBRARY and SPIKES_TEST_NGSPICE required")
    def test_actual_reference_traces(self):
        report = run_deck_qualification(os.environ["SPIKES_TEST_LIBRARY"], repetitions=1,
                                        ngspice=os.environ["SPIKES_TEST_NGSPICE"])
        self.assertEqual(report["status"], "passed", [(c["case_id"], c.get("reference", {}).get("maximum_absolute_error"),
                                                      c.get("reference", {}).get("error")) for c in report["cases"]])
        self.assertEqual(report["reference_engine"]["status"], "passed")
        for case in report["cases"]:
            self.assertGreater(case["reference"]["compared_points"], 0)
            self.assertTrue(case["reference"]["native_trace"]["values"])
            self.assertTrue(case["reference"]["reference_trace"]["values"])

    @unittest.skipUnless(os.environ.get("SPIKES_TEST_LIBRARY"), "SPIKES_TEST_LIBRARY required")
    def test_text_decks_reach_owned_native_kernel(self):
        report = run_deck_qualification(os.environ["SPIKES_TEST_LIBRARY"], repetitions=1)
        self.assertEqual(report["status"], "passed", report)
        self.assertEqual(report["summary"], dict(total=4, passed=4, failed=0))
        self.assertFalse(any(report["claims"].values()))
        for case in report["cases"]:
            self.assertEqual(len(case["observations"]), 2)
            self.assertTrue(case["source_sha256"])
            self.assertGreater(case["warm_median_elapsed_ns"], 0)
            self.assertTrue(all(o["native_status"] == "completed" for o in case["observations"]))


if __name__ == "__main__":
    unittest.main()
