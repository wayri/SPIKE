# SPDX-License-Identifier: Apache-2.0
"""Real native-run workbench captures and assertions, never mock curves."""
from pathlib import Path
import time
import wx
import numpy as np
from .document import write_json
from .ui_evidence import capture_window


def verify(frame, destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+60
    def check(condition,message):
        if not condition:raise AssertionError(message)
        checks[message]=True
    def fail(error):
        write_json(destination/'verification.json',dict(ok=False,checks=checks,error=str(error)))
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    def finish():
        try:
            frame.SetSize((960,720));frame.book.SetSelection(13);frame.Layout();wx.Yield()
            capture_window(frame,destination/'dashboard-narrow.png')
            check(frame.dashboard_panel.IsShown(),'dashboard available at narrow window')
            panel=frame.dashboard_panel
            panel.inspector_button.SetValue(False);panel.toggle_inspector();wx.Yield()
            check(not panel.side.IsShown(),'dashboard inspector can be collapsed')
            capture_window(frame,destination/'dashboard-focused.png')
            panel.inspector_button.SetValue(True);panel.toggle_inspector();wx.Yield()
            check(panel.side.IsShown(),'dashboard inspector can be reopened')
            frame.doc.save(destination/'workbench.spksch')
            from .document import Document
            reopened=Document.load(destination/'workbench.spksch')
            check(reopened.data['dashboard']==frame.doc.data['dashboard'],'dashboard persists on reopen')
            frame.SetSize((1320,880));frame.show_manufacturer_parts()
            frame.manufacturer_panel.search.SetValue('GRM21BR61A106KE19L')
            frame.manufacturer_panel.listing.SetSelection(0);frame.manufacturer_panel.select()
            frame.Layout();wx.Yield();capture_window(frame,destination/'manufacturer-library.png')
            check(frame.manufacturer_panel.record['mpn']=='GRM21BR61A106KE19L','real Murata exact-MPN browser selection')
            write_json(destination/'verification.json',dict(ok=True,checks=checks,
                provenance=frame.result['provenance'],hardware_connected=False))
            frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
        except Exception as error:fail(error)
    def begin_live():
        try:
            part=next(p for p in frame.doc.data['components'] if p['ref']=='V1')
            frame.doc.commit(lambda data:next(p for p in data['components'] if p['id']==part['id'])['parameters'].__setitem__('canvas_control',dict(low=0.,high=1.)))
            frame.refresh_document();frame.book.SetSelection(0);frame.canvas.Update();wx.Yield()
            frame.start_interactive();frame.book.SetSelection(0);frame.canvas.Update();wx.Yield()
            frame.interaction_mode=True
            event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(frame.canvas.point(part['x'],part['y']))
            frame.canvas.GetEventHandler().ProcessEvent(event)
            wx.CallLater(100,await_live)
        except Exception as error:fail(error)
    def await_live():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Continuous symbol interaction timed out')
            snapshot=frame.active_run.snapshot() or {}
            events=snapshot.get('provenance',{}).get('control_events',[])
            if not any(e.get('source')=='V1' and e.get('value')==0. for e in events):
                wx.CallLater(100,await_live);return
            check(True,'direct source-symbol click acknowledged at a real native step')
            frame.interaction_mode=False;frame.stop_run();wx.CallLater(100,await_stop)
        except Exception as error:fail(error)
    def await_stop():
        if frame.job_running:
            if time.monotonic()>deadline:fail(TimeoutError('Native stop did not acknowledge'));return
            wx.CallLater(100,await_stop);return
        try:
            check(True,'continuous native stop acknowledged')
            finish()
        except Exception as error:fail(error)
    def await_run():
        if time.monotonic()>deadline:fail(TimeoutError('Native GUI verification exceeded 60 s'));return
        if frame.job_running:wx.CallLater(100,await_run);return
        try:
            if frame.math is None:raise RuntimeError(getattr(frame,'last_error','No real solver result'))
            expected=1-np.exp(-frame.math.time/.001)
            error=float(np.max(np.abs(frame.math.signals['v(out)'].values-expected)))
            check(error<.012,'actual native RC trace agrees with analytic response')
            resistor=next(p for p in frame.doc.data['components'] if p['ref']=='R1')
            findings=frame.part_alerts.get(resistor['id'],{}).get('findings',[])
            check(any(f['limit']=='voltage_v' and f['severity']=='exceeded' for f in findings),'actual captured voltage drives declared-limit indicator')
            frame.book.SetSelection(0);frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
            capture_window(frame,destination/'captured-limit-indicators.png')
            frame.add_trace('i(R1)');frame.plot_workbench.refresh()
            check(frame.plot_workbench.signals.GetItemCount()>0,'recorded signals available in plot browser')
            frame.put_cursor(.001,0,'v(out)');frame.draw_plot()
            check(frame.plot_workbench.cursor_list.GetItemCount()==1,'dedicated cursor panel reads actual run')
            frame.book.SetSelection(1);frame.Layout();wx.Yield()
            capture_window(frame,destination/'waveforms-wide.png')
            frame.set_theme('Dark',save=False);wx.Yield()
            capture_window(frame,destination/'waveforms-dark.png')
            frame.set_theme('Light',save=False);wx.Yield()
            frame.book.SetSelection(13);frame.Layout();wx.Yield()
            frame.dashboard_panel.create_starters();frame.dashboard_panel.tick()
            check(len(frame.doc.data['dashboard']['widgets'])>=2,'starter instruments bind to real recorded signals')
            panel=frame.dashboard_panel
            frame.Raise();frame.SetFocus();wx.Yield()
            panel.inspector_button.SetFocus();wx.Yield()
            simulator=wx.UIActionSimulator();simulator.Char(wx.WXK_SPACE);wx.MilliSleep(60);wx.Yield()
            if panel.side.IsShown():
                focus=wx.Window.FindFocus()
                raise AssertionError('Inspector keyboard activation failed; focus='+str(focus.GetName() if focus else None))
            check(True,'focused inspector Space activation bypasses schematic shortcuts')
            simulator.Char(wx.WXK_SPACE);wx.MilliSleep(60);wx.Yield()
            check(panel.side.IsShown(),'focused inspector Space restores properties')
            frame.Layout();wx.Yield();capture_window(frame,destination/'dashboard-wide.png')
            wx.CallLater(200,begin_live)
        except Exception as error:fail(error)
    try:
        frame.set_theme('Light',save=False)
        frame.SetSize((1320,880));frame.book.SetSelection(0);frame.Layout();wx.Yield()
        # Deliberately low user-declared limits demonstrate indicators using
        # real calculated channels, not claims that this resistor is damaged.
        resistor=next(p for p in frame.doc.data['components'] if p['ref']=='R1')
        frame.doc.update([resistor['id']],{'limits':dict(voltage_v=.5,power_w=.0005)})
        frame.refresh_document()
        capture_window(frame,destination/'schematic-wide.png')
        check(len(frame.doc.data['wires'])==3,'startup has source-authoritative wires')
        frame.run();wx.CallLater(100,await_run)
    except Exception as error:fail(error)
