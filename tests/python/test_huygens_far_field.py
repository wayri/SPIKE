# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent analytical Hertzian current-element tests; no solver fixtures."""
import unittest
import numpy as np

from python.spike_core.huygens_far_field import box_samples, huygens_far_field, FarFieldError

MU = 4e-7 * np.pi
EPS = 8.8541878128e-12
FREQ = 299792458.
K = 2 * np.pi * FREQ * np.sqrt(MU * EPS)
ETA = np.sqrt(MU / EPS)


def dipole_request(n=16, translation=(0., 0., 0.), phase=1.):
    shift = np.array(translation)
    bounds = np.array([[-.2, .2]] * 3) + shift[:, None]
    e, h = {}, {}
    for name, (xyz, _, _) in box_samples(bounds, [n]*3).items():
        # z-directed Hertzian current moment I*l = 1 A m. Radial and theta
        # components include induction/electrostatic terms, not just far fields.
        rel = xyz - shift
        r = np.linalg.norm(rel, axis=-1)
        rhat = rel / r[..., None]
        cost = rhat[..., 2]
        transverse = np.array([0., 0., 1.]) - cost[..., None] * rhat
        outgoing = np.exp(-1j*K*r)
        er = ETA/(2*np.pi) * cost * (1/r**2 + 1/(1j*K*r**3)) * outgoing
        et_over_sin = ETA/(4*np.pi) * (1j*K/r + 1/r**2 + 1/(1j*K*r**3)) * outgoing
        hp_over_sin = (1j*K/r + 1/r**2) * outgoing / (4*np.pi)
        e[name] = phase * (er[..., None] * rhat - et_over_sin[..., None] * transverse)
        h[name] = phase * hp_over_sin[..., None] * np.cross([0., 0., 1.], rhat)
    return dict(bounds_m=bounds, divisions=[n]*3, electric_fields=e, magnetic_fields=h,
                frequency_hz=FREQ, permittivity_f_per_m=EPS, permeability_h_per_m=MU,
                homogeneous_lossless_exterior=True, directions=np.array([[1., 0., 0.], [0., 0., 1.]]))


class HuygensFarFieldTests(unittest.TestCase):
    def test_unrepresentable_scalar_is_structured_error(self):
        request=dipole_request(2)
        request["frequency_hz"]=10**1000
        with self.assertRaises(FarFieldError):
            huygens_far_field(**request)

    def test_json_cli_example_and_strict_input(self):
        import json
        from pathlib import Path
        from scripts.run_huygens_far_field import solve
        root=Path(__file__).resolve().parents[2]
        request=json.loads((root/"examples/em/huygens_dipole_request.json").read_text())
        result=solve(request)
        self.assertEqual(result["status"],"completed",result)
        self.assertFalse(result["production_qualified"])
        json.dumps(result,allow_nan=False)
        request["extra"]=True
        self.assertEqual(solve(request)["status"],"blocked")

    def test_complex_amplitude_and_second_order_convergence(self):
        errors = []
        exact = np.array([0., 0., -1j*K*ETA/(4*np.pi)])
        for n in (6, 12, 24):
            got = huygens_far_field(**dipole_request(n))["electric_amplitude_v"]
            errors.append(np.linalg.norm(got[0] - exact)/np.linalg.norm(exact))
            self.assertLess(np.linalg.norm(got[1]), 1e-10)
        self.assertLess(errors[-1], .001)
        self.assertTrue(all(np.log2(a/b) > 1.9 for a, b in zip(errors, errors[1:])))

    def test_integrated_power_directivity_and_transversality(self):
        z, w = np.polynomial.legendre.leggauss(12)
        phis = np.arange(16)*2*np.pi/16
        dirs = np.array([[np.sqrt(1-t*t)*np.cos(p), np.sqrt(1-t*t)*np.sin(p), t] for t in z for p in phis])
        request = dipole_request(24)
        request["directions"] = dirs
        result = huygens_far_field(**request)
        power = np.sum(result["radiation_intensity_w_per_sr"] * np.repeat(w, 16))*2*np.pi/16
        expected = ETA*K*K/(12*np.pi)
        self.assertAlmostEqual(power/expected, 1., delta=.002)
        equator = huygens_far_field(**dipole_request(24))["radiation_intensity_w_per_sr"][0]
        self.assertAlmostEqual(4*np.pi*equator/power, 1.5, delta=.002)
        self.assertLess(np.max(np.abs(np.sum(dirs*result["electric_amplitude_v"], axis=1))), 1e-10)

    def test_translation_and_complex_source_phase(self):
        base = huygens_far_field(**dipole_request())["electric_amplitude_v"]
        phase = np.exp(.7j)
        moved = huygens_far_field(**dipole_request(translation=(.13, -.07, .04), phase=phase))["electric_amplitude_v"]
        np.testing.assert_allclose(moved[0], base[0]*phase*np.exp(1j*K*.13), rtol=1e-12, atol=1e-12)

    def test_closed_surface_and_material_required(self):
        request = dipole_request(2)
        del request["electric_fields"]["x_min"]
        with self.assertRaisesRegex(FarFieldError, "E_INPUT"):
            huygens_far_field(**request)
        request = dipole_request(2)
        request["homogeneous_lossless_exterior"] = False
        with self.assertRaisesRegex(FarFieldError, "E_UNSUPPORTED"):
            huygens_far_field(**request)

    def test_reject_nonfinite_shape_and_nonunit_directions(self):
        for value in (np.array([[2., 0., 0.]]), np.array([[np.nan, 0., 0.]]), np.zeros((2, 2))):
            request = dipole_request(2)
            request["directions"] = value
            with self.assertRaises(FarFieldError):
                huygens_far_field(**request)
        request = dipole_request(2)
        request["electric_fields"]["x_min"][0, 0, 0] = np.inf
        with self.assertRaises(FarFieldError):
            huygens_far_field(**request)

    def test_budgets_and_cancellation(self):
        with self.assertRaisesRegex(FarFieldError, "E_RESOURCE"):
            box_samples([[-1., 1.]]*3, [1000]*3)
        with self.assertRaisesRegex(FarFieldError, "E_CANCELLED"):
            huygens_far_field(**dipole_request(2), cancelled=lambda: True)
        calls = []
        def cancel_later():
            calls.append(1)
            return len(calls) > 7
        with self.assertRaisesRegex(FarFieldError, "E_CANCELLED"):
            huygens_far_field(**dipole_request(2), cancelled=cancel_later)

    def test_strict_scalar_grid_and_work_validation(self):
        for divisions in (2, [True, 2, 2], [2., 2, 2], [0, 2, 2]):
            with self.assertRaises(FarFieldError):
                box_samples([[-1., 1.]]*3, divisions)
        for frequency in (True, "100", 0., float("inf")):
            request = dipole_request(2)
            request["frequency_hz"] = frequency
            with self.assertRaises(FarFieldError):
                huygens_far_field(**request)
        request = dipole_request(40)
        request["directions"] = np.tile([1., 0., 0.], (4096, 1))
        with self.assertRaisesRegex(FarFieldError, "E_RESOURCE"):
            huygens_far_field(**request)

    def test_zero_fields_and_truthful_scope(self):
        request = dipole_request(2)
        for fields in (request["electric_fields"], request["magnetic_fields"]):
            for values in fields.values():
                values[:] = 0
        result = huygens_far_field(**request)
        self.assertFalse(result["production_qualified"])
        self.assertEqual(np.max(result["radiation_intensity_w_per_sr"]), 0.)


if __name__ == "__main__":
    unittest.main()
