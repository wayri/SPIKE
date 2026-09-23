# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic

import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.structured_solid_thermal import REQUEST_CONTRACT, solve_structured_solid_thermal


def _boundaries(left, right):
    return {
        "x_min": left,
        "x_max": right,
        "y_min": {"type": "adiabatic"},
        "y_max": {"type": "adiabatic"},
        "z_min": {"type": "adiabatic"},
        "z_max": {"type": "adiabatic"},
    }


def _request(nx=8):
    return {
        "contract": REQUEST_CONTRACT,
        "grid": {"shape": [nx, 1, 1], "spacing_m": [1.0 / nx, 1.0, 1.0]},
        "materials": [{"id": "solid", "thermal_conductivity_w_mk": 2.0, "density_kg_m3": 4.0, "specific_heat_j_kgk": 5.0}],
        "material_ids": ["solid"] * nx,
        "heat_generation_w_m3": 0.0,
        "boundaries": _boundaries({"type": "temperature", "temperature_k": 300.0}, {"type": "temperature", "temperature_k": 400.0}),
        "study": {"type": "steady"},
    }


class StructuredSolidThermalTests(unittest.TestCase):
    def test_radiation_matches_independent_surface_temperature_law(self):
        for ambient, inward in ((300.0, 100.0), (500.0, -50.0)):
            request = _request(1)
            request["materials"][0]["thermal_conductivity_w_mk"] = 0.1
            request["boundaries"] = _boundaries(
                {"type": "heat_flux", "inward_heat_flux_w_m2": inward},
                {"type": "radiation", "ambient_temperature_k": ambient, "emissivity": 0.8},
            )
            result = solve_structured_solid_thermal(request)
            surface = (ambient ** 4 + inward / (0.8 * 5.670374419e-8)) ** 0.25
            expected_cell = surface + inward * 0.5 / 0.1
            self.assertEqual(result["status"], "completed", result)
            self.assertAlmostEqual(result["temperature_k"][0], expected_cell, places=7)

    def test_three_dimensional_manufactured_solution_converges(self):
        errors = []
        for n in (3, 6, 12, 24):
            request = _request(1)
            request["grid"] = {"shape": [n, n, n], "spacing_m": 1.0 / n}
            request["material_ids"] = ["solid"] * n ** 3
            request["materials"][0]["thermal_conductivity_w_mk"] = [1.0, 2.0, 3.0]
            coordinates = (np.arange(n) + 0.5) / n
            z, y, x = np.meshgrid(coordinates, coordinates, coordinates, indexing="ij")
            mode = np.sin(np.pi * x) * np.sin(np.pi * y) * np.sin(np.pi * z)
            request["heat_generation_w_m3"] = (6 * np.pi ** 2 * mode).ravel().tolist()
            request["boundaries"] = {face: {"type": "temperature", "temperature_k": 300.0} for face in request["boundaries"]}
            result = solve_structured_solid_thermal(request)
            self.assertEqual(result["status"], "completed", result.get("issues"))
            errors.append(float(np.linalg.norm(np.asarray(result["temperature_k"]) - (300 + mode).ravel()) / n ** 1.5))
        self.assertTrue(all(np.log2(a / b) > 1.95 for a, b in zip(errors, errors[1:])), errors)

    def test_balanced_source_free_slab_uses_boundary_throughput(self):
        result = solve_structured_solid_thermal(_request(7))
        self.assertEqual(result["status"], "completed", result)
        self.assertAlmostEqual(result["energy"]["boundary_throughput_w"], 400.0, places=8)
        self.assertLess(result["energy"]["relative_residual"], 1e-12)

    def test_cancellation_after_solve_discards_fields(self):
        checks = iter((False, False, True))
        result = solve_structured_solid_thermal(_request(), cancel_check=lambda: next(checks))
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["temperature_k"], [])

    def test_bad_early_step_is_rejected_even_when_not_saved(self):
        request = _request(1)
        request["study"] = {"type": "transient", "initial_temperature_k": 300.0, "time_step_s": 1.0, "steps": 3, "output_stride": 3}
        with patch("python.spike_core.structured_solid_thermal._energy", return_value={"passed": False}) as energy:
            result = solve_structured_solid_thermal(request)
        self.assertEqual(energy.call_count, 1)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["frames"], [])

    def test_zero_emissivity_is_not_a_steady_temperature_constraint(self):
        request = _request(1)
        request["boundaries"] = {face: {"type": "radiation", "ambient_temperature_k": 300.0, "emissivity": 0.0} for face in request["boundaries"]}
        self.assertEqual(solve_structured_solid_thermal(request)["status"], "blocked")

    def test_transient_backward_euler_has_first_order_convergence(self):
        errors = []
        for steps in (10, 20, 40, 80):
            request = _request(1)
            request["boundaries"] = _boundaries({"type": "adiabatic"}, {"type": "temperature", "temperature_k": 400.0})
            request["study"] = {"type": "transient", "initial_temperature_k": 300.0, "time_step_s": 5.0 / steps, "steps": steps, "output_stride": steps}
            result = solve_structured_solid_thermal(request)
            self.assertEqual(result["status"], "completed", result)
            expected = 400 - 100 * np.exp(-1)
            errors.append(abs(result["temperature_k"][0] - expected))
        self.assertTrue(all(np.log2(a / b) > 0.94 for a, b in zip(errors, errors[1:])), errors)

    def test_radiation_to_zero_kelvin_starts_and_extreme_input_is_rejected(self):
        request = _request(1)
        request["heat_generation_w_m3"] = 100.0
        request["boundaries"] = _boundaries({"type": "adiabatic"}, {"type": "radiation", "ambient_temperature_k": 0.0, "emissivity": 1.0})
        result = solve_structured_solid_thermal(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertAlmostEqual(result["temperature_k"][0], (100 / 5.670374419e-8) ** 0.25 + 25, places=7)
        request["boundaries"]["x_max"]["ambient_temperature_k"] = 1e308
        result = solve_structured_solid_thermal(request)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["temperature_k"], [])

    def test_numeric_strings_and_booleans_are_rejected(self):
        for value in (True, "2.0"):
            request = _request(1)
            request["materials"][0]["thermal_conductivity_w_mk"] = value
            self.assertEqual(solve_structured_solid_thermal(request)["status"], "blocked")

    def test_one_dimensional_slab_is_linear_and_conservative(self):
        result = solve_structured_solid_thermal(_request())
        self.assertEqual(result["status"], "completed")
        np.testing.assert_allclose(result["temperature_k"], np.linspace(306.25, 393.75, 8), rtol=0, atol=1e-11)
        self.assertLess(result["summary"]["linear_relative_residual"], 1e-12)
        self.assertLess(result["energy"]["relative_residual"], 1e-12)
        self.assertFalse(result["qualification"]["production_qualified"])

    def test_anisotropic_layer_contact_matches_series_resistance(self):
        request = _request(2)
        request["grid"]["spacing_m"] = [1.0, 1.0, 1.0]
        request["materials"] = [
            {"id": "a", "thermal_conductivity_w_mk": [2.0, 1.0, 1.0], "density_kg_m3": 1.0, "specific_heat_j_kgk": 1.0},
            {"id": "b", "thermal_conductivity_w_mk": [4.0, 1.0, 1.0], "density_kg_m3": 1.0, "specific_heat_j_kgk": 1.0},
        ]
        request["material_ids"] = ["a", "b"]
        request["interface_contacts"] = [{"materials": ["a", "b"], "resistance_m2k_w": 0.25}]
        result = solve_structured_solid_thermal(request)
        self.assertEqual(result["status"], "completed")
        expected_heat = 100.0 / (1.0 / 2.0 + 0.25 + 1.0 / 4.0)
        self.assertAlmostEqual(result["energy"]["outward_boundary_power_w"], 0.0, places=10)
        self.assertAlmostEqual((result["temperature_k"][1] - result["temperature_k"][0]) / (0.25 + 0.25 + 0.125), expected_heat, places=9)

    def test_transient_adiabatic_cell_tracks_exact_energy_ramp(self):
        request = _request(1)
        request["boundaries"] = {face: {"type": "adiabatic"} for face in request["boundaries"]}
        request["heat_generation_w_m3"] = 20.0
        request["study"] = {"type": "transient", "initial_temperature_k": 300.0, "time_step_s": 0.5, "steps": 4, "output_stride": 2}
        result = solve_structured_solid_thermal(request)
        self.assertEqual(result["status"], "completed")
        self.assertAlmostEqual(result["temperature_k"][0], 302.0, places=11)
        self.assertEqual([frame["time_s"] for frame in result["frames"]], [1.0, 2.0])
        self.assertLess(result["energy"]["relative_residual"], 1e-12)

    def test_convection_and_radiation_are_supported_without_false_qualification(self):
        request = _request(1)
        request["heat_generation_w_m3"] = 10.0
        request["boundaries"] = _boundaries(
            {"type": "convection", "ambient_temperature_k": 300.0, "heat_transfer_coefficient_w_m2k": 10.0},
            {"type": "radiation", "ambient_temperature_k": 300.0, "emissivity": 0.8},
        )
        result = solve_structured_solid_thermal(request)
        self.assertEqual(result["status"], "completed", result.get("issues"))
        self.assertGreater(result["temperature_k"][0], 300.0)
        self.assertLess(result["energy"]["relative_residual"], 1e-9)

    def test_rejects_unknown_fields_unbounded_output_and_unconstrained_steady_problem(self):
        request = _request(1)
        request["surprise"] = True
        self.assertEqual(solve_structured_solid_thermal(request)["status"], "blocked")
        request = _request(1)
        request["boundaries"] = {face: {"type": "adiabatic"} for face in request["boundaries"]}
        self.assertEqual(solve_structured_solid_thermal(request)["status"], "blocked")
        request = _request(1)
        request["study"] = {"type": "transient", "initial_temperature_k": 300.0, "time_step_s": 1.0, "steps": 10_000, "output_stride": 1}
        request["grid"]["shape"] = [256, 1, 1]
        request["material_ids"] = ["solid"] * 256
        self.assertEqual(solve_structured_solid_thermal(request)["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
