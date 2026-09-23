import math
import unittest

from python.spike_core.assembly_frames import reparent_part_preserving_world, resolve_world, validate_rigid_transform
from python.spike_core.design_ir_v2 import AssemblyIRV1
from python.spike_core.design_ir_v2_schema import CoordinateFrame


def transform(x, y, z, degrees=0):
    angle = math.radians(degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (
        cosine, -sine, 0, x,
        sine, cosine, 0, y,
        0, 0, 1, z,
        0, 0, 0, 1,
    )


def fixture():
    return AssemblyIRV1.from_dict({
        "contract": "spike/assembly-ir/v1", "assembly_id": "frames", "name": "Frames",
        "frame": {"frame_id": "assembly"}, "boards": [], "harnesses": [],
        "connector_mappings": [], "rigid_flex_links": [], "materials": [],
        "thermal_contacts": [], "electrical_bonds": [],
        "parts": [
            {"id": "parent-a", "name": "A", "frame": {"frame_id": "frame-a", "parent_frame_id": "assembly", "transform": transform(10, 2, 0, 30)}},
            {"id": "parent-b", "name": "B", "frame": {"frame_id": "frame-b", "parent_frame_id": "assembly", "transform": transform(-4, 8, 2, -25)}},
            {"id": "child", "name": "Child", "model_id": "model-child", "frame": {"frame_id": "child-frame", "parent_frame_id": "frame-a", "transform": transform(3, 1, 5, 12)}},
        ],
    })


class AssemblyFrameTests(unittest.TestCase):
    def test_reparent_preserves_world_transform(self):
        assembly = fixture()
        child = next(item for item in assembly.parts if item.id == "child")
        before = resolve_world(assembly, child.frame)
        old_parent, new_parent = reparent_part_preserving_world(assembly, "child", "frame-b")
        after = resolve_world(assembly, child.frame)
        self.assertEqual((old_parent, new_parent), ("frame-a", "frame-b"))
        self.assertEqual(child.frame.frame_id, "child-frame")
        for expected, actual in zip(before, after):
            self.assertAlmostEqual(expected, actual, places=10)

    def test_reparent_to_root_makes_local_equal_previous_world(self):
        assembly = fixture()
        child = next(item for item in assembly.parts if item.id == "child")
        before = resolve_world(assembly, child.frame)
        reparent_part_preserving_world(assembly, "child", "assembly")
        self.assertEqual(tuple(child.frame.transform), before)

    def test_descendant_and_singular_destinations_fail(self):
        assembly = fixture()
        parent = next(item for item in assembly.parts if item.id == "parent-a")
        with self.assertRaisesRegex(ValueError, "descendant"):
            reparent_part_preserving_world(assembly, parent.id, "child-frame")
        target = next(item for item in assembly.parts if item.id == "parent-b")
        target.frame = CoordinateFrame(frame_id="frame-b", parent_frame_id="assembly", transform=(
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
        ))
        with self.assertRaisesRegex(ValueError, "singular"):
            reparent_part_preserving_world(assembly, "child", "frame-b")

    def test_manifest_bound_placement_requires_proper_rigid_transform(self):
        self.assertEqual(validate_rigid_transform(transform(1, 2, 3, 25)), transform(1, 2, 3, 25))
        invalid = {
            "projective": (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.1, 0, 0, 1),
            "scale": (2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
            "shear": (1, 0.2, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
            "reflection": (-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        }
        for label, matrix in invalid.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_rigid_transform(matrix)


if __name__ == "__main__":
    unittest.main()
