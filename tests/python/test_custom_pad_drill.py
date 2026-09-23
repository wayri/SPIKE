"""Synthetic regression coverage for the admitted drilled custom-pad subset.

These boards are purpose-built test inputs; this module makes no claim about
supporting any bundled or third-party board fixture.
"""

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


_SQUARE = ((-2.0, -1.5), (2.0, -1.5), (2.0, 1.5), (-2.0, 1.5))


def _points(points: tuple[tuple[float, float], ...]) -> str:
    return " ".join(f"(xy {x} {y})" for x, y in points)


def _inside_circle(point: tuple[float, float], diameter: float, tolerance: float = 1e-8) -> bool:
    return point[0] ** 2 + point[1] ** 2 < (diameter / 2 - tolerance) ** 2


def _inside_oval(point: tuple[float, float], width: float, height: float, tolerance: float = 1e-8) -> bool:
    radius = min(width, height) / 2
    half_straight = abs(width - height) / 2
    if width >= height:
        distance = max(abs(point[0]) - half_straight, 0.0)
        return distance ** 2 + point[1] ** 2 < (radius - tolerance) ** 2
    distance = max(abs(point[1]) - half_straight, 0.0)
    return point[0] ** 2 + distance ** 2 < (radius - tolerance) ** 2


class CustomPadDrillTests(unittest.TestCase):
    def write_board(
        self,
        *,
        pad_type: str = "thru_hole",
        drill: str = "(drill 0.8)",
        size: tuple[float, float] = (4.0, 3.0),
        points: tuple[tuple[float, float], ...] = _SQUARE,
        layers: str = '"*.Cu"',
    ) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "synthetic-custom-pad-drill.kicad_pcb"
        path.write_text(
            f'''(kicad_pcb
              (version 20260101)
              (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
              (net 1 "VCC")
              (footprint "Fixture:CustomDrill" (layer "F.Cu")
                (property "Reference" "TP1")
                (pad "1" {pad_type} custom (at 10 20) (size {size[0]} {size[1]}) {drill}
                  (layers {layers}) (net 1 "VCC") (uuid "synthetic-custom-drilled-pad")
                  (options (clearance outline) (anchor rect))
                  (primitives
                    (gr_poly (pts {_points(points)}) (width 0) (fill yes)))))
            )''',
            encoding="utf-8",
        )
        return path

    def imported_pad(self, **kwargs: object) -> dict:
        return import_kicad_design(str(self.write_board(**kwargs))).pads[0]

    @staticmethod
    def design_for(pad: dict) -> DesignIR:
        return DesignIR(
            layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
            stackup=[
                {"name": "F.Cu", "type": "copper", "thickness": 0.035},
                {"name": "dielectric 1", "type": "core", "thickness": 1.0},
                {"name": "B.Cu", "type": "copper", "thickness": 0.035},
            ],
            nets=[{"id": 1, "name": "VCC"}],
            pads=[pad],
        )

    def test_parser_design_ir_and_schema_round_trip_centered_circle_drill(self) -> None:
        board = self.write_board(drill="(drill 0.8)")
        parsed = KicadParser(board).pads[0]
        self.assertEqual(parsed["custom_geometry"]["status"], "supported")
        self.assertEqual(parsed["drill_shape"], "circle")
        self.assertEqual(parsed["drill_size"], (0.8, 0.8))

        imported = import_kicad_design(str(board))
        typed = DesignIRV2.from_v1(imported)
        restored = DesignIRV2.from_dict(typed.to_dict())
        self.assertEqual(restored.pads[0].drill_shape, "circle")
        self.assertEqual(restored.pads[0].drill_size_mm, (0.8, 0.8))
        self.assertTrue(restored.pads[0].plated)
        self.assertEqual(restored.to_v1().pads[0]["custom_geometry"], parsed["custom_geometry"])

        root = Path(__file__).resolve().parents[2]
        v1_schema = json.loads((root / "schemas" / "design-ir-v1.schema.json").read_text(encoding="utf-8"))
        v2_schema = json.loads((root / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(v1_schema["$id"], Resource.from_contents(v1_schema))
        Draft202012Validator(v2_schema, registry=registry).validate(
            json.loads(json.dumps(restored.to_dict()))
        )

    def test_circle_and_oval_drills_subtract_from_synthetic_custom_pad_surface(self) -> None:
        for drill, shape, dimensions in (
            ("(drill 0.8)", "circle", (0.8, 0.8)),
            ("(drill oval 1.4 0.6)", "oval", (1.4, 0.6)),
        ):
            with self.subTest(shape=shape):
                pad = self.imported_pad(drill=drill)
                mesh = build_hybrid_mesh(
                    self.design_for(pad),
                    AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 0.2}),
                )
                cells = [
                    cell for cell in mesh.cells
                    if cell["source_id"] == pad["id"] and cell["source_kind"] == "pad"
                ]
                resolved = pad["custom_geometry"]["positive_filled_polygon"]

                self.assertGreater(len(cells), 0)
                self.assertFalse([cell for cell in cells if cell.get("source_kind") == "analytic_void"])
                self.assertTrue(all(
                    _polygon_is_contained_in(
                        [(float(x) - 10.0, float(y) - 20.0) for x, y, _z in cell["vertices_mm"]],
                        resolved,
                        1e-6,
                    )
                    for cell in cells
                ))
                hole = _inside_circle if shape == "circle" else _inside_oval
                self.assertTrue(all(
                    not hole((float(x) - 10.0, float(y) - 20.0), *dimensions)
                    for cell in cells for x, y, _z in cell["vertices_mm"]
                ))

    def test_multilayer_plated_custom_pad_generates_owned_barrel_volume(self) -> None:
        pad = self.imported_pad(drill="(drill oval 1.4 0.6)")
        design = self.design_for(pad)
        preview = build_mesh(
            design,
            AnalysisSpec(
                mode="dc", net_names=["VCC"],
                mesh={"dimension": VOLUME_3D, "target_size_mm": 0.2, "max_preview_cells": 10000},
            ),
        )
        barrels = [cell for cell in preview["cells"] if cell["source_kind"] == "pad_barrel"]

        self.assertGreater(len(barrels), 0)
        self.assertTrue(all(cell["topology"] == "hex8_barrel" for cell in barrels))
        audit = audit_dc_conductor_volume_ownership(design, preview["cells"])
        self.assertEqual(audit["status"], "passed")
        self.assertEqual(audit["by_source_kind"]["pad_barrel"], len(barrels))

    def test_parser_rejects_offset_smd_npth_and_anchor_sized_custom_drills(self) -> None:
        cases = (
            ("offset", {"drill": "(drill 0.8 (offset 0.1 0))"}, "offset_custom_drill"),
            ("smd", {"pad_type": "smd", "drill": "(drill 0.8)", "layers": '\"F.Cu\"'}, "custom_drill_requires_plated_through_hole"),
            ("npth", {"pad_type": "np_thru_hole", "drill": "(drill 0.8)"}, "custom_drill_requires_plated_through_hole"),
            ("anchor", {"drill": "(drill oval 4.0 0.6)"}, "custom_drill_not_within_anchor"),
        )
        for name, kwargs, reason in cases:
            with self.subTest(name=name):
                pad = KicadParser(self.write_board(**kwargs)).pads[0]
                self.assertEqual(pad["custom_geometry"], {"status": "unsupported", "reason": reason})

    def test_drill_plating_envelope_crossing_resolved_source_boundary_is_solver_blocked(self) -> None:
        # The 1.98 mm circle fits the 2 x 2 mm anchor, but its plated envelope
        # crosses the resolved anchor/polygon boundary.
        pad = self.imported_pad(
            drill="(drill 1.98)",
            size=(2.0, 2.0),
            points=((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)),
        )
        self.assertEqual(pad["custom_geometry"]["status"], "supported")
        mesh = build_hybrid_mesh(
            self.design_for(pad),
            AnalysisSpec(mode="dc", net_names=["VCC"], mesh={"target_size_mm": 0.2}),
        )

        self.assertEqual(
            len([cell for cell in mesh.cells if cell["source_id"] == pad["id"]]),
            0,
        )
        self.assertTrue(any(
            issue.code == "SPIKE-BE-MESH-E-0016" and issue.status == "unsupported"
            for issue in mesh.issues
        ))


if __name__ == "__main__":
    unittest.main()
