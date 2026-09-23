"""Regression coverage for conservative stroked custom-pad polygons."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from python.core.board_parser import KicadParser
from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.hybrid_mesh import _polygon_is_contained_in, build_hybrid_mesh
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.mesh_ownership import audit_dc_conductor_volume_ownership
from python.spike_core.meshing import VOLUME_3D, build_mesh


_SQUARE = ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))


def _points(points: tuple[tuple[float, float], ...]) -> str:
    return " ".join(f"(xy {x} {y})" for x, y in points)


class CustomPadStrokeTests(unittest.TestCase):
    def write_board(
        self,
        points: tuple[tuple[float, float], ...] = _SQUARE,
        *,
        width: str = "0.2",
        fill: str = "yes",
        drill: str = "",
        anchor: str = "rect",
        extra_primitives: str = "",
    ) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "stroke-fixture.kicad_pcb"
        path.write_text(
            f'''(kicad_pcb
              (version 20260101)
              (layers (0 "F.Cu" signal))
              (net 1 "VCC")
              (footprint "Fixture:Stroke" (layer "F.Cu")
                (property "Reference" "TP1")
                (pad "1" smd custom (at 0 0) (size 1 1) {drill}
                  (layers "F.Cu") (net 1 "VCC") (uuid "stroke-pad")
                  (options (clearance outline) (anchor {anchor}))
                  (primitives
                    (gr_poly (pts {_points(points)}) (width {width}) (fill {fill}))
                    {extra_primitives})))
            )''',
            encoding="utf-8",
        )
        return path

    def geometry(self, **kwargs: object) -> dict:
        return KicadParser(self.write_board(**kwargs)).pads[0]["custom_geometry"]

    def test_width_changes_resolved_boundary_and_persists_stroke_evidence(self) -> None:
        narrow = self.geometry(width="0.1")
        wide = self.geometry(width="0.4")

        self.assertEqual(narrow["status"], "supported")
        self.assertEqual(wide["status"], "supported")
        narrow_extent = max(abs(value) for point in narrow["positive_filled_polygon"] for value in point)
        wide_extent = max(abs(value) for point in wide["positive_filled_polygon"] for value in point)
        self.assertGreater(wide_extent, narrow_extent)
        evidence = wide["stroke_approximation"]
        self.assertEqual(evidence["method"], "inscribed_round_offset_v1")
        self.assertEqual(evidence["source_width_mm"], 0.4)
        self.assertLessEqual(evidence["maximum_radial_error_mm"], 0.001)
        self.assertEqual(evidence["quantization_grid_mm"], 1e-8)
        self.assertTrue(evidence["round_join"])
        self.assertTrue(evidence["closed_path_no_caps"])
        self.assertTrue(evidence["conservative_source_containment"])

    def test_winding_and_explicit_duplicate_closure_are_deterministic(self) -> None:
        clockwise = self.geometry(points=_SQUARE)
        counterclockwise = self.geometry(points=tuple(reversed(_SQUARE)))
        explicitly_closed = self.geometry(points=(*_SQUARE, _SQUARE[0]))

        self.assertEqual(clockwise, counterclockwise)
        self.assertEqual(clockwise, explicitly_closed)

    def test_ambiguous_stroked_custom_primitives_fail_closed(self) -> None:
        malformed = self.geometry(points=((0, 0), (1, 1), (0, 1), (1, 0)))
        unfilled = self.geometry(fill="no")
        drilled = self.geometry(drill="(drill 0.2)")
        anchor_outside = self.geometry(points=((2, 2), (3, 2), (3, 3), (2, 3)))
        mixed = self.geometry(extra_primitives=(
            "(gr_circle (center 0 0) (end 0.1 0) (width 0) (fill yes))"
        ))

        for geometry in (malformed, unfilled, drilled, anchor_outside, mixed):
            self.assertEqual(geometry["status"], "unsupported")
            self.assertIsInstance(geometry.get("reason"), str)
            self.assertNotIn("positive_filled_polygon", geometry)
        self.assertEqual(anchor_outside["reason"], "stroke_anchor_not_contained")
        self.assertEqual(mixed["reason"], "stroked_polygon_mixed_primitives")

    def test_schema_and_design_ir_roundtrip_preserve_stroke_evidence(self) -> None:
        imported = import_kicad_design(str(self.write_board(width="0.3")))
        typed = DesignIRV2.from_v1(imported)
        restored = DesignIRV2.from_dict(typed.to_dict())
        self.assertEqual(
            restored.pads[0].custom_geometry["stroke_approximation"],
            imported.pads[0]["custom_geometry"]["stroke_approximation"],
        )

        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8"))
        v1_schema = json.loads((root / "schemas" / "design-ir-v1.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(v1_schema["$id"], Resource.from_contents(v1_schema))
        Draft202012Validator(schema, registry=registry).validate(
            json.loads(json.dumps(restored.to_dict()))
        )

    def test_hybrid_and_volume_mesh_use_the_resolved_stroked_boundary(self) -> None:
        imported = import_kicad_design(str(self.write_board(width="0.2")))
        pad = imported.pads[0]
        design = DesignIR(
            layers=[{"name": "F.Cu"}], nets=[{"id": 1, "name": "VCC"}], pads=[pad],
        )
        hybrid = build_hybrid_mesh(
            design,
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 0.1}),
        )
        hybrid_cells = [cell for cell in hybrid.cells if cell["source_id"] == pad["id"]]
        resolved = pad["custom_geometry"]["positive_filled_polygon"]
        self.assertGreater(len(hybrid_cells), 0)
        self.assertTrue(all(
            _polygon_is_contained_in(
                [(float(x), float(y)) for x, y, _z in cell["vertices_mm"]], resolved, 1e-6,
            )
            for cell in hybrid_cells
        ))
        self.assertGreater(
            max(abs(point[axis]) for cell in hybrid_cells for point in cell["vertices_mm"] for axis in (0, 1)),
            0.5,
        )

        preview = build_mesh(
            design,
            AnalysisSpec(
                mode="dc", net_names=["VCC"],
                mesh={"dimension": VOLUME_3D, "target_size_mm": 0.1, "max_preview_cells": 10_000},
            ),
        )
        volumes = [cell for cell in preview["cells"] if cell["source_id"] == pad["id"]]
        self.assertGreater(len(volumes), 0)
        self.assertEqual(
            audit_dc_conductor_volume_ownership(design, volumes)["checked_volumes"], len(volumes),
        )

    def test_ebrake_custom_pads_are_all_supported_with_expected_stroke_evidence(self) -> None:
        board = Path(__file__).resolve().parents[2] / "app" / "public" / "demo" / "ebrake1.kicad_pcb"
        custom_pads = [pad for pad in KicadParser(board).pads if pad.get("shape") == "custom"]

        self.assertEqual(len(custom_pads), 52)
        self.assertTrue(all(pad["custom_geometry"]["status"] == "supported" for pad in custom_pads))
        self.assertEqual(sum(
            "stroke_approximation" in pad["custom_geometry"] for pad in custom_pads
        ), 40)


if __name__ == "__main__":
    unittest.main()
