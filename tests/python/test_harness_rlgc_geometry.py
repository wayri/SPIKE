# SPDX-License-Identifier: Apache-2.0
"""Independent analytical geometry, diffusion, energy and admission oracles."""
import copy
import json
import math
import unittest

import numpy as np

from python.spike_core.harness_rlgc_geometry import (
    CONTRACT, EPSILON0, MU0, _internal_impedance, extract_parallel_round_rlgc,
)


def fixture():
    return {"contract": CONTRACT, "reference_plane": {"kind": "ideal_infinite_ground_plane"},
            "wires": [{"wire_id": name, "x_m": x, "height_m": .01, "radius_m": .0002,
                       "conductivity_s_m": 5.8e7, "relative_permeability": 1}
                      for name, x in (("p", -.005), ("n", .005))],
            "dielectric": {"relative_permittivity": 2.25, "loss_tangent": .01},
            "frequency_hz": [0, 1, 1e3, 1e6, 1e8],
            "provenance": {"source": "Independent synthetic straight-wire analytical fixture"}}


class HarnessGeometryRlgcTests(unittest.TestCase):
    def test_dc_internal_inductance_and_resistance(self):
        request = fixture()
        result = extract_parallel_round_rlgc(request)
        model = result["model"]
        expected_r = 1 / (math.pi * .0002**2 * 5.8e7)
        np.testing.assert_allclose(model["r_ohm_per_m"][0], np.eye(2) * expected_r, rtol=1e-14)
        lint = np.array(model["l_h_per_m"][0]) - result["external_inductance_h_per_m"]
        np.testing.assert_allclose(lint, np.eye(2) * 5e-8, rtol=1e-14)
        np.testing.assert_equal(model["g_s_per_m"][0], np.zeros((2, 2)))
        for key in ("r_ohm_per_m", "l_h_per_m"):
            np.testing.assert_allclose(model[key][1], model[key][0], rtol=1e-7)

    def test_symmetric_two_wire_modes_and_tem_duality(self):
        result = extract_parallel_round_rlgc(fixture())
        external = np.array(result["external_inductance_h_per_m"])
        c = np.array(result["model"]["c_f_per_m"][0])
        self_term = MU0 / (2 * math.pi) * math.log(100)
        mutual_term = MU0 / (2 * math.pi) * math.log(math.sqrt(5))
        for vector, sign in ((np.array([1., 1.]), 1), (np.array([1., -1.]), -1)):
            inductance = self_term + sign * mutual_term
            capacitance = MU0 * EPSILON0 * 2.25 / inductance
            np.testing.assert_allclose(external @ vector, inductance * vector, rtol=1e-13)
            np.testing.assert_allclose(c @ vector, capacitance * vector, rtol=1e-13)
        np.testing.assert_allclose(external @ c, np.eye(2) * MU0 * EPSILON0 * 2.25, rtol=1e-13, atol=1e-32)
        # Equal wire physics leaves common/differential modes uncoupled.
        q = np.array([[1., 1.], [1., -1.]]) / math.sqrt(2)
        for key in ("r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"):
            for matrix in result["model"][key]:
                modal = q.T @ matrix @ q
                self.assertLessEqual(abs(modal[0, 1]), 1e-14 * np.max(abs(modal)))

    def test_radial_diffusion_series_oracle_across_skin_transition(self):
        wire = fixture()["wires"][0]
        # Solve cylindrical diffusion with a radial polynomial, normalize by
        # its integrated current. No Bessel call or stored external fixture.
        for t in (1e-8, 1e-4, .01, 1, 10, 100):
            term = 1 + 0j
            surface, area_mean = term, term
            for order in range(1, 150):
                term *= 1j * t / (4 * order**2)
                surface += term
                area_mean += term / (order + 1)
            rdc = 1 / (math.pi * wire["radius_m"]**2 * wire["conductivity_s_m"])
            expected = rdc * surface / area_mean
            omega = t / (MU0 * wire["conductivity_s_m"] * wire["radius_m"]**2)
            resistance, inductance = _internal_impedance(omega / (2 * math.pi), wire)
            actual = resistance + 1j * omega * inductance
            self.assertAlmostEqual(actual.real / expected.real, 1, delta=2e-13)
            self.assertAlmostEqual(actual.imag / expected.imag, 1, delta=2e-10)

    def test_scaled_bessel_high_skin_limit_does_not_overflow(self):
        wire = fixture()["wires"][0]
        frequency = 1e10
        resistance, inductance = _internal_impedance(frequency, wire)
        omega = 2 * math.pi * frequency
        skin_depth = math.sqrt(2 / (omega * MU0 * wire["conductivity_s_m"]))
        surface_resistance = 1 / (2 * math.pi * wire["radius_m"] * wire["conductivity_s_m"] * skin_depth)
        self.assertAlmostEqual(resistance / surface_resistance, 1, delta=.002)
        self.assertAlmostEqual(omega * inductance / surface_resistance, 1, delta=.002)

    def test_reciprocal_positive_energy_passive_dielectric_and_skin_trend(self):
        model = extract_parallel_round_rlgc(fixture())["model"]
        for key in ("r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"):
            for matrix in model[key]:
                matrix = np.array(matrix)
                self.assertTrue(np.all(np.isfinite(matrix)))
                np.testing.assert_equal(matrix, matrix.T)
                self.assertGreaterEqual(np.min(np.linalg.eigvalsh(matrix)), 0)
        for f, g, c in zip(model["frequency_hz"], model["g_s_per_m"], model["c_f_per_m"]):
            np.testing.assert_allclose(g, 2 * math.pi * f * .01 * np.array(c), rtol=1e-14)
        r = np.array(model["r_ohm_per_m"])[:, 0, 0]
        l = np.array(model["l_h_per_m"])[:, 0, 0]
        self.assertTrue(np.all(np.diff(r) > 0))
        self.assertTrue(np.all(np.diff(l) < 0))

    def test_thin_wire_single_cylinder_error_decreases_quadratically(self):
        errors = []
        for radius in (.0005, .00025, .000125):
            request = fixture()
            request["wires"] = [dict(request["wires"][0], radius_m=radius)]
            result = extract_parallel_round_rlgc(request)
            calculated = result["external_inductance_h_per_m"][0][0]
            # Exact bipolar-coordinate solution for a circular wire over plane.
            exact = MU0 / (2 * math.pi) * math.acosh(.01 / radius)
            errors.append(abs(calculated - exact))
            self.assertLess(abs(calculated / exact - 1), .0002)
        self.assertAlmostEqual(errors[0] / errors[1], 4, delta=.004)
        self.assertAlmostEqual(errors[1] / errors[2], 4, delta=.001)

    def test_identity_provenance_no_defaults_and_no_mutation(self):
        request = fixture()
        request.update(harness_id="h", occurrence_id="assembly/a")
        request["wires"][0].update(role="signal", occurrence_id="assembly/a/p")
        before = copy.deepcopy(request)
        result = extract_parallel_round_rlgc(request)
        self.assertEqual(request, before)
        self.assertEqual(result["request_snapshot"], before)
        self.assertEqual(result["wire_metadata"], [{"wire_id": "p", "role": "signal", "occurrence_id": "assembly/a/p"}, {"wire_id": "n"}])
        self.assertEqual(result["provenance"], before["provenance"])
        self.assertFalse(result["production_qualified"])
        self.assertFalse(result["field_coupling_executed"])
        self.assertTrue(result["geometry_rlgc_executed"])
        self.assertEqual(result["model_status"], "approximate")
        json.dumps(result, allow_nan=False)

    def test_permutation_and_horizontal_translation_invariance(self):
        request = fixture()
        original = extract_parallel_round_rlgc(request)["model"]
        request["wires"].reverse()
        for wire in request["wires"]:
            wire["x_m"] += 3
        moved = extract_parallel_round_rlgc(request)["model"]
        self.assertEqual(moved["wire_ids"], ["n", "p"])
        for key in ("r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"):
            np.testing.assert_allclose(moved[key], np.array(original[key])[:, ::-1, ::-1], rtol=1e-13, atol=1e-30)

    def test_unsupported_geometry_frequency_reference_and_magnetic_are_not_models(self):
        edits = [lambda r: r["wires"][0].update(height_m=.001),
                 lambda r: r["wires"][1].update(x_m=-.005),
                 lambda r: r.update(frequency_hz=[1e10]),
                 lambda r: r["reference_plane"].update(kind="finite_lossy_plane"),
                 lambda r: r["wires"][0].update(relative_permeability=2)]
        for edit in edits:
            request = fixture()
            edit(request)
            result = extract_parallel_round_rlgc(request)
            self.assertEqual(result["status"], "unsupported")
            self.assertEqual(result["model_status"], "unsupported")
            self.assertNotIn("model", result)
            self.assertFalse(result["geometry_rlgc_executed"])
            self.assertTrue(result["issues"])

    def test_invalid_missing_unknown_nonfinite_duplicate_and_resource_bounds(self):
        edits = [lambda r: r.pop("reference_plane"), lambda r: r.pop("provenance"),
                 lambda r: r.update(shield={}), lambda r: r["wires"][0].update(twist_pitch_m=.02),
                 lambda r: r["dielectric"].update(conductivity_s_m=1),
                 lambda r: r["reference_plane"].update(thickness_m=.001),
                 lambda r: r["wires"][0].update(radius_m=float("nan")),
                 lambda r: r["wires"][0].update(height_m=True),
                 lambda r: r["wires"][1].update(wire_id="p"),
                 lambda r: r.update(frequency_hz=[1, 1]),
                 lambda r: r.update(frequency_hz=[-1]),
                 lambda r: r.update(frequency_hz=list(range(258))),
                 lambda r: r.update(wires=r["wires"] * 9),
                 lambda r: r["provenance"].update(bad=float("inf")),
                 lambda r: r["provenance"].update(large="x" * 131072)]
        for index, edit in enumerate(edits):
            request = fixture()
            edit(request)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "HARNESS_RLGC_INPUT"):
                extract_parallel_round_rlgc(request)

    def test_cancellation_during_sweep_discards_all_samples(self):
        calls = []
        def cancel():
            calls.append(True)
            return len(calls) == 4
        with self.assertRaisesRegex(ValueError, "CANCELLED"):
            extract_parallel_round_rlgc(fixture(), cancel_check=cancel)
        self.assertEqual(len(calls), 4)

    def test_maximum_admitted_dimensions_remain_finite_and_passive(self):
        request = fixture()
        request["wires"] = [dict(request["wires"][0], wire_id=str(i), x_m=.01 * i) for i in range(16)]
        request["frequency_hz"] = [100000 * i for i in range(257)]
        result = extract_parallel_round_rlgc(request)
        self.assertEqual(result["status"], "completed")
        for key in ("r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"):
            matrix = np.array(result["model"][key])
            self.assertEqual(matrix.shape, (257, 16, 16))
            self.assertTrue(np.all(np.isfinite(matrix)))
            self.assertGreaterEqual(np.min(np.linalg.eigvalsh(matrix)), 0)


if __name__ == "__main__":
    unittest.main()
