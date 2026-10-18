# SPDX-License-Identifier: Apache-2.0
"""Real value-first placement dialog and post-placement wiring checks."""
from pathlib import Path
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def edit():
        try:
            dialog=next(w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetTitle()=='Add component')
            check(dialog.book.GetSelection()==0,'value and parameters are the default insertion tab')
            pin_page=next(i for i in range(dialog.book.GetPageCount()) if dialog.book.GetPageText(i)=='Pins & connections')
            check(all(c.GetParent()==dialog.book.GetPage(pin_page) for c in dialog.pins.values()),'pin mappings are confined to the separate connections tab')
            dialog.parameter_fields['r'].SetValue('4.7k');dialog.Layout();wx.Yield();capture_window(dialog,directory/'values-first.png')
            dialog.book.SetSelection(pin_page);dialog.Layout();wx.Yield();capture_window(dialog,directory/'pins-separate.png')
            dialog.book.SetSelection(0);dialog.accept()
        except Exception as error:
            frame._insert_test_error=error
            for w in wx.GetTopLevelWindows():
                if isinstance(w,wx.Dialog):w.EndModal(wx.ID_CANCEL)
    try:
        frame.set_theme('Light',save=False);wx.CallLater(100,edit);frame.place_shortcut('part.resistor',explicit=True)
        if hasattr(frame,'_insert_test_error'):raise frame._insert_test_error
        record,mapping,count=frame.pending_library_placement
        check(record['parameters']['r']==4700,'edited value reaches pending placement')
        check(all(value!='0' for value in mapping.values()),'default pins are isolated, not grounded')
        event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(frame.canvas.point(620,500));frame.canvas.GetEventHandler().ProcessEvent(event)
        part=next(p for p in frame.doc.data['components'] if p['ref'].startswith('RNEW'))
        check(float(part['value'])==4700,'canvas click inserts requested resistor value')
        ground=next(p for p in frame.doc.data['components'] if p['ref']=='V1')
        frame.doc.connect((ground['id'],1),(part['id'],1));frame.refresh_document();frame.Layout();wx.Yield();capture_window(frame,directory/'wired-component.png')
        check(next(p for p in frame.doc.data['components'] if p['id']==part['id'])['nodes'][1]=='0','isolated inserted primitive can be wired normally')
        frame.doc.save(directory/'placed.spksch')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
