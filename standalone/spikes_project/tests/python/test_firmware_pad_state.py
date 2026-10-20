# SPDX-License-Identifier: Apache-2.0
"""Register fixtures for pure STM32F407 and nRF52840 pad decoding."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))

from spikes_studio.firmware_pad_state import (  # noqa: E402
    UnsupportedPadConfiguration,
    decode_nrf,
    decode_stm32,
)


class Stm32F407PadStateTests(unittest.TestCase):
    def test_input_pull_and_exact_speed_metadata(self):
        pin = 3
        result = decode_stm32(
            0,
            1 << pin,
            1 << (pin * 2),
            2 << (pin * 2),
            1 << pin,
            pin,
        )
        self.assertTrue(result["input_enabled"])
        self.assertEqual(
            result["state"],
            {
                "mode": "input",
                "output": "released",
                "drive_level": "strong",
                "pull": "up",
            },
        )
        self.assertEqual(result["output_speed"], "fast")
        self.assertEqual(result["ospeedr"], 2)
        self.assertEqual(result["output_latch"], 1)
        self.assertEqual(result["drive_level_source"], "generic_profile_default")

    def test_push_pull_output_uses_odr(self):
        pin = 7
        registers = (1 << (pin * 2), 0, 2 << (pin * 2), 1 << (pin * 2))
        low = decode_stm32(*registers, 0, pin)
        high = decode_stm32(*registers, 1 << pin, pin)
        self.assertEqual(
            low["state"],
            {"mode": "push_pull", "output": "low", "drive_level": "strong", "pull": "down"},
        )
        self.assertEqual(
            high["state"],
            {"mode": "push_pull", "output": "high", "drive_level": "strong", "pull": "down"},
        )
        self.assertEqual(low["output_speed"], "medium")

    def test_open_drain_low_and_release(self):
        pin = 11
        mode = 1 << (pin * 2)
        otype = 1 << pin
        low = decode_stm32(mode, otype, 0, 3 << (pin * 2), 0, pin)
        released = decode_stm32(mode, otype, 0, 3 << (pin * 2), 1 << pin, pin)
        self.assertEqual(
            low["state"],
            {"mode": "open_drain", "output": "low", "drive_level": "strong", "pull": "none"},
        )
        self.assertEqual(
            released["state"],
            {"mode": "open_drain", "output": "released", "drive_level": "strong", "pull": "none"},
        )
        self.assertEqual(released["output_speed"], "high")

    def test_af_analog_and_reserved_pull_fail_closed(self):
        pin = 2
        for mode_value, text in ((2, "alternate-function"), (3, "analog")):
            with self.subTest(mode=mode_value), self.assertRaisesRegex(
                UnsupportedPadConfiguration, text
            ):
                decode_stm32(mode_value << (pin * 2), 0, 0, 0, 0, pin)
        with self.assertRaisesRegex(UnsupportedPadConfiguration, "reserved"):
            decode_stm32(0, 0, 3 << (pin * 2), 0, 0, pin)

    def test_rejects_invalid_registers_pins_and_reserved_upper_bits(self):
        invalid_calls = (
            lambda: decode_stm32(-1, 0, 0, 0, 0, 0),
            lambda: decode_stm32(0, True, 0, 0, 0, 0),
            lambda: decode_stm32(0, 1 << 16, 0, 0, 0, 0),
            lambda: decode_stm32(0, 0, 0, 0, 1 << 16, 0),
            lambda: decode_stm32(0, 0, 0, 0, 0, 16),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()


class Nrf52840PadStateTests(unittest.TestCase):
    def test_all_drive_encodings_choose_the_driven_side_strength(self):
        expected = {
            0: (("push_pull", "low", "weak"), ("push_pull", "high", "weak")),
            1: (("push_pull", "low", "strong"), ("push_pull", "high", "weak")),
            2: (("push_pull", "low", "weak"), ("push_pull", "high", "strong")),
            3: (("push_pull", "low", "strong"), ("push_pull", "high", "strong")),
            4: (("open_source", "released", "weak"), ("open_source", "high", "weak")),
            5: (("open_source", "released", "strong"), ("open_source", "high", "strong")),
            6: (("open_drain", "low", "weak"), ("open_drain", "released", "weak")),
            7: (("open_drain", "low", "strong"), ("open_drain", "released", "strong")),
        }
        pin = 19
        for drive, outputs in expected.items():
            pin_cnf = 1 | (drive << 8)
            for latch, expected_fields in enumerate(outputs):
                with self.subTest(drive=drive, latch=latch):
                    result = decode_nrf(pin_cnf, latch << pin, pin)
                    self.assertEqual(
                        (
                            result["state"]["mode"],
                            result["state"]["output"],
                            result["state"]["drive_level"],
                        ),
                        expected_fields,
                    )
                    self.assertEqual(result["drive"], drive)

    def test_input_buffer_disconnect_pull_and_sense_are_preserved(self):
        # DIR=input, INPUT=disconnect, PULL=up, DRIVE=S0H1, SENSE=low.
        pin_cnf = (1 << 1) | (3 << 2) | (2 << 8) | (3 << 16)
        result = decode_nrf(pin_cnf, 1 << 31, 31)
        self.assertFalse(result["input_enabled"])
        self.assertEqual(
            result["state"],
            {"mode": "input", "output": "released", "drive_level": "strong", "pull": "up"},
        )
        self.assertEqual(result["input_buffer"], "disconnected")
        self.assertEqual(result["drive_name"], "S0H1")
        self.assertEqual(result["sense_name"], "low")

    def test_pull_down_and_connected_input(self):
        result = decode_nrf(1 << 2, 0, 0)
        self.assertTrue(result["input_enabled"])
        self.assertEqual(
            result["state"],
            {"mode": "input", "output": "released", "drive_level": "weak", "pull": "down"},
        )

    def test_reserved_configurations_fail_closed(self):
        invalid = (
            (2 << 2, "PULL"),
            (1 << 16, "SENSE"),
            (1 << 4, "reserved bits"),
        )
        for pin_cnf, text in invalid:
            with self.subTest(pin_cnf=pin_cnf), self.assertRaisesRegex(
                UnsupportedPadConfiguration, text
            ):
                decode_nrf(pin_cnf, 0, 0)

    def test_rejects_invalid_values_and_pin(self):
        invalid_calls = (
            lambda: decode_nrf(-1, 0, 0),
            lambda: decode_nrf(0, 0x1_0000_0000, 0),
            lambda: decode_nrf(0, False, 0),
            lambda: decode_nrf(0, 0, 32),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
