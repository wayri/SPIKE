# SPDX-License-Identifier: Apache-2.0
"""Inert settings and opt-in real-wx electrical-pad property tests."""
from copy import deepcopy
import math
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))

from spikes_studio.controller_boards import get_record
from spikes_studio.firmware_pad_settings import (
    GENERIC_WARNING, connections, default_settings, enabled_connections, gpio_pins,
    resolve_pad_state, settings_by_prefix, validate, validate_settings,
)
from python.spikes.native_io_pad import PadState

NRF = "nordic-nrf52840-dk-pca10056-r3-0-2"
STM = "st-stm32f407g-disc1-mb997"


class FirmwarePadSettingsTests(unittest.TestCase):
    def setUp(self):
        self.board = get_record(NRF)
        self.settings = default_settings(self.board)
        self.first = gpio_pins(self.board)[0]

    def enable_first(self):
        pin, _port, _index = self.first
        value = self.settings["pins"][pin["id"]]
        value.update(enabled=True, signal_node="button", vdd_node="vdd", vss_node="0")
        return pin, value

    def test_versioned_per_physical_pin_contract_and_connection(self):
        pin, value = self.enable_first()
        value["profile"]["high_strong_resistance_ohm"] = 33.
        saved = validate_settings(deepcopy(self.settings), self.board)
        self.assertEqual(validate(saved, self.board), saved)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["qualification"], "generic_unqualified")
        self.assertEqual(set(saved["pins"]), {p["id"] for p, _port, _index in gpio_pins(self.board)})
        connection, = enabled_connections(saved, self.board)
        self.assertEqual(connections(saved, self.board), (connection,))
        self.assertEqual(settings_by_prefix(saved, self.board)[connection.prefix], saved["pins"][pin["id"]])
        self.assertEqual((connection.port, connection.pin), self.first[1:])
        self.assertEqual((connection.node, connection.vdd, connection.vss), ("button", "vdd", "0"))
        self.assertEqual(connection.profile.high_strong_resistance_ohm, 33.)
        self.assertIn("Generic, unqualified", GENERIC_WARNING)

    def test_rejects_nonfinite_bounds_and_threshold_order(self):
        pin, value = self.enable_first()
        for field, bad in (("off_resistance_ohm", math.inf),
                           ("high_strong_resistance_ohm", 1e-9)):
            broken = deepcopy(self.settings); broken["pins"][pin["id"]]["profile"][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_settings(broken, self.board)
        value["vil_ratio"] = .8; value["vih_ratio"] = .7
        with self.assertRaisesRegex(ValueError, "VIL/VDD"):
            validate_settings(self.settings, self.board)

    def test_duplicate_header_alias_for_one_gpio_is_rejected(self):
        board = get_record(STM); settings = default_settings(board)
        groups = {}
        for pin, port, index in gpio_pins(board): groups.setdefault((port, index), []).append(pin)
        pair = next(group for group in groups.values() if len(group) > 1)
        for pin in pair[:2]:
            settings["pins"][pin["id"]].update(enabled=True, signal_node=pin["id"],
                                                  vdd_node="vdd", vss_node="0")
        with self.assertRaisesRegex(ValueError, "Only one physical header pin"):
            validate_settings(settings, board)

    def test_static_sources_are_explicit_circuit_only_overrides(self):
        _pin, value = self.enable_first()
        value["output_source"] = "static"; value["pull_source"] = "static"
        value["static_state"] = {"mode": "open_drain", "output": "low",
                                 "drive_level": "weak", "pull": "up"}
        state = resolve_pad_state(value, PadState("push_pull", "high", "strong", "down"))
        self.assertEqual(state, PadState("open_drain", "low", "weak", "up"))
        value["output_source"] = "firmware"
        state = resolve_pad_state(value, PadState("push_pull", "high", "strong", "down"))
        self.assertEqual(state, PadState("push_pull", "high", "strong", "up"))

    def test_unsupported_board_cannot_create_an_empty_pad_contract(self):
        unsupported = deepcopy(self.board); unsupported["id"] = "not-a-native-firmware-target"
        with self.assertRaisesRegex(ValueError, "admitted native firmware board"):
            default_settings(unsupported)


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "requires real wx runtime")
class FirmwarePadPropertiesDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx; cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        from spikes_studio.firmware_pad_properties import FirmwarePadPropertiesDialog
        self.board = get_record(NRF); self.frame = self.wx.Frame(None)
        self.dialog = FirmwarePadPropertiesDialog(self.frame, self.board, net_names=("0", "vdd", "signal"))

    def tearDown(self):
        self.dialog.Destroy(); self.frame.Destroy(); self.wx.Yield()

    def test_labeled_grouped_fields_and_readonly_gpio_mapping(self):
        labels = {child.GetLabel() for child in self.dialog.profile_panel.GetChildren()
                  if isinstance(child, self.wx.StaticText)}
        self.assertIn("High strong resistance", labels)
        self.assertIn("VIL / supply", labels)
        self.assertIn("Temperature", labels)
        self.assertTrue(self.dialog.grid.IsReadOnly(0, 1))
        self.assertTrue(self.dialog.grid.IsReadOnly(0, 2))
        self.assertTrue(self.dialog.selected_label.GetLabel())
        self.assertIsNone(self.dialog.result)

    def test_per_pin_profile_apply_validation_and_persistence(self):
        pin0 = self.dialog.pin_rows[0][0]; pin1 = self.dialog.pin_rows[1][0]
        self.dialog.fields["high_strong_resistance_ohm"].SetValue("33")
        self.dialog.select_pin(1)
        self.dialog.fields["high_strong_resistance_ohm"].SetValue("44")
        self.dialog.select_pin(0)
        self.assertEqual(self.dialog.fields["high_strong_resistance_ohm"].GetValue(), "33")
        self.dialog.grid.SetCellValue(0, 0, "1")
        self.dialog.grid.SetCellValue(0, 3, "signal")
        self.dialog.grid.SetCellValue(0, 4, "vdd")
        self.dialog.grid.SetCellValue(0, 5, "0")
        self.dialog.accept()
        saved = self.dialog.result
        self.assertIsNotNone(saved)
        self.assertEqual(saved["pins"][pin0["id"]]["profile"]["high_strong_resistance_ohm"], 33.)
        self.assertEqual(saved["pins"][pin1["id"]]["profile"]["high_strong_resistance_ohm"], 44.)
        second = type(self.dialog)(self.frame, self.board, saved)
        try:
            self.assertEqual(second.configuration(), saved)
            self.assertEqual(second.cancel_button.GetId(), self.wx.ID_CANCEL)
        finally: second.Destroy()

    def test_invalid_engineering_value_does_not_apply(self):
        self.dialog.fields["vil_ratio"].SetValue("800m")
        self.dialog.fields["vih_ratio"].SetValue("700m")
        self.dialog.accept()
        self.assertIsNone(self.dialog.result)
        self.assertIn("VIL/VDD", self.dialog.error.GetLabel())

    def test_modal_apply_and_cancel_return_codes(self):
        cancel = type(self.dialog)(self.frame, self.board)
        try:
            self.wx.CallAfter(cancel.EndModal, self.wx.ID_CANCEL)
            self.assertEqual(cancel.ShowModal(), self.wx.ID_CANCEL)
            self.assertIsNone(cancel.result)
        finally: cancel.Destroy()
        apply = type(self.dialog)(self.frame, self.board)
        try:
            self.wx.CallAfter(apply.accept)
            self.assertEqual(apply.ShowModal(), self.wx.ID_OK)
            self.assertEqual(apply.result, default_settings(self.board))
        finally: apply.Destroy()


if __name__ == "__main__": unittest.main()
