# SPDX-License-Identifier: Apache-2.0
"""Original metadata fixtures; no vendor model or numerical execution."""
import unittest

from python.spike_core.solvers.signal_integrity.receivers.si_ibis import parse_ibis, reduce_ibis


PREFIX = """[IBIS Ver] 8.0
[Component] Fixture
[Package]
R_pkg 0.1 0.05 0.2
L_pkg 1n 0.5n 2n
C_pkg 1p 0.5p 2p
"""
MODEL = """[Model] Receiver
Model_type Input
C_comp 1p 0.5p 2p
[End]
"""


class BehavioralInventoryTests(unittest.TestCase):
    def test_pin_header_reordering_preserves_physical_dimensions(self):
        text = PREFIX + "[Pin] signal_name model_name C_pin R_pin L_pin\n1 RX Receiver 3p 0.2 4n\n" + MODEL
        inventory = parse_ibis(text)
        self.assertEqual(inventory["components"]["Fixture"]["pins"][0]["rlc"], [0.2, 4e-9, 3e-12])
        values = reduce_ibis(inventory, {"model": "Receiver", "component": "Fixture", "pin": "1"}, "receiver")["values"]
        self.assertEqual(values["package_r_ohm"], 0.2)
        self.assertEqual(values["package_l_h"], 4e-9)
        self.assertEqual(values["package_c_f"], 3e-12)

    def test_na_and_absent_pin_parasitics_retain_package_fallback(self):
        for row in ("1 RX Receiver", "1 RX Receiver NA NA NA"):
            inventory = parse_ibis(PREFIX + "[Pin] signal_name model_name R_pin L_pin C_pin\n" + row + "\n" + MODEL)
            values = reduce_ibis(inventory, {"model": "Receiver", "component": "Fixture", "pin": "1"}, "receiver")["values"]
            self.assertEqual(values["package_r_ohm"], 0.1)
            self.assertEqual(values["package_l_h"], 1e-9)

    def test_malformed_pin_columns_and_duplicate_pins_are_rejected(self):
        for header, rows in (
            ("R_pin R_pin C_pin", "1 RX Receiver 1 2 3"),
            ("R_pin L_pin", "1 RX Receiver 1 2"),
            ("R_pin L_pin C_pin", "1 RX Receiver 1 2"),
            ("R_pin L_pin C_pin", "1 RX Receiver\n1 RX Receiver"),
        ):
            with self.subTest(header=header, rows=rows), self.assertRaises(ValueError):
                parse_ibis(PREFIX + "[Pin] signal_name model_name " + header + "\n" + rows + "\n" + MODEL)

    def test_explicit_references_are_retained_but_not_enabled_in_legacy_reduction(self):
        text = PREFIX + MODEL.replace("[End]", "[Pullup Reference] 1.8 1.7 1.9\n[Pulldown Reference] 0 0 0\n[Power Clamp Reference] 1.8 1.7 1.9\n[GND Clamp Reference] 0 0 0\n[End]")
        inventory = parse_ibis(text)
        self.assertEqual(inventory["models"]["Receiver"]["parameters"]["pullup_reference"], [1.8, 1.7, 1.9])
        with self.assertRaisesRegex(ValueError, "does not support"):
            reduce_ibis(inventory, {"model": "Receiver"}, "receiver")


if __name__ == "__main__":
    unittest.main()
