# SPDX-License-Identifier: Apache-2.0
"""Real-wx admission and full-package mapping checks for product discovery."""
from copy import deepcopy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "requires native wx")
class ManufacturerExecutableWxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        from spikes_studio.document import Document
        from spikes_studio import manufacturer_library_hub as hub
        from spikes_studio.themes import PALETTES

        self.hub = hub
        self.frame = self.wx.Frame(None)
        document = Document.from_netlist("Manufacturer executable UI\nVCC vp 0 5\n.op\n.end\n")
        self.status = []
        self.refreshes = []
        self.owner = SimpleNamespace(
            palette=PALETTES["Light"],
            guarded=lambda function: function(),
            doc=document,
            job_running=False,
            require_clean_directive_source=lambda: None,
            refresh_document=lambda: self.refreshes.append(True),
            SetStatusText=lambda value: self.status.append(value),
            book=SimpleNamespace(SetSelection=lambda _index: None),
            editor_page=lambda: 0,
        )
        self.panel = hub.ProductCatalog(self.frame, self.owner)

    def tearDown(self):
        self.panel.Destroy()
        self.frame.Destroy()
        self.wx.Yield()

    def select_identity(self, identity):
        row = next(item for item in self.panel.catalog["records"] if item["id"] == identity)
        self.panel.listing.set_rows([row])
        state = self.wx.LIST_STATE_SELECTED | self.wx.LIST_STATE_FOCUSED
        self.panel.listing.SetItemState(0, state, state)
        self.panel.select()
        return row

    def test_product_catalog_enables_only_the_reviewed_executable_tier(self):
        states = [self.panel.executable_state(row) for row in self.panel.catalog["records"]]
        self.assertEqual(len(states), 208)
        self.assertEqual(sum(state["executable"] for state in states), 5)
        self.assertEqual(sum(not state["executable"] for state in states), 203)
        self.select_identity("ti-lm358")
        self.assertTrue(self.panel.executable_button.IsEnabled())
        detail = self.panel.detail.GetValue()
        self.assertIn("Qualified: false", detail)
        self.assertIn("No slew-rate limiting", detail)
        self.assertIn("1=OUT_A", detail)
        self.assertIn("8=V_PLUS", detail)

        self.select_identity("adi-ad8221")
        self.assertFalse(self.panel.executable_button.IsEnabled())
        self.assertIn("No reviewed SPIKE executable approximation", self.panel.detail.GetValue())

        self.panel.execution.SetSelection(1)
        self.panel.refresh()
        self.assertEqual(len(self.panel.listing.rows), 5)
        self.assertEqual({row["id"] for row in self.panel.listing.rows}, self.panel.executable_ids)

        self.panel.execution.SetSelection(0)
        self.select_identity("ti-lm358")
        self.owner.job_running = True
        with self.assertRaisesRegex(ValueError, "Stop simulation"):
            self.panel._place_executable()

    def test_lm358_dialog_lists_all_numbered_package_pins(self):
        from spikes_studio.manufacturer_executable import executable_record, source_pins
        from spikes_studio.manufacturer_executable_dialog import ExecutablePlacementDialog

        record = executable_record("ti-lm358")
        dialog = ExecutablePlacementDialog(self.frame, self.owner, record)
        try:
            self.assertEqual(list(dialog.nodes), source_pins(record))
            self.assertEqual(len(dialog.nodes), 8)
            labels = [label.GetLabel() for label in dialog.pin_labels]
            for pin in record["pins"]:
                self.assertTrue(any(
                    f"Pin {pin['number']} · {pin['name']} ({pin['role']})" in label
                    for label in labels
                ))
        finally:
            dialog.Destroy()

    def test_product_action_retains_full_x_instance_and_renders_only_flattened_native_parts(self):
        row = self.select_identity("ti-lm358")
        before = deepcopy(self.owner.doc.data)
        mapping = {
            "OUT_A": "out_a", "IN_A_MINUS": "out_a", "IN_A_PLUS": "in_a", "V_MINUS": "0",
            "IN_B_PLUS": "in_b", "IN_B_MINUS": "out_b", "OUT_B": "out_b", "V_PLUS": "vp",
        }

        class FakeDialog:
            def __init__(dialog_self, _parent, _owner, record):
                self.assertEqual(record["discovery_id"], row["id"])
                dialog_self.count = SimpleNamespace(GetValue=lambda: 1)
            def __enter__(dialog_self): return dialog_self
            def __exit__(dialog_self, *args): return False
            def ShowModal(dialog_self): return self.wx.ID_OK
            def mapping(dialog_self): return mapping

        with patch.object(self.hub, "ExecutablePlacementDialog", FakeDialog):
            plan = self.panel._place_executable()

        line = next(item for item in self.owner.doc.data["source"].splitlines() if item.startswith("XMAN1 "))
        tokens = line.split()
        self.assertEqual(tokens[1:9], [mapping[name] for name in (
            "OUT_A", "IN_A_MINUS", "IN_A_PLUS", "V_MINUS",
            "IN_B_PLUS", "IN_B_MINUS", "OUT_B", "V_PLUS",
        )])
        self.assertEqual(len(tokens), 10)
        flattened = [part for part in self.owner.doc.data["components"] if part["ref"].startswith("XMAN1:")]
        self.assertTrue(flattened)
        self.assertFalse(any(part["ref"] == "XMAN1" for part in self.owner.doc.data["components"]))
        self.assertTrue(all(part["kind"] in {
            "resistor", "capacitor", "voltage_source", "diode", "vcvs",
        } for part in flattened))
        self.assertNotIn("manufacturer_package", self.owner.doc.data["metadata"])
        self.assertEqual(plan["refs"], ["XMAN1"])
        self.assertTrue(self.refreshes)
        self.assertIn("qualified=false", self.status[-1])
        self.owner.doc.undo()
        self.assertEqual(self.owner.doc.data, before)


if __name__ == "__main__":
    unittest.main()
