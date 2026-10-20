# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent simplex construction, continuum oracles and rejection checks."""
import copy
import itertools
import math
import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix, eye, kron

from python.spike_core.cfd_tetra_mesh import admit_cfd_tetra_mesh
from python.spike_core.cfd_tetra_stokes import (
    CONTRACT, CfdTetraStokesError, _block_preconditioner, solve_cfd_tetra_stokes)


def box_mesh(n, *, shear=False, shift=0.):
    coordinates = list(itertools.product(range(n+1), repeat=3))
    ids = {xyz: index for index, xyz in enumerate(coordinates)}
    vertices = np.asarray(coordinates, dtype=float)/n
    if shear:
        vertices = vertices @ np.array([[1., .2, .1], [0., 1., .15], [0., 0., 1.]]).T
    vertices[:, 0] += shift
    cells = []
    for base in itertools.product(range(n), repeat=3):
        for order in itertools.permutations(range(3)):
            position = list(base)
            cell = [ids[tuple(position)]]
            for d in order:
                position[d] += 1
                cell.append(ids[tuple(position)])
            if np.linalg.det((vertices[cell[1:]]-vertices[cell[0]]).T) < 0.:
                cell[0], cell[1] = cell[1], cell[0]
            cells.append(cell)
    owners = {}
    for cell in cells:
        for face in itertools.combinations(cell, 3):
            key = tuple(sorted(face))
            owners[key] = owners.get(key, 0)+1
    patches = {"inlet": [], "outlet": [], "prescribed_sides": []}
    for face, count in owners.items():
        if count != 1:
            continue
        xs = [coordinates[i][0] for i in face]
        patch_name = "inlet" if all(x == 0 for x in xs) else "outlet" if all(x == n for x in xs) else "prescribed_sides"
        patches[patch_name].append(list(face))
    return {"contract": "spike/cfd-tetra-mesh/v1", "units": "m", "vertices": vertices.tolist(),
            "cells": cells, "boundary_patches": patches}


def square_average(values):
    """Independent exact triangle average of a scalar linear field squared."""
    values = np.asarray(values)
    return (np.sum(values*values, axis=-1)+np.sum(values, axis=-1)**2)/12.


def poiseuille(n, *, pressure_offset=0., reverse=False):
    mesh = box_mesh(n)
    vertices = np.array(mesh["vertices"])
    amplitude = -.01 if reverse else .01
    conditions = {}
    for name, triangles in mesh["boundary_patches"].items():
        points = vertices[np.array(triangles)]
        if name == "outlet":
            values = np.tile([-pressure_offset, 0., 0.], (len(triangles), 1))
            conditions[name] = {"kind": "pseudo_traction", "face_average_pseudo_traction_pa": values,
                                "reject_backflow": True}
        else:
            ys = points[:, :, 1]
            values = np.zeros((len(triangles), 3))
            values[:, 0] = amplitude*(np.mean(ys, axis=1)-square_average(ys))
            conditions[name] = {"kind": "velocity_dirichlet", "face_average_velocity_m_s": values}
    return {"contract": CONTRACT, "mesh": mesh, "dynamic_viscosity_pa_s": 1., "density_kg_m3": 1.,
            "body_force_n_m3": np.zeros((len(mesh["cells"]), 3)),
            "boundary_conditions": conditions, "controls": {}}


def quadratic_mms(n):
    mesh = box_mesh(n, shear=True)
    vertices = np.asarray(mesh["vertices"])
    amplitude = .001
    conditions = {}
    for name, triangles in mesh["boundary_patches"].items():
        points = vertices[np.array(triangles)]
        values = amplitude*np.stack([square_average(points[:, :, 1]),
                                     square_average(points[:, :, 2]),
                                     square_average(points[:, :, 0])], axis=1)
        conditions[name] = {"kind": "velocity_dirichlet", "face_average_velocity_m_s": values}
    force = np.tile(amplitude*np.array([-1., 0., -5.]), (len(mesh["cells"]), 1))
    return {"contract": CONTRACT, "mesh": mesh, "dynamic_viscosity_pa_s": 1., "density_kg_m3": 1.,
            "body_force_n_m3": force, "boundary_conditions": conditions, "controls": {}}


def quadrature():
    # Duffy transform of a tensor Gauss rule, independently authored.
    node, weight = np.polynomial.legendre.leggauss(4)
    node, weight = .5*(node+1), .5*weight
    bary, weights = [], []
    for i, j, k in itertools.product(range(4), repeat=3):
        r, s, t = node[i], node[j], node[k]
        bary.append([(1-r)*(1-s)*(1-t), r, (1-r)*s, (1-r)*(1-s)*t])
        weights.append(6*weight[i]*weight[j]*weight[k]*(1-r)**2*(1-s))
    return np.array(bary), np.array(weights)


def errors(request, result, *, quadratic=False):
    vertices = np.asarray(request["mesh"]["vertices"])
    cells = np.asarray(request["mesh"]["cells"])
    tetra = vertices[cells]
    volumes = np.linalg.det(np.transpose(tetra[:, 1:]-tetra[:, :1], (0, 2, 1)))/6
    centroids = np.mean(tetra, axis=1)
    face_map = {tuple(sorted(face)): i for i, face in enumerate(result["fields"]["face_vertices"])}
    cell_faces = np.array([[face_map[tuple(sorted(np.delete(cell, local)))]
                            for local in range(4)] for cell in cells])
    face_u = np.asarray(result["fields"]["face_average_velocity_m_s"])
    bary, weights = quadrature()
    xyz = np.einsum("qj,cjd->cqd", bary, tetra)
    actual = np.einsum("qj,cjd->cqd", 1-3*bary, face_u[cell_faces])
    if quadratic:
        exact = .001*np.stack([xyz[:, :, 1]**2, xyz[:, :, 2]**2, xyz[:, :, 0]**2], axis=-1)
        exact_p = .001*(centroids @ np.array([1., 2., -3.]))
    else:
        exact = np.zeros_like(xyz)
        exact[:, :, 0] = .01*xyz[:, :, 1]*(1-xyz[:, :, 1])
        exact_p = .02*(1-centroids[:, 0])
    weighted = volumes[:, None]*weights
    velocity_error = np.sqrt(np.sum(weighted*np.sum((actual-exact)**2, axis=-1))
                             / np.sum(weighted*np.sum(exact**2, axis=-1)))
    p = np.array(result["fields"]["cell_pressure_pa"])
    if quadratic:
        p -= np.average(p, weights=volumes)
        exact_p -= np.average(exact_p, weights=volumes)
    pressure_error = np.sqrt(np.sum(volumes*(p-exact_p)**2)/np.sum(volumes*exact_p**2))
    return float(velocity_error), float(pressure_error)


class TetraStokesTests(unittest.TestCase):
    def completed(self, request):
        result = solve_cfd_tetra_stokes(request)
        self.assertEqual(result["status"], "completed", result)
        return result

    def blocked(self, request, text=None):
        result = solve_cfd_tetra_stokes(request)
        self.assertEqual(result["status"], "blocked", result)
        self.assertNotIn("fields", result)
        if text:
            self.assertIn(text, result["issues"][0]["message"])
        return result

    def test_block_preconditioner_positive_symmetric_and_exact_blocks(self):
        scalar = np.array([[2., -1.], [-1., 2.]])
        velocity = kron(csr_matrix(scalar), eye(3), format="csr")
        operator, nonzeros = _block_preconditioner(velocity, np.array([3., 5.]), 1, lambda: None)
        rng = np.random.default_rng(572)
        for _ in range(12):
            x, y = rng.normal(size=(2, 9))
            expected = np.r_[np.linalg.solve(scalar, x[:6].reshape(2, 3)).ravel(),
                             x[6:8]/[3., 5.], x[8]]
            np.testing.assert_allclose(operator @ x, expected, rtol=2e-15, atol=2e-15)
            self.assertGreater(x @ (operator @ x), 0.)
            self.assertAlmostEqual(x @ (operator @ y), y @ (operator @ x), delta=1e-13)
        self.assertLess(nonzeros, 20)
        with self.assertRaises(CfdTetraStokesError):
            _block_preconditioner(velocity, np.array([-3., 5.]), 1, lambda: None)

    def test_poiseuille_three_meshes_fixed_accuracy_mass_and_energy_gates(self):
        records = []
        for n in (2, 4, 8):
            request = poiseuille(n)
            result = self.completed(request)
            records.append(errors(request, result))
            diagnostics = result["diagnostics"]
            self.assertLessEqual(diagnostics["scaled_linear_relative_residual"], 1e-10)
            self.assertLessEqual(diagnostics["momentum_relative_residual"], 1e-10)
            self.assertLessEqual(diagnostics["maximum_local_mass_scaled_residual"], 1e-10)
            self.assertLessEqual(diagnostics["relative_energy_defect"], 1e-9)
            self.assertLessEqual(diagnostics["reynolds_upper_bound"], .1)
            self.assertLess(diagnostics["boundary_patch_outward_flux_m3_s"]["inlet"], 0.)
            self.assertGreater(diagnostics["boundary_patch_outward_flux_m3_s"]["outlet"], 0.)
            self.assertEqual(diagnostics["pressure_gauge_cells"], [])
        orders = [math.log(records[i][0]/records[i+1][0], 2) for i in range(2)]
        self.assertTrue(all(order >= .8 for order in orders), (records, orders))
        self.assertLess(records[-1][0], .05)
        self.assertLess(records[-1][1], .15)
        self.assertTrue(records[0][1] > records[1][1] > records[2][1], records)

    def test_affine_sheared_quadratic_manufactured_solution(self):
        records = []
        for n in (2, 4, 8):
            request = quadratic_mms(n)
            result = self.completed(request)
            records.append(errors(request, result, quadratic=True))
            self.assertEqual(result["diagnostics"]["pressure_gauge_cells"], [0])
            self.assertEqual(result["fields"]["cell_pressure_pa"][0], 0.)
        orders = [math.log(records[i][0]/records[i+1][0], 2) for i in range(2)]
        self.assertTrue(all(order >= .8 for order in orders), (records, orders))
        self.assertLess(records[-1][0], .05)
        self.assertLess(records[-1][1], .2)
        self.assertTrue(records[0][1] > records[1][1] > records[2][1], records)

    def test_rotated_sheared_si_affine_harmonic_patch(self):
        request = quadratic_mms(2)
        angle = .37
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0.],
                             [math.sin(angle), math.cos(angle), 0.], [0., 0., 1.]])
        vertices = .001*np.asarray(request["mesh"]["vertices"]) @ rotation.T
        request["mesh"]["vertices"] = vertices.tolist()
        request["body_force_n_m3"][:] = 0.
        for name, triangles in request["mesh"]["boundary_patches"].items():
            averages = np.zeros((len(triangles), 3))
            averages[:, 0] = 1e-4+.1*np.mean(vertices[np.asarray(triangles), 1], axis=1)
            request["boundary_conditions"][name]["face_average_velocity_m_s"] = averages
        result = self.completed(request)
        all_faces = np.asarray(result["fields"]["face_vertices"])
        expected = np.zeros((len(all_faces), 3))
        expected[:, 0] = 1e-4+.1*np.mean(vertices[all_faces, 1], axis=1)
        np.testing.assert_allclose(result["fields"]["face_average_velocity_m_s"], expected, atol=5e-16)
        np.testing.assert_allclose(result["fields"]["cell_pressure_pa"], 0., atol=1e-10)
        self.assertLess(result["diagnostics"]["momentum_relative_residual"], 1e-10)
        self.assertLess(result["diagnostics"]["relative_energy_defect"], 1e-9)

    def test_unresolved_zero_work_translation_fails_closed(self):
        request = quadratic_mms(2)
        request["body_force_n_m3"][:] = 0.
        for boundary in request["boundary_conditions"].values():
            boundary["face_average_velocity_m_s"][:] = [.001, 0., 0.]
        # Physical work and dissipation both vanish. The retained physical
        # relative-power gate cannot resolve roundoff reactions in this case;
        # do not silently waive it or publish a qualified field.
        self.blocked(request, "power balance")

    def test_natural_pressure_sign_and_boundary_flux(self):
        base = self.completed(poiseuille(3))
        shifted = self.completed(poiseuille(3, pressure_offset=.03))
        np.testing.assert_allclose(base["fields"]["face_average_velocity_m_s"],
                                   shifted["fields"]["face_average_velocity_m_s"], atol=2e-15)
        np.testing.assert_allclose(np.asarray(shifted["fields"]["cell_pressure_pa"])
                                   - np.asarray(base["fields"]["cell_pressure_pa"]), .03, atol=2e-14)
        self.assertGreater(shifted["diagnostics"]["relative_energy_defect"], -1.)

    def test_independent_cell_flux_and_gradient_reconstruction(self):
        request = poiseuille(3)
        result = self.completed(request)
        mesh = admit_cfd_tetra_mesh(request["mesh"])
        values = np.array(result["fields"]["face_average_velocity_m_s"])
        gradients = np.array(result["fields"]["cell_velocity_gradient_s_inv"])
        for c, cell in enumerate(mesh["cells"]):
            total = 0.
            for local, face in enumerate(mesh["cell_faces"][c]):
                total += mesh["face_areas"][face]*np.dot(values[face], mesh["cell_outward_normals"][c, local])
            self.assertLess(abs(total), 1e-16)
            self.assertLess(abs(np.trace(gradients[c])), 1e-12)
        self.assertIn("not_symmetric_stress", result["natural_boundary"])
        self.assertFalse(result["production_qualified"])

    def test_disconnected_zero_pressure_gauges(self):
        first, second = box_mesh(1), box_mesh(1, shift=2.)
        offset = len(first["vertices"])
        first["vertices"].extend(second["vertices"])
        first["cells"].extend([[v+offset for v in cell] for cell in second["cells"]])
        for name, triangles in second["boundary_patches"].items():
            first["boundary_patches"]["second_"+name] = [[v+offset for v in face] for face in triangles]
        request = quadratic_mms(1)
        request["mesh"] = first
        request["body_force_n_m3"] = np.zeros((len(first["cells"]), 3))
        request["boundary_conditions"] = {
            name: {"kind": "velocity_dirichlet", "face_average_velocity_m_s": np.zeros((len(faces), 3))}
            for name, faces in first["boundary_patches"].items()
        }
        result = self.completed(request)
        self.assertEqual(result["diagnostics"]["pressure_gauge_cells"], [0, 6])
        np.testing.assert_array_equal(result["fields"]["cell_pressure_pa"], 0.)
        np.testing.assert_array_equal(result["fields"]["face_average_velocity_m_s"], 0.)

    def test_incompatible_closed_flux_and_backflow_rejected(self):
        request = quadratic_mms(2)
        request["boundary_conditions"]["inlet"]["face_average_velocity_m_s"][0, 0] += .01
        self.blocked(request, "incompatible")
        self.blocked(poiseuille(2, reverse=True), "backflow")
        request = poiseuille(2)
        request["boundary_conditions"]["outlet"]["reject_backflow"] = False
        self.blocked(request, "reject_backflow")

    def test_high_re_condition_runtime_cancellation_and_no_fields(self):
        request = poiseuille(2)
        request["density_kg_m3"] = 1000.
        self.blocked(request, "Reynolds")
        request = poiseuille(2)
        with patch("python.spike_core.cfd_tetra_stokes.onenormest", return_value=1e20):
            self.blocked(request, "condition")
        result = solve_cfd_tetra_stokes(request, cancel_check=lambda: True)
        self.assertEqual(result["status"], "cancelled")
        self.assertNotIn("fields", result)
        with patch("python.spike_core.cfd_tetra_stokes.time.monotonic", side_effect=[0., 100.]):
            self.blocked(request, "runtime")

    def test_strict_boundary_and_mesh_forgery_no_mutation(self):
        original = poiseuille(2)
        saved = copy.deepcopy(original)
        self.completed(original)
        self.assertEqual(saved["mesh"], original["mesh"])
        cases = []
        request = poiseuille(2)
        request["boundary_conditions"]["outlet"]["kind"] = "physical_traction"
        cases.append(request)
        request = poiseuille(2)
        request["body_force_n_m3"][0, 0] = math.nan
        cases.append(request)
        request = poiseuille(2)
        request["mesh"]["cells"][0][0], request["mesh"]["cells"][0][1] = request["mesh"]["cells"][0][1], request["mesh"]["cells"][0][0]
        cases.append(request)
        request = poiseuille(2)
        request["mesh"]["boundary_patches"]["outlet"][0] = request["mesh"]["boundary_patches"]["inlet"][0]
        cases.append(request)
        request = poiseuille(2)
        del request["boundary_conditions"]["outlet"]
        cases.append(request)
        request = poiseuille(2)
        request["controls"]["relative_tolerance"] = 1e-3
        cases.append(request)
        request = poiseuille(2)
        request["dynamic_viscosity_pa_s"] = 1e-310
        cases.append(request)
        for request in cases:
            self.blocked(request)


if __name__ == "__main__":
    unittest.main()
