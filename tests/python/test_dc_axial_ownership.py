# SPDX-License-Identifier: Apache-2.0
"""Independent cylindrical integration and explicit stack-ownership controls."""
from copy import deepcopy
import json
import math
import unittest

import numpy as np

from python.spike_core.dc_axial_ownership import (
    REQUEST, AxialOwnershipError, compile_axial_ownership, make_gap_branches,
)
from python.spike_core.hybrid_mesh import HybridMesh


def explicit_stack():
    """Authored three-land stack; two gaps share one land without duplicating it."""
    lands = [{"id": name, "layer": layer, "node": node,
              "z_min_mm": z - .05, "z_max_mm": z + .05,
              "outer_radius_mm": .4, "conductivity_s_m": 5.8e7}
             for name, layer, node, z in (("bottom", "B.Cu", 5, 0.),
                                         ("middle", "In1.Cu", 9, 1.),
                                         ("top", "F.Cu", 17, 2.))]
    segments = []
    for index, (source, target) in enumerate(zip(lands, lands[1:])):
        name = "barrel" + str(index)
        def contact(land, side):
            return {"id": name + side, "land_id": land["id"], "node": land["node"],
                    "inner_radius_mm": .15, "outer_radius_mm": .175}
        segments.append({"id": name, "kind": "via", "source_land": source["id"],
            "target_land": target["id"], "start_z_mm": float(index), "end_z_mm": float(index + 1),
            "outer_radius_mm": .175, "conductivity_s_m": 5.8e7, "current_a": float(index + 2),
            "source_contact": contact(source, "-source"), "target_contact": contact(target, "-target")})
    return {"contract": REQUEST, "center_xy_mm": [3., -2.], "net": "N",
            "bore_radius_mm": .15, "lands": lands, "segments": segments}


class AxialOwnershipTests(unittest.TestCase):
    def test_independent_cylinder_integration_and_signed_face_current(self):
        report = compile_axial_ownership(explicit_stack())
        radial, wr = np.polynomial.legendre.leggauss(4)
        angular, wt = np.polynomial.legendre.leggauss(3)
        axial, wz = np.polynomial.legendre.leggauss(2)
        for row in report["segments"]:
            # Integrate in SI cylindrical coordinates, independently of the
            # helper's annular-area, mm conversions, and lumped R evaluation.
            ri, ro = row["inner_radius_mm"] * 1e-3, row["outer_radius_mm"] * 1e-3
            length = row["length_mm"] * 1e-3
            j = row["current_density_a_mm2"][2] * 1e6
            volume, heat, current = 0., 0., 0.
            for nr, rw in zip(radial, wr):
                radius = (ri + ro) / 2 + nr * (ro - ri) / 2
                for _, tw in zip(angular, wt):
                    da = radius * rw * (ro - ri) / 2 * tw * math.pi
                    current += j * da
                    for _, zw in zip(axial, wz):
                        dv = da * zw * length / 2
                        volume += dv
                        heat += j * j / row["conductivity_s_m"] * dv
            self.assertAlmostEqual(volume * 1e9 / row["volume_mm3"], 1., places=14)
            self.assertAlmostEqual(heat / row["imposed_current_joule_heat_w"], 1., places=14)
            self.assertAlmostEqual(current / row["imposed_current_a"], 1., places=14)
            expected_r = length / (row["conductivity_s_m"] * math.pi * (ro * ro - ri * ri))
            self.assertAlmostEqual(row["gap_resistance_ohm"] / expected_r, 1., places=14)

    def test_shared_middle_land_counted_once_and_incidence_retained(self):
        out = compile_axial_ownership(explicit_stack())
        self.assertEqual(len(out["lands"]), 3)
        self.assertEqual(len(out["segments"]), 2)
        expected_land_volume = 3 * math.pi * (.4**2 - .15**2) * .1
        expected_gap_volume = 1.8 * math.pi * (.175**2 - .15**2)
        self.assertAlmostEqual(out["land_volume_mm3"], expected_land_volume)
        self.assertAlmostEqual(out["axial_gap_volume_mm3"], expected_gap_volume)
        self.assertEqual([land["net_current_to_barrels_a"] for land in out["lands"]], [2., 1., -3.])
        self.assertEqual(out["segments"][0]["end_mm"][2], .95)
        self.assertEqual(out["segments"][1]["start_mm"][2], 1.05)
        self.assertFalse(out["complete_physical_volume"])
        self.assertFalse(out["production_qualified"])
        self.assertIsNone(out["land_transition_heat_w"])
        self.assertEqual(out["land_transition_fields_status"], "unresolved")
        self.assertTrue(out["requires_resolve"])

    def test_order_independence_and_direction_reversal(self):
        raw = explicit_stack(); base = compile_axial_ownership(raw)
        reordered = deepcopy(raw); reordered["lands"].reverse(); reordered["segments"].reverse()
        again = compile_axial_ownership(reordered)
        self.assertEqual(base["segments"], again["segments"])
        self.assertEqual(base["lands"], again["lands"])
        reversed_raw = deepcopy(raw)
        for s in reversed_raw["segments"]:
            for a, b in (("source_land", "target_land"), ("start_z_mm", "end_z_mm"),
                         ("source_contact", "target_contact")):
                s[a], s[b] = s[b], s[a]
            s["current_a"] *= -1
        reverse = compile_axial_ownership(reversed_raw)
        self.assertEqual(base["lands"], reverse["lands"])
        for a, b in zip(base["segments"], reverse["segments"]):
            self.assertEqual(a["current_density_a_mm2"], b["current_density_a_mm2"])
            self.assertEqual(a["start_mm"], b["end_mm"])
            self.assertEqual(a["end_mm"], b["start_mm"])
            self.assertEqual(a["imposed_current_joule_heat_w"], b["imposed_current_joule_heat_w"])

    def test_current_sign_scaling_zero_and_conductivity(self):
        raw = explicit_stack(); base = compile_axial_ownership(raw)
        for factor in (0., -1., 4.):
            altered = deepcopy(raw)
            for s in altered["segments"]: s["current_a"] *= factor
            out = compile_axial_ownership(altered)
            for a, b in zip(base["segments"], out["segments"]):
                self.assertAlmostEqual(b["current_density_a_mm2"][2], factor * a["current_density_a_mm2"][2])
                self.assertAlmostEqual(b["imposed_current_joule_heat_w"], factor**2 * a["imposed_current_joule_heat_w"])
        altered = deepcopy(raw)
        for s in altered["segments"]: s["conductivity_s_m"] *= 2
        out = compile_axial_ownership(altered)
        self.assertAlmostEqual(out["axial_imposed_current_heat_w"] * 2, base["axial_imposed_current_heat_w"])
        self.assertEqual(out["axial_gap_volume_mm3"], base["axial_gap_volume_mm3"])

    def test_fresh_branch_adapter_keeps_node_identity_and_corrected_resistance(self):
        raw = explicit_stack(); before = deepcopy(raw)
        original_mesh = HybridMesh(); original_before = deepcopy(original_mesh)
        first, second = make_gap_branches(raw), make_gap_branches(raw)
        out = compile_axial_ownership(raw)
        self.assertEqual(raw, before); self.assertEqual(original_mesh, original_before)
        for branch, other, row in zip(first, second, out["segments"]):
            self.assertIsNot(branch, other)
            self.assertEqual((branch.node_p, branch.node_n), (row["node_p"], row["node_n"]))
            self.assertAlmostEqual(branch.resistance_ohm / row["gap_resistance_ohm"], 1., places=14)
            self.assertLess(branch.resistance_ohm, row["original_center_span_resistance_ohm"])
            self.assertTrue(row["requires_resolve"])
            self.assertEqual(branch.evidence_id, out["input_digest"])
        json.dumps(out, allow_nan=False)

    def test_face_contacts_cannot_be_resized_or_reassigned(self):
        for key, value in (("node", 17), ("node", True), ("land_id", "top"),
                           ("inner_radius_mm", .14), ("outer_radius_mm", .176)):
            raw = explicit_stack(); raw["segments"][0]["source_contact"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AxialOwnershipError):
                compile_axial_ownership(raw)
        raw = explicit_stack()
        raw["segments"][1]["source_contact"]["id"] = raw["segments"][0]["source_contact"]["id"]
        with self.assertRaisesRegex(AxialOwnershipError, "Duplicate face"):
            compile_axial_ownership(raw)

    def test_overlaps_missing_gaps_and_endpoint_overhangs_reject(self):
        changes = [lambda r: r["lands"][1].__setitem__("z_min_mm", .04),
            lambda r: r["lands"][1].__setitem__("z_min_mm", .05),
            lambda r: r["segments"].pop(),
            lambda r: r["segments"][1].update(source_land="bottom", target_land="middle"),
            lambda r: r["segments"][0].__setitem__("target_land", "top"),
            lambda r: r["segments"][0].__setitem__("start_z_mm", .01),
            lambda r: r["segments"][0].__setitem__("end_z_mm", 1.01),
            lambda r: r["lands"][0].__setitem__("outer_radius_mm", .16)]
        for mutate in changes:
            raw = explicit_stack(); mutate(raw)
            with self.assertRaises(AxialOwnershipError): compile_axial_ownership(raw)

    def test_strict_schema_finite_inputs_bounds_and_representability(self):
        changes = [lambda r: r.__setitem__("extra", True),
            lambda r: r.__setitem__("contract", "unsupported"),
            lambda r: r.__setitem__("bore_radius_mm", 0.),
            lambda r: r.__setitem__("center_xy_mm", [0., float("nan")]),
            lambda r: r["lands"][0].__setitem__("node", True),
            lambda r: r["lands"][0].__setitem__("node", 9),
            lambda r: r["lands"][0].__setitem__("layer", "In1.Cu"),
            lambda r: r["segments"][0].__setitem__("kind", "source_contact"),
            lambda r: r["segments"][0].__setitem__("conductivity_s_m", 0.),
            lambda r: r["segments"][0].__setitem__("current_a", float("inf")),
            lambda r: r["segments"][0].__setitem__("current_a", 1e-300),
            lambda r: r["segments"][0].__setitem__("outer_radius_mm", .15)]
        for mutate in changes:
            raw = explicit_stack(); mutate(raw)
            with self.assertRaises(AxialOwnershipError): compile_axial_ownership(raw)
        raw = explicit_stack(); raw["lands"] *= 100
        with self.assertRaisesRegex(AxialOwnershipError, "2..256"): compile_axial_ownership(raw)


if __name__ == "__main__":
    unittest.main()
