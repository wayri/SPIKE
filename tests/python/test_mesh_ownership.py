"""Regression tests for fail-closed conductor-volume ownership."""

from __future__ import annotations

import copy
import unittest

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.mesh_ownership import audit_dc_conductor_volume_ownership
from python.spike_core.meshing import VOLUME_3D, build_mesh


def _volume_fixture() -> tuple[DesignIR, list[dict]]:
    design = DesignIR(
        design_id="ownership-fixture",
        layers=[{"name": "F.Cu", "type": "copper"}, {"name": "B.Cu", "type": "copper"}],
        stackup=[
            {"name": "F.Cu", "type": "copper", "thickness": 0.035},
            {"name": "dielectric 1", "type": "core", "thickness": 1.0},
            {"name": "B.Cu", "type": "copper", "thickness": 0.035},
        ],
        tracks=[{
            "id": "track-actual", "start": [0.0, 0.0], "end": [5.0, 0.0],
            "width": 0.5, "layer": "F.Cu", "net_name": "VCC",
        }],
        zones=[{
            "id": "zone-actual", "points": [[6.0, -1.0], [10.0, -1.0], [10.0, 1.0], [6.0, 1.0]],
            "layer": "F.Cu", "net_name": "VCC",
        }],
        pads=[{
            "id": "pad-actual", "at": [12.0, 0.0], "size": [2.0, 2.0],
            "shape": "circle", "drill": 0.8, "drill_size": [0.8, 0.8],
            "plating_thickness_mm": 0.025,
            "layers": ["F.Cu", "B.Cu"], "net_name": "VCC",
        }],
        vias=[{
            "id": "via-actual", "at": [14.0, 0.0], "drill": 0.3,
            "plating_thickness_mm": 0.025, "layers": ["F.Cu", "B.Cu"], "net_name": "VCC",
        }],
    )
    spec = AnalysisSpec(
        mode="dc", net_names=["VCC"],
        mesh={"dimension": VOLUME_3D, "target_size_mm": 0.25, "max_preview_cells": 10000},
    )
    return design, build_mesh(design, spec)["cells"]


class MeshOwnershipTests(unittest.TestCase):
    def test_track_zone_circle_pad_and_via_volumes_pass(self) -> None:
        design, volumes = _volume_fixture()
        audit = audit_dc_conductor_volume_ownership(design, volumes)

        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["checked_volumes"], len(volumes))
        self.assertEqual(set(audit["by_source_kind"]), {"track", "zone", "pad", "pad_barrel", "via"})

    def test_out_of_owner_vertex_is_rejected(self) -> None:
        design, volumes = _volume_fixture()
        escaped = copy.deepcopy(volumes)
        track = next(cell for cell in escaped if cell["source_kind"] == "track")
        track["vertices_mm"][0][1] += 10.0

        with self.assertRaisesRegex(ValueError, "SPIKE-BE-MESH-E-0001.*escapes track"):
            audit_dc_conductor_volume_ownership(design, escaped)

    def test_net_layer_and_unknown_source_mismatches_are_rejected(self) -> None:
        design, volumes = _volume_fixture()
        wrong_net = copy.deepcopy(volumes)
        wrong_net[0]["net"] = "OTHER"
        with self.assertRaisesRegex(ValueError, "SPIKE-BE-MESH-E-0001.*net does not match"):
            audit_dc_conductor_volume_ownership(design, wrong_net)

        unknown = copy.deepcopy(volumes)
        unknown[0]["source_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "SPIKE-BE-MESH-E-0001.*references unknown"):
            audit_dc_conductor_volume_ownership(design, unknown)

    def test_pad_face_crossing_drill_void_is_rejected(self) -> None:
        design, volumes = _volume_fixture()
        escaped = copy.deepcopy(volumes)
        pad = next(cell for cell in escaped if cell["source_kind"] == "pad")
        half = len(pad["vertices_mm"]) // 2
        for index in (0, half):
            pad["vertices_mm"][index][0] = 12.0
            pad["vertices_mm"][index][1] = 0.0

        with self.assertRaisesRegex(ValueError, "SPIKE-BE-MESH-E-0001.*escapes pad"):
            audit_dc_conductor_volume_ownership(design, escaped)

    def test_face_crossing_capsule_slot_is_rejected(self) -> None:
        design, _ = _volume_fixture()
        design.pads = [{
            "id": "slot-pad", "at": [0.0, 0.0], "size": [4.0, 2.0],
            "shape": "oval", "drill_size": [1.6, 0.8], "drill_shape": "oval",
            "layers": ["F.Cu"], "net_name": "VCC",
        }]
        design.tracks = []
        design.zones = []
        design.vias = []
        volume = {
            "id": "slot-crossing", "source_kind": "pad", "source_id": "slot-pad",
            "layer": "F.Cu", "net": "VCC",
            "vertices_mm": [
                [-0.3, 0.35, 0.0], [0.3, 0.35, 0.0], [0.3, 0.6, 0.0], [-0.3, 0.6, 0.0],
                [-0.3, 0.35, 0.035], [0.3, 0.35, 0.035], [0.3, 0.6, 0.035], [-0.3, 0.6, 0.035],
            ],
        }

        with self.assertRaisesRegex(ValueError, "SPIKE-BE-MESH-E-0001.*escapes pad"):
            audit_dc_conductor_volume_ownership(design, [volume])

    def test_pad_barrel_outside_plated_envelope_is_rejected(self) -> None:
        design, volumes = _volume_fixture()
        escaped = copy.deepcopy(volumes)
        barrel = next(cell for cell in escaped if cell["source_kind"] == "pad_barrel")
        barrel["vertices_mm"][0][0] += 0.5

        with self.assertRaisesRegex(ValueError, "SPIKE-BE-MESH-E-0001.*escapes pad_barrel"):
            audit_dc_conductor_volume_ownership(design, escaped)


if __name__ == "__main__":
    unittest.main()
