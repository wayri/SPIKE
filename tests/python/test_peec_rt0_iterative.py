# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Analytical continuum limit and direct-discretization oracles for trace CG."""

import unittest
from unittest.mock import patch

import numpy as np
from scipy.sparse import csr_matrix, diags

from python.spike_core.hybrid_mesh import MeshBranch
from python.spike_core.peec_conforming_dc import solve_conforming_dc
from python.spike_core.peec_rt0_iterative import solve_iterative_conforming_dc, _multilevel_preconditioner
from tests.python.test_peec_conforming_dc import rectangle_mesh


def coupon(divisions=4):
    rectangles = []
    h = 1/divisions
    for x in range(2*divisions):
        for y in range(divisions):
            node = 0 if x < divisions//2 else (1 if x >= 3*divisions//2 else 2+x*divisions+y)
            rectangles.append((node, (x*h, y*h, (x+1)*h, (y+1)*h)))
    return rectangle_mesh(rectangles)


def via_chain():
    mesh = rectangle_mesh([(0, (0, 0, 1, 1))], contacts=(0, 1, 2))
    for index, layer in enumerate(("In1.Cu", "B.Cu"), 1):
        cell = dict(mesh.cells[0], layer=layer, control_node=index)
        cell["vertices_mm"] = [[x, y, index] for x, y, _ in cell["vertices_mm"]]
        mesh.cells.append(cell)
        mesh.branches.append(MeshBranch(f"conforming:{index}", "zone", index, index,
            (0, 0, index), (1, 0, index), 1, 1, 1000, layer, "N", "sheet"))
        mesh.branches.append(MeshBranch(f"via:{index}", "via", index-1, index,
            (.5, .5, index-1), (.5, .5, index), 1, 1, 1000, layer, "N", "via"))
    return mesh


class IterativeRT0Tests(unittest.TestCase):
    def test_multilevel_is_symmetric_positive_definite_with_barrel_term(self):
        n = 40
        planar = diags((-np.ones(n-1), 2*np.ones(n), -np.ones(n-1)), (-1, 0, 1)).tocsr()
        coupling = np.zeros((n, 2))
        coupling[:4, 0] = .25
        coupling[-4:, 1] = -.25
        d = np.array([[2., -.25], [-.25, 1.]])
        apply, info = _multilevel_preconditioner(planar, csr_matrix(coupling),
            lambda rhs: np.linalg.solve(d, rhs), check_budget=lambda: None, coarse_limit=8)
        matrix = np.column_stack([apply(column) for column in np.eye(n)])
        np.testing.assert_allclose(matrix, matrix.T, atol=5e-14, rtol=1e-13)
        self.assertGreater(np.linalg.eigvalsh(matrix)[0], 0)
        self.assertGreater(info["preconditioner_levels"], 1)
        with self.assertRaisesRegex(ValueError, "nonzero budget"):
            _multilevel_preconditioner(planar, csr_matrix(coupling),
                lambda rhs: np.linalg.solve(d, rhs), check_budget=lambda: None, max_nonzeros=10)

    def test_multilevel_reduces_coupon_iterations_without_changing_result(self):
        mesh = coupon(16)
        jacobi = solve_iterative_conforming_dc(mesh, 0, 1, preconditioner_kind="jacobi")
        multilevel = solve_iterative_conforming_dc(mesh, 0, 1, preconditioner_kind="multilevel")
        self.assertLess(multilevel["iterations"], jacobi["iterations"]//2)
        self.assertAlmostEqual(multilevel["resistance_ohm"], jacobi["resistance_ohm"], places=10)

    def test_coupon_refinement_and_direct_equivalence(self):
        # Integrating I(x)^2/(sigma*t*W) for unit sheet conductance, 2x1
        # rectangle and .5-wide uniform finite contacts gives R=4/3 ohm.
        errors = []
        for divisions in (4, 8, 16):
            mesh = coupon(divisions)
            direct = solve_conforming_dc(mesh, 0, 1)
            result = solve_iterative_conforming_dc(mesh, 0, 1)
            self.assertAlmostEqual(result["resistance_ohm"], direct["resistance_ohm"], places=10)
            self.assertLess(result["maximum_cell_kcl_error_a"], 1e-11)
            self.assertLess(result["maximum_face_kcl_error_a"], 1e-10)
            self.assertLess(result["relative_energy_error"], 1e-10)
            self.assertLess(result["relative_residual"], 1e-10)
            self.assertFalse(result["production_qualified"])
            self.assertEqual(result["dense_factor_order"], 0)
            errors.append(abs(result["resistance_ohm"]-4/3))
        self.assertLess(errors[-1], .001)
        self.assertLess(errors[1], errors[0]/3.8)
        self.assertLess(errors[2], errors[1]/3.8)

    def test_shared_barrel_contacts_and_reversed_drive(self):
        mesh = via_chain()
        direct = solve_conforming_dc(mesh, 0, 2)
        for ports in ((0, 2), (2, 0)):
            result = solve_iterative_conforming_dc(mesh, *ports)
            self.assertAlmostEqual(result["resistance_ohm"], 2.0, places=11)
            self.assertAlmostEqual(result["resistance_ohm"], direct["resistance_ohm"], places=11)
            self.assertEqual(result["dense_factor_order"], 2)
            self.assertLess(result["maximum_barrel_voltage_error_v"], 1e-12)

    def test_offset_via_contacts_with_planar_loss_and_material_scaling(self):
        mesh = rectangle_mesh([(0, (0, 0, 1, 1)), (2, (1, 0, 2, 1))], (0, 1, 2, 3))
        for original in list(mesh.cells):
            cell = dict(original, layer="B.Cu", control_node=1 if original["control_node"] == 0 else 3)
            cell["vertices_mm"] = [[x, y, 1] for x, y, _ in original["vertices_mm"]]
            mesh.cells.append(cell)
        mesh.branches.append(MeshBranch("conforming:back", "zone", 1, 3,
            (0, 0, 1), (1, 0, 1), 1, 1, 1000, "B.Cu", "N", "sheet"))
        mesh.branches.append(MeshBranch("via", "via", 2, 3,
            (1.5, .5, 0), (1.5, .5, 1), 1, 1, 1000, "F.Cu", "N", "via"))
        reference = solve_conforming_dc(mesh, 0, 1)["resistance_ohm"]
        self.assertGreater(reference, 1.0)  # A one-ohm barrel is not the entire path.
        for multiplier in (1.0, 1e5):
            for branch in mesh.branches:
                branch.conductivity_s_m = 1000*multiplier
            result = solve_iterative_conforming_dc(mesh, 0, 1)
            self.assertAlmostEqual(result["resistance_ohm"]*multiplier, reference, places=10)
            self.assertLess(result["relative_energy_error"], 1e-10)

    def test_hanging_mesh_direct_equivalence(self):
        mesh = rectangle_mesh([(0, (0, 0, 1, 2)), (1, (1, 0, 2, 1)), (2, (1, 1, 2, 2))])
        expected = solve_conforming_dc(mesh, 0, 1)
        actual = solve_iterative_conforming_dc(mesh, 0, 1)
        self.assertAlmostEqual(actual["resistance_ohm"], expected["resistance_ohm"], places=12)
        self.assertLess(actual["maximum_face_kcl_error_a"], 1e-12)

    def test_disconnected_component_does_not_change_gauge(self):
        mesh = coupon()
        original = solve_iterative_conforming_dc(mesh, 0, 1)
        extra = rectangle_mesh([(999, (5, 0, 6, 1))], contacts=())
        mesh.cells += extra.cells
        result = solve_iterative_conforming_dc(mesh, 0, 1)
        self.assertAlmostEqual(result["resistance_ohm"], original["resistance_ohm"], places=12)
        self.assertEqual(result["global_trace_count"], original["global_trace_count"])

    def test_iteration_exhaustion_is_failure(self):
        with self.assertRaisesRegex(ValueError, "failed convergence"):
            solve_iterative_conforming_dc(coupon(), 0, 1, max_iterations=1)

    def test_false_success_is_rejected_by_recomputed_physical_checks(self):
        def bogus_cg(operator, rhs, **kwargs):
            return np.zeros(len(rhs)), 0

        with patch("python.spike_core.peec_rt0_iterative.cg", side_effect=bogus_cg):
            with self.assertRaisesRegex(ValueError, "checks failed"):
                solve_iterative_conforming_dc(coupon(), 0, 1)

    def test_cancellation_and_timeout_fail_before_assembly(self):
        with patch("python.spike_core.peec_rt0_iterative.assemble_conforming_dc") as assemble:
            with self.assertRaisesRegex(ValueError, "cancelled"):
                solve_iterative_conforming_dc(coupon(), 0, 1, cancelled=lambda: True)
            assemble.assert_not_called()
        with patch("python.spike_core.peec_rt0_iterative.monotonic", side_effect=[0.0, 2.0]):
            with self.assertRaisesRegex(ValueError, "timeout"):
                solve_iterative_conforming_dc(coupon(), 0, 1, timeout_s=1)

    def test_cancellation_during_iteration(self):
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls >= 4

        with self.assertRaisesRegex(ValueError, "cancelled"):
            solve_iterative_conforming_dc(coupon(), 0, 1, cancelled=cancel)

    def test_caps_invalid_controls_and_disconnected_terminals(self):
        with self.assertRaisesRegex(ValueError, "barrel-block budget"):
            solve_iterative_conforming_dc(via_chain(), 0, 2, max_vias=1)
        for controls in ({"max_iterations": True}, {"max_vias": 0},
                         {"relative_tolerance": 1e-3}, {"timeout_s": float("nan")},
                         {"cancelled": False}, {"max_triangles": 4}, {"max_unknowns": 10}):
            with self.subTest(controls=controls), self.assertRaises(ValueError):
                solve_iterative_conforming_dc(coupon(), 0, 1, **controls)
        mesh = rectangle_mesh([(0, (0, 0, 1, 1)), (1, (2, 0, 3, 1))])
        with self.assertRaisesRegex(ValueError, "disconnected"):
            solve_iterative_conforming_dc(mesh, 0, 1)


if __name__ == "__main__":
    unittest.main()
