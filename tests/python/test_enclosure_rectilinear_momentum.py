# SPDX-License-Identifier: Apache-2.0
"""Continuum oracles and weighted geometric invariants for fine-grid momentum."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.enclosure_refinement import build_enclosure_grid, prolong_mac_fluxes
from python.spike_core.enclosure_rectilinear_momentum import (
    CONTRACT, _advection, _assemble, solve_enclosure_rectilinear_momentum,
)
from tests.python.test_enclosure_laminar import exact_fields


def fixture(n=4, refined=False, separated=False):
    grid = build_enclosure_grid({
        "shape": [int(2.25*n) if separated else n, n, n],
        "spacing_m": [1/n]*3, "origin_m": [0.]*3,
        "local_refinement": ([{"bounds_m": [[.25, .5]]*3, "split_factor": 2}] if refined else []),
    })
    shape = grid["shape"]
    mask = np.ones(shape, bool)
    if separated:
        mask[(grid["cell_centers_m"][0] >= 1.) & (grid["cell_centers_m"][0] < 1.25)] = False
    return {"contract": CONTRACT, "grid": grid, "fluid_mask": mask,
            "body_force_n_m3": np.zeros(shape+(3,)), "dynamic_viscosity_pa_s": 1.,
            "density_kg_m3": 1., "nonlinear_controls": {
                "max_iterations": 60, "relaxation": 1., "relative_tolerance": 1e-10}}


def manufactured(n, refined=False, separated=False):
    request = fixture(n, refined, separated)
    grid = request["grid"]
    coordinates = list(grid["cell_centers_m"])
    if separated:
        coordinates[0] = np.where(coordinates[0] >= 1.25, coordinates[0]-1.25, coordinates[0])
    request["body_force_n_m3"] = exact_fields(np.meshgrid(*coordinates, indexing="ij"))[1]
    result = solve_enclosure_rectilinear_momentum(request)
    if result["status"] != "completed":
        raise AssertionError(result)
    error, norm = 0., 0.
    for axis in range(3):
        xyz = list(grid["cell_centers_m"])
        xyz[axis] = grid["axes_m"][axis]
        if separated:
            xyz[0] = np.where(xyz[0] >= 1.25, xyz[0]-1.25, xyz[0])
        reference = exact_fields(np.meshgrid(*xyz, indexing="ij"))[0][..., axis]
        actual = np.asarray(result["fields"]["face_velocity_m_s"][axis])
        # Independent trapezoidal normal / cell-width tangential integration.
        weights = list(grid["cell_widths_m"])
        weights[axis] = np.r_[weights[axis][0]/2,
                              (weights[axis][:-1]+weights[axis][1:])/2,
                              weights[axis][-1]/2]
        volume = weights[0][:, None, None]*weights[1][None, :, None]*weights[2][None, None, :]
        if separated:
            original_x = grid["axes_m"][0] if axis == 0 else grid["cell_centers_m"][0]
            reference[(original_x > 1.) & (original_x < 1.25)] = 0.
        error += np.sum(volume*(actual-reference)**2)
        norm += np.sum(volume*reference**2)
    return np.sqrt(error/norm), result, request


class RectilinearMomentumTests(unittest.TestCase):
    def test_zero_conservative_force_and_disconnected_gauges(self):
        for vector in ([0., 0., 0.], [.4, -.3, .2]):
            request = fixture(4, refined=True, separated=True)
            request["body_force_n_m3"][...] = vector
            result = solve_enclosure_rectilinear_momentum(request)
            self.assertEqual(result["status"], "completed", result)
            self.assertEqual(result["diagnostics"]["fluid_components"], 2)
            for field in result["fields"]["face_velocity_m_s"]:
                self.assertLess(np.max(np.abs(field)), 1e-13)
            p = np.asarray(result["fields"]["pressure_pa"])
            xyz = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
            expected = sum(vector[a]*xyz[a] for a in range(3))
            for slab in (xyz[0] < 1., xyz[0] >= 1.25):
                difference = p[slab]-expected[slab]
                self.assertLess(np.ptp(difference), 2e-13)

    def test_dual_flux_pressure_adjoint_and_positive_diffusion_with_obstacles(self):
        request = fixture(4, refined=True)
        request["fluid_mask"][2:4, 1:3, 2:4] = False
        system = _assemble(request["grid"], request["fluid_mask"], request["body_force_n_m3"], 1.3)
        rng = np.random.default_rng(9471)
        u = rng.normal(size=len(system["faces"]))
        p = rng.normal(size=len(system["cells"]))
        convection, imbalance = _advection(system, u, 1.7)
        primal = system["B"] @ u
        ids = {c: i for i, c in enumerate(system["cells"])}
        expected = [.5*(primal[ids[c]]+primal[ids[o]]) for _, c, o in system["faces"]]
        np.testing.assert_allclose(imbalance, expected, atol=1e-16)
        np.testing.assert_allclose((convection+convection.T).toarray(),
                                   np.diag(1.7*imbalance), atol=1e-15)
        grad = -(system["B"].T @ p)/system["dual_volumes"]
        div = primal/system["cell_volumes"]
        self.assertAlmostEqual(u @ (system["dual_volumes"]*grad),
                               -p @ (system["cell_volumes"]*div), places=12)
        np.testing.assert_allclose((system["K"]-system["K"].T).data, 0., atol=1e-14)
        self.assertGreater(u @ (system["K"] @ u), 0.)

    def test_uniform_continuum_mms_retains_second_order(self):
        errors = [manufactured(n)[0] for n in (4, 8, 12)]
        for i, ratio in enumerate((2., 1.5)):
            self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), 1.8)
        self.assertLess(errors[-1], .02)

    def test_nonuniform_continuum_mms_refinement(self):
        # Step transitions have first-order local truncation; require >=0.8
        # observed global order without asserting smooth-grid second order.
        runs = [manufactured(n, refined=True) for n in (4, 8, 12)]
        errors = [run[0] for run in runs]
        for i, ratio in enumerate((2., 1.5)):
            self.assertGreater(np.log(errors[i]/errors[i+1])/np.log(ratio), .8)
        self.assertLess(errors[-1], .08)
        self.assertEqual(runs[-1][1]["diagnostics"]["momentum_grid_shape"], [15]*3)

    def test_disconnected_obstacle_continuum_refinement(self):
        runs = [manufactured(n, separated=True) for n in (4, 8)]
        self.assertGreater(np.log(runs[0][0]/runs[1][0])/np.log(2), 1.8)
        self.assertLess(runs[-1][0], .03)
        self.assertEqual(runs[-1][1]["diagnostics"]["fluid_components"], 2)

    def test_nonuniform_disconnected_obstacle_continuum_refinement(self):
        runs = [manufactured(n, refined=True, separated=True) for n in (4, 8)]
        self.assertGreater(np.log(runs[0][0]/runs[1][0])/np.log(2), .8)
        self.assertLess(runs[-1][0], .08)
        self.assertEqual(runs[-1][1]["diagnostics"]["fluid_components"], 2)

    def test_obstacle_inertia_mass_energy_and_exact_wall_zeros(self):
        request = fixture(4, refined=True)
        request["fluid_mask"][2:4, 2:4, 2:4] = False
        xyz = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
        request["body_force_n_m3"] = exact_fields(xyz)[1]
        result = solve_enclosure_rectilinear_momentum(request)
        self.assertEqual(result["status"], "completed", result)
        system = _assemble(request["grid"], request["fluid_mask"], request["body_force_n_m3"], 1.)
        fields = [np.asarray(x) for x in result["fields"]["face_velocity_m_s"]]
        u = []
        for axis, c, _ in system["faces"]:
            index = list(c)
            index[axis] += 1
            u.append(fields[axis][tuple(index)])
            fields[axis][tuple(index)] = 0.
        for remaining in fields:
            np.testing.assert_array_equal(remaining, 0.)
        u = np.asarray(u)
        convection, _ = _advection(system, u, 1.)
        self.assertGreater(np.linalg.norm(convection @ u), 1e-3)
        self.assertLess(np.max(np.abs(system["B"] @ u/system["cell_volumes"])), 1e-10)
        self.assertLess(abs(result["diagnostics"]["advective_power_w"]), 1e-10)
        self.assertLess(result["diagnostics"]["relative_energy_defect"], 1e-9)

    def test_refined_solution_is_not_coarse_prolongation(self):
        _, coarse, _ = manufactured(4)
        _, fine, request = manufactured(4, refined=True)
        prolonged = prolong_mac_fluxes(request["grid"], coarse["fields"]["face_velocity_m_s"])
        difference = sum(np.linalg.norm(np.asarray(actual)-expected)
                         for actual, expected in zip(fine["fields"]["face_velocity_m_s"],
                                                     prolonged["face_velocity_m_s"]))
        self.assertGreater(difference, .01)

    def test_fail_closed_malformed_nonconverged_condition_and_cancel(self):
        request = fixture()
        variants = []
        for key, value in (("extra", 1), ("density_kg_m3", True),
                           ("fluid_mask", np.ones((4, 4, 4), int))):
            variant = copy.deepcopy(request)
            variant[key] = value
            variants.append(variant)
        broken = copy.deepcopy(request)
        broken["grid"]["cell_volumes_m3"][0, 0, 0] *= 2.
        variants.append(broken)
        forcing = copy.deepcopy(request)
        forcing["body_force_n_m3"] = exact_fields(np.meshgrid(
            *forcing["grid"]["cell_centers_m"], indexing="ij"))[1]
        forcing["nonlinear_controls"]["max_iterations"] = 1
        variants.append(forcing)
        for variant in variants:
            result = solve_enclosure_rectilinear_momentum(variant)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
        with patch("python.spike_core.enclosure_rectilinear_momentum.onenormest", return_value=1e20):
            result = solve_enclosure_rectilinear_momentum(request)
            self.assertEqual(result["status"], "blocked", result)
            self.assertIn("condition", result["issues"][0]["message"])
        result = solve_enclosure_rectilinear_momentum(request, cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)

    def test_isolated_fluid_cells_have_no_fake_velocity(self):
        request = fixture()
        request["fluid_mask"][...] = False
        request["fluid_mask"][0, 0, 0] = request["fluid_mask"][3, 3, 3] = True
        result = solve_enclosure_rectilinear_momentum(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["diagnostics"]["velocity_unknowns"], 0)
        self.assertEqual(result["diagnostics"]["fluid_components"], 2)

    def test_reynolds_and_metric_rejections_and_small_scale_fail_closed(self):
        request = fixture()
        xyz = np.meshgrid(*request["grid"]["cell_centers_m"], indexing="ij")
        request["body_force_n_m3"] = exact_fields(xyz, amplitude=4.)[1]
        result = solve_enclosure_rectilinear_momentum(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertIn("Reynolds", result["issues"][0]["message"])
        request = fixture()
        request["grid"] = build_enclosure_grid({"shape": [4]*3, "spacing_m": [1., 1., .001],
            "origin_m": [0.]*3, "local_refinement": []})
        result = solve_enclosure_rectilinear_momentum(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertIn("metric", result["issues"][0]["message"])
        request = fixture()
        request["body_force_n_m3"][...] = 1e-320
        result = solve_enclosure_rectilinear_momentum(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertNotIn("fields", result)

    def test_dimensional_norm_floor_counterexample(self):
        # Independent review: dimensional floors previously admitted a 50%
        # damped iterate as converged when the integrated force was tiny.
        for spacing in (1e-100, 1e-60, 1e-20):
            results = []
            for relaxation in (1., .5):
                request = fixture(3)
                request["grid"] = build_enclosure_grid({
                    "shape": [3]*3, "spacing_m": [spacing]*3,
                    "origin_m": [0.]*3, "local_refinement": []})
                request["body_force_n_m3"][..., 0] = np.arange(3)[None, :, None]*1e6
                request["nonlinear_controls"].update(max_iterations=100, relaxation=relaxation)
                results.append(solve_enclosure_rectilinear_momentum(request))
            if spacing < 1e-20:
                for result in results:
                    self.assertEqual(result["status"], "blocked", result)
                    self.assertNotIn("fields", result)
            else:
                for result in results:
                    self.assertEqual(result["status"], "completed", result)
                self.assertGreater(results[1]["diagnostics"]["iterations"], 20)
                for direct, damped in zip(results[0]["fields"]["face_velocity_m_s"],
                                          results[1]["fields"]["face_velocity_m_s"]):
                    np.testing.assert_allclose(np.asarray(damped)/1e-35,
                                               np.asarray(direct)/1e-35, rtol=1e-8, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
