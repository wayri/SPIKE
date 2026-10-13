# SPDX-License-Identifier: Apache-2.0
"""Real C++ run capture for floating derived-analysis windows."""
from pathlib import Path
import time
import wx
from .run_control import native_batch
from .signal_math import SignalMath
from .analysis_plot_window import AnalysisPlotWindow
from .ui_evidence import capture_window
from .document import write_json


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);window=None;checks={}
    try:
        result=native_batch(frame.doc.data['source'],frame.library)
        if result['status']!='completed':raise ValueError('Native evidence run did not complete')
        frame.math=SignalMath.from_result(result);frame.expression.SetValue('v(out)')
        frame.set_theme('Light',save=False);window=AnalysisPlotWindow(frame)
        for kind,size,name in [('FFT peak amplitude',(1040,720),'fft-wide.png'),
                               ('Cumulative integral',(780,600),'integral-narrow.png')]:
            window.SetSize(size);window.view.SetStringSelection(kind);window.reflect();window.request()
            deadline=time.monotonic()+8
            while window.busy and time.monotonic()<deadline:wx.Yield();time.sleep(.01)
            if window.busy or not hasattr(window,'last_data') or window.last_data['view']!=kind:raise AssertionError('Derived plot failed: '+window.report.GetValue())
            checks[kind]=True;window.Layout();wx.Yield();capture_window(window,directory/name)
        write_json(directory/'verification.json',dict(ok=True,checks=checks,source_provenance=result['provenance']))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    finally:
        if window:window.Close()
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
