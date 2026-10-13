# SPDX-License-Identifier: Apache-2.0
"""Actual workspace tabs, navigation buttons and docked-tool tab evidence."""
from pathlib import Path
from copy import deepcopy
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False);bar=frame.workflow_bar;before=deepcopy(frame.doc.data)
        bar.views[13].activate();bar.views[2].activate()
        bar.navigation_buttons['view.back'].activate();check(frame.book.GetSelection()==13,'Back restores previous workspace tab')
        bar.navigation_buttons['view.forward'].activate();check(frame.book.GetSelection()==2,'Forward restores next workspace tab')
        frame.execute_command('view.manufacturer_parts');frame.tool_windows.entries[16][0].Hide()
        bar.navigation_buttons['view.back'].activate();check(frame.book.GetSelection()==2,'tool-window visits participate in navigation history')
        bar.navigation_buttons['view.forward'].activate();check(frame.tool_windows.entries[16][0].IsShown(),'Forward reopens the same tool window')
        frame.tool_windows.entries[16][0].Hide();bar.home()
        frame.Layout();wx.Yield();capture_window(frame,directory/'navigation-home.png')
        frame.set_split('top_bottom');bar.navigation_buttons['view.home'].activate()
        check(not frame.split_view and frame.canvas.GetParent()==frame.schematic_host,'Home returns live editor from split mode')
        frame.tool_windows.dock(16);check(16 in bar.views,'returned specialist tool gains a main-window tab')
        frame.Layout();wx.Yield();capture_window(frame,directory/'navigation-tool-tab.png')
        frame.SetSize((960,720));bar.home();frame.Layout();frame.fit();wx.Yield();capture_window(frame,directory/'navigation-narrow.png')
        check(frame.doc.data==before,'section navigation does not change project content')
        check(frame.keymap.bindings['view.back']=='Alt+Left' and frame.keymap.bindings['view.home']=='Alt+Home','navigation shortcuts are registered')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
