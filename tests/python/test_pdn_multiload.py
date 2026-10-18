# SPDX-License-Identifier: Apache-2.0
"""Original shared-return equations and multi-load transient contracts."""

import copy
import math
import unittest
from unittest.mock import patch

from python.spike_core import pdn_network
from python.spike_core.pdn_network import PdnNetworkError, evaluate_pdn_network, validate_pdn_network


PERIOD = 1 / 1024
RA, RB, RR = .25, .5, .125
LA, LB, LR = PERIOD / 2, PERIOD / 4, PERIOD


def shared_return(divisions=16):
    """Two distinct supplied source branches connected through a shared RL."""
    elements = [{"id": name, "type": "source_output_impedance", "positive": positive,
                 "negative": negative, "resistance_ohm": resistance, "inductance_h": inductance,
                 "provenance": {"kind": "supplied", "source_id": "independent-shared-return-equations"}}
                for name, positive, negative, resistance, inductance in
                (("a", "A", "R", RA, LA), ("b", "B", "R", RB, LB), ("return", "R", "GND", RR, LR))]
    loads = [{"port_id": port, "points": [{"time_s": time * PERIOD, "current_a": current}
                                            for time, current in samples]}
             for port, samples in (("A", [(0., 0.), (1., 1.), (2., 1.), (3., 0.), (4., 0.)]),
                                   ("B", [(0., 0.), (.5, .5), (1.5, 0.), (2.5, -.5), (4., 0.)]))]
    return {"contract": "spike/pdn-network-request/v1", "reference": "GND",
            "nodes": ["A", "B", "R"], "elements": elements,
            "ports": [{"id": node, "mode": "single", "positive": node, "negative": "GND"}
                      for node in ("A", "B")], "frequencies_hz": [1 / PERIOD],
            "load_transient": {"loads": loads, "output_times_s": [i * PERIOD / 4 for i in range(17)],
                               "max_step_s": PERIOD / divisions}}


def exact_currents(time):
    """Independent piecewise equations; interior derivatives are right-sided."""
    t = time / PERIOD
    a, da = ((t, 1.) if t < 1 else (1., 0.) if t < 2 else (3. - t, -1.) if t < 3 else (0., 0.))
    b, db = ((t, 1.) if t < .5 else (.75 - .5 * t, -.5) if t < 2.5 else ((t - 4.) / 3, 1 / 3))
    return a, b, da / PERIOD, db / PERIOD


class PdnMultiLoadTests(unittest.TestCase):
    def test_asynchronous_shared_return_rl_and_energy_at_refinements(self):
        for divisions in (4, 8, 16):
            with self.subTest(divisions=divisions):
                result = evaluate_pdn_network(shared_return(divisions))["load_transient"]
                self.assertEqual(result["load_port_ids"], ["A", "B"])
                for point in result["points"]:
                    a, b, da, db = exact_currents(point["time_s"])
                    return_voltage = -RR * (a + b) - LR * (da + db)
                    voltages = {"R": return_voltage, "A": return_voltage - RA * a - LA * da,
                                "B": return_voltage - RB * b - LB * db}
                    for node, expected in voltages.items():
                        self.assertAlmostEqual(point["node_voltage_v"][node], expected, delta=2e-10)
                    self.assertAlmostEqual(point["load_current_a_by_port"]["A"], a, delta=1e-14)
                    self.assertAlmostEqual(point["load_current_a_by_port"]["B"], b, delta=1e-14)
                    self.assertAlmostEqual(point["stored_energy_j"],
                                           .5 * (LA * a*a + LB * b*b + LR * (a+b)**2), delta=2e-14)
                self.assertLess(result["energy_balance_relative_error"], 1e-12)

    def test_linear_superposition_on_identical_grids_with_shared_energy_cross_term(self):
        req = shared_return()
        combined = evaluate_pdn_network(req)["load_transient"]
        separate = []
        for load in req["load_transient"]["loads"]:
            one = copy.deepcopy(req)
            one["load_transient"] = {**load, "output_times_s": req["load_transient"]["output_times_s"],
                                     "max_step_s": req["load_transient"]["max_step_s"]}
            separate.append(evaluate_pdn_network(one)["load_transient"])
        self.assertEqual([result["steps"] for result in separate], [combined["steps"]] * 2)
        for total, left, right in zip(combined["points"], separate[0]["points"], separate[1]["points"]):
            for field in ("node_voltage_v", "port_voltage_v"):
                for node, actual in total[field].items():
                    self.assertAlmostEqual(actual, left[field][node] + right[field][node], delta=2e-10)
            a, b, _, _ = exact_currents(total["time_s"])
            self.assertAlmostEqual(total["stored_energy_j"] - left["stored_energy_j"] - right["stored_energy_j"],
                                   LR * a * b, delta=2e-14)

    def test_load_order_and_legacy_envelopes(self):
        req = shared_return()
        original = evaluate_pdn_network(req)["load_transient"]
        req["load_transient"]["loads"].reverse()
        reverse = evaluate_pdn_network(req)["load_transient"]
        self.assertEqual(reverse["load_port_ids"], ["B", "A"])
        self.assertNotIn("load_port_id", reverse)
        for left, right in zip(original["points"], reverse["points"]):
            self.assertNotIn("load_current_a", right)
            self.assertEqual(list(right["load_current_a_by_port"]), ["B", "A"])
            self.assertEqual(left["load_current_a_by_port"], right["load_current_a_by_port"])
            for node, voltage in left["node_voltage_v"].items():
                self.assertAlmostEqual(voltage, right["node_voltage_v"][node], delta=2e-10)
        req["load_transient"]["loads"] = req["load_transient"]["loads"][:1]
        multi = evaluate_pdn_network(req)["load_transient"]
        selected = req["load_transient"].pop("loads")[0]
        req["load_transient"].update(selected)
        legacy = evaluate_pdn_network(req)["load_transient"]
        self.assertEqual(legacy["load_port_id"], "B")
        self.assertNotIn("load_port_ids", legacy)
        self.assertEqual(legacy["steps"], multi["steps"])
        for old, new in zip(legacy["points"], multi["points"]):
            self.assertNotIn("load_current_a_by_port", old)
            self.assertEqual(old["load_current_a"], new["load_current_a_by_port"]["B"])
            for node, voltage in old["node_voltage_v"].items():
                self.assertAlmostEqual(voltage, new["node_voltage_v"][node], delta=2e-10)

    def test_strict_multiload_admission(self):
        cases = []
        req = shared_return()
        bad = copy.deepcopy(req); bad["load_transient"]["port_id"] = "A"; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["port_id"] = "A"; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["port_id"] = "unknown"; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["points"][-1]["time_s"] = math.nextafter(4 * PERIOD, math.inf); cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["points"][0]["current_a"] = 1.; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["points"][1]["time_s"] = 0.; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["points"][1]["current_a"] = True; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["points"][1]["current_a"] = 1e308; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][1]["extra"] = 1.; cases.append((bad, "INVALID_REQUEST"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"] = []; cases.append((bad, "RESOURCE_LIMIT"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"] *= 9; cases.append((bad, "RESOURCE_LIMIT"))
        bad = copy.deepcopy(req); bad["load_transient"]["loads"][0]["points"] *= 256; cases.append((bad, "RESOURCE_LIMIT"))
        for index, (bad, code) in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(PdnNetworkError) as caught:
                validate_pdn_network(bad)
            self.assertEqual(caught.exception.code, "PDN_" + code)

    def test_union_grid_resource_limit_is_checked_before_solving(self):
        req = shared_return()
        req["load_transient"]["loads"] = [
            {"port_id": port, "points": [{"time_s": 0., "current_a": 0.},
                                          {"time_s": corner, "current_a": 1.},
                                          {"time_s": 1., "current_a": 1.}]}
            for port, corner in (("A", .25), ("B", .5))]
        req["load_transient"]["output_times_s"] = [0., .75, 1.]
        req["load_transient"]["max_step_s"] = 1.
        with patch.object(pdn_network, "_MAX_STEPS", 3), patch.object(pdn_network, "_solve_linear") as solve:
            for load in req["load_transient"]["loads"]:
                one = copy.deepcopy(req)
                one["load_transient"] = {**load, "output_times_s": [0., .75, 1.], "max_step_s": 1.}
                self.assertEqual(validate_pdn_network(one)["transient_steps"], 3)
            with self.assertRaises(PdnNetworkError) as caught:
                evaluate_pdn_network(req)
            self.assertEqual(caught.exception.code, "PDN_RESOURCE_LIMIT")
            solve.assert_not_called()

    def test_multiload_mid_solve_cancellation_is_atomic(self):
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls == 10

        with self.assertRaises(PdnNetworkError) as caught:
            evaluate_pdn_network(shared_return(), cancel_check=cancel)
        self.assertEqual(caught.exception.code, "PDN_CANCELLED")
        self.assertEqual(calls, 10)


if __name__ == "__main__":
    unittest.main()
