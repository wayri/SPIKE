# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original rigid-frame/SI oracles and a cancelling-volume rounding regression."""
import copy
import itertools
import math
import unittest

import numpy as np

from python.spike_core.solvers.execution.coupling.assembly_field_geometry import lower_body, validate_frames
from python.spike_core.spider_v2 import AssemblyIRV1, BoardInstance
from python.spike_core.spider_v2_schema import CoordinateFrame


def assembly_at(rotation=None, translation_mm=(0, 0, 0)):
    matrix = np.eye(4)
    matrix[:3, :3] = np.eye(3) if rotation is None else rotation
    matrix[:3, 3] = translation_mm
    occurrence = BoardInstance(id="occurrence", design_id="original-fixture",
                               frame=CoordinateFrame(frame_id="occurrence-frame", parent_frame_id="assembly",
                                                     transform=tuple(matrix.flat)))
    return AssemblyIRV1(assembly_id="fixture", name="Original frame fixture", boards=[occurrence]), occurrence


def body_from_mesh(vertices, connectivity, units="mm"):
    cells, face_counts = [], {}
    for ids in connectivity:
        ids = list(ids)
        p = np.array([vertices[i] for i in ids])
        if np.linalg.det((p[1:] - p[0]).T) < 0:
            ids[1], ids[2] = ids[2], ids[1]
        cells.append({"id": f"cell-{len(cells)}", "kind": "tetrahedron", "vertices": ids,
                      "material_id": "local", "source_object_ids": ["source"]})
        for face in itertools.combinations(ids, 3):
            key = tuple(sorted(face))
            face_counts[key] = face_counts.get(key, 0) + 1
    mesh = {"contract": "spike/solver-mesh/v1", "units": units, "coordinate_system": "right_handed_xyz",
            "vertices": vertices, "cells": cells, "counts": {"vertices": len(vertices), "cells": len(cells)},
            "object_map": {"source": {"kind": "solid"}}}
    return {"mesh": mesh, "boundary_faces": [{"id": f"face-{i}", "vertices": list(face)}
                                              for i, (face, count) in enumerate(face_counts.items()) if count == 1],
            "material_map": {"local": "physical"}}


def cell_volumes(mesh):
    points = np.array(mesh["vertices"])
    return np.array([np.linalg.det((points[c["vertices"]][1:] - points[c["vertices"]][0]).T) / 6
                     for c in mesh["cells"]])


def near_face_cube():
    # Six square faces, two original triangles per face, joined to one interior
    # point. Moving that point changes element volumes but not total cube volume.
    points = list(map(list, itertools.product((0., 1.), repeat=3)))
    lookup = {tuple(point): i for i, point in enumerate(points)}
    center = len(points)
    points.append([1e-7, .5, .5])
    tets = []
    for axis in range(3):
        others = [i for i in range(3) if i != axis]
        for side in (0., 1.):
            corners = []
            for u, v in ((0., 0.), (1., 0.), (1., 1.), (0., 1.)):
                p = [0., 0., 0.]
                p[axis], p[others[0]], p[others[1]] = side, u, v
                corners.append(lookup[tuple(p)])
            tets.extend(([corners[0], corners[1], corners[2], center],
                         [corners[0], corners[2], corners[3], center]))
    return body_from_mesh(points, tets, "m")


class AssemblyFieldGeometryTests(unittest.TestCase):
    def test_exact_mm_to_m_translation(self):
        body = body_from_mesh([[0., 0., 0.], [2., 0., 0.], [0., 3., 0.], [0., 0., 4.]], [[0, 1, 2, 3]])
        before = copy.deepcopy(body)
        assembly, occurrence = assembly_at(translation_mm=(100, -20, 35))
        validate_frames(assembly)
        world, matrix, volume = lower_body(assembly, occurrence, body, {"physical"})
        expected = np.array(body["mesh"]["vertices"]) * .001 + [.1, -.02, .035]
        np.testing.assert_allclose(world["vertices"], expected, rtol=0, atol=1e-16)
        np.testing.assert_array_equal(matrix[:3, 3], [100, -20, 35])
        self.assertAlmostEqual(volume, 4e-9, delta=1e-22)
        self.assertEqual(world["units"], "m")
        self.assertEqual(body, before)

    def test_rotated_mm_geometry_and_jacobian(self):
        body = body_from_mesh([[0., 0., 0.], [2., 0., 0.], [0., 3., 0.], [0., 0., 4.]], [[0, 1, 2, 3]])
        for angle in (math.pi / 2, .37):
            with self.subTest(angle=angle):
                rotation = np.array([[math.cos(angle), -math.sin(angle), 0],
                                     [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
                assembly, occurrence = assembly_at(rotation, (100, -20, 35))
                validate_frames(assembly)
                world, matrix, volume = lower_body(assembly, occurrence, body, {"physical"})
                expected = np.array(body["mesh"]["vertices"]) @ rotation.T * .001 + [.1, -.02, .035]
                np.testing.assert_allclose(world["vertices"], expected, rtol=0, atol=1e-16)
                np.testing.assert_allclose(matrix[:3, :3], rotation, atol=1e-16)
                self.assertAlmostEqual(volume, 4e-9, delta=1e-22)
                p = np.array(world["vertices"])
                np.testing.assert_allclose((p[1:] - p[0]).T, rotation @ np.diag([.002, .003, .004]), atol=1e-16)

    def test_local_m_and_mm_are_equivalent(self):
        body = body_from_mesh([[0., 0., 0.], [2., 0., 0.], [0., 3., 0.], [0., 0., 4.]], [[0, 1, 2, 3]])
        metres = copy.deepcopy(body)
        metres["mesh"]["units"] = "m"
        metres["mesh"]["vertices"] = [[x * .001 for x in p] for p in body["mesh"]["vertices"]]
        assembly, occurrence = assembly_at(translation_mm=(7, 11, -3))
        a, _, va = lower_body(assembly, occurrence, body, {"physical"})
        b, _, vb = lower_body(assembly, occurrence, metres, {"physical"})
        np.testing.assert_array_equal(a["vertices"], b["vertices"])
        self.assertEqual(va, vb)

    def test_individual_cell_rounding_not_hidden_by_total_volume(self):
        body = near_face_cube()
        assembly, occurrence = assembly_at(translation_mm=(999999000, 0, 0))
        validate_frames(assembly)
        represented = copy.deepcopy(body["mesh"])
        represented["vertices"] = (np.array(represented["vertices"]) + [999999., 0., 0.]).tolist()
        original, moved = cell_volumes(body["mesh"]), cell_volumes(represented)
        self.assertAlmostEqual(float(moved.sum() / original.sum()), 1, delta=1e-12)
        self.assertGreater(float(np.max(np.abs(moved / original - 1))), 1e-6)
        with self.assertRaisesRegex(ValueError, "ASSEMBLY_FIELD_FRAME"):
            lower_body(assembly, occurrence, body, {"physical"})

    def test_scale_shear_and_reflection_rejected(self):
        for rotation in (np.diag([2., 1., 1.]), np.diag([-1., 1., 1.]),
                         np.array([[1., .01, 0], [0, 1, 0], [0, 0, 1]])):
            assembly, _ = assembly_at(rotation)
            with self.assertRaises(ValueError):
                validate_frames(assembly)


if __name__ == "__main__":
    unittest.main()
