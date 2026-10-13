# SPDX-License-Identifier: Apache-2.0
"""Native T-entry block placement and source-backed comment toggles."""
from pathlib import Path
import wx
from .document import Document,write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def children(window):
        for child in window.GetChildren():
            yield child;yield from children(child)
    def enter(text,enabled):
        def edit():
            try:
                dialog=next(w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetTitle()=='Canvas text / SPICE · T')
                controls=list(children(dialog))
                next(c for c in controls if c.GetName()=='Canvas text or SPICE block').SetValue(text)
                next(c for c in controls if isinstance(c,wx.CheckBox)).SetValue(enabled)
                dialog.Layout();wx.Yield();capture_window(dialog,directory/'text-entry.png')
                next(c for c in controls if hasattr(c,'activate') and c.GetLabel()=='Validate / place').activate()
            except Exception as error:
                frame._text_error=error
                for window in wx.GetTopLevelWindows():
                    if isinstance(window,wx.Dialog):window.EndModal(wx.ID_CANCEL)
        wx.CallLater(100,edit);frame.execute_command('edit.canvas_text')
        if hasattr(frame,'_text_error'):raise frame._text_error
    def click(x,y):
        event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(frame.canvas.point(x,y));frame.canvas.GetEventHandler().ProcessEvent(event)
    try:
        frame.set_theme('Light',save=False)
        check(frame.keymap.bindings['edit.canvas_text']=='T','T is bound to canvas text entry')
        enter('.param gain=2\n.temp 40',False);click(140,500)
        added=[v for v in frame.doc.data['directives'] if v['text'].startswith(('.param','.temp'))]
        check(len(added)==2 and all(not v['enabled'] for v in added),'T-entry places a disabled directive block')
        check('* @spikes-off .temp 40' in frame.doc.data['source'],'commented commands are actual SPICE source comments')
        frame.Layout();frame.fit();frame.canvas.Refresh();frame.canvas.Update();wx.Yield();capture_window(frame,directory/'commented-canvas.png')
        frame.toggle_directive(added[1]['id'])
        check(next(v for v in frame.doc.data['directives'] if v['id']==added[1]['id'])['enabled'],'commented directive can be enabled again')
        before=frame.doc.data['source'];enter('Observe ripple here',True);click(440,480)
        check(frame.doc.data['source']==before and frame.doc.data['annotations'][-1]['text']=='Observe ripple here','ordinary T-entry creates an inert note')
        frame.doc.save(directory/'canvas-text.spksch')
        check(Document.load(directory/'canvas-text.spksch').data['directives']==frame.doc.data['directives'],'directive comment state and position survive reopen')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
