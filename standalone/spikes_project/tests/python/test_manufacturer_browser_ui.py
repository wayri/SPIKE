# SPDX-License-Identifier: Apache-2.0
"""Focused structure and opt-in native-wx checks for the manufacturer browser."""
from pathlib import Path
import os
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
STUDIO_PYTHON = ROOT / "studio" / "python"
PANEL_SOURCE = STUDIO_PYTHON / "spikes_studio" / "manufacturer_parts_panel.py"


class ManufacturerBrowserSourceTests(unittest.TestCase):
    def test_browser_uses_structured_report_and_details(self):
        source = PANEL_SOURCE.read_text(encoding="utf-8")
        self.assertIn("wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL", source)
        self.assertIn('("Manufacturer", "manufacturer"', source)
        self.assertIn('("Model readiness", "readiness"', source)
        self.assertIn('AddPage(overview_page, "Overview"', source)
        self.assertIn('AddPage(pins_page, "Pins"', source)
        self.assertIn('AddPage(evidence_page, "Evidence"', source)
        self.assertIn("ActionButton(right", source)
        self.assertNotIn("wx.ListBox(left)", source)

    def test_qualification_language_stays_explicit(self):
        source = PANEL_SOURCE.read_text(encoding="utf-8")
        self.assertIn("Catalog inclusion is not model qualification", source)
        self.assertIn("review-only", source)
        self.assertIn("not qualified", source)


@unittest.skipUnless(os.environ.get("SPIKES_TEST_WX") == "1", "set SPIKES_TEST_WX=1 for native wx controls")
class ManufacturerBrowserWxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(STUDIO_PYTHON))
        import wx
        from spikes_studio.manufacturer_parts_panel import ManufacturerPartsPanel
        from spikes_studio.themes import PALETTES

        cls.wx = wx
        cls.owns_app = wx.GetApp() is None
        cls.app = wx.GetApp() or wx.App(False)
        cls.frame = wx.Frame(None)
        owner = type("Owner", (), {"palette": PALETTES["Light"]})()
        cls.panel = ManufacturerPartsPanel(cls.frame, owner)

    @classmethod
    def tearDownClass(cls):
        cls.frame.Destroy()
        if cls.owns_app: cls.app.Destroy()
        sys.path.remove(str(STUDIO_PYTHON))

    def test_columns_and_listbox_compatible_selection(self):
        listing = self.panel.listing
        self.assertEqual(listing.GetColumnCount(), 5)
        self.assertEqual([listing.GetColumn(i).GetText() for i in range(5)],
                         ["Manufacturer", "MPN", "Category", "Nominal", "Model readiness"])
        listing.SetSelection(0)
        self.panel.select()
        self.assertEqual(listing.GetSelection(), 0)
        self.assertIs(self.panel.record, self.panel.rows[0])

    def test_refresh_preserves_matching_record_selection(self):
        self.panel.listing.SetSelection(0)
        self.panel.select()
        selected_id = self.panel.record["id"]
        self.panel.search.SetValue(self.panel.record["mpn"])
        self.panel.refresh()
        self.assertEqual(self.panel.record["id"], selected_id)
        self.assertGreaterEqual(self.panel.listing.GetSelection(), 0)

    def test_sort_keeps_details_bound_to_selected_identity(self):
        self.panel.search.SetValue('')
        self.panel.refresh()
        self.panel.listing.SetSelection(2); self.panel.select()
        selected_id = self.panel.record['id']
        event = self.wx.ListEvent(self.wx.wxEVT_LIST_COL_CLICK); event.SetColumn(1)
        self.panel.listing._sort(event); self.panel.select()
        self.assertEqual(self.panel.record['id'], selected_id)
        self.assertIs(self.panel.rows, self.panel.listing.rows)


if __name__ == "__main__":
    unittest.main()
