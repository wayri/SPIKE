# SPDX-License-Identifier: Apache-2.0
"""Focused persistence and inert-UI tests for firmware pin workflow glue."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "standalone/spikes_project/studio/python"))

from spikes_studio.controller_board_blocks import add, create, update
from spikes_studio.controller_boards import get_record
from spikes_studio.document import Document, RC_DECK
from spikes_studio.firmware_pad_settings import default_settings

NRF = "nordic-nrf52840-dk-pca10056-r3-0-2"


def placed_document():
    document = Document.from_netlist(RC_DECK)
    block = create(get_record(NRF), 40, 80)
    add(document, block)
    return document, deepcopy(document.data["controller_boards"][0])


def workflow_window(document, block):
    status = SimpleNamespace(value="")
    status.SetLabel = lambda value: setattr(status, "value", value)
    owner = SimpleNamespace(doc=document, job_running=False, refresh_document=Mock())
    return SimpleNamespace(owner=owner, block=deepcopy(block), busy=False, status=status)


class FirmwarePinDocumentWorkflowTests(unittest.TestCase):
    def test_save_reopen_preserves_mode_and_pads_as_one_undoable_change(self):
        from spikes_studio.firmware_pin_workflow import _save
        document, block = placed_document(); window = workflow_window(document, block)
        pads = default_settings(block["board"])
        before = deepcopy(document.data); undo_count = len(document.undo_stack)
        _save(window, firmware_coupling_mode="electrical", electrical_pads=pads)
        self.assertEqual(len(document.undo_stack), undo_count + 1)
        self.assertEqual(document.data["revision"], before["revision"] + 1)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            path = Path(folder) / "firmware-pins.spikes.json"
            document.save(path); reopened = Document.load(path)
        saved = reopened.data["controller_boards"][0]
        self.assertEqual(saved["firmware_coupling_mode"], "electrical")
        self.assertEqual(saved["electrical_pads"], pads)
        document.undo()
        self.assertEqual(document.data, before)

    def test_document_rejects_malformed_saved_pad_settings(self):
        document, block = placed_document(); pads = default_settings(block["board"])
        pin = next(iter(pads["pins"].values()))
        pin["vil_ratio"] = .9; pin["vih_ratio"] = .2
        broken = deepcopy(document.data)
        broken["controller_boards"][0]["electrical_pads"] = pads
        with self.assertRaisesRegex(ValueError, "VIL/VDD"):
            Document(broken)

    def test_cancelled_editor_does_not_mutate_document(self):
        from spikes_studio import firmware_pin_workflow as workflow
        document, block = placed_document(); window = workflow_window(document, block)
        before = deepcopy(document.data); undo_count = len(document.undo_stack)
        with patch("spikes_studio.firmware_pad_properties.show", return_value=None) as show:
            workflow.edit(window)
        show.assert_called_once()
        self.assertEqual(document.data, before)
        self.assertEqual(len(document.undo_stack), undo_count)

    def test_stale_board_snapshot_is_rejected_without_mutation(self):
        from spikes_studio.firmware_pin_workflow import _save
        document, stale = placed_document()
        replacement = deepcopy(stale); replacement["x"] += 10
        update(document, replacement["id"], replacement)
        window = workflow_window(document, stale)
        before = deepcopy(document.data); undo_count = len(document.undo_stack)
        with self.assertRaisesRegex(ValueError, "Board changed"):
            _save(window, firmware_coupling_mode="electrical")
        self.assertEqual(document.data, before)
        self.assertEqual(len(document.undo_stack), undo_count)

    def test_prepare_selects_legacy_electrical_and_timestamped_controllers(self):
        from spikes_studio import firmware_coupling
        # Import before mocking its base class; otherwise Python creates a
        # subclass of Mock on first lazy import and contaminates later tests.
        from spikes_studio import firmware_synchronous
        from spikes_studio import firmware_peripheral
        constructors = {name: Mock(name=name, return_value=name) for name in
                        ("legacy", "electrical", "timestamped", "synchronous", "peripheral")}
        with patch.object(firmware_coupling, "FirmwareController", constructors["legacy"]), \
             patch("spikes_studio.firmware_electrical.ElectricalFirmwareController",
                   constructors["electrical"]), \
             patch("spikes_studio.firmware_timestamped.TimestampedFirmwareController",
                   constructors["timestamped"]), \
             patch("spikes_studio.firmware_synchronous.SynchronousFirmwareController",
                   constructors["synchronous"]), \
             patch("spikes_studio.firmware_peripheral.PeripheralFirmwareController",constructors["peripheral"]):
            for mode in constructors:
                with self.subTest(mode=mode):
                    document, block = placed_document()
                    block["firmware_coupling_mode"] = mode
                    if mode != "legacy": block["electrical_pads"] = default_settings(block["board"])
                    document = Document({**document.data, "controller_boards": [block]})
                    owner = SimpleNamespace(doc=document, job_running=False)
                    captured = []
                    status = SimpleNamespace(SetLabel=lambda _value: None)
                    window = SimpleNamespace(
                        owner=owner, block=deepcopy(block), busy=False, running=False,
                        duration=SimpleNamespace(GetValue=lambda: "100u"), status=status,
                        attachment_context=lambda: {
                            "block": deepcopy(block), "firmware": {"path": "image.bin", "sha256": "a" * 64},
                            "approved": True, "target_id": NRF, "runtime_path": "Renode.exe",
                        },
                        _submit=lambda work, complete: captured.append(work),
                    )
                    firmware_coupling.run(owner, window)
                    self.assertEqual(len(captured), 1)
                    self.assertEqual(captured[0](), mode)
                    constructors[mode].assert_called_once()


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "requires real wx runtime")
class FirmwarePinRealWxWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx; cls.app = wx.GetApp() or wx.App(False)

    def test_mode_and_pin_buttons_are_inert_without_explicit_run(self):
        from spikes_studio import firmware_window
        document, block = placed_document()
        owner = self.wx.Frame(None); owner.doc = document; owner.job_running = False
        owner.refresh_document = Mock()
        session = Mock(side_effect=AssertionError("mode/property controls must not execute firmware"))
        with patch.object(firmware_window, "FirmwareSession", session), \
             patch.object(firmware_window, "find_runtime", return_value=None), \
             patch("spikes_studio.firmware_pad_properties.show", return_value=None) as show:
            window = firmware_window.FirmwareWindow(owner, block)
            try:
                window.coupling_mode.SetSelection(1)
                choice = self.wx.CommandEvent(self.wx.EVT_CHOICE.typeId, window.coupling_mode.GetId())
                choice.SetEventObject(window.coupling_mode)
                window.coupling_mode.GetEventHandler().ProcessEvent(choice)
                click = self.wx.CommandEvent(self.wx.EVT_BUTTON.typeId, window.pad_properties_button.GetId())
                click.SetEventObject(window.pad_properties_button)
                window.pad_properties_button.GetEventHandler().ProcessEvent(click)
                self.assertEqual(document.data["controller_boards"][0]["firmware_coupling_mode"], "electrical")
                show.assert_called_once(); session.assert_not_called()
                self.assertIsNone(window.session)
            finally:
                window.close(); owner.Destroy(); self.wx.Yield()


if __name__ == "__main__": unittest.main()
