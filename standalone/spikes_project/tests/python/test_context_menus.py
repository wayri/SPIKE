# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class ContextTests(unittest.TestCase):
    def setUp(self):
        import wx
        from spikes_studio.desktop import Studio
        self.app=wx.GetApp() or wx.App(False);self.frame=Studio()
    def tearDown(self):
        import wx
        self.frame.timer.Stop();self.frame.autosave_timer.Stop();self.frame.Destroy();wx.Yield()
    def test_editor_history_and_readonly_availability(self):
        import wx
        from spikes_studio.context_menus import editor_menu
        editor=self.frame.code;editor.SetText('abc');editor.SetSelection(0,2)
        menu=editor_menu(editor)
        try:
            items={i.GetItemLabelText():i for i in menu.menu.GetMenuItems() if not i.IsSeparator()}
            self.assertTrue(items['Copy'].IsEnabled());self.assertTrue(items['Cut'].IsEnabled())
            event=wx.CommandEvent(wx.wxEVT_MENU,items['Delete selection'].GetId());menu.menu.ProcessEvent(event)
            self.assertEqual(editor.GetText(),'c');editor.Undo();self.assertEqual(editor.GetText(),'abc')
        finally:menu.menu.Destroy()
        editor.SetReadOnly(True);menu=editor_menu(editor)
        try:self.assertFalse(next(i for i in menu.menu.GetMenuItems() if i.GetItemLabelText()=='Cut').IsEnabled())
        finally:menu.menu.Destroy()
    def test_dashboard_duplicate_context_action_and_run_lock(self):
        import wx
        from spikes_studio.dashboard_context import build,set_mode
        panel=self.frame.dashboard_panel;panel.add('Diagram block');original=panel.selected_row()['id'];menu=build(panel,panel.selected_row())
        try:
            item=next(i for i in menu.menu.GetMenuItems() if i.GetItemLabelText()=='Duplicate item')
            menu.menu.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU,item.GetId()))
            self.assertEqual(len(panel.data()['widgets']),2);self.assertNotEqual(panel.selected,original)
            self.frame.doc.undo();panel.refresh();self.assertEqual(len(panel.data()['widgets']),1)
        finally:menu.menu.Destroy()
        panel.select(panel.data()['widgets'][0]);set_mode(panel,'Run');menu=build(panel,panel.selected_row())
        try:self.assertFalse(next(i for i in menu.menu.GetMenuItems() if i.GetItemLabelText()=='Duplicate item').IsEnabled())
        finally:menu.menu.Destroy()
    def test_schematic_groups_selection_availability(self):
        import wx
        from spikes_studio.schematic_context import build
        event=wx.MouseEvent(wx.wxEVT_RIGHT_UP);event.SetPosition(wx.Point(15,15));canvas=self.frame.canvas
        canvas.selected.clear();menu=build(canvas,event,canvas.world(event.GetPosition()))
        try:
            groups={i.GetItemLabelText():i.GetSubMenu() for i in menu.menu.GetMenuItems() if i.GetSubMenu()}
            self.assertIn('Probe / instruments',groups)
            self.assertTrue(all(not i.IsEnabled() for i in groups['Move / transform'].GetMenuItems()))
        finally:menu.menu.Destroy()
    def test_manufacturer_menu_targets_clicked_part_and_clears_blank(self):
        import wx
        from unittest.mock import patch
        from spikes_studio.context_menus import ContextMenu
        panel=self.frame.manufacturer_panel;self.frame.Show();self.frame.book.SetSelection(16);self.frame.Layout();wx.Yield()
        panel.listing.SetSelection(0);panel.select();target=panel.listing.rows[2]
        rect=panel.listing.GetItemRect(2);position=panel.listing.ClientToScreen(wx.Point(rect.x+10,rect.y+rect.height//2))
        event=wx.ContextMenuEvent(wx.wxEVT_CONTEXT_MENU);event.SetPosition(position)
        with patch.object(ContextMenu,'popup',lambda menu,*args:menu.menu.Destroy()):panel.context(event)
        self.assertEqual(panel.record['id'],target['id'])
        event.SetPosition(panel.listing.ClientToScreen(wx.Point(-20,-20)))
        with patch.object(ContextMenu,'popup',lambda menu,*args:menu.menu.Destroy()):panel.context(event)
        self.assertIsNone(panel.record);self.assertFalse(panel.source_button.IsEnabled())
