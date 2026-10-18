# SPDX-License-Identifier: Apache-2.0
"""Focused opt-in wx checks for component-library discovery and recovery."""

import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "studio/python"))


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "set SPIKES_TEST_WX=1 for native wx controls")
class LibraryDiscoveryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx

        cls.wx = wx
        cls.app = wx.GetApp() or wx.App(False)

    def setUp(self):
        from spikes_studio.component_panel import ComponentPanel
        from spikes_studio.document import Document, RC_DECK
        from spikes_studio.themes import PALETTES

        wx = self.wx
        self.owner = wx.Frame(None, size=(1100, 760))
        self.host = wx.Panel(self.owner)
        self.owner.palette = PALETTES["Light"]
        self.owner.doc = Document.from_netlist(RC_DECK)
        self.owner.pin_browser = lambda: None
        self.owner.open_physics_models = lambda: None
        self.owner.guarded = lambda callback: callback()
        self.owner.update_title = lambda: None
        self.owner.assign_part_shortcut = lambda _ident: None
        self.panel = ComponentPanel(self.owner, self.host)
        host_box = wx.BoxSizer(wx.VERTICAL)
        host_box.Add(self.panel, 1, wx.EXPAND)
        self.host.SetSizer(host_box)
        owner_box = wx.BoxSizer(wx.VERTICAL)
        owner_box.Add(self.host, 1, wx.EXPAND)
        self.owner.SetSizer(owner_box)
        self.owner.Show()
        self.owner.Layout()
        wx.Yield()

    def tearDown(self):
        self.panel.Destroy()
        self.host.Destroy()
        self.owner.Destroy()
        self.wx.Yield()

    def select_first(self):
        self.panel.list.SetSelection(0)
        self.panel.select()
        self.assertIsNotNone(self.panel.record)

    def test_quick_collections_filter_and_empty_state_recovers(self):
        panel = self.panel
        panel.show_favorites()
        self.assertEqual(panel.visible, [])
        self.assertTrue(panel.empty_panel.IsShown())
        self.assertIn("No favorites yet", panel.empty_message.GetLabel())

        panel.reset_filters()
        self.assertGreater(len(panel.visible), 0)
        self.assertFalse(panel.empty_panel.IsShown())

        panel.circuit_ready()
        self.assertTrue(panel.visible)
        self.assertTrue(all(row["status"] == "native_subcircuit" for row in panel.visible))

        panel.show_recent()
        self.assertEqual(panel.visible, [])
        self.assertIn("No recent inserts", panel.empty_message.GetLabel())

    def test_selection_draft_and_reset_survive_discovery_changes(self):
        panel = self.panel
        panel.search.ChangeValue("id:generic.resistor.001")
        panel.filter()
        self.select_first()
        ident = panel.record["id"]
        original = panel.record["parameters"]["r"]
        panel.parameters.fields["r"].SetValue("4.7k")

        panel.sort.SetStringSelection("Family")
        panel.filter()
        self.assertEqual(panel.record["id"], ident)
        self.assertEqual(panel.parameters.fields["r"].GetValue(), "4.7k")

        panel.search.ChangeValue("definitely-no-such-component")
        panel.filter()
        self.assertIsNone(panel.record)
        panel.search.ChangeValue("id:" + ident)
        panel.filter()
        self.select_first()
        self.assertEqual(panel.parameters.fields["r"].GetValue(), "4.7k")

        panel.reset_draft()
        self.assertEqual(panel.edited()["parameters"]["r"], original)

    def test_advanced_disclosure_event_reflows_controls_above_results(self):
        wx = self.wx
        panel = self.panel
        self.owner.SetSize((1000, 720))
        self.owner.Layout()
        panel.advanced.Collapse(False)
        event = wx.CollapsiblePaneEvent(panel.advanced, panel.advanced.GetId(), False)
        panel.advanced.GetEventHandler().ProcessEvent(event)
        wx.Yield()

        pane = panel.advanced.GetPane()
        self.assertFalse(panel.advanced.IsCollapsed())
        self.assertTrue(pane.IsShownOnScreen())
        pane_rect = pane.GetScreenRect()
        for control in (panel.category, panel.status, panel.sort, panel.descending,
                        panel.unit, panel.minimum, panel.maximum,
                        panel.favorite_only, panel.recent_only):
            self.assertTrue(control.IsShownOnScreen(), control.GetName())
            self.assertTrue(pane_rect.Contains(control.GetScreenRect()), control.GetName())
        self.assertLessEqual(pane_rect.GetBottom(), panel.split.GetScreenRect().GetTop())
        self.assertLessEqual(pane_rect.height, 100)
        self.assertLessEqual(panel.split.GetScreenRect().GetTop() - pane_rect.GetBottom(), 12)

    def test_compact_pinned_layout_keeps_core_discovery_controls(self):
        panel = self.panel
        panel.set_compact(True)
        self.owner.SetSize((480, 720))
        self.owner.Layout()
        self.wx.Yield()

        self.assertFalse(panel.summary.IsShown())
        self.assertFalse(panel.advanced.IsShown())
        self.assertFalse(panel.tree.IsShown())
        self.assertTrue(panel.search.IsShownOnScreen())
        self.assertTrue(panel.insert_button.IsShown())
        self.assertEqual(panel.right.GetSplitMode(), self.wx.SPLIT_HORIZONTAL)
        self.assertGreaterEqual(panel.search.GetSize().width, 190)

        panel.set_compact(False)
        self.owner.SetSize((1100, 760))
        self.owner.Layout()
        self.wx.Yield()
        self.assertTrue(panel.summary.IsShown())
        self.assertTrue(panel.advanced.IsShown())
        self.assertTrue(panel.tree.IsShown())
        self.assertEqual(panel.right.GetSplitMode(), self.wx.SPLIT_VERTICAL)


if __name__ == "__main__":
    unittest.main()
