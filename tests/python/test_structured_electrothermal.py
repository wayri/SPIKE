# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import math
import json
import unittest
from copy import deepcopy

from python.spike_core.structured_electrothermal import CONTRACT, solve_structured_electrothermal
from tests.python.test_structured_solid_thermal import _request


def coupled_request():
    thermal = _request(1)
    thermal["boundaries"] = {face: {"type": "adiabatic"} for face in thermal["boundaries"]}
    # One-cell half-conduction resistance = 0.5 / (1/6) = 3 K/W.
    thermal["materials"][0]["thermal_conductivity_w_mk"] = 1 / 6
    thermal["boundaries"]["x_min"] = {"type": "temperature", "temperature_k": 300.0}
    return {"contract": CONTRACT, "thermal": thermal,
            "circuit": {"contract": "spike/native-mna-request/v1", "request_id": "heated-resistor", "ground_node": "0",
                        "analysis": {"mode": "operating_point"}, "elements": [
                            {"id": "V", "type": "voltage_source", "positive_node": "hot", "negative_node": "0", "dc_value": 12.0},
                            {"id": "R", "type": "resistor", "positive_node": "hot", "negative_node": "0", "resistance_ohm": 4.0}]},
            "bindings": [{"element_id": "R", "cells": [0], "weights": [1.0], "reference_temperature_k": 300.0, "temperature_coefficient_per_k": 0.004}]}


class StructuredElectrothermalTests(unittest.TestCase):
    def test_circuit_field_solution_matches_closed_form_quadratic(self):
        request = coupled_request()
        before = deepcopy(request)
        result = solve_structured_electrothermal(request)
        self.assertEqual(result["status"], "completed", result)
        rise = 2 * 108 / (1 + math.sqrt(1 + 4 * 0.004 * 108))
        self.assertAlmostEqual(result["temperature_k"][0], 300 + rise, places=6)
        self.assertAlmostEqual(result["electrical"]["data"]["element_power_w"]["R"], rise / 3, places=7)
        self.assertEqual(request, before)
        self.assertFalse(result["qualification"]["production_qualified"])
        self.assertLess(result["history"][-1]["mapping_residual_w"], 1e-12)
        json.dumps(result, allow_nan=False)

    def test_distributed_loss_and_temperature_sampling_are_adjoint(self):
        request = coupled_request()
        request["thermal"]["grid"] = {"shape": [2, 1, 1], "spacing_m": [0.5, 1, 1]}
        request["thermal"]["material_ids"] = ["solid", "solid"]
        request["bindings"][0].update(cells=[0, 1], weights=[0.25, 0.75])
        result = solve_structured_electrothermal(request)
        self.assertEqual(result["status"], "completed", result)
        # Half-cell resistance to ambient is 1.5 K/W; the far cell's
        # deposited fraction crosses another 3 K/W. w^T K^-1 w = 3.1875.
        coupling = 3.1875 * 36
        rise = 2 * coupling / (1 + math.sqrt(1 + 4 * 0.004 * coupling))
        sampled = sum(w * t for w, t in zip((0.25, 0.75), result["temperature_k"]))
        self.assertAlmostEqual(sampled, 300 + rise, places=6)
        self.assertLess(abs(result["coupled_power_residual_w"]), 1e-8)

    def test_background_cooling_is_balanced_with_electrical_heating(self):
        request = coupled_request()
        request["bindings"][0]["temperature_coefficient_per_k"] = 0.0
        request["circuit"]["elements"][0]["dc_value"] = 24.0
        request["thermal"]["heat_generation_w_m3"] = -120.0
        result = solve_structured_electrothermal(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertAlmostEqual(result["temperature_k"][0], 372.0, places=8)
        self.assertAlmostEqual(result["electrical"]["data"]["element_power_w"]["R"], 144.0, places=8)
        self.assertLess(abs(result["coupled_power_residual_w"]), 1e-10)

    def test_missing_duplicate_or_nonconservative_loss_mapping_rejected(self):
        for mutation in ("missing", "duplicate", "weight", "cell"):
            request = coupled_request()
            if mutation == "missing": request["bindings"] = []
            elif mutation == "duplicate": request["bindings"] *= 2
            elif mutation == "weight": request["bindings"][0]["weights"] = [0.5]
            else: request["bindings"][0]["cells"] = [2]
            result = solve_structured_electrothermal(request)
            self.assertEqual(result["status"], "blocked", mutation)
            self.assertEqual(result["temperature_k"], [])

    def test_small_relaxation_cannot_hide_nonconvergence(self):
        request = coupled_request()
        request["iteration"] = {"relaxation": 1e-6, "max_iterations": 2, "temperature_tolerance_k": 1e-3}
        result = solve_structured_electrothermal(request)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("iteration limit", result["issues"][0]["message"])

    def test_cancellation_and_invalid_material_law_leave_no_fields(self):
        result = solve_structured_electrothermal(coupled_request(), cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        request = coupled_request()
        request["bindings"][0]["temperature_coefficient_per_k"] = -1.0
        result = solve_structured_electrothermal(request)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["temperature_k"], [])
