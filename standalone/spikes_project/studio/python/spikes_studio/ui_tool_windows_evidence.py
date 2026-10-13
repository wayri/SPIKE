# SPDX-License-Identifier: Apache-2.0
"""Actual native main-navigation and floating library lifecycle evidence."""
from pathlib import Path
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False)
        choice=frame.workflow_bar.choice
        check(choice.GetCount()==4,'workspace selector contains only four main views')
        frame.Layout();wx.Yield();capture_window(frame,directory/'main-workspace.png')
        menu=frame.GetMenuBar()
        check(all(menu.FindMenu(name)>=0 for name in ('Libraries','Analysis','Tools','Simulation')),'specialist tools have organized menu groups')
        frame.execute_command('view.manufacturer_parts');window=frame.tool_windows.entries[16][0]
        panel=frame.manufacturer_panel;panel.search.SetValue('yageo');panel.refresh()
        panel.listing.SetSelection(0);panel.select()
        window.Layout();wx.Yield();capture_window(window,directory/'floating-library.png')
        record_id=panel.record['id'];window.Close();wx.Yield()
        check(not window.IsShown(),'closing a tool hides it without destroying the panel')
        frame.execute_command('view.manufacturer_parts')
        check(frame.tool_windows.entries[16][0] is window and panel.record['id']==record_id,'reopening retains filters and selected model')
        check(frame.book.GetSelection()==0,'floating library does not replace the schematic workspace')
        window.SetSize((760,600));window.Layout();wx.Yield();capture_window(window,directory/'floating-library-narrow.png')
        frame.book.SetSelection(1)
        check(window.IsShown(),'main view switching leaves the floating tool open')
        frame.tool_windows.dock(16)
        check(panel.GetParent()==frame.book,'return to workspace reparents the same panel')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
