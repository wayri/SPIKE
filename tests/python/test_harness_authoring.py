import copy
import math
import unittest

from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.design_ir_v2 import AssemblyIRV1
from python.spike_core.harness_authoring import plan_harnesses
from python.spike_core.harness_routing import route_cable
from python.spike_core.service_assembly_handlers import handle_assembly_request


def fixture():
    transform = list(IDENTITY)
    transform[3] = 100
    assembly = {"assembly_id": "test", "name": "Test", "boards": [
        {"id": "a", "design_id": "d", "frame": {"frame_id": "af", "transform": IDENTITY}},
        {"id": "b", "design_id": "d", "frame": {"frame_id": "bf", "transform": transform}},
    ], "connector_mappings": [
        {"id": "ca", "data": {"board_id": "a", "connector_id": "J1", "position_mm": [0, 0, 0], "pins": {"1": "SIGNAL", "2": "GND"}}},
        {"id": "cb", "data": {"board_id": "b", "connector_id": "J2", "position_mm": [0, 0, 0], "pins": {"5": "SIGNAL", "6": "GND"}}},
    ]}
    return {"assembly": assembly, "designs": {}}


class HarnessAuthoringTests(unittest.TestCase):
    def test_automatic_matching_and_cut_list(self):
        request = fixture()
        before = copy.deepcopy(request)
        plan = plan_harnesses(request)
        self.assertEqual(request, before)
        self.assertEqual(len(plan["harnesses"]), 1)
        harness = plan["harnesses"][0]
        self.assertEqual(harness["pin_map"], {"1": "5", "2": "6"})
        self.assertAlmostEqual(harness["length_mm"], 130)
        self.assertAlmostEqual(plan["total_wire_length_mm"], 260)
        self.assertEqual(plan["harnesses"], plan_harnesses(request)["harnesses"])
        self.assertFalse(plan["solver_ready"])

    def test_ambiguous_net_and_explicit_override(self):
        request = fixture()
        request["assembly"]["connector_mappings"][0]["data"]["pins"]["3"] = "GND"
        plan = plan_harnesses(request)
        self.assertEqual(plan["harnesses"][0]["pin_map"], {"1": "5"})
        self.assertTrue(plan["diagnostics"])
        request["pairs"] = [{"endpoint_a": "a::J1", "endpoint_b": "b::J2", "pin_map": {"3": "6"}}]
        self.assertEqual(plan_harnesses(request)["harnesses"][0]["pin_map"], {"3": "6"})

    def test_no_reuse_of_assigned_pins(self):
        request = fixture()
        request["assembly"]["harnesses"] = plan_harnesses(request)["harnesses"]
        self.assertFalse(plan_harnesses(request)["harnesses"])
        request["pairs"] = [{"endpoint_a": "a::J1", "endpoint_b": "b::J2", "pin_map": {"1": "5"}}]
        with self.assertRaisesRegex(ValueError, "already assigned"):
            plan_harnesses(request)

    def test_unknown_and_duplicate_target_pins_rejected(self):
        for pins in ({"99": "5"}, {"1": "5", "2": "5"}):
            request = fixture()
            request["pairs"] = [{"endpoint_a": "a::J1", "endpoint_b": "b::J2", "pin_map": pins}]
            with self.assertRaises(ValueError): plan_harnesses(request)

    def test_keepout_detour_and_waypoint_length(self):
        box = {"min_mm": [40, -10, -10], "max_mm": [60, 10, 10]}
        routed = route_cable([0, 0, 0], [100, 0, 0], [box], 2)
        self.assertAlmostEqual(routed["routed_length_mm"], 124)
        self.assertTrue(any(abs(p[1]) >= 12 or abs(p[2]) >= 12 for p in routed["route_mm"]))
        self.assertAlmostEqual(route_cable([0, 0, 0], [100, 0, 0], waypoints=[[0, 50, 0]])["routed_length_mm"], 200)
        with self.assertRaisesRegex(ValueError, "inside"):
            route_cable([50, 0, 0], [100, 0, 0], [box])

    def test_connector_discovery_and_rotated_parent(self):
        request = fixture()
        request["assembly"]["connector_mappings"] = []
        request["designs"] = {"d": {"components": [{"id": "j", "reference": "J1", "position_mm": [2, 3]}], "nets": [{"id": "n", "name": "DATA"}], "pads": [{"component_id": "j", "pin_id": "1", "net_id": "n"}]}}
        plan = plan_harnesses(request)
        self.assertEqual(plan["connectors"]["b::J1"]["assembly_position_mm"], [102, 3, 0])
        transform = [0, -1, 0, 100, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        request["assembly"]["boards"][1]["frame"]["transform"] = transform
        self.assertEqual(plan_harnesses(request)["connectors"]["b::J1"]["assembly_position_mm"], [97, 2, 0])

    def test_nonfinite_rejected_and_worker_errors_structured(self):
        request = fixture()
        request["slack_percent"] = math.nan
        self.assertFalse(handle_assembly_request("plan_assembly_harnesses", {"request": request})["ok"])
        request = fixture()
        request["assembly"]["harnesses"] = [{"id": "bad", "endpoint_a": "a::J1", "endpoint_b": "b::J2", "length_mm": math.nan}]
        with self.assertRaises(ValueError): AssemblyIRV1.from_dict(request["assembly"])

    def test_canonical_pin_ids_resolve_to_physical_numbers(self):
        request = fixture()
        request["assembly"]["connector_mappings"] = []
        request["designs"] = {"d": {"components": [{"id": "j", "reference": "J1", "position_mm": [2, 3]}],
            "pins": [{"id": "canonical-pin-uuid", "number": "7"}], "nets": [{"id": "n", "name": "DATA"}],
            "pads": [{"component_id": "j", "pin_id": "canonical-pin-uuid", "net_id": "n"}]}}
        self.assertEqual(plan_harnesses(request)["harnesses"][0]["pin_map"], {"7": "7"})


if __name__ == "__main__": unittest.main()
