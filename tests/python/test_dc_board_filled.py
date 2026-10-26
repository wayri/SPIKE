# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import unittest

from shapely.geometry import Point

from python.spike_core.contracts import SpiDeR
from python.spike_core.solvers.power_integrity.dc.dc_board_filled import prepare_board_copper_groups


def bridged_zone(identity="zone", net="N"):
    points = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0),
              (1, 1), (1, 3), (3, 3), (3, 1), (1, 1), (0, 0)]
    return {"id": identity, "layer": "F.Cu", "net_name": net, "points": points,
            "source_kind": "filled_zone", "source_zone_id": identity,
            "filled_copper_id": identity + ":fill", "source_fill_group_sha256": "a" * 64,
            "source_fill_component_sha256": "b" * 64,
            "source_fill_provenance_complete": True, "filled_copper_state": "source_filled",
            "source_fill_representation": "flat_polygon_path"}


def design(zone):
    return SpiDeR(layers=[{"name": "F.Cu"}, {"name": "B.Cu"}], zones=[zone],
        stackup=[{"name": "F.Cu", "type": "copper", "thickness": .035},
                 {"name": "core", "type": "dielectric", "thickness": 1.},
                 {"name": "B.Cu", "type": "copper", "thickness": .035}])


class BoardFilledTests(unittest.TestCase):
    def test_retraced_bridge_hole_is_exact_and_source_identity_is_restored(self):
        board = design(bridged_zone())
        before = deepcopy(board.to_dict())
        groups, axial, evidence = prepare_board_copper_groups(board, ["N"])
        self.assertEqual(board.to_dict(), before)
        self.assertEqual(axial, [])
        copper = groups["F.Cu", "N"]["geometry"]
        self.assertAlmostEqual(copper.area, 12., places=12)
        self.assertFalse(copper.covers(Point(2, 2)))
        self.assertEqual(groups["F.Cu", "N"]["source_inventory"], [{"id": "zone", "kind": "zone"}])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["source_record_id"], "zone")
        self.assertEqual(evidence[0]["source_zone_id"], "zone")
        self.assertEqual(evidence[0]["hole_count"], 1)
        self.assertTrue(evidence[0]["overlay_audit"]["accepted"])
        self.assertLessEqual(evidence[0]["overlay_audit"]["symmetric_difference_area_mm2"],
                             evidence[0]["overlay_audit"]["admitted_overlay_tolerance_mm2"])

    def test_simple_zone_uses_existing_path_unchanged(self):
        zone = {"id": "simple", "layer": "F.Cu", "net_name": "N",
                "points": [(0, 0), (2, 0), (2, 1), (0, 1)]}
        groups, axial, evidence = prepare_board_copper_groups(design(zone), ["N"])
        self.assertEqual(evidence, [])
        self.assertEqual(axial, [])
        self.assertAlmostEqual(groups["F.Cu", "N"]["geometry"].area, 2.)
        self.assertEqual(groups["F.Cu", "N"]["source_inventory"], [{"id": "simple", "kind": "zone"}])

    def test_bad_topology_and_unknown_fill_provenance_fail_closed(self):
        bowtie = {"id": "bad", "layer": "F.Cu", "net_name": "N",
                  "points": [(0, 0), (2, 2), (0, 2), (2, 0)]}
        with self.assertRaisesRegex(ValueError, "neither simple"):
            prepare_board_copper_groups(design(bowtie), ["N"])
        unknown = bridged_zone()
        del unknown["source_fill_provenance_complete"]
        with self.assertRaisesRegex(ValueError, "provenance"):
            prepare_board_copper_groups(design(unknown), ["N"])

    def test_foreign_hole_is_applied_after_filled_piece_conversion(self):
        board = design(bridged_zone())
        board.pads = [{"id": "hole", "net_name": "OTHER", "layers": ["B.Cu"], "at": [.5, .5],
                       "shape": "circle", "size": [.5, .5], "drill": .4,
                       "type": "np_thru_hole", "pad_kind": "np_thru_hole"}]
        groups, _, evidence = prepare_board_copper_groups(board, ["N"])
        self.assertFalse(groups["F.Cu", "N"]["geometry"].covers(Point(.5, .5)))
        self.assertEqual(len(evidence), 1)


if __name__ == "__main__":
    unittest.main()
