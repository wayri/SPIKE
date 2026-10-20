# SPDX-License-Identifier: Apache-2.0
"""Independent rotating-frame continuum and equilibrium checks."""
import copy
import unittest

import numpy as np
from scipy.sparse import diags

from python.spike_core.enclosure_rectilinear_momentum import (
    _assemble, _iteration, solve_enclosure_rectilinear_momentum,
)
from python.spike_core.enclosure_refinement import build_enclosure_grid
from python.spike_core.enclosure_rotating_frame import (
    CONTRACT, _coriolis, solve_enclosure_rotating_frame,
)
from python.spike_core.enclosure_stokes import EnclosureFlowError
from tests.python.test_enclosure_laminar import exact_fields
from tests.python.test_enclosure_rectilinear_momentum import fixture as base_fixture


def fixture(n=4, refined=False):
    request = base_fixture(n, refined=refined)
    request.update(contract=CONTRACT, angular_velocity_rad_s=[.4, -.7, 1.1],
                   rotation_origin_m=[.2, .3, .4])
    return request


def manufactured(n):
    request = fixture(n)
    xyz = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
    velocity, forcing, _ = exact_fields(xyz)
    request["body_force_n_m3"] = forcing + 2*np.cross(request["angular_velocity_rad_s"], velocity)
    result = solve_enclosure_rotating_frame(request)
    if result["status"] != "completed":
        raise AssertionError(result)
    error, norm = 0., 0.
    for axis in range(3):
        coordinates = list(request["grid"]["cell_centers_m"])
        coordinates[axis] = request["grid"]["axes_m"][axis]
        exact = exact_fields(np.meshgrid(*coordinates, indexing="ij"))[0][..., axis]
        actual = np.asarray(result["fields"]["face_velocity_m_s"][axis])
        error += np.linalg.norm(actual-exact)**2
        norm += np.linalg.norm(exact)**2
    return np.sqrt(error/norm), result, request


class RotatingFrameTests(unittest.TestCase):
    def test_rigid_corotation_relative_zero_and_physical_pressure(self):
        request = fixture(refined=True)
        request["angular_velocity_rad_s"] = [0., 0., 2.]
        request["density_kg_m3"] = 1.5
        request["fluid_mask"][2, :, :] = False
        result = solve_enclosure_rotating_frame(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["diagnostics"]["fluid_components"], 2)
        for field in result["fields"]["face_velocity_m_s"]:
            np.testing.assert_array_equal(field, 0.)
        np.testing.assert_array_equal(result["fields"]["reduced_pressure_pa"], 0.)
        # Independent scalar rigid-rotation pressure: rho*Omega_z^2*r_perp^2/2.
        x, y, _ = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
        radius_squared = (x-.2)**2+(y-.3)**2
        pressure = np.asarray(result["fields"]["pressure_pa"])
        for slab in (slice(0, 2), slice(3, None)):
            expected = 3.*radius_squared[slab]
            expected -= expected.flat[0]
            np.testing.assert_allclose(pressure[slab], expected, atol=1e-14)
        np.testing.assert_array_equal(pressure[2], 0.)

    def test_coriolis_weighted_skew_and_right_hand_axis_sign(self):
        request = fixture(refined=True)
        request["fluid_mask"][1:3, 2:4, 2:4] = False
        system = _assemble(request["grid"], request["fluid_mask"], request["body_force_n_m3"], 1.)
        rng = np.random.default_rng(8115)
        trial = rng.normal(size=len(system["faces"]))
        omega = np.array([.4, -.7, 1.1])
        operator, interpolation = _coriolis(system, omega, 1.7)
        reverse, _ = _coriolis(system, -omega, 1.7)
        np.testing.assert_allclose((operator+operator.T).toarray(), 0., atol=1e-16)
        np.testing.assert_allclose((operator+reverse).toarray(), 0., atol=1e-16)
        pointwise = (operator @ trial)/system["dual_volumes"]
        self.assertLess(abs(trial @ (system["dual_volumes"]*pointwise)), 1e-13)
        cell = (interpolation @ trial).reshape(-1, 3)
        # Cross product independently evaluated at cell centers; projection
        # back tests volume weighting and the required factor of two.
        expected = interpolation.T @ (3.4*system["cell_volumes"][:, None]*np.cross(omega, cell)).ravel()
        np.testing.assert_allclose(operator @ trial, expected, atol=1e-15)
        for axis in range(3):
            rotation_axis = np.eye(3)[axis]
            velocity_axis = np.eye(3)[(axis+1) % 3]
            sign_operator, _ = _coriolis(system, rotation_axis, 1.)
            face_trial = np.array([velocity_axis[a] for a, _, _ in system["faces"]])
            response = sign_operator @ face_trial
            for value, (component, _, _) in zip(response, system["faces"]):
                if component == (axis+2) % 3:
                    self.assertGreaterEqual(value, 0.)
                else:
                    self.assertEqual(value, 0.)
            self.assertGreater(np.linalg.norm(response), 0.)

    def test_three_component_rotating_continuum_mms_second_order(self):
        runs = [manufactured(n) for n in (4, 8, 12)]
        errors = [run[0] for run in runs]
        for i, ratio in enumerate((2., 1.5)):
            self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), 1.8)
        self.assertLess(errors[-1], .02)
        for _, result, _ in runs:
            d = result["diagnostics"]
            self.assertGreater(d["reynolds_upper_bound"], 2.)
            self.assertLessEqual(d["reynolds_upper_bound"], 20.)
            self.assertLess(d["momentum_relative_residual"], 1e-10)
            self.assertLess(abs(d["coriolis_power_w"]), 1e-11)
            self.assertLess(d["relative_energy_defect"], 1e-9)

    def test_rotation_changes_solved_momentum_not_only_pressure(self):
        _, rotating, request = manufactured(4)
        request["contract"] = "spike/enclosure-rectilinear-momentum/v1"
        request.pop("angular_velocity_rad_s")
        request.pop("rotation_origin_m")
        inertial = solve_enclosure_rectilinear_momentum(request)
        self.assertEqual(inertial["status"], "completed", inertial)
        difference = sum(np.linalg.norm(np.asarray(a)-np.asarray(b))
                         for a, b in zip(rotating["fields"]["face_velocity_m_s"],
                                         inertial["fields"]["face_velocity_m_s"]))
        self.assertGreater(difference, .01)

    def test_zero_rotation_preserves_default_solver(self):
        request = fixture()
        request["angular_velocity_rad_s"] = [0., 0., 0.]
        xyz = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
        request["body_force_n_m3"] = exact_fields(xyz)[1]
        rotating = solve_enclosure_rotating_frame(request)
        baseline_request = copy.deepcopy(request)
        baseline_request["contract"] = "spike/enclosure-rectilinear-momentum/v1"
        baseline_request.pop("angular_velocity_rad_s")
        baseline_request.pop("rotation_origin_m")
        baseline = solve_enclosure_rectilinear_momentum(baseline_request)
        self.assertEqual(rotating["status"], "completed", rotating)
        for a, b in zip(rotating["fields"]["face_velocity_m_s"], baseline["fields"]["face_velocity_m_s"]):
            np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(rotating["fields"]["pressure_pa"], baseline["fields"]["pressure_pa"])

    def test_large_rotation_origin_does_not_cancel_pressure_difference(self):
        request = fixture()
        request.update(angular_velocity_rad_s=[0., 0., 1.], rotation_origin_m=[1e12, -2e12, 0.])
        result = solve_enclosure_rotating_frame(request)
        self.assertEqual(result["status"], "completed", result)
        x, y, _ = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
        dx, dy = x-x.flat[0], y-y.flat[0]
        expected = (x.flat[0]-1e12)*dx + (y.flat[0]+2e12)*dy + .5*(dx*dx+dy*dy)
        np.testing.assert_allclose(result["fields"]["pressure_pa"], expected, rtol=2e-15, atol=1e-4)
        self.assertGreater(np.max(np.abs(result["fields"]["pressure_pa"])), 1e12)

    def test_translated_frame_covariance(self):
        _, reference, request = manufactured(4)
        translation = np.array([10., -7., 3.])
        request["grid"] = build_enclosure_grid({
            "shape": [4]*3, "spacing_m": [.25]*3,
            "origin_m": translation.tolist(), "local_refinement": []})
        request["rotation_origin_m"] = (np.array(request["rotation_origin_m"])+translation).tolist()
        actual = solve_enclosure_rotating_frame(request)
        self.assertEqual(actual["status"], "completed", actual)
        for a, b in zip(actual["fields"]["face_velocity_m_s"], reference["fields"]["face_velocity_m_s"]):
            np.testing.assert_array_equal(a, b)
        np.testing.assert_allclose(actual["fields"]["pressure_pa"], reference["fields"]["pressure_pa"], atol=1e-14)

    def test_private_linear_skew_rejects_non_skew_wrong_shape_and_nonfinite(self):
        request = fixture()
        system = _assemble(request["grid"], request["fluid_mask"], request["body_force_n_m3"], 1.)
        n = len(system["faces"])
        variants = [diags(np.ones(n)), diags(np.ones(n+1)),
                    diags(np.full(n, np.nan)), np.zeros((n, n))]
        for operator in variants:
            with self.assertRaises(EnclosureFlowError):
                _iteration(system, 1., request["nonlinear_controls"], .25, 1., 1., None,
                           linear_skew=operator)

    def test_fail_closed_unknown_frame_overflow_rotation_number_and_cancellation(self):
        for key, value in (("angular_velocity_rad_s", [0., True, 1.]),
                           ("angular_velocity_rad_s", [0., 0., 11.]),
                           ("angular_velocity_rad_s", [float("inf"), 0., 0.]),
                           ("rotation_origin_m", [1e200, 0., 0.]),
                           ("moving_wall", True), ("contract", "unknown")):
            request = fixture()
            request[key] = value
            result = solve_enclosure_rotating_frame(request)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        result = solve_enclosure_rotating_frame(fixture(), cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)


if __name__ == "__main__":
    unittest.main()
