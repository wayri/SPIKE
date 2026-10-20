# SPDX-License-Identifier: Apache-2.0
"""Independent continuous coupled mean-flow/SA verification and joint gates."""
import copy
import json
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.enclosure_rans_research import (
    CONTRACT, solve_enclosure_rans_research,
)
from python.spike_core.enclosure_symmetric_stress import (
    CONTRACT as STRESS_CONTRACT, solve_enclosure_symmetric_stress,
)
from tests.python.test_enclosure_sa_transport import manufactured_request as scalar_fixture


def exact_mean(xyz, *, q_amplitude=1.92, nu=.01, speed=10.):
    """Differentiate continuous polynomial curl and viscosity, not matrices."""
    shape = xyz[0].shape
    b = [t*(1.-t) for t in xyz]
    db = [1.-2.*t for t in xyz]
    factors = [[v*v, 2.*v*d, 2.*d*d-4.*v, -12.*d] for v, d in zip(b, db)]
    terms = (((speed, (0, 1, 0)),), ((-speed, (1, 0, 0)),), ())

    def derivative(component, orders):
        total = np.zeros(shape)
        for coefficient, powers in terms[component]:
            value = np.full(shape, coefficient)
            for axis in range(3):
                value *= factors[axis][powers[axis]+orders[axis]]
            total += value
        return total

    velocity = np.stack([derivative(a, (0, 0, 0)) for a in range(3)], axis=-1)
    jacobian = np.zeros(shape+(3, 3))
    for a in range(3):
        for j in range(3):
            order = [0]*3; order[j] = 1
            jacobian[..., a, j] = derivative(a, order)
    modulation = 1.+.5*xyz[0]+.3*xyz[1]
    q = q_amplitude*b[0]*b[1]*b[2]*modulation
    gradq = [q_amplitude*b[(a+1)%3]*b[(a+2)%3]
             *(db[a]*modulation+b[a]*(.5, .3, 0.)[a]) for a in range(3)]
    chi = q/nu
    damping = chi**3/(chi**3+7.1**3)
    viscosity = nu+q*damping  # rho=1 fixture
    # d(q*fv1(q/nu))/dq = fv1*(4-3*fv1), derived by quotient/product rules.
    gradmu = [damping*(4.-3.*damping)*v for v in gradq]
    force = np.zeros(shape+(3,))
    for a in range(3):
        for j in range(3):
            order = [0]*3; order[j] = 2
            force[..., a] += (velocity[..., j]*jacobian[..., a, j]
                             -viscosity*derivative(a, order)
                             -(jacobian[..., a, j]+jacobian[..., j, a])*gradmu[j])
        force[..., a] += .001*db[a]*b[(a+1)%3]*b[(a+2)%3]
    return velocity, force, q, viscosity


def fixture(n=4, *, seed=.5, q_amplitude=1.92):
    scalar, _ = scalar_fixture(n, seed=seed, q_amplitude=q_amplitude)
    grid = scalar["grid"]
    _, force, exactq, _ = exact_mean(
        np.meshgrid(*grid["cell_centers_m"], indexing="ij"), q_amplitude=q_amplitude)
    controls = {"max_iterations": 60, "relaxation": 1., "relative_tolerance": 1e-11}
    return {"contract": CONTRACT, "grid": grid, "density_kg_m3": 1.,
            "molecular_kinematic_viscosity_m2_s": .01,
            "initial_nu_tilde_m2_s": seed*exactq,
            "manufactured_momentum_source_n_m3": force,
            "manufactured_sa_source_m2_s2": scalar["manufactured_source_m2_s2"],
            "outer_controls": {"max_iterations": 40, "relaxation": 1., "relative_tolerance": 1e-9},
            "momentum_controls": dict(controls), "sa_controls": dict(controls)}, exactq


def velocity_error(request, result):
    grid = request["grid"]
    error, norm = 0., 0.
    for axis in range(3):
        coordinates = list(grid["cell_centers_m"])
        coordinates[axis] = grid["axes_m"][axis]
        expected = exact_mean(np.meshgrid(*coordinates, indexing="ij"))[0][..., axis]
        widths = list(grid["cell_widths_m"])
        widths[axis] = np.r_[widths[axis][0]/2.,
                             .5*(widths[axis][:-1]+widths[axis][1:]),
                             widths[axis][-1]/2.]
        volume = widths[0][:, None, None]*widths[1][None, :, None]*widths[2][None, None, :]
        actual = np.asarray(result["fields"]["face_velocity_m_s"][axis])
        error += float(np.sum(volume*(actual-expected)**2))
        norm += float(np.sum(volume*expected**2))
    return math.sqrt(error/norm)


def frozen_molecular_request(request, viscosity=None):
    return {"contract": STRESS_CONTRACT, "grid": request["grid"],
            "fluid_mask": np.ones(request["grid"]["shape"], bool),
            "body_force_n_m3": request["manufactured_momentum_source_n_m3"],
            "dynamic_viscosity_pa_s": (np.full(request["grid"]["shape"], .01)
                                       if viscosity is None else viscosity),
            "density_kg_m3": 1., "nonlinear_controls": request["momentum_controls"]}


class CoupledRANSResearchTests(unittest.TestCase):
    def solve(self, request):
        result = solve_enclosure_rans_research(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertLessEqual(result["diagnostics"]["joint_relative_residual"], 1e-9)
        self.assertTrue(result["research_only"])
        self.assertFalse(result["production_qualified"])
        return result

    def test_fixed_three_grid_joint_continuum_acceptance(self):
        velocity_errors, q_errors = [], []
        for n in (4, 8, 12):
            request, qexact = fixture(n)
            result = self.solve(request)
            q = np.asarray(result["fields"]["nu_tilde_m2_s"])
            velocity_errors.append(velocity_error(request, result))
            q_errors.append(float(np.linalg.norm(q-qexact)/np.linalg.norm(qexact)))
            self.assertGreater(result["diagnostics"]["maximum_eddy_to_molecular_ratio"], .1)
            self.assertGreater(result["diagnostics"]["outer_iterations"], 1)
            self.assertLessEqual(result["diagnostics"]["molecular_reynolds_upper_bound"], 20.)
            self.assertEqual(result["diagnostics"]["residual_state"], "same_u_p_updated_q_reassembled")
            self.assertLessEqual(result["diagnostics"]["relative_energy_defect"], 1e-9)
            self.assertLessEqual(result["diagnostics"]["relative_strain_energy_defect"], 1e-9)
            self.assertLessEqual(result["diagnostics"]["last_mean_inner_scaled_condition_estimate"], 1e10)
            self.assertLessEqual(result["diagnostics"]["last_mean_inner_relative_residual"], 1e-11)
        for errors, tolerance in ((velocity_errors, .05), (q_errors, .1)):
            self.assertLess(errors[-1], tolerance, errors)
            orders = [math.log(errors[i]/errors[i+1])/math.log((8, 12)[i]/(4, 8)[i])
                      for i in range(2)]
            self.assertTrue(all(v >= .7 for v in orders), (errors, orders))

    def test_closure_feedback_materially_changes_velocity(self):
        request, _ = fixture(4)
        coupled = self.solve(request)
        uncoupled = solve_enclosure_symmetric_stress(frozen_molecular_request(request))
        self.assertEqual(uncoupled["status"], "completed", uncoupled)
        delta, norm = 0., 0.
        for left, right in zip(coupled["fields"]["face_velocity_m_s"], uncoupled["fields"]["face_velocity_m_s"]):
            left, right = np.asarray(left), np.asarray(right)
            delta += float(np.sum((left-right)**2)); norm += float(np.sum(left**2))
        self.assertGreater(math.sqrt(delta/norm), .01)
        self.assertGreater(coupled["diagnostics"]["outer_residual_history"][0]["momentum_relative_residual"], 1e-3)

    def test_zero_closure_matches_molecular_mean_flow(self):
        request, _ = fixture(4, q_amplitude=0.)
        result = self.solve(request)
        reference = solve_enclosure_symmetric_stress(frozen_molecular_request(request))
        self.assertEqual(reference["status"], "completed", reference)
        np.testing.assert_array_equal(result["fields"]["nu_tilde_m2_s"], 0.)
        for actual, expected in zip(result["fields"]["face_velocity_m_s"], reference["fields"]["face_velocity_m_s"]):
            np.testing.assert_allclose(actual, expected, rtol=2e-9, atol=1e-14)

    def test_json_roundtrip_equivalence_and_forged_grid_rejection(self):
        request, _ = fixture(4)
        reference = self.solve(request)
        serialized = json.loads(json.dumps(
            request, default=lambda value: value.tolist() if isinstance(value, np.ndarray) else value.item()))
        retained = copy.deepcopy(serialized)
        actual = self.solve(serialized)
        self.assertEqual(serialized, retained)
        for key in ("nu_tilde_m2_s", "eddy_kinematic_viscosity_m2_s", "pressure_pa"):
            np.testing.assert_array_equal(actual["fields"][key], reference["fields"][key])
        for left, right in zip(actual["fields"]["face_velocity_m_s"],
                               reference["fields"]["face_velocity_m_s"]):
            np.testing.assert_array_equal(left, right)
        mutations = {
            "cell_volumes_m3": lambda grid: grid["cell_volumes_m3"][0][0].__setitem__(0, .123),
            "cell_centers_m": lambda grid: grid["cell_centers_m"][0].__setitem__(0, .123),
            "cell_widths_m": lambda grid: grid["cell_widths_m"][0].__setitem__(0, .123),
            "face_areas_m2": lambda grid: grid["face_areas_m2"][0][0][0].__setitem__(0, .123),
            "parent_indices": lambda grid: grid["parent_indices"][0].__setitem__(0, 1),
        }
        for field, mutate in mutations.items():
            forged = copy.deepcopy(retained)
            mutate(forged["grid"])
            result = solve_enclosure_rans_research(forged)
            self.assertEqual(result["status"], "blocked", result)
            self.assertIn(field, str(result["issues"]))
            self.assertNotIn("fields", result)

    def test_alternate_seed_and_actual_relaxed_state(self):
        request, _ = fixture(4, seed=.2)
        reference = self.solve(request)
        request, _ = fixture(4, seed=2.)
        request["outer_controls"]["relaxation"] = .5
        result = self.solve(request)
        np.testing.assert_allclose(result["fields"]["nu_tilde_m2_s"],
                                   reference["fields"]["nu_tilde_m2_s"], rtol=2e-8, atol=0.)
        self.assertGreater(result["diagnostics"]["outer_iterations"], reference["diagnostics"]["outer_iterations"])

    def test_dimensional_time_scaling_has_no_residual_floor(self):
        request, _ = fixture(4)
        reference = self.solve(request)
        for scale in (1e-8, 1e8):
            scaled = copy.deepcopy(request)
            scaled["molecular_kinematic_viscosity_m2_s"] *= scale
            scaled["initial_nu_tilde_m2_s"] *= scale
            scaled["manufactured_momentum_source_n_m3"] *= scale**2
            scaled["manufactured_sa_source_m2_s2"] *= scale**2
            result = self.solve(scaled)
            np.testing.assert_allclose(np.asarray(result["fields"]["nu_tilde_m2_s"])/scale,
                                       reference["fields"]["nu_tilde_m2_s"], rtol=2e-8, atol=0.)
            for actual, expected in zip(result["fields"]["face_velocity_m_s"], reference["fields"]["face_velocity_m_s"]):
                np.testing.assert_allclose(np.asarray(actual)/scale, expected, rtol=1e-7, atol=1e-14)

    def test_outer_exhaustion_inner_exhaustion_cancel_and_malformed(self):
        request, _ = fixture(4)
        mutations = [
            lambda r: r["outer_controls"].__setitem__("max_iterations", 1),
            lambda r: r["momentum_controls"].__setitem__("max_iterations", 1),
            lambda r: r["sa_controls"].__setitem__("max_iterations", 1),
            lambda r: r["initial_nu_tilde_m2_s"].fill(-1.),
            lambda r: r["initial_nu_tilde_m2_s"].fill(float("nan")),
            lambda r: r.__setitem__("molecular_kinematic_viscosity_m2_s", 0.),
            lambda r: r.__setitem__("unknown", True),
            lambda r: r["grid"].__setitem__("shape", (10**9, 10**9, 10**9)),
        ]
        for mutation in mutations:
            bad = copy.deepcopy(request); mutation(bad)
            result = solve_enclosure_rans_research(bad)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        result = solve_enclosure_rans_research(request, cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)
        polls = [0]
        def late_cancel():
            polls[0] += 1
            return polls[0] > 30
        result = solve_enclosure_rans_research(request, cancel_check=late_cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)
        with patch("python.spike_core.enclosure_rans_research.MAX_FIELD_BYTES", 1):
            result = solve_enclosure_rans_research(request)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("2 MiB", str(result["issues"]))
        self.assertNotIn("fields", result)

    def test_original_molecular_reynolds_not_effective_viscosity(self):
        request, _ = fixture(4)
        # Actual standalone variable-viscosity solve passes its effective basis;
        # the identical mean problem must fail the original molecular gate here.
        request["initial_nu_tilde_m2_s"] = np.full((4, 4, 4), .1)
        chi3 = 10.**3
        mu = .01+.1*chi3/(chi3+7.1**3)
        request["manufactured_momentum_source_n_m3"] *= 200.
        effective = solve_enclosure_symmetric_stress(frozen_molecular_request(
            request, np.full((4, 4, 4), mu)))
        self.assertEqual(effective["status"], "completed", effective)
        self.assertGreater(effective["diagnostics"]["reynolds_upper_bound"]*mu/.01, 20.)
        result = solve_enclosure_rans_research(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertIn("Reynolds", str(result["issues"]))
        self.assertNotIn("fields", result)

    def test_same_state_gate_rejects_fake_inner_sa_success(self):
        request, _ = fixture(4)
        request["outer_controls"]["max_iterations"] = 2
        def false_success(req, **kwargs):
            return {"status": "completed", "fields": {"nu_tilde_m2_s": np.zeros((4, 4, 4)).tolist()},
                    "diagnostics": {"iterations": 1, "residual_reference_m5_s2": 1.}}
        with patch("python.spike_core.enclosure_rans_research.solve_enclosure_sa_transport",
                   side_effect=false_success):
            result = solve_enclosure_rans_research(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertNotIn("fields", result)


if __name__ == "__main__":
    unittest.main()
