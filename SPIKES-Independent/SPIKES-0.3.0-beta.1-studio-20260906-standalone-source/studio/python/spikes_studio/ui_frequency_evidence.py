"""Actual wx frequency controls, solver results and captured chart evidence."""
from pathlib import Path
import time
import wx
import numpy as np
from .document import write_json
from .frequency import VIEWS,validate_result,series,save_frequency,load_frequency
from .ui_evidence import capture_window


def verify_frequency(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+50
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop()
        write_json(destination/'error.json',{'error':str(exc),'checks':checks})
        frame.timer.Stop();frame.Destroy()
    def begin():
        try:
            frame.book.SetSelection(8);frame.frequency.run();wx.CallLater(150,await_run)
        except Exception as exc:fail(exc)
    def await_run():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Frequency worker timed out')
            if frame.job_running:wx.CallLater(150,await_run);return
            panel=frame.frequency
            check(panel.result is not None,'AC / PZ button returns real calculated result')
            check(frame.run_history.records[-1]['state']=='completed','simulation manager records completed frequency run')
            check(frame.run_history.records[-1]['samples']==401,'run history records frequency sample count')
            engine=validate_result(panel.result);values,_=series(engine,panel.expression.GetValue())
            check(np.max(abs(values-1/(1+2j*np.pi*engine.time*.001)))<1e-10,'GUI uses analytical-matching calculated RC phasors')
            check(panel.result['pole_zero']['data']['pole_count']==1,'GUI calculates descriptor-system pole')
            captures={'Bode dB / phase':'01-bode.png','Smith impedance':'02-smith.png','Nyquist':'03-nyquist.png','Pole-zero':'04-pole-zero.png','Polar':'05-polar.png'}
            for view in VIEWS:
                if view.startswith('Smith') or view in ('Return loss','VSWR'):panel.impedance()
                else:panel.transfer()
                panel.view.SetStringSelection(view)
                event=wx.CommandEvent(wx.wxEVT_COMMAND_CHOICE_SELECTED,panel.view.GetId());panel.view.GetEventHandler().ProcessEvent(event)
                check(len(panel.figure.axes)>0,'view selector renders '+view)
                if view in captures:capture_window(frame,destination/captures[view])
            panel.view.SetStringSelection('Pole-zero');panel.draw()
            check('-1000' in panel.report.GetValue(),'pole table reports actual −1000 rad/s pole')
            path=destination/'rc.spkfreq';save_frequency(path,panel.result);loaded=load_frequency(path)
            check(loaded==panel.result,'compressed frequency archive round-trips actual data')
            panel.impedance();panel.z0.SetValue('75');panel.draw()
            original_choose=frame.choose_path
            try:
                frame.choose_path=lambda *a,**k:destination/'plot-recipe.spkfreq'
                panel.save();panel.z0.SetValue('50');panel.view.SetStringSelection('Polar');panel.load()
                check(panel.z0.GetValue()=='75.0' and panel.view.GetStringSelection()=='Smith impedance','archive controls restore reference impedance and plot recipe')
            finally:frame.choose_path=original_choose
            panel.transfer();panel.figure.axes[0].set_xlim(10,10000);panel.plot.draw()
            check(np.allclose(panel.figure.axes[0].get_xlim(),[10,10000]),'scientific chart supports explicit axis zoom')
            write_json(destination/'checks.json',checks)
            write_json(destination/'run-report.json',frame.run_history.records[-1])
            frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)
    begin()
