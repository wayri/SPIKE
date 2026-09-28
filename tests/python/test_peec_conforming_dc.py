# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent affine, conservation and finite-contact analytical oracles."""

import unittest

import numpy as np

from python.spike_core.hybrid_mesh import HybridMesh, MeshBranch
from python.spike_core.peec_conforming_dc import (
    assemble_conforming_dc, solve_conforming_dc, triangle_resistance,
    solve_hybridized_conforming_dc,
)


def rectangle_mesh(rectangles, contacts=(0, 1), conductance=1.0):
    mesh = HybridMesh()
    for index, (node, (x0,y0,x1,y1)) in enumerate(rectangles):
        mesh.cells.append({"kind":"surface", "layer":"F.Cu", "net":"N",
            "control_node":node, "vertices_mm":[[x0,y0,0],[x1,y0,0],[x1,y1,0],[x0,y1,0]]})
    # Assembly reads material from admitted planar branches, not their TPFA R.
    mesh.branches.append(MeshBranch("conforming:material", "zone", 0, 1,
        (0,0,0),(1,0,0),1,1,conductance*1000,"F.Cu","N","sheet"))
    mesh.branch_admission["conforming_partition"] = {
        "terminal_contacts":[{"node":node} for node in contacts]}
    return mesh


class ConformingDCTests(unittest.TestCase):
    def assert_condensation_equivalent(self, mesh, source=0, load=1):
        mixed = solve_conforming_dc(mesh, source, load)
        original = solve_hybridized_conforming_dc(mesh, source, load, condense_spokes=False)
        condensed = solve_hybridized_conforming_dc(mesh, source, load)
        reverse = solve_hybridized_conforming_dc(mesh, load, source)
        for result in (mixed, original, reverse):
            np.testing.assert_allclose(condensed["resistance_ohm"], result["resistance_ohm"],
                                       rtol=1e-10, atol=1e-13)
            np.testing.assert_allclose(condensed["dissipation_w_at_one_ampere"],
                result["dissipation_w_at_one_ampere"], rtol=1e-10, atol=1e-13)
        self.assertLess(condensed["global_unknown_count"], original["global_unknown_count"])
        self.assertEqual(condensed["uncondensed_global_unknown_count"], original["global_unknown_count"])
        self.assertEqual(condensed["global_unknown_count"]+condensed["eliminated_spoke_trace_count"],
                         original["global_unknown_count"])
        self.assertLess(condensed["relative_residual"], 1e-10)
        self.assertLess(condensed["maximum_cell_kcl_error_a"], 1e-10)
        self.assertLess(condensed["maximum_face_kcl_error_a"], 1e-10)
        self.assertLess(condensed["relative_energy_error"], 1e-10)
        self.assertFalse(condensed["production_qualified"])

    def test_rectangle_condensation_hanging_faces_and_shared_contact_owners(self):
        self.assert_condensation_equivalent(rectangle_mesh(
            [(0,(0,0,1,2)), (1,(1,0,2,1)), (2,(1,1,2,2))]))
        # Distinct rectangles with the same contact node must not be grouped
        # into an equipotential cell or lose their uniform distributed source.
        self.assert_condensation_equivalent(rectangle_mesh(
            [(0,(0,0,.5,1)), (0,(.5,0,1,1)), (2,(1,0,2,1)),
             (1,(2,0,2.5,1)), (1,(2.5,0,3,1))]))

    def test_condensation_admits_smaller_actual_global_system_with_same_caps(self):
        mesh = rectangle_mesh([(0,(0,0,1,1)), (2,(1,0,2,1)), (1,(2,0,3,1))])
        with self.assertRaisesRegex(ValueError, "unknown budget"):
            solve_hybridized_conforming_dc(mesh, 0, 1, max_unknowns=10, condense_spokes=False)
        result = solve_hybridized_conforming_dc(mesh, 0, 1, max_unknowns=10)
        self.assertEqual(result["global_unknown_count"], 9)
        self.assertEqual(result["eliminated_spoke_trace_count"], 12)
        self.assertEqual(result["global_unknown_budget"], 10)
        with self.assertRaisesRegex(ValueError, "budget"):
            solve_hybridized_conforming_dc(mesh, 0, 1, max_triangles=11)

    def test_hanging_face_affine_patch_each_face_and_rotation(self):
        mesh = rectangle_mesh([(0,(0,0,1,2)), (1,(1,0,2,1)), (2,(1,1,2,2))])
        system = assemble_conforming_dc(mesh)
        self.assertEqual(len(system.triangles_mm), 13)
        for angle in (0, 0.37, 1.21):
            rotation = np.array([[np.cos(angle),-np.sin(angle)], [np.sin(angle),np.cos(angle)]])
            for gradient in (np.array([0.,1.]), np.array([0.7,-1.3])):
                gradient = rotation@gradient
                for triangle in system.triangles_mm:
                    triangle = triangle@rotation.T
                    midpoints = (np.roll(triangle,-1,axis=0)+np.roll(triangle,-2,axis=0))/2
                    lam = midpoints@gradient + 0.3
                    mass = triangle_resistance(triangle, 2.5)
                    inverse_one = np.linalg.solve(mass, np.ones(3))
                    pressure = float(inverse_one@lam/inverse_one.sum())
                    flux = np.linalg.solve(mass, pressure-lam)
                    tangents = np.roll(triangle,-2,axis=0)-np.roll(triangle,-1,axis=0)
                    normals = np.column_stack((tangents[:,1], -tangents[:,0]))
                    exact = -2.5*(normals@gradient)
                    np.testing.assert_allclose(flux, exact, rtol=1e-13, atol=8e-14)
                    inverse = np.linalg.inv(mass)
                    h_local = inverse-np.outer(inverse_one,inverse_one)/inverse_one.sum()
                    np.testing.assert_allclose(-h_local@lam,exact,rtol=1e-13,atol=8e-14)
                    self.assertAlmostEqual(float(flux.sum()), 0.0, places=12)
                    self.assertAlmostEqual(pressure, float(triangle.mean(axis=0)@gradient+0.3), places=12)

    def test_global_affine_field_has_shared_flux_and_cell_conservation(self):
        system = assemble_conforming_dc(rectangle_mesh(
            [(0,(0,0,1,2)), (1,(1,0,2,1)), (2,(1,1,2,2))]))
        gradient = np.array([0.,1.])
        tangents = system.edges_mm[:,1]-system.edges_mm[:,0]
        normals = np.column_stack((tangents[:,1], -tangents[:,0]))
        currents = -(normals@gradient)
        pressure = system.triangles_mm.mean(axis=1)@gradient
        boundary = np.zeros(len(currents))
        boundary[system.boundary_edges] = system.edges_mm[system.boundary_edges].mean(axis=1)@gradient
        np.testing.assert_allclose(system.incidence@currents, 0, atol=2e-15)
        np.testing.assert_allclose(system.resistance@currents-system.incidence.T@pressure,
                                   -boundary, atol=3e-15)
        hanging_face = np.all(system.edges_mm[:,:,0] == 1, axis=1)
        self.assertEqual(np.count_nonzero(hanging_face), 2)
        np.testing.assert_array_equal(currents[hanging_face], 0)

    def test_finite_distributed_contacts_converge_to_sheet_loss(self):
        # L=2,W=1,k=1. Uniform source on [0,a], sink on [L-a,L],
        # a=.5 gives I(x)=x/a,1,(L-x)/a and integral(I^2)/kW=L-4a/3.
        exact = 2 - 4*0.5/3
        errors = []
        for divisions in (4,8,16):
            h = 1/divisions
            rectangles = []
            for ix in range(2*divisions):
                for iy in range(divisions):
                    node = 0 if ix < divisions//2 else (1 if ix >= 3*divisions//2 else 2+ix*divisions+iy)
                    rectangles.append((node,(ix*h,iy*h,(ix+1)*h,(iy+1)*h)))
            result = solve_conforming_dc(rectangle_mesh(rectangles), 0, 1)
            hybrid = solve_hybridized_conforming_dc(rectangle_mesh(rectangles), 0, 1)
            self.assertAlmostEqual(hybrid["resistance_ohm"],result["resistance_ohm"],places=10)
            self.assertLess(hybrid["maximum_cell_kcl_error_a"],1e-11)
            self.assertLess(hybrid["maximum_face_kcl_error_a"],1e-11)
            errors.append(abs(result["resistance_ohm"]-exact))
            self.assertLess(result["maximum_cell_kcl_error_a"], 1e-10)
            self.assertLess(result["relative_energy_error"], 1e-11)
            self.assertFalse(result["production_qualified"])
        self.assertLess(errors[-1], 0.001)
        self.assertLess(errors[1], errors[0]/3.8)
        self.assertLess(errors[2], errors[1]/3.8)

    def test_via_keeps_finite_barrel_and_planar_contact_loss(self):
        base = [(0,(0,0,1,1)), (2,(1,0,2,1))]
        mesh = rectangle_mesh(base, (0,1,2,3))
        for cell in list(mesh.cells):
            copy = dict(cell, layer="B.Cu", control_node=1 if cell["control_node"] == 0 else 3)
            copy["vertices_mm"] = [[x,y,1] for x,y,z in cell["vertices_mm"]]
            mesh.cells.append(copy)
        mesh.branches.append(MeshBranch("conforming:other", "zone", 1, 3,
            (0,0,1),(1,0,1),1,1,1000,"B.Cu","N","sheet"))
        mesh.branches.append(MeshBranch("via", "via", 2, 3,
            (1.5,.5,0),(1.5,.5,1),1,1,1000,"F.Cu","N","via"))
        mesh.cells.append({"kind":"surface", "source_kind":"via", "layer":"F.Cu->B.Cu",
            "vertices_mm":[[1.4,.5,0],[1.5,.6,0],[1.5,.6,1],[1.4,.5,1]]})
        first = solve_conforming_dc(mesh, 0, 1)
        hybrid = solve_hybridized_conforming_dc(mesh, 0, 1)
        self.assertAlmostEqual(hybrid["resistance_ohm"],first["resistance_ohm"],places=11)
        self.assert_condensation_equivalent(mesh)
        mesh.branches[-1].conductivity_s_m = 500
        second = solve_conforming_dc(mesh, 0, 1)
        self.assertGreater(first["resistance_ohm"], 1.0)
        self.assertAlmostEqual(second["resistance_ohm"]-first["resistance_ohm"], 1.0, places=11)

    def test_hybrid_shared_contact_between_two_barrels(self):
        mesh = rectangle_mesh([(0,(0,0,1,1))],(0,1,2))
        for index, layer in enumerate(("In1.Cu","B.Cu"),1):
            cell = dict(mesh.cells[0],layer=layer,control_node=index)
            cell["vertices_mm"] = [[x,y,index] for x,y,z in mesh.cells[0]["vertices_mm"]]
            mesh.cells.append(cell)
            mesh.branches.append(MeshBranch(f"conforming:{index}","zone",index,index,
                (0,0,index),(1,0,index),1,1,1000,layer,"N","sheet"))
            mesh.branches.append(MeshBranch(f"via:{index}","via",index-1,index,
                (.5,.5,index-1),(.5,.5,index),1,1,1000,layer,"N","via"))
        # Matching uniform injection and barrel extraction have zero in-plane
        # divergence. The middle contact's two opposite barrel currents cancel.
        mixed = solve_conforming_dc(mesh,0,2)
        hybrid = solve_hybridized_conforming_dc(mesh,0,2)
        reverse = solve_hybridized_conforming_dc(mesh,2,0)
        self.assertAlmostEqual(mixed["resistance_ohm"],2.0,places=12)
        self.assertAlmostEqual(hybrid["resistance_ohm"],2.0,places=12)
        self.assertAlmostEqual(reverse["resistance_ohm"],2.0,places=12)
        self.assert_condensation_equivalent(mesh,0,2)

    def test_rejects_partial_disconnected_malformed_and_over_budget(self):
        mesh = rectangle_mesh([(0,(0,0,1,1)), (1,(2,0,3,1))])
        with self.assertRaisesRegex(ValueError, "disconnected"):
            solve_conforming_dc(mesh, 0, 1)
        with self.assertRaisesRegex(ValueError, "disconnected"):
            solve_hybridized_conforming_dc(mesh, 0, 1)
        mesh.truncated = True
        with self.assertRaisesRegex(ValueError, "partial"):
            solve_conforming_dc(mesh, 0, 1)
        mesh.truncated = False
        with self.assertRaisesRegex(ValueError, "budget"):
            solve_conforming_dc(mesh, 0, 1, max_unknowns=10)
        with self.assertRaisesRegex(ValueError, "budget"):
            solve_hybridized_conforming_dc(mesh, 0, 1, max_triangles=4)
        with self.assertRaisesRegex(ValueError, "budget"):
            solve_hybridized_conforming_dc(rectangle_mesh(
                [(0,(0,0,1,1)), (2,(1,0,2,1)), (3,(2,0,3,1)), (1,(3,0,4,1))]),
                0, 1, max_unknowns=10)
        mesh = rectangle_mesh([(0,(0,0,1,1)), (1,(.5,0,1.5,1))])
        with self.assertRaisesRegex(ValueError, "overlap"):
            solve_conforming_dc(mesh, 0, 1)
        with self.assertRaisesRegex(ValueError, "degenerate"):
            triangle_resistance(np.array([[0,0],[1,0],[2,0]]), 1)


if __name__ == "__main__":
    unittest.main()
