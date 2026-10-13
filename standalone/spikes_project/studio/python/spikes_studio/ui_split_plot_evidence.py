# SPDX-License-Identifier: Apache-2.0
"""Exercise native splits and attached plots using a real C++ RC run."""
from pathlib import Path
import time
import wx
from .document import Document, write_json
from .editor_geometry import terminal
from .plot_workspace import attachment_node, instrument_data
from .ui_evidence import capture_window


def verify(frame, destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+35
    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True
    def finish(error=None):
        write_json(directory/'verification.json',dict(ok=error is None,checks=checks,error=str(error) if error else None))
        frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
    def click(at):
        event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(frame.canvas.point(*at))
        frame.canvas.GetEventHandler().ProcessEvent(event)
    def inspect():
        try:
            if frame.job_running:
                if time.monotonic()>deadline:raise TimeoutError('RC run timed out')
                wx.CallLater(150,inspect);return
            check(frame.result is not None,'actual native RC simulation completed')
            resistor=next(p for p in frame.doc.data['components'] if p['ref']=='R1')
            capacitor=next(p for p in frame.doc.data['components'] if p['ref']=='C1')
            frame.refresh_document()
            frame.start_mini_plot();click(terminal(resistor,1));click((420,420))
            check(len(frame.doc.data['instruments'])==1,'two canvas clicks attach and drop a mini plot')
            item=frame.doc.data['instruments'][0]
            check(attachment_node(frame.doc,item)=='out','mini plot attaches to the selected net')
            label,value,curve=instrument_data(frame,item)
            check(curve is not None and len(curve[0])>100,'mini plot reads real retained waveform samples')
            frame.canvas.Refresh();wx.Yield()
            rect,_=frame.canvas.instrument_hits[0]
            event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(wx.Point(rect.x+20,rect.y+10));frame.canvas.click(event)
            frame.canvas.move_delta[:]=(40,20)
            event=wx.MouseEvent(wx.wxEVT_LEFT_UP);event.SetPosition(wx.Point(rect.x+60,rect.y+30));frame.canvas.move_end(event)
            item=frame.doc.data['instruments'][0]
            check(item['x']==460 and item['y']==440,'mini plot card drag is persisted')
            frame.doc.save(directory/'attached.spksch')
            restored=Document.load(directory/'attached.spksch').data['instruments'][0]
            check(restored==item,'plot and terminal binding survive project reopen')
            from .editor_geometry import route
            parts={p['id']:p for p in frame.doc.data['components']};junctions={j['id']:j for j in frame.doc.data['junctions']}
            wire=next(w for w in frame.doc.data['wires'] if w['a']==[resistor['id'],1] or w['b']==[resistor['id'],1])
            points=route(parts,wire,junctions);mid=[(points[0][i]+points[1][i])/2 for i in (0,1)]
            frame.start_mini_plot();click(mid);click((300,360))
            check('attach_point' in frame.doc.data['instruments'][-1],'wire click retains its exact geometric attachment point')
            frame.doc.undo();frame.refresh_document()
            frame.SetSize((1320,880));frame.fit();frame.Layout();wx.Yield();capture_window(frame,directory/'canvas-mini-plot.png')
            frame.set_split('side_by_side');frame.fit();frame.Layout();wx.Yield()
            check(frame.plot_splitter.GetSplitMode()==wx.SPLIT_VERTICAL,'side-by-side split uses the actual live editor')
            capture_window(frame,directory/'side-by-side.png')
            frame.set_split('top_bottom');frame.fit();frame.Layout();wx.Yield()
            check(frame.plot_splitter.GetSplitMode()==wx.SPLIT_HORIZONTAL,'top-bottom split switches orientation')
            capture_window(frame,directory/'top-bottom.png')
            frame.SetSize((960,720));frame.Layout();frame.fit();wx.Yield();capture_window(frame,directory/'split-narrow.png')
            frame.toggle_split()
            check(frame.canvas.GetParent()==frame.schematic_host and not frame.split_view,'plot-only layout returns editor to schematic host')
            finish()
        except Exception as error:finish(error)
    frame.set_theme('Light',save=False);frame.run();wx.CallLater(150,inspect)
