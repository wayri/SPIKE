# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original analytical energy fixtures, no device/vendor data or code."""
import copy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import jsonschema

from python.spike_core.solvers.thermal_fluid.electrothermal.electrical_heat_sources import ElectricalHeatSourceError, evaluate_electrical_heat_source


def waveform():
    # v(t)=1+2t, i(t)=2+3t => p(t)=2+7t+6t^2, integral[0,1]=7.5 J.
    return {"kind": "terminal_waveform", "time_s": [0, 1], "voltage_v": [1, 3],
            "current_a": [2, 5], "energy_policy": "dissipative_terminal_power"}


def spectral():
    return {"kind": "spectral_resistive", "frequency_hz": [0, 50, 100],
            "rms_current_a": [2, 3, 4], "resistance_ohm": [5, 5, 5]}


def table():
    return {"kind": "semiconductor_loss_table", "temperature_k": [300, 400],
            "conduction_power_w": [2, 4], "turn_on_energy_j": [0.001, 0.003],
            "turn_off_energy_j": [0.002, 0.004], "reverse_recovery_energy_j": [0.0005, 0.0015],
            "switching_frequency_hz": 1000, "conditions": "Synthetic fixed V=100 V, I=2 A; original test oracle.",
            "energy_terms_nonoverlapping": True}


def request(model=None):
    return {"contract": "spike/electrical-heat-source/v1", "id": "source-1", "model": model or waveform(),
            "distribution": [{"occurrence_id": "board-a", "cell_id": "cell-a", "weight": 0.25},
                             {"occurrence_id": "board-b", "cell_id": "cell-a", "weight": 0.75}],
            "provenance": {"source_sha256": "a" * 64, "description": "Original analytic fixture; hash is a declaration."}}


class ElectricalHeatSourcesTests(unittest.TestCase):
    def reject(self, raw, code, temperature=350):
        with self.assertRaises(ElectricalHeatSourceError) as caught:
            evaluate_electrical_heat_source(raw, temperature)
        self.assertEqual(caught.exception.code, code)

    def test_exact_quadratic_product_not_trapezoidal_endpoint_power(self):
        result = evaluate_electrical_heat_source(request(), 350)
        self.assertAlmostEqual(result["total_energy_j"], 7.5, places=14)
        self.assertEqual(result["interval_energy_j"], [7.5])
        self.assertEqual(result["average_power_w"], 7.5)
        self.assertNotEqual(result["average_power_w"], (2 + 15) / 2)
        self.assertEqual(result["duration_s"], 1)

    def test_nonuniform_sampling_and_time_translation_conserve_exact_energy(self):
        model = waveform()
        model.update(time_s=[7, 7.125, 7.75, 8], voltage_v=[1, 1.25, 2.5, 3], current_a=[2, 2.375, 4.25, 5])
        result = evaluate_electrical_heat_source(request(model), 0)
        self.assertAlmostEqual(result["total_energy_j"], 7.5, places=14)
        self.assertAlmostEqual(math.fsum(result["interval_energy_j"]), 7.5, places=14)

    def test_negative_between_positive_endpoints_rejected(self):
        model = waveform()
        model.update(voltage_v=[-1, 3], current_a=[-3, 1])
        self.reject(request(model), "nondissipative_power")

    def test_negative_narrow_interval_away_from_midpoint_rejected(self):
        model = waveform()
        model.update(voltage_v=[-1, 9], current_a=[-2, 8])
        self.reject(request(model), "nondissipative_power")

    def test_one_ulp_zero_crossing_difference_cannot_hide_negative_power(self):
        model = waveform()
        model.update(voltage_v=[-1, 1], current_a=[-1, math.nextafter(1, 2)])
        self.reject(request(model), "nondissipative_power")

    def test_mixed_sign_endpoint_and_subnormal_negative_rejected(self):
        for voltage, current in (([1, 3], [-1, 5]), ([1e-300, 1], [-1e-300, 1])):
            model = waveform()
            model.update(voltage_v=voltage, current_a=current)
            self.reject(request(model), "nondissipative_power")

    def test_matching_zero_crossing_is_dissipative_and_exact(self):
        model = waveform()
        model.update(voltage_v=[-1, 1], current_a=[-2, 2])
        self.assertAlmostEqual(evaluate_electrical_heat_source(request(model), 350)["total_energy_j"], 2 / 3)

    def test_energy_storage_policy_and_undeclared_current_rejected(self):
        model = waveform()
        model["energy_policy"] = "net_terminal_energy"
        self.reject(request(model), "energy_policy")
        model = waveform()
        model["stored_energy_j"] = [0, 1]
        self.reject(request(model), "invalid_fields")

    def test_rms_parseval_resistor_and_no_transient_claim(self):
        result = evaluate_electrical_heat_source(request(spectral()), 350)
        # i=2+3*sqrt(2)*cos(wt)+4*sqrt(2)*sin(2wt), orthogonal integer cycles.
        sampled = [2 + 3 * math.sqrt(2) * math.cos(2 * math.pi * n / 4096)
                   + 4 * math.sqrt(2) * math.sin(4 * math.pi * n / 4096) for n in range(4096)]
        oracle = 5 * math.fsum(value * value for value in sampled) / len(sampled)
        self.assertAlmostEqual(result["average_power_w"], 145, places=12)
        self.assertAlmostEqual(result["average_power_w"], oracle, places=11)
        self.assertEqual(result["ledger"]["power_w"], [20, 45, 80])
        self.assertEqual(result["temporal_scope"], "steady_average_only")
        self.assertNotIn("total_energy_j", result)

    def test_temperature_feedback_interpolation_and_ledger(self):
        raw = request(table())
        for temperature, expected in ((300, 5.5), (350, 9), (400, 12.5)):
            result = evaluate_electrical_heat_source(raw, temperature)
            self.assertAlmostEqual(result["average_power_w"], expected, places=13)
            self.assertEqual(result["temperature_k"], temperature)
            self.assertEqual(result["provenance_status"], "caller_declared_not_verified")
        middle = evaluate_electrical_heat_source(raw, 350)["ledger"]
        self.assertEqual(middle["conduction_power_w"], 3)
        self.assertAlmostEqual(middle["turn_on_energy_j"], 0.002)
        self.assertAlmostEqual(middle["turn_on_power_w"], 2)
        self.assertEqual(middle["temperature_bracket_k"], [300, 400])
        self.assertEqual(middle["interpolation_fraction"], 0.5)

    def test_no_extrapolation_or_implicit_double_count_policy(self):
        for temperature in (299.999, 400.001):
            self.reject(request(table()), "temperature_out_of_bounds", temperature)
        for value in (False, 1, "true"):
            model = table()
            model["energy_terms_nonoverlapping"] = value
            self.reject(request(model), "overlapping_energy_terms")
        model = table()
        del model["energy_terms_nonoverlapping"]
        self.reject(request(model), "invalid_fields")
        model = table()
        model["conditions"] = " "
        self.reject(request(model), "invalid_text")

    def test_zero_frequency_keeps_conduction_and_zero_spectral_power(self):
        model = table()
        model["switching_frequency_hz"] = 0
        self.assertEqual(evaluate_electrical_heat_source(request(model), 350)["average_power_w"], 3)
        model = spectral()
        model["resistance_ohm"] = [0, 0, 0]
        self.assertEqual(evaluate_electrical_heat_source(request(model), 350)["average_power_w"], 0)

    def test_distribution_preserved_not_normalized_and_unique(self):
        raw = request()
        raw["distribution"][1]["weight"] += 5e-13
        before = copy.deepcopy(raw)
        result = evaluate_electrical_heat_source(raw, 350)
        self.assertEqual(raw, before)
        self.assertEqual(result["distribution"], raw["distribution"])
        result["distribution"][0]["weight"] = 0
        self.assertEqual(raw, before)
        raw["distribution"][1]["weight"] = 0.5
        self.reject(raw, "weight_sum")
        raw = request()
        raw["distribution"][1]["occurrence_id"] = "board-a"
        self.reject(raw, "duplicate_target")

    def test_strict_contract_provenance_and_model_fields(self):
        raw = request()
        raw["contract"] = "other/v1"
        self.reject(raw, "invalid_contract")
        raw = request()
        raw["model"]["kind"] = "arbitrary_spice"
        self.reject(raw, "unsupported_model")
        raw = request()
        raw["provenance"]["source_sha256"] = "A" * 64
        self.reject(raw, "invalid_provenance")
        raw = request()
        raw["model"]["rms_current_a"] = [1, 1]
        self.reject(raw, "invalid_fields")

    def test_invalid_numbers_grids_and_array_lengths(self):
        for value in (float("nan"), float("inf"), -1, True, "350", 10**400):
            self.reject(request(), "invalid_number", value)
        for factory, key in ((waveform, "time_s"), (spectral, "frequency_hz"), (table, "temperature_k")):
            model = factory()
            model[key][1] = model[key][0]
            self.reject(request(model), "invalid_grid")
        for factory, key in ((waveform, "current_a"), (spectral, "rms_current_a"), (table, "conduction_power_w")):
            model = factory()
            model[key].append(2)
            self.reject(request(model), "array_length")
            for invalid in (float("nan"), float("inf"), True):
                model = factory()
                model[key][0] = invalid
                self.reject(request(model), "invalid_number")

    def test_resource_budgets_and_arithmetic_overflow(self):
        with patch("python.spike_core.solvers.thermal_fluid.electrothermal.electrical_heat_sources.MAX_SAMPLES", 1):
            self.reject(request(), "array_budget")
        with patch("python.spike_core.solvers.thermal_fluid.electrothermal.electrical_heat_sources.MAX_DISTRIBUTION", 1):
            self.reject(request(), "distribution_budget")
        for factory, key in ((waveform, "voltage_v"), (spectral, "rms_current_a"), (table, "turn_on_energy_j")):
            model = factory()
            model[key] = [1e308] * len(model[key])
            self.reject(request(model), "numeric_range")

    def test_schema_validates_all_models_and_rejects_unknown_fields(self):
        path = Path(__file__).resolve().parents[2] / "schemas" / "electrical-heat-source-v1.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        for factory in (waveform, spectral, table):
            raw = request(factory())
            validator.validate(raw)
            raw["model"]["unknown"] = 1
            self.assertTrue(list(validator.iter_errors(raw)))


if __name__ == "__main__":
    unittest.main()
