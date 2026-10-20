# SPDX-License-Identifier: Apache-2.0
"""Independent native contact facts, including drill voids and frame controls."""
import math
import unittest

from scripts.audit_board_terminal_contacts import (
    audit, expression, native_geometry, segment_distance, terminal_fact,
)


class NativeContactTests(unittest.TestCase):
    def test_parser_keeps_quoted_parentheses_and_rejects_incomplete_sources(self):
        self.assertEqual(expression('(kicad_pcb (name "a (b)"))')[1], ["name", "a (b)"])
        for text in ("(kicad_pcb", "(kicad_pcb))", "(kicad_pcb)(kicad_pcb)", "outside (kicad_pcb)"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                expression(text)

    def test_source_frames_and_backside_coordinates_are_not_mirrored_twice(self):
        source = '''(kicad_pcb (net 1 "P")
          (footprint "F" (at 10 20 -90) (property "Reference" "J")
            (pad "2" thru_hole oval (at 2.5 0 270) (size 2 3)
              (drill 1) (layers "*.Cu" "*.Mask") (net 1 "P") (uuid "pad")))
          (footprint "B" (at 30 40) (layer "B.Cu") (fp_text reference "C")
            (pad "1" smd rect (at -.45 0) (size .62 .62)
              (layers "B.Cu") (net 1 "P") (tstamp "old-id"))))'''
        _, pads = native_geometry(source)
        self.assertAlmostEqual(pads[0]["center_mm"][0], 10)
        self.assertAlmostEqual(pads[0]["center_mm"][1], 22.5)
        self.assertEqual(pads[0]["native_pad_angle_deg"], 270)
        self.assertEqual(pads[1]["center_mm"], [29.55, 40])
        self.assertEqual(pads[1]["uuid"], "old-id")

    def test_projection_uses_segment_endpoints_and_degenerate_segment(self):
        self.assertEqual(segment_distance((3, 1), (0, 0), (2, 0)), math.sqrt(2))
        self.assertEqual(segment_distance((1, 1), (0, 0), (2, 0)), 1)
        self.assertEqual(segment_distance((0, 1), (0, 0), (0, 0)), 1)

    def test_drawn_track_never_overrides_through_drill_void(self):
        tracks = [{"net": "3Vin", "layer": "B.Cu", "start_mm": [0, 0],
                   "end_mm": [1, 0], "width_mm": .7, "uuid": "track"}]
        pads = [{"drill_shape": "circle", "drill_dimensions_mm": [.95],
                 "has_drill_offset": False, "center_mm": [0, 0], "layers": ["*.Cu"],
                 "component_pad": "J.1"}]
        fact = terminal_fact((.025, .025), tracks, pads)
        self.assertEqual(len(fact["track_primitive_envelopes_covering_point"]), 1)
        self.assertEqual(len(fact["centered_circular_through_drill_voids_covering_point"]), 1)
        self.assertFalse(fact["finite_electrode_footprint_specified"])
        # A point on the hole wall is not claimed strictly inside its void.
        wall = terminal_fact((.475, 0), tracks, pads)
        self.assertEqual(wall["centered_circular_through_drill_voids_covering_point"], [])
        pads[0]["has_drill_offset"] = True
        self.assertEqual(terminal_fact((0, 0), tracks, pads)["centered_circular_through_drill_voids_covering_point"], [])

    def test_pinned_native_ebrake_and_marble_contact_facts(self):
        result = audit()
        self.assertTrue(result["sources_unchanged"])
        self.assertFalse(result["full_board_pisi_ready"])
        source, load = (result["ebrake_original_dc"][key] for key in ("source", "load"))
        self.assertEqual(source["position_mm"], [165.1, 116.3])
        self.assertEqual(load["position_mm"], [149.05, 116.3])
        self.assertEqual(len(source["track_primitive_envelopes_covering_point"]), 3)
        self.assertEqual(len(load["track_primitive_envelopes_covering_point"]), 1)
        hole = load["centered_circular_through_drill_voids_covering_point"]
        self.assertEqual(len(hole), 1)
        self.assertEqual(hole[0]["component_pad"], "J7.2")
        self.assertAlmostEqual(hole[0]["drill_radius_mm"], .475)
        self.assertAlmostEqual(hole[0]["center_distance_mm"], math.sqrt(2)*.025)
        pads = {p["component_pad"]: p for p in result["marble_native_pads"]}
        self.assertEqual(pads["U37.18"]["center_mm"], [232.9726, 159.4734])
        self.assertAlmostEqual(pads["C383.1"]["center_mm"][0], 234.4784)
        self.assertEqual(pads["R195.1"]["layers"][0], "F.Cu")


if __name__ == "__main__":
    unittest.main()
