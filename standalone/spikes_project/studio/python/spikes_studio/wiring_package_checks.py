# SPDX-License-Identifier: Apache-2.0
"""Exercise native wiring feedback in source, frozen and installed acceptance."""
from copy import deepcopy
from types import SimpleNamespace


def verify(frame,check,capture_dir=None):
    import wx
    from .document import Document,RC_DECK
    from .schematic_layout import startup_layout
    from .schematic_symbol_renderer import label_positions

    original=frame.doc;selected=set(frame.canvas.selected);size=frame.GetSize()
    zoom=frame.canvas.zoom;offset=frame.canvas.offset.copy()
    try:
        frame.doc=Document.from_netlist(RC_DECK);startup_layout(frame.doc)
        frame.refresh_document(force_source=True);canvas=frame.canvas
        before=deepcopy(frame.doc.data)
        frame.start_wire();canvas.Refresh();canvas.Update();wx.Yield()
        point=next(point for point,ident,index in canvas.wire_pins if index is not None)
        event=SimpleNamespace(GetPosition=lambda:point,GetKeyCode=lambda:0)
        canvas.motion(event)
        check(canvas.wire_target['kind']=='terminal','wiring exposes an explicit terminal snap target')
        canvas.click(event);previous=canvas.wire_bend;frame.toggle_wire_bend()
        check(canvas.wire_bend!=previous and 'Backspace' in frame.GetStatusBar().GetStatusText(),
              'wire bend toggle and backtrack guidance are available')
        canvas.Refresh();canvas.Update();wx.Yield()
        if capture_dir is not None:
            from pathlib import Path
            from .ui_evidence import capture_window
            from .editor_geometry import route
            destination=Path(capture_dir);destination.mkdir(parents=True,exist_ok=True)
            parts={p['id']:p for p in frame.doc.data['components']}
            junctions={j['id']:j for j in frame.doc.data['junctions']}
            branch=None
            for wire in canvas.visible_wires():
                points=route(parts,wire,junctions)
                for a,b in zip(points,points[1:]):
                    world=((a[0]+b[0])/2,(a[1]+b[1])/2)
                    target=canvas.wire_snap_target(canvas.point(*world))
                    if target and target['kind']=='branch':branch=world;break
                if branch:break
            check(branch is not None,'existing wire branches expose a precise snap target')
            for name,dimensions in (('wire-wide',(1380,900)),('wire-narrow',(1000,720))):
                frame.SetSize(dimensions);frame.Layout();wx.Yield()
                point=canvas.point(*branch);canvas.motion(SimpleNamespace(GetPosition=lambda:point))
                canvas.Refresh();canvas.Update();wx.Yield();capture_window(frame,destination/(name+'.png'))
        canvas.placement_key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_ESCAPE))
        check(canvas.wire_mode and canvas.wire_start is None,'first Escape cancels the active wire segment')
        canvas.placement_key(SimpleNamespace(GetKeyCode=lambda:wx.WXK_ESCAPE))
        wire_control=next(control for control,command in frame.command_controls if command=='edit.wire')
        check(not wire_control.GetValue(),'closing Wire immediately clears its toolbar toggle')
        check(not canvas.wire_mode and frame.doc.data==before,
              'second Escape closes Wire without changing the document')
        anchors=label_positions(dict(x=0,y=0,rotation=90))
        check(all(x>28 for x,y in anchors) and len({y for x,y in anchors})==3,
              'rotated component identity text stacks beside the body')
        frame.doc=Document.from_netlist('Parallel routes\nV1 a 0 1\nR1 a 0 1k\nV2 b 0 2\nR2 b 0 2k\n.op\n.end\n')
        for part,position in zip(frame.doc.data['components'],((100,100),(400,100),(100,108),(400,108))):
            part['x'],part['y']=position
        parts=frame.doc.data['components']
        frame.doc.connect((parts[0]['id'],0),(parts[1]['id'],0),[[200,100]])
        frame.doc.connect((parts[2]['id'],0),(parts[3]['id'],0),[[200,108]])
        first,second=frame.doc.data['wires']
        canvas.zoom=1;canvas.offset=offset*0+[20.,15.]
        canvas.wire_mode=True;canvas.wire_start=(parts[3]['id'],1)
        near_a=canvas.wire_snap_target(canvas.point(200,100))
        near_b=canvas.wire_snap_target(canvas.point(200,108))
        check(near_a['wire_id']==first['id'] and near_b['wire_id']==second['id'],
              'parallel wire targets resolve to the nearest visible net')
    finally:
        canvas=frame.canvas;canvas.wire_mode=False;canvas.wire_start=None
        canvas.wire_corners=[];canvas.wire_hover=None;canvas.wire_target=None
        frame.doc=original;canvas.selected=selected;canvas.zoom=zoom;canvas.offset=offset;frame.SetSize(size);frame.refresh_document(force_source=True)
