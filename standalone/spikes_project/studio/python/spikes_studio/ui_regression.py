"""Regression exercise through the running wx control/event handlers."""
from pathlib import Path
import time
import wx
import numpy as np
from .document import write_json
from .ui_evidence import capture_window


def verify_controls(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+45;paused=None

    def check(condition,message):
        if not condition:raise AssertionError(message)
        checks[message]=True

    def command(name):
        event=wx.CommandEvent(wx.wxEVT_COMMAND_MENU_SELECTED,frame.ids[name])
        frame.GetEventHandler().ProcessEvent(event)

    def protect(fn):
        try:
            if time.monotonic()>deadline:raise TimeoutError('GUI regression timed out')
            fn()
        except Exception as exc:
            frame.validation_failure=True
            if frame.active_run:frame.active_run.stop()
            write_json(destination/'error.json',{'error':str(exc),'checks':checks})
            frame.timer.Stop();frame.Destroy()

    def later(fn,ms=150):wx.CallLater(ms,lambda:protect(fn))

    def begin():
        from .desktop import Properties
        part=frame.doc.data['components'][1];ident=part['id']
        frame.source.SetText(frame.doc.data['source'].replace('1k','2k'))
        frame.doc.add_probe('V(in,out)',ident);frame.refresh_document()
        check('2k' in frame.source.GetText(),'refresh retains unapplied circuit text')
        frame.apply_source()
        check(frame.doc.data['components'][1]['id']==ident,'source apply preserves component identity')
        frame.canvas.selected={ident}
        dialog=Properties(frame)
        def apply():dialog.fields['package'].SetValue('0603');dialog.apply()
        wx.CallLater(100,apply);dialog.ShowModal();dialog.Destroy()
        check(frame.doc.data['components'][1]['package']=='0603','property dialog applies persisted values')
        frame.book.SetSelection(0);frame.canvas.Refresh();frame.canvas.Update();wx.YieldIfNeeded()
        x,y=part['x'],part['y'];start=frame.canvas.point(x,y);end=frame.canvas.point(x+60,y+40)
        event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(start);frame.canvas.GetEventHandler().ProcessEvent(event)
        event=wx.MouseEvent(wx.wxEVT_MOTION);event.SetPosition(end);event.SetLeftDown(True);frame.canvas.GetEventHandler().ProcessEvent(event)
        event=wx.MouseEvent(wx.wxEVT_LEFT_UP);event.SetPosition(end);frame.canvas.GetEventHandler().ProcessEvent(event)
        check(frame.doc.data['components'][1]['x']==x+60,'canvas drag commits one move')
        command('edit.undo');check(frame.doc.data['components'][1]['x']==x,'menu undo restores dragged position')
        command('edit.redo');check(frame.doc.data['components'][1]['x']==x+60,'menu redo restores move')
        frame.path=destination/'edited.spksch';command('file.save')
        check(not frame.doc.dirty,'Save clears document dirty state')
        # The user need not find and press a separate Apply button before F5.
        frame.source.SetText(frame.doc.data['source'].replace('2k','3k'))
        command('run.start');later(await_batch)

    def await_batch():
        if frame.job_running:later(await_batch);return
        check(frame.math is not None,'menu Run obtains native result')
        t=frame.math.time;v=frame.math.signals['v(out)'].values
        check(float(np.max(abs(v-(1-np.exp(-t/.003)))))<.0001,'Run uses unapplied edited 3k resistor')
        check(any(n=='V(in,out)' for n,_,_ in frame.traces),'saved differential probe is plotted after Run')
        frame.expression.SetValue('v(out)*i(R1)');frame.add_trace(frame.expression.GetValue())
        check(len(frame.axes)==2,'voltage and power have separate unit axes')
        frame.axes[0].set_xlim(.001,.002)
        class Cursor: xdata=.0015;inaxes=frame.axes[0]
        frame.cursor(Cursor())
        check(np.allclose(frame.axes[0].get_xlim(),(.001,.002)),'measurement cursor preserves zoom')
        capture_window(frame,destination/'01-batch-probes.png')
        command('run.interactive');later(await_interactive)

    def await_interactive():
        if frame.active_run and frame.active_run.state=='failed':raise RuntimeError(frame.active_run.error)
        if frame.active_run is None or frame.active_run.total_samples<100:later(await_interactive);return
        command('run.pause');later(await_pause)

    def await_pause():
        nonlocal paused
        if frame.active_run.state!='paused':later(await_pause);return
        paused=frame.active_run.snapshot();later(check_paused,250)

    def check_paused():
        check(paused['data']==frame.active_run.snapshot()['data'],'Pause freezes actual native samples')
        capture_window(frame,destination/'02-continuous-paused.png')
        frame.live_source.SetStringSelection('V1');frame.live_value.SetValue('2')
        event=wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED,frame.live_apply.GetId())
        frame.live_apply.GetEventHandler().ProcessEvent(event)
        command('run.pause');later(await_control)

    def await_control():
        snapshot=frame.active_run.snapshot()
        if snapshot['data']['node_voltage_v']['out'][-1]<1.99:later(await_control);return
        check(snapshot['data']['node_voltage_v']['in'][-1]==2,'live source button changes native input')
        check(bool(snapshot['provenance']['control_events']),'live source event has simulation timestamp')
        check(snapshot['data']['time_s'][0]>0,'continuous window contains actual accepted timesteps')
        frame.poll_run();capture_window(frame,destination/'03-live-control.png')
        write_json(destination/'continuous-snapshot.json',snapshot)
        command('run.stop');later(await_stop)

    def await_stop():
        if frame.job_running:later(await_stop);return
        check(frame.active_run is None,'Stop releases continuous worker')
        frame.source.SetText(frame.doc.data['source'].replace('10u 5m','10n 5m'))
        command('run.start');command('run.stop');later(finish)

    def finish():
        if frame.job_running:later(finish);return
        check(frame.active_run is None,'Stop terminates batch worker')
        frame.source.SetText(frame.doc.data['source'].replace('10n 5m','1n 1'))
        command('run.start')
        check(not frame.job_running and 'output points' in frame.last_error,'oversized batch is rejected nonmodally')
        check(frame.doc.data['source']==frame.source.GetText(),'oversized source remains editable for rolling mode')
        write_json(destination/'evidence.json',{'contract':'spikes/studio-workflow-regressions/v1','checks':checks,'all_passed':True,
                   'native_library':frame.library,'no_synthetic_display_data':True})
        frame.timer.Stop();frame.Destroy()

    protect(begin)
