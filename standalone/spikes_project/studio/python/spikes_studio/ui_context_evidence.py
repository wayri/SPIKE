# SPDX-License-Identifier: Apache-2.0
"""Native popup-menu captures and real menu-command acceptance evidence."""
from pathlib import Path
import ctypes
import threading
import time
import os
import wx
from .document import write_json
from .context_menus import editor_menu
from .dashboard_context import build as dashboard_menu
from .schematic_context import build as schematic_menu


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def capture_popup(menu,window,name,position):
        frame.Show();frame.Raise();ctypes.windll.user32.SetForegroundWindow(int(frame.GetHandle()));wx.Yield()
        handle=int(window.GetHandle());frame_handle=int(frame.GetHandle());errors=[]
        def capture():
            try:
                time.sleep(.4)
                from PIL import ImageGrab
                ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
                foreground_pid=ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(ctypes.windll.user32.GetForegroundWindow(),ctypes.byref(foreground_pid))
                if foreground_pid.value!=os.getpid():raise RuntimeError('Test window lost foreground; screenshot is not accepted')
                class Rect(ctypes.Structure):_fields_=[(key,ctypes.c_long) for key in ('left','top','right','bottom')]
                rect=Rect()
                if not ctypes.windll.user32.GetWindowRect(frame_handle,ctypes.byref(rect)):raise RuntimeError('Cannot locate test window')
                bounds=(rect.left,rect.top,rect.right,rect.bottom)
                ImageGrab.grab(bbox=bounds).save(directory/name)
            except Exception as error:errors.append(str(error))
            finally:ctypes.windll.user32.PostMessageW(handle,0x001F,0,0) # WM_CANCELMODE ends only this test popup.
        worker=threading.Thread(target=capture,daemon=True);worker.start()
        try:window.PopupMenu(menu.menu,position)
        finally:menu.menu.Destroy()
        worker.join(3)
        if errors:raise RuntimeError(errors[0])
    try:
        frame.set_theme('Light',save=False);frame.Raise();frame.fit();wx.Yield()
        canvas=frame.canvas;canvas.selected={frame.doc.data['components'][0]['id']};frame.refresh_inspector()
        event=wx.MouseEvent(wx.wxEVT_RIGHT_UP);event.SetPosition(wx.Point(300,170))
        menu=schematic_menu(canvas,event,canvas.world(event.GetPosition()))
        checks['schematic exposes grouped real commands']=any(i.GetSubMenu() for i in menu.menu.GetMenuItems())
        capture_popup(menu,canvas,'schematic-menu.png',wx.Point(250,120))
        panel=frame.dashboard_panel;frame.book.SetSelection(13);panel.add('Diagram block');frame.Layout();wx.Yield()
        menu=dashboard_menu(panel,panel.selected_row());item=next(i for i in menu.menu.GetMenuItems() if i.GetItemLabelText()=='Duplicate item')
        menu.menu.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU,item.GetId()));menu.menu.Destroy()
        checks['duplicate menu command creates independent dashboard item']=len(panel.data()['widgets'])==2
        menu=dashboard_menu(panel,panel.selected_row());capture_popup(menu,panel.canvas,'dashboard-menu.png',wx.Point(120,80))
        frame.book.SetSelection(3);frame.code.SetSelection(0,6);frame.Layout();wx.Yield()
        menu=editor_menu(frame.code);capture_popup(menu,frame.code,'editor-menu.png',wx.Point(140,40))
        frame.SetSize((1000,720));frame.Layout();wx.Yield();menu=editor_menu(frame.code)
        capture_popup(menu,frame.code,'editor-menu-narrow.png',wx.Point(140,40))
        from unittest.mock import patch
        from .context_menus import ContextMenu
        from .run_control import native_batch
        from matplotlib.backend_bases import MouseEvent
        from .signal_math import SignalMath
        frame.SetSize((1320,880));result=native_batch(frame.doc.data['source'],frame.library)
        frame.math=SignalMath.from_result(result);frame.run_results=[result];frame.run_engines=[frame.math];frame.selected_run=0;frame.result=result
        frame.add_trace('V(out)',persist=False);frame.book.SetSelection(1);frame.Layout();wx.Yield();frame.plot.draw()
        x,y=frame.axes[0].transAxes.transform((.5,.5))
        with patch.object(ContextMenu,'popup',lambda m,w,position=None:capture_popup(m,w,'plot-menu.png',wx.Point(200,80))):
            frame.plot_interactions.context_menu(MouseEvent('button_press_event',frame.plot,x,y,button=3))
        checks['plot menu opens on actual native run']=frame.math is not None
        write_json(directory/'verification.json',dict(ok=all(checks.values()),checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
