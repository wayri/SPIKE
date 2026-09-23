# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Independent polynomial/topological checks; these do not validate an EFIE."""
import unittest

import numpy as np

from python.spike_core.mom_surface_basis import build_surface_basis, divergence, evaluate, SurfaceBasisError


POINTS = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
FACES = [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]]


class SurfaceBasisTests(unittest.TestCase):
    def test_closed_topology_and_integrated_divergence(self):
        mesh = build_surface_basis(POINTS, FACES)
        self.assertEqual(len(mesh.edges), 6)
        self.assertEqual(mesh.boundary_edges, ())
        self.assertEqual(mesh.connected_components, 1)
        self.assertFalse(mesh.intersection_free_proven)
        self.assertFalse(mesh.executable_em_solver)
        for ei, edge in enumerate(mesh.edges):
            integrated = [divergence(mesh, ei, fi) * area for fi, area in enumerate(mesh.areas_m2)]
            self.assertAlmostEqual(sum(integrated), 0.)
            self.assertAlmostEqual(integrated[edge.plus_face], edge.length_m)
            self.assertAlmostEqual(integrated[edge.minus_face], -edge.length_m)

    def test_tangency_edge_flux_and_divergence_theorem(self):
        mesh = build_surface_basis(POINTS, FACES)
        for ei, edge in enumerate(mesh.edges):
            outward_flux = []
            for fi in (edge.plus_face, edge.minus_face):
                face = mesh.triangles[fi]
                bary = [[.5 if v in edge.vertices else 0. for v in face]]
                field = evaluate(mesh, ei, fi, bary)[0]
                normal = np.array(mesh.normals[fi])
                self.assertAlmostEqual(float(field @ normal), 0.)
                local = next(i for i in range(3) if {face[i], face[(i+1)%3]} == set(edge.vertices))
                tangent = np.subtract(mesh.vertices_m[face[(local+1)%3]], mesh.vertices_m[face[local]]) / edge.length_m
                conormal = np.cross(tangent, normal)
                outward_flux.append(float(field @ conormal))
                # Normal flux vanishes on the other two edges.
                integral = 0.
                for j in range(3):
                    aa, bb = face[j], face[(j+1)%3]
                    segment = np.subtract(mesh.vertices_m[bb], mesh.vertices_m[aa])
                    w = [[.5 if v in (aa, bb) else 0. for v in face]]
                    integral += float(evaluate(mesh, ei, fi, w)[0] @ np.cross(segment, normal))
                self.assertAlmostEqual(integral, divergence(mesh, ei, fi)*mesh.areas_m2[fi])
            self.assertAlmostEqual(outward_flux[0], 1.)
            self.assertAlmostEqual(outward_flux[1], -1.)

    def test_polynomial_gram_positive_definite(self):
        mesh = build_surface_basis(POINTS, FACES)
        gram = np.zeros((6, 6))
        # Three-point triangle rule is exact for products of affine RWGs.
        points = [[2/3, 1/6, 1/6], [1/6, 2/3, 1/6], [1/6, 1/6, 2/3]]
        for fi, area in enumerate(mesh.areas_m2):
            values = np.array([evaluate(mesh, ei, fi, points) for ei in range(6)])
            gram += area/3 * np.einsum('iqk,jqk->ij', values, values)
        np.testing.assert_allclose(gram, gram.T, atol=1e-14)
        self.assertGreater(np.linalg.eigvalsh(gram)[0], .01)

    def test_canonical_permutations(self):
        expected = build_surface_basis(POINTS, FACES)
        order = [2, 0, 3, 1]
        inverse = {old: new for new, old in enumerate(order)}
        faces = [[inverse[v] for v in face[1:]+face[:1]] for face in reversed(FACES)]
        self.assertEqual(build_surface_basis([POINTS[i] for i in order], faces), expected)

    def test_scale_units_and_disconnected_components(self):
        baseline = build_surface_basis(POINTS, FACES)
        for scale in (1e-6, 1e6):
            scaled = build_surface_basis(np.array(POINTS)*scale, FACES)
            np.testing.assert_allclose(scaled.areas_m2, np.array(baseline.areas_m2)*scale**2)
            for ei, edge in enumerate(baseline.edges):
                fi = edge.plus_face
                np.testing.assert_allclose(evaluate(scaled, ei, fi, [[.2,.3,.5]]), evaluate(baseline, ei, fi, [[.2,.3,.5]]), atol=1e-14)
                self.assertAlmostEqual(divergence(scaled, ei, fi)*scale, divergence(baseline, ei, fi))
        points = POINTS + (np.array(POINTS)+[3.,0.,0.]).tolist()
        mesh = build_surface_basis(points, FACES+[[i+4 for i in face] for face in FACES])
        self.assertEqual(mesh.connected_components, 2)
        self.assertEqual(len(mesh.edges), 12)

    def test_open_surface_has_no_half_basis(self):
        mesh = build_surface_basis(POINTS[:3], [[0, 1, 2]])
        self.assertEqual(len(mesh.boundary_edges), 3)
        self.assertEqual(len(mesh.edges), 0)
        square = build_surface_basis([[0,0,0], [1,0,0], [1,1,0], [0,1,0]], [[0,1,2], [0,2,3]])
        self.assertEqual(len(square.edges), 1)
        self.assertEqual(len(square.boundary_edges), 4)

    def test_reject_bad_topology(self):
        cases = [
            (POINTS, [FACES[0], FACES[1], list(reversed(FACES[2])), FACES[3]]),
            (POINTS[:3], [[0,1,2], [2,1,0]]),
            (POINTS[:3], [[0,0,2]]),
            (POINTS[:3], [[0,1,3]]),
            (POINTS[:3], [[False,1,2]]),
            (POINTS, [[0,1,2]]),
            ([[0,0,0], [1,0,0], [2,0,0]], [[0,1,2]]),
            ([[0,0,0], [1,0,0], [0,1,0], [-1,0,0], [0,-1,0]], [[0,1,2], [0,3,4]]),
            (POINTS + [[0,-1,0]], [[0,1,2], [1,0,3], [0,1,4]]),
        ]
        for points, faces in cases:
            with self.subTest(points=points, faces=faces), self.assertRaises(SurfaceBasisError):
                build_surface_basis(points, faces)

    def test_numeric_admission_and_bounds(self):
        for value in (float('nan'), float('inf'), 10**1000, True, '0'):
            with self.subTest(value=str(value)[:20]), self.assertRaises(SurfaceBasisError):
                build_surface_basis([[value,0,0], [1,0,0], [0,1,0]], [[0,1,2]])
        with self.assertRaises(SurfaceBasisError):
            build_surface_basis(np.array(POINTS)*1e200, FACES)
        with self.assertRaises(SurfaceBasisError):
            build_surface_basis([[True,0,0], [2,0,0], [0,1,0]], [[0,1,2]])
        mesh = build_surface_basis(POINTS, FACES)
        for weights in ([[1,1,1]], [[-1,1,1]], [[float('nan'),0,1]], [['1','0','0']]):
            with self.assertRaises(SurfaceBasisError):
                evaluate(mesh, 0, 0, weights)
        for index in (-1, True, 1.5, 6):
            with self.assertRaises(SurfaceBasisError):
                divergence(mesh, index, 0)


if __name__ == '__main__':
    unittest.main()
