# SPDX-License-Identifier: Apache-2.0
"""Actual shared netlist/IDE/controller editors and linked schematic evidence."""
from pathlib import Path
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def select(editor,binding,token):
        position=editor.GetText().index(token);editor.SetFocus();editor.SetSelection(position,position+len(token));wx.Yield();binding.refresh()
    try:
        frame.set_theme('Light',save=False);source=frame.source.GetText()
        frame.show_code_split(2);frame.Layout();frame.fit();wx.Yield();select(frame.source,frame.source_binding,'out')
        check('out' in frame.canvas.highlighted_nets,'netlist selection cross-highlights the actual output net')
        check(frame.editor_split.host.GetSplitMode()==wx.SPLIT_VERTICAL,'netlist and canvas use a side-by-side splitter')
        capture_window(frame,directory/'netlist-beside-canvas.png')
        frame.show_code_split(2,'top_bottom');frame.Layout();frame.fit();wx.Yield()
        check(frame.source.GetText()==source,'split orientation changes preserve netlist text')
        capture_window(frame,directory/'netlist-top-bottom.png')
        frame.show_code_split(3);frame.code.SetText('module top(input sense, output drive);\n  wire out;\n  assign drive = sense;\nendmodule\n')
        frame.Layout();frame.fit();wx.Yield();select(frame.code,frame.code_binding,'out')
        check('out' in frame.canvas.highlighted_nets,'HDL name selection cross-highlights a known net')
        capture_window(frame,directory/'hdl-beside-canvas.png')
        frame.workflow_bar.home();frame.controller_panel.apply();frame.canvas.Refresh();wx.Yield()
        window=frame.open_controller_code();editor=frame.controller_panel.code
        draft=editor.GetText();select(editor,frame.controller_binding,'inputs[0]')
        check('sense' in frame.canvas.highlighted_controller_pins and 'out' in frame.canvas.highlighted_nets,'controller indexed input links its named pin and plant net')
        window.Layout();wx.Yield();capture_window(window,directory/'controller-code-window.png')
        frame.canvas.Refresh();frame.canvas.Update();wx.Yield();capture_window(frame,directory/'controller-pin-highlight.png')
        check(not window.compile_button.IsEnabled(),'opening code does not grant execution trust')
        window.SetSize((550,380));window.Layout();wx.Yield();capture_window(window,directory/'controller-code-narrow.png')
        window.Close();wx.Yield();check(not window.IsShown(),'closing controller editor hides it and retains draft')
        check(frame.open_controller_code() is window and editor.GetText()==draft,'reopening uses the same controller editor and source')
        window.restore();check(editor.GetParent()==frame.controller_panel,'Return editor restores the original source widget')
        frame.book.SetSelection(12);frame.Layout();wx.Yield()
        check(not isinstance(frame.controller_panel.settings,wx.TextCtrl),'controller setup uses visual fields instead of JSON text')
        capture_window(frame,directory/'controller-visual-settings.png')
        frame.SetSize((1000,720));frame.Layout();wx.Yield();capture_window(frame,directory/'controller-visual-narrow.png')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
