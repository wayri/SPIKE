# SPDX-License-Identifier: Apache-2.0
"""Actual blank-space double-click palette, completion and insertion evidence."""
from pathlib import Path
import time
import wx
from .document import write_json
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def capture(popup,name):
        popup.Refresh();popup.Update();deadline=time.monotonic()+.06
        while time.monotonic()<deadline:wx.Yield();time.sleep(.005)
        capture_window(popup,directory/name)
    def open_popup():
        frame.book.SetSelection(0);frame.Layout();wx.Yield()
        event=wx.MouseEvent(wx.wxEVT_LEFT_DCLICK);event.SetPosition(wx.Point(500,400));frame.canvas.double_click(event);wx.Yield()
        popup=getattr(frame,'quick_insert_popup',None)
        check(popup is not None and not popup.closed,'blank-space double-click opens a native palette')
        return popup
    try:
        frame.set_theme('Light',save=False);frame.fit();popup=open_popup()
        popup.query.SetValue('resistor');wx.Yield();capture(popup,'component-search.png')
        original=frame.doc.data['source'];popup.query.SetValue('resistr');wx.Yield();capture(popup,'fuzzy-component-search.png')
        check(popup.rows[0]['payload']=='generic.resistor.001','fuzzy component query prioritizes the matching primitive')
        check(frame.doc.data['source']==original,'fuzzy search never mutates circuit source')
        popup.query.SetValue('.tr');wx.Yield();capture(popup,'directive-completion.png')
        check(popup.rows[0]['completion'],'partial directive has a template completion')
        popup.accept();check(popup.query.GetValue().startswith('.tran '),'Enter expands template rather than executes incomplete syntax')
        popup.query.SetValue('.param quick_gain=2');wx.Yield();capture(popup,'text-spice-options.png')
        check({'spice','text'}<={r['kind'] for r in popup.rows},'typed SPICE offers explicit text and directive actions')
        popup.accept();wx.Yield();check('.param quick_gain=2' in frame.doc.data['source'],'directive placement changes validated source')
        frame.doc.undo();frame.refresh_document(force_source=True)
        popup=open_popup();popup.query.SetValue('My circuit note');popup.accept();wx.Yield()
        check(frame.doc.data['annotations'][-1]['text']=='My circuit note','free text places an inert note at the clicked location')
        frame.doc.undo();frame.refresh_document();frame.SetSize((1000,720));frame.Layout();wx.Yield()
        popup=open_popup();popup.category.SetStringSelection('Monitors');popup.query.SetValue('meter');popup.refresh();wx.Yield()
        capture(popup,'monitor-search-narrow.png');check(all(r['kind']=='monitor' for r in popup.rows),'monitor filter excludes components and directive templates')
        popup.close();write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
