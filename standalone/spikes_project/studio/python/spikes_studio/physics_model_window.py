# SPDX-License-Identifier: Apache-2.0
"""Explicit generic lumped-device library with parameter and terminal previews."""
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.patches import Polygon,Circle
from python.spikes.lumped_physics_parts import catalog,build
from .themes import apply_window,figure_theme
from .flat_controls import ActionButton


class PhysicsModelWindow(wx.Frame):
    def __init__(self,owner):
        super().__init__(owner,title='Lumped device models - explicit terminals',size=(1000,750))
        self.SetMinSize((800,620));self.owner=owner;self.entries=catalog();self.fields={};self.model=None
        panel=wx.Panel(self);box=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(box)
        self.note_text='Original generic subcircuit references, not foundry/process or TCAD models. Exported parts retain every declared terminal. No automatic native backend substitution.'
        self.note=wx.StaticText(panel,label=self.note_text)
        self.note.Wrap(930);box.Add(self.note,0,wx.ALL,10)
        self.choice=wx.Choice(panel,choices=[item['name'] for item in self.entries]);self.choice.SetSelection(0);box.Add(self.choice,0,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        row=wx.BoxSizer(wx.HORIZONTAL);self.form=wx.ScrolledWindow(panel,size=(350,-1));self.form.SetScrollRate(0,10);row.Add(self.form,0,wx.EXPAND|wx.ALL,10)
        right=wx.BoxSizer(wx.VERTICAL);self.figure=Figure();self.canvas=FigureCanvasWxAgg(panel,-1,self.figure)
        right.Add(self.canvas,1,wx.EXPAND)
        self.report=wx.TextCtrl(panel,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,160));right.Add(self.report,0,wx.EXPAND|wx.TOP,5)
        row.Add(right,1,wx.EXPAND|wx.ALL,10);box.Add(row,1,wx.EXPAND)
        actions=wx.WrapSizer(wx.HORIZONTAL)
        for label,fn in [('Update preview',self.update_preview),('Export SPICE subcircuit…',self.export),('Review generated model…',self.show_source)]:
            button=ActionButton(panel,label=label);button.Bind(wx.EVT_BUTTON,lambda event,action=fn:owner.guarded(action));actions.Add(button,0,wx.ALL,5)
        box.Add(actions,0,wx.ALIGN_RIGHT|wx.ALL,5)
        self.choice.Bind(wx.EVT_CHOICE,lambda event:self.select())
        self.Bind(wx.EVT_SIZE,self.resized)
        apply_window(self,owner.palette);self.select();self.Show()

    def select(self):
        self.form.DestroyChildren();self.fields={}
        box=wx.BoxSizer(wx.VERTICAL);self.form.SetSizer(box)
        for key,value in self.entries[self.choice.GetSelection()]['defaults'].items():
            label=key.replace('_',' ')
            for suffix,unit in (('_a_per_v2','A/V^2'),('_per_v','1/V'),('_sqrt_v','sqrt(V)'),
                                ('_ohm','ohm'),('_f','F'),('_h','H'),('_s','s'),('_a','A'),('_v','V')):
                if key.endswith(suffix):label=key[:-len(suffix)].replace('_',' ')+' ['+unit+']';break
            box.Add(wx.StaticText(self.form,label=label),0,wx.TOP,7)
            field=wx.TextCtrl(self.form,value=format(value,'.12g'));field.SetName('Physics parameter '+key)
            box.Add(field,0,wx.EXPAND|wx.TOP|wx.BOTTOM,5);self.fields[key]=field
        self.form.Layout();self.form.FitInside();self.update_preview();self.Layout()

    def resized(self,event):
        if hasattr(self,'note'):
            self.note.SetLabel(self.note_text);self.note.Wrap(max(700,self.GetClientSize().width-30))
        if hasattr(self,'canvas'):wx.CallAfter(self.fit_canvas)
        event.Skip()

    def fit_canvas(self):
        if not self:return
        width,height=self.canvas.GetClientSize()
        if width>0 and height>0:
            self.figure.set_size_inches(width/self.figure.dpi,height/self.figure.dpi,forward=False)
            self.canvas.draw()

    def configured(self):
        from python.spikes.netlist import parse_spice_number
        parameters={key:parse_spice_number(field.GetValue(),'scalar') for key,field in self.fields.items()}
        return build(self.entries[self.choice.GetSelection()]['id'],parameters,name='SPK_PHYSICS')

    def update_preview(self):
        # Validate before replacing the previous model/diagram.
        model=self.configured();symbol=self.owner.symbols[model['symbol_id']]
        self.figure.clear();axis=self.figure.add_subplot()
        for item in symbol['primitives']:
            if item['kind'] in ('line','polyline'):
                axis.plot([p[0] for p in item['points']],[p[1] for p in item['points']],color=self.owner.palette['fg'])
            elif item['kind']=='polygon':axis.add_patch(Polygon(item['points'],fill=item.get('fill',False),edgecolor=self.owner.palette['fg'],facecolor=self.owner.palette['fg']))
            elif item['kind']=='circle':axis.add_patch(Circle(item['center'],item['radius'],fill=False,edgecolor=self.owner.palette['fg']))
        for pin,label in zip(symbol['terminals'],model['pins']):
            x,y=pin['at'];a,b=pin['leg_endpoint'];axis.plot([x,a],[y,b],color=self.owner.palette['accent'])
            axis.plot([x],[y],'o',markerfacecolor=self.owner.palette['canvas'],markeredgecolor=self.owner.palette['accent'])
            axis.annotate(label,(x,y),xytext=(6,7),textcoords='offset points')
        anchors=[pin['at'] for pin in symbol['terminals']]
        axis.set_xlim(min(x for x,y in anchors)-25,max(x for x,y in anchors)+25)
        axis.set_ylim(max(y for x,y in anchors)+25,min(y for x,y in anchors)-25)
        axis.set_aspect('equal',adjustable='box');axis.set_axis_off();axis.set_title(model['name'])
        figure_theme(self.figure,self.owner.palette,self.owner.theme_name);self.figure.set_layout_engine('constrained');self.fit_canvas()
        self.model=model
        self.report.SetValue('Model status: '+model['model_status']+'\nTerminal order: '+', '.join(model['pins'])+
                             '\nSupported analyses: '+', '.join(model['supported_analyses'])+
                             '\n'+'\n'.join(model['limitations'])+'\nSymbol conformance: unverified common convention.')

    def export(self):
        model=self.configured()
        with wx.FileDialog(self,'Export original generic SPICE model',defaultFile=model['kind']+'.lib',wildcard='SPICE library (*.lib)|*.lib',style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal()==wx.ID_OK:
                from pathlib import Path
                Path(dialog.GetPath()).write_text(model['source'],encoding='ascii')

    def show_source(self):
        model=self.configured()
        with wx.Dialog(self,title='Generated SPICE model - all terminals retained',size=(800,600),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
            box=wx.BoxSizer(wx.VERTICAL);box.Add(wx.TextCtrl(dialog,value=model['source'],style=wx.TE_MULTILINE|wx.TE_READONLY),1,wx.EXPAND|wx.ALL,10)
            box.Add(dialog.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,8);dialog.SetSizer(box);dialog.ShowModal()
