# SPDX-License-Identifier: Apache-2.0
"""Labeled controller-board symbols; geometry never establishes circuit nets."""
from copy import deepcopy
import math
import wx


def geometry(board):
    pins=board['pins'];rows=math.ceil(len(pins)/2)
    return 420,max(110,72+24*rows),[(pin,0 if i<rows else 1,56+24*(i if i<rows else i-rows))
                                 for i,pin in enumerate(pins)]


class BoardCanvasTools:
    def __init__(self,canvas):
        self.canvas=canvas;self.pending=None;self.selected=None;self.drag=None;self.hits=[]
        for event,handler in ((wx.EVT_LEFT_DOWN,self.down),(wx.EVT_LEFT_UP,self.up),
                              (wx.EVT_MOTION,self.motion),(wx.EVT_LEFT_DCLICK,self.edit),
                              (wx.EVT_RIGHT_UP,self.context),(wx.EVT_KEY_DOWN,self.key),
                              (wx.EVT_MOUSE_CAPTURE_LOST,self.capture_lost)):
            canvas.Bind(event,handler)

    def visible(self):
        scope=getattr(self.canvas,'sheet_scope',None) or ''
        return [b for b in self.canvas.owner.doc.data.get('controller_boards',[]) if b.get('scope','')==scope]

    def start(self,board):
        self.cancel();self.pending=deepcopy(board);self.canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS))
        self.canvas.owner.book.SetSelection(0);self.canvas.SetFocus()
        self.canvas.owner.SetStatusText('Click to place the labeled controller pinout; Escape cancels. Pins do not create nets until explicitly bound.')

    def at(self,point):
        world=self.canvas.world(point)
        for block in reversed(self.visible()):
            w,h,_=geometry(block['board'])
            if block['x']-28<=world[0]<=block['x']+w+28 and block['y']<=world[1]<=block['y']+h:return block
        return None

    def down(self,event):
        c=self.canvas;owner=c.owner
        if self.pending:
            if owner.job_running:return
            from .controller_board_blocks import create
            x,y=(round(float(v)/10)*10 for v in c.world(event.GetPosition()))
            refs={b['ref'] for b in owner.doc.data['controller_boards']};index=1
            while f'MCU{index}' in refs:index+=1
            record=self.pending.get('board',self.pending)
            block=create(record,x,y,ref=f'MCU{index}',scope=getattr(c,'sheet_scope',None) or '')
            if 'bindings' in self.pending:block['bindings']=deepcopy(self.pending['bindings'])
            owner.doc.commit(lambda d:d['controller_boards'].append(block));self.selected=block['id'];self.pending=None
            c.SetCursor(wx.NullCursor);owner.refresh_document();return
        block=self.at(event.GetPosition())
        if not block or c.wire_mode or c.probe_mode:
            self.selected=None;event.Skip();return
        self.selected=block['id'];c.selected.clear();c.SetFocus();c.Refresh()
        if owner.job_running:return
        self.drag={'id':block['id'],'start':c.world(event.GetPosition()),'x':block['x'],'y':block['y'],
                   'position':(block['x'],block['y']),'revision':owner.doc.data['revision'],'document':owner.doc.data['id']}
        if not c.HasCapture():c.CaptureMouse()

    def motion(self,event):
        if self.drag and event.LeftIsDown():
            delta=self.canvas.world(event.GetPosition())-self.drag['start']
            self.drag['position']=tuple(round((self.drag[key]+float(delta[i]))/10)*10 for i,key in enumerate(('x','y')))
            self.canvas.Refresh();return
        event.Skip()

    def up(self,event):
        if not self.drag:event.Skip();return
        drag=self.drag;self.cancel();owner=self.canvas.owner
        if owner.job_running or owner.doc.data['id']!=drag['document'] or owner.doc.data['revision']!=drag['revision']:return
        if drag['position']==(drag['x'],drag['y']):return
        def move(data):
            target=next(b for b in data['controller_boards'] if b['id']==drag['id'])
            target['x'],target['y']=drag['position']
        owner.doc.commit(move);owner.refresh_document()

    def cancel(self):
        self.drag=None;self.pending=None
        if self.canvas.HasCapture():self.canvas.ReleaseMouse()
        self.canvas.SetCursor(wx.NullCursor);self.canvas.Refresh()

    def capture_lost(self,event):
        self.drag=None;self.canvas.Refresh();event.Skip()

    def key(self,event):
        if event.GetKeyCode()==wx.WXK_ESCAPE and (self.pending or self.drag):self.cancel();return
        if event.GetKeyCode()==wx.WXK_DELETE and self.selected:
            self.canvas.owner.guarded(lambda:self.remove(self.selected));return
        event.Skip()

    def edit(self,event):
        block=self.at(event.GetPosition())
        if not block:event.Skip();return
        from .controller_board_browser import show
        self.canvas.owner.guarded(lambda:show(self.canvas.owner,block))

    def remove(self,ident):
        owner=self.canvas.owner
        if owner.job_running:raise ValueError('Stop simulation before removing a controller board')
        if (owner.doc.data.get('controller_setup') or {}).get('board_block_id')==ident:
            raise ValueError('Detach this board from the saved sampled-controller setup before removing it')
        owner.doc.commit(lambda d:d.__setitem__('controller_boards',[b for b in d['controller_boards'] if b['id']!=ident]))
        self.selected=None;owner.refresh_document()

    def context(self,event):
        block=self.at(event.GetPosition())
        if not block:event.Skip();return
        owner=self.canvas.owner
        from .controller_board_browser import show
        menu=wx.Menu()
        for label,fn in [('Board pins / sampled I/O bindings…',lambda:show(owner,block)),
                         ('Remove board block',lambda:self.remove(block['id']))]:
            item=menu.Append(wx.ID_ANY,label);menu.Bind(wx.EVT_MENU,lambda e,f=fn:owner.guarded(f),item)
        self.canvas.PopupMenu(menu);menu.Destroy()

    def draw(self,dc,palette):
        self.hits=[];c=self.canvas
        for block in self.visible():
            x,y=(self.drag['position'] if self.drag and self.drag['id']==block['id'] else (block['x'],block['y']))
            width,height,pins=geometry(block['board']);point=lambda a,b:c.point(x+a,y+b)
            a,b=point(0,0),point(width,height)
            dc.SetPen(wx.Pen(palette['accent'] if block['id']==self.selected else palette['fg'],2))
            dc.SetBrush(wx.Brush(palette['panel']));dc.DrawRoundedRectangle(a.x,a.y,max(1,b.x-a.x),max(1,b.y-a.y),5)
            font=wx.Font(max(6,round(9*c.zoom)),wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL);dc.SetFont(font)
            dc.SetTextForeground(palette['fg'])
            title=f"{block['ref']} · {block['board']['name']}"
            dc.SetClippingRegion(wx.Rect(a.x+4,a.y+3,max(1,b.x-a.x-8),max(1,round(44*c.zoom))))
            dc.DrawText(title,point(8,6));dc.SetTextForeground(palette['muted']);dc.DrawText('Controller pinout · explicit execution backend',point(8,25));dc.DestroyClippingRegion()
            for pin,side,row in pins:
                boundary=width if side else 0;end=boundary+28 if side else boundary-28
                bound=block.get('bindings',{}).get(pin['id'],{}).get('mode','NC')!='NC'
                color=palette['accent'] if bound else palette['muted']
                dc.SetPen(wx.Pen(color,1));dc.DrawLine(point(boundary,row),point(end,row))
                dc.SetBrush(wx.Brush(color if bound else palette['canvas']));dc.DrawCircle(point(end,row),max(2,round(3*c.zoom)))
                dc.SetTextForeground(palette['fg'])
                label=f"{pin['header']}.{pin['position']}  {pin['label']}"
                start=point(width/2+8 if side else 8,row-9);w=max(1,round((width/2-16)*c.zoom));h=max(1,round(20*c.zoom))
                dc.SetClippingRegion(wx.Rect(start.x,start.y,w,h));dc.DrawLabel(label,wx.Rect(start.x,start.y,w,h),wx.ALIGN_RIGHT if side else wx.ALIGN_LEFT);dc.DestroyClippingRegion()
                self.hits.append((point(end,row),block['id'],pin['id']))
