# SPDX-License-Identifier: Apache-2.0
"""Visual sampled-controller settings; serialization stays outside the UI."""
from copy import deepcopy
import wx


class ControllerVisual(wx.Panel):
    def __init__(self,parent):
        super().__init__(parent);self.data={}
        box=wx.BoxSizer(wx.HORIZONTAL);form=wx.FlexGridSizer(cols=2,hgap=8,vgap=10)
        self.language=wx.Choice(self,choices=['C','C++'])
        self.step=wx.TextCtrl(self)
        self.states=wx.SpinCtrl(self,min=1,max=64)
        for label,control in [('Language',self.language),('Sample interval (s)',self.step),('State variables',self.states)]:
            form.Add(wx.StaticText(self,label=label),0,wx.ALIGN_CENTER_VERTICAL);form.Add(control,1,wx.EXPAND)
        form.AddGrowableCol(1);box.Add(form,0,wx.ALL,10)
        self.preview=wx.ScrolledWindow(self,style=wx.BORDER_NONE);self.preview.SetMinSize((280,150));self.preview.SetScrollRate(0,16)
        self.preview.SetBackgroundStyle(wx.BG_STYLE_PAINT);self.preview.Bind(wx.EVT_PAINT,self.paint)
        self.preview.Bind(wx.EVT_SIZE,lambda e:(self.preview.Refresh(),e.Skip()))
        self.preview.Bind(wx.EVT_LEFT_DCLICK,lambda e:self.edit_pins())
        box.Add(self.preview,1,wx.EXPAND|wx.ALL,5);self.SetSizer(box)

    def edit_pins(self):
        from .controller_pin_dialog import edit_pins
        panel=self.GetParent();panel.owner.guarded(lambda:edit_pins(panel))

    def load(self,config):
        self.data=deepcopy(config);self.data.pop('source',None)
        self.language.SetStringSelection(config['language']);self.step.SetValue(f"{config['step_s']:.12g}");self.states.SetValue(config['state_count'])
        pins=config['pins'];rows=max(sum(p['mode'].endswith('I') for p in pins),sum(p['mode'].endswith('O') for p in pins))
        self.preview.SetVirtualSize((-1,max(150,60+rows*34)))
        self.preview.SetToolTip('Double-click to edit pins\n'+'\n'.join(f"{p['name']} ({p['mode']}): "+(p['node']+' relative to '+p['reference'] if p['mode'].endswith('I') else p['source']) for p in pins))
        self.preview.Refresh()

    def config(self):
        data=deepcopy(self.data);data.update(language=self.language.GetStringSelection(),step_s=float(self.step.GetValue()),state_count=self.states.GetValue());return data

    def paint(self,event):
        dc=wx.AutoBufferedPaintDC(self.preview);self.preview.PrepareDC(dc)
        palette=getattr(self.GetParent().owner,'palette',{})
        dc.SetBackground(wx.Brush(palette.get('panel','#f5f6f8')));dc.Clear()
        dc.SetTextForeground(wx.Colour(palette.get('fg','#202124')))
        pins=self.data.get('pins',[]);inputs=[p for p in pins if p['mode'].endswith('I')];outputs=[p for p in pins if p['mode'].endswith('O')]
        width=max(280,self.preview.GetClientSize().width);left=int(width*.38);right=int(width*.62)
        height=max(95,35+34*max(len(inputs),len(outputs)))
        dc.SetPen(wx.Pen(palette.get('accent','#1769aa'),2));dc.SetBrush(wx.Brush(palette.get('canvas','#ffffff')))
        dc.DrawRoundedRectangle(left,10,right-left,height,6)
        dc.DrawLabel('Controller',wx.Rect(left,15,right-left,22),wx.ALIGN_CENTER)
        font=dc.GetFont();font.SetPointSize(9);dc.SetFont(font)
        for side,items in [('input',inputs),('output',outputs)]:
            for i,pin in enumerate(items):
                y=48+i*34;x=left if side=='input' else right;end=x-18 if side=='input' else x+18
                dc.DrawLine(x,y,end,y);dc.DrawCircle(end,y,3)
                binding=pin['node'] if side=='input' else pin['source']
                label=f"{pin['name']} ({pin['mode']})\n{binding}"
                rect=wx.Rect(3,y-14,max(30,left-25),32) if side=='input' else wx.Rect(right+24,y-14,max(30,width-right-27),32)
                # Clip each pin label to its own side; full binding remains in tooltip/editor.
                dc.SetClippingRegion(rect);dc.DrawLabel(label,rect,wx.ALIGN_RIGHT if side=='input' else wx.ALIGN_LEFT);dc.DestroyClippingRegion()
