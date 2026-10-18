# SPDX-License-Identifier: Apache-2.0
"""Independent small-domain circuit and constraint oracles for decap selection."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_decap_selection as selection
from tests.python.test_pdn_decap_corners import request as corner_request, cap_z
from tests.python.test_pdn_network import basic, element


def request():
    old = corner_request()
    options = [{"id": cap["id"], "part_id": cap["id"], "unit_cost_minor": cost,
                "provenance": cap["provenance"], "corners": cap["corners"]}
               for cap, cost in zip(old["capacitors"], (6, 2))]
    return {"contract": selection.REQUEST_CONTRACT, "base_request": old["base_request"],
            "corners": old["corners"], "target_impedance_ohm_by_port": old["target_impedance_ohm_by_port"],
            "sites": [{"id": site, "positive": "V", "negative": "GND", "options": deepcopy(options)} for site in ("a", "b")],
            "inventory": [{"part_id": "bulk", "max_quantity": 1}, {"part_id": "small", "max_quantity": 2}],
            "budget_minor": 8, "max_capacitors": 2}


POPULATIONS = [(None, "bulk"), (None, "small"), ("bulk", None), ("bulk", "bulk"),
               ("bulk", "small"), ("small", None), ("small", "bulk"), ("small", "small")]


def scalar_ratios(req, population):
    """Parallel branch admittance, independent of the selector/core results."""
    options = {o["part_id"]: o for o in req["sites"][0]["options"]}
    samples = []
    for corner in req["corners"]:
        for frequency in req["base_request"]["frequencies_hz"]:
            omega = 2 * math.pi * frequency
            impedance = 1 / (1 / (.08 + 1j * omega * 2e-7)
                             + sum(1 / cap_z(options[p], corner["id"], omega) for p in population if p is not None))
            samples.append(abs(impedance) / req["target_impedance_ohm_by_port"]["load"])
    return max(samples)


class PdnDecapSelectionTests(unittest.TestCase):
    def test_manual_enumeration_scalar_oracle_and_lexicographic_winner(self):
        for target in (.1, 100., 1e-8):
            req = request(); req["target_impedance_ohm_by_port"]["load"] = target
            before = deepcopy(req)
            out = selection.run_pdn_decap_selection(req)
            self.assertEqual(req, before)
            self.assertEqual(len(out["configurations"]), 8)
            ranks = []
            for i, (summary, population) in enumerate(zip(out["configurations"], POPULATIONS)):
                cost = sum({"bulk": 6, "small": 2}[p] for p in population if p)
                count = sum(p is not None for p in population)
                self.assertEqual(summary["cost_minor"], cost)
                self.assertEqual(summary["capacitor_count"], count)
                self.assertEqual(summary["id"], f"configuration-{i+1}")
                self.assertEqual(summary["selection"], [{"site_id": site, "option_id": part, "part_id": part}
                    for site, part in zip(("a", "b"), population) if part])
                if population == ("bulk", "bulk"):
                    self.assertEqual(summary["status"], "constraint_rejected")
                    self.assertEqual(summary["constraint_violations"], ["budget_exceeded", "inventory_exceeded:bulk"])
                    self.assertIsNone(summary["meets_target"])
                    self.assertIsNone(summary["worst_case"])
                    continue
                ratio = scalar_ratios(req, population)
                self.assertAlmostEqual(summary["worst_case"]["target_ratio"], ratio, delta=max(1., ratio) * 1e-11)
                self.assertEqual(summary["meets_target"], ratio <= 1)
                ranks.append(((0, cost, ratio, count, i) if ratio <= 1 else (1, ratio, cost, count, i), summary["id"]))
            self.assertEqual(out["selected_id"], min(ranks)[1])
            chosen = next(row for row in out["configurations"] if row["id"] == out["selected_id"])
            self.assertEqual(out["meets_target"], chosen["meets_target"])
            self.assertEqual(out["selected_result"]["worst_case"], chosen["worst_case"])
            self.assertEqual(out["diagnostics"]["evaluated_count"], 7)
            self.assertFalse(out["production_qualified"])
            self.assertEqual(out["model_status"], "experimental")
            self.assertEqual(out["input_digest"], selection.corner_service._digest(before))
            if target == 100.:
                early, late = out["configurations"][1], out["configurations"][5]
                self.assertEqual(early["cost_minor"], late["cost_minor"])
                self.assertEqual(early["capacitor_count"], late["capacitor_count"])
                self.assertEqual(early["worst_case"]["target_ratio"], late["worst_case"]["target_ratio"])
                self.assertEqual(out["selected_id"], "configuration-2")
            if target == 1e-8:
                self.assertFalse(out["meets_target"])

    def test_location_dependent_twoport_nodal_oracle(self):
        req = request()
        req["sites"][0].update(positive="A")
        req["sites"][1].update(positive="B")
        for site in req["sites"]:
            site["options"] = site["options"][:1]
        req["inventory"] = [{"part_id": "bulk", "max_quantity": 2}]
        req["budget_minor"] = 12
        req["base_request"] = basic([
            element("source", "resistor", positive="A", negative="GND", resistance_ohm=.2),
            element("link", "source_output_impedance", positive="A", negative="B", resistance_ohm=.05, inductance_h=1e-6)],
            nodes=["A", "B"], ports=[{"id": "a", "mode": "single", "positive": "A", "negative": "GND"},
                                     {"id": "b", "mode": "single", "positive": "B", "negative": "GND"}],
            frequencies=[10000., 100000.])
        req["target_impedance_ohm_by_port"] = {"a": .1, "b": .1}
        out = selection.run_pdn_decap_selection(req)
        for summary, population in zip(out["configurations"], ((1,), (0,), (0, 1))):
            worst = 0.
            for corner in req["corners"]:
                for frequency in req["base_request"]["frequencies_hz"]:
                    omega = 2 * math.pi * frequency
                    link = 1 / (.05 + 1j * omega * 1e-6)
                    matrix = np.array([[5. + link, -link], [-link, link]], dtype=complex)
                    for index in population:
                        matrix[index, index] += 1 / cap_z(req["sites"][index]["options"][0], corner["id"], omega)
                    impedance = np.linalg.solve(matrix, np.eye(2))
                    worst = max(worst, max(abs(impedance[0, 0]), abs(impedance[1, 1])) / .1)
            self.assertAlmostEqual(summary["worst_case"]["target_ratio"], worst, delta=1e-11)
        self.assertNotAlmostEqual(out["configurations"][0]["worst_case"]["target_ratio"],
                                  out["configurations"][1]["worst_case"]["target_ratio"], delta=1e-3)

    def test_all_constraint_reasons_and_zero_admissible_failure(self):
        req = request(); req.update(max_capacitors=1, budget_minor=6)
        req["inventory"][1]["max_quantity"] = 1
        out = selection.run_pdn_decap_selection(req)
        self.assertEqual(out["diagnostics"]["evaluated_count"], 4)
        both = out["configurations"][3]
        self.assertEqual(both["constraint_violations"], ["budget_exceeded", "capacitor_count_exceeded", "inventory_exceeded:bulk"])
        req["budget_minor"] = 0
        with patch.object(selection.corner_service, "run_pdn_decap_corners") as solve:
            with self.assertRaises(selection.PdnDecapSelectionError) as caught:
                selection.run_pdn_decap_selection(req)
            self.assertEqual(caught.exception.code, "PDN_DECAP_SELECTION_NO_FEASIBLE_CONFIGURATION")
            solve.assert_not_called()

    def test_part_identity_order_invariance_and_collision_safe_mapping(self):
        req = request()
        req["base_request"]["elements"][0]["id"] = "selection-site-0"
        for option in req["sites"][1]["options"]:
            option["corners"].reverse()
        out = selection.run_pdn_decap_selection(req)
        mapping = out["selected_result"]["corners"][0]["element_mapping"]
        self.assertTrue(all(row["capacitor_id"] != "selection-site-0" for row in mapping))
        self.assertEqual(out["sites"], req["sites"])
        for key, value in (("unit_cost_minor", 7), ("provenance", {"kind": "supplied", "source_id": "different"})):
            bad = deepcopy(req); bad["sites"][1]["options"][0][key] = value
            with self.assertRaisesRegex(selection.PdnDecapSelectionError, "Inconsistent definition"):
                selection.run_pdn_decap_selection(bad)
        bad = deepcopy(req); bad["sites"][1]["options"][0]["corners"][0]["capacitance_f"] *= 2
        with self.assertRaisesRegex(selection.PdnDecapSelectionError, "Inconsistent definition"):
            selection.run_pdn_decap_selection(bad)

    def test_excluded_invalid_options_and_strict_money_count_domain(self):
        mutations = [lambda r: r.update(extra=True), lambda r: r.update(budget_minor=True),
            lambda r: r.update(max_capacitors=0), lambda r: r.update(max_capacitors=9),
            lambda r: r["inventory"][0].update(max_quantity=True),
            lambda r: r["inventory"].append({"part_id": "unused", "max_quantity": 0}),
            lambda r: r["inventory"].pop(), lambda r: r["inventory"][1].update(part_id="bulk"),
            lambda r: r["sites"][1].update(id="a"),
            lambda r: r["sites"][0]["options"][1].update(id="bulk"),
            lambda r: r["sites"][0]["options"][0].update(unit_cost_minor=1.5),
            lambda r: r["sites"][0]["options"][0]["corners"][0].update(capacitance_f=-1.)]
        for i, mutate in enumerate(mutations):
            req = request(); req["budget_minor"] = 0
            for part in req["inventory"]: part["max_quantity"] = 0
            mutate(req)
            with self.subTest(case=i), patch.object(selection.corner_service, "run_pdn_decap_corners") as solve:
                with self.assertRaises(selection.PdnDecapSelectionError) as caught:
                    selection.run_pdn_decap_selection(req)
                self.assertNotEqual(caught.exception.code, "PDN_DECAP_SELECTION_NO_FEASIBLE_CONFIGURATION")
                solve.assert_not_called()

    def test_resource_preflight_and_aggregate_work_before_solving(self):
        for constant in ("_MAX_REQUEST_BYTES", "_MAX_RESULT_BYTES", "_MAX_DENSE_WORK", "_MAX_CONFIGURATIONS"):
            with patch.object(selection, constant, 1), patch.object(selection.corner_service, "run_pdn_decap_corners") as solve:
                with self.assertRaises(selection.PdnDecapSelectionError) as caught:
                    selection.run_pdn_decap_selection(request())
                self.assertEqual(caught.exception.code, "PDN_DECAP_SELECTION_RESOURCE_LIMIT")
                solve.assert_not_called()
        req = request()
        req["sites"] = [{**deepcopy(req["sites"][0]), "id": str(i)} for i in range(6)]
        with patch.object(selection.corner_service, "run_pdn_decap_corners") as solve:
            with self.assertRaisesRegex(selection.PdnDecapSelectionError, "256 nonempty"):
                selection.run_pdn_decap_selection(req)
            solve.assert_not_called()
        req = request()
        admitted = selection._prepare(req, len(selection.corner_service._json(req)), lambda: None)
        largest_single = max(selection._admit_corner(job, lambda: None)[-2] for _, job in admitted[1])
        self.assertGreater(admitted[-2], largest_single)
        with patch.object(selection, "_MAX_DENSE_WORK", largest_single), patch.object(selection.corner_service, "run_pdn_decap_corners") as solve:
            with self.assertRaisesRegex(selection.PdnDecapSelectionError, "Aggregate selection"):
                selection.run_pdn_decap_selection(req)
            solve.assert_not_called()

    def test_cancel_or_later_numerical_failure_discards_earlier_winner(self):
        real_solve = selection.corner_service.run_pdn_decap_corners
        completed = 0

        def finish(raw, **kwargs):
            nonlocal completed
            result = real_solve(raw, **kwargs)
            completed += 1
            return result

        with patch.object(selection.corner_service, "run_pdn_decap_corners", side_effect=finish):
            with self.assertRaises(selection.PdnDecapSelectionError) as caught:
                selection.run_pdn_decap_selection(request(), cancel_check=lambda: completed >= 2)
            self.assertEqual(caught.exception.code, "PDN_DECAP_SELECTION_CANCELLED")
        self.assertEqual(completed, 2)
        completed = 0

        def fail_later(raw, **kwargs):
            if completed:
                raise selection.corner_service.PdnDecapCornersError("singular_network", "independent injected later solve failure")
            return finish(raw, **kwargs)

        with patch.object(selection.corner_service, "run_pdn_decap_corners", side_effect=fail_later):
            with self.assertRaises(selection.PdnDecapSelectionError) as caught:
                selection.run_pdn_decap_selection(request())
            self.assertEqual(caught.exception.code, "PDN_DECAP_SELECTION_SINGULAR_NETWORK")
        self.assertEqual(completed, 1)


if __name__ == "__main__":
    unittest.main()
