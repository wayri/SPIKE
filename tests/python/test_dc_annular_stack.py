# SPDX-License-Identifier: Apache-2.0
"""Independent physical series/parallel and coupled annular field witnesses."""
from copy import deepcopy
import math
import unittest

import numpy as np

from python.spike_core.dc_annular_stack import solve_annular_stack
from python.spike_core.dc_annular_evidence import validate_annular_stack


def explicit_annular_stack(*, spreading=False, current=1.):
    """Three disjoint land slabs plus two gaps; ownership currents are unrelated."""
    bore, barrel, outer = .15, .175, .4 if spreading else .175
    lands = [{"id": name, "layer": layer, "node": node,
              "z_min_mm": z, "z_max_mm": z+.1, "outer_radius_mm": outer,
              "conductivity_s_m": 5.8e7}
             for name, layer, node, z in (("lower", "B.Cu", 11, 0.),
                                         ("center", "In1.Cu", 27, 1.),
                                         ("upper", "F.Cu", 56, 2.))]
    ownership = {"contract": "spike/dc-axial-ownership-request/v1", "center_xy_mm": [2., -3.],
                 "net": "explicit-net", "bore_radius_mm": bore, "lands": lands, "segments": []}
    requests = []
    for i, land in enumerate(lands):
        z0, z1 = land["z_min_mm"], land["z_max_mm"]
        low_id = "drive" if i == 0 else "gap"+str(i-1)+"-target"
        high_id = "return" if i == 2 else "gap"+str(i)+"-source"
        def patch(cid, face, interval):
            return {"id": cid, "attachment_id": cid, "face": face, "interval_mm": interval, "current_a": 0.}
        contacts = [patch(low_id, "z_min", [.25, outer] if spreading and i == 0 else [bore, barrel]),
                    patch(high_id, "z_max", [.25, outer] if spreading and i == 2 else [bore, barrel])]
        requests.append({"land_id": land["id"], "source_binding": None, "request": {
            "contract": "spike/dc-annular-land-request/v1", "conductivity_s_m": 5.8e7,
            "radial_planes_mm": [bore, barrel, .25, outer] if spreading else [bore, barrel],
            "axial_planes_mm": [z0, (z0+z1)/2, z1], "contacts": contacts}})
    connections = []
    for i in range(2):
        source, target = lands[i:i+2]; sid = "gap"+str(i)
        def support(land, suffix):
            return {"id": sid+suffix, "land_id": land["id"], "node": land["node"],
                    "inner_radius_mm": bore, "outer_radius_mm": barrel}
        ownership["segments"].append({"id": sid, "kind": "via", "source_land": source["id"],
            "target_land": target["id"], "start_z_mm": source["z_min_mm"]+.05,
            "end_z_mm": target["z_min_mm"]+.05, "outer_radius_mm": barrel,
            "conductivity_s_m": 5.8e7, "current_a": 7. if i == 0 else -11.,
            "source_contact": support(source, "-source"), "target_contact": support(target, "-target")})
        connections.append({"segment_id": sid, "source_contact_id": sid+"-source", "target_contact_id": sid+"-target"})
    external = {row["land_id"]: {p["id"]: 0. for p in row["request"]["contacts"]} for row in requests}
    external["lower"]["drive"] = current; external["upper"]["return"] = -current
    return {"contract": "spike/dc-annular-stack-request/v1", "ownership": ownership,
            "lands": requests, "connections": connections, "resistors": [], "external_currents": external}


def series_resistance():
    return .0021/(5.8e7*math.pi*((.175e-3)**2-(.15e-3)**2))


class AnnularStackTests(unittest.TestCase):
    def assert_balances(self, raw, result):
        validate_annular_stack(result)
        external = raw["external_currents"]
        nodes = {(row["land_id"], contact["id"]): [contact["inward_current_a"], voltage]
                 for row in result["lands"]
                 for contact, voltage in zip(row["field_result"]["contacts"], row["global_port_potentials_v"])}
        residual = {key: external[key[0]][key[1]]-state[0] for key, state in nodes.items()}
        for edge in result["edges"]:
            def key(endpoint):
                land = result["lands"][endpoint[0]]
                return land["land_id"], land["field_result"]["contacts"][endpoint[1]]["id"]
            p, n = key(edge["p"]), key(edge["n"])
            residual[p] -= edge["current_a"]; residual[n] += edge["current_a"]
            self.assertAlmostEqual(nodes[p][1]-nodes[n][1], edge["current_a"]*edge["resistance_ohm"], delta=1e-13)
            self.assertAlmostEqual(edge["heat_w"], edge["current_a"]**2*edge["resistance_ohm"], delta=1e-14)
        self.assertLess(max(abs(v) for v in residual.values()), 1e-10)
        work = math.fsum(external[key[0]][key[1]]*value[1] for key, value in nodes.items())
        self.assertAlmostEqual(result["total_heat_w"], work, delta=1e-13)
        for land in result["lands"]:
            field = land["field_result"]
            self.assertLess(abs(math.fsum(c["inward_current_a"] for c in field["contacts"])), 1e-12)
            self.assertAlmostEqual(math.fsum(c["joule_heat_w"] for c in field["cells"]), field["joule_heat_w"], delta=1e-15)

    def test_three_land_uniform_series_includes_slabs_and_gaps(self):
        raw = explicit_annular_stack(); before = deepcopy(raw)
        result = solve_annular_stack(raw)
        self.assertEqual(raw, before)
        self.assertAlmostEqual(result["total_heat_w"]/series_resistance(), 1., delta=2e-10)
        self.assertAlmostEqual(result["land_heat_w"]/result["total_heat_w"], .3/2.1, delta=2e-10)
        self.assertAlmostEqual(result["barrel_heat_w"]/result["total_heat_w"], 1.8/2.1, delta=2e-10)
        for edge in result["edges"]:
            self.assertAlmostEqual(edge["current_a"], 1., delta=1e-12)
            self.assertNotIn("current_density_a_mm2", edge["geometry"])
            self.assertNotIn("imposed_current_joule_heat_w", edge["geometry"])
            density = edge["current_density_a_m2"][2]
            independent_heat = density**2/5.8e7*edge["volume_m3"]
            self.assertAlmostEqual(edge["heat_w"], independent_heat, delta=1e-15)
        self.assertFalse(result["ownership_currents_reused"])
        self.assertFalse(result["complete_board_physical_volume"])
        self.assert_balances(raw, result)

    def test_parallel_resistor_current_split_and_work(self):
        raw = explicit_annular_stack()
        raw["resistors"] = [{"id": "shunt", "p": {"land_id": "lower", "contact_id": "drive"},
                             "n": {"land_id": "upper", "contact_id": "return"}, "resistance_ohm": series_resistance()}]
        result = solve_annular_stack(raw)
        self.assertAlmostEqual(result["total_heat_w"]/series_resistance(), .5, delta=2e-10)
        for edge in result["edges"]:
            self.assertAlmostEqual(edge["current_a"], .5, delta=1e-11)
        self.assertAlmostEqual(result["resistor_heat_w"]/series_resistance(), .25, delta=2e-10)
        self.assert_balances(raw, result)

    def test_spreading_finite_patches_actual_fresh_fields(self):
        raw = explicit_annular_stack(spreading=True)
        result = solve_annular_stack(raw)
        self.assert_balances(raw, result)
        self.assertGreater(result["land_heat_w"], 0.)
        self.assertTrue(any(abs(c["center_density_rz_a_m2"][0]) > 1e3
                            for land in result["lands"] for c in land["field_result"]["cells"]))
        for land in result["lands"]:
            self.assertAlmostEqual(abs(land["field_result"]["contacts"][0]["inward_current_a"]), 1., delta=1e-12)
        changed = deepcopy(raw)
        for segment in changed["ownership"]["segments"]:
            segment["current_a"] *= -13.
        again = solve_annular_stack(changed)
        self.assertEqual(result["total_heat_w"], again["total_heat_w"])

    def test_scaling_zero_and_all_record_reordering(self):
        for current in (0., -2.5):
            raw = explicit_annular_stack(current=current)
            raw["lands"].reverse(); raw["connections"].reverse()
            raw["ownership"]["lands"].reverse(); raw["ownership"]["segments"].reverse()
            for land in raw["lands"]:
                land["request"]["contacts"].reverse()
            result = solve_annular_stack(raw)
            self.assertAlmostEqual(result["total_heat_w"], current**2*series_resistance(), delta=1e-13)
            self.assert_balances(raw, result)

    def test_multiport_spreading_uses_independent_unit_responses(self):
        raw = explicit_annular_stack(spreading=True)
        lower = raw["lands"][0]["request"]
        lower["contacts"].append({"id": "side", "attachment_id": "side", "face": "r_max",
                                  "interval_mm": [0., .1], "current_a": 0.})
        raw["external_currents"]["lower"]["side"] = .25
        raw["external_currents"]["upper"]["return"] = -1.25
        result = solve_annular_stack(raw)
        self.assert_balances(raw, result)
        self.assertEqual(len(result["response_field_results"][0]), 2)
        for edge in result["edges"]:
            self.assertAlmostEqual(edge["current_a"], 1.25, delta=1e-11)
        reduced = np.asarray(result["reduced_responses_ohm"][0])
        for p, field in enumerate(result["response_field_results"][0]):
            currents = [c["inward_current_a"] for c in field["contacts"]]
            self.assertEqual(currents, [1. if j == p else -1. if j == 2 else 0. for j in range(3)])
            voltage = np.array([c["mean_potential_v"] for c in field["contacts"]])
            np.testing.assert_allclose(voltage[:-1]-voltage[-1], reduced[:, p], rtol=0, atol=0)

    def test_reversed_barrel_orientation_preserves_physical_density(self):
        raw = explicit_annular_stack()
        for segment in raw["ownership"]["segments"]:
            for a, b in (("source_land", "target_land"), ("start_z_mm", "end_z_mm"), ("source_contact", "target_contact")):
                segment[a], segment[b] = segment[b], segment[a]
        for connection in raw["connections"]:
            connection["source_contact_id"], connection["target_contact_id"] = connection["target_contact_id"], connection["source_contact_id"]
        result = solve_annular_stack(raw)
        self.assert_balances(raw, result)
        expected_j = 1./(math.pi*((.175e-3)**2-(.15e-3)**2))
        for edge in result["edges"]:
            self.assertAlmostEqual(edge["current_a"], -1., delta=1e-11)
            self.assertAlmostEqual(edge["current_density_a_m2"][2]/expected_j, 1., delta=1e-11)

    def test_mismatches_and_cancellation_reject(self):
        bad = []
        raw = explicit_annular_stack(); raw["lands"][0]["request"]["conductivity_s_m"] *= 2; bad.append(raw)
        raw = explicit_annular_stack(); raw["lands"][0]["request"]["contacts"][1]["face"] = "r_max"
        raw["lands"][0]["request"]["contacts"][1]["interval_mm"] = [0., .1]; bad.append(raw)
        raw = explicit_annular_stack(); raw["connections"][0]["source_contact_id"] = "drive"; bad.append(raw)
        raw = explicit_annular_stack(); raw["lands"][0]["request"]["contacts"][0]["current_a"] = 1.; bad.append(raw)
        raw = explicit_annular_stack(); raw["external_currents"]["lower"]["drive"] = 2.; bad.append(raw)
        for raw in bad:
            with self.assertRaises(ValueError):
                solve_annular_stack(raw)
        with self.assertRaisesRegex(ValueError, "cancelled"):
            solve_annular_stack(explicit_annular_stack(), cancelled=lambda: True)
        checks = []
        def cancel_after_response():
            checks.append(1)
            return len(checks) == 4
        with self.assertRaisesRegex(ValueError, "cancelled"):
            solve_annular_stack(explicit_annular_stack(), cancelled=cancel_after_response)


if __name__ == "__main__":
    unittest.main()
