from pathlib import Path
import unittest

from python.spikes.competitive_benchmark import (
    CompetitiveCase,
    REPORT_CONTRACT,
    _ltspice_deck,
    _reduce_transient,
    find_ltspice,
    run_competitive_benchmarks,
    shared_dc_cases,
    shared_first_release_cases,
)


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "build-spikes-hybrid" / "spikes_c_api.dll"


class CompetitiveBenchmarkTests(unittest.TestCase):
    def test_shared_cases_are_bounded_and_digestable(self):
        cases = shared_dc_cases()
        self.assertEqual(len(cases), 3)
        self.assertEqual(len({item.case_id for item in cases}), len(cases))
        self.assertTrue(all(len(item.to_dict()["netlist_sha256"]) == 64 for item in cases))

    def test_first_release_cases_add_passive_transient_and_switching_metrics(self):
        cases = shared_first_release_cases()
        self.assertEqual(len(cases), 9)
        self.assertEqual(len({item.case_id for item in cases}), len(cases))
        classes = {name for case in cases for name in case.classes}
        self.assertTrue({"operating_point", "transient", "switching", "converter", "rf", "motor"} <= classes)
        self.assertEqual(
            [item.measurement for item in cases],
            ["scalar", "scalar", "scalar", "find_at_time", "find_at_time", "average_window",
             "find_at_time", "find_at_time", "find_at_time"],
        )

    def test_ltspice_deck_adds_measure_and_end_when_missing(self):
        case = CompetitiveCase(
            "missing.end", "Missing end", "Title\nV1 out 0 1\n.op\n",
            "V(out)", 1.0,
        )
        deck = _ltspice_deck(case)
        self.assertIn(".meas op bench_value FIND v(out)", deck)
        self.assertTrue(deck.endswith(".end\n"))

    def test_ltspice_deck_uses_measure_style_transient_reductions(self):
        rc, switch = shared_first_release_cases()[3], shared_first_release_cases()[5]
        self.assertIn(
            ".meas tran bench_value FIND v(out) AT=0.00101",
            _ltspice_deck(rc),
        )
        switching_deck = _ltspice_deck(switch)
        self.assertIn(".meas tran bench_value AVG v(out)", switching_deck)
        self.assertIn("FROM=0 TO=0.0040000000000000001", switching_deck)

    def test_transient_reducer_interpolates_and_integrates(self):
        find_case = shared_first_release_cases()[3]
        self.assertAlmostEqual(
            _reduce_transient(find_case, [0.0, 0.0005, 0.00101], [0.0, 0.4, 0.6]),
            0.6,
        )
        average_case = shared_first_release_cases()[5]
        self.assertAlmostEqual(
            _reduce_transient(
                average_case,
                [0.0, 0.001, 0.002, 0.003, 0.004],
                [0.0, 10.0, 0.0, 10.0, 0.0],
            ),
            5.0,
        )

    @unittest.skipUnless(LIBRARY.is_file(), "owned C ABI library is unavailable")
    def test_real_shared_subset_report_never_promotes_performance(self):
        report = run_competitive_benchmarks(LIBRARY, repetitions=1)
        self.assertEqual(report["contract"], REPORT_CONTRACT)
        self.assertFalse(report["performance_claim_eligible"])
        if report["shared_subset_accuracy_passed"]:
            self.assertTrue(report["timing_comparable"])
        self.assertEqual(report["engines"][0]["status"], "passed")
        self.assertEqual(report["corpus"]["case_count"], 9)
        self.assertIn("switching", report["corpus"]["classes"])
        self.assertIn("large", report["corpus"]["missing_required_classes"])
        ltspice = next(item for item in report["engines"] if item["engine_id"] == "ltspice")
        self.assertEqual(bool(find_ltspice()), ltspice["status"] != "blocked")


if __name__ == "__main__":
    unittest.main()
