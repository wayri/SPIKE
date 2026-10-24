# SPDX-License-Identifier: Apache-2.0
"""Independent topology, volume and finite-contact checks for board tetrahedra."""
from __future__ import annotations

from copy import deepcopy
import itertools
import json
import math
import unittest

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, box

from python.spike_core.dc_board_volume import compile_board_volume
from python.spike_core.dc_tetra_rt0 import solve_tetra_dc


def fixture():
    land = box(0, 0, 2, 2).difference(box(.8, .8, 1.2, 1.2))
    bore = box(.8, .8, 1.2, 1.2)
    barrel = box(.7, .7, 1.3, 1.3).difference(bore)
    rotated = affinity.rotate(box(3, 0, 3.8, .5), 23, origin=(3.4, .25))
    second = affinity.rotate(box(4.2, .2, 4.7, .8), -17, origin=(4.45, .5))
    tiny = Polygon([(5., 0.), (5.0002, 0.), (5., .0002)])
    groups = {
        ("B.Cu", "A"): {"geometry": land, "thickness_mm": .1, "z_mm": .05,
                           "conductivity_s_m": 5.8e7,
                           "source_inventory": [{"id": "via-1", "kind": "via"}, {"id": "trace-b", "kind": "track"}]},
        ("F.Cu", "A"): {"geometry": land, "thickness_mm": .1, "z_mm": 1.05,
                           "conductivity_s_m": 5.8e7,
                           "source_inventory": [{"id": "via-1", "kind": "via"}, {"id": "trace-f", "kind": "track"}]},
        ("In1.Cu", "B"): {"geometry": MultiPolygon([rotated, second, tiny]), "thickness_mm": .06,
                             "z_mm": .5, "conductivity_s_m": 4.1e7,
                             "source_inventory": [{"id": "isolated-b", "kind": "zone"}]},
    }
    barrels = [{"id": "barrel-1", "source_id": "via-1", "net": "A", "geometry": barrel,
                "z_min_mm": .1, "z_max_mm": 1., "conductivity_s_m": 5.8e7}]
    holed_patch = box(1.35, 0, 2, .65).difference(box(1.55, .2, 1.75, .4))
    contacts = [
        {"id": "source", "layer": "B.Cu", "net": "A", "side": "bottom",
         "geometry": box(0, .1, .4, .7), "current_a": 1.},
        {"id": "return", "layer": "F.Cu", "net": "A", "side": "top",
         "geometry": MultiPolygon([holed_patch, box(.1, 1.4, .35, 1.8)]), "current_a": -1.},
    ]
    return groups, barrels, contacts


def compile_fixture(**kwargs):
    groups, barrels, contacts = fixture()
    return compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"},
                                target_mm=kwargs.pop("target_mm", .55),
                                max_cells=kwargs.pop("max_cells", 5000), **kwargs)


class BoardVolumeTests(unittest.TestCase):
    def test_global_arrangement_positive_tetrahedra_volume_and_contacts(self):
        groups, barrels, contacts = fixture()
        before_inventory = deepcopy({key: value["source_inventory"] for key, value in groups.items()})
        result = compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"},
                                      target_mm=.55, max_cells=5000)
        self.assertEqual(before_inventory, {key: value["source_inventory"] for key, value in groups.items()})
        request, coverage = result["request"], result["coverage"]
        self.assertEqual(set(request), {"contract", "mesh", "conductivity_s_m", "contacts"})
        self.assertEqual(request["contract"], "spike/tetra-dc-rt0-request/v1")
        mesh = request["mesh"]
        self.assertEqual(mesh["counts"], {"vertices": len(mesh["vertices"]), "cells": len(mesh["cells"])})
        self.assertEqual(set(request["conductivity_s_m"]), {cell["id"] for cell in mesh["cells"]})
        json.dumps(result, sort_keys=True, allow_nan=False)
        self.assertLessEqual(len(mesh["cells"]), 5000)
        points = np.asarray(mesh["vertices"])
        for cell in mesh["cells"]:
            xyz = points[cell["vertices"]]
            self.assertGreater(np.linalg.det((xyz[1:] - xyz[0]).T), 0.)
        for row in coverage["volumes"]:
            self.assertAlmostEqual(row["source_volume_mm3"], row["mesh_volume_mm3"], delta=2e-12)
            audit = row["footprint_overlay_audit"]
            self.assertTrue(audit["accepted"])
            self.assertGreaterEqual(audit["source_minus_mesh_area_mm2"], 0.)
            self.assertGreaterEqual(audit["mesh_minus_source_area_mm2"], 0.)
            self.assertLessEqual(audit["symmetric_difference_area_mm2"],
                                 audit["admitted_overlay_tolerance_mm2"])
        self.assertTrue(coverage["all_source_volumes_retained"])
        self.assertTrue(coverage["no_intentional_geometry_omission"])
        self.assertGreaterEqual(coverage["overlay_symmetric_difference_volume_mm3"], 0.)
        self.assertEqual(coverage["expected_axial_source_ids"], ["via-1"])
        self.assertEqual(len(coverage["volumes"]), 4)
        isolated = next(row for row in coverage["volumes"] if row["net"] == "B")
        self.assertEqual(isolated["input_geometry"]["component_count"], 3)
        self.assertGreater(isolated["mesh_volume_mm3"], 0.)
        self.assertEqual({row["body_id"] for row in mesh["object_map"].values() if row["net"] == "A"}, {"net:A"})

        face_count = {}
        for cell in mesh["cells"]:
            for face in itertools.combinations(cell["vertices"], 3):
                key = tuple(sorted(face)); face_count[key] = face_count.get(key, 0) + 1
        self.assertEqual([item["id"] for item in request["contacts"]], ["source", "return"])
        for item in request["contacts"]:
            self.assertTrue(item["faces"])
            self.assertTrue(all(face_count[tuple(sorted(face))] == 1 for face in item["faces"]))
            for face in item["faces"]:
                xy = points[face, :2]
                signed = ((xy[1, 0]-xy[0, 0])*(xy[2, 1]-xy[0, 1])
                          - (xy[1, 1]-xy[0, 1])*(xy[2, 0]-xy[0, 0]))
                self.assertGreater(signed if item["id"] == "return" else -signed, 0.)
        for row in coverage["contacts"]:
            self.assertAlmostEqual(row["source_area_mm2"], row["mesh_area_mm2"], delta=1e-12)
            self.assertTrue(row["overlay_audit"]["accepted"])
        solved = solve_tetra_dc(request)
        self.assertGreater(solved["joule_heat_w"], 0.)
        self.assertAlmostEqual(solved["signed_terminal_work_w"], solved["joule_heat_w"], delta=1e-12)
        self.assertGreater(solved["current_density_observable"]["undriven_volume_m3"], 0.)
        np.testing.assert_allclose([row["recovered_inward_current_a"] for row in solved["contacts"]],
                                   [1., -1.], rtol=2e-14, atol=0.)

    def test_gap_barrel_and_slabs_remain_distinct_same_source_volumes(self):
        result = compile_fixture(target_mm=.8)
        rows = result["coverage"]["volumes"]
        via_rows = [row for row in rows if any(item["id"] == "via-1" for item in row["source_inventory"])]
        self.assertEqual(len(via_rows), 3)
        spans = sorted((row["z_min_mm"], row["z_max_mm"], row["kind"]) for row in via_rows)
        self.assertEqual(spans, [(0., .1, "copper_slab"), (.1, 1., "plated_barrel"), (1., 1.1, "copper_slab")])
        self.assertEqual(next(row for row in rows if row["kind"] == "plated_barrel")["landing_layers"],
                         [["B.Cu"], ["F.Cu"]])

    def test_one_expected_axial_source_can_have_several_disjoint_gap_barrels(self):
        groups, barrels, contacts = fixture()
        groups[("In2.Cu", "A")] = {"geometry": groups[("B.Cu", "A")]["geometry"],
            "thickness_mm": .1, "z_mm": .55, "conductivity_s_m": 5.8e7,
            "source_inventory": [{"id": "via-1", "kind": "via"}]}
        middle_low = groups[("In2.Cu", "A")]["z_mm"] - groups[("In2.Cu", "A")]["thickness_mm"] / 2
        middle_high = groups[("In2.Cu", "A")]["z_mm"] + groups[("In2.Cu", "A")]["thickness_mm"] / 2
        first = {**barrels[0], "id": "barrel-low", "z_max_mm": middle_low}
        second = {**barrels[0], "id": "barrel-high", "z_min_mm": middle_high}
        result = compile_board_volume(groups, [first, second], contacts,
                                      expected_axial_source_ids={"via-1"}, target_mm=.8)
        self.assertEqual(result["coverage"]["compiled_axial_source_ids"], ["via-1"])
        self.assertEqual(sum(row["kind"] == "plated_barrel" for row in result["coverage"]["volumes"]), 2)

    def test_overlap_missing_barrel_and_unlanded_barrel_fail_closed(self):
        groups, barrels, contacts = fixture()
        groups[("Other.Cu", "C")] = {**groups[("B.Cu", "A")], "source_inventory": [{"id": "other"}],
                                        "z_mm": .05}
        with self.assertRaisesRegex(ValueError, "volumes overlap"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)
        groups, barrels, contacts = fixture()
        with self.assertRaisesRegex(ValueError, "exactly cover expected"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1", "missing"}, target_mm=.5)
        barrels[0]["geometry"] = box(10, 10, 11, 11).difference(box(10.2, 10.2, 10.8, 10.8))
        with self.assertRaisesRegex(ValueError, "lacks complete same-net slab support"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)

    def test_internal_partial_void_and_overlapping_contacts_reject(self):
        groups, barrels, contacts = fixture()
        contacts[0].update(side="top", geometry=box(.71, .71, .79, .79))
        with self.assertRaisesRegex(ValueError, "internal or nonmanifold"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)
        groups, barrels, contacts = fixture()
        contacts[0]["geometry"] = box(.9, .9, 1.1, 1.1)
        with self.assertRaisesRegex(ValueError, "cuts a void or leaves copper"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)
        groups, barrels, contacts = fixture()
        contacts.append({**contacts[0], "id": "overlap", "current_a": 0.})
        with self.assertRaisesRegex(ValueError, "footprints overlap"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)

    def test_no_point_contact_or_different_net_face_weld(self):
        groups, barrels, contacts = fixture()
        contacts[0]["geometry"] = Point(.2, .2)
        with self.assertRaisesRegex(ValueError, "polygonal geometry"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)
        groups, barrels, contacts = fixture()
        groups[("Touch.Cu", "C")] = {"geometry": groups[("B.Cu", "A")]["geometry"], "thickness_mm": .1,
            "z_mm": -.05, "conductivity_s_m": 1e7, "source_inventory": [{"id": "touch", "kind": "zone"}]}
        with self.assertRaisesRegex(ValueError, "Different nets touch"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)

    def test_preflight_budget_rejects_without_partial_mesh(self):
        with self.assertRaisesRegex(ValueError, "budget"):
            compile_fixture(target_mm=.05, max_cells=30)
        groups, barrels, contacts = fixture()
        contacts[0]["current_a"] = math.inf
        with self.assertRaisesRegex(ValueError, "Invalid contact current"):
            compile_board_volume(groups, barrels, contacts, expected_axial_source_ids={"via-1"}, target_mm=.5)

    def test_vertical_refinement_preserves_exact_shared_endpoints(self):
        outer = Point(0, 0).buffer(.4, quad_segs=32)
        bore = Point(0, 0).buffer(.15, quad_segs=32)
        land = outer.difference(bore)
        groups = {
            ("B.Cu", "STACK"): {"geometry": land, "thickness_mm": .035, "z_mm": -1.6,
                "conductivity_s_m": 5.8e7, "source_inventory": [{"id": "pad", "kind": "pad"}]},
            ("F.Cu", "STACK"): {"geometry": land, "thickness_mm": .035, "z_mm": 0.,
                "conductivity_s_m": 5.8e7, "source_inventory": [{"id": "pad", "kind": "pad"}]},
        }
        barrels = [{"id": "gap", "source_id": "pad", "net": "STACK",
                    "geometry": Point(0, 0).buffer(.175, quad_segs=32).difference(bore),
                    "z_min_mm": -1.5825, "z_max_mm": -.0175,
                    "conductivity_s_m": 5.8e7}]
        contacts = [
            {"id": "bottom", "layer": "B.Cu", "net": "STACK", "side": "bottom",
             "geometry": land, "current_a": 1.},
            {"id": "top", "layer": "F.Cu", "net": "STACK", "side": "top",
             "geometry": land, "current_a": -1.},
        ]
        result = compile_board_volume(groups, barrels, contacts,
                                      expected_axial_source_ids=["pad"], target_mm=1., max_cells=5000)
        self.assertEqual(result["coverage"]["z_plane_count"], 5)
        self.assertEqual(result["request"]["mesh"]["counts"]["cells"], 4608)


if __name__ == "__main__":
    unittest.main()
