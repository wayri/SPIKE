import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource

from python.core.board_parser import KicadParser
from python.spike_core.design_ir_v2 import DesignIRV2
from python.spike_core.kicad_importer import import_kicad_design


class KicadThermalConnectionRetentionTests(unittest.TestCase):
    def write(self, body: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "thermal-connections.kicad_pcb"
        path.write_text(body, encoding="utf-8")
        return path

    def fixture(self, *, zone_connect="", footprint_connect="", pad_connect="") -> Path:
        return self.write(f"""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
          (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layer "F.Cu") (uuid "zone-a")
            {zone_connect}
            (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.4))
            (polygon (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5)))
            (filled_polygon (layer "F.Cu") (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5))))
          (footprint "Fixture:Part" (layer "F.Cu") (at 1 1) (uuid "fp-a")
            (property "Reference" "J1") {footprint_connect}
            (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 1 "VCC")
              (uuid "pad-a") {pad_connect}))
        )""")

    def test_zone_and_override_values_are_typed_and_round_trip(self):
        path = self.fixture(
            zone_connect="(connect_pads thru_hole_only (clearance 0.2))",
            footprint_connect="(zone_connect 1)",
            pad_connect="(zone_connect 3) (thermal_gap 0.1) (thermal_bridge_width 0.25) (thermal_bridge_angle 45)",
        )
        parser = KicadParser(path)
        zone, footprint, pad = parser.zones[0], parser.footprints[0], parser.pads[0]
        self.assertEqual(zone["zone_connection_default"], "tht_thermal")
        self.assertTrue(zone["zone_connection_declared"])
        self.assertEqual(zone["clearance_mm"], 0.2)
        self.assertEqual(zone["thermal_gap_mm"], 0.3)
        self.assertEqual(zone["thermal_spoke_width_mm"], 0.4)
        self.assertEqual(zone["filled_copper_state"], "source_filled")
        self.assertEqual(zone["filled_copper_id"], zone["id"])
        self.assertEqual(zone["source_fill_group_id"], "zone-a:F.Cu")
        self.assertEqual(zone["source_fill_component_ordinal"], 1)
        self.assertEqual(zone["source_fill_component_count"], 1)
        self.assertEqual(len(zone["source_fill_group_sha256"]), 64)
        self.assertEqual(len(zone["source_fill_component_sha256"]), 64)
        self.assertEqual(zone["source_fill_representation"], "flat_polygon_path")
        self.assertTrue(zone["source_fill_provenance_complete"])
        self.assertFalse(zone["thermal_topology_eligible"])
        self.assertEqual(footprint["zone_connection_override"], "thermal")
        self.assertEqual(pad["zone_connection_override"], "tht_thermal")
        self.assertEqual(pad["pad_kind"], "smd")
        self.assertEqual(pad["thermal_spoke_angle_deg"], 45.0)

        typed = DesignIRV2.from_v1(import_kicad_design(str(path)))
        restored = DesignIRV2.from_dict(typed.to_dict())
        self.assertEqual(restored.zones[0].zone_connection_default, "tht_thermal")
        self.assertEqual(restored.components[0].zone_connection_override, "thermal")
        self.assertEqual(restored.pads[0].zone_connection_override, "tht_thermal")
        self.assertEqual(restored.pads[0].thermal_spoke_width_override_mm, 0.25)
        schema = json.loads((Path(__file__).parents[2] / "schemas" / "design-ir-v2.schema.json").read_text(encoding="utf-8"))
        v1_schema = json.loads((Path(__file__).parents[2] / "schemas" / "design-ir-v1.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(v1_schema["$id"], Resource.from_contents(v1_schema))
        Draft202012Validator(schema, registry=registry).validate(json.loads(json.dumps(restored.to_dict())))
        forged = restored.to_dict()
        forged["zones"][0]["source_fill_provenance_complete"] = False
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema, registry=registry).validate(forged)

    def test_omission_is_inheritance_while_zone_omission_defaults_to_thermal(self):
        parser = KicadParser(self.fixture())
        self.assertEqual(parser.zones[0]["zone_connection_default"], "thermal")
        self.assertFalse(parser.zones[0]["zone_connection_declared"])
        self.assertEqual(parser.footprints[0]["zone_connection_override"], "inherit")
        self.assertEqual(parser.pads[0]["zone_connection_override"], "inherit")
        self.assertTrue(parser.zones[0]["thermal_settings_valid"])
        self.assertTrue(parser.pads[0]["thermal_settings_valid"])

    def test_unsupported_and_nonfinite_settings_fail_closed(self):
        parser = KicadParser(self.fixture(
            zone_connect="(connect_pads future_mode)",
            footprint_connect="(zone_connect 9)",
            pad_connect="(zone_connect 9) (thermal_gap -0.1) (thermal_bridge_angle 360)",
        ))
        self.assertEqual(parser.zones[0]["zone_connection_default"], "unknown")
        self.assertFalse(parser.zones[0]["thermal_settings_valid"])
        self.assertEqual(parser.footprints[0]["zone_connection_override"], "unknown")
        self.assertEqual(parser.pads[0]["zone_connection_override"], "unknown")
        self.assertFalse(parser.pads[0]["thermal_settings_valid"])
        self.assertGreaterEqual(len(parser.diagnostics), 4)

        typed = DesignIRV2.from_v1(import_kicad_design(str(self.fixture())))
        broken = typed.to_dict()
        broken["pads"][0]["zone_connection_override"] = "future_mode"
        with self.assertRaisesRegex(ValueError, "override"):
            DesignIRV2.from_dict(broken)
        broken = typed.to_dict()
        broken["zones"][0]["thermal_gap_mm"] = -0.01
        with self.assertRaisesRegex(ValueError, "dimensions"):
            DesignIRV2.from_dict(broken)
        broken = typed.to_dict()
        broken["zones"][0]["thermal_topology_eligible"] = True
        with self.assertRaisesRegex(ValueError, "not yet eligible"):
            DesignIRV2.from_dict(broken)

    def test_source_filled_components_retain_layer_group_and_order_independent_snapshot(self):
        def board(polygons: str) -> Path:
            return self.write(f"""(kicad_pcb
              (version 20260101)
              (layers (0 "F.Cu" signal) (2 "B.Cu" signal))
              (net 1 "VCC")
              (zone (net 1) (net_name "VCC") (layers "F.Cu" "B.Cu") (uuid "zone-multi")
                (connect_pads thermal)
                (fill yes (thermal_gap 0.2) (thermal_bridge_width 0.3))
                (polygon (pts (xy 0 0) (xy 8 0) (xy 8 8) (xy 0 8)))
                {polygons}))""")

        first = """
          (filled_polygon (layer "F.Cu") (pts (xy 0 0) (xy 2 0) (xy 2 2) (xy 0 2)))
          (filled_polygon (layer "B.Cu") (pts (xy 0 0) (xy 4 0) (xy 4 4) (xy 0 4)))
          (filled_polygon (layer "F.Cu") (pts (xy 6 6) (xy 8 6) (xy 8 8) (xy 6 8)))
        """
        reordered = """
          (filled_polygon (layer "F.Cu") (pts (xy 6 6) (xy 8 6) (xy 8 8) (xy 6 8)))
          (filled_polygon (layer "B.Cu") (pts (xy 0 0) (xy 4 0) (xy 4 4) (xy 0 4)))
          (filled_polygon (layer "F.Cu") (pts (xy 0 0) (xy 2 0) (xy 2 2) (xy 0 2)))
        """
        parsed = KicadParser(board(first)).zones
        swapped = KicadParser(board(reordered)).zones
        front = [zone for zone in parsed if zone["layer"] == "F.Cu"]
        back = [zone for zone in parsed if zone["layer"] == "B.Cu"]
        self.assertEqual([zone["source_fill_component_ordinal"] for zone in front], [1, 2])
        self.assertTrue(all(zone["source_fill_component_count"] == 2 for zone in front))
        self.assertEqual(back[0]["source_fill_component_count"], 1)
        self.assertNotEqual(front[0]["source_fill_group_id"], back[0]["source_fill_group_id"])
        self.assertEqual(len({zone["source_fill_group_sha256"] for zone in front}), 1)
        swapped_front = [zone for zone in swapped if zone["layer"] == "F.Cu"]
        self.assertEqual(front[0]["source_fill_group_sha256"], swapped_front[0]["source_fill_group_sha256"])
        self.assertEqual(
            {zone["source_fill_component_sha256"] for zone in front},
            {zone["source_fill_component_sha256"] for zone in swapped_front},
        )
        self.assertTrue(all(not zone["thermal_topology_eligible"] for zone in parsed))

    def test_incomplete_source_fill_group_is_retained_but_not_qualified(self):
        parser = KicadParser(self.write("""(kicad_pcb
          (version 20260101)
          (layers (0 "F.Cu" signal))
          (net 1 "VCC")
          (zone (net 1) (net_name "VCC") (layer "F.Cu") (uuid "zone-incomplete")
            (fill yes (thermal_gap 0.2) (thermal_bridge_width 0.3))
            (polygon (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5)))
            (filled_polygon (layer "F.Cu") (pts (xy 0 0) (xy 5 0) (xy 5 5) (xy 0 5)))
            (filled_polygon (layer "F.Cu") (pts (xy 1 1) (xy 2 1)))))
        """))
        self.assertEqual(len(parser.zones), 1)
        zone = parser.zones[0]
        self.assertFalse(zone["source_fill_provenance_complete"])
        self.assertEqual(zone["source_fill_group_id"], "")
        self.assertEqual(zone["source_fill_component_count"], 0)
        self.assertEqual(zone["source_fill_representation"], "none")
        self.assertFalse(zone["thermal_topology_eligible"])
        self.assertTrue(any("fewer than three points" in item for item in parser.diagnostics))
        self.assertTrue(any("provenance exceeds bounds or is incomplete" in item for item in parser.diagnostics))

    def test_bundled_boards_retain_source_filled_zone_and_override_census(self):
        demo = Path(__file__).parents[2] / "app" / "public" / "demo"
        ebrake = KicadParser(demo / "ebrake1.kicad_pcb")
        ebrake_filled = [zone for zone in ebrake.zones if zone.get("source_kind") == "filled_zone"]
        self.assertEqual(len(ebrake_filled), 26)
        self.assertEqual(Counter(zone["zone_connection_default"] for zone in ebrake_filled), {"solid": 26})
        self.assertTrue(all(zone["source_fill_provenance_complete"] for zone in ebrake_filled))
        self.assertTrue(all(not zone["thermal_topology_eligible"] for zone in ebrake_filled))
        self.assertEqual(sum(item["zone_connection_override"] == "thermal" for item in ebrake.footprints), 6)
        self.assertEqual(sum(item["zone_connection_override"] == "solid" for item in ebrake.pads), 14)
        self.assertEqual(sum(item["thermal_spoke_angle_deg"] == 45.0 for item in ebrake.pads), 12)

        modular = KicadParser(demo / "MODULAR-BUS-NIB.kicad_pcb")
        modular_filled = [zone for zone in modular.zones if zone.get("source_kind") == "filled_zone"]
        self.assertEqual(len(modular_filled), 83)
        self.assertEqual(Counter(zone["zone_connection_default"] for zone in modular_filled), {"solid": 80, "thermal": 3})
        self.assertTrue(all(zone["source_fill_provenance_complete"] for zone in modular_filled))
        self.assertTrue(all(not zone["thermal_topology_eligible"] for zone in modular_filled))
        self.assertEqual(sum(item["thermal_spoke_angle_deg"] == 0.0 for item in modular.pads), 14)
        self.assertTrue(all(item["zone_connection_override"] == "inherit" for item in modular.pads))


if __name__ == "__main__":
    unittest.main()
