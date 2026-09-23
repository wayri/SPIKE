"""Regression coverage for composite filled custom-pad primitives."""

from __future__ import annotations

from itertools import permutations
import json
from pathlib import Path
import tempfile
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from python.core.board_parser import KicadParser
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.hybrid_mesh import build_hybrid_mesh
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.mesh_ownership import audit_dc_conductor_volume_ownership
from python.spike_core.meshing import VOLUME_3D, build_mesh


_UPPER_CIRCLE = """(gr_circle
  (center 0 0.25) (end 0.5 0.25) (width 0) (fill yes))"""
_LOWER_CIRCLE = """(gr_circle
  (center 0 -0.25) (end 0.5 -0.25) (width 0) (fill yes))"""
_RIGHT_POLYGON = """(gr_poly
  (pts (xy 0.5 0.75) (xy 0 0.75) (xy 0 -0.75) (xy 0.5 -0.75))
  (width 0) (fill yes))"""


class CompositeCustomPadUnionTests(unittest.TestCase):
    def write(self, primitives: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.kicad_pcb"
        path.write_text(f"""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (footprint "Fixture:Composite" (layer "F.Cu")
            (property "Reference" "JP1")
            (pad "1" smd custom (at 0 0) (size 1 0.5) (layers "F.Cu") (net 1 "VCC")
              (uuid "composite-pad")
              (options (clearance outline) (anchor rect))
              (primitives {primitives})))
        )""", encoding="utf-8")
        return path

    def parse_geometry(self, primitives: str) -> dict:
        return KicadParser(self.write(primitives)).pads[0]["custom_geometry"]

    def test_anchor_two_filled_circles_and_polygon_union_deterministically(self):
        primitives = (_UPPER_CIRCLE, _LOWER_CIRCLE, _RIGHT_POLYGON)
        geometries = [
            self.parse_geometry("\n".join(order))
            for order in permutations(primitives)
        ]

        self.assertTrue(all(geometry["status"] == "supported" for geometry in geometries))
        self.assertTrue(all(geometry == geometries[0] for geometry in geometries[1:]))
        boundary = geometries[0]["positive_filled_polygon"]
        self.assertGreaterEqual(len(boundary), 8)
        self.assertEqual(min(point[0] for point in boundary), -0.5)
        self.assertEqual(max(point[0] for point in boundary), 0.5)
        self.assertEqual(min(point[1] for point in boundary), -0.75)
        self.assertEqual(max(point[1] for point in boundary), 0.75)

    def test_disjoint_composite_primitive_fails_closed(self):
        disjoint_polygon = """(gr_poly
          (pts (xy 3 0) (xy 4 0) (xy 4 1) (xy 3 1))
          (width 0) (fill yes))"""
        geometry = self.parse_geometry("\n".join((_UPPER_CIRCLE, _LOWER_CIRCLE, disjoint_polygon)))
        self.assertEqual(geometry["status"], "unsupported")
        self.assertNotIn("positive_filled_polygon", geometry)

    def test_ebrake_jumper_custom_pads_are_admitted_as_composite_boundaries(self):
        board = Path(__file__).parents[2] / "app" / "public" / "demo" / "ebrake1.kicad_pcb"
        parser = KicadParser(board)
        jumpers = [
            pad for pad in parser.pads
            if pad.get("shape") == "custom" and str(pad.get("component", "")).startswith("JP")
        ]

        self.assertEqual(len(jumpers), 12)
        self.assertTrue(all(pad["custom_geometry"]["status"] == "supported" for pad in jumpers))
        self.assertTrue(all(
            len(pad["custom_geometry"]["positive_filled_polygon"]) >= 8
            for pad in jumpers
        ))

    def test_composite_curve_evidence_round_trips_and_mesh_is_owned(self):
        path = self.write("\n".join((_UPPER_CIRCLE, _LOWER_CIRCLE, _RIGHT_POLYGON)))
        imported = import_kicad_design(str(path))
        typed = DesignIRV2.from_v1(imported)
        restored = DesignIRV2.from_dict(typed.to_dict())
        geometry = restored.pads[0].custom_geometry
        self.assertEqual(geometry["curve_approximation"]["source_circle_count"], 2)
        self.assertLessEqual(geometry["curve_approximation"]["maximum_sagitta_mm"], 0.001)
        schema = json.loads(
            (Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8")
        )
        v1_schema = json.loads(
            (Path(__file__).parents[2] / "schemas" / "design-ir-v1.schema.json").read_text(encoding="utf-8")
        )
        registry = Registry().with_resource(v1_schema["$id"], Resource.from_contents(v1_schema))
        Draft202012Validator(schema, registry=registry).validate(
            json.loads(json.dumps(restored.to_dict()))
        )

        pad = restored.to_v1().pads[0]
        design = DesignIR(
            layers=[{"name": "F.Cu"}], nets=[{"id": 1, "name": "VCC"}], pads=[pad],
        )
        spec = AnalysisSpec(
            mode="dc", net_names=["VCC"],
            mesh={"dimension": VOLUME_3D, "target_size_mm": 0.1, "max_preview_cells": 10000},
        )
        hybrid = build_hybrid_mesh(design, spec)
        self.assertFalse([issue for issue in hybrid.issues if issue.severity == "error"])
        preview = build_mesh(design, spec)
        volumes = [cell for cell in preview["cells"] if cell["source_id"] == pad["id"]]
        self.assertGreater(len(volumes), 0)
        self.assertEqual(
            audit_dc_conductor_volume_ownership(design, volumes)["checked_volumes"],
            len(volumes),
        )


if __name__ == "__main__":
    unittest.main()
