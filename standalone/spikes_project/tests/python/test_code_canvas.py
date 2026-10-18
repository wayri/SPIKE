# SPDX-License-Identifier: Apache-2.0
"""Native shared-editor pairing, syntax and controller code lifecycle tests."""
from pathlib import Path
import os
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'studio/python'))


@unittest.skipUnless(os.environ.get('SPIKES_TEST_WX')=='1','opt-in native wx')
class CodeCanvasTests(unittest.TestCase):
    def test_visual_controller_settings_roundtrip_and_validation(self):
        import wx
        from spikes_studio.desktop import Studio
        from spikes_studio.controller_block import default_config
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            panel=frame.controller_panel;self.assertEqual(panel.config(),default_config())
            self.assertNotIsInstance(panel.settings,wx.TextCtrl)
            panel.settings.language.SetStringSelection('C++');panel.settings.step.SetValue('0.002');panel.settings.states.SetValue(12)
            panel.apply();saved=frame.doc.data['controller_setup']
            self.assertEqual((saved['language'],saved['step_s'],saved['state_count']),('C++',.002,12))
            self.assertEqual(saved['pins'],default_config()['pins'])
            panel.reflect();self.assertEqual(panel.config(),saved)
            panel.settings.step.SetValue('-1')
            with self.assertRaises(ValueError):panel.apply()
            self.assertEqual(frame.doc.data['controller_setup'],saved)
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_hdl_suite_cursor_and_filter_preserve_original_data(self):
        import wx
        from matplotlib.backend_bases import MouseEvent
        from spikes_studio.desktop import Studio
        from spikes_studio.ide import read_vcd
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();frame.book.SetSelection(3);frame.Layout();wx.Yield()
            data=read_vcd('$timescale 1 ns $end $scope module top $end $var wire 1 ! clk $end $upscope $end $enddefinitions $end #0 0! #5 1! #10 0! #15 1! #20 0!')
            frame.draw_timing(data);frame.hdl_suite.book.SetSelection(2);wx.Yield()
            plotter=frame.hdl_suite.plotter;plotter.canvas.draw();ax=plotter.cursor_lines[0].axes
            middle_y=sum(ax.get_ylim())/2;x,y=ax.transData.transform((0,middle_y))
            plotter.canvas.callbacks.process('button_press_event',MouseEvent('button_press_event',plotter.canvas,x,y,button=1))
            x,y=ax.transData.transform((7e-9,middle_y))
            plotter.canvas.callbacks.process('motion_notify_event',MouseEvent('motion_notify_event',plotter.canvas,x,y,button=1))
            plotter.canvas.callbacks.process('button_release_event',MouseEvent('button_release_event',plotter.canvas,x,y,button=1))
            self.assertAlmostEqual(plotter.cursor_times[0],7e-9,delta=1e-9)
            self.assertEqual(frame.hdl_suite.readings.GetCellValue(0,1),'1')
            self.assertIn('B - A',frame.hdl_suite.cursor_summary.GetLabel())
            before=plotter.cursor_times[:];frame.hdl_suite.search.SetValue('clk');wx.Yield()
            self.assertEqual(plotter.cursor_times,before)
            self.assertIs(plotter.data,data)
            self.assertTrue(frame.hdl_suite.readings.IsReadOnly(0,1))
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_pairing_crossprobe_syntax_and_draft_preservation(self):
        import wx
        import wx.stc as stc
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();frame.show_code_split(2);wx.Yield()
            self.assertTrue(frame.canvas_available(2))
            self.assertEqual(frame.editor_split.host.GetSplitMode(),wx.SPLIT_VERTICAL)
            draft=frame.source.GetText()+'* retained draft\n';frame.source.SetText(draft)
            position=draft.index('out');frame.source.SetFocus();frame.source.SetSelection(position,position+3);wx.Yield();frame.source_binding.refresh()
            self.assertIn('out',frame.canvas.highlighted_nets)
            frame.start_wire();self.assertEqual(frame.book.GetSelection(),2)
            frame.show_code_split(2,'top_bottom');self.assertEqual(frame.editor_split.host.GetSplitMode(),wx.SPLIT_HORIZONTAL)
            self.assertEqual(frame.source.GetText(),draft)
            frame.show_code_split(3)
            frame.code.SetText('module top; wire out; endmodule');frame.code.Colourise(0,-1)
            self.assertEqual(frame.code.GetStyleAt(0),stc.STC_V_WORD)
            frame.language.SetStringSelection('VHDL');frame.configure_code_editors()
            frame.code.SetText('entity top is end entity;');frame.code.Colourise(0,-1)
            self.assertEqual(frame.code.GetLexer(),stc.STC_LEX_VHDL)
            self.assertEqual(frame.code.GetStyleAt(0),stc.STC_VHDL_KEYWORD)
            frame.workflow_bar.home();self.assertFalse(frame.editor_split.active)
            self.assertIs(frame.canvas.GetParent(),frame.schematic_host)
            self.assertEqual(frame.source.GetText(),draft)
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()

    def test_controller_window_reuses_code_and_pin_bindings(self):
        import wx
        from spikes_studio.desktop import Studio
        app=wx.GetApp() or wx.App(False);frame=Studio()
        try:
            frame.Show();frame.controller_panel.apply();frame.canvas.Update();wx.Yield()
            editor=frame.controller_panel.code;window=frame.open_controller_code();wx.Yield()
            self.assertIs(editor.GetParent(),window)
            editor.SetText('double result = sense; outputs[0] = result;');editor.SetFocus();editor.SetSelection(16,21);wx.Yield();frame.controller_binding.refresh()
            self.assertIn('sense',frame.canvas.highlighted_controller_pins)
            self.assertIn('out',frame.canvas.highlighted_nets)
            draft=editor.GetText();window.Close();wx.Yield()
            self.assertFalse(window.IsShown());self.assertIs(frame.open_controller_code(),window)
            window.restore();self.assertIs(editor.GetParent(),frame.controller_panel)
            self.assertEqual(editor.GetText(),draft)
        finally:frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy();wx.Yield()
