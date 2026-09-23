"""Deterministic exact-selector geometric placement regressions."""

from __future__ import annotations

import unittest

from python.spike_core.assembly_geometric_constraints import (
    AssemblyGeometricConstraintError,
    apply_single_geometric_constraint,
)
from python.spike_core.design_ir_v2 import AssemblyIRV1


def _geometry(representation, origin, direction=None):
    return {
        "contract": "spike/package-shape-selector-geometry/v1", "coordinate_space": "shape_local_mm",
        "representation": representation, "origin_mm": origin, "direction": direction, "radius_mm": None,
    }


def _case(kind, representation, origin_a, origin_b, direction_a=None, direction_b=None, value=None):
    assembly = AssemblyIRV1.from_dict({
        "assembly_id": "snap", "name": "Snap", "boards": [],
        "parts": [
            {"id": "a", "part_type": "mechanical", "model_id": "ma", "frame": {"frame_id": "fa", "parent_frame_id": "assembly"}},
            {"id": "b", "part_type": "mechanical", "model_id": "mb", "frame": {"frame_id": "fb", "parent_frame_id": "assembly"}},
        ],
    })
    topology_kind = {"point": "vertex", "line": "edge", "plane": "face", "axis": "axis"}[representation]
    entities = [
        {"topology_id": "ta", "kind": topology_kind, "geometry": _geometry(representation, origin_a, direction_a)},
        {"topology_id": "tb", "kind": topology_kind, "geometry": _geometry(representation, origin_b, direction_b)},
    ]
    shapes = [
        {"shape_id": "sa", "part_id": "a", "source_model_id": "ma", "entities": [entities[0]]},
        {"shape_id": "sb", "part_id": "b", "source_model_id": "mb", "entities": [entities[1]]},
    ]
    refs = [
        {"part_id": "a", "shape_id": "sa", "topology_id": "ta", "topology_kind": topology_kind},
        {"part_id": "b", "shape_id": "sb", "topology_id": "tb", "topology_kind": topology_kind},
    ]
    constraint = {"constraint_id": "c", "kind": kind, "references": refs, "value_mm": value if kind == "distance" else None, "value_deg": value if kind == "angle" else None}
    models = {"models": [{"id": "ma", "transform": []}, {"id": "mb", "transform": []}]}
    return assembly, models, {"shapes": shapes, "constraints": [constraint]}


class AssemblyGeometricConstraintTests(unittest.TestCase):
    def _apply(self, *args):
        assembly, models, index = _case(*args)
        result = apply_single_geometric_constraint(assembly, models, index, "c", "b")
        part = next(item for item in assembly.parts if item.id == "b")
        self.assertLessEqual(result["residual"]["position_mm"], result["residual"]["position_tolerance_mm"])
        self.assertLessEqual(result["residual"]["angle_deg"], result["residual"]["angle_tolerance_deg"])
        return tuple(part.frame.transform)

    def test_point_coincidence_and_distance(self):
        coincident = self._apply("coincident", "point", [0, 0, 0], [10, 0, 0])
        self.assertAlmostEqual(coincident[3], -10.0)
        distance = self._apply("distance", "point", [0, 0, 0], [10, 0, 0], None, None, 3.0)
        self.assertAlmostEqual(distance[3], -7.0)

    def test_axis_concentric_edge_face_and_angle(self):
        concentric = self._apply("concentric", "axis", [0, 0, 0], [10, 0, 0], [0, 0, 1], [0, 0, 1])
        self.assertAlmostEqual(concentric[3], -10.0)
        edge = self._apply("edge", "line", [0, 0, 0], [0, 5, 0], [1, 0, 0], [1, 0, 0])
        self.assertAlmostEqual(edge[7], -5.0)
        face = self._apply("face", "plane", [0, 0, 0], [0, 0, 5], [0, 0, 1], [0, 0, 1])
        self.assertAlmostEqual(face[11], -5.0)
        axis = self._apply("axis", "axis", [0, 0, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0])
        self.assertAlmostEqual(axis[8], 1.0)
        angle = self._apply("angle", "axis", [0, 0, 0], [0, 0, 0], [0, 0, 1], [1, 0, 0], 0.0)
        self.assertAlmostEqual(angle[8], 1.0)

    def test_missing_descriptor_and_same_part_fail_without_mutation(self):
        assembly, models, index = _case("coincident", "point", [0, 0, 0], [1, 0, 0])
        before = tuple(assembly.parts[1].frame.transform)
        del index["shapes"][1]["entities"][0]["geometry"]
        with self.assertRaisesRegex(AssemblyGeometricConstraintError, "re-extraction"):
            apply_single_geometric_constraint(assembly, models, index, "c", "b")
        self.assertEqual(tuple(assembly.parts[1].frame.transform), before)
        index["constraints"][0]["references"][0]["part_id"] = "b"
        with self.assertRaisesRegex(AssemblyGeometricConstraintError, "distinct anchor"):
            apply_single_geometric_constraint(assembly, models, index, "c", "b")


if __name__ == "__main__":
    unittest.main()
