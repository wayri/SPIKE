# SPDX-License-Identifier: Apache-2.0
"""Actual native dashboard diagram editing, persistence and meter evidence."""
from pathlib import Path
import wx
from .dashboard import widget,update_widget
from .document import Document,write_json
from .signal_math import SignalMath
from .ui_evidence import capture_window
from .run_control import native_batch


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False);panel=frame.dashboard_panel;frame.book.SetSelection(13)
        frame.math=SignalMath.from_result(native_batch(frame.doc.data['source'],frame.library))
        a,b,m,n=[widget(k) for k in ('Diagram block','Diagram block','Meter','Note')]
        a.update(title='MCU / connector J1',expression='GPIO PA5 -> gate driver',x=20,y=20)
        b.update(title='MOSFET / DUT',expression='Power switch and load',x=400,y=20)
        m.update(title='Output voltage',expression='V(out)',x=400,y=250)
        n.update(title='Interface boundary',expression='Diagram links are visual only.\nDUT hardware is disconnected.',x=20,y=250)
        data={'version':1,'widgets':[a,b,m,n]};panel.commit(data);panel.select(a);panel.begin_connect()
        event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(wx.Point(450,60));panel.canvas.GetEventHandler().ProcessEvent(event)
        check(panel.data()['connections']==[{'from':a['id'],'to':b['id']}],'canvas click creates a stable visual connector')
        binding=dict(device='future debug adapter',connector='J1',pin='3',gpio='PA5',direction='Write',safe_value=0)
        panel.commit(update_widget(panel.data(),a['id'],dut_binding=binding))
        path=directory/'diagram.spksch';frame.doc.save(path);loaded=Document.load(path)
        check(loaded.data['dashboard']==panel.data(),'diagram and data-only DUT mapping survive save/reopen')
        frame.doc.undo();panel.refresh();check(not panel.data()['widgets'][0].get('dut_binding'),'mapping change is undoable')
        frame.doc.redo();panel.refresh();panel.select(None);frame.Layout();wx.Yield()
        capture_window(frame,directory/'diagram-wide.png')
        frame.SetSize((1000,760));panel.inspector_button.SetValue(False);panel.toggle_inspector();frame.Layout();wx.Yield()
        capture_window(frame,directory/'diagram-narrow.png')
        write_json(directory/'verification.json',dict(ok=True,checks=checks,hardware_connected=False))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
