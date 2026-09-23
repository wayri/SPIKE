"""Exercise real setup controls and native manager runs; capture only this test window."""
from copy import deepcopy
from pathlib import Path
import time
import wx
from .document import Document,write_json
from .simulation_manager import ThermalSetup
from .ui_evidence import capture_window


def verify_setup(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+45

    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True

    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop()
        write_json(destination/'error.json',{'error':str(exc),'checks':checks})
        frame.timer.Stop();frame.Destroy()

    def choose(key,value):
        control,kind=frame.manager.fields[key]
        if isinstance(kind,tuple):control.SetSelection(kind.index(value))
        else:control.SetValue(value)

    def begin():
        dialog=ThermalSetup(frame)
        def edit():
            try:
                dialog.fields['board.length_mm'][0].SetValue('180')
                dialog.layer_count.SetValue(6);dialog.resize_layers()
                dialog.fields['environment.ambient_c'][0].SetValue('45')
                dialog.fields['environment.airflow'][0].SetSelection(2)
                dialog.fields['environment.air_speed_m_s'][0].SetValue('2')
                dialog.fields['enclosure.type'][0].SetSelection(1)
                capture_window(dialog,destination/'01-board-stackup.png')
                dialog.book.SetSelection(2);dialog.Layout()
                capture_window(dialog,destination/'02-thermal-environment.png')
                dialog.apply()
                if frame.doc.data['thermal_setup']['board']['length_mm']!=180:raise AssertionError('Thermal form rejected valid setup')
            except Exception as exc:
                if dialog.IsModal():dialog.EndModal(wx.ID_CANCEL)
                fail(exc)
        wx.CallLater(200,edit);dialog.ShowModal();dialog.Destroy()
        if getattr(frame,'validation_failure',False):return
        try:
            check(len(frame.doc.data['thermal_setup']['board']['layers'])==6,'layer control saves six-layer stackup')
            frame.path=destination/'thermal-project.spksch';frame.save_document()
            check(Document.load(frame.path).data['thermal_setup']==frame.doc.data['thermal_setup'],'thermal setup survives project round trip')
            check('.temp' not in frame.doc.data['source'].lower(),'ambient does not silently change electrical temperature')
            frame.book.SetSelection(6)
            for key,value in {'name':'Thermal context RC','analysis':'transient','method':'backward_euler','time_step':'20u','stop_time':'2m'}.items():choose(key,value)
            frame.manager.run_profile();wx.CallLater(150,await_batch)
        except Exception as exc:fail(exc)

    def await_batch():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Manager batch run timed out')
            if frame.job_running:wx.CallLater(150,await_batch);return
            record=frame.run_history.records[-1]
            check(record['state']=='completed','manager runs actual native batch successfully')
            check(frame.manager.run_button.IsEnabled() and not frame.manager.stop_button.IsEnabled(),'manager re-enables run after completion')
            check(frame.result['provenance']['integration']=='backward_euler','selected integration reaches C++ batch runner')
            check(abs(frame.math.time[-1]-.002)<1e-12,'run-only stop time applied')
            check('.tran 10u 5m' in frame.doc.data['source'],'profile does not rewrite circuit source')
            setup=deepcopy(frame.doc.data['thermal_setup']);setup['environment']['ambient_c']=60
            frame.doc.update_setup('thermal_setup',setup);frame.refresh_document()
            check(record['thermal_setup']['environment']['ambient_c']==45,'run preserves original environment after project edit')
            write_json(destination/'batch-run-report.json',record)
            frame.book.SetSelection(6);capture_window(frame,destination/'03-simulation-manager.png')
            for key,value in {'execution':'continuous','method':'bdf2','capture_samples':'64','speed_ratio':'0.01'}.items():choose(key,value)
            frame.manager.run_profile();wx.CallLater(150,await_live)
        except Exception as exc:fail(exc)

    def await_live():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Manager continuous run timed out')
            run=frame.active_run
            if not run:raise AssertionError('Continuous run failed: '+str(frame.run_history.records[-1]))
            if run.total_samples<150:wx.CallLater(100,await_live);return
            check(len(run.snapshot()['data']['time_s'])==64,'manager applies bounded rolling capture')
            check(run.snapshot()['provenance']['integration']=='bdf2','manager applies native continuous BDF2')
            frame.pause_run();wx.CallLater(100,await_pause)
        except Exception as exc:fail(exc)

    def await_pause():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Pause timed out')
            if frame.active_run.state!='paused':wx.CallLater(100,await_pause);return
            frame.poll_run();check(frame.run_history.records[-1]['state']=='paused','manager reports acknowledged pause')
            frame.stop_run();wx.CallLater(100,await_stop)
        except Exception as exc:fail(exc)

    def await_stop():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Stop timed out')
            if frame.job_running:wx.CallLater(100,await_stop);return
            check(frame.run_history.records[-1]['state']=='stopped','manager reports native session stop')
            write_json(destination/'checks.json',checks)
            write_json(destination/'continuous-run-report.json',frame.run_history.records[-1])
            frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)

    begin()
