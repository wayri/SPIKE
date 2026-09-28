"""Bounded series-component SI impact regressions.

SPDX-License-Identifier: MIT
Copyright (c) 2026 SigHarmonic
"""

import unittest

import numpy as np

from python.spike_core.si_workflow import (
    REQUEST,
    SERIES_IMPACT_RESULT,
    run_series_component_impact,
)
from python.spike_core.sparameters import touchstone_text
from tests.python.test_si_workflow import IBIS


def touchstone_request(s_parameters=None):
    frequencies = np.array([0.0, 1e9, 2e9])
    if s_parameters is None:
        s_parameters = np.tile(np.array([[0, 1], [1, 0]], dtype=complex), (len(frequencies), 1, 1))
    return {
        "contract": REQUEST,
        "channel": {
            "kind": "touchstone",
            "name": "board-path.s2p",
            "text": touchstone_text(frequencies, s_parameters),
        },
        "sources": [{"port": 0, "rise_time_s": 0, "fall_time_s": 0}],
        "receivers": [{"port": 1, "resistance_ohm": 50, "capacitance_f": 0}],
        "run_time_domain": False,
    }


class SeriesComponentImpactTests(unittest.TestCase):
    def test_touchstone_before_after_series_rl_is_reproducible(self):
        result = run_series_component_impact(touchstone_request(), [{
            "id": "R17",
            "port": 0,
            "connection": "series",
            "model": {
                "kind": "resistor",
                "grade": "thin_film",
                "resistance_ohm": 22,
                "inductance_h": 0.8e-9,
                "capacitance_f": 0,
                "tolerance_fraction": 0,
            },
        }])
        self.assertEqual(result["contract"], SERIES_IMPACT_RESULT)
        self.assertEqual(result["validation"]["channel_passivity"]["status"], "pass")
        self.assertEqual((result["source_port"], result["receiver_port"]), (0, 1))
        # Ideal through with 50-ohm source/load: Vload/Vsource = 50/(100+R) at DC.
        self.assertAlmostEqual(10 ** (result["comparison"][0]["after_magnitude_db"] / 20), 50 / 122)
        self.assertLess(result["comparison"][-1]["delta_magnitude_db"], result["comparison"][0]["delta_magnitude_db"])
        self.assertEqual(result["after"]["passives"][0]["id"], "R17")

    def test_series_capacitor_uses_declared_esr_esl_and_leakage_topology(self):
        result = run_series_component_impact(touchstone_request(), [{
            "port": 1,
            "model": {
                "kind": "capacitor",
                "grade": "C0G",
                "capacitance_f": 10e-12,
                "esr_ohm": 0.2,
                "esl_h": 0.5e-9,
                "leakage_ohm": 1e12,
                "tolerance_fraction": 0,
            },
        }])
        self.assertLess(result["comparison"][0]["after_magnitude_db"], -100)
        self.assertGreater(result["comparison"][1]["after_magnitude_db"], result["comparison"][0]["after_magnitude_db"])

    def test_nonpassive_touchstone_and_unmapped_or_internal_placement_fail_closed(self):
        active = np.tile(np.array([[0, 1.1], [1.1, 0]], dtype=complex), (3, 1, 1))
        component = [{"port": 0, "model": {"resistance_ohm": 22}}]
        with self.assertRaisesRegex(ValueError, "passive input channel"):
            run_series_component_impact(touchstone_request(active), component)
        with self.assertRaisesRegex(ValueError, "declared source or receiver"):
            request = touchstone_request()
            request["channel"]["name"] = "four.s4p"
            request["channel"]["text"] = touchstone_text(
                [0, 1e9, 2e9], np.tile(np.eye(4, dtype=complex) * 0.1, (3, 1, 1)))
            run_series_component_impact(request, [{"port": 2, "model": {"resistance_ohm": 22}}])
        with self.assertRaisesRegex(ValueError, "Unknown series component fields"):
            run_series_component_impact(
                touchstone_request(),
                [{"port": 0, "placement": "mid-channel", "model": {"resistance_ohm": 22}}],
            )

    def test_multi_endpoint_selection_is_explicit(self):
        request = touchstone_request()
        request["receivers"].append({"port": 0, "resistance_ohm": 50, "capacitance_f": 0})
        # Duplicate endpoint itself is rejected by the base workflow before a
        # comparison can ambiguously select it.
        with self.assertRaisesRegex(ValueError, "only one source or receiver"):
            run_series_component_impact(request, [{"port": 0, "model": {"resistance_ohm": 22}}])

    def test_bounded_ibis_reduction_is_preserved_without_full_ibis_claim(self):
        request = touchstone_request()
        request["sources"] = [{
            "port": 0,
            "ibis": {"text": IBIS, "model": "output", "corner": "min"},
        }]
        result = run_series_component_impact(
            request, [{"port": 0, "model": {"resistance_ohm": 22}}]
        )
        self.assertEqual(result["before"]["ibis"][0]["corner"], "min")
        self.assertIn("DC-slope/ramp reduction", result["limitations"][1])
        self.assertFalse(result["production_qualified"])


if __name__ == "__main__":
    unittest.main()
