"""Real UI catalog insertion, bench alert, compiled controller and native feedback."""
from pathlib import Path
import json
import time
import wx
from .document import write_json,RC_DECK
from .ui_evidence import capture_window


def verify_catalog(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={};deadline=time.monotonic()+90
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop();frame.active_run.thread.join(timeout=2)
        write_json(destination/'error.json',{'error':str(exc),'checks':checks});frame.timer.Stop();frame.Destroy()
    def begin():
        try:
            panel=frame.catalog_panel;frame.book.SetSelection(11)
            check(len(panel.catalog['records'])==5000,'catalog exposes 5000 labeled presets')
            panel.category.SetStringSelection('Passives');panel.filter();check(len(panel.visible)==500,'category filter returns 500 presets')
            panel.search.SetValue('fuse');panel.filter();panel.list.SetSelection(0);panel.select();panel.inputs.SetValue('{"current":100}');panel.evaluate()
            check('TRIPPED' in panel.output.GetValue(),'bench fuse threshold produces visible alert text')
            capture_window(frame,destination/'catalog-bench.png')
            panel.search.SetValue('resistor');panel.filter();panel.list.SetSelection(0);panel.select();record=panel.edited()
            panel.insert_recipe(record,{'P':'out','N':'0'})
            check('XCAT1' in frame.doc.data['source'],'catalog native subcircuit inserts into authoritative circuit')
            frame.source.SetText(RC_DECK.replace('10u 5m','100u 5m'));frame.apply_source()
            frame.doc.commit(lambda d:d['components'][1]['limits'].update(power_w=.00001))
            control=frame.controller_panel;frame.book.SetSelection(12);control.trust.SetValue(True);control.compile();wx.CallLater(150,after_compile)
        except Exception as exc:fail(exc)
    def after_compile():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Controller compile test timed out')
            if frame.job_running:wx.CallLater(150,after_compile);return
            check(frame.controller_panel.compiled is not None,'actual C controller compile succeeds through panel')
            capture_window(frame,destination/'compiled-controller.png')
            frame.controller_panel.run();wx.CallLater(150,after_feedback)
        except Exception as exc:fail(exc)
    def after_feedback():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Controller feedback timed out')
            run=frame.active_run
            if run is None:raise AssertionError('Continuous controller stopped unexpectedly')
            if run.state=='failed':raise AssertionError(run.error)
            snap=run.snapshot()
            if not snap or snap['provenance']['total_samples']<35:wx.CallLater(100,after_feedback);return
            run.pause();wx.CallLater(150,after_pause)
        except Exception as exc:fail(exc)
    def after_pause():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Controller pause timed out')
            run=frame.active_run
            if run.state!='paused':wx.CallLater(100,after_pause);return
            snapshot=run.snapshot();check(any(e.get('origin')=='compiled_controller' for e in snapshot['provenance']['control_events']),'compiled controller drives timestamped native source events')
            check(.6<snapshot['data']['node_voltage_v']['out'][-1]<1.5,'native RC feedback tracks generic 1 V controller threshold')
            check('V1' not in run.controls,'controller-owned source excluded from manual control')
            frame.poll_run();check(any(f['severity']=='exceeded' for a in frame.part_alerts.values() for f in a['findings']),'captured native power raises schematic limit marker')
            frame.book.SetSelection(0);frame.canvas.Refresh();capture_window(frame,destination/'closed-loop-alert.png')
            write_json(destination/'native-feedback.json',snapshot)
            run.resume();check(run.pause_requested is False,'controller session resumes virtual time');run.stop();wx.CallLater(150,after_stop)
        except Exception as exc:fail(exc)
    def after_stop():
        try:
            if frame.active_run is not None:
                if time.monotonic()>deadline:raise TimeoutError('Controller stop timed out')
                wx.CallLater(100,after_stop);return
            check(not frame.job_running,'controller session stops cleanly')
            write_json(destination/'checks.json',checks);frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)
    begin()
