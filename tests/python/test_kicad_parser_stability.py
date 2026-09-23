import tempfile
import unittest
from pathlib import Path

from python.core.board_parser import KicadParser
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.kicad_importer import import_kicad_design


class KicadParserStabilityTests(unittest.TestCase):
    def write(self, contents: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.kicad_pcb"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_malformed_root_fails_instead_of_returning_partial_design(self):
        path = self.write("(not_a_board (layers (0 F.Cu signal)))")
        with self.assertRaises(RuntimeError):
            KicadParser(path)

    def test_copper_graphic_polygon_is_preserved_as_conductive_geometry(self):
        path = self.write("""(kicad_pcb
          (version 20241229)
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
          (net 1 "VCC")
          (gr_poly (pts (xy 1 1) (xy 4 1) (xy 4 3) (xy 1 3)) (layer "F.Cu") (net 1))
        )""")
        parser = KicadParser(path)
        self.assertEqual(len(parser.zones), 1)
        self.assertEqual(parser.zones[0]["source_kind"], "graphic_polygon")
        self.assertEqual(parser.zones[0]["net_name"], "VCC")
        self.assertFalse(parser.diagnostics)

    def test_multilayer_zone_uses_each_filled_polygon_layer_without_outline_duplication(self):
        path = self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal) (4 "In1.Cu" power) (2 "B.Cu" signal))
          (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layers "F.Cu" "In1.Cu" "B.Cu")
            (uuid "zone-uuid")
            (polygon (pts (xy 0 0) (xy 10 0) (xy 10 10) (xy 0 10)))
            (filled_polygon (layer "F.Cu")
              (pts (xy 0 0) (xy 4 0) (xy 4 4) (xy 0 4)))
            (filled_polygon (layer "In1.Cu")
              (pts (xy 1 1) (xy 5 1) (xy 5 5) (xy 1 5)))
            (filled_polygon (layer "B.Cu")
              (pts (xy 2 2) (xy 6 2) (xy 6 6) (xy 2 6)))
          )
        )""")
        parser = KicadParser(path)
        self.assertEqual(len(parser.zones), 3)
        self.assertEqual({zone["layer"] for zone in parser.zones}, {"F.Cu", "In1.Cu", "B.Cu"})
        self.assertTrue(all(zone["source_kind"] == "filled_zone" for zone in parser.zones))
        self.assertEqual(len({zone["id"] for zone in parser.zones}), 3)

    def test_modular_12vout_zone_is_one_fill_per_copper_layer(self):
        path = Path(__file__).resolve().parents[2] / "app" / "public" / "demo" / "MODULAR-BUS-NIB.kicad_pcb"
        parser = KicadParser(path)
        zones = [zone for zone in parser.zones if zone["net_name"] == "/12Vout"]
        self.assertEqual(len(zones), 6)
        self.assertEqual(
            {zone["layer"] for zone in zones},
            {"F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"},
        )
        self.assertEqual(len({(zone["zone_uuid"], zone["layer"]) for zone in zones}), 6)

    def test_native_object_ids_survive_parse_import_and_v2_normalization(self):
        path = self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
          (net 1 "VCC")
          (segment (start 0 0) (end 2 0) (width 0.2) (layer "F.Cu") (net 1)
            (uuid "track-uuid"))
          (arc (start 2 0) (mid 3 1) (end 4 0) (width 0.2) (layer "F.Cu") (net 1)
            (uuid "arc-uuid"))
          (via (at 4 0) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net 1)
            (tstamp "via-tstamp"))
          (footprint "Fixture:R_0603" (layer "F.Cu") (at 5 0)
            (uuid "footprint-uuid")
            (property "Reference" "R1")
            (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 1 "VCC")
              (uuid "pad-uuid")))
        )""")

        parser = KicadParser(path)
        self.assertEqual(parser.tracks[0]["id"], "track-uuid")
        self.assertEqual(
            [track["id"] for track in parser.tracks[1:]],
            [f"arc-uuid:segment:{index}" for index in range(1, 9)],
        )
        self.assertTrue(all(track["source_parent_id"] == "arc-uuid" for track in parser.tracks[1:]))
        self.assertEqual(parser.vias[0]["id"], "via-tstamp")
        self.assertEqual(parser.footprints[0]["id"], "footprint-uuid")
        self.assertEqual(parser.pads[0]["id"], "pad-uuid")

        legacy = import_kicad_design(str(path))
        normalized = DesignIRV2.from_v1(legacy)
        self.assertEqual(normalized.tracks[0].source_id, "track-uuid")
        self.assertEqual(normalized.vias[0].source_id, "via-tstamp")
        self.assertEqual(normalized.pads[0].source_id, "pad-uuid")
        self.assertEqual(normalized.components[0].source_id, "footprint-uuid")

    def test_through_hole_and_oval_slot_dimensions_are_preserved(self):
        path = self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
          (net 1 "VCC")
          (footprint "Fixture:TH" (layer "F.Cu") (at 10 20)
            (property "Reference" "J1")
            (pad "1" thru_hole circle (at 0 0) (size 2 2)
              (drill 0.8) (layers "*.Cu") (net 1 "VCC"))
            (pad "2" thru_hole oval (at 3 0) (size 3 1.8)
              (drill oval 1.6 0.7) (layers "*.Cu") (net 1 "VCC")))
        )""")

        pads = KicadParser(path).pads
        self.assertEqual(pads[0]["drill_shape"], "circle")
        self.assertEqual(pads[0]["drill_size"], (0.8, 0.8))
        self.assertEqual(pads[0]["drill"], 0.8)
        self.assertEqual(pads[1]["drill_shape"], "oval")
        self.assertEqual(pads[1]["drill_size"], (1.6, 0.7))
        self.assertEqual(pads[1]["drill"], 0.7)

    def test_simple_filled_undrilled_custom_pad_round_trips_exactly(self):
        path = self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (footprint "Fixture:Custom" (layer "F.Cu") (at 10 20 90)
            (property "Reference" "U1")
            (pad "1" smd custom (at 1 2) (size 4 4) (layers "F.Cu") (net 1 "VCC")
              (uuid "custom-pad-uuid")
              (options (clearance outline) (anchor rect))
              (primitives
                (gr_poly (pts (xy -2 -2) (xy 2 -2) (xy 2 2) (xy -2 2))
                  (width 0) (fill yes)))))
        )""")

        parser = KicadParser(path)
        expected = {
            "status": "supported",
            "coordinate_space": "pad_local_mm",
            "mirror_x": False,
            "positive_filled_polygon": [[-2.0, -2.0], [2.0, -2.0], [2.0, 2.0], [-2.0, 2.0]],
        }
        self.assertEqual(parser.pads[0]["custom_geometry"], expected)
        self.assertFalse(parser.diagnostics)

        normalized = DesignIRV2.from_v1(import_kicad_design(str(path)))
        restored = DesignIRV2.from_dict(normalized.to_dict())
        self.assertEqual(restored.pads[0].custom_geometry, expected)
        self.assertEqual(restored.to_v1().pads[0]["custom_geometry"], expected)

    def test_filled_circle_custom_pad_is_bounded_and_round_trips(self):
        path = self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (footprint "Fixture:Custom" (layer "F.Cu")
            (property "Reference" "U1")
            (pad "1" smd custom (at 0 0) (size 4 4) (layers "F.Cu") (net 1 "VCC")
              (uuid "unsupported-custom-pad")
              (options (clearance outline) (anchor rect))
              (primitives (gr_circle (center 0 0) (end 1 0) (width 0) (fill yes)))))
        )""")

        parser = KicadParser(path)
        self.assertEqual(len(parser.pads), 1)
        geometry = parser.pads[0]["custom_geometry"]
        self.assertEqual(geometry["status"], "supported")
        self.assertEqual(geometry["curve_approximation"]["method"], "inscribed_equal_angle_v1")
        self.assertLessEqual(geometry["curve_approximation"]["maximum_sagitta_mm"], 0.001)
        self.assertTrue(geometry["curve_approximation"]["conservative_source_containment"])
        restored = DesignIRV2.from_v1(import_kicad_design(str(path)))
        self.assertEqual(restored.to_v1().pads[0]["custom_geometry"], geometry)

    def test_rect_anchor_is_exactly_unioned_with_one_filled_polygon(self):
        path = self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (footprint "Fixture:Custom" (layer "F.Cu")
            (property "Reference" "U1")
            (pad "1" smd custom (at 0 0) (size 2 2) (layers "F.Cu") (net 1 "VCC")
              (uuid "anchor-union-pad")
              (options (clearance outline) (anchor rect))
              (primitives (gr_poly
                (pts (xy 0 -2) (xy 2 -2) (xy 2 2) (xy 0 2))
                (width 0) (fill yes)))))
        )""")

        parser = KicadParser(path)
        geometry = parser.pads[0]["custom_geometry"]
        self.assertEqual(geometry["status"], "supported")
        self.assertEqual(
            geometry["positive_filled_polygon"],
            [[-1.0, -1.0], [0.0, -1.0], [0.0, -2.0], [2.0, -2.0],
             [2.0, 2.0], [0.0, 2.0], [0.0, 1.0], [-1.0, 1.0]],
        )
        restored = DesignIRV2.from_v1(import_kicad_design(str(path)))
        self.assertEqual(restored.to_v1().pads[0]["custom_geometry"], geometry)

    def test_bundled_modular_custom_pad_anchor_unions_are_all_admitted(self):
        board = Path(__file__).parents[2] / "app" / "public" / "demo" / "MODULAR-BUS-NIB.kicad_pcb"
        parser = KicadParser(board)
        custom = [pad for pad in parser.pads if pad.get("shape") == "custom"]
        self.assertEqual(len(custom), 6)
        self.assertEqual({pad["custom_geometry"]["status"] for pad in custom}, {"supported"})
        normalized = DesignIRV2.from_v1(import_kicad_design(str(board)))
        typed_custom = [pad for pad in normalized.pads if pad.shape == "custom"]
        self.assertEqual(len(typed_custom), 6)
        self.assertTrue(all(len(pad.custom_geometry["positive_filled_polygon"]) >= 4 for pad in typed_custom))


if __name__ == "__main__":
    unittest.main()
