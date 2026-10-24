# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

from python.spike_core import si_pair_geometry as geometry
from python.spike_core.spider_v2 import Arc, Pad, Track, Via
from tests.python import test_si_channel as fixtures


class PairGeometryTests(unittest.TestCase):
    def fixture(self):
        design = fixtures.SiUniformChannelTests().coupled_design()
        request = {"signal_net": design.nets[0].id, "victim_net": design.nets[-1].id,
                   "reference_net": "GND", "reference_layer": "layer-reference"}
        return design, request

    def check_coverage(self, design, result):
        for track in design.tracks:
            parts = [p for p in result["track_partitions"] if p["track_id"] == track.id]
            self.assertTrue(parts)
            intervals = [(Fraction(*p["interval"][0]), Fraction(*p["interval"][1])) for p in parts]
            self.assertEqual(intervals[0][0], 0)
            self.assertEqual(intervals[-1][1], 1)
            self.assertTrue(all(a[1] == b[0] for a, b in zip(intervals, intervals[1:])))
            self.assertEqual(sum(b - a for a, b in intervals), 1)

    def test_unequal_subdivision_exact_coverage_and_immutability(self):
        design, request = self.fixture()
        victim = design.tracks[-1]
        original_end = victim.end_mm
        victim.end_mm = (20.0, victim.start_mm[1])
        design.tracks.append(Track(id="extra", net_id=victim.net_id, layer_id=victim.layer_id,
                                  start_mm=victim.end_mm, end_mm=original_end, width_mm=victim.width_mm))
        before = deepcopy(design.to_dict())
        result = geometry.prepare_pair_geometry(design, request)
        self.check_coverage(design, result)
        self.assertEqual(len(result["parallel_overlap_candidates"]), 2)
        self.assertEqual(len(result["routes"]["signal"]["sources"]["tracks"]), 1)
        self.assertEqual(len(result["routes"]["victim"]["sources"]["tracks"]), 2)
        self.assertEqual(design.to_dict(), before)
        self.assertFalse(result["channel_extracted"])
        self.assertFalse(result["production_qualified"])

    def test_nonparallel_fanout_retained_without_fictitious_coupling(self):
        design, request = self.fixture()
        a, b = design.tracks
        a.end_mm = (30.0, 0.0)
        b.end_mm = (30.0, b.end_mm[1])
        design.tracks.append(Track(id="fanout", net_id=a.net_id, layer_id=a.layer_id,
                                  start_mm=a.end_mm, end_mm=(33.0, 4.0), width_mm=a.width_mm))
        result = geometry.prepare_pair_geometry(design, request)
        self.check_coverage(design, result)
        self.assertEqual(result["routes"]["signal"]["straight_centerline_length_mm"], 35.0)
        self.assertEqual([p["status"] for p in result["track_partitions"] if p["track_id"] == "fanout"], ["unpaired"])
        transitions = result["routes"]["signal"]["transition_regions"]
        self.assertTrue(any(t["kind"] == "bend_or_reversal" and "fanout" in t["source_ids"] for t in transitions))

    def test_overlap_partition_not_index_zip(self):
        design, request = self.fixture()
        design.tracks[0].start_mm, design.tracks[0].end_mm = (0, 0), (10, 0)
        design.tracks[1].start_mm, design.tracks[1].end_mm = (8, 1), (3, 1)
        result = geometry.prepare_pair_geometry(design, request)
        self.check_coverage(design, result)
        parts = [p for p in result["track_partitions"] if p["track_id"] == design.tracks[0].id]
        self.assertEqual([p["length_mm"] for p in parts], [3, 5, 2])
        self.assertEqual([p["status"] for p in parts], ["unpaired", "candidate", "unpaired"])

    def test_parallel_candidates_do_not_choose_nearest_or_hide_ambiguity(self):
        design, request = self.fixture()
        b = design.tracks[1]
        design.tracks.append(Track(id="other-run", net_id=b.net_id, layer_id=b.layer_id,
                                  start_mm=(0, 4), end_mm=(50, 4), width_mm=b.width_mm))
        result = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(result["track_partitions"][0]["status"], "ambiguous_candidates")
        self.assertEqual(result["routes"]["victim"]["topology"]["status"], "unresolved_endpoint_topology")

    def test_via_and_arc_never_removed_or_replaced_by_rlc(self):
        design, request = self.fixture()
        a = design.tracks[0]
        design.vias.append(Via(id="via", net_id=a.net_id, center_mm=a.end_mm,
                              start_layer_id=a.layer_id, end_layer_id="layer-reference", diameter_mm=0.6, drill_mm=0.3))
        design.arcs.append(Arc(id="arc", net_id=a.net_id, layer_id=a.layer_id,
                              start_mm=(50, 0), mid_mm=(51, 1), end_mm=(52, 0), width_mm=a.width_mm))
        result = geometry.prepare_pair_geometry(design, request)
        route = result["routes"]["signal"]
        self.assertEqual(route["sources"]["vias"][0]["id"], "via")
        self.assertIsNone(route["arc_centerline_length_mm"])
        self.assertEqual(route["sources"]["arcs"][0]["mid_mm"], (51, 1))
        self.assertNotIn("rlgc_per_m", result)
        self.assertTrue(any(t["kind"] == "via" for t in route["transition_regions"]))

    def test_diagonal_exact_length_and_no_tolerance_fitting(self):
        design, request = self.fixture()
        a, b = design.tracks
        a.start_mm, a.end_mm = (0, 0), (3, 4)
        b.start_mm, b.end_mm = (0, 1), (3, 5)
        result = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(result["routes"]["signal"]["straight_centerline_length_mm"], 5)
        self.assertEqual(len(result["parallel_overlap_candidates"]), 1)
        b.end_mm = (3, 5.000000000000001)
        result = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(result["parallel_overlap_candidates"], [])
        self.check_coverage(design, result)

    def test_terminal_identity_and_reference_no_contact_claim(self):
        design, request = self.fixture()
        for index in range(2):
            design.pads.append(Pad(id=f"pad{index}", net_id=design.nets[0].id))
        request["terminal_pad_ids"] = {"signal": ["pad0", "pad1"]}
        result = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(result["routes"]["signal"]["terminal_pad_ids"], ["pad0", "pad1"])
        self.assertEqual(result["routes"]["signal"]["terminal_status"], "source_assignment_only")
        request["terminal_pad_ids"]["victim"] = ["pad0", "pad1"]
        with self.assertRaisesRegex(ValueError, "two distinct pads"):
            geometry.prepare_pair_geometry(design, request)

    def test_malformed_geometry_and_requests_fail_closed(self):
        for mutation in (lambda d, r: setattr(d.tracks[0], "width_mm", float("nan")),
                         lambda d, r: setattr(d.tracks[0], "width_mm", 10**1000),
                         lambda d, r: setattr(d.tracks[0], "end_mm", d.tracks[0].start_mm),
                         lambda d, r: object.__setattr__(d.frame, "units", "m"),
                         lambda d, r: r.update(path_mode="piecewise_planar"),
                         lambda d, r: r.update(signal_net=[]),
                         lambda d, r: r.update(terminal_pad_ids={"signal": [[], []]}),
                         lambda d, r: r.update(reference_net=r["signal_net"])):
            with self.subTest(mutation=mutation):
                design, request = self.fixture()
                mutation(design, request)
                with self.assertRaises(ValueError):
                    geometry.prepare_pair_geometry(design, request)

    def test_budgets_cancel_and_determinism(self):
        design, request = self.fixture()
        baseline = geometry.prepare_pair_geometry(design, request)
        design.tracks.reverse()
        # Source design digest deliberately binds ordering; geometric partition order is stable.
        again = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(baseline["track_partitions"], again["track_partitions"])
        with self.assertRaisesRegex(ValueError, "cancelled"):
            geometry.prepare_pair_geometry(design, request, cancel_check=lambda: True)
        for name in ("MAX_SOURCES", "MAX_PAIR_COMPARISONS", "MAX_PARTITIONS", "MAX_CANDIDATES", "MAX_OUTPUT_BYTES"):
            with self.subTest(name=name), patch.object(geometry, name, 0):
                with self.assertRaisesRegex(ValueError, "budget"):
                    geometry.prepare_pair_geometry(design, request)

    def test_rigid_coordinate_change_and_unit_scaling(self):
        design, request = self.fixture()
        original = geometry.prepare_pair_geometry(design, request)
        for track in design.tracks:
            track.start_mm = (-track.start_mm[1] + 32, track.start_mm[0] - 16)
            track.end_mm = (-track.end_mm[1] + 32, track.end_mm[0] - 16)
        rotated = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(original["track_partitions"], rotated["track_partitions"])
        for track in design.tracks:
            track.start_mm = tuple(value * 2 for value in track.start_mm)
            track.end_mm = tuple(value * 2 for value in track.end_mm)
            track.width_mm *= 2
        scaled = geometry.prepare_pair_geometry(design, request)
        self.assertEqual(scaled["routes"]["signal"]["straight_centerline_length_mm"], 100)
        self.check_coverage(design, scaled)

    def test_layer_change_retains_complete_via_span(self):
        design, request = self.fixture()
        a = design.tracks[0]
        a.end_mm = (25, 0)
        design.vias.append(Via(id="via", net_id=a.net_id, center_mm=(25, 0),
                              start_layer_id=a.layer_id, end_layer_id="layer-reference", diameter_mm=0.6, drill_mm=0.3))
        design.tracks.append(Track(id="bottom", net_id=a.net_id, layer_id="layer-reference",
                                  start_mm=(25, 0), end_mm=(50, 0), width_mm=a.width_mm))
        result = geometry.prepare_pair_geometry(design, request)
        self.check_coverage(design, result)
        route = result["routes"]["signal"]
        self.assertEqual(route["topology"]["status"], "open_endpoint_chain")
        self.assertEqual(len(route["topology"]["ordered_edges"]), 3)
        self.assertGreater(route["via_axial_span_mm"], 0)
        self.assertEqual([p["status"] for p in result["track_partitions"] if p["track_id"] == "bottom"], ["unpaired"])


if __name__ == "__main__":
    unittest.main()
