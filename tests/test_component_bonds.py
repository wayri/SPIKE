"""Regression tests for the bounded component-bond core contract."""

from __future__ import annotations

import unittest

from python.spike_core.component_bonds import (
    COMPONENT_BONDS_CONTRACT,
    DEFAULT_SEARCH_DISTANCE_MM,
    bond_defaults,
    define_component_bond,
    infer_component_bonds,
)


class ComponentBondTests(unittest.TestCase):
    def test_infers_nearest_same_net_copper_on_each_side_deterministically(self) -> None:
        pins = [{"id": "U1.1", "x": 0, "y": 0, "net": "VCC"}]
        pads = [
            {"id": "pad-z", "x": 0.1, "y": 0, "net": "VCC"},
            {"id": "pad-a", "x": -0.1, "y": 0, "net": "VCC"},
        ]
        copper = [
            {"id": "b", "x": -0.1, "y": 0.1, "net": "VCC", "layer": "B.Cu"},
            {"id": "a", "x": -0.1, "y": 0.1, "net": "VCC", "layer": "F.Cu"},
        ]

        result = infer_component_bonds(pins, pads, copper)

        self.assertEqual(result["contract"], COMPONENT_BONDS_CONTRACT)
        self.assertEqual(result["status"], "ready")
        self.assertEqual([(bond["pad_id"], bond["copper_id"], bond["side"]) for bond in result["bonds"]], [("pad-a", "a", "top"), ("pad-a", "b", "bottom")])
        self.assertEqual(result["search_distance_mm"], DEFAULT_SEARCH_DISTANCE_MM)
        self.assertEqual(result["bonds"][0]["solder"]["electrical_resistance_ohm"], 0.001)

    def test_nearby_other_net_is_warning_not_connection(self) -> None:
        result = infer_component_bonds(
            [{"id": "U1.2", "x": 1, "y": 1, "net_name": "GND"}],
            [{"id": "pad-vcc", "x": 1.05, "y": 1, "net": "VCC"}],
        )

        self.assertEqual(result["status"], "unresolved")
        self.assertEqual(result["bonds"][0]["status"], "net_mismatch")
        self.assertIsNone(result["bonds"][0]["pad_id"])
        self.assertEqual(result["warnings"][0]["code"], "net_mismatch")

    def test_explicit_bond_rejects_cross_net_connection(self) -> None:
        with self.assertRaisesRegex(ValueError, "across nets"):
            define_component_bond(
                {"id": "U1.1", "x": 0, "y": 0, "net": "VCC"},
                {"id": "P1", "x": 0, "y": 0, "net": "GND"},
            )

    def test_configuration_and_solder_defaults_are_bounded_and_validated(self) -> None:
        result = infer_component_bonds(
            [], [], config={"search_distance_mm": 0.75, "solder": {"thermal_resistance_k_per_w": 10}},
        )
        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["solder_defaults"]["thermal_resistance_k_per_w"], 10.0)
        self.assertEqual(bond_defaults()["thermal_conductance_w_per_k"], 0.05)
        with self.assertRaisesRegex(ValueError, "<= 10.0 mm"):
            infer_component_bonds([], [], config={"search_distance_mm": 10.1})
        with self.assertRaisesRegex(ValueError, "Unknown solder property"):
            bond_defaults({"magic": 1})


if __name__ == "__main__":
    unittest.main()
