import json
import tempfile
import unittest
from pathlib import Path

from python.spike_core.contracts import AnalysisSpec
from python.spike_core.solvers.geometry_meshing.preparation.geometry import extract_net_geometry
from python.spike_core.service import _design_from_kicad
from python.spike_core.solvers.geometry_meshing.preparation.solver_geometry import build_solver_geometry
from python.spike_core.spider_v2 import SpiDeRV2
from python.core.board_parser import KicadParser


RIGID_FLEX_BOARD = """(kicad_pcb
  (version 20240108)
  (generator pcbnew)
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "User.1" user "Flex Region")
    (37 "User.2" user "Bend R1.5 A90")
    (44 "Edge.Cuts" user)
  )
  (net 0 "")
  (net 1 "VCC")
  (gr_line (start 0 0) (end 10 0) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (stroke (width 0.05) (type default)) (layer "Edge.Cuts"))
  (gr_rect (start 0 0) (end 4 10) (stroke (width 0.05) (type default)) (fill none) (layer "User.1"))
  (gr_line (start 2 0) (end 2 10) (stroke (width 0.05) (type default)) (layer "User.2"))
  (segment (start 1 5) (end 9 5) (width 0.5) (layer "F.Cu") (net 1))
)"""


KIKAKUKA_BOARD = """(kicad_pcb
  (version 20250114)
  (generator pcbnew)
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "User.4" user "fReEkIcAd")
    (44 "Edge.Cuts" user)
  )
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "dielectric 1" (type "core") (thickness 0.13))
    (layer "B.Cu" (type "copper") (thickness 0.035))
  ))
  (net 0 "")
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
  (gr_line (start 3 0) (end 3 10) (layer "User.4") (uuid "bend-span"))
  (gr_text "s=0.942477796076938mm a=90" (at 3.1 0) (layer "User.4"))
  (gr_line (start 6 0) (end 6 10) (layer "User.4") (uuid "bend-radius"))
  (gr_text "s=4mm r=0.2cm a=-70deg" (at 6 0) (layer "User.4"))
  (gr_line (start 8 0) (end 8 10) (layer "User.4") (uuid "bend-unset"))
  (gr_line (start 8.5 0) (end 8.5 10) (layer "User.4") (uuid "bend-zero"))
  (gr_text "a=90 r=0" (at 8.5 0) (layer "User.4"))
  (gr_line (start 9 0) (end 9 10) (layer "User.4") (uuid "bend-bad"))
  (gr_text "a=oops r=bad" (at 9 0) (layer "User.4"))
  (gr_text "a=45" (at 9 0.01) (layer "User.4"))
  (gr_line (start 9.5 0) (end 9.5 10) (layer "User.4") (uuid "bend-negative"))
  (gr_text "a=90 r=-1mm" (at 9.5 0) (layer "User.4"))
)"""


KIKAKUKA_NUMERIC_EDGE_BOARD = """(kicad_pcb
  (version 20250114)
  (generator pcbnew)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "User.4" user "FreekiCAD") (44 "Edge.Cuts" user))
  (setup (stackup
    (layer "F.Cu" (type "copper") (thickness 0.035))
    (layer "dielectric 1" (type "core") (thickness 0.13))
    (layer "B.Cu" (type "copper") (thickness 0.035))))
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
  (gr_line (start 1 0) (end 1 10) (layer "User.4") (uuid "exact"))
  (gr_text "a=90 r=.5mm" (at 1.1 0) (layer "User.4"))
  (gr_line (start 2 0) (end 2 10) (layer "User.4") (uuid "outside"))
  (gr_text "a=90 r=.6mm" (at 2.10001 0) (layer "User.4"))
  (gr_line (start 3 0) (end 3 10) (layer "User.4") (uuid "zero-angle"))
  (gr_text "a=0 s=1mm" (at 3 0) (layer "User.4"))
  (gr_line (start 4 0) (end 4 10) (layer "User.4") (uuid "derived-overflow"))
  (gr_text "a=1e-9 s=1e308mm" (at 4 0) (layer "User.4"))
  (gr_line (start 5 0) (end 5 10) (layer "User.4") (uuid "literal-overflow"))
  (gr_text "a=90 r=1e999" (at 5 0) (layer "User.4"))
  (gr_line (start 6 0) (end 6 10) (layer "User.4") (uuid "unit-overflow"))
  (gr_text "a=90 r=1e308cm" (at 6 0) (layer "User.4"))
)"""


def kikakuka_span_board(stackup):
    return f"""(kicad_pcb
  (version 20250114)
  (generator pcbnew)
  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "User.4" user "FreekiCAD") (44 "Edge.Cuts" user))
  {stackup}
  (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts"))
  (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts"))
  (gr_line (start 10 10) (end 0 10) (layer "Edge.Cuts"))
  (gr_line (start 0 10) (end 0 0) (layer "Edge.Cuts"))
  (gr_line (start 5 0) (end 5 10) (layer "User.4"))
  (gr_text "a=90 s=1mm" (at 5 0) (layer "User.4")))"""


class RigidFlexImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.board_path = Path(self.temporary.name) / "rigid-flex.kicad_pcb"
        self.board_path.write_text(RIGID_FLEX_BOARD, encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_kicad_regions_and_bends_reach_design_ir(self):
        design = _design_from_kicad(str(self.board_path))

        self.assertEqual(design.technology, "rigid-flex")
        self.assertEqual(len(design.regions), 1)
        self.assertEqual(design.regions[0]["kind"], "flex")
        self.assertAlmostEqual(design.regions[0]["outline"][1][0], 4.0)
        self.assertEqual(len(design.bends), 1)
        self.assertAlmostEqual(design.bends[0]["radius_mm"], 1.5)
        self.assertAlmostEqual(design.bends[0]["angle_deg"], 90.0)

    def test_rigid_flex_metadata_survives_solver_exchange(self):
        design = _design_from_kicad(str(self.board_path))
        net_geometry = extract_net_geometry(design, "VCC")
        bundle = build_solver_geometry(
            design,
            AnalysisSpec(mode="dc", net_names=["VCC"]),
        )

        self.assertEqual(net_geometry["technology"], "rigid-flex")
        self.assertEqual(net_geometry["regions"], design.regions)
        self.assertEqual(net_geometry["bends"], design.bends)
        self.assertEqual(bundle["assembly"]["technology"], "rigid-flex")
        self.assertEqual(bundle["assembly"]["regions"], design.regions)
        self.assertEqual(bundle["counts"]["bends"], 1)

    def test_kikakuka_freekicad_bends_preserve_format_and_derive_span_radius(self):
        board_path = Path(self.temporary.name) / "kikakuka.kicad_pcb"
        board_path.write_text(KIKAKUKA_BOARD, encoding="utf-8")
        parser = KicadParser(board_path)

        self.assertEqual(parser.technology, "flex")
        self.assertEqual(len(parser.bends), 6)
        self.assertEqual(parser.regions[0]["source"], "implicit-board-outline")
        span, explicit, unset, zero, malformed, negative = parser.bends
        self.assertEqual(span["format"], "kikakuka/freekicad-v1")
        self.assertEqual(span["source_layer"], "User.4")
        self.assertEqual(span["source_layer_user_name"], "fReEkIcAd")
        self.assertEqual(span["source_drawing_id"], "bend-span")
        self.assertEqual(span["annotation_position"], [3.1, 0.0])
        self.assertAlmostEqual(span["span_mm"], 0.942477796076938)
        self.assertAlmostEqual(span["radius_mm"], 0.5)
        self.assertEqual(span["radius_source"], "s")
        self.assertAlmostEqual(explicit["radius_mm"], 2.0)
        self.assertEqual(explicit["radius_source"], "r")
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_RADIUS_PRECEDENCE" for issue in explicit["issues"]))
        self.assertFalse(unset["configured"])
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_ANNOTATION_MISSING" for issue in unset["issues"]))
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_ANNOTATION_CONFLICT" for issue in malformed["issues"]))
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_ANNOTATION_MALFORMED" for issue in malformed["issues"]))
        self.assertEqual(zero["radius_mm"], 0.0)
        self.assertFalse(any(issue["code"] == "KIKAKUKA_BEND_RADIUS_NEGATIVE" for issue in zero["issues"]))
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_RADIUS_NEGATIVE" for issue in negative["issues"]))

    def test_kikakuka_length_units_are_documented_units(self):
        values, _ = KicadParser._parse_kikakuka_annotation("r=.2in s=10mil")
        self.assertAlmostEqual(values["r"], 5.08)
        self.assertAlmostEqual(values["s"], 0.254)
        values, _ = KicadParser._parse_kikakuka_annotation("r=2500um s=2.5CM")
        self.assertAlmostEqual(values["r"], 2.5)
        self.assertAlmostEqual(values["s"], 25.0)

    def test_kikakuka_metadata_survives_design_import(self):
        board_path = Path(self.temporary.name) / "kikakuka-design.kicad_pcb"
        board_path.write_text(KIKAKUKA_BOARD, encoding="utf-8")
        design = _design_from_kicad(str(board_path))

        self.assertEqual(design.technology, "flex")
        self.assertEqual(design.bends[0]["annotation"], "s=0.942477796076938mm a=90")
        self.assertAlmostEqual(design.bends[0]["radius_mm"], 0.5)
        self.assertEqual(design.regions[0]["format"], "kikakuka/freekicad-v1")
        restored = SpiDeRV2.from_dict(SpiDeRV2.from_v1(design).to_dict()).to_v1()
        self.assertEqual(restored.bends[0]["annotation"], design.bends[0]["annotation"])
        self.assertEqual(restored.bends[0]["span_mm"], design.bends[0]["span_mm"])
        self.assertEqual(restored.bends[4]["issues"], design.bends[4]["issues"])

    def test_kikakuka_rejects_nonfinite_numbers_and_respects_endpoint_tolerance(self):
        path = Path(self.temporary.name) / "kikakuka-numeric.kicad_pcb"
        path.write_text(KIKAKUKA_NUMERIC_EDGE_BOARD, encoding="utf-8")
        parser = KicadParser(path)
        exact, outside, zero_angle, derived_overflow, literal_overflow, unit_overflow = parser.bends

        self.assertEqual(exact["annotation"], "a=90 r=.5mm")
        self.assertAlmostEqual(exact["radius_mm"], 0.5)
        self.assertIsNone(outside["annotation"])
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_ANNOTATION_MISSING" for issue in outside["issues"]))
        self.assertTrue(any(issue["code"] == "KIKAKUKA_ANNOTATION_ORPHAN" for issue in parser.flex_issues))
        self.assertIsNone(zero_angle["radius_mm"])
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_SPAN_NEEDS_ANGLE" for issue in zero_angle["issues"]))
        self.assertIsNone(derived_overflow["radius_mm"])
        self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_RADIUS_NONFINITE" for issue in derived_overflow["issues"]))
        for bend in (literal_overflow, unit_overflow):
            self.assertIsNone(bend["radius_mm"])
            self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_ANNOTATION_MALFORMED" for issue in bend["issues"]))
        json.dumps(parser.bends, allow_nan=False)

    def test_kikakuka_span_requires_finite_explicit_thickness(self):
        cases = (
            ("", "missing"),
            ('(setup (stackup (layer "F.Cu" (type "copper") (thickness 1e308)) (layer "B.Cu" (type "copper") (thickness 1e308))))', "nonfinite"),
        )
        for stackup, label in cases:
            with self.subTest(label=label):
                path = Path(self.temporary.name) / f"kikakuka-thickness-{label}.kicad_pcb"
                path.write_text(kikakuka_span_board(stackup), encoding="utf-8")
                bend = KicadParser(path).bends[0]
                self.assertIsNone(bend["radius_mm"])
                self.assertTrue(any(issue["code"] == "KIKAKUKA_BEND_SPAN_NEEDS_THICKNESS" for issue in bend["issues"]))


if __name__ == "__main__":
    unittest.main()
