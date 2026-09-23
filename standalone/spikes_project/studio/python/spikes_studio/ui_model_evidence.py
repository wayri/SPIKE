"""Real property-dialog model selection followed by native waveform execution."""
from pathlib import Path
import time
import wx
import numpy as np
from .document import write_json,Document
from .part_properties import parse
from .ui_evidence import capture_window


def verify_model_editor(frame,destination):
    from .desktop import Properties
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+30

    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True

    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop()
        write_json(destination/'error.json',{'error':str(exc),'checks':checks})
        frame.timer.Stop();frame.Destroy()

    def edit(dialog,fn):
        def action():
            try:fn()
            except Exception as exc:
                dialog.EndModal(wx.ID_CANCEL);frame.validation_failure=True
                write_json(destination/'error.json',{'error':str(exc),'checks':checks})
        wx.CallLater(150,action);dialog.ShowModal();dialog.Destroy()
        if getattr(frame,'validation_failure',False):raise AssertionError('Property dialog validation failed')

    def begin():
        part=frame.doc.data['components'][0];frame.canvas.selected={part['id']}
        dialog=Properties(frame)
        def pulse():
            dialog.fields['value'].SetValue('0')
            dialog.model_choice.SetSelection(1)
            event=wx.CommandEvent(wx.wxEVT_COMMAND_CHOICE_SELECTED,dialog.model_choice.GetId())
            dialog.model_choice.GetEventHandler().ProcessEvent(event)
            for key,value in {'high':'5','rise':'10u','fall':'10u','width':'1m','period':'2m'}.items():dialog.model_fields[key].SetValue(value)
            capture_window(dialog,destination/'01-source-value-model.png');dialog.apply()
        edit(dialog,pulse)
        source=frame.doc.data['source']
        check(parse(source).elements[0].waveform.kind=='pulse','dropdown binds PULSE source')
        dialog=Properties(frame)
        def reopen():
            check(dialog.chosen_mode()=='pulse','reopened dialog restores model type')
            check(float(dialog.model_fields['high'].GetValue())==5,'reopened dialog restores waveform parameters')
            dialog.EndModal(wx.ID_CANCEL)
        edit(dialog,reopen)
        frame.path=destination/'pulse.spksch';frame.save_document()
        check(Document.load(frame.path).data['source']==source,'model source survives save/load')
        frame.run();wx.CallLater(150,await_run)

    def await_run():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Native PULSE GUI run timed out')
            if frame.job_running:wx.CallLater(150,await_run);return
            check(frame.math is not None,'native PULSE run produces recorded data')
            values=frame.math.signals['v(in)'].values
            check(float(np.max(values))==5 and float(np.min(values))==0,'native input reaches entered low/high values')
            frame.add_trace('V(in)');capture_window(frame,destination/'02-pulse-native-result.png')
            write_json(destination/'pulse-result.json',frame.result)
            # Also exercise an actual named-model dropdown and private diode form.
            frame.doc=Document.from_netlist('Diode editor\nI1 0 a 1m\nD1 a 0 rect\n.model rect D(IS=1p N=1)\n.op\n.end\n')
            frame.refresh_document(force_source=True);frame.canvas.selected={frame.doc.data['components'][1]['id']}
            dialog=Properties(frame)
            def diode():
                dialog.model_choice.SetSelection(1);dialog.render_model()
                dialog.model_fields['is'].SetValue('5p');dialog.model_fields['n'].SetValue('1.5')
                capture_window(dialog,destination/'03-diode-model-fields.png');dialog.apply()
            edit(dialog,diode)
            check(parse(frame.doc.data['source']).elements[1].diode_model.emission_coefficient==1.5,'diode parameters bind to private executable model')
            write_json(destination/'evidence.json',{'all_passed':True,'checks':checks,'native_library':frame.library})
            frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)

    try:begin()
    except Exception as exc:fail(exc)
