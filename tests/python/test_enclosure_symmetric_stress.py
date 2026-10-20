# SPDX-License-Identifier: Apache-2.0
"""Continuum and energy oracles for prescribed-variable-viscosity MAC stress."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import diags, vstack

from python.spike_core.enclosure_rectilinear_momentum import _assemble
from python.spike_core.enclosure_refinement import build_enclosure_grid
from python.spike_core.enclosure_symmetric_stress import (
    CONTRACT, _stress_operator, solve_enclosure_symmetric_stress,
)


def fixture(n=4, refined=False):
    grid = build_enclosure_grid({
        "shape": [n]*3, "spacing_m": [1/n]*3, "origin_m": [0.]*3,
        "local_refinement": ([{"bounds_m": [[.25, .5]]*3, "split_factor": 2}]
                             if refined else []),
    })
    shape = grid["shape"]
    return {"contract": CONTRACT, "grid": grid, "fluid_mask": np.ones(shape, bool),
            "body_force_n_m3": np.zeros(shape+(3,)),
            "dynamic_viscosity_pa_s": np.ones(shape), "density_kg_m3": 1.,
            "nonlinear_controls": {"max_iterations": 60, "relaxation": 1.,
                                   "relative_tolerance": 1e-10}}


def exact_fields(xyz, variable=True):
    """Independent analytic curl, strain, variable mu and forcing; p not zero.

    u=curl((.3,.5,1)*product(sin(pi*x)^2)); mu=1+.3x+.2y+.1z.
    f_i=u_j*d_j(u_i)-mu*lap(u_i)-(d_j(u_i)+d_i(u_j))*d_j(mu)+d_i(p).
    """
    shape, p = xyz[0].shape, np.pi
    factors = [[np.sin(p*x)**2, p*np.sin(2*p*x), 2*p*p*np.cos(2*p*x),
                -4*p**3*np.sin(2*p*x)] for x in xyz]
    terms = (((1., (0, 1, 0)), (-.5, (0, 0, 1))),
             ((.3, (0, 0, 1)), (-1., (1, 0, 0))),
             ((.5, (1, 0, 0)), (-.3, (0, 1, 0))))

    def derivative(component, extra):
        total = np.zeros(shape)
        for coefficient, powers in terms[component]:
            value = np.full(shape, coefficient)
            for axis in range(3):
                value *= factors[axis][powers[axis]+extra[axis]]
            total += value
        return total

    if variable == "quadratic":
        gradient_mu = [2*x for x in xyz]
        mu = 1+sum(x*x for x in xyz)
    else:
        gradient_mu = np.array([.3, .2, .1]) if variable else np.zeros(3)
        mu = 1+sum(gradient_mu[a]*xyz[a] for a in range(3))
    velocity = np.stack([derivative(a, (0, 0, 0)) for a in range(3)], axis=-1)
    jacobian = np.empty(shape+(3, 3))
    for a in range(3):
        for b in range(3):
            order = [0]*3
            order[b] = 1
            jacobian[..., a, b] = derivative(a, order)
    force, viscosity_gradient_force = np.zeros(shape+(3,)), np.zeros(shape+(3,))
    for a in range(3):
        for b in range(3):
            second = [0]*3
            second[b] = 2
            force[..., a] += velocity[..., b]*jacobian[..., a, b]-mu*derivative(a, second)
            viscosity_gradient_force[..., a] -= (
                jacobian[..., a, b]+jacobian[..., b, a])*gradient_mu[b]
        pressure_gradient = np.full(shape, .2*p)
        for b in range(3):
            pressure_gradient *= np.cos(p*xyz[b]) if a == b else np.sin(p*xyz[b])
        force[..., a] += pressure_gradient+viscosity_gradient_force[..., a]
    pressure = .2*np.prod([np.sin(p*x) for x in xyz], axis=0)
    return velocity, force, pressure, mu, viscosity_gradient_force


def manufactured(n, variable=True, refined=False):
    request = fixture(n, refined)
    grid = request["grid"]
    _, force, pressure, viscosity, gradient_force = exact_fields(
        np.meshgrid(*grid["cell_centers_m"], indexing="ij"), variable)
    request["dynamic_viscosity_pa_s"] = viscosity
    request["body_force_n_m3"] = force
    result = solve_enclosure_symmetric_stress(request)
    if result["status"] != "completed":
        raise AssertionError(result)
    error, norm = 0., 0.
    for axis in range(3):
        coordinates = list(grid["cell_centers_m"])
        coordinates[axis] = grid["axes_m"][axis]
        reference = exact_fields(np.meshgrid(*coordinates, indexing="ij"), variable)[0][..., axis]
        actual = np.asarray(result["fields"]["face_velocity_m_s"][axis])
        weights = list(grid["cell_widths_m"])
        weights[axis] = np.r_[weights[axis][0]/2,
                              (weights[axis][:-1]+weights[axis][1:])/2,
                              weights[axis][-1]/2]
        volume = weights[0][:, None, None]*weights[1][None, :, None]*weights[2][None, None, :]
        error += np.sum(volume*(actual-reference)**2)
        norm += np.sum(volume*reference**2)
    actual_p = np.asarray(result["fields"]["pressure_pa"])
    delta = actual_p-pressure
    volume = grid["cell_volumes_m3"]
    delta -= np.sum(volume*delta)/np.sum(volume)
    pressure_error = float(np.sqrt(np.sum(volume*delta**2)/np.sum(volume)))
    return float(np.sqrt(error/norm)), pressure_error, result, float(np.linalg.norm(gradient_force))


def scalar_diffusion_substitute(grid, system, viscosity, cancel_check=None):
    """Deliberately incorrect div(mu grad(u)); used only as a negative control."""
    _, strain, weights, normal_rows = _stress_operator(grid, system, viscosity, cancel_check)
    axes = np.array([axis for axis, _, _ in system["faces"]])
    # Remove the off-component shear products and halve doubled normal strain.
    parts = [strain[:normal_rows]]
    for axis in range(3):
        parts.append(strain[normal_rows:] @ diags((axes == axis).astype(float)))
    wrong_strain = vstack(parts, format="csr")
    wrong_weights = np.r_[weights[:normal_rows]/2, np.tile(weights[normal_rows:], 3)]
    wrong_matrix = (wrong_strain.T @ diags(wrong_weights) @ wrong_strain).tocsr()
    return wrong_matrix, wrong_strain, wrong_weights, normal_rows


class SymmetricStressTests(unittest.TestCase):
    def test_constant_viscosity_discrete_laplacian_plus_grad_div_identity(self):
        for refined in (False, True):
            request = fixture(4, refined)
            grid = request["grid"]
            system = _assemble(grid, request["fluid_mask"], request["body_force_n_m3"], 1.7)
            stress, _, _, _ = _stress_operator(grid, system, np.full(grid["shape"], 1.7))
            grad_div = system["B"].T @ diags(1.7/system["cell_volumes"]) @ system["B"]
            defect = stress-system["K"]-grad_div
            np.testing.assert_allclose(defect.toarray(), 0., atol=3e-15)

    def test_cross_components_positive_energy_and_no_velocity_nullspace(self):
        request = fixture(3, True)
        grid = request["grid"]
        mu = exact_fields(np.meshgrid(*grid["cell_centers_m"], indexing="ij"))[3]
        system = _assemble(grid, request["fluid_mask"], request["body_force_n_m3"], 1.)
        stiffness, strain, weights, normal_rows = _stress_operator(grid, system, mu)
        np.testing.assert_allclose((stiffness-stiffness.T).toarray(), 0., atol=1e-14)
        self.assertGreater(np.linalg.eigvalsh(stiffness.toarray())[0], 0.)
        axes = np.array([a for a, _, _ in system["faces"]])
        coo = stiffness.tocoo()
        self.assertTrue(np.any(np.abs(coo.data[axes[coo.row] != axes[coo.col]]) > 0.))
        u = np.random.default_rng(617).normal(size=len(system["faces"]))
        rate = strain @ u
        self.assertAlmostEqual(float(u @ (stiffness @ u)), float(weights @ (rate*rate)), places=11)
        self.assertGreater(float(weights[normal_rows:] @ rate[normal_rows:]**2), 0.)

    def test_uniform_constant_and_variable_mu_continuum_second_order(self):
        # Fixed before observing the new operator: existing full-box targets.
        for variable in (False, True):
            runs = [manufactured(n, variable=variable) for n in (4, 8, 12)]
            errors = [run[0] for run in runs]
            for i, ratio in enumerate((2., 1.5)):
                self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), 1.8, errors)
            self.assertLess(errors[-1], .02, errors)
            self.assertLess(runs[-1][1], runs[0][1])
            if variable:
                self.assertGreater(runs[-1][3], 0.)
            for _, _, result, _ in runs:
                diagnostics = result["diagnostics"]
                self.assertGreater(diagnostics["reynolds_upper_bound"], 2.)
                self.assertLess(diagnostics["relative_energy_defect"], 1e-9)
                self.assertLess(diagnostics["relative_strain_energy_defect"], 1e-9)
                self.assertFalse(result["production_qualified"])

    def test_quadratic_viscosity_additional_fine_range(self):
        # The original coarse 4/8/12 order failure remains in the method record.
        # Separately authorized additional resolution uses UNCHANGED gates;
        # expecting an accuracy failure is not a qualification test.
        levels = (8, 12, 16)
        runs = [manufactured(n, variable="quadratic") for n in levels]
        errors = [run[0] for run in runs]
        orders = [np.log(errors[i]/errors[i+1])/np.log(levels[i+1]/levels[i])
                  for i in range(2)]
        for order in orders:
            self.assertGreater(order, 1.8, (errors, orders))
        self.assertLess(errors[-1], .02)
        self.assertLess(runs[-1][1], runs[0][1])

    def test_scalar_component_diffusion_fails_quadratic_viscosity_reference(self):
        # Quadratic mu has Hessian=2I: the omitted transpose-gradient term is
        # grad(u dot grad(mu))-2u. Its -2u part cannot be absorbed by pressure.
        # Predeclared detector budgets: >1e-3 changed velocity and >.05 Pa
        # additional pressure error on the same n=12 independent continuum case.
        correct = manufactured(12, variable="quadratic")
        with patch("python.spike_core.enclosure_symmetric_stress._stress_operator",
                   side_effect=scalar_diffusion_substitute):
            wrong = manufactured(12, variable="quadratic")
        changed, reference = 0., 0.
        for correct_field, wrong_field in zip(correct[2]["fields"]["face_velocity_m_s"],
                                               wrong[2]["fields"]["face_velocity_m_s"]):
            correct_field, wrong_field = np.asarray(correct_field), np.asarray(wrong_field)
            changed += np.sum((correct_field-wrong_field)**2)
            reference += np.sum(correct_field**2)
        self.assertGreater(float(np.sqrt(changed/reference)), 1e-3)
        self.assertGreater(wrong[1]-correct[1], .05)
        self.assertGreater(wrong[0], .02)  # Fails the same fine-grid velocity budget.
        self.assertGreater(correct[3], 0.)

    def test_nonuniform_variable_mu_continuum_refinement(self):
        # Abrupt tensor-plane transitions have only first-order local consistency.
        # These inherited nonuniform gates were fixed before executing this case.
        runs = [manufactured(n, refined=True) for n in (4, 8, 12)]
        errors = [run[0] for run in runs]
        for i, ratio in enumerate((2., 1.5)):
            self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), .8, errors)
        self.assertLess(errors[-1], .08, errors)

    def test_rejects_obstacles_invalid_viscosity_nonconvergence_and_cancel(self):
        base = fixture()
        variants = []
        for value in (np.zeros((4, 4, 4)), np.full((4, 4, 4), -1.),
                      np.ones((3, 3, 3)), np.ones((4, 4, 4), bool),
                      np.full((4, 4, 4), np.nan)):
            variant = copy.deepcopy(base)
            variant["dynamic_viscosity_pa_s"] = value
            variants.append(variant)
        obstacle = copy.deepcopy(base)
        obstacle["fluid_mask"][1, 1, 1] = False
        variants.append(obstacle)
        nonconverged = copy.deepcopy(base)
        xyz = np.meshgrid(*base["grid"]["cell_centers_m"], indexing="ij")
        nonconverged["body_force_n_m3"] = exact_fields(xyz)[1]
        nonconverged["nonlinear_controls"]["max_iterations"] = 1
        variants.append(nonconverged)
        for variant in variants:
            result = solve_enclosure_symmetric_stress(variant)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        result = solve_enclosure_symmetric_stress(base, cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)
        result = solve_enclosure_symmetric_stress(base)
        self.assertEqual(result["status"], "completed", result)
        for field in result["fields"]["face_velocity_m_s"]:
            np.testing.assert_array_equal(field, 0.)


if __name__ == "__main__":
    unittest.main()
