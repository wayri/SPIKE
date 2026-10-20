# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from python.spike_core.dc_annular_source import (
    bind_annular_pad_source, solve_source_annular_stack, verify_annular_pad_binding,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "dc_annular_source.kicad_pcb"
PAD_UUID = "b6805fb9-ea4f-456f-a1b1-2ca414521568"


def source_hash(path=FIXTURE):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_stack(path=FIXTURE):
    """Two source-bound lands with explicit finite contacts and barrel gap."""
    path = Path(path)
    sha = source_hash(path)
    sigma = 5.8e7
    lower_binding = bind_annular_pad_source(path, sha, PAD_UUID, "B.Cu", [0., .1], sigma)
    upper_binding = bind_annular_pad_source(path, sha, PAD_UUID, "F.Cu", [1., 1.1], sigma)
    lands = [
        {"id": "lower", "layer": "B.Cu", "node": 1, "z_min_mm": 0., "z_max_mm": .1,
         "outer_radius_mm": .4, "conductivity_s_m": sigma},
        {"id": "upper", "layer": "F.Cu", "node": 2, "z_min_mm": 1., "z_max_mm": 1.1,
         "outer_radius_mm": .4, "conductivity_s_m": sigma},
    ]
    def support(land_id, node, identity):
        return {"id": identity, "land_id": land_id, "node": node,
                "inner_radius_mm": .15, "outer_radius_mm": .2}
    segment = {"id": "barrel", "kind": "via", "source_land": "lower", "target_land": "upper",
               "start_z_mm": .05, "end_z_mm": 1.05, "outer_radius_mm": .2,
               "conductivity_s_m": sigma, "current_a": 0.,
               "source_contact": support("lower", 1, "barrel-source"),
               "target_contact": support("upper", 2, "barrel-target")}
    ownership = {"contract": "spike/dc-axial-ownership-request/v1", "center_xy_mm": [10., 20.],
                 "net": "STACK", "bore_radius_mm": .15, "lands": lands, "segments": [segment]}
    def contact(identity, face, interval):
        return {"id": identity, "attachment_id": identity, "face": face,
                "interval_mm": interval, "current_a": 0.}
    requests = [
        {"land_id": "lower", "source_binding": lower_binding, "request": {
            "contract": "spike/dc-annular-land-request/v1", "conductivity_s_m": sigma,
            "radial_planes_mm": [.15, .2, .25, .4], "axial_planes_mm": [0., .05, .1],
            "contacts": [contact("drive", "z_min", [.25, .4]),
                         contact("barrel-source", "z_max", [.15, .2])]}},
        {"land_id": "upper", "source_binding": upper_binding, "request": {
            "contract": "spike/dc-annular-land-request/v1", "conductivity_s_m": sigma,
            "radial_planes_mm": [.15, .2, .25, .4], "axial_planes_mm": [1., 1.05, 1.1],
            "contacts": [contact("barrel-target", "z_min", [.15, .2]),
                         contact("return", "z_max", [.25, .4])]}},
    ]
    return {"contract": "spike/dc-annular-stack-request/v1", "ownership": ownership,
            "lands": requests, "connections": [{"segment_id": "barrel",
                "source_contact_id": "barrel-source", "target_contact_id": "barrel-target"}],
            "resistors": [], "external_currents": {
                "lower": {"drive": 1., "barrel-source": 0.},
                "upper": {"barrel-target": 0., "return": -1.}}}


class AnnularSourceTests(unittest.TestCase):
    def copied(self, transform=lambda text: text):
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / FIXTURE.name
        path.write_text(transform(FIXTURE.read_text(encoding="utf-8")), encoding="utf-8")
        self.addCleanup(temporary.cleanup)
        return path

    def assert_rejected(self, transform, message):
        path = self.copied(transform)
        with self.assertRaisesRegex(ValueError, message):
            bind_annular_pad_source(path, source_hash(path), PAD_UUID, "F.Cu", [0., .1], 5.8e7)

    def test_exact_native_evidence_hash_and_no_mutation(self):
        before = FIXTURE.read_bytes()
        binding = bind_annular_pad_source(FIXTURE, source_hash(), PAD_UUID, "F.Cu", [1., 1.1], 5.8e7)
        self.assertEqual(FIXTURE.read_bytes(), before)
        self.assertEqual(binding["source_sha256"], source_hash())
        native = binding["native_pad_evidence"]
        self.assertEqual(native["native_uuid"], PAD_UUID)
        self.assertEqual(native["drill_offset_mm"], [0., 0.])
        self.assertEqual(native["remove_unused_layers"], "no")
        self.assertEqual(native["padstack_geometry"], "uniform_implicit")
        self.assertEqual((binding["bore_radius_mm"], binding["outer_radius_mm"]), (.15, .4))
        verify_annular_pad_binding(binding)

    def test_source_mutation_and_wrong_hash_fail_closed(self):
        path = self.copied()
        with self.assertRaisesRegex(ValueError, "hash differs"):
            bind_annular_pad_source(path, "0"*64, PAD_UUID, "F.Cu", [0., .1], 5.8e7)
        binding = bind_annular_pad_source(path, source_hash(path), PAD_UUID, "F.Cu", [0., .1], 5.8e7)
        path.write_text(path.read_text(encoding="utf-8")+"\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            verify_annular_pad_binding(binding)

    def test_native_offset_and_ambiguous_uuid_fail_closed(self):
        self.assert_rejected(lambda s: s.replace("(drill 0.3)", "(drill 0.3 (offset 0.01 0))"), "offset drills")
        self.assert_rejected(lambda s: s.replace("(drill 0.3)", "(drill 0.3 unknown_scalar)"),
                             "Unsupported native drill declaration")
        pad = '''\n    (pad "2" thru_hole circle (at 1 0) (size 0.8 0.8) (drill 0.3)
      (layers "*.Cu" "*.Mask") (net 1 "STACK")
      (uuid "b6805fb9-ea4f-456f-a1b1-2ca414521568"))'''
        self.assert_rejected(lambda s: s.replace(")))\n  (gr_rect", "))"+pad+")\n  (gr_rect"),
                             "Select one exact source pad ID|missing or ambiguous")

    def test_np_thru_hole_shape_net_and_layer_reject(self):
        self.assert_rejected(lambda s: s.replace("thru_hole circle", "np_thru_hole circle"), "plated through-hole")
        self.assert_rejected(lambda s: s.replace("thru_hole circle", "thru_hole oval"), "circular land")
        self.assert_rejected(lambda s: s.replace('(net 1 "STACK")\n      (pinfunction', '(net 1 "")\n      (pinfunction'), "net must be explicit")
        with self.assertRaisesRegex(ValueError, "no requested copper layer"):
            bind_annular_pad_source(FIXTURE, source_hash(), PAD_UUID, "In1.Cu", [0., .1], 5.8e7)

    def test_layer_removal_and_per_layer_padstack_reject(self):
        self.assert_rejected(lambda s: s.replace("(remove_unused_layers no)", "(remove_unused_layers yes)"),
                             "Unused-layer removal")
        self.assert_rejected(lambda s: s.replace("(remove_unused_layers no)",
            '(remove_unused_layers no)\n      (padstack (mode front_inner_back) (layer "B.Cu" (shape circle) (size 0.7 0.7)))'),
            "Per-layer native padstack")

    def test_authenticated_two_land_solve(self):
        request = source_stack()
        original = deepcopy(request)
        result = solve_source_annular_stack(request)
        self.assertEqual(request, original)
        self.assertTrue(result["source_files_revalidated"])
        physical = result["result"]
        self.assertGreater(physical["total_heat_w"], 0.)
        self.assertAlmostEqual(physical["source_work_w"], physical["total_heat_w"], delta=1e-12)
        self.assertEqual([row["current_a"] for row in physical["edges"]], [1.])


if __name__ == "__main__":
    unittest.main()
