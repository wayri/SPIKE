# SPDX-License-Identifier: Apache-2.0
"""Actual wx heading dialog, original-sample math and captured-cursor drag."""
from pathlib import Path
import time
import numpy as np
import wx
from matplotlib.backend_bases import MouseEvent
from .document import write_json
from .plot_workspace import sample
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+30
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def finish(error=None):
        frame.plot_interactions.cancel_drag()
        write_json(directory/'verification.json',dict(ok=error is None,checks=checks,error=str(error) if error else None))
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    def mouse(name,axis,t,y,button=1):
        x,pixel_y=axis.transData.transform((t,y))
        return MouseEvent(name,frame.plot,x,pixel_y,button=button)
    def edit_dialog():
        try:
            dialogs=[w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetTitle()=='Edit waveform']
            check(len(dialogs)==1,'clicking actual trace heading opens waveform editor')
            dialog=dialogs[0];field=wx.Window.FindWindowByName('Waveform expression',dialog)
            check(field is not None,'heading editor exposes editable equation')
            field.SetValue('v(out)*i(R1)')
            dialog.Layout();wx.Yield();capture_window(dialog,directory/'waveform-editor.png')
            wx.Window.FindWindowByName('Apply waveform',dialog).activate()
        except Exception as error:
            for window in wx.GetTopLevelWindows():
                if isinstance(window,wx.Dialog):window.EndModal(wx.ID_CANCEL)
            frame._waveform_test_error=error
    def await_run():
        if frame.job_running and time.monotonic()<deadline:wx.CallLater(100,await_run);return
        try:
            check(frame.math is not None,'native solver supplied original waveform samples')
            frame.add_trace('i(R1)');frame.book.SetSelection(1);frame.Layout();wx.Yield()
            frame.put_cursor(.001,0,'v(out)');frame.draw_plot();wx.Yield()
            heading=frame.axes[0].get_legend().get_texts()[0];box=heading.get_window_extent()
            event=MouseEvent('button_press_event',frame.plot,(box.x0+box.x1)/2,(box.y0+box.y1)/2,button=1)
            wx.CallLater(100,edit_dialog);frame.plot.callbacks.process('button_press_event',event)
            if hasattr(frame,'_waveform_test_error'):raise frame._waveform_test_error
            check(frame.traces[0][0]=='v(out)*i(R1)' and frame.traces[0][2]=='W','heading equation produces real power trace')
            expected=frame.math.signals['v(out)'].values*frame.math.signals['i(r1)'].values
            check(np.allclose(frame.traces[0][1],expected,rtol=1e-12,atol=1e-15),'math trace agrees with original-sample product')
            check(len(frame.cursors)==1 and frame.cursor_descriptor(0)['expression']=='v(out)*i(R1)','heading click does not create stray cursor and rebinds existing cursor')
            frame.plot.draw();axis=frame.axes[0];y=sum(axis.get_ylim())/2
            frame.plot.callbacks.process('button_press_event',mouse('button_press_event',axis,.001,y))
            check(frame.plot.HasCapture(),'cursor drag captures native mouse input')
            frame.plot.callbacks.process('motion_notify_event',mouse('motion_notify_event',axis,.003,y))
            actual_time=frame.cursors[0]
            check(abs(actual_time-.003)<2e-5,'cursor follows dragged pixel position')
            from matplotlib.ticker import EngFormatter
            check(frame.plot_workbench.cursor_list.GetItemText(0,2)==EngFormatter(unit='s',places=4)(actual_time),'docked cursor time updates during drag')
            measured=sample(frame.math,'v(out)*i(R1)',actual_time)
            check(abs(float(measured.values)-float(np.interp(actual_time,frame.math.time,expected)))<1e-14,'drag measurement uses original samples')
            frame.plot.callbacks.process('button_release_event',mouse('button_release_event',axis,.003,y))
            check(not frame.plot.HasCapture() and frame.plot_interactions.drag is None,'release ends native capture')
            check(frame.plot_interactions.window is None,'cursor placement does not force floating window focus')
            frame.put_cursor(.002,0,'v(out)*i(R1)');frame.draw_plot();frame.plot.draw();capture_window(frame,directory/'edited-waveforms.png')
            frame.doc.save(directory/'waveform-project.spksch')
            from .document import Document
            check('v(out)*i(R1)' in Document.load(directory/'waveform-project.spksch').data['expressions'],'edited expression persists on project reopen')
            finish()
        except Exception as error:finish(error)
    try:
        frame.set_theme('Light',save=False);frame.SetSize((1320,880));frame.run();wx.CallLater(100,await_run)
    except Exception as error:finish(error)
