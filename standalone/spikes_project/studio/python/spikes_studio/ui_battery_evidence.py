# SPDX-License-Identifier: Apache-2.0
"""Actual wx power-symbol and prescribed-current battery study checks."""
import json
from pathlib import Path
import time
import wx
from .document import Document,write_json
from .editor_geometry import terminal
from .ui_evidence import capture_window


def verify(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+45
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def finish(error=None):
        write_json(destination/'verification.json',dict(ok=error is None,checks=checks,error=str(error) if error else None,scope='Unqualified prescribed-current battery reference, not circuit-coupled or safety-qualified'))
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    def await_result():
        if frame.job_running and time.monotonic()<deadline:wx.CallLater(100,await_result);return
        try:
            panel=frame.battery_panel;result=panel.result
            check(result is not None,'actual worker produced battery study')
            import math
            # I=Q=1, gamma=.001 per EFC: SOH=1-k*t, k=gamma/7200.
            # Integrating dSOC/dt=-1/(3600*SOH) gives the independent oracle.
            rate=.001/7200
            expected=1+math.log1p(-rate*120)/(3600*rate)
            check(abs(result['samples'][-1]['soc']-expected)<1e-8,'aging-aware coulomb counting agrees with analytical capacity')
            check(result['samples'][-1]['temperature_k']>298.15,'Joule and polarization heating changes temperature')
            check(result['samples'][-1]['capacity_soh']<1,'explicit cycle-aging coefficient decreases capacity health')
            panel.market.Collapse(False);panel.filter_parts();panel.parts.SetSelection(0);panel.select_part();frame.Layout();wx.Yield();frame.Layout();panel.Layout();panel.plot.draw()
            check(len(panel.records)>=15,'market-cell source catalog loaded')
            capture_window(frame,destination/'battery-wide.png')
            frame.SetSize((960,720));frame.Layout();wx.Yield();frame.Layout();panel.Layout();panel.draw();panel.plot.draw();capture_window(frame,destination/'battery-narrow.png')
            write_json(destination/'battery-result.json',result)
            frame.doc.save(destination/'battery-power.spksch');reopened=Document.load(destination/'battery-power.spksch')
            check(reopened.data['metadata']['battery_study']==frame.doc.data['metadata']['battery_study'],'battery inputs and profile persist on reopen')
            check(reopened.data['power_symbols']==frame.doc.data['power_symbols'],'power symbols persist on reopen')
            finish()
        except Exception as error:finish(error)
    try:
        frame.set_theme('Light',save=False);frame.SetSize((1320,880))
        parts={p['ref']:p for p in frame.doc.data['components']}
        for kind,ref,index in [('reference_ground','C1',1),('power_flag','V1',0),('chassis_ground','R1',1)]:
            frame.place_designer_tool({'power_symbol':kind},terminal(parts[ref],index))
        check(len(frame.doc.data['power_symbols'])==3,'dedicated power/ground tools place semantic terminal markers')
        frame.book.SetSelection(0);frame.Layout();wx.Yield();capture_window(frame,destination/'power-symbols.png')
        panel=frame.battery_panel;frame.book.SetSelection(frame.book.FindPage(panel));frame.Layout();wx.Yield()
        panel.fields['duration_s'].SetValue('120');panel.fields['current_a'].SetValue('1')
        model=json.loads(panel.model.GetValue());model['cycle_capacity_loss_per_efc']=0.001;panel.model.SetValue(json.dumps(model))
        panel.run();wx.CallLater(100,await_result)
    except Exception as error:finish(error)
