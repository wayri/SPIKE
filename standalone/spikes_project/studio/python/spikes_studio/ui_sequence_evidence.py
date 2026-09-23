"""Actual native OP → transient queue and archived-result regression."""
from copy import deepcopy
from pathlib import Path
import json
import time
import wx
from .simulation_setup import default_profile
from .simulation_sequences import plan
from .document import write_json
from .ui_evidence import capture_window


def verify_sequences(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={};deadline=time.monotonic()+45
    def finish(error=None):
        frame.validation_failure=bool(error)
        write_json(destination/'checks.json',{'checks':checks,'error':error})
        if frame.active_run:frame.active_run.stop()
        frame.timer.Stop();frame.Destroy()
    def poll():
        try:
            panel=frame.manager.sequences
            if time.monotonic()>deadline:raise TimeoutError('Sequence exceeded 45 seconds')
            if panel.current is not None or frame.job_running:wx.CallLater(100,poll);return
            results=[json.loads(p.read_text()) for p in sorted(destination.glob('*-result.json'))]
            assert len(results)==2 and all(r['state']=='completed' for r in results),'Two native runs must complete'
            checks['OP then transient both archived']=True
            assert results[0]['profile']['name']=='Bias' and results[1]['profile']['name']=='Startup'
            checks['saved ordering retained']=True
            assert abs(results[0]['result']['data']['node_voltage_v']['out']-1)<1e-8
            assert results[1]['result']['data']['time_s'][-1]>.0049
            checks['native scalar and transient data verified']=True
            assert frame.doc.data['source']==panel.snapshot['source']
            checks['sequence does not rewrite project source']=True
            frame.book.SetSelection(6);frame.Layout();capture_window(frame,destination/'simulation-sequence-manager.png');finish()
        except Exception as exc:finish(repr(exc))
    try:
        sequence={'name':'RC verification','entries':[{'enabled':True,'profile':default_profile()|{'name':name,'analysis':analysis}} for name,analysis in [('Bias','operating_point'),('Startup','transient')]]}
        frame.doc.commit(lambda d:d.update(simulation_sequences=[sequence]));frame.refresh_document()
        panel=frame.manager.sequences;panel.directory=destination;panel.snapshot=deepcopy(frame.doc.data);panel.queue=plan(frame.doc.data['source'],sequence);panel.advance();wx.CallLater(100,poll)
    except Exception as exc:finish(repr(exc))
