# SPDX-License-Identifier: Apache-2.0
"""Real compact shell geometry, tools, navigation and acquired plot checks."""
from pathlib import Path
import time
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+30
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def finish(error=None):
        write_json(directory/'verification.json',dict(ok=error is None,checks=checks,error=str(error) if error else None))
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    def await_run():
        if frame.job_running and time.monotonic()<deadline:wx.CallLater(100,await_run);return
        try:
            check(frame.math is not None,'actual native run supplies waveform data')
            frame.add_trace('i(R1)');frame.book.SetSelection(1);frame.Layout();wx.Yield();frame.plot.draw()
            capture_window(frame,directory/'waveforms-light.png')
            check(not frame.workflow_bar.tools.IsShown(),'schematic tools hide in waveform workspace')
            frame.set_theme('Dark',save=False);wx.Yield();frame.plot.draw();capture_window(frame,directory/'waveforms-dark.png')
            finish()
        except Exception as error:finish(error)
    try:
        frame.set_theme('Light',save=False);frame.SetSize((1320,880));frame.Layout();wx.Yield()
        check(frame.workflow_bar.GetSize().height<=96,'wide shell uses at most two compact rows')
        check(not frame.theme_picker.IsShown(),'appearance selector does not duplicate View menu')
        check(not frame.inspector.IsShown(),'empty selection inspector uses no space')
        capture_window(frame,directory/'schematic-light.png')
        button=frame.workflow_bar.sidebar_button;button.SetValue(False);frame.workflow_bar.toggle_sidebar();wx.Yield()
        check(not frame.workspace.IsSplit(),'navigator collapses without hiding circuit')
        frame.SetSize((960,720));frame.Layout();wx.Yield()
        check(frame.workflow_bar.GetSize().height<=96,'narrow shell remains bounded')
        capture_window(frame,directory/'schematic-focused-narrow.png')
        button.SetValue(True);frame.workflow_bar.toggle_sidebar();wx.Yield()
        check(frame.workspace.IsSplit(),'navigator reopens')
        wire=next(control for control,command in frame.command_controls if command=='edit.wire')
        wire.activate();check(frame.canvas.wire_mode,'icon-only wire tool routes through command registry')
        frame.canvas.wire_mode=False
        frame.set_theme('Dark',save=False);frame.Layout();wx.Yield();capture_window(frame,directory/'schematic-dark-narrow.png')
        frame.set_theme('Light',save=False);frame.SetSize((1320,880));frame.Layout();frame.run();wx.CallLater(100,await_run)
    except Exception as error:finish(error)
