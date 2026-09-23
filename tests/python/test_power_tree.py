"""Focused regression tests for deterministic PI power-path extraction."""

from __future__ import annotations

import unittest

from python.spike_core.contracts import DesignIR
from python.spike_core.power_tree import POWER_PATH_CONTRACT, extract_power_path
from python.spike_core.service import handle


def power_path_fixture() -> DesignIR:
    return DesignIR(
        name="Power tree fixture",
        components=[
            {"id": "f1", "reference": "F1", "value": "5 A fuse"},
            {"id": "l1", "reference": "L1", "value": "2.2 uH"},
            {"id": "c1", "reference": "C1", "value": "22 uF"},
            {"id": "u1", "reference": "U1", "value": "Buck regulator"},
            {"id": "c2", "reference": "C2", "value": "47 uF"},
            {"id": "r1", "reference": "R1", "value": "100k"},
        ],
        pads=[
            {"id": "j1.1", "component": "J1", "name": "1", "net_name": "VIN"},
            {"id": "f1.1", "component": "F1", "name": "1", "net_name": "VIN"},
            {"id": "f1.2", "component": "F1", "name": "2", "net_name": "VIN_FUSED"},
            {"id": "l1.1", "component": "L1", "name": "1", "net_name": "VIN_FUSED"},
            {"id": "l1.2", "component": "L1", "name": "2", "net_name": "VIN_FILTERED"},
            {"id": "c1.1", "component": "C1", "name": "1", "net_name": "VIN_FILTERED"},
            {"id": "c1.2", "component": "C1", "name": "2", "net_name": "GND"},
            {"id": "u1.1", "component": "U1", "name": "VIN", "net_name": "VIN_FILTERED"},
            {"id": "u1.2", "component": "U1", "name": "VOUT", "net_name": "VOUT"},
            {"id": "u1.3", "component": "U1", "name": "GND", "net_name": "GND"},
            {"id": "c2.1", "component": "C2", "name": "1", "net_name": "VOUT"},
            {"id": "c2.2", "component": "C2", "name": "2", "net_name": "GND"},
            {"id": "r1.1", "component": "R1", "name": "1", "net_name": "VOUT"},
            {"id": "r1.2", "component": "R1", "name": "2", "net_name": "GND"},
            {"id": "j2.1", "component": "J2", "name": "1", "net_name": "VOUT"},
        ],
    )


class PowerTreeExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.design = power_path_fixture()

    def test_path_uses_only_non_ground_series_transitions_and_exposes_shunts(self) -> None:
        result = extract_power_path(self.design, {"pad_id": "j1.1"}, {"component_ref": "J2", "pad_name": "1"})

        self.assertEqual(result["contract"], POWER_PATH_CONTRACT)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["simulation_status"], "needs_model_assignment")
        self.assertEqual([item["component_ref"] for item in result["series_path"]], ["F1", "L1", "U1"])
        self.assertEqual(result["path_nets"], ["VIN", "VIN_FUSED", "VIN_FILTERED", "VOUT"])
        self.assertFalse(any(item["input_net"] == "GND" or item["output_net"] == "GND" for item in result["series_path"]))
        self.assertEqual([(item["component_ref"], item["rail_net"]) for item in result["shunt_elements"]], [("C1", "VIN_FILTERED"), ("C2", "VOUT"), ("R1", "VOUT"), ("U1", "VIN_FILTERED"), ("U1", "VOUT")])
        regulator = result["series_path"][-1]
        self.assertEqual(regulator["model_kind"], "integrated_circuit")
        self.assertTrue(regulator["requires_pin_model_assignment"])

    def test_result_is_deterministic_and_accepts_net_selectors(self) -> None:
        first = extract_power_path(self.design, "VIN", "VOUT")
        second = extract_power_path(self.design, "VIN", "VOUT")

        self.assertEqual(first, second)
        self.assertEqual([item["component_ref"] for item in first["series_path"]], ["F1", "L1", "U1"])

    def test_ground_cannot_be_used_as_series_shortcut(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-ground power terminals"):
            extract_power_path(self.design, "VIN", "GND")

    def test_disconnected_nets_return_no_path_without_inventing_a_route(self) -> None:
        result = extract_power_path(self.design, "VIN", "AUX_5V")

        self.assertEqual(result["status"], "no_path")
        self.assertEqual(result["simulation_status"], "no_path")
        self.assertEqual(result["series_path"], [])
        self.assertIn("No non-ground component path", result["warnings"][-1])

    def test_worker_exposes_the_backend_extractor(self) -> None:
        response = handle({
            "method": "extract_power_path",
            "params": {"design": self.design.to_dict(), "source": "j1.1", "sink": "j2.1"},
        })

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["status"], "ready")
        self.assertEqual(response["result"]["series_path"][0]["component_ref"], "F1")


if __name__ == "__main__":
    unittest.main()
