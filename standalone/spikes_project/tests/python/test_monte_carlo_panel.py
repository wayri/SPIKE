# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "Opt-in wx Studio panel test")
class MonteCarloPanelTests(unittest.TestCase):
    SOURCE = """Monte Carlo divider
V1 in 0 10
R1 in out 1k
R2 out 0 1k
.op
.end
"""

    def test_real_backend_is_seeded_and_returns_actual_probe_values(self):
        from spikes_studio.monte_carlo_panel import prepare_request, probe_case_value, run_request

        request = prepare_request(self.SOURCE, "R1=10%\nR2=0.05", "V(out)", 4, 123, "uniform")
        first = run_request(request)
        replay = run_request(request)
        self.assertEqual(first, replay)
        self.assertEqual(first["contract"], "spikes/monte-carlo-result/v1")
        values = [probe_case_value(case, "V(out)") for case in first["cases"]]
        self.assertEqual(len(values), 4)
        self.assertTrue(all(0.0 < value < 10.0 for value in values))
        self.assertEqual(first["provenance"]["execution"], "independent_reference_runner_cases")

    def test_percent_parser_and_limits_fail_before_execution(self):
        from spikes_studio.monte_carlo_panel import parse_variations, prepare_request, run_request

        parsed = parse_variations("r1=5%\nR2=.1")
        self.assertEqual([(item.element, item.tolerance) for item in parsed], [("R1", .05), ("R2", .1)])
        with self.assertRaisesRegex(ValueError, "at least one"):
            parse_variations("\n")
        request = prepare_request(self.SOURCE, "R1=5%", "V(out)", 257, 1, "uniform")
        with self.assertRaisesRegex(ValueError, "between 1 and 256"):
            run_request(request)

    def test_nonlinear_decks_and_invalid_seed_are_not_broadened(self):
        from spikes_studio.monte_carlo_panel import prepare_request, run_request

        nonlinear = "V1 in 0 1\nD1 in 0 DM\n.model DM D(IS=1e-14 N=1)\n.op\n.end\n"
        with self.assertRaisesRegex(ValueError, "R/L/C/V/I"):
            prepare_request(nonlinear, "V1=1%", "V(in)", 2, 1, "uniform")
        request = prepare_request(self.SOURCE, "R1=5%", "V(out)", 2, -1, "uniform")
        with self.assertRaisesRegex(ValueError, "0 through"):
            run_request(request)


if __name__ == "__main__":
    unittest.main()
