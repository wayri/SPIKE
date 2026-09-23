"""No-code IC package geometry editor with draggable, grid-snapped terminals."""
import json
import math
from copy import deepcopy
from pathlib import Path
import wx
from . import symbol_design as design


class SymbolCanvas(wx.Panel):
    def __init__(self,parent):
        super().__init__(parent);self.editor=parent;self.scale=3.;self.drag=None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT,self.paint);self.Bind(wx.EVT_LEFT_DOWN,self.down)
        self.Bind(wx.EVT_MOTION,self.motion);self.Bind(wx.EVT_LEFT_UP,self.up)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST,lambda e:setattr(self,'drag',None))
        self.Bind(wx.EVT_MOUSEWHEEL,self.wheel)
    def point(self,p):
        w,h=self.GetClientSize();return (round(w/2+p[0]*self.scale),round(h/2+p[1]*self.scale))
    def local(self,p):
        w,h=self.GetClientSize();return ((p.x-w/2)/self.scale,(p.y-h/2)/self.scale)
    def wheel(self,e):self.scale=max(.5,min(8,self.scale*(1.15 if e.GetWheelRotation()>0 else 1/1.15)));self.Refresh()
    def paint(self,e):
        dc=wx.AutoBufferedPaintDC(self);p=getattr(self.editor.owner,'palette',{})
        dc.SetBackground(wx.Brush(p.get('canvas','#171f26')));dc.Clear();dc.SetTextForeground(p.get('fg','#e5edf3'))
        w,h=self.GetClientSize();spacing=max(5,round(self.editor.symbol['grid']*self.scale))
        dc.SetPen(wx.Pen(p.get('grid','#34434e')))
        for x in range(w//2%spacing,w,spacing):
            for y in range(h//2%spacing,h,spacing):dc.DrawPoint(x,y)
        dc.SetPen(wx.Pen(p.get('fg','#e5edf3'),2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
        for item in self.editor.symbol['primitives']:
            if item['kind'] in ('polygon','polyline','line'):dc.DrawLines([self.point(p) for p in item['points']])
            elif item['kind']=='circle':dc.DrawCircle(self.point(item['center']),round(item['radius']*self.scale))
        for i,pin in enumerate(self.editor.symbol['terminals']):
            dc.SetPen(wx.Pen('#f4ba62' if i==self.editor.selected else p.get('accent','#71c9d8'),2))
            a,b=self.point(pin['at']),self.point(pin['leg_endpoint']);dc.DrawLine(*a,*b);dc.DrawCircle(*a,4)
            dc.DrawText(pin['id']+' '+pin['name'],a[0]+5,a[1]-19)
        high=self.point(self.editor.symbol['body_keepout']['max']);dc.SetBrush(wx.Brush('#71c9d8'));dc.DrawRectangle(high[0]-5,high[1]-5,10,10)
    def down(self,e):
        for i,p in enumerate(self.editor.symbol['terminals']):
            x,y=self.point(p['at'])
            if abs(x-e.x)<12 and abs(y-e.y)<12:
                self.editor.select(i);self.drag=('pin',i,deepcopy(self.editor.symbol));self.CaptureMouse();return
        x,y=self.point(self.editor.symbol['body_keepout']['max'])
        if abs(x-e.x)<12 and abs(y-e.y)<12:self.drag=('body',None,deepcopy(self.editor.symbol));self.CaptureMouse()
    def motion(self,e):
        if not self.drag or not e.Dragging():return
        x,y=self.local(e.GetPosition());kind,i,original=self.drag
        try:
            self.editor.symbol=design.drag_pin(original,i,x,y) if kind=='pin' else design.resize(original,2*abs(x),2*abs(y))
            self.editor.status.SetLabel('Release to commit. Pins snap to the nearest body edge and grid.');self.Refresh()
        except ValueError as error:self.editor.status.SetLabel(str(error))
    def up(self,e):
        if not self.drag:return
        original=self.drag[2];self.drag=None
        if self.HasCapture():self.ReleaseMouse()
        if original!=self.editor.symbol:self.editor.history.append(original)
        self.editor.refresh()


class SymbolDesignerPanel(wx.Panel):
    def __init__(self,parent,owner=None):
        super().__init__(parent);self.owner=owner or parent;self.symbol=design.new_symbol();self.selected=0;self.history=[]
        root=wx.BoxSizer(wx.VERTICAL);bar=wx.BoxSizer(wx.HORIZONTAL)
        for label,handler in [('New IC',self.new),('Open…',self.load),('Save symbol…',self.save),('Add to library',self.publish),('Undo',self.undo)]:
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e,h=handler:self.guard(h));bar.Add(b,0,wx.RIGHT,6)
        root.Add(bar,0,wx.ALL,10)
        root.Add(wx.StaticText(self,label='Drag pin circles onto an edge. Lower-right handle rebuilds a rectangular IC body. Mouse wheel zooms.'),0,wx.LEFT|wx.BOTTOM,10)
        middle=wx.BoxSizer(wx.HORIZONTAL);self.canvas=SymbolCanvas(self);middle.Add(self.canvas,1,wx.EXPAND|wx.ALL,8)
        form=wx.BoxSizer(wx.VERTICAL);self.fields={}
        for key,label,value in [('id','Library ID','user.ic'),('name','Part name','Custom IC'),('number','Pin number','1'),('pin_name','Pin name','IN')]:
            form.Add(wx.StaticText(self,label=label),0,wx.TOP,6);field=wx.TextCtrl(self,value=value);self.fields[key]=field;form.Add(field,0,wx.EXPAND)
        form.Add(wx.StaticText(self,label='Pin side'),0,wx.TOP,6);self.side=wx.Choice(self,choices=['west','east','north','south']);self.side.SetSelection(0);form.Add(self.side,0,wx.EXPAND)
        form.Add(wx.StaticText(self,label='Position along edge (grid units)'),0,wx.TOP,6);self.position=wx.SpinCtrl(self,min=-10000,max=10000);form.Add(self.position,0,wx.EXPAND)
        for label,handler in [('Apply pin',self.apply_pin),('Add pin',self.add_pin),('Remove pin',self.remove_pin)]:
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e,h=handler:self.guard(h));form.Add(b,0,wx.EXPAND|wx.TOP,6)
        self.pins=wx.ListBox(self);self.pins.Bind(wx.EVT_LISTBOX,lambda e:self.select(e.GetSelection()));form.Add(self.pins,1,wx.EXPAND|wx.TOP,8)
        middle.Add(form,0,wx.EXPAND|wx.ALL,10);root.Add(middle,1,wx.EXPAND)
        self.status=wx.StaticText(self,label='Geometry only: attach and qualify an electrical model separately. Pin order does not create a simulation model.')
        root.Add(self.status,0,wx.ALL,10);self.SetSizer(root);self.refresh()
    def guard(self,fn):
        try:fn()
        except (ValueError,KeyError,TypeError,OSError) as error:wx.MessageBox(str(error),'Symbol designer',wx.OK|wx.ICON_WARNING,self)
    def commit(self,value):self.history.append(deepcopy(self.symbol));self.symbol=value;self.refresh()
    def refresh(self):
        self.fields['id'].ChangeValue(self.symbol['id']);self.fields['name'].ChangeValue(self.symbol['name'])
        self.pins.Set([p['id']+' — '+p['name'] for p in self.symbol['terminals']]);self.select(min(self.selected,len(self.symbol['terminals'])-1));self.canvas.Refresh()
    def select(self,index):
        self.selected=index;p=self.symbol['terminals'][index];self.pins.SetSelection(index)
        self.fields['number'].ChangeValue(p['id']);self.fields['pin_name'].ChangeValue(p['name']);side=p.get('direction','west');self.side.SetStringSelection(side)
        self.position.SetValue(round(p['at'][1 if side in ('west','east') else 0]/self.symbol['grid']));self.canvas.Refresh()
    def draft(self):
        s=deepcopy(self.symbol)
        for key in ('id','name'):
            s[key]=self.fields[key].GetValue().strip()
            if not s[key]:raise ValueError('Library ID and name are required')
        return s
    def apply_pin(self):
        self.commit(design.set_pin(self.draft(),self.selected,self.fields['number'].GetValue(),self.fields['pin_name'].GetValue(),self.side.GetStringSelection(),self.position.GetValue()*self.symbol['grid']))
    def add_pin(self):
        s=self.draft();used={p['id'] for p in s['terminals']};number=next(str(n) for n in range(1,1000) if str(n) not in used)
        for side in ('west','east','north','south'):
            low,high=s['body_keepout']['min'],s['body_keepout']['max'];axis=1 if side in ('west','east') else 0
            for step in range(math.ceil(low[axis]/s['grid']),math.floor(high[axis]/s['grid'])+1):
                pos=step*s['grid']
                try:value=design.set_pin(s,None,number,'PIN'+number,side,pos)
                except ValueError:continue
                self.selected=len(s['terminals']);self.commit(value);return
        raise ValueError('No free pin sites. Enlarge the body first.')
    def remove_pin(self):
        s=self.draft()
        if len(s['terminals'])==1:raise ValueError('A symbol needs at least one pin')
        del s['terminals'][self.selected];self.commit(design.checked(s))
    def undo(self):
        if self.history:self.symbol=self.history.pop();self.refresh()
    def new(self):self.commit(design.new_symbol())
    def load(self):
        with wx.FileDialog(self,'Open symbol',wildcard='Symbol JSON|*.json',style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST) as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            value=json.loads(Path(dialog.GetPath()).read_text(encoding='utf-8'))
            if 'symbols' in value:
                items=value['symbols']
                if not items:raise ValueError('Library has no symbols')
                with wx.SingleChoiceDialog(self,'Select symbol','Open library',[s['name'] for s in items]) as chooser:
                    if chooser.ShowModal()!=wx.ID_OK:return
                    value=items[chooser.GetSelection()]
            if any(p.get('kind') not in ('polygon','polyline','line','circle') for p in value['primitives']):raise ValueError('This visual editor supports polygon, line and circle geometry; use the advanced editor for other primitives.')
            self.commit(design.checked(value))
    def save(self):
        value=design.checked(self.draft())
        with wx.FileDialog(self,'Save symbol',wildcard='Symbol JSON|*.json',style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal()==wx.ID_OK:
                library={'contract':'spikes/studio-symbol-library/v1','library_id':'user.local','version':'1.0.0','license':'User-supplied; review before redistribution','symbols':[value]}
                Path(dialog.GetPath()).write_text(json.dumps(library,indent=2),encoding='utf-8');self.symbol=value;self.status.SetLabel('Saved reusable symbol library. Electrical behavior still requires a separate qualified model.')
    def publish(self):
        value=design.checked(self.draft())
        if not hasattr(self.owner,'symbols'):raise ValueError('No library connected; use Save symbol instead.')
        if value['id'] in self.owner.symbols and wx.MessageBox('Replace this library symbol?','Confirm replacement',wx.YES_NO|wx.NO_DEFAULT,self)!=wx.YES:return
        self.owner.symbols[value['id']]=value;self.owner.filter_library();self.symbol=value;self.status.SetLabel('Added to session symbol library. Save the library to persist. No electrical model has been generated.')
