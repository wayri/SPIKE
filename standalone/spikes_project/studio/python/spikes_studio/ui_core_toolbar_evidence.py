# SPDX-License-Identifier: Apache-2.0
"""Native button activation and readable toolbar layout evidence."""
from pathlib import Path
import wx
from .document import write_json
from .editor_geometry import terminal
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False);frame.Layout();wx.Yield()
        buttons={command:control for control,command in frame.command_controls}
        check(len(buttons)==8 and all(v.GetLabel() for v in buttons.values()),'eight core actions have visible text labels')
        capture_window(frame,directory/'toolbar-wide.png')
        part=frame.doc.data['components'][1]
        frame.canvas.selected={part['id']};frame.refresh_inspector();frame.context_tools()
        buttons['edit.rotate'].activate()
        check(frame.doc.data['components'][1]['rotation']==90,'Rotate button changes selected symbol geometry')
        def close_properties():
            dialogs=[w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetTitle().startswith('Component properties')]
            if dialogs:
                checks['Properties button opens the complete component editor']=True
                dialogs[0].EndModal(wx.ID_CANCEL)
        wx.CallLater(100,close_properties);buttons['edit.properties'].activate()
        check(checks.get('Properties button opens the complete component editor'), 'Properties button opens the complete component editor')
        buttons['edit.move'].activate()
        check(frame.canvas.keyboard_move_mode=='move','Move button arms interactive placement')
        frame.canvas.keyboard_move_mode=None;frame.canvas.capture_lost()
        frame.set_split('side_by_side');buttons['edit.wire'].activate()
        check(frame.book.GetSelection()==1 and frame.canvas.wire_mode,'Wire stays on the live split editor')
        buttons['probe.voltage'].activate()
        frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
        part=frame.doc.data['components'][1];event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(frame.canvas.point(*terminal(part,1)))
        frame.canvas.GetEventHandler().ProcessEvent(event)
        check(any(p['expression'].casefold()=='v(out)' for p in frame.doc.data['probes']),'Probe button and terminal click create a saved net probe')
        buttons['edit.box_select'].activate();buttons['view.fit_schematic'].activate()
        check(frame.book.GetSelection()==1,'Select and Fit keep the split workspace active')
        frame.toggle_split();frame.book.SetSelection(0);frame.SetSize((960,720));frame.Layout();frame.fit();wx.Yield()
        check(frame.workflow_bar.choice.GetStringSelection()=='Schematic','main view label stays synchronized after split tools')
        frame.workflow_bar.choice.Refresh();frame.workflow_bar.choice.Update();wx.Yield()
        capture_window(frame,directory/'toolbar-narrow.png')
        buttons['view.component_catalog'].activate()
        check(frame.tool_windows.entries[11][0].IsShown(),'Parts opens the floating component selector')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
