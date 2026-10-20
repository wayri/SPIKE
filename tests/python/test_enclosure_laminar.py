# SPDX-License-Identifier: Apache-2.0
"""Analytical curl-field oracle, separate from the discrete flow operators."""
import copy
import unittest

import numpy as np

from python.spike_core.enclosure_laminar import CONTRACT, _advection, solve_enclosure_laminar
from python.spike_core.enclosure_stokes import _assemble


def fixture(n=4):
    return {"contract": CONTRACT, "shape": [n] * 3, "spacing_m": [1/n] * 3,
            "fluid_mask": np.ones((n, n, n), bool).tolist(),
            "body_force_n_m3": np.zeros((n, n, n, 3)).tolist(),
            "dynamic_viscosity_pa_s": 1., "density_kg_m3": 1.,
            "nonlinear_controls": {"max_iterations": 60, "relaxation": 1., "relative_tolerance": 1e-10}}


def exact_fields(xyz, amplitude=1.):
    # A=(.3,.5,1)*amp*product(sin(pi*x_i)^2), u=curl(A).
    # Derivatives of each analytic tensor factor supply f=rho*(u.grad)u-mu*lap(u)+grad(p).
    shape = xyz[0].shape
    p = np.pi
    derivatives = [[np.sin(p*x)**2, p*np.sin(2*p*x), 2*p*p*np.cos(2*p*x),
                    -4*p**3*np.sin(2*p*x)] for x in xyz]
    terms = [[(1., (0, 1, 0)), (-.5, (0, 0, 1))],
             [(.3, (0, 0, 1)), (-1., (1, 0, 0))],
             [(.5, (1, 0, 0)), (-.3, (0, 1, 0))]]

    def derivative(component, extra):
        value = np.zeros(shape)
        for coefficient, orders in terms[component]:
            factor = np.ones(shape) * (amplitude * coefficient)
            for axis in range(3):
                factor *= derivatives[axis][orders[axis] + extra[axis]]
            value += factor
        return value

    velocity = np.stack([derivative(a, (0, 0, 0)) for a in range(3)], axis=-1)
    forcing = np.zeros(shape + (3,))
    for component in range(3):
        for direction in range(3):
            first, second = [0]*3, [0]*3
            first[direction], second[direction] = 1, 2
            forcing[..., component] += (velocity[..., direction] * derivative(component, first)
                                       - derivative(component, second))
        # Nonzero, smooth pressure independent of velocity.
        pressure_gradient = np.ones(shape) * (.2 * p)
        for axis in range(3):
            pressure_gradient *= np.cos(p*xyz[axis]) if axis == component else np.sin(p*xyz[axis])
        forcing[..., component] += pressure_gradient
    pressure = .2 * np.prod([np.sin(p*x) for x in xyz], axis=0)
    return velocity, forcing, pressure


def manufactured(n, amplitude=1.):
    request = fixture(n)
    centers = (np.arange(n) + .5) / n
    _, force, pressure = exact_fields(np.meshgrid(centers, centers, centers, indexing="ij"), amplitude)
    request["body_force_n_m3"] = force.tolist()
    result = solve_enclosure_laminar(request)
    if result["status"] != "completed":
        raise AssertionError(result)
    error, norm = 0., 0.
    for axis in range(3):
        coordinates = [centers] * 3
        coordinates[axis] = np.arange(n+1) / n
        reference = exact_fields(np.meshgrid(*coordinates, indexing="ij"), amplitude)[0][..., axis]
        actual = np.asarray(result["fields"]["face_velocity_m_s"][axis])
        error += np.linalg.norm(actual-reference)**2
        norm += np.linalg.norm(reference)**2
    computed_p = np.asarray(result["fields"]["pressure_pa"])
    pressure_error = np.linalg.norm((computed_p-computed_p.mean())-(pressure-pressure.mean())) / n**1.5
    return np.sqrt(error/norm), pressure_error, result


class EnclosureLaminarTests(unittest.TestCase):
    def test_zero_and_hydrostatic_force(self):
        for vector in ([0., 0., 0.], [1., -.5, .25]):
            request = fixture()
            request["body_force_n_m3"] = np.broadcast_to(vector, (4, 4, 4, 3)).tolist()
            result = solve_enclosure_laminar(request)
            self.assertEqual(result["status"], "completed", result)
            for values in result["fields"]["face_velocity_m_s"]:
                self.assertLess(np.max(np.abs(values)), 1e-14)
            pressure = np.asarray(result["fields"]["pressure_pa"])
            for axis in range(3):
                np.testing.assert_allclose(np.diff(pressure, axis=axis), vector[axis]/4, atol=1e-13)

    def test_advection_skew_and_three_dimensional_interpolation(self):
        shape, h = (4, 3, 5), np.array([.2, .3, .1])
        _, faces, _, _, _, _ = _assemble(shape, h, np.ones(shape, bool), np.zeros(shape+(3,)), 1., None)
        rng = np.random.default_rng(3126)
        velocity = rng.normal(size=len(faces))
        convection = _advection(faces, h, velocity, 1.3)
        np.testing.assert_array_equal((convection + convection.T).toarray(), 0)
        trial = rng.normal(size=len(faces))
        self.assertLess(abs(trial @ (convection @ trial)), 1e-12)
        ids = {(axis, c): i for i, (axis, c, _) in enumerate(faces)}
        # x momentum across a z dual face transports the mean of its two z velocities.
        i, j = ids[(0, (1, 1, 1))], ids[(0, (1, 1, 2))]
        expected = 1.3 * (velocity[ids[(2, (1, 1, 1))]] + velocity[ids[(2, (2, 1, 1))]]) / (4*h[2])
        self.assertEqual(convection[i, j], expected)

    def test_three_component_inertial_continuum_refinement(self):
        runs = [manufactured(n) for n in (4, 8, 12)]
        errors = [run[0] for run in runs]
        for i, ratio in enumerate((2., 1.5)):
            self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), 1.8)
        self.assertLess(errors[-1], .04)
        self.assertLess(runs[-1][1], runs[0][1])
        for _, _, result in runs:
            diagnostics = result["diagnostics"]
            self.assertGreater(diagnostics["reynolds_upper_bound"], 2.)
            self.assertGreater(diagnostics["iterations"], 2)
            self.assertLess(diagnostics["momentum_relative_residual"], 1e-10)
            self.assertLess(diagnostics["maximum_divergence_s_inv"], 1e-10)
            self.assertLess(abs(diagnostics["advective_power_w"]), 1e-10)
            self.assertLess(abs(diagnostics["pressure_power_w"]), 1e-10)
            self.assertLess(diagnostics["relative_energy_defect"], 1e-9)

    def test_nonconvergence_never_publishes_fields(self):
        request = fixture()
        centers = (np.arange(4)+.5)/4
        request["body_force_n_m3"] = exact_fields(np.meshgrid(centers, centers, centers, indexing="ij"))[1].tolist()
        request["nonlinear_controls"]["max_iterations"] = 1
        result = solve_enclosure_laminar(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertIn("did not converge", result["issues"][0]["message"])
        self.assertNotIn("fields", result)

    def test_relaxation_and_si_similarity(self):
        request = fixture()
        centers = (np.arange(4)+.5)/4
        force = exact_fields(np.meshgrid(centers, centers, centers, indexing="ij"))[1]
        request["body_force_n_m3"] = force.tolist()
        reference = solve_enclosure_laminar(request)
        request["nonlinear_controls"]["relaxation"] = .5
        # x'=s*x, u'=t*u, mu'=m*mu; rho'=m/(s*t)*rho preserves Re.
        s, t, m = .4, 3., .7
        request["spacing_m"] = [s/4]*3
        request["dynamic_viscosity_pa_s"] = m
        request["density_kg_m3"] = m/(s*t)
        request["body_force_n_m3"] = (m*t/s**2*force).tolist()
        result = solve_enclosure_laminar(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertGreater(result["diagnostics"]["iterations"], reference["diagnostics"]["iterations"])
        for actual, expected in zip(result["fields"]["face_velocity_m_s"], reference["fields"]["face_velocity_m_s"]):
            np.testing.assert_allclose(actual, t*np.asarray(expected), rtol=1e-7, atol=1e-8)
        np.testing.assert_allclose(result["fields"]["pressure_pa"], m*t/s*np.asarray(reference["fields"]["pressure_pa"]),
                                   rtol=1e-7, atol=1e-8)
        self.assertAlmostEqual(result["diagnostics"]["reynolds_upper_bound"],
                               reference["diagnostics"]["reynolds_upper_bound"], places=8)

    def test_reynolds_envelope_rejection(self):
        request = fixture()
        centers = (np.arange(4)+.5)/4
        request["body_force_n_m3"] = exact_fields(np.meshgrid(centers, centers, centers, indexing="ij"), 4.)[1].tolist()
        result = solve_enclosure_laminar(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertIn("Reynolds", result["issues"][0]["message"])
        self.assertNotIn("fields", result)

    def test_scope_invalid_and_resource_rejections(self):
        request = fixture()
        variants = []
        for key, value in (("contract", "spike/enclosure-stokes/v1"), ("extra", 0),
                           ("spacing_m", [0, 1, 1]), ("shape", [64]*3),
                           ("density_kg_m3", True), ("dynamic_viscosity_pa_s", float("nan"))):
            variant = copy.deepcopy(request)
            variant[key] = value
            variants.append(variant)
        obstacle = copy.deepcopy(request)
        obstacle["fluid_mask"][1][1][1] = False
        variants.append(obstacle)
        for key, value in (("relaxation", 0), ("max_iterations", True),
                           ("relative_tolerance", float("inf")), ("unknown", 1)):
            variant = copy.deepcopy(request)
            variant["nonlinear_controls"][key] = value
            variants.append(variant)
        for variant in variants:
            result = solve_enclosure_laminar(variant)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)

    def test_cancelled_never_publishes_fields(self):
        count = 0

        def check():
            nonlocal count
            count += 1
            return count >= 147  # After assembly, first solve, before publication.

        result = solve_enclosure_laminar(fixture(), cancel_check=check)
        self.assertEqual(result["status"], "cancelled", result)
        self.assertNotIn("fields", result)


if __name__ == "__main__":
    unittest.main()
