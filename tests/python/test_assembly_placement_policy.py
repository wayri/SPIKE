"""Typed, topology-free AssemblyIR placement-policy regressions."""

from __future__ import annotations

import math
import unittest

from python.spike_core.assembly_frames import enforce_placement_policy
from python.spike_core.assembly_placement_policy import AssemblyPlacementPolicy
from python.spike_core.design_ir_v2 import AssemblyIRV1


IDENTITY = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def transform(*, x: float = 0, y: float = 0, z: float = 0, rz_deg: float = 0) -> tuple[float, ...]:
    angle = math.radians(rz_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    return (cosine, -sine, 0, x, sine, cosine, 0, y, 0, 0, 1, z, 0, 0, 0, 1)


class AssemblyPlacementPolicyTests(unittest.TestCase):
    def test_strict_contract_accepts_free_and_bounded_policies(self) -> None:
        free = AssemblyPlacementPolicy.from_dict({
            "contract": "spike/assembly-placement-policy/v1",
            "translation_snap_mm": None,
            "rotation_snap_deg": None,
        })
        bounded = AssemblyPlacementPolicy.from_dict({
            "contract": "spike/assembly-placement-policy/v1",
            "translation_snap_mm": 0.25,
            "rotation_snap_deg": 15,
        })
        self.assertIsNone(free.translation_snap_mm)
        self.assertEqual(bounded.translation_snap_mm, 0.25)
        self.assertEqual(bounded.rotation_snap_deg, 15.0)

    def test_contract_rejects_missing_unknown_and_invalid_values(self) -> None:
        valid = {
            "contract": "spike/assembly-placement-policy/v1",
            "translation_snap_mm": 1,
            "rotation_snap_deg": 15,
        }
        for invalid in (
            {key: value for key, value in valid.items() if key != "contract"},
            {**valid, "future": True},
            {**valid, "translation_snap_mm": 0},
            {**valid, "translation_snap_mm": float("inf")},
            {**valid, "rotation_snap_deg": 181},
            {**valid, "rotation_snap_deg": -1},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                AssemblyPlacementPolicy.from_dict(invalid)

    def test_parent_local_translation_and_rotation_deltas_are_enforced(self) -> None:
        policy = AssemblyPlacementPolicy(translation_snap_mm=1, rotation_snap_deg=15)
        enforce_placement_policy(IDENTITY, transform(x=2, y=-3, z=1, rz_deg=30), policy)
        with self.assertRaisesRegex(ValueError, "translation increment"):
            enforce_placement_policy(IDENTITY, transform(x=2.25), policy)
        with self.assertRaisesRegex(ValueError, "rotation increment"):
            enforce_placement_policy(IDENTITY, transform(rz_deg=20), policy)

    def test_policy_round_trip_rejects_a_non_rigid_reference_frame(self) -> None:
        raw = {
            "assembly_id": "assembly", "name": "Policy fixture", "boards": [],
            "parts": [{
                "id": "part", "part_type": "mechanical", "model_id": "model",
                "frame": {"frame_id": "part-frame", "parent_frame_id": "assembly"},
                "placement_policy": {
                    "contract": "spike/assembly-placement-policy/v1",
                    "translation_snap_mm": 1,
                    "rotation_snap_deg": 15,
                },
            }],
        }
        assembly = AssemblyIRV1.from_dict(raw)
        self.assertEqual(assembly.to_dict()["parts"][0]["placement_policy"]["translation_snap_mm"], 1.0)
        raw["parts"][0]["frame"]["transform"] = [2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        with self.assertRaisesRegex(ValueError, "scale and shear"):
            AssemblyIRV1.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
