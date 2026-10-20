# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original tetra fixtures; analytical affine identities, not CFD validation."""
import copy
from fractions import Fraction
import itertools
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.cfd_tetra_mesh import (
    CONTRACT, CfdTetraMeshError, admit_cfd_tetra_mesh, prepare_cfd_tetra_mesh,
)


def mesh_fixture(two=False):
    vertices = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
    cells = [[0, 1, 2, 3]]
    if two:
        vertices.append([0., 0., -1.])
        cells.append([0, 2, 1, 4])
    return with_boundary(vertices, cells)


def with_boundary(vertices, cells):
    occurrences = {}
    for cell in cells:
        for face in itertools.combinations(cell, 3):
            key = tuple(sorted(face))
            occurrences[key] = occurrences.get(key, 0)+1
    return {"contract": CONTRACT, "units": "m", "vertices": vertices, "cells": cells,
            "boundary_patches": {"wall": [list(f) for f, n in occurrences.items() if n == 1]}}


def occ_fixture():
    """Minimal independently constructed existing-result schema, in millimetres."""
    numerical = mesh_fixture()
    cell = {"id": "42", "kind": "tetrahedron", "vertices": [0, 1, 2, 3],
            "material_id": "air", "source_object_ids": ["fluid"]}
    boundary = [{"vertices": face, "cad_surface_tag": i+1, "cell_ids": ["42"],
                 "material_ids": ["air"], "source_object_ids": ["fluid"]}
                for i, face in enumerate(numerical["boundary_patches"]["wall"])]
    return {"contract": "spike/gmsh-occ-mesh-result/v1", "status": "completed",
            "production_qualified": False, "scope": "single_closed_step_solid_first_order_tetrahedra",
            "mesh": {"contract": "spike/solver-mesh/v1", "units": "mm",
                     "coordinate_system": "right_handed_xyz", "vertices": numerical["vertices"],
                     "cells": [cell], "counts": {"vertices": 4, "cells": 1},
                     "object_map": {"fluid": {"kind": "step_solid"}}},
            "boundary_faces": boundary, "boundary_triangles": [f["vertices"] for f in boundary],
            "interface_faces": [],
            "fragment_ownership": {"1": {"material_id": "air", "source_object_ids": ["fluid"],
                                        "cad_volume_mm3": 1./6.}},
            "metrics": {"cad_volume_mm3": 1./6., "tetrahedron_volume_mm3": 1./6.,
                        "source_cad_volumes_mm3": {"fluid": 1./6.},
                        "fragment_mesh_volumes_mm3": {"1": 1./6.},
                        "minimum_mean_ratio_quality": 1.}}


class CfdTetraMeshTests(unittest.TestCase):
    def test_reference_tetra_geometry_and_opposite_vertex_order(self):
        result = admit_cfd_tetra_mesh(mesh_fixture())
        self.assertAlmostEqual(result["volumes"][0], 1./6., places=14)
        expected = [[-1., -1., -1.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
        np.testing.assert_allclose(result["barycentric_gradients"][0], expected, rtol=0, atol=1e-14)
        np.testing.assert_allclose(result["cell_centroids"], [[.25, .25, .25]], atol=1e-14)
        for opposite, face in enumerate(result["cell_faces"][0]):
            self.assertEqual(set(result["face_vertices"][face]), set(range(4))-{opposite})
        self.assertFalse(result["global_intersections_checked"])

    def test_rotated_sheared_translated_cell_moments_and_linear_gradient(self):
        matrix = np.array([[2., .25, -.125], [0., 1.5, .375], [0., 0., .75]])
        rotation = np.array([[0., -1., 0.], [0., 0., 1.], [-1., 0., 0.]])
        transform = rotation @ matrix  # proper rotation, determinant +1
        mesh = mesh_fixture()
        origin = np.array([1e6, -2e6, 3e6])
        mesh["vertices"] = (np.asarray(mesh["vertices"]) @ transform.T+origin).tolist()
        result = admit_cfd_tetra_mesh(mesh)
        self.assertAlmostEqual(result["volumes"][0], .375, places=13)
        g = np.array([2., -3., .75])
        relative_vertices = np.asarray(mesh["vertices"])-origin
        reconstructed = (relative_vertices @ g) @ result["barycentric_gradients"][0]
        np.testing.assert_allclose(reconstructed, g, rtol=1e-13, atol=1e-13)
        f = result["cell_faces"][0]
        vectors = result["face_areas"][f, None]*result["cell_outward_normals"][0]
        np.testing.assert_allclose(vectors.sum(axis=0), 0., atol=1e-13)
        moments = (result["face_centroids"][f]-origin).T @ vectors
        np.testing.assert_allclose(moments, .375*np.eye(3), rtol=1e-9, atol=1e-9)

    def test_two_cells_cancel_shared_flux_and_preserve_patch_order(self):
        mesh = mesh_fixture(True)
        mesh["boundary_patches"]["wall"].reverse()
        result = admit_cfd_tetra_mesh(mesh)
        interior = np.flatnonzero(result["face_owners"][:, 1] >= 0)
        self.assertEqual(len(interior), 1)
        face = int(interior[0])
        normal = []
        for owner in result["face_owners"][face]:
            local = list(result["cell_faces"][owner]).index(face)
            normal.append(result["cell_outward_normals"][owner, local])
        np.testing.assert_array_equal(normal[0], -normal[1])
        for expected, actual in zip(mesh["boundary_patches"]["wall"], result["boundary_patches"]["wall"]):
            self.assertEqual(set(expected), set(result["face_vertices"][actual]))
        np.testing.assert_array_equal(result["components"][0], [0, 1])

    def test_disconnected_components_and_copied_inputs(self):
        first = mesh_fixture()
        vertices = first["vertices"]+[(np.asarray(v)+[3., 0., 0.]).tolist() for v in first["vertices"]]
        mesh = with_boundary(vertices, [[0, 1, 2, 3], [4, 5, 6, 7]])
        before = copy.deepcopy(mesh)
        result = admit_cfd_tetra_mesh(mesh)
        self.assertEqual([c.tolist() for c in result["components"]], [[0], [1]])
        result["vertices"][0, 0] = 99.
        self.assertEqual(mesh, before)

    def test_scale_similarity_and_unrepresentable_rejection(self):
        for scale in (1e-40, 1e40):
            mesh = mesh_fixture()
            mesh["vertices"] = (np.asarray(mesh["vertices"])*scale).tolist()
            result = admit_cfd_tetra_mesh(mesh)
            self.assertAlmostEqual(result["volumes"][0]/scale**3, 1./6., places=13)
            self.assertTrue(np.isfinite(result["barycentric_gradients"]).all())
        mesh = mesh_fixture()
        mesh["vertices"] = (np.asarray(mesh["vertices"])*1e-120).tolist()
        with self.assertRaises(CfdTetraMeshError):
            admit_cfd_tetra_mesh(mesh)

    def test_bad_geometry_topology_and_patch_coverage(self):
        mutations = [
            lambda m: m["cells"][0].__setitem__(slice(None), [1, 0, 2, 3]),
            lambda m: m["vertices"][3].__setitem__(2, 1e-9),
            lambda m: m["vertices"][3].__setitem__(2, 0.),
            lambda m: m["vertices"].append([3., 3., 3.]),
            lambda m: m["vertices"].__setitem__(3, [0., 0., 0.]),
            lambda m: m["cells"].append([0, 1, 2, 3]),
            lambda m: m["boundary_patches"]["wall"].pop(),
            lambda m: m["boundary_patches"]["wall"].append([0, 1, 2]),
            lambda m: m["boundary_patches"].__setitem__("empty", []),
            lambda m: m["cells"][0].__setitem__(0, False),
            lambda m: m["vertices"][0].__setitem__(0, True),
            lambda m: m["vertices"][0].__setitem__(0, math.nan),
            lambda m: m.update(extra=True),
            lambda m: m.update(units="mm"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                mesh = mesh_fixture()
                mutate(mesh)
                with self.assertRaises(CfdTetraMeshError):
                    admit_cfd_tetra_mesh(mesh)
        mesh = mesh_fixture(True)
        mesh["boundary_patches"]["wall"].append([0, 1, 2])
        with self.assertRaisesRegex(CfdTetraMeshError, "exterior"):
            admit_cfd_tetra_mesh(mesh)

    def test_same_side_overlap_nonmanifold_face_and_pinched_edge(self):
        mesh = mesh_fixture()
        vertices = mesh["vertices"]+[[.1, .1, .5]]
        with self.assertRaisesRegex(CfdTetraMeshError, "opposite sides"):
            admit_cfd_tetra_mesh(with_boundary(vertices, [[0, 1, 2, 3], [0, 1, 2, 4]]))
        vertices.append([0., 0., -1.])
        with self.assertRaisesRegex(CfdTetraMeshError, "Nonmanifold face"):
            admit_cfd_tetra_mesh(with_boundary(vertices, [[0, 1, 2, 3], [0, 2, 1, 5], [0, 1, 2, 4]]))
        vertices = mesh["vertices"]+[[0., -1., 0.], [0., 0., -1.]]
        with self.assertRaisesRegex(CfdTetraMeshError, "exterior edge"):
            admit_cfd_tetra_mesh(with_boundary(vertices, [[0, 1, 2, 3], [0, 1, 4, 5]]))

    def test_resource_and_cancellation_gates_before_numerical_allocation(self):
        mesh = mesh_fixture()
        mesh["cells"] *= 4097
        with patch("python.spike_core.cfd_tetra_mesh.np.array", side_effect=AssertionError("allocated")):
            with self.assertRaisesRegex(CfdTetraMeshError, "resource"):
                admit_cfd_tetra_mesh(mesh)
        with self.assertRaises(InterruptedError):
            admit_cfd_tetra_mesh(mesh_fixture(), cancel_check=lambda: True)
        polls = [0]
        def cancel():
            polls[0] += 1
            return polls[0] > 1
        with self.assertRaises(InterruptedError):
            admit_cfd_tetra_mesh(mesh_fixture(), cancel_check=cancel)

    def test_occ_bridge_units_provenance_and_curved_volume_discrepancy(self):
        source = occ_fixture()
        assignments = {1: "inlet", 2: "outlet", 3: "wall", 4: "wall"}
        before = copy.deepcopy(source)
        converted = prepare_cfd_tetra_mesh(source, assignments)
        self.assertEqual(source, before)
        geometry = admit_cfd_tetra_mesh(converted["mesh"])
        self.assertAlmostEqual(geometry["volumes"][0]/1e-9, 1./6., places=13)
        self.assertEqual(converted["provenance"]["original_cell_records"][0]["id"], "42")
        self.assertEqual(len(converted["provenance"]["occ_result_sha256"]), 64)
        self.assertFalse(converted["provenance"]["source_authenticity_verified"])
        source["fragment_ownership"]["1"]["cad_volume_mm3"] = .2
        source["metrics"]["cad_volume_mm3"] = .2
        source["metrics"]["source_cad_volumes_mm3"]["fluid"] = .2
        curved = prepare_cfd_tetra_mesh(source, assignments)
        self.assertAlmostEqual(curved["geometry_diagnostics"]["relative_cad_tetra_volume_difference"], 1./6.)
        self.assertNotEqual(curved["provenance"]["occ_result_sha256"],
                            converted["provenance"]["occ_result_sha256"])

    def test_forged_occ_membership_source_and_volume_bindings_rejected(self):
        mutations = [
            lambda r: r["boundary_faces"][0].update(cell_ids=["999"]),
            lambda r: r["boundary_faces"][0].update(material_ids=["copper"]),
            lambda r: r["boundary_faces"][0].update(source_object_ids=["other"]),
            lambda r: r["mesh"]["object_map"].update(other={"kind": "step"}),
            lambda r: r["fragment_ownership"]["1"].update(material_id="water"),
            lambda r: r["fragment_ownership"]["1"].update(source_object_ids=["other"]),
            lambda r: r["metrics"].update(tetrahedron_volume_mm3=.2),
            lambda r: r["metrics"]["source_cad_volumes_mm3"].update(fluid=.2),
            lambda r: r["metrics"]["fragment_mesh_volumes_mm3"].update({"1": .2}),
            lambda r: r.update(boundary_triangles=[]),
            lambda r: r.update(interface_faces=[{}]),
            lambda r: r.update(request_sha256="forged"),
            lambda r: r.update(status="failed"),
            lambda r: r["mesh"]["cells"][0].update(source_object_ids=["other"]),
            lambda r: r["boundary_faces"][0].update(cad_surface_tag=True),
        ]
        for mutate in mutations:
            source = occ_fixture()
            mutate(source)
            with self.subTest(mutation=mutate), self.assertRaises(CfdTetraMeshError):
                prepare_cfd_tetra_mesh(source, {i: "wall" for i in range(1, 5)})
        for assignments in ({1: "wall"}, {i: "wall" for i in range(1, 6)},
                            {"1": "wall", 2: "wall", 3: "wall", 4: "wall"}):
            with self.assertRaises(CfdTetraMeshError):
                prepare_cfd_tetra_mesh(occ_fixture(), assignments)

    def test_global_overlap_without_shared_ids_and_exact_near_contact(self):
        original = mesh_fixture()["vertices"]
        for offset, overlaps in (([.1, .1, .1], True), ([.375]*3, False),
                                 ([.5, .25, .25], False),
                                 ([np.nextafter(.5, 0.), .25, .25], True),
                                 ([np.nextafter(.5, 1.), .25, .25], False)):
            vertices = original+[(np.asarray(v)+offset).tolist() for v in original]
            mesh = with_boundary(vertices, [[0, 1, 2, 3], [4, 5, 6, 7]])
            with self.subTest(offset=offset, overlaps=overlaps):
                if overlaps:
                    with self.assertRaisesRegex(CfdTetraMeshError, "Positive-volume"):
                        admit_cfd_tetra_mesh(mesh)
                else:
                    result = admit_cfd_tetra_mesh(mesh)
                    screen = result["intersection_screening"]
                    self.assertTrue(screen["positive_volume_overlap_checked"])
                    self.assertFalse(screen["nonshared_zero_measure_contacts_qualified"])
                    self.assertEqual(screen["candidate_pairs"], 1)
                    if offset[0] >= .5:
                        self.assertGreater(screen["exact_predicates"], 0)

    def test_sat_on_rotated_sheared_and_rescaled_nonintersecting_cells(self):
        original = np.asarray(mesh_fixture()["vertices"])
        transform = np.array([[1., .25, -.125], [.5, 1., .25], [0., -.25, 1.]])
        for scale in (2.**-80, 1., 2.**80):
            vertices = np.vstack((original, original+[.375]*3)) @ transform.T*scale
            mesh = with_boundary(vertices.tolist(), [[0, 1, 2, 3], [4, 5, 6, 7]])
            result = admit_cfd_tetra_mesh(mesh)
            self.assertTrue(result["intersection_screening"]["positive_volume_overlap_checked"])
        with patch("python.spike_core.cfd_tetra_intersections.MAX_CANDIDATES", 0):
            with self.assertRaisesRegex(CfdTetraMeshError, "candidate budget"):
                admit_cfd_tetra_mesh(mesh)
        vertices = np.vstack((original, original+[.5, .25, .25]))
        mesh = with_boundary(vertices.tolist(), [[0, 1, 2, 3], [4, 5, 6, 7]])
        with patch("python.spike_core.cfd_tetra_intersections.MAX_EXACT_PREDICATES", 0):
            with self.assertRaisesRegex(CfdTetraMeshError, "Exact intersection"):
                admit_cfd_tetra_mesh(mesh)

    def test_floating_sign_filter_against_independent_exact_determinants(self):
        from python.spike_core.cfd_tetra_intersections import _filtered_determinants
        random = np.random.default_rng(20261021)
        for shift in (0., 2.**40):
            for _ in range(30):
                p = random.normal(size=(6, 3))+shift
                e, f, g = p[1]-p[0], p[3]-p[2], p[5]-p[4]
                certified = int(_filtered_determinants(e, f, g))
                # Fraction endpoints precede subtraction, independently checking
                # the input-difference rounding included in the filter bound.
                rational = [[Fraction.from_float(float(x)) for x in row] for row in p]
                a, b, c = [[rational[i+1][j]-rational[i][j] for j in range(3)]
                           for i in (0, 2, 4)]
                exact = (a[0]*(b[1]*c[2]-b[2]*c[1])
                         - a[1]*(b[0]*c[2]-b[2]*c[0])
                         + a[2]*(b[0]*c[1]-b[1]*c[0]))
                if certified:
                    self.assertEqual(certified, int(exact > 0)-int(exact < 0))

    def test_cross_edge_axis_is_needed_for_disjoint_convex_tetrahedra(self):
        # Original integer fixture: all face projections overlap, but an
        # edge-edge axis separates. Integer dot products are exact here.
        points = np.array([[4, -3, 4], [4, 1, -4], [4, 1, 1], [0, 3, -3],
                           [2, 1, 2], [-3, -2, -4], [-4, -3, -4], [0, 2, -4]])
        cells = [[0, 2, 1, 3], [4, 5, 6, 7]]
        for cell in cells:
            for a, b, c in itertools.combinations(cell, 3):
                normal = np.cross(points[b]-points[a], points[c]-points[a])
                left, right = points[:4] @ normal, points[4:] @ normal
                self.assertGreater(left.max(), right.min())
                self.assertGreater(right.max(), left.min())
        axis = np.array([-29, -10, 8])
        left, right = points[:4] @ axis, points[4:] @ axis
        self.assertLessEqual(left.max(), right.min())
        result = admit_cfd_tetra_mesh(with_boundary(points.tolist(), cells))
        self.assertGreater(result["intersection_screening"]["axis_tests"], 8)


if __name__ == "__main__":
    unittest.main()
