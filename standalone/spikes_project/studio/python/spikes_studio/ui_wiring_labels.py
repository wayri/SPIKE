# SPDX-License-Identifier: Apache-2.0
"""Native junction/hop/scope rendering and source-preserving evidence."""
from pathlib import Path
import wx
from .document import Document,write_json
from .net_labels import attach
from .hierarchy_views import open_sheet
from .ui_evidence import capture_window


def verify(frame,destination):
    directory=Path(destination);directory.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Light',save=False)
        frame.doc=Document.from_netlist('Wire intersections\nV1 a 0 5\nV2 b 0 3\nR1 0 a 1k\nR3 a 0 2k\nR2 0 b 1k\nR4 b 0 3k\nR5 a 0 5k\n.op\n.end\n')
        parts={p['ref']:p for p in frame.doc.data['components']}
        for ref,x,y,rotation in [('V1',140,450,90),('V2',700,80,90),('R1',140,220,0),('R3',700,220,0),('R2',420,70,90),('R4',420,500,90),('R5',700,350,0)]:parts[ref].update(x=x,y=y,rotation=rotation)
        frame.doc.connect([parts['R1']['id'],1],[parts['R3']['id'],0],bend='horizontal')
        wire_id=frame.doc.data['wires'][-1]['id']
        frame.doc.connect([parts['R2']['id'],1],[parts['R4']['id'],0],bend='vertical')
        ident=frame.doc.branch(wire_id,(300,220),[parts['R5']['id'],0],[(300,350)],tolerance=0)
        source=frame.doc.data['source'];frame.toggle_wire_hops();check(frame.doc.data['source']==source,'wire hops do not change circuit source')
        attach(frame.doc,'local','output',[parts['R3']['id'],0]);attach(frame.doc,'global','rail',[parts['R4']['id'],0])
        frame.refresh_document(force_source=True);frame.fit();frame.canvas.junction_hover=(300,220);frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
        check(any(v['kind']=='hop' for v in frame.canvas.auto_junctions),'different source nets automatically receive a hop')
        check(len(frame.canvas.label_hits)==2,'local and global labels are rendered')
        frame.start_wire();point=frame.canvas.point(300,220);event=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);event.SetPosition(point);frame.canvas.click(event)
        check(frame.canvas.wire_start==(ident,),'an explicit junction starts the real wire tool')
        frame.canvas.wire_mode=False;frame.canvas.wire_start=None;frame.canvas.SetCursor(wx.NullCursor)
        capture_window(frame,directory/'junction-hop-labels.png')
        frame.SetSize((1000,720));frame.Layout();frame.fit();wx.Yield();capture_window(frame,directory/'junction-hop-narrow.png')
        hierarchy='''Scoped circuit
V1 supply 0 5
.global rail
.subckt cell input output
R1 input inner 1k
R2 inner output 2k
R3 rail output 10k
.ends cell
X1 supply left cell
X2 supply right cell
Rload1 left 0 3k
Rload2 right 0 4k
.op
.end
'''
        frame.doc=Document.from_netlist(hierarchy);frame.refresh_document(force_source=True)
        part=next(p for p in frame.doc.data['components'] if p['ref']=='X1:R1')
        attach(frame.doc,'hierarchical','input',[part['id'],0]);attach(frame.doc,'local','inner',[part['id'],1])
        open_sheet(frame,'X1');wx.Yield();frame.canvas.Update()
        check(all(p['ref'].startswith('X1:') for _,p in frame.canvas.hits),'subsheet view excludes other instance geometry')
        capture_window(frame,directory/'subsheet-ports.png')
        path=directory/'scoped.spksch';frame.doc.save(path);check(Document.load(path).data['labels']==frame.doc.data['labels'],'scoped labels survive save and reopen')
        write_json(directory/'verification.json',dict(ok=True,checks=checks))
    except Exception as error:write_json(directory/'verification.json',dict(ok=False,checks=checks,error=str(error)))
    frame.timer.Stop();frame.autosave_timer.Stop();frame.Destroy()
