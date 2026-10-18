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
        check(not canvas.wire_mode and frame.doc.data==before,
              'second Escape closes Wire without changing the document')
        anchors=label_positions(dict(x=0,y=0,rotation=90))
        check(all(x>28 for x,y in anchors) and len({y for x,y in anchors})==3,
              'rotated component identity text stacks beside the body')
    finally:
        canvas=frame.canvas;canvas.wire_mode=False;canvas.wire_start=None
        canvas.wire_corners=[];canvas.wire_hover=None;canvas.wire_target=None
        frame.doc=original;canvas.selected=selected;frame.SetSize(size);frame.refresh_document(force_source=True)
