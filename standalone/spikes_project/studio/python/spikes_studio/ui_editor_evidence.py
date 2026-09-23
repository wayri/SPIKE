"""Exercise actual rotated-terminal hit testing and native wired connectivity."""
from pathlib import Path
import wx
from .document import Document,write_json
from .run_control import native_batch
from .ui_evidence import capture_window

def verify_editor(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def run():
        try:
            frame.doc=Document.from_netlist('Wire test\nV1 in 0 1\nR1 in a 1k\nR2 b 0 1k\n.op\n.end\n');frame.refresh_document(force_source=True)
            a,b=frame.doc.data['components'][1:];frame.canvas.selected={a['id']}
            event=wx.CommandEvent(wx.wxEVT_MENU,frame.ids['edit.rotate']);frame.GetEventHandler().ProcessEvent(event)
            frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
            check(frame.doc.data['components'][1]['rotation']==90,'rotation menu changes persisted angle')
            frame.start_wire()
            for pid,index in ((a['id'],1),(b['id'],0)):
                point=next(p for p,i,n in frame.canvas.wire_pins if i==pid and n==index)
                click=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);click.SetPosition(point);frame.canvas.GetEventHandler().ProcessEvent(click)
                if pid==a['id']:
                    corner=frame.canvas.point(50,80)
                    click=wx.MouseEvent(wx.wxEVT_LEFT_DOWN);click.SetPosition(corner);frame.canvas.GetEventHandler().ProcessEvent(click)
            check(len(frame.doc.data['wires'])==1,'two terminal clicks create electrical wire')
            check(frame.doc.data['wires'][0]['waypoints']==[[50.,80.]],'intermediate click stores wire corner')
            result=native_batch(frame.doc.data['source'],frame.library)
            check(result['status']=='completed','wired circuit solves natively')
            check(abs(result['data']['node_voltage_v']['a']-.5)<1e-9,'wire produces the analytical 0.5 V divider output')
            capture_window(frame,destination/'wired-rotated-divider.png')
            before=frame.doc.data['source']
            for kind,at,down in [(wx.wxEVT_LEFT_DOWN,(250,80),True),(wx.wxEVT_MOTION,(250,100),True),(wx.wxEVT_LEFT_UP,(250,100),False)]:
                event=wx.MouseEvent(kind);event.SetPosition(frame.canvas.point(*at));event.SetLeftDown(down);frame.canvas.GetEventHandler().ProcessEvent(event)
            check(frame.doc.data['wires'][0]['waypoints']!=[[50.,80.]],'mouse drag moves wire route')
            check(frame.doc.data['source']==before,'wire drag preserves electrical connectivity')
            frame.doc.undo();frame.refresh_document()
            frame.doc.undo();frame.refresh_document();check(not frame.doc.data['wires'],'wire transaction undoes')
            check(isinstance(frame.book,wx.Simplebook),'workspace has no tab strip')
            frame.canvas.selected={a['id']};frame.mirror_parts('horizontal')
            check(any(frame.doc.data['components'][1].get(k,False) for k in ('mirror_x','mirror_y')),'mirror control changes saved geometry')
            frame.selection_tool('box');frame.canvas.Refresh();frame.canvas.Update();wx.Yield()
            start=wx.Point(5,5);end=wx.Point(frame.canvas.GetClientSize().width-8,frame.canvas.GetClientSize().height-8)
            for kind,point,down in [(wx.wxEVT_LEFT_DOWN,start,True),(wx.wxEVT_MOTION,end,True)]:
                event=wx.MouseEvent(kind);event.SetPosition(point);event.SetLeftDown(down);frame.canvas.GetEventHandler().ProcessEvent(event)
            check(len(frame.canvas.selection_path)>1,'box selection gesture has visible outline data')
            capture_window(frame,destination/'designer-selection.png')
            event=wx.MouseEvent(wx.wxEVT_LEFT_UP);event.SetPosition(end);frame.canvas.GetEventHandler().ProcessEvent(event)
            check(bool(frame.canvas.selected),'box selection selects circuit parts')
            frame.place_designer_tool({'annotation':'rect'},(80,180))
            check(len(frame.doc.data['annotations'])==1,'designer shape creates saved annotation')
            frame.doc.undo();check(not frame.doc.data['annotations'],'annotation insertion is undoable')
            panel=frame.catalog_panel;frame.book.SetSelection(11);panel.reset_filters()
            panel.search.ChangeValue('id:generic.d_flipflop.001');panel.filter();panel.list.SetSelection(0);panel.select();panel.notebook.SetSelection(0)
            check('VDD [power]' in panel.details.GetValue() and 'CLK [input]' in panel.details.GetValue(),'digital preview exposes labeled supply and clock pins')
            check(not panel.insert_button.IsEnabled(),'logical pin preview does not misrepresent MNA readiness')
            capture_window(frame,destination/'digital-pin-preview.png')
            write_json(destination/'checks.json',checks)
        except Exception as exc:
            frame.validation_failure=True;write_json(destination/'error.json',{'error':str(exc),'checks':checks})
        frame.timer.Stop();frame.Destroy()
    wx.CallLater(200,run)
