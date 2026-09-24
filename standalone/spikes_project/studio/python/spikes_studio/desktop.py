"""Runnable wxWidgets Studio workbench; plots consume owned-engine results."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import io
import json
import os
from pathlib import Path
import threading
import time

import numpy as np
import wx
import wx.grid
import wx.stc
import wx.aui
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg, NavigationToolbar2WxAgg
from matplotlib.ticker import EngFormatter

from .document import Document, RC_DECK, Keymap, COMMANDS, write_json
from .signal_math import SignalMath, FUNCTION_HELP
from .interchange import import_text, export_netlist
from .ide import analyze, read_vcd
from .result_file import save_result, load_result
from .simulation_setup import RunHistory, effective_source
from .simulation_manager import SimulationManager, ThermalSetup
from .directive_manager import DirectiveManager, DirectiveEditor
from .frequency_panel import FrequencyPanel
from .themes import PALETTES,load_theme,native_appearance,apply_window,figure_theme,toolbar_icon
from .power_panel import PowerPanel
from .analytics_panel import AnalyticsPanel


def button(parent, title, handler, sizer):
    widget = wx.Button(parent, label=title)
    widget.Bind(wx.EVT_BUTTON, handler)
    sizer.Add(widget, 0, wx.ALL, 3)
    return widget


def text_editor(parent, text=""):
    editor = wx.stc.StyledTextCtrl(parent)
    editor.SetText(text)
    editor.SetMarginType(0, wx.stc.STC_MARGIN_NUMBER)
    editor.SetMarginWidth(0, 42)
    editor.StyleSetFont(wx.stc.STC_STYLE_DEFAULT, wx.Font(10, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
    editor.StyleClearAll()
    editor.SetTabWidth(4)
    editor.SetIndent(4)
    editor.SetWrapMode(wx.stc.STC_WRAP_WORD)
    return editor


class PropertiesForm:
    def initialize(self, parent):
        self.owner, self.fields = parent, {}
        self.document_id=parent.doc.data['id'];self.revision=parent.doc.data['revision'];self.applied=False
        selection = [p for p in parent.doc.data["components"] if p["id"] in parent.canvas.selected]
        if not selection: raise ValueError("Select a component first")
        self.ids = [p["id"] for p in selection]
        self.original = {}
        from .part_properties import form,parse,VALUE_LABELS
        project=parse(parent.doc.data['source'])
        self.forms=[form(parent.doc.data['source'],p['ref'],project) for p in selection]
        self.same_kind=len({f['kind'] for f in self.forms})==1
        self.model_editable=self.same_kind and all(f['editable'] for f in self.forms)
        self.mode_original=self.forms[0]['mode'] if len({f['mode'] for f in self.forms})==1 else None
        self.model_fields={};self.model_original={};self.model_cache={};self.last_mode=None
        layout = wx.BoxSizer(wx.VERTICAL)
        fidelity_button=wx.Button(self,label='Model fidelity / inherited policy…')
        from .fidelity_dialog import show as show_fidelity
        fidelity_button.Bind(wx.EVT_BUTTON,lambda e:parent.guarded(lambda:show_fidelity(parent,selection[0]['ref'])))
        layout.Add(fidelity_button,0,wx.ALL,8)
        layout.Add(wx.StaticText(self, label="Selected: " + ", ".join(p["ref"] for p in selection)), 0, wx.ALL, 12)
        self.error=wx.InfoBar(self);layout.Add(self.error,0,wx.EXPAND|wx.LEFT|wx.RIGHT,8)
        header=wx.FlexGridSizer(cols=2,hgap=12,vgap=6);header.AddGrowableCol(0,1);header.AddGrowableCol(1,1)
        self.value_label=wx.StaticText(self,label=VALUE_LABELS.get(selection[0]['kind'],'Value') if self.same_kind else 'Value — select one component family')
        header.Add(self.value_label);header.Add(wx.StaticText(self,label='Simulation model type'))
        value=self.forms[0]['value'] if len({f['value'] for f in self.forms})==1 else '<multiple values>'
        self.fields['value']=wx.TextCtrl(self,value=value);self.original['value']=value
        self.fields['value'].SetToolTip('Engineering suffixes: 4.7k, 220u, 10n. SPICE m means milli; use Meg for mega.')
        header.Add(self.fields['value'],1,wx.EXPAND)
        self.model_options=self.forms[0]['options'] if self.model_editable else []
        if self.model_options and self.mode_original is None:self.model_options=[(None,'Multiple models — keep unchanged'),*self.model_options]
        self.model_choice=wx.Choice(self,choices=[label for _,label in self.model_options] or ['Source-defined / not editable here'])
        self.model_choice.SetSelection(next((i for i,(mode,_) in enumerate(self.model_options) if mode==self.mode_original),0))
        self.model_choice.Enable(self.model_editable);header.Add(self.model_choice,1,wx.EXPAND)
        layout.Add(header,0,wx.EXPAND|wx.ALL,12)
        if self.same_kind and selection[0]['kind'] in ('resistor','capacitor','inductor'):
            row=wx.BoxSizer(wx.HORIZONTAL);self.preferred_series=wx.Choice(self,choices=['E6','E12','E24']);self.preferred_series.SetSelection(2);row.Add(self.preferred_series,0,wx.ALL,3)
            button(self,'Nearest standard value…',self.preferred_value,row);layout.Add(row,0,wx.LEFT|wx.RIGHT,8)
        hint=wx.StaticText(self,label='Enter a value with SI units or SPICE suffixes. Model fields below change the actual netlist.');hint.Wrap(340 if self.docked else 700)
        layout.Add(hint,0,wx.LEFT|wx.RIGHT|wx.BOTTOM,12)
        self.book = wx.aui.AuiNotebook(self,style=wx.aui.AUI_NB_TOP|wx.aui.AUI_NB_SCROLL_BUTTONS|wx.aui.AUI_NB_WINDOWLIST_BUTTON)
        groups = [("Parameters", [("parameters", "User metadata (JSON; not automatically stamped)"), ("temperature_k", "Declared temperature [K] (metadata)"), ("package", "Package"), ("variant", "Assembly variant")]),
                  ("Pins", [("nodes", "Ordered electrical nodes (JSON array)")]),
                  ("Limits", [("limits", 'Declared limits in SI (JSON; e.g. {"power_w": 0.25})')]),
                  ("Model & evidence", [("model_source", "Model source notes (inert; use the selector to bind an executable model)"), ("evidence", "Datasheet references / qualification evidence")])]
        for title, fields in groups:
            panel = wx.ScrolledWindow(self.book);panel.SetScrollRate(0,12); box = wx.BoxSizer(wx.VERTICAL)
            if title=='Parameters':
                self.parameter_panel=panel;self.parameter_box=box
                self.model_panel=wx.Panel(panel);self.model_box=wx.BoxSizer(wx.VERTICAL);self.model_panel.SetSizer(self.model_box)
                box.Add(self.model_panel,0,wx.EXPAND|wx.ALL,6)
            for key, label in fields:
                value = selection[0][key]
                mixed = any(p[key] != value for p in selection)
                rendered = "<multiple values>" if mixed else json.dumps(value, indent=2) if isinstance(value, (dict, list)) else str(value)
                self.original[key] = rendered
                box.Add(wx.StaticText(panel, label=label), 0, wx.TOP | wx.LEFT, 8)
                control = wx.TextCtrl(panel, value=rendered, style=wx.TE_MULTILINE if key in ("limits", "parameters", "model_source", "evidence") else 0)
                if key in ('limits','model_source','evidence'):control.SetMinSize((-1,110))
                if key=='parameters':control.SetMinSize((-1,55))
                box.Add(control, 0, wx.EXPAND | wx.ALL, 8)
                self.fields[key] = control
            panel.SetSizer(box); self.book.AddPage(panel, title)
        layout.Add(self.book, 1, wx.EXPAND | wx.ALL, 8)
        actions = wx.BoxSizer(wx.HORIZONTAL)
        button(self, "Reload selection" if self.docked else "Cancel", lambda e: self.EndModal(wx.ID_CANCEL), actions)
        if not self.docked:button(self,"Pin to side",self.pin_to_side,actions)
        button(self, "Apply changes", self.apply, actions)
        layout.Add(actions, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(layout)
        self.model_choice.Bind(wx.EVT_CHOICE,self.render_model)
        self.render_model()
        apply_window(self,parent.palette)

    def dirty(self):
        return (any(c.GetValue()!=self.original[k] for k,c in self.fields.items()) or
                self.chosen_mode()!=self.mode_original or
                any(c.GetValue()!=self.model_original[k] for k,c in self.model_fields.items()))

    def preferred_value(self,event):
        try:
            from .preferred_values import recommend
            from .part_properties import parse
            kind=self.forms[0]['kind'];prefix={'resistor':'R','capacitor':'C','inductor':'L'}[kind]
            value=parse('Value check\n'+prefix+'1 a 0 '+self.fields['value'].GetValue()+'\n.op\n.end\n').elements[0].value
            result=recommend(value,self.preferred_series.GetStringSelection())
            text=f"Nearest: {result['nearest']:.12g} SI ({result['error_percent']:+.3g}%)\nLower: {result['lower']:.12g} · Upper: {result['upper']:.12g}\n\nUse nearest in this draft? Availability and ratings must still be checked."
            if wx.MessageBox(text,'Preferred passive value',wx.YES_NO|wx.NO_DEFAULT,self)==wx.YES:self.fields['value'].SetValue(format(result['nearest'],'.12g'))
        except Exception as exc:self.error.ShowMessage(str(exc),wx.ICON_ERROR)

    def pin_to_side(self,event):
        if self.dirty():
            self.error.ShowMessage('Apply or cancel this draft before pinning; no edits were discarded.',wx.ICON_WARNING);return
        self.EndModal(wx.ID_CANCEL);wx.CallAfter(self.owner.pin_properties,True)

    def chosen_mode(self):
        index=self.model_choice.GetSelection()
        return self.model_options[index][0] if self.model_options and index>=0 else None

    def render_model(self,event=None):
        from .part_properties import field_specs,model_names
        if self.last_mode is not None:self.model_cache[self.last_mode]={k:c.GetValue() for k,c in self.model_fields.items()}
        self.model_box.Clear(delete_windows=True);self.model_fields={};self.model_original={}
        mode=self.chosen_mode();self.last_mode=mode;kind=self.forms[0]['kind']
        editable=self.model_editable and mode is not None
        self.fields['value'].Enable(editable and kind not in ('diode','voltage_controlled_switch') and mode!='pwl')
        notes={'ideal':'Ideal electrical model; no parasitics or thermal loss are inferred.',
               'dc':'DC value above; optional AC magnitude and phase below.',
               'pulse':'Value above is the initial level. Enter the high level and timing below.',
               'pwl':'Enter explicit time/value pairs below. The Value box is not used.',
               'named_model':'Binds this instance to an existing .MODEL D card without changing other parts.',
               'shockley':'Creates a private .MODEL D card for this instance. Static Shockley; no reverse recovery or charge storage.',
               'smooth_switch':'Smooth voltage-controlled switch; transition width is not hysteresis.'}
        note=notes.get(mode,'Mixed or unsupported device selection: metadata can still be edited; use Circuit text for electrical changes.')
        hint=wx.StaticText(self.model_panel,label=note);hint.Wrap(320 if self.docked else 670);self.model_box.Add(hint,0,wx.ALL,4)
        grid=wx.FlexGridSizer(cols=1 if self.docked else 2,hgap=10,vgap=7);grid.AddGrowableCol(0 if self.docked else 1,1)
        if editable:
            for key,label,default in field_specs(kind,mode):
                values=[f['fields'].get(key,default) for f in self.forms]
                original=values[0] if len(set(values))==1 else '<multiple values>'
                value=self.model_cache.get(mode,{}).get(key,original)
                grid.Add(wx.StaticText(self.model_panel,label=label),0,wx.ALIGN_CENTER_VERTICAL)
                if key=='model_name':control=wx.ComboBox(self.model_panel,value=value,choices=model_names(self.owner.doc.data['source']))
                else:control=wx.TextCtrl(self.model_panel,value=value,style=wx.TE_MULTILINE if key=='points' else 0)
                if key=='points':control.SetMinSize((-1,100))
                self.model_fields[key]=control;self.model_original[key]=original;grid.Add(control,1,wx.EXPAND)
        self.model_box.Add(grid,0,wx.EXPAND|wx.ALL,4)
        self.model_panel.Layout();self.parameter_panel.Layout();self.parameter_panel.FitInside();self.Layout()
        apply_window(self.model_panel,self.owner.palette)
        if event:self.book.SetSelection(0)

    def apply(self, event=None):
        try:
            if self.owner.job_running:raise ValueError('Stop simulation before changing component properties')
            if self.docked and (self.owner.doc.data['id']!=self.document_id or self.owner.doc.data['revision']!=self.revision):raise ValueError('The circuit changed while this draft was open. Copy any needed edits, then Reload selection before applying.')
            self.owner.require_clean_directive_source()
            changes = {}
            for key, control in self.fields.items():
                if key=='value' and not control.IsEnabled():continue
                value = control.GetValue()
                if value == self.original[key]: continue
                if key in ("nodes", "limits", "parameters"):
                    value = json.loads(value)
                    if key == "nodes" and (not isinstance(value, list) or not all(isinstance(x, str) for x in value)): raise ValueError("Nodes must be an array of strings")
                    if key != "nodes" and not isinstance(value, dict): raise ValueError("Expected a JSON object")
                if key == "temperature_k": value = float(value)
                changes[key] = value
            mode=self.chosen_mode()
            fields={key:control.GetValue() for key,control in self.model_fields.items() if control.GetValue()!=self.model_original[key]}
            model={'mode':mode,'fields':fields} if self.model_editable and mode is not None and (mode!=self.mode_original or fields) else None
            if changes or model: self.owner.doc.update(self.ids, changes,model=model)
            self.applied=True
            self.owner.refresh_document()
            self.EndModal(wx.ID_OK)
        except Exception as exc:self.error.ShowMessage(str(exc),wx.ICON_ERROR);self.Layout()


class Properties(PropertiesForm,wx.Dialog):
    docked=False
    def __init__(self,parent):
        wx.Dialog.__init__(self,parent,title='Component properties — value & model',size=(780,730),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.SetMinSize((640,560));self.initialize(parent)


class DockedProperties(PropertiesForm,wx.Panel):
    docked=True
    def __init__(self,owner,parent):
        wx.Panel.__init__(self,parent);self.initialize(owner)
    def EndModal(self,code):wx.CallAfter(self.owner.sync_properties,True)


class SchematicCanvas(wx.Panel):
    def __init__(self, owner, parent):
        super().__init__(parent)
        self.owner, self.selected, self.zoom = owner, set(), 1.0
        self.offset = np.array([20., 15.]); self.probe_mode = None; self.first_node = None
        self.drag_start = None; self.drag_part = None; self.hits = []; self.pins = []
        self.move_origin = None; self.move_positions = {}; self.move_delta = np.zeros(2)
        self.directive_hits=[];self.selected_directive=None;self.moving_directive=None
        self.instrument_hits=[];self.moving_instrument=None
        self.controller_hit=None
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.click)
        self.Bind(wx.EVT_LEFT_UP, self.move_end)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self.capture_lost)
        self.Bind(wx.EVT_LEFT_DCLICK,self.double_click)
        self.Bind(wx.EVT_MIDDLE_DOWN, self.pan_start)
        self.Bind(wx.EVT_MIDDLE_UP, self.pan_end)
        self.Bind(wx.EVT_MOTION, self.motion)
        self.Bind(wx.EVT_MOUSEWHEEL, self.wheel)
        self.Bind(wx.EVT_RIGHT_UP, self.context)
        self.Bind(wx.EVT_KEY_DOWN,self.placement_key)
        self.wire_start=None;self.wire_mode=False;self.wire_pins=[]
        self.selection_path=[];self.selection_tool='box';self.selection_add=False
        self.designer_tool=None;self.annotation_hits=[];self.selected_annotation=None;self.moving_annotation=None
        from .designer_workspace import SchematicDropTarget
        self.SetDropTarget(SchematicDropTarget(self))

    def placement_key(self,event):
        if event.GetKeyCode()==wx.WXK_ESCAPE and (self.selection_path or self.designer_tool):
            self.selection_path=[];self.designer_tool=None
            if self.HasCapture():self.ReleaseMouse()
            self.SetCursor(wx.NullCursor);self.Refresh();return
        if event.GetKeyCode()==wx.WXK_ESCAPE and self.wire_mode:
            self.wire_mode=False;self.wire_start=None;self.SetCursor(wx.NullCursor);self.owner.SetStatusText('Wire cancelled');return
        if event.GetKeyCode()==wx.WXK_ESCAPE and self.owner.pending_library_placement:
            self.owner.pending_library_placement=None;self.SetCursor(wx.NullCursor);self.Refresh();self.owner.SetStatusText('Library placement cancelled')
        else:event.Skip()

    def point(self, x, y): return wx.Point(round(x*self.zoom+self.offset[0]), round(y*self.zoom+self.offset[1]))
    def world(self, point): return (np.array([point.x, point.y]) - self.offset) / self.zoom

    def double_click(self,event):
        from .subsheet import enter
        part=next((part for rect,part in reversed(self.hits) if rect.Contains(event.GetPosition())),None)
        if part and enter(self.owner,part['ref']):return
        annotation=next((item for rect,item in self.annotation_hits if rect.Contains(event.GetPosition())),None)
        if annotation:self.owner.guarded(lambda:self.owner.edit_canvas_annotation(annotation));return
        if self.controller_hit and self.controller_hit.Contains(event.GetPosition()):self.owner.book.SetSelection(12)
        elif any(rect.Contains(event.GetPosition()) for rect,item in self.instrument_hits):
            self.owner.guarded(self.owner.manage_instruments)
        else:self.owner.guarded(lambda:self.owner.edit_directive(self.selected_directive) if self.selected_directive else self.owner.properties())

    def paint(self, event):
        colors=self.owner.palette
        dc = wx.AutoBufferedPaintDC(self); dc.SetBackground(wx.Brush(colors['canvas'])); dc.Clear()
        self.hits, self.pins = [], []
        self.directive_hits=[]
        dc.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        width, height = self.GetClientSize()
        dc.SetPen(wx.Pen(colors['grid'], 1))
        spacing=max(8,round(20*self.zoom))
        for x in range(round(self.offset[0])%spacing, width if self.owner.canvas_grid else 0, spacing):
            for y in range(round(self.offset[1])%spacing, height, spacing): dc.DrawPoint(x, y)
        dc.SetTextForeground(colors['muted'])
        dc.DrawText("Click: select  |  E: properties  |  Space: rotate  |  W: wire  |  Wheel: zoom  |  Middle-drag: pan", 12, 10)
        if self.owner.pending_library_placement:
            record,mapping,count=self.owner.pending_library_placement
            dc.SetTextForeground(colors['accent']);dc.DrawText(f"PLACE {count} × {record['name']} — click canvas; Escape cancels",12,32)
        from .editor_geometry import transform,route
        from .pin_geometry import pins as component_pins, bounds as pin_bounds
        positions={part['id']:dict(part,x=part['x']+(self.move_delta[0] if part['id'] in self.move_positions else 0),y=part['y']+(self.move_delta[1] if part['id'] in self.move_positions else 0)) for part in self.owner.doc.data['components']}
        dc.SetPen(wx.Pen(colors['accent'],2))
        for wire in self.owner.doc.data['wires']:
            display=wire
            if getattr(self,'moving_wire',None)==wire['id']:
                display=dict(wire,waypoints=[[x+float(self.move_delta[0]),y+float(self.move_delta[1])] for x,y in route(positions,wire)])
            dc.DrawLines([self.point(*at) for at in route(positions,display)])
        if self.wire_mode and self.wire_start:
            from .editor_geometry import terminal
            points=[terminal(positions[self.wire_start[0]],self.wire_start[1])]
            for target in getattr(self,'wire_corners',[])+[getattr(self,'wire_tip',points[0])]:
                points.extend([(target[0],points[-1][1]),tuple(target)])
            dc.SetPen(wx.Pen(colors['accent'],2,wx.PENSTYLE_SHORT_DASH))
            if len(points)>1:dc.DrawLines([self.point(*at) for at in points])
        self.wire_pins=[]
        for part in self.owner.doc.data["components"]:
            x, y = np.array([part["x"], part["y"]]) + (self.move_delta if part['id'] in self.move_positions else 0)
            geometry=dict(part,x=x,y=y)
            p = lambda a, b: self.point(*transform(geometry,a,b))
            left,right=p(-55,0),p(55,0)
            lo,top,hi,bottom=pin_bounds(part)
            corners=[p(a,b) for a,b in ((lo,top),(hi,top),(hi,bottom),(lo,bottom))]
            rect=wx.Rect(min(v.x for v in corners),min(v.y for v in corners),max(v.x for v in corners)-min(v.x for v in corners),max(v.y for v in corners)-min(v.y for v in corners))
            self.hits.append((rect, part))
            if part["id"] in self.selected:
                dc.SetPen(wx.Pen(colors['accent'], 1, wx.PENSTYLE_SHORT_DASH)); dc.SetBrush(wx.Brush(colors['selected'])); dc.DrawRectangle(rect)
            dc.SetPen(wx.Pen(colors['fg'], 2)); dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawLine(left, p(-28,0)); dc.DrawLine(p(28,0), right)
            for pin in component_pins(part)[2:]:dc.DrawLine(p(*pin.body),p(*pin.anchor))
            kind = part["kind"]
            if kind == "capacitor":
                dc.DrawLine(p(-28,0),p(-7,0)); dc.DrawLine(p(7,0),p(28,0))
                dc.DrawLine(p(-7,-22),p(-7,22)); dc.DrawLine(p(7,-22),p(7,22))
            elif kind == "inductor":
                for center in (-18, 0, 18):dc.DrawLines([p(center-9*np.cos(t),-13*np.sin(t)) for t in np.linspace(0,np.pi,15)])
                dc.DrawLine(p(-28,0),p(-27,0));dc.DrawLine(p(27,0),p(28,0))
            elif kind == 'diode':
                dc.DrawLine(p(-28,0),p(-16,0));dc.DrawLine(p(16,0),p(28,0))
                dc.DrawLines([p(-16,-18),p(-16,18),p(16,0),p(-16,-18)])
                dc.DrawLine(p(16,-18),p(16,18))
            elif kind in ("voltage_source", "current_source"):
                dc.DrawCircle(p(0,0),round(28*self.zoom))
                if kind=='voltage_source':
                    dc.DrawLine(p(-19,0),p(-7,0));dc.DrawLine(p(-13,-6),p(-13,6));dc.DrawLine(p(7,0),p(19,0))
                else:
                    dc.DrawLine(p(-16,0),p(16,0));dc.DrawLines([p(7,-7),p(16,0),p(7,7)])
            else:
                body_height=22 if len(part['nodes'])>2 else 17
                dc.DrawLines([p(a,b) for a,b in ((-28,-body_height),(28,-body_height),(28,body_height),(-28,body_height),(-28,-body_height))])
                if kind != "resistor": dc.DrawText(kind[:6],p(-24,-10))
            dc.SetTextForeground(colors['fg'])
            dc.DrawText(part['ref'],self.point(x+15,y-40) if part.get('rotation',0)%180 else self.point(x-28,y-43))
            dc.DrawText(part['value'],self.point(x+15,y+12) if part.get('rotation',0)%180 else self.point(x-28,y+24))
            findings=self.owner.part_alerts.get(part['id'],{}).get('findings',[])
            levels={v['severity'] for v in findings}
            if 'exceeded' in levels or 'warning' in levels:
                color=colors['danger'] if 'exceeded' in levels else colors['accent']
                dc.SetPen(wx.Pen(color,2));dc.SetBrush(wx.Brush(colors['canvas']));dc.DrawCircle(p(40,-30),10)
                dc.SetTextForeground(color);dc.DrawText('!',p(37,-39));dc.SetBrush(wx.TRANSPARENT_BRUSH);dc.DrawLines([p(-33,-22),p(33,-22),p(33,22),p(-33,22),p(-33,-22)])
            dc.SetPen(wx.Pen(colors['accent'],2)); dc.SetBrush(wx.Brush(colors['canvas']))
            for pin,node in zip(component_pins(part),part['nodes']):
                position=p(*pin.anchor)
                self.wire_pins.append((position,part['id'],pin.index))
                dc.DrawCircle(position,4); self.pins.append((position,node,part["id"]))
                dc.DrawText((pin.label+': ' if len(part['nodes'])>2 else '')+node,position.x+8,position.y+8)
            for probe in self.owner.doc.data["probes"]:
                if probe.get("anchor") == part["id"]:
                    dc.SetTextForeground(colors['accent']); dc.DrawText(probe["expression"],p(-45,60))
        self.controller_hit=None
        controller=self.owner.doc.data.get('controller_setup')
        if controller:
            at=self.point(850,330);width=round(250*self.zoom);height=round((80+22*len(controller['pins']))*self.zoom)
            rect=wx.Rect(at.x,at.y,width,height);self.controller_hit=rect
            dc.SetPen(wx.Pen(colors['accent'],2));dc.SetBrush(wx.Brush(colors['panel']));dc.DrawRoundedRectangle(rect,5)
            dc.SetTextForeground(colors['fg']);dc.DrawText('Sampled controller · '+controller['language'],at.x+8,at.y+8)
            dc.SetTextForeground(colors['muted']);dc.DrawText(f"tick={controller['step_s']:g}s · double-click to edit",at.x+8,at.y+28)
            for index,pin in enumerate(controller['pins']):
                input_pin=pin['mode'].endswith('I');y=at.y+round((65+22*index)*self.zoom);x=at.x if input_pin else at.x+width
                terminal=x-round(20*self.zoom) if input_pin else x+round(20*self.zoom)
                dc.SetPen(wx.Pen(colors['accent'],1));dc.DrawLine(x,y,terminal,y);dc.SetBrush(wx.Brush(colors['canvas']));dc.DrawCircle(terminal,y,3)
                label=pin['mode']+' '+pin['name']+' → '+(pin['node'] if input_pin else pin['source'])
                dc.SetTextForeground(colors['fg']);dc.DrawText(label,at.x+8,y-8)
        for item in self.owner.doc.data['directives']:
            if not item['visible']:continue
            dc.SetFont(wx.Font(max(6,round(10*self.zoom)),wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
            delta=self.move_delta if self.moving_directive==item['id'] else np.zeros(2)
            pos=self.point(item['x']+delta[0],item['y']+delta[1])
            lines=item['text'].splitlines();text='\n'.join(line[:90] for line in lines[:3])+('\n… double-click for full directive' if len(lines)>3 or any(len(line)>90 for line in lines[:3]) else '')
            heading=item['group']+(' · '+item['title'] if item['title'] else '')+(' [disabled]' if not item['enabled'] else '')
            heading=heading[:90]
            width=max(dc.GetTextExtent(heading)[0],dc.GetMultiLineTextExtent(text)[0])+20
            body_y=dc.GetTextExtent(heading)[1]+12
            height=dc.GetMultiLineTextExtent(text)[1]+body_y+8
            rect=wx.Rect(pos.x,pos.y,width,height);self.directive_hits.append((rect,item))
            dc.SetPen(wx.Pen(colors['accent'] if item['id']==self.selected_directive else colors['grid'],2 if item['id']==self.selected_directive else 1))
            dc.SetBrush(wx.Brush(colors['selected'] if item['enabled'] else colors['panel']));dc.DrawRoundedRectangle(rect,4)
            dc.SetTextForeground(colors['fg'] if item['enabled'] else colors['muted'])
            dc.DrawText(heading,pos.x+8,pos.y+5);dc.DrawLabel(text,wx.Rect(pos.x+8,pos.y+body_y,width-16,height-body_y))
        dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
        self.instrument_hits=[]
        from .plot_workspace import instrument_data
        from .plotting import extrema_indices
        for item in self.owner.doc.data['instruments']:
            delta=self.move_delta if self.moving_instrument==item['id'] else np.zeros(2)
            pos=self.point(item['x']+delta[0],item['y']+delta[1]);w=max(170,round(275*self.zoom));h=round((160 if item['kind']=='Mini plot' else 75)*self.zoom)
            h=max(75,h);rect=wx.Rect(pos.x,pos.y,w,h);self.instrument_hits.append((rect,item))
            part=next((p for p in self.owner.doc.data['components'] if p['id']==item['anchor']),None)
            dc.SetPen(wx.Pen(colors['accent'],1,wx.PENSTYLE_SHORT_DASH))
            if part:
                import re
                match=re.match(r'\s*v\(\s*([^,)]+)',item['expression'],re.I)
                node=match[1].strip() if match else None
                terminal=part['nodes'].index(node) if node in part['nodes'][:2] else None
                at=self.point(*transform(part,-55 if terminal==0 else 55 if terminal==1 else 0,0))
                dc.DrawLine(at,pos);dc.DrawCircle(at,3)
            dc.SetBrush(wx.Brush(colors['panel']));dc.DrawRoundedRectangle(rect,5)
            dc.SetClippingRegion(rect)
            dc.SetTextForeground(colors['accent']);dc.DrawText(item['expression']+' · '+item['kind'],pos.x+7,pos.y+5)
            try:
                if part is None:raise ValueError('Detached component')
                label,value,curve=instrument_data(self.owner,item)
                dc.SetTextForeground(colors['fg']);dc.DrawText(value.replace('∠','@'),pos.x+7,pos.y+25)
                dc.SetTextForeground(colors['muted']);dc.DrawText(label,pos.x+7,pos.y+h-20)
                if curve is not None and h>95:
                    tx,values=curve;indices=extrema_indices(values,budget=200)
                    low,high=float(np.min(values)),float(np.max(values));span=high-low or max(abs(low)*.01,1e-12)
                    points=[wx.Point(pos.x+8+round((tx[i]-tx[0])/(tx[-1]-tx[0])*(w-16)),pos.y+h-30-round((values[i]-low)/span*(h-82))) for i in indices]
                    dc.SetPen(wx.Pen(colors['accent'],1));dc.DrawLines(points)
            except Exception as exc:
                dc.SetTextForeground(colors['muted']);dc.DrawText('Unavailable: '+str(exc),pos.x+7,pos.y+28)
            dc.DestroyClippingRegion()
        self.annotation_hits=[]
        for item in self.owner.doc.data.get('annotations',[]):
            delta=self.move_delta if self.moving_annotation==item['id'] else np.zeros(2)
            at=self.point(item['x']+delta[0],item['y']+delta[1]);rect=wx.Rect(at.x,at.y,round(item['width']*self.zoom),round(item['height']*self.zoom));self.annotation_hits.append((rect,item))
            color=colors.get({'text':'fg','warning':'accent'}.get(item['color'],item['color']),colors['accent']);dc.SetPen(wx.Pen(color,2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
            if item['kind']=='ellipse':dc.DrawEllipse(rect)
            else:dc.DrawRectangle(rect)
            if item['text']:dc.SetTextForeground(color);dc.DrawLabel(item['text'],wx.Rect(rect.x+5,rect.y+5,max(1,rect.width-10),max(1,rect.height-10)))
        from collections import Counter
        from .editor_geometry import terminal
        endpoints=Counter(tuple(w[key]) for w in self.owner.doc.data['wires'] for key in ('a','b'))
        dc.SetPen(wx.Pen(colors['accent'],1));dc.SetBrush(wx.Brush(colors['accent']))
        for endpoint,count in endpoints.items():
            if count>=2:dc.DrawCircle(self.point(*terminal(positions[endpoint[0]],endpoint[1])),max(4,round(5*self.zoom)))
        if len(self.selection_path)>1:
            dc.SetPen(wx.Pen(colors['accent'],1,wx.PENSTYLE_SHORT_DASH));dc.SetBrush(wx.TRANSPARENT_BRUSH)
            points=[self.point(*p) for p in self.selection_path]
            if self.selection_tool=='lasso':dc.DrawLines([*points,points[0]])
            else:dc.DrawRectangle(min(points[0].x,points[-1].x),min(points[0].y,points[-1].y),abs(points[-1].x-points[0].x),abs(points[-1].y-points[0].y))
        dc.SetTextForeground(colors['muted'])
        dc.DrawText("Named terminals with the same label are electrically connected.",12,max(30,self.GetClientSize().height-28))

    def click(self, event):
        self.SetFocus(); position = event.GetPosition()
        if self.designer_tool:
            payload=self.designer_tool;self.designer_tool=None;self.SetCursor(wx.NullCursor)
            self.owner.guarded(lambda:self.owner.place_designer_tool(payload,self.world(position)));return
        if self.wire_mode:
            candidates=[(np.hypot(position.x-p.x,position.y-p.y),(pid,index)) for p,pid,index in self.wire_pins]
            if not candidates or min(candidates)[0]>18:
                if self.wire_start:
                    point=np.round(self.world(position)/10)*10
                    self.wire_corners.append(point.tolist());self.Refresh()
                    self.owner.SetStatusText('Corner placed. Click another corner or destination terminal; Escape cancels.')
                else:self.owner.SetStatusText('Start at a terminal circle; then click corners and destination. Escape cancels.')
                return
            endpoint=min(candidates)[1]
            if self.wire_start is None:
                self.wire_start=endpoint;self.wire_tip=self.world(position).tolist();self.Refresh()
                self.owner.SetStatusText('Wire started: move to preview, click corners, then destination terminal. Escape cancels.');return
            def connect():
                self.owner.require_clean_directive_source()
                if self.owner.job_running:raise ValueError('Stop simulation before changing wiring')
                self.owner.doc.connect(self.wire_start,endpoint,getattr(self,'wire_corners',[]));self.wire_mode=False;self.wire_start=None;self.SetCursor(wx.NullCursor);self.owner.refresh_document()
            self.owner.guarded(connect);return
        if self.owner.pending_library_placement:
            record,mapping,count=self.owner.pending_library_placement;point=self.world(position)
            def place():
                self.owner.catalog_panel.insert_recipe(record,mapping,count=count,position=point)
                self.owner.pending_library_placement=None;self.SetCursor(wx.NullCursor);self.Refresh()
            self.owner.guarded(place);return
        if self.probe_mode is None:
            for rect,item in reversed(self.annotation_hits):
                if rect.Contains(position):
                    self.selected_annotation=item['id'];self.moving_annotation=item['id'];self.move_origin=self.world(position);self.move_delta=np.zeros(2)
                    if not self.HasCapture():self.CaptureMouse()
                    return
            for rect,item in reversed(self.instrument_hits):
                if rect.Contains(position):
                    self.moving_instrument=item['id'];self.move_origin=self.world(position);self.move_delta=np.zeros(2)
                    if not self.HasCapture():self.CaptureMouse()
                    return
            for rect,item in reversed(self.directive_hits):
                if rect.Contains(position):
                    self.selected.clear();self.selected_directive=item['id'];self.moving_directive=item['id']
                    self.move_origin=self.world(position);self.move_delta=np.zeros(2)
                    if not self.HasCapture():self.CaptureMouse()
                    self.owner.inspector.SetValue(item['group']+'\n'+item['text']+'\n\nDouble-click to edit; drag to move.');self.Refresh();return
        self.selected_directive=None
        if self.probe_mode in ("voltage", "differential"):
            candidates = [(np.hypot(position.x-p.x,position.y-p.y),node,pid) for p,node,pid in self.pins]
            if candidates:
                distance,node,pid = min(candidates)
                if distance <= 18:
                    if self.probe_mode == "differential" and self.first_node is None:
                        self.first_node = node; self.owner.SetStatusText(f"Positive terminal: {node}. Click negative terminal."); return
                    expression = f"V({node})" if self.probe_mode == "voltage" else f"V({self.first_node},{node})"
                    self.owner.doc.add_probe(expression,pid); self.probe_mode=None; self.first_node=None; self.owner.refresh_document(); return
            self.owner.SetStatusText("Click a terminal connection point"); return
        for rect,part in reversed(self.hits):
            if rect.Contains(position):
                if self.probe_mode in ("current", "power"):
                    self.owner.doc.add_probe(f"{'I' if self.probe_mode=='current' else 'P'}({part['ref']})", part["id"])
                    self.probe_mode=None; self.owner.refresh_document(); return
                if event.ControlDown():
                    self.selected.symmetric_difference_update({part["id"]})
                else: self.selected = {part["id"]}
                self.move_origin=self.world(position)
                self.move_positions={p['id']:(p['x'],p['y']) for p in self.owner.doc.data['components'] if p['id'] in self.selected}
                self.move_delta=np.zeros(2)
                if self.move_positions and not self.HasCapture():self.CaptureMouse()
                self.owner.refresh_inspector(); self.Refresh(); return
        from .editor_geometry import route
        parts={p['id']:p for p in self.owner.doc.data['components']}
        for wire in reversed(self.owner.doc.data['wires']):
            points=[np.array(tuple(self.point(*p)),dtype=float) for p in route(parts,wire)]
            for a,b in zip(points,points[1:]):
                delta=b-a;length=float(delta@delta)
                closest=a+np.clip((np.array(tuple(position))-a)@delta/length,0,1)*delta if length else a
                if np.linalg.norm(np.array(tuple(position))-closest)<12:
                    self.moving_wire=wire['id'];self.move_origin=self.world(position);self.move_delta=np.zeros(2)
                    if not self.HasCapture():self.CaptureMouse()
                    self.SetCursor(wx.Cursor(wx.CURSOR_SIZING));self.Refresh()
                    self.owner.SetStatusText('Drag wire route; connected terminals remain fixed.');return
        self.selection_path=[self.world(position)];self.selection_add=event.ControlDown()
        if not self.selection_add:self.selected.clear()
        if not self.HasCapture():self.CaptureMouse()
        self.owner.refresh_inspector();self.Refresh()

    def move_end(self,event):
        if self.selection_path:
            from .editor_geometry import select_box,select_lasso
            end=self.world(event.GetPosition())
            chosen=select_lasso(self.owner.doc.data['components'],[*self.selection_path,end]) if self.selection_tool=='lasso' else select_box(self.owner.doc.data['components'],self.selection_path[0],end)
            self.selected=(self.selected|set(chosen)) if self.selection_add else set(chosen)
            self.selection_path=[]
            if self.HasCapture():self.ReleaseMouse()
            self.owner.refresh_inspector();self.Refresh();return
        if self.move_origin is not None and np.any(self.move_delta):
            if getattr(self,'moving_wire',None):
                self.owner.guarded(lambda:self.owner.doc.move_wire_route(self.moving_wire,float(self.move_delta[0]),float(self.move_delta[1])))
            elif self.moving_annotation:
                item=next(v for v in self.owner.doc.data['annotations'] if v['id']==self.moving_annotation)
                values={k:v for k,v in item.items() if k!='id'};values.update(x=item['x']+float(self.move_delta[0]),y=item['y']+float(self.move_delta[1]))
                self.owner.guarded(lambda:self.owner.doc.edit_annotation(item['id'],**values))
            elif self.moving_instrument:
                ident=self.moving_instrument;delta=self.move_delta.copy()
                def move(d):
                    item=next(v for v in d['instruments'] if v['id']==ident);item.update(x=float(item['x']+delta[0]),y=float(item['y']+delta[1]))
                self.owner.guarded(lambda:self.owner.doc.commit(move))
            elif self.moving_directive:
                item=next(v for v in self.owner.doc.data['directives'] if v['id']==self.moving_directive)
                self.owner.guarded(lambda:self.owner.doc.organize_directives([item['id']],x=float(item['x']+self.move_delta[0]),y=float(item['y']+self.move_delta[1])))
            else:
                positions={ident:np.array(at)+self.move_delta for ident,at in self.move_positions.items()}
                self.owner.guarded(lambda:self.owner.doc.move(positions))
        self.capture_lost()
        if self.HasCapture():self.ReleaseMouse()
        self.owner.refresh_document()

    def capture_lost(self,event=None):
        self.moving_wire=None
        if not self.wire_mode:self.SetCursor(wx.NullCursor)
        self.moving_annotation=None;self.selection_path=[]
        self.move_origin=None;self.move_positions={};self.move_delta=np.zeros(2);self.drag_start=None;self.moving_directive=None;self.moving_instrument=None;self.Refresh()

    def wheel(self,event):
        at=self.world(event.GetPosition()); self.zoom=max(.25,min(4,self.zoom*(1.2 if event.GetWheelRotation()>0 else 1/1.2)))
        self.offset=np.array([event.GetX(),event.GetY()])-at*self.zoom; self.Refresh()

    def pan_start(self,event): self.drag_start=event.GetPosition(); self.CaptureMouse()
    def pan_end(self,event):
        self.drag_start=None
        if self.HasCapture(): self.ReleaseMouse()
    def motion(self,event):
        if self.wire_mode and self.wire_start:
            self.wire_tip=(np.round(self.world(event.GetPosition())/10)*10).tolist();self.Refresh()
        if self.selection_path and event.LeftIsDown():
            point=self.world(event.GetPosition())
            if self.selection_tool=='lasso':self.selection_path.append(point)
            elif len(self.selection_path)==1:self.selection_path.append(point)
            else:self.selection_path[-1]=point
            self.Refresh()
        elif self.move_origin is not None and event.LeftIsDown():
            self.move_delta=np.round((self.world(event.GetPosition())-self.move_origin)/10)*10;self.Refresh()
        elif self.drag_start is not None:
            point=event.GetPosition(); self.offset+=np.array([point.x-self.drag_start.x,point.y-self.drag_start.y]); self.drag_start=point; self.Refresh()
    def context(self,event):
        point=self.world(event.GetPosition())
        annotation=next((item for rect,item in self.annotation_hits if rect.Contains(event.GetPosition())),None)
        if annotation:
            menu=wx.Menu()
            for label,action in [('Edit annotation…',lambda:self.owner.edit_canvas_annotation(annotation)),('Delete annotation',lambda:(self.owner.doc.remove_annotations([annotation['id']]),self.owner.refresh_document()))]:
                item=menu.Append(wx.ID_ANY,label);self.Bind(wx.EVT_MENU,lambda e,f=action:self.owner.guarded(f),item)
            self.PopupMenu(menu);menu.Destroy();return
        directive=next((item for rect,item in reversed(self.directive_hits) if rect.Contains(event.GetPosition())),None)
        if directive:
            self.selected_directive=directive['id'];self.selected.clear();self.Refresh()
            menu=wx.Menu()
            for label,fn in [('Edit directive…',lambda:self.owner.edit_directive(directive['id'])),('Directive manager',lambda:self.owner.book.SetSelection(7))]:
                item=menu.Append(wx.ID_ANY,label);self.Bind(wx.EVT_MENU,lambda e,f=fn:self.owner.guarded(f),item)
            self.PopupMenu(menu);menu.Destroy();return
        if not any(rect.Contains(event.GetPosition()) and part['id'] in self.selected for rect,part in self.hits):
            self.selected={part['id'] for rect,part in self.hits if rect.Contains(event.GetPosition())}
            self.owner.refresh_inspector();self.Refresh()
        menu=wx.Menu()
        for command in ('edit.box_select','edit.lasso_select','edit.mirror_horizontal','edit.mirror_vertical'):
            self.owner.append_command_item(menu,command)
        for label,action in [('Add note…',lambda:self.owner.place_designer_tool({'annotation':'note'},point)),('Add rectangle',lambda:self.owner.place_designer_tool({'annotation':'rect'},point)),('Add ellipse',lambda:self.owner.place_designer_tool({'annotation':'ellipse'},point))]:
            item=menu.Append(wx.ID_ANY,label);self.Bind(wx.EVT_MENU,lambda e,f=action:self.owner.guarded(f),item)
        for command in ('edit.rotate','edit.wire'):self.owner.append_command_item(menu,command)
        menu.AppendSeparator()
        item=menu.Append(wx.ID_ANY,'Schematic readouts / mini plots…');self.Bind(wx.EVT_MENU,lambda e:self.owner.guarded(self.owner.manage_instruments),item)
        item=menu.Append(wx.ID_ANY,'Add SPICE directive here…');self.Bind(wx.EVT_MENU,lambda e:self.owner.guarded(lambda:self.owner.edit_directive(position=point)),item)
        item=menu.Append(wx.ID_ANY,'SPICE directive manager');self.Bind(wx.EVT_MENU,lambda e:self.owner.book.SetSelection(7),item)
        for command in ('edit.properties','probe.voltage','probe.differential','probe.current'):
            self.owner.append_command_item(menu,command)
        self.PopupMenu(menu); menu.Destroy()


class Studio(wx.Frame):
    def __init__(self, library=None):
        super().__init__(None,title="SPIKES Studio — RC startup",size=(1320,880))
        from .resources import resource_dir
        icon=resource_dir('library')/'spikes-studio.png'
        if icon.is_file():self.SetIcon(wx.Icon(str(icon),wx.BITMAP_TYPE_PNG))
        self.SetMinSize((900,650)); self.CreateStatusBar()
        self.theme_name=load_theme();self.palette=PALETTES[self.theme_name]
        self.doc=Document.from_netlist(RC_DECK); self.path=None; self.math=None; self.result=None
        self.library=library; self.keymap=Keymap(); self.job_running=False; self.cursors=[]; self.traces=[]
        self.active_run=None;self.source_baseline=RC_DECK;self.result_source=None;self.run_expressions=[]
        self.run_snapshot=None;self.live_samples=-1;self.closing=False
        self.hidden_traces=set()
        self.part_alerts={}
        self.pending_library_placement=None
        self.plot_grid=True;self.canvas_grid=True;self.split_view=False;self.run_results=[];self.run_engines=[];self.selected_run=0;self.cursor_bindings=[];self.visible_runs=None
        self.run_history=RunHistory();self.active_record_id=None;self.capture_record_id=None
        from .designer_workspace import WorkspaceStack,DesignerPalette
        self.workspace=wx.SplitterWindow(self); left=wx.Panel(self.workspace);self.project_sidebar=left; self.book=WorkspaceStack(self.workspace)
        left_box=wx.BoxSizer(wx.VERTICAL)
        left_box.Add(wx.StaticText(left,label="DESIGNER · drag tools onto schematic"),0,wx.ALL,8)
        from .designer_icons import tool
        tools=wx.GridSizer(cols=6,hgap=3,vgap=3)
        for label,handler in [('Select',lambda:self.selection_tool('box')),('Lasso',lambda:self.selection_tool('lasso')),('Wire',self.start_wire),('Rotate',self.rotate_parts),('Mirror X',lambda:self.mirror_parts('horizontal')),('Mirror Y',lambda:self.mirror_parts('vertical'))]:
            control=tool(left,self,label+(' · W' if label=='Wire' else ''),handler);tools.Add(control,0,wx.EXPAND)
        left_box.Add(tools,0,wx.EXPAND|wx.ALL,6)
        self.designer_palette=DesignerPalette(left,self);left_box.Add(self.designer_palette,1,wx.EXPAND|wx.ALL,6)
        self.parts=wx.ListBox(left); left_box.Add(self.parts,1,wx.EXPAND|wx.ALL,6)
        self.parts.Bind(wx.EVT_LISTBOX,self.select_list)
        self.inspector=wx.TextCtrl(left,style=wx.TE_MULTILINE|wx.TE_READONLY); left_box.Add(self.inspector,1,wx.EXPAND|wx.ALL,6)
        button(left,"Edit selected properties…",lambda e:self.properties(),left_box)
        button(left,"Pin / hide properties panel",lambda e:self.pin_properties(),left_box)
        self.probes=wx.ListBox(left); left_box.Add(self.probes,1,wx.EXPAND|wx.ALL,6)
        self.probes.Bind(wx.EVT_LISTBOX_DCLICK,lambda e:self.add_trace(self.probes.GetStringSelection()))
        left.SetSizer(left_box)
        self.schematic_host=wx.Panel(self.book);self.schematic_host.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self.split_return=wx.Button(self.schematic_host,label='Schematic is in the split Plots view — return it here')
        self.split_return.Bind(wx.EVT_BUTTON,lambda e:(self.toggle_split(),self.book.SetSelection(0)))
        self.schematic_host.GetSizer().Add(self.split_return,0,wx.ALL,16);self.split_return.Hide()
        self.canvas=SchematicCanvas(self,self.schematic_host);self.schematic_host.GetSizer().Add(self.canvas,1,wx.EXPAND);self.book.AddPage(self.schematic_host,"Schematic")
        self.make_plot(); self.make_source(); self.make_ide(); self.make_parts(); self.make_help()
        self.manager=SimulationManager(self,self.book);self.book.AddPage(self.manager,'Simulation manager')
        self.directives=DirectiveManager(self,self.book);self.book.AddPage(self.directives,'SPICE directives')
        self.frequency=FrequencyPanel(self,self.book);self.book.AddPage(self.frequency,'Frequency / poles & zeros')
        self.power_tree=PowerPanel(self,self.book);self.book.AddPage(self.power_tree,'Power tree')
        self.analytics=AnalyticsPanel(self,self.book);self.book.AddPage(self.analytics,'Analytics / extensions')
        from .component_panel import ComponentPanel
        from .controller_panel import ControllerPanel
        self.catalog_host=wx.Panel(self.book);self.catalog_host.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self.catalog_return=wx.Button(self.catalog_host,label='Browser is pinned — return to full tab');self.catalog_return.Bind(wx.EVT_BUTTON,lambda e:self.pin_browser(False));self.catalog_host.GetSizer().Add(self.catalog_return,0,wx.ALL,12);self.catalog_return.Hide()
        self.catalog_panel=ComponentPanel(self,self.catalog_host);self.catalog_host.GetSizer().Add(self.catalog_panel,1,wx.EXPAND);self.book.AddPage(self.catalog_host,'Component catalog')
        self.controller_panel=ControllerPanel(self,self.book);self.book.AddPage(self.controller_panel,'Controller')
        from .dashboard_panel import DashboardPanel
        self.dashboard_panel=DashboardPanel(self,self.book);self.book.AddPage(self.dashboard_panel,'Dashboard')
        from .symbol_designer import SymbolDesignerPanel
        self.symbol_designer=SymbolDesignerPanel(self.book,self);self.book.AddPage(self.symbol_designer,'Visual symbols')
        from .offline_report_panel import OfflineReportPanel
        self.offline_report=OfflineReportPanel(self,self.book);self.book.AddPage(self.offline_report,'Interactive report')
        for index,title in enumerate(('Schematic','Plots','Netlist','Blocks / IDE','Parts','Help','Runs','Directives','Frequency','Power tree','Analytics')):self.book.SetPageText(index,title)
        self.workspace.SplitVertically(left,self.book,250); self.workspace.SetMinimumPaneSize(200)
        self.info=wx.InfoBar(self);layout=wx.BoxSizer(wx.VERTICAL)
        self.initialize_docking()
        layout.Add(self.info,0,wx.EXPAND);layout.Add(self.dock_root,1,wx.EXPAND);self.SetSizer(layout)
        self.build_menu();self.build_toolbar();self.build_workflow_bar(layout); self.install_keys(); self.refresh_document()
        self.set_theme(self.theme_name,save=False)
        self.Bind(wx.EVT_WINDOW_CREATE,self.theme_new_window)
        self.Bind(wx.EVT_CLOSE,self.close)
        self.Bind(wx.EVT_CHILD_FOCUS,self.focus_shortcuts)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,self.poll_run,self.timer);self.timer.Start(200)
        from .recovery import Recovery
        self.recovery=Recovery();self.autosave_timer=wx.Timer(self)
        self.Bind(wx.EVT_TIMER,self.autosave,self.autosave_timer);self.autosave_timer.Start(60000)

    def initialize_docking(self):
        self.browser_pinned=False;self.properties_pinned=False;self.properties_editor=None
        self.dock_root=wx.Panel(self);self.workspace.Reparent(self.dock_root)
        self.docks=wx.aui.AuiManager(self.dock_root)
        self.docks.AddPane(self.workspace,wx.aui.AuiPaneInfo().Name('workspace').CenterPane())
        self.browser_side=wx.Panel(self.dock_root);self.browser_side.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self.properties_side=wx.Panel(self.dock_root);self.properties_side.SetSizer(wx.BoxSizer(wx.VERTICAL))
        self.properties_notice=wx.StaticText(self.properties_side,label='Select a component on the schematic.');self.properties_notice.Wrap(340)
        self.properties_side.GetSizer().Add(self.properties_notice,0,wx.EXPAND|wx.ALL,8)
        for name,window,caption,right,width in [('browser',self.browser_side,'Parts browser · drag title to float',False,480),('properties',self.properties_side,'Properties · drag title to float',True,390)]:
            pane=wx.aui.AuiPaneInfo().Name(name).Caption(caption).BestSize(width,700).MinSize(340,350).CloseButton(True).Floatable(True).Hide()
            self.docks.AddPane(window,pane.Right() if right else pane.Left())
        self.dock_root.Bind(wx.aui.EVT_AUI_PANE_CLOSE,self.dock_closed)
        self.dock_root.Bind(wx.EVT_WINDOW_DESTROY,self.destroy_docking);self.docks.Update()

    def destroy_docking(self,event):
        if event.GetEventObject() is self.dock_root:self.docks.UnInit()
        event.Skip()

    def dock_closed(self,event):
        name=event.GetPane().name
        if name in ('browser','properties'):
            event.Veto()
            wx.CallAfter(self.pin_browser if name=='browser' else self.pin_properties,False)
        else:event.Skip()

    def pin_browser(self,pinned=None):
        pinned=not self.browser_pinned if pinned is None else pinned
        if pinned!=self.browser_pinned:
            self.catalog_panel.GetContainingSizer().Detach(self.catalog_panel)
            target=self.browser_side if pinned else self.catalog_host
            self.catalog_panel.Reparent(target);target.GetSizer().Add(self.catalog_panel,1,wx.EXPAND)
            self.browser_pinned=pinned;self.catalog_return.Show(pinned);self.catalog_panel.set_compact(pinned)
        self.docks.GetPane('browser').Show(pinned);self.docks.Update();self.catalog_host.Layout();self.browser_side.Layout()
        if pinned:
            if self.workspace.IsSplit():self.workspace.Unsplit(self.project_sidebar)
            self.book.SetSelection(0)
        else:
            if not self.workspace.IsSplit():self.project_sidebar.Show();self.workspace.SplitVertically(self.project_sidebar,self.book,250)
            self.book.SetSelection(11);self.catalog_panel.initial_layout=False;wx.CallAfter(self.catalog_panel.fit_initial_layout)

    def show_browser(self):
        if self.browser_pinned:self.docks.GetPane('browser').Show();self.docks.Update()
        else:self.book.SetSelection(11)
        self.catalog_panel.search.SetFocus()

    def pin_properties(self,pinned=None):
        self.properties_pinned=not self.properties_pinned if pinned is None else pinned
        self.docks.GetPane('properties').Show(self.properties_pinned);self.docks.Update()
        if self.properties_pinned:self.sync_properties()

    def sync_properties(self,force=False):
        if not self or not self.properties_pinned:return
        editor=self.properties_editor
        selected=sorted(self.canvas.selected);signature=(self.doc.data['id'],self.doc.data['revision'],selected)
        if not force and editor and not editor.applied and editor.dirty():
            if signature!=self.properties_signature:self.properties_notice.SetLabel('Draft retained for '+', '.join(editor.ids)+'\nApply or Reload selection to continue.');self.properties_notice.Wrap(340)
            self.properties_side.Layout();return
        if not force and signature==getattr(self,'properties_signature',None):return
        self.properties_signature=signature
        if editor:self.properties_side.GetSizer().Detach(editor);editor.Destroy();self.properties_editor=None
        valid=set(p['id'] for p in self.doc.data['components']);self.canvas.selected.intersection_update(valid)
        self.properties_notice.SetLabel('Selection follows the canvas · edits require Apply' if self.canvas.selected else 'Select a component on the schematic.')
        self.properties_notice.Wrap(340)
        if self.canvas.selected:
            try:
                self.properties_editor=DockedProperties(self,self.properties_side);self.properties_side.GetSizer().Add(self.properties_editor,1,wx.EXPAND)
            except Exception as exc:self.properties_notice.SetLabel(str(exc))
        self.properties_side.Layout();apply_window(self.properties_side,self.palette)

    def focus_shortcuts(self,event):
        self.install_keys(text_focus=isinstance(event.GetWindow(),(wx.TextCtrl,wx.ComboBox,wx.SearchCtrl,wx.stc.StyledTextCtrl)))
        event.Skip()

    def theme_new_window(self,event):
        window=event.GetWindow()
        # Never queue raw child-window wrappers: a property rebuild can destroy
        # them before CallAfter runs while their Python truth value stays true.
        # Dialog show occurs after construction; dynamic forms theme themselves.
        if isinstance(window,wx.Dialog):
            def shown(e):
                if e.IsShown() and window and not window.IsBeingDeleted():apply_window(window,self.palette)
                e.Skip()
            window.Bind(wx.EVT_SHOW,shown)
        event.Skip()

    def set_theme(self,name,save=True):
        if name not in PALETTES:raise ValueError('Unknown theme')
        self.theme_name=name;self.palette=PALETTES[name];native_appearance(name);apply_window(self,self.palette)
        from .designer_icons import icon
        for control,label in getattr(self,'designer_icon_controls',[]):control.SetBitmap(icon(label,self.palette))
        art=self.docks.GetArtProvider()
        for metric,key in [(wx.aui.AUI_DOCKART_BACKGROUND_COLOUR,'panel'),(wx.aui.AUI_DOCKART_BORDER_COLOUR,'grid'),(wx.aui.AUI_DOCKART_SASH_COLOUR,'grid'),(wx.aui.AUI_DOCKART_ACTIVE_CAPTION_COLOUR,'selected'),(wx.aui.AUI_DOCKART_INACTIVE_CAPTION_COLOUR,'panel'),(wx.aui.AUI_DOCKART_ACTIVE_CAPTION_TEXT_COLOUR,'fg'),(wx.aui.AUI_DOCKART_INACTIVE_CAPTION_TEXT_COLOUR,'fg')]:art.SetColour(metric,wx.Colour(self.palette[key]))
        art.SetMetric(wx.aui.AUI_DOCKART_GRADIENT_TYPE,wx.aui.AUI_GRADIENT_NONE);self.docks.Update()
        for command in self.ids:
            if self.run_bar.FindById(self.ids[command]):
                self.run_bar.SetToolNormalBitmap(self.ids[command],toolbar_icon(command,self.palette))
                self.run_bar.SetToolDisabledBitmap(self.ids[command],toolbar_icon(command,self.palette|{'fg':self.palette['muted'],'accent':self.palette['muted'],'danger':self.palette['muted']}))
        self.run_bar.Realize();self.refresh_figures_theme();self.canvas.Refresh()
        self.preview_symbol()
        self.theme_picker.SetStringSelection(name)
        if save:
            from .themes import preferences_path
            path=preferences_path();path.parent.mkdir(parents=True,exist_ok=True);write_json(path,{'theme':name})

    def refresh_figures_theme(self):
        for figure,canvas in [(self.figure,self.plot),(self.frequency.figure,self.frequency.plot),(self.timing_figure,self.timing_canvas),(self.symbol_figure,self.symbol_canvas),(self.analytics.figure,self.analytics.plot)]:
            figure_theme(figure,self.palette,self.theme_name);canvas.draw_idle()

    def close(self,event):
        if self.active_run:
            if wx.MessageBox('Stop the active simulation and close?', 'Close Studio', wx.YES_NO|wx.NO_DEFAULT, self)!=wx.YES:return
            self.closing=True;self.stop_run();return
        if self.job_running:
            wx.MessageBox("A simulation or build is still running. Wait for its result before closing.","Work in progress",parent=self); return
        if not self.confirm_replace():return
        self.timer.Stop()
        self.autosave_timer.Stop()
        self.Destroy()

    def autosave(self,event=None):
        try:self.recovery.save(self.doc,self.source.GetText(),self.path)
        except Exception as exc:self.SetStatusText('Autosave failed: '+str(exc))

    def recover_document(self):
        from .recovery import restore
        with wx.FileDialog(self,'Recover autosave as an unsaved copy',defaultDir=str(self.recovery.directory),wildcard='SPIKES recovery (*.spkrecovery)|*.spkrecovery',style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal()!=wx.ID_OK:return
            document,draft=restore(dlg.GetPath())
        if not self.confirm_replace():return
        self.doc=document;self.path=None;self.canvas.selected.clear();self.refresh_document(force_source=True);self.source.SetText(draft);self.update_title()

    def confirm_replace(self):
        if not self.doc.dirty and self.source.GetText()==self.doc.data['source']:return True
        answer=wx.MessageBox('Save changes before closing or replacing this document?', 'Unsaved circuit', wx.YES_NO|wx.CANCEL|wx.CANCEL_DEFAULT, self)
        if answer==wx.CANCEL:return False
        if answer==wx.YES:
            try:return bool(self.save_document())
            except Exception as exc:self.guarded(lambda:(_ for _ in ()).throw(exc));return False
        return True

    def new_document(self):
        if self.confirm_replace():
            self.doc=Document.from_netlist(RC_DECK);self.path=None;self.canvas.selected.clear();self.refresh_document(force_source=True)

    def build_toolbar(self):
        bar=self.CreateToolBar(wx.TB_HORIZONTAL|wx.TB_TEXT|wx.TB_FLAT)
        self.run_bar=bar
        for command,label,art in [('file.new','New RC',wx.ART_NEW),('file.open','Open',wx.ART_FILE_OPEN),
            ('file.save','Save',wx.ART_FILE_SAVE),('run.start','Run batch',wx.ART_GO_FORWARD),
            ('run.interactive','Continuous',wx.ART_REDO),('run.pause','Pause / Resume',wx.ART_CROSS_MARK),
            ('run.stop','Stop',wx.ART_QUIT),('run.manager','Runs',wx.ART_REPORT_VIEW)]:
            bar.AddTool(self.ids[command],label,wx.ArtProvider.GetBitmap(art,wx.ART_TOOLBAR,(20,20)),shortHelp=label)
        bar.AddSeparator();self.theme_picker=wx.Choice(bar,choices=list(PALETTES));self.theme_picker.SetStringSelection(self.theme_name)
        self.theme_picker.Bind(wx.EVT_CHOICE,lambda e:self.guarded(lambda:self.set_theme(self.theme_picker.GetStringSelection())));bar.AddControl(self.theme_picker)
        bar.Realize();self.update_run_controls()

    def build_workflow_bar(self,layout):
        from .designer_icons import tool
        panel=wx.Panel(self);row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE)
        self.workspace_choice=wx.Choice(panel,choices=[self.book.GetPageText(i) for i in range(self.book.GetPageCount())]);self.workspace_choice.SetSelection(self.book.GetSelection())
        self.workspace_choice.Bind(wx.EVT_CHOICE,lambda e:self.book.SetSelection(self.workspace_choice.GetSelection()));row.Add(self.workspace_choice,0,wx.ALL,3)
        def changed(index):
            self.workspace_choice.SetSelection(index);self.context_tools()
        self.book.on_selection=changed
        groups=[('Library',[('Manufacturer parts','view.manufacturer_parts'),('Primitives','view.component_catalog'),('Design symbol','view.symbol_designer')]),
                ('Draw / edit',[('Select','edit.box_select'),('Wire · W','edit.wire'),('Rotate · Space','edit.rotate'),('Properties · E','edit.properties')]),
                ('Measure',[('Probe V · P','probe.voltage'),('Differential','probe.differential')]),
                ('Workspace',[('Fit view','view.fit'),('Plots','view.plots'),('Split view','view.split_canvas_plots'),('Dashboard','view.dashboard')])]
        self.command_controls=[]
        for title,actions in groups:
            group=wx.Panel(panel);column=wx.BoxSizer(wx.VERTICAL);buttons=wx.BoxSizer(wx.HORIZONTAL)
            for label,command in actions:
                cell=wx.BoxSizer(wx.VERTICAL);control=tool(group,self,label,lambda c=command:self.execute_command(c));cell.Add(control,0,wx.ALIGN_CENTER|wx.ALL,2)
                self.command_controls.append((control,command))
                caption=label.split(' · ')[0].replace('Manufacturer parts','Vendor parts').replace('Fit schematic','Fit')
                cell.Add(wx.StaticText(group,label=caption),0,wx.ALIGN_CENTER|wx.LEFT|wx.RIGHT,4);buttons.Add(cell,0,wx.ALL,2)
            column.Add(buttons);column.Add(wx.StaticLine(group),0,wx.EXPAND|wx.TOP,3)
            column.Add(wx.StaticText(group,label=title),0,wx.ALIGN_CENTER|wx.ALL,2);group.SetSizer(column);row.Add(group,0,wx.ALL,3)
        panel.SetSizer(row);layout.Insert(1,panel,0,wx.EXPAND);self.workflow_bar=panel

    def context_tools(self):
        schematic=self.book.GetSelection()==0 or self.book.GetSelection()==1 and self.split_view
        for control,label in getattr(self,'designer_icon_controls',[]):
            if label.split(' · ')[0] in ('Select','Lasso','Wire','Rotate','Mirror X','Mirror Y','Properties','Probe V','Differential'):
                control.Enable(schematic)
        for control,command in getattr(self,'command_controls',[]):
            reason=self.commands.reason(command);control.Enable(not reason)
            spec=self.commands.commands[command];key=self.keymap.bindings.get(command,'')
            control.SetToolTip(reason or spec.label+(' · '+key if key else '')+'\n'+spec.description)

    def context_fit(self):
        if self.book.GetSelection()==1:self.draw_plot()
        elif self.book.GetSelection()==0:self.fit()
        else:self.SetStatusText('Fit view is available in Schematic or Plots.')

    def update_run_controls(self):
        from .run_control import InteractiveRun
        interactive=isinstance(self.active_run,InteractiveRun)
        state=self.active_run.state if self.active_run else 'idle'
        enabled={command:not self.commands.reason(command) for command in ('run.start','run.interactive','run.pause','run.stop')}
        for command,value in enabled.items():
            self.GetMenuBar().Enable(self.ids[command],value)
            if hasattr(self,'run_bar'):self.run_bar.EnableTool(self.ids[command],value)
        self.live_apply.Enable(interactive)
        self.live_source.Enable(interactive);self.live_value.Enable(interactive)
        self.manager.update_controls()

    def build_menu(self):
        self.actions={"file.new":self.new_document,"file.open":self.open_document,"file.save":self.save_document,"file.import":self.import_file,"file.export":self.export_file,
            "edit.undo":lambda:(self.doc.undo(),self.refresh_document()),"edit.redo":lambda:(self.doc.redo(),self.refresh_document()),"edit.paste":self.paste,
            "edit.properties":self.properties,"probe.voltage":lambda:self.probe("voltage"),"probe.differential":lambda:self.probe("differential"),
            "probe.current":lambda:self.probe("current"),"probe.power":lambda:self.probe("power"),"view.fit":self.context_fit,"run.start":self.run,
            "run.interactive":self.start_interactive,"run.pause":self.pause_run,"run.stop":self.stop_run,
            "run.manager":lambda:self.book.SetSelection(6),"run.thermal_setup":self.thermal_setup,
            "view.directives":lambda:self.book.SetSelection(7),"edit.directive":self.edit_directive,
            "view.frequency":lambda:self.book.SetSelection(8),
            "view.power_tree":lambda:self.book.SetSelection(9),"view.analytics":lambda:self.book.SetSelection(10),
            "view.split_canvas_plots":self.toggle_split,"view.schematic_instruments":self.manage_instruments,"view.linked_cursors":lambda:self.plot_interactions.show_cursors(),
            "view.component_catalog":self.show_browser,"view.pin_parts_browser":self.pin_browser,"view.pin_properties":self.pin_properties,"view.controller":lambda:self.book.SetSelection(12),"view.part_alerts":self.show_part_alerts,
            "view.canvas_grid":self.toggle_canvas_grid,
            "view.parts":lambda:self.book.SetSelection(4),"view.math":lambda:self.book.SetSelection(1),"view.ide":lambda:self.book.SetSelection(3),"help.open":lambda:self.book.SetSelection(5)}
        menubar=wx.MenuBar(); self.ids={}
        self.actions.update({'edit.rotate':self.rotate_parts,'edit.wire':self.start_wire})
        from .sensor_dialog import import_sensor
        self.actions['file.import_audio_sensor']=lambda:import_sensor(self)
        self.actions['file.recover_autosave']=self.recover_document
        from .library_package import exchange
        self.actions['file.import_library_package']=lambda:exchange(self)
        self.actions['file.export_library_package']=lambda:exchange(self,True)
        self.actions['edit.shortcut_profiles']=self.shortcuts
        from .help_center import show as learning_center,examples as browse_examples
        self.actions['help.learning_center']=lambda:learning_center(self)
        self.actions['help.examples']=lambda:browse_examples(self)
        from .subsheet import create as create_subsheet
        self.actions['edit.create_subsheet']=lambda:create_subsheet(self)
        self.actions.update({'edit.copy':self.copy_circuit,'edit.select_all':self.select_all_parts,
            'edit.properties_standard':self.properties,'edit.rotate_standard':self.rotate_parts,
            'edit.redo_alternative':self.actions['edit.redo'],
            'view.schematic':lambda:self.book.SetSelection(0),'view.plots':lambda:self.book.SetSelection(1),
            'view.circuit_text':lambda:self.book.SetSelection(2)})
        self.actions.update({'edit.mirror_horizontal':lambda:self.mirror_parts('horizontal'),'edit.mirror_vertical':lambda:self.mirror_parts('vertical'),'edit.box_select':lambda:self.selection_tool('box'),'edit.lasso_select':lambda:self.selection_tool('lasso'),'view.solver_log':self.show_solver_log})
        self.actions.update({'view.dashboard':lambda:self.book.SetSelection(13),'view.symbol_designer':lambda:self.book.SetSelection(14)})
        from .command_palette import show as command_search
        self.actions['view.command_search']=lambda:command_search(self)
        self.actions['view.manufacturer_parts']=self.catalog_panel.manufacturer_library
        self.actions['view.offline_report']=lambda:self.book.SetSelection(self.book.FindPage(self.offline_report))
        from .workbench_layout import PRESETS
        for name in PRESETS:
            ident='view.workspace_'+name.split()[0].lower()
            self.actions[ident]=lambda n=name:self.apply_workspace_preset(n)
        self.actions['file.export_workspace']=self.export_workspace
        self.actions['file.import_workspace']=self.import_workspace
        from .command_registry import CommandRegistry
        self.commands=CommandRegistry.from_actions(self.actions,self.command_context)
        for title,prefixes in (("File",("file.",)),("Edit",("edit.",)),("Probes",("probe.",)),("View",("view.",)),("Simulation",("run.",)),("Help",("help.",))):
            menu=wx.Menu()
            for command,handler in self.actions.items():
                if not command.startswith(prefixes):continue
                item=menu.Append(wx.ID_ANY,self.commands.commands[command].label)
                self.ids[command]=item.GetId(); self.Bind(wx.EVT_MENU,lambda e,c=command:self.execute_command(c),item)
                self.Bind(wx.EVT_UPDATE_UI,lambda e,c=command:e.Enable(not self.commands.reason(c)),id=item.GetId())
            if title=="Edit":
                item=menu.Append(wx.ID_ANY,"Keyboard shortcuts…");self.Bind(wx.EVT_MENU,lambda e:self.shortcuts(),item)
                self.part_keys_item=menu.AppendCheckItem(wx.ID_ANY,'Enable part-placement shortcuts');self.part_keys_item.Check(self.keymap.part_shortcuts)
                self.Bind(wx.EVT_MENU,lambda e:self.toggle_part_shortcuts(e.IsChecked()),self.part_keys_item)
            if title=="File":
                item=menu.Append(wx.ID_ANY,"Bill of materials…");self.Bind(wx.EVT_MENU,lambda e:self.bom(),item)
            if title=='View':
                themes=wx.Menu()
                for name in PALETTES:
                    item=themes.Append(wx.ID_ANY,name);self.Bind(wx.EVT_MENU,lambda e,n=name:self.guarded(lambda:self.set_theme(n)),item)
                menu.AppendSubMenu(themes,'Theme')
            menubar.Append(menu,title)
        self.SetMenuBar(menubar)

    def command_context(self):
        from .command_registry import Context
        from .run_control import InteractiveRun
        index=self.book.GetSelection()
        return Context(page=self.book.GetPageText(index),schematic=index==0 or index==1 and self.split_view,
            selected=len(self.canvas.selected),undo=bool(self.doc.undo_stack),redo=bool(self.doc.redo_stack),
            busy=self.job_running,run_state=getattr(self.active_run,'state','idle'),
            interactive=isinstance(self.active_run,InteractiveRun),has_results=self.math is not None)

    def execute_command(self,ident):
        return self.guarded(lambda:self.commands.execute(ident))

    def append_command_item(self,menu,ident):
        spec=self.commands.commands[ident];key=self.keymap.bindings.get(ident,'')
        item=menu.Append(self.ids[ident],spec.label+(' ('+key+')' if key else ''))
        item.Enable(not self.commands.reason(ident))
        return item

    def apply_workspace_preset(self,name):
        from .workbench_layout import preset
        self.apply_workspace(preset(name))

    def apply_workspace(self,data):
        from .workbench_layout import validate
        pages=[self.book.GetPageText(i) for i in range(self.book.GetPageCount())]
        data=validate(data,pages)
        # Validate first: malformed imports cannot partially rearrange the UI.
        if self.split_view!=data['split']:self.toggle_split()
        self.pin_browser(data['browser']);self.pin_properties(data['properties'])
        target='Plots' if data['split'] and data['page']=='Schematic' else data['page']
        self.book.SetSelection(pages.index(target));self.context_tools()
        self.SetStatusText('Workspace: '+data['name'])

    def export_workspace(self):
        from .workbench_layout import CONTRACT
        data=dict(contract=CONTRACT,name='Custom workspace',page=self.book.GetPageText(self.book.GetSelection()),
                  split=self.split_view,browser=self.browser_pinned,properties=self.properties_pinned)
        path=self.choose_path('Export workspace layout','SPIKES workspace (*.spkworkspace)|*.spkworkspace',True)
        if path:write_json(path,data)

    def import_workspace(self):
        path=self.choose_path('Import workspace layout','SPIKES workspace (*.spkworkspace)|*.spkworkspace')
        if path:
            if Path(path).stat().st_size>65536:raise ValueError('Workspace profile exceeds 64 KiB')
            self.apply_workspace(json.loads(Path(path).read_text(encoding='utf-8')))

    def rotate_parts(self):
        self.doc.rotate(self.canvas.selected);self.canvas.Refresh();self.refresh_inspector();self.update_title()

    def start_wire(self):
        self.canvas.wire_corners=[]
        self.canvas.designer_tool=None;self.canvas.selection_path=[]
        self.pending_library_placement=None;self.canvas.probe_mode=None;self.canvas.wire_mode=True;self.canvas.wire_start=None
        self.book.SetSelection(0);self.canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS));self.canvas.SetFocus();self.SetStatusText('Wire: click source terminal, then destination terminal; Escape cancels')

    def arm_designer_tool(self,payload):
        if 'part' in payload:return self.place_shortcut(payload['part'],explicit=True)
        self.canvas.designer_tool=payload;self.book.SetSelection(1 if self.split_view else 0);self.canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS));self.SetStatusText('Click schematic to place; Escape cancels')

    def place_designer_tool(self,payload,position):
        if 'part' in payload:
            self.place_shortcut(payload['part'],explicit=True)
            if self.pending_library_placement:
                record,mapping,count=self.pending_library_placement
                self.catalog_panel.insert_recipe(record,mapping,count=count,position=position);self.pending_library_placement=None
            return
        if 'directive' in payload:
            self.require_clean_directive_source()
            with DirectiveEditor(self,position=position) as dialog:
                dialog.text.SetValue(payload['directive']);dialog.ShowModal()
            return
        kind=payload['annotation'];text=''
        if kind=='note':
            with wx.TextEntryDialog(self,'Schematic note (does not execute as SPICE)','Add note') as dialog:
                if dialog.ShowModal()!=wx.ID_OK:return
                text=dialog.GetValue()
        self.doc.edit_annotation(kind=kind,x=float(position[0]),y=float(position[1]),text=text);self.refresh_document()

    def mirror_parts(self,axis):
        self.doc.mirror(self.canvas.selected,axis);self.refresh_document()

    def selection_tool(self,kind):
        self.canvas.selection_tool=kind;self.canvas.probe_mode=None;self.canvas.wire_mode=False;self.canvas.designer_tool=None;self.pending_library_placement=None
        self.SetStatusText(f'{kind.title()} select: drag empty canvas; Ctrl adds to selection. Drag a selected part to move it.')

    def edit_canvas_annotation(self,item):
        with wx.TextEntryDialog(self,'Annotation text (not executable SPICE)','Edit annotation',item['text']) as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            values={k:v for k,v in item.items() if k!='id'};values['text']=dialog.GetValue()
            self.doc.edit_annotation(item['id'],**values);self.refresh_document()

    def show_solver_log(self):
        result=self.result or {}
        if hasattr(result,'to_dict'):result=result.to_dict()
        if not isinstance(result,dict):result={}
        report={k:result[k] for k in ('status','issues','diagnostics','provenance','measurements') if k in result}
        if self.active_run:report['active_session']={'state':self.active_run.state,'error':self.active_run.error}
        with wx.Dialog(self,title='Simulation diagnostics · actual engine results',size=(900,600),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
            box=wx.BoxSizer(wx.VERTICAL);box.Add(wx.StaticText(dialog,label='Diagnostic snapshot, not a fabricated SPICE console log. Run errors remain available in the simulation manager.'),0,wx.ALL,8)
            text=wx.TextCtrl(dialog,value=json.dumps(report,indent=2,default=str) if report else 'No solver result has been acquired.',style=wx.TE_MULTILINE|wx.TE_READONLY);box.Add(text,1,wx.EXPAND|wx.ALL,8)
            box.Add(dialog.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,8);dialog.SetSizer(box);apply_window(dialog,self.palette);dialog.ShowModal()

    def install_keys(self,text_focus=False):
        entries=[]
        for command in self.actions:
            item=self.GetMenuBar().FindItemById(self.ids[command])
            key=self.keymap.bindings.get(command)
            label=self.commands.commands[command].label
            item.SetItemLabel(label+(f' ({key})' if key else ''))
        for command,key in self.keymap.bindings.items():
            if command.startswith(('part.','part:')):
                if command not in self.ids:
                    self.ids[command]=int(wx.NewIdRef());self.Bind(wx.EVT_MENU,lambda e,c=command:self.guarded(lambda:self.place_shortcut(c)),id=self.ids[command])
                if not self.keymap.part_shortcuts or text_focus:continue
            if text_focus and (not any(modifier in key.lower() for modifier in ('ctrl+','alt+')) and not (key.startswith('F') and key[1:].isdigit()) or command in ("edit.undo","edit.redo","edit.redo_alternative","edit.paste","edit.copy","edit.select_all","edit.properties_standard","edit.rotate_standard")):continue
            entry=wx.AcceleratorEntry()
            if not entry.FromString(key):raise ValueError(f"Unrecognized key combination: {key}")
            entry.Set(entry.GetFlags(),entry.GetKeyCode(),self.ids[command]); entries.append(entry)
        self.SetAcceleratorTable(wx.AcceleratorTable(entries))

    def toggle_part_shortcuts(self,enabled):
        self.keymap.part_shortcuts=bool(enabled);self.part_keys_item.Check(bool(enabled))
        self.install_keys(text_focus=isinstance(wx.Window.FindFocus(),(wx.TextCtrl,wx.ComboBox,wx.SearchCtrl,wx.stc.StyledTextCtrl)))

    def place_shortcut(self,command,explicit=False):
        if not explicit and not self.keymap.part_shortcuts:return
        if not explicit and isinstance(wx.Window.FindFocus(),(wx.TextCtrl,wx.ComboBox,wx.SearchCtrl,wx.stc.StyledTextCtrl)):return
        ident=command[5:] if command.startswith('part:') else 'generic.'+command.split('.')[1]+'.001'
        panel=self.catalog_panel
        record=panel.index.by_id.get(ident)
        if not record or record['status']!='native_subcircuit':raise ValueError('Shortcut target is not a native insertable preset: '+ident)
        panel.reset_filters();panel.search.ChangeValue('id:'+ident);panel.filter();panel.list.SetSelection(0);panel.select();panel.insert()

    def assign_part_shortcut(self,ident):
        with wx.TextEntryDialog(self,'Key combination (e.g. Alt+R). Conflicts are rejected.\nSave the profile in Edit → Keyboard shortcuts to reuse it.','Link preset shortcut') as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            candidate=Keymap(self.keymap.bindings|{'part:'+ident:dialog.GetValue()},self.keymap.part_shortcuts)
            entry=wx.AcceleratorEntry()
            if not entry.FromString(dialog.GetValue()):raise ValueError('Invalid key combination')
            self.keymap=candidate;self.install_keys();self.SetStatusText('Shortcut linked to '+ident)

    def guarded(self,fn):
        try:return fn()
        except Exception as exc:self.report_error(exc)

    def report_error(self,error):
        self.last_error=str(error)
        message=self.last_error
        if 'output points' in message:
            message+=' Use Continuous for bounded rolling capture, or increase .tran TSTEP / reduce TSTOP for a full-history batch.'
        self.info.ShowMessage(message,wx.ICON_ERROR)
        self.measurements.SetValue(message);self.SetStatusText('Action rejected — circuit and previous results retained');self.Layout()

    def refresh_document(self,force_source=False):
        if getattr(self,'_browser_document_id',None)!=self.doc.data['id']:
            self._browser_document_id=self.doc.data['id'];self.pending_library_placement=None;self.canvas.SetCursor(wx.NullCursor)
            if hasattr(self,'catalog_panel'):self.catalog_panel.filter()
        self.parts.Set([f"{p['ref']}  {p['value']}" for p in self.doc.data["components"]])
        if force_source or self.source.GetText()==self.source_baseline:
            self.source.SetText(self.doc.data["source"]);self.source_baseline=self.doc.data['source']
        self.probes.Set([p["expression"] for p in self.doc.data["probes"]])
        self.canvas.Refresh();self.refresh_inspector()
        self.SetStatusText(f"Revision {self.doc.data['revision']} · {len(self.doc.data['components'])} parts · {len(self.doc.data['probes'])} probes")
        self.update_title()
        self.manager.reflect_document()
        self.directives.refresh()
        self.power_tree.refresh();self.analytics.refresh()
        self.dashboard_panel.refresh()
        if self.controller_panel.loaded_id!=self.doc.data['id']:self.controller_panel.reflect()
        signature=repr(self.doc.data['plot_layout'])
        if getattr(self,'_plot_layout_signature',None)!=signature:
            self._plot_layout_signature=signature;self.guarded(self.draw_plot)
        if self.canvas.selected_directive not in {v['id'] for v in self.doc.data['directives']}:self.canvas.selected_directive=None

    def require_clean_directive_source(self):
        if self.source.GetText()!=self.doc.data['source']:raise ValueError('Circuit text has unapplied edits. Validate and apply them before editing directives; your draft has been retained.')

    def edit_directive(self,ident=None,position=None):
        self.require_clean_directive_source()
        with DirectiveEditor(self,ident,position) as dialog:dialog.ShowModal()

    def thermal_setup(self):
        with ThermalSetup(self) as dialog:dialog.ShowModal()

    def update_title(self):
        dirty=self.doc.dirty or self.source.GetText()!=self.doc.data['source']
        self.SetTitle(f"SPIKES Studio — {self.doc.data['title']}{' *' if dirty else ''} — Native workbench")

    def select_list(self,event):
        self.canvas.selected_directive=None
        i=self.parts.GetSelection()
        if i!=wx.NOT_FOUND:self.canvas.selected={self.doc.data["components"][i]["id"]};self.canvas.Refresh();self.refresh_inspector()

    def refresh_inspector(self):
        selected=[p for p in self.doc.data["components"] if p["id"] in self.canvas.selected]
        self.inspector.SetValue("\n\n".join(f"{p['ref']} · {p['kind']}\nValue: {p['value']}\nNodes: {', '.join(p['nodes'])}\nPackage: {p['package'] or 'unspecified'}\nDeclared limits: {json.dumps(p['limits'])}" for p in selected))
        if getattr(self,'properties_pinned',False):wx.CallAfter(self.sync_properties)
        if hasattr(self,'commands'):self.context_tools()

    def properties(self):
        if self.canvas.selected_directive:self.edit_directive(self.canvas.selected_directive);return
        self.apply_source()
        if not self.canvas.selected:self.SetStatusText("Select a component first");return
        if self.properties_pinned:self.sync_properties();self.properties_side.SetFocus();return
        with Properties(self) as dialog:dialog.ShowModal()

    def probe(self,mode):
        self.book.SetSelection(0);self.canvas.probe_mode=mode;self.canvas.first_node=None
        self.SetStatusText("Click positive then negative terminal" if mode=="differential" else f"Click {'a terminal' if mode=='voltage' else 'a component'} for a {mode} probe")

    def fit(self):
        parts=self.doc.data['components']
        directives=[v for v in self.doc.data['directives'] if v['visible']]
        if not parts and not directives:return
        lows=[(p['x']-90,p['y']-70) for p in parts]+[(v['x'],v['y']) for v in directives]
        highs=[(p['x']+90,p['y']+90) for p in parts]+[(v['x']+max(240,min(90,max(map(len,v['text'].splitlines())))*9+30),v['y']+125) for v in directives]
        low=np.min(lows,axis=0);high=np.max(highs,axis=0)
        size=np.maximum(np.array(self.canvas.GetClientSize())-80,1)
        self.canvas.zoom=float(np.clip(np.min(size/(high-low)),.25,4))
        self.canvas.offset=40+(size-(high-low)*self.canvas.zoom)/2-low*self.canvas.zoom;self.canvas.Refresh()

    def choose_path(self,message,wildcard,save=False):
        with wx.FileDialog(self,message,wildcard=wildcard,style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT if save else wx.FD_OPEN|wx.FD_FILE_MUST_EXIST) as dlg:
            return Path(dlg.GetPath()) if dlg.ShowModal()==wx.ID_OK else None

    def open_document(self):
        path=self.choose_path("Open schematic","SPIKES schematic (*.spksch)|*.spksch")
        if path:
            replacement=Document.load(path)
            if self.confirm_replace():self.doc=replacement;self.path=path;self.canvas.selected.clear();self.refresh_document(force_source=True)

    def save_document(self):
        self.apply_source()
        path=self.path or self.choose_path("Save schematic","SPIKES schematic (*.spksch)|*.spksch",True)
        if path:self.doc.save(path);self.path=path;self.update_title();self.SetStatusText(f"Saved {path}");return True
        return False

    def accept_import(self,text):
        from .model_placement import is_model_card,prepare,insert
        if is_model_card(text):
            plan=prepare(self.doc,text)
            pins='\n'.join(f'{name}: {node}' for name,node in plan['pin_order'])
            message=f"Create {plan['part']['ref']} from this model?\n\n{plan['model']}\n\nPin order (SPICE):\n{pins}\n\nThe part starts unconnected. Existing components and models are preserved.\nParser-compatible does not mean manufacturer-qualified."
            if wx.MessageBox(message,'Paste model → schematic part',wx.OK|wx.CANCEL,self)==wx.OK:
                size=self.canvas.GetClientSize();point=self.canvas.world(wx.Point(size.width//2,size.height//2))
                part_id=insert(self.doc,plan,point);self.book.SetSelection(0)
                self.canvas.selected={part_id};self.refresh_document(force_source=True);self.canvas.SetFocus()
                self.SetStatusText('Model part inserted and selected. E: properties; Space: rotate; Ctrl+Z: undo. Connect its isolated pins before running.')
            return
        report=import_text(text)
        if report.document:
            if wx.MessageBox(f"Detected {report.format}. Replace the current sheet with {len(report.document.data['components'])} imported parts?","Import review",wx.YES_NO|wx.NO_DEFAULT,self)==wx.YES:
                if self.confirm_replace():self.doc=report.document;self.path=None;self.canvas.selected.clear();self.refresh_document(force_source=True)
        else:
            self.last_import=report
            with wx.Dialog(self,title=f"{report.format} import review",size=(700,500),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
                box=wx.BoxSizer(wx.VERTICAL);field=wx.TextCtrl(dlg,value="\n".join(report.warnings)+"\n\n"+json.dumps(report.inventory,indent=2),style=wx.TE_MULTILINE|wx.TE_READONLY)
                box.Add(field,1,wx.EXPAND|wx.ALL,8)
                def preserve(e):
                    path=self.choose_path("Preserve original imported source","Original source (*.*)|*.*",True)
                    if path:path.write_text(report.source,encoding="utf-8")
                button(dlg,"Save original source…",preserve,box);dlg.SetSizer(box);dlg.ShowModal()

    def import_file(self):
        path=self.choose_path("Import circuit / model","Circuit files|*.cir;*.net;*.sp;*.asc;*.qsch;*.kicad_sch;*.spksch|All files|*.*")
        if path:self.accept_import(path.read_text(encoding="utf-8-sig"))

    def paste(self):
        focus=wx.Window.FindFocus()
        if isinstance(focus,(wx.TextCtrl,wx.stc.StyledTextCtrl)):focus.Paste();return
        if wx.TheClipboard.Open():
            data=wx.TextDataObject();ok=wx.TheClipboard.GetData(data);wx.TheClipboard.Close()
            if ok:self.accept_import(data.GetText())

    def select_all_parts(self):
        focus=wx.Window.FindFocus()
        if isinstance(focus,(wx.TextCtrl,wx.ComboBox,wx.stc.StyledTextCtrl)):focus.SelectAll();return
        self.canvas.selected={p['id'] for p in self.doc.data['components']}
        self.canvas.Refresh();self.refresh_inspector()

    def copy_circuit(self):
        focus=wx.Window.FindFocus()
        if isinstance(focus,(wx.TextCtrl,wx.ComboBox,wx.stc.StyledTextCtrl)):focus.Copy();return
        # Whole-sheet transport preserves scoped models and dependent sources.
        # Fragment merging needs explicit reference and net remapping first.
        if not wx.TheClipboard.Open():raise ValueError('Clipboard is busy')
        try:
            if not wx.TheClipboard.SetData(wx.TextDataObject(json.dumps(self.doc.data))):raise ValueError('Unable to copy circuit')
        finally:wx.TheClipboard.Close()
        self.SetStatusText('Copied entire schematic with models. Paste opens import review; selected-part duplication is not implemented.')

    def export_file(self):
        self.apply_source()
        path=self.choose_path("Export shared SPICE netlist","SPICE netlist (*.cir)|*.cir",True)
        if path:path.write_text(export_netlist(self.doc),encoding="utf-8")

    def make_source(self):
        panel=wx.Panel(self.book);box=wx.BoxSizer(wx.VERTICAL);tools=wx.BoxSizer(wx.HORIZONTAL)
        button(panel,"Validate and apply netlist",lambda e:self.guarded(self.apply_source),tools)
        button(panel,'SPICE directive manager',lambda e:self.book.SetSelection(7),tools)
        box.Add(tools);self.source=text_editor(panel,RC_DECK);box.Add(self.source,1,wx.EXPAND);panel.SetSizer(box);self.book.AddPage(panel,"Circuit text")
        self.source.Bind(wx.stc.EVT_STC_CHANGE,lambda e:self.update_title())

    def apply_source(self):
        self.doc.apply_source(self.source.GetText())
        self.source_baseline=self.doc.data['source']
        self.canvas.selected.intersection_update(p['id'] for p in self.doc.data['components'])
        self.refresh_document()

    def make_plot(self):
        self.plot_splitter=wx.SplitterWindow(self.book);self.plot_splitter.SetMinimumPaneSize(100)
        panel=wx.Panel(self.plot_splitter);self.plot_panel=panel;box=wx.BoxSizer(wx.VERTICAL);controls=wx.BoxSizer(wx.HORIZONTAL)
        self.expression=wx.TextCtrl(panel,value="v(out)",style=wx.TE_PROCESS_ENTER)
        controls.Add(self.expression,1,wx.ALL|wx.EXPAND,4)
        self.expression.Bind(wx.EVT_TEXT_ENTER,lambda e:self.guarded(lambda:self.add_trace(self.expression.GetValue())))
        button(panel,"Add expression",lambda e:self.guarded(lambda:self.add_trace(self.expression.GetValue())),controls)
        button(panel,"Measure",lambda e:self.guarded(self.measure),controls)
        self.measure_window=wx.Choice(panel,choices=["Whole capture","A/B window"]);self.measure_window.SetSelection(0);controls.Add(self.measure_window,0,wx.ALL,4)
        button(panel,"Run circuit",lambda e:self.guarded(self.run),controls)
        box.Add(controls,0,wx.EXPAND)
        self.figure=Figure(figsize=(9,5),layout="constrained");self.plot=FigureCanvasWxAgg(panel,-1,self.figure)
        self.plot.SetMinSize((100,100))
        self.plot.SetToolTip('Wheel: zoom time around pointer. Shift+wheel: zoom Y. Toolbar: pan or box zoom. Fit Y in view: scale visible signals. Click: place measurement cursor.')
        self.toolbar=NavigationToolbar2WxAgg(self.plot);box.Add(self.toolbar,0,wx.EXPAND);box.Add(self.plot,1,wx.EXPAND)
        self.measurements=wx.TextCtrl(panel,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,105));box.Add(self.measurements,0,wx.EXPAND|wx.ALL,4)
        row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE)
        button(panel,"Fit all",lambda e:self.draw_plot(),row)
        button(panel,"Fit Y in view",lambda e:self.fit_plot_y(),row)
        button(panel,"Clear traces",lambda e:(self.traces.clear(),self.cursors.clear(),self.draw_plot()),row)
        button(panel,"Save .spkdata",lambda e:self.guarded(self.save_data),row)
        button(panel,"Load .spkdata",lambda e:self.guarded(self.open_data),row)
        button(panel,"Functions…",lambda e:wx.MessageBox(FUNCTION_HELP,"Signal math",parent=self),row)
        button(panel,"Solve equation…",lambda e:self.guarded(self.solve_equation),row)
        button(panel,"Crossings…",lambda e:self.guarded(self.crossings),row)
        button(panel,"Axes…",lambda e:self.guarded(self.axis_options),row)
        from .plot_panes import edit_panes
        button(panel,'Stack / arrange panes…',lambda e:self.guarded(lambda:edit_panes(self)),row)
        self.plot_tools=row
        box.Add(row,0,wx.EXPAND);panel.SetSizer(box);self.plot_splitter.Initialize(panel);self.book.AddPage(self.plot_splitter,"Plots & measurements")
        row=wx.WrapSizer(wx.HORIZONTAL)
        button(panel,'Split canvas / plots',lambda e:self.toggle_split(),row)
        button(panel,'Tools / readout',lambda e:self.toggle_plot_details(),row)
        self.run_choice=wx.Choice(panel,choices=['No run']);self.run_choice.SetSelection(0);row.Add(self.run_choice,0,wx.ALL,3)
        self.run_choice.Bind(wx.EVT_CHOICE,lambda e:self.guarded(lambda:self.select_run(self.run_choice.GetSelection())))
        self.overlay_runs=wx.CheckBox(panel,label='Overlay step runs');row.Add(self.overlay_runs,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        self.overlay_runs.Bind(wx.EVT_CHECKBOX,lambda e:self.guarded(self.draw_plot))
        button(panel,'Select overlays…',lambda e:self.guarded(self.select_overlays),row)
        self.grid_control=wx.CheckBox(panel,label='Plot grid');self.grid_control.SetValue(True);row.Add(self.grid_control,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        self.grid_control.Bind(wx.EVT_CHECKBOX,lambda e:(setattr(self,'plot_grid',self.grid_control.GetValue()),self.draw_plot(preserve_view=True)))
        button(panel,'Cursor window…',lambda e:self.guarded(self.plot_interactions.show_cursors),row)
        button(panel,'Schematic instruments…',lambda e:self.guarded(self.manage_instruments),row)
        box.Insert(1,row,0,wx.EXPAND)
        live=wx.BoxSizer(wx.HORIZONTAL)
        live.Add(wx.StaticText(panel,label='Live DC source:'),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,5)
        self.live_source=wx.Choice(panel);live.Add(self.live_source,0,wx.ALL,4)
        self.live_value=wx.TextCtrl(panel,value='1',size=(100,-1));live.Add(self.live_value,0,wx.ALL,4)
        self.live_apply=button(panel,'Apply SI value',lambda e:self.guarded(self.apply_live_source),live)
        self.live_label=wx.StaticText(panel,label='Continuous: best-effort pacing, 20,000-sample rolling capture. Not HIL qualified.')
        box.Add(live,0,wx.EXPAND);box.Add(self.live_label,0,wx.LEFT|wx.BOTTOM,5)
        self.plot_detail_items=[self.measurements,self.plot_tools,live,self.live_label];self.plot_details=True
        from .plot_interactions import PlotInteractions
        self.plot_interactions=PlotInteractions(self);self.plot_interactions.connect()
        self.plot.mpl_connect("motion_notify_event",self.hover)
        self.plot.mpl_connect("pick_event",self.pick_trace)
        self.draw_plot()

    def toggle_split(self):
        """Move the actual editor; no screenshot or independent schematic copy."""
        if self.split_view:
            self.split_return.Hide()
            self.plot_splitter.Unsplit(self.canvas);self.canvas.Reparent(self.schematic_host)
            self.schematic_host.GetSizer().Add(self.canvas,1,wx.EXPAND);self.canvas.Show();self.schematic_host.Layout()
        else:
            self.split_return.Show()
            self.schematic_host.GetSizer().Detach(self.canvas);self.canvas.Reparent(self.plot_splitter)
            self.plot_splitter.SplitHorizontally(self.canvas,self.plot_panel,max(150,self.plot_splitter.GetClientSize().height//3));self.canvas.Show()
        self.split_view=not self.split_view;self.book.SetSelection(1);self.plot_splitter.Layout();self.canvas.Refresh()
        self.set_plot_details(not self.split_view)

    def set_plot_details(self,visible):
        self.plot_details=visible
        for item in self.plot_detail_items:self.plot_panel.GetSizer().Show(item,visible)
        self.plot_panel.Layout();self.draw_plot(preserve_view=True)

    def toggle_plot_details(self):self.set_plot_details(not self.plot_details)

    def toggle_canvas_grid(self):
        self.canvas_grid=not self.canvas_grid;self.canvas.Refresh()

    def manage_instruments(self):
        from .workspace_dialogs import instruments_dialog
        instruments_dialog(self)

    def show_part_alerts(self):
        with wx.Dialog(self,title='Measured part limits · not a physical damage prediction',size=(850,560),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
            box=wx.BoxSizer(wx.VERTICAL)
            text='Use component properties → Limits: voltage_v, current_a, power_w in SI. Warning at 80%, exceeded at 100% of declared limit.\nPeaks refer to the retained capture window, not discarded continuous history. Thermal and other unsupported limits are marked unavailable.\n\n'
            text+=json.dumps(self.part_alerts,indent=2) if self.part_alerts else 'No recorded electrical limit warnings.'
            field=wx.TextCtrl(dlg,value=text,style=wx.TE_MULTILINE|wx.TE_READONLY);box.Add(field,1,wx.EXPAND|wx.ALL,8);box.Add(dlg.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,5)
            dlg.SetSizer(box);apply_window(dlg,self.palette);dlg.ShowModal()

    def manage_cursors(self):
        from .workspace_dialogs import cursors_dialog
        cursors_dialog(self)

    def select_overlays(self):
        if not self.run_results:raise ValueError('Run a stepped circuit first')
        with wx.MultiChoiceDialog(self,'Select runs to overlay; the active run always remains visible.','Step trace visibility',self.run_choice.GetStrings()) as dlg:
            dlg.SetSelections(list(range(len(self.run_results))) if self.visible_runs is None else sorted(self.visible_runs))
            apply_window(dlg,self.palette)
            if dlg.ShowModal()==wx.ID_OK:
                self.visible_runs=set(dlg.GetSelections());self.overlay_runs.SetValue(True);self.draw_plot()

    def cursor_descriptor(self,index):
        if index<len(self.cursor_bindings):
            binding=self.cursor_bindings[index]
        else:binding={'run':self.selected_run,'expression':self.expression.GetValue()}
        return dict(binding,time=self.cursors[index])

    def cursor_label(self,index):
        from .plot_workspace import sample,format_value
        c=self.cursor_descriptor(index)
        try:value=format_value(sample(self.run_engines[c['run']],c['expression'],c['time']))
        except Exception as exc:value='Unavailable: '+str(exc)
        return f"{chr(65+index)} · run {c['run']+1} · {c['expression']} · {c['time']:.9g}s · {value}"

    def put_cursor(self,time,run,expression,index=None):
        from .plot_workspace import sample
        if not 0<=run<len(self.run_engines) or self.run_engines[run] is None:raise ValueError('Choose a transient run')
        sample(self.run_engines[run],expression,time)
        if index is None and len(self.cursors)>=16:raise ValueError('At most 16 cursors; use the cursor manager to edit or remove them')
        while len(self.cursor_bindings)<len(self.cursors):self.cursor_bindings.append({'run':self.selected_run,'expression':expression})
        self.cursor_bindings=self.cursor_bindings[:len(self.cursors)]
        if index is None:self.cursors.append(time);self.cursor_bindings.append({'run':run,'expression':expression})
        else:self.cursors[index]=time;self.cursor_bindings[index]={'run':run,'expression':expression}

    def run(self):
        if not self.prepare_run():return
        from .run_control import BatchRun
        backend=self.run_snapshot['run_profile'].get('backend','native')
        self.active_run=BatchRun(self.run_snapshot['source'],self.library,method=self.run_snapshot['run_profile']['method'],
                                 kind='ngspice' if backend=='ngspice' else 'circuit')
        self.active_record_id=self.run_history.start(self.run_snapshot,self.library if backend=='native' else 'explicit ngspice process adapter')
        self.manager.refresh_runs()
        self.job_running=True;self.SetStatusText(f'Running {backend} batch worker — Stop cancels; Pause is available in native Continuous mode')
        self.update_run_controls()

    def start_frequency(self,settings):
        if self.job_running:raise ValueError('A simulation or build is already running')
        self.apply_source()
        from .run_control import BatchRun
        self.run_snapshot=deepcopy(self.doc.data);self.run_snapshot['document_source']=self.doc.data['source']
        from .model_fidelity import preflight
        preflight(self.run_snapshot, 'ac')
        self.active_run=BatchRun(self.run_snapshot['source'],None,kind='frequency',settings=settings)
        self.active_record_id=self.run_history.start(self.run_snapshot,'Python/SciPy linear frequency backend')
        self.run_history.get(self.active_record_id)['frequency_setup']=deepcopy(settings)
        self.job_running=True;self.SetStatusText('Running bounded linear AC / descriptor PZ in a cancellable worker')
        self.manager.refresh_runs();self.update_run_controls()

    def prepare_run(self,interactive=False):
        if self.job_running:raise ValueError('A simulation or build is already running')
        self.apply_source()
        snapshot=deepcopy(self.doc.data)
        snapshot['document_source']=snapshot['source']
        snapshot['run_profile']['execution']='continuous' if interactive else 'batch'
        snapshot['source']=effective_source(snapshot['source'],snapshot['run_profile'])
        backend=snapshot['run_profile'].get('backend','native')
        from .model_fidelity import preflight,preflight_compatibility
        if backend=='ngspice':preflight_compatibility(snapshot)
        else:
            preflight(snapshot)
            from python.spikes.netlist import parse_netlist
            parse_netlist(snapshot['source'],native_extensions=True,transient_capture='rolling' if interactive else 'full')
        if backend=='native' and not self.library:
            path=self.choose_path("Select SPIKES native engine","Native library|*.dll;*.so;*.dylib")
            if not path:return False
            self.library=str(path)
        self.run_snapshot=snapshot
        self.run_expressions=list(dict.fromkeys([p['expression'] for p in self.run_snapshot['probes']]+self.run_snapshot['expressions']))
        self.cursors.clear();self.live_samples=-1
        return True

    def start_interactive(self):
        if not self.prepare_run(interactive=True):return
        from .run_control import InteractiveRun
        profile=self.run_snapshot['run_profile']
        controller=self.controller_panel.attached()
        self.active_run=InteractiveRun(self.run_snapshot['source'],self.library,method=profile['method'],capacity=profile['capture_samples'],speed_ratio=profile['speed_ratio'],controller=controller)
        self.active_record_id=self.run_history.start(self.run_snapshot,self.library)
        self.manager.refresh_runs()
        self.job_running=True
        self.live_source.Set(list(self.active_run.controls))
        if self.live_source.GetCount():self.live_source.SetSelection(0)
        if self.book.GetSelection()!=13:self.book.SetSelection(1)
        self.update_run_controls()

    def pause_run(self):
        from .run_control import InteractiveRun
        if not isinstance(self.active_run,InteractiveRun):raise ValueError('Pause is available in Continuous mode only')
        if self.active_run.state=='paused':self.active_run.resume()
        else:self.active_run.pause()

    def stop_run(self):
        if self.active_run:self.active_run.stop();self.SetStatusText('Stopping — waiting for worker / native step boundary')

    def apply_live_source(self):
        from .run_control import InteractiveRun
        if not isinstance(self.active_run,InteractiveRun):raise ValueError('Start Continuous mode to control a source')
        self.active_run.set_source(self.live_source.GetStringSelection(),float(self.live_value.GetValue()))
        self.SetStatusText('Source change queued for next native step; circuit file is unchanged')

    def show_run_result(self,result,live=False):
        self.collection_snapshot=deepcopy(self.run_snapshot);self.collection_record_id=self.active_record_id
        self.run_results=result.get('runs',[result]);self.run_engines=[SignalMath.from_result(r) if len(r.get('data',{}).get('time_s',[]))>=2 else None for r in self.run_results]
        from .plot_workspace import run_label
        self.run_choice.Set([run_label(r,i) for i,r in enumerate(self.run_results)])
        self.selected_run=0;self.run_choice.SetSelection(0)
        if not live:self.cursors.clear();self.cursor_bindings.clear();self.visible_runs=None
        self.display_run_result(self.run_results[0],live)

    def select_run(self,index):
        if not 0<=index<len(self.run_results):return
        if 'data' not in self.run_results[index]:return  # single imported .spkdata already active
        self.selected_run=index;self.run_choice.SetSelection(index)
        saved=self.run_expressions
        try:
            if self.traces:self.run_expressions=[n for n,_,_ in self.traces]
            self.display_run_result(self.run_results[index])
        finally:self.run_expressions=saved

    def display_run_result(self,result,live=False):
        self.result=result;self.result_source=self.collection_snapshot
        result.setdefault('provenance',{})['resolved_models']=deepcopy(self.collection_snapshot.get('resolved_models'))
        self.capture_record_id=self.collection_record_id
        from .part_alerts import evaluate_limits
        self.part_alerts=evaluate_limits(self.collection_snapshot,result)
        result.setdefault('provenance',{}).update(run_id=self.collection_record_id,
            run_profile=deepcopy(self.collection_snapshot['run_profile']),thermal_setup=deepcopy(self.collection_snapshot['thermal_setup']),
            thermal_solver_binding='not_coupled',document_revision=self.collection_snapshot['revision'])
        if 'time_s' not in result.get('data',{}):
            self.math=None;self.traces.clear();self.draw_plot()
            self.measurements.SetValue(json.dumps(result.get('data',result),indent=2));self.canvas.Refresh();self.book.SetSelection(1);return
        if len(result['data']['time_s'])<2:return
        self.math=SignalMath.from_result(result)
        requested=[n for n,_,_ in self.traces] if live and self.live_samples>=0 else list(self.run_expressions)
        if not requested:requested=['v(out)' if 'v(out)' in self.math.signals else next(iter(self.math.signals))]
        self.traces.clear();errors=[]
        for expression in requested:
            try:self.add_trace(expression,persist=False,redraw=False)
            except Exception as exc:errors.append(f'{expression}: {exc}')
        self.draw_plot()
        self.canvas.Refresh()
        if errors:self.measurements.SetValue('Some saved probes / expressions could not be evaluated:\n'+'\n'.join(errors))
        if result.get('measurements'):
            self.measurements.SetValue('Directive measurements (recorded native samples)\n'+json.dumps(result['measurements'],indent=2)+('\nProbe errors: '+'; '.join(errors) if errors else ''))
        if not live:self.book.SetSelection(1)

    def poll_run(self,event=None):
        from .run_control import InteractiveRun,BatchRun
        run=self.active_run
        if run is None:return
        data=None
        if isinstance(run,BatchRun):
            run.poll()
            if run.state=='completed':
                if run.kind=='frequency':
                    run.result['provenance'].update(run_id=self.active_record_id,document_revision=self.run_snapshot['revision'],
                        resolved_models=deepcopy(self.run_snapshot.get('resolved_models')),
                        thermal_setup=deepcopy(self.run_snapshot['thermal_setup']),thermal_solver_binding='not_coupled')
                    self.guarded(lambda:self.frequency.accept(run.result))
                else:self.guarded(lambda:self.show_run_result(run.result))
                data=run.result.get('data')
        else:
            snapshot=run.snapshot()
            if snapshot and snapshot['provenance']['total_samples']!=self.live_samples:
                self.guarded(lambda:self.show_run_result(snapshot,live=True))
                self.live_samples=snapshot['provenance']['total_samples']
            if snapshot:
                data=snapshot['data']
                self.live_label.SetLabel(f"{run.state} · t={snapshot['data']['time_s'][-1]:.6g} s · retained {len(snapshot['data']['time_s'])} / {snapshot['provenance']['total_samples']} samples")
        state=run.state
        self.run_history.update(self.active_record_id,state,data=data,error=run.error)
        if isinstance(run,BatchRun) and run.result:
            record=self.run_history.get(self.active_record_id);record['measurements']=deepcopy(run.result.get('measurements',{}))
            if run.result.get('runs'):
                record['step_runs']=[{'parameters':r['provenance']['step_parameters'],'samples':len(r['data'].get('time_s',r['data'].get('sweep',{}).get('values',[0])))} for r in run.result['runs']]
                record['samples']=sum(r['samples'] for r in record['step_runs'])
        self.manager.refresh_runs()
        if state in ('completed','stopped','failed'):
            self.active_run=None;self.job_running=False
            if state=='failed':self.measurements.SetValue(run.error or 'Native run failed')
            stale=self.run_snapshot['document_source']!=self.doc.data['source'] or self.run_snapshot['revision']!=self.doc.data['revision'] or self.source.GetText()!=self.doc.data['source']
            self.SetStatusText(f"{state.title()} · captured revision {self.run_snapshot['revision']}"+(' · circuit has changed since this run' if stale else '')+(f' · {run.error}' if run.error else ''))
            self.guarded(lambda:self.manager.sequences.finished(run))
            if self.closing:self.closing=False;wx.CallAfter(self.Close)
        self.update_run_controls()

    def background(self,work,done,message):
        if self.job_running:raise ValueError("A job is already running")
        self.job_running=True;self.SetStatusText(message)
        self.update_run_controls()
        def worker():
            try:value=work();error=None
            except Exception as exc:value=None;error=str(exc)
            def complete():
                self.job_running=False
                self.update_run_controls()
                if error:self.report_error(error)
                else:self.guarded(lambda:done(value))
            wx.CallAfter(complete)
        threading.Thread(target=worker,daemon=True).start()

    def add_trace(self,expression,persist=True,redraw=True):
        if not self.math:raise ValueError("Run or open recorded data first")
        answer=self.math.evaluate(expression)
        values=np.broadcast_to(answer.values,self.math.time.shape)
        if np.iscomplexobj(values):raise ValueError("Choose real(), imag(), abs() or angle() for a complex expression")
        self.traces=[trace for trace in self.traces if trace[0]!=expression]
        self.traces.append((expression,values,str(answer.unit)))
        if persist and expression not in self.doc.data['expressions']:self.doc.commit(lambda d:d['expressions'].append(expression))
        if redraw:self.draw_plot();self.book.SetSelection(1)
        self.update_title()

    def draw_plot(self,preserve_view=False):
        from .plotting import add_waveform,install_navigation
        from .plot_panes import groups
        panes=groups(self.traces,self.doc.data['plot_layout'])
        previous=[(ax.get_xlim(),ax.get_ylim()) for ax in getattr(self,'axes',[])] if preserve_view else []
        self.figure.clear();self.axes=[]
        if not panes:
            install_navigation(self.plot,[])
            ax=self.figure.add_subplot();ax.set_title("Run a circuit or load recorded data");ax.set_xlabel("Time [s]");ax.set_ylabel("Signal");figure_theme(self.figure,self.palette,self.theme_name);self.plot_interactions.after_draw();self.plot.draw();return
        grid=self.figure.add_gridspec(len(panes),1,height_ratios=[v[2] for v in panes])
        for i,(pane,items,weight) in enumerate(panes):
            unit=items[0][2]
            ax=self.figure.add_subplot(grid[i],sharex=self.axes[0] if self.axes else None);self.axes.append(ax)
            for name,values,u in items:
                add_waveform(ax,self.math.time,values,label=name,linewidth=1.3,visible=name not in self.hidden_traces)
                if self.overlay_runs.GetValue():
                    for run_index,engine in enumerate(self.run_engines):
                        if run_index==self.selected_run or engine is None or (self.visible_runs is not None and run_index not in self.visible_runs):continue
                        answer=engine.evaluate(name);other=np.broadcast_to(answer.values,engine.time.shape)
                        if np.iscomplexobj(other) or str(answer.unit)!=u:continue
                        label=f'{name} · run {run_index+1}'
                        add_waveform(ax,engine.time,other,label=label,linewidth=1,linestyle='--',visible=label not in self.hidden_traces)
            if i<len(panes)-1:ax.tick_params(labelbottom=False)
            ax.set_ylabel(f"[{unit}]");ax.xaxis.set_major_formatter(EngFormatter(unit="s"));ax.grid(True,alpha=.25)
            if not self.plot_grid:ax.grid(False)
            legend=ax.legend(loc="best")
            for label in legend.get_texts():label.set_picker(True);label.set_alpha(.35 if label.get_text() in self.hidden_traces else 1)
            for j,time in enumerate(self.cursors):ax.axvline(time,color="tab:red",linestyle="--",linewidth=.8);ax.text(time,.98,chr(65+j),transform=ax.get_xaxis_transform(),va="top")
            if i<len(previous):ax.set_xlim(previous[i][0]);ax.set_ylim(previous[i][1])
        self.axes[-1].set_xlabel("Simulation time");self.figure.suptitle("SPIKES · "+self.run_choice.GetStringSelection())
        self.figure.set_layout_engine('constrained',h_pad=.1,w_pad=.08,rect=(0,.045,1,.955))
        figure_theme(self.figure,self.palette,self.theme_name)
        install_navigation(self.plot,self.axes)
        self.plot_interactions.after_draw()
        self.plot.draw()

    def fit_plot_y(self):
        from .plotting import fit_visible_y
        fit_visible_y(self.axes);self.plot.draw_idle()

    def pick_trace(self,event):
        if hasattr(event.artist,"get_text"):
            name=event.artist.get_text()
            self.hidden_traces.symmetric_difference_update({name})
            for ax in self.axes:
                for line in ax.lines:
                    if line.get_label()==name:line.set_visible(not line.get_visible());event.artist.set_alpha(1 if line.get_visible() else .35)
            self.plot.draw_idle()

    def hover(self,event):
        if not self.math or event.xdata is None or not event.inaxes:return
        t=float(np.clip(event.xdata,self.math.time[0],self.math.time[-1]))
        self.SetStatusText(f"Run {self.selected_run+1} · t={t:.9g} s | "+" | ".join(f"{n}={np.interp(t,self.math.time,y):.7g} {u}" for n,y,u in self.traces))

    def cursor(self,event):
        if not self.math or event.xdata is None or not event.inaxes or self.toolbar.mode:return
        if getattr(event,'button',1)!=1:return
        def place():
            # Bind the clicked pane's first visible signal, not the expression editor.
            names=[line.get_label() for line in event.inaxes.lines if line.get_visible()]
            expression=next((n for n,_,_ in self.traces if n in names),self.expression.GetValue())
            self.put_cursor(float(np.clip(event.xdata,self.math.time[0],self.math.time[-1])),self.selected_run,expression)
            self.draw_plot(preserve_view=True);self.canvas.Refresh()
            lines=[self.cursor_label(i) for i in range(len(self.cursors))]
            if len(self.cursors)>=2:
                a,b=self.cursors[:2];lines.append(f'Δt(A,B)={b-a:.9g} s')
                from .plot_workspace import cursor_math,format_value
                try:lines.append('B − A = '+format_value(cursor_math(self.run_engines,self.cursor_descriptor(0),self.cursor_descriptor(1))))
                except ValueError as exc:lines.append(str(exc))
            self.measurements.SetValue('\n'.join(lines))
        self.guarded(place)

    def measure(self):
        if not self.math:raise ValueError("No recorded data")
        expr=self.expression.GetValue();lines=[];engine=self.math
        if self.measure_window.GetSelection()==1:
            if len(self.cursors)<2:raise ValueError('Place both A/B cursors first')
            left,right=sorted(self.cursors[:2])
            if left<self.math.time[0] or right>self.math.time[-1]:raise ValueError('A/B interval is outside the selected run')
            from .signal_math import Quantity
            time=np.unique(np.r_[left,self.math.time[(self.math.time>left)&(self.math.time<right)],right])
            engine=SignalMath(time,{name:Quantity(np.interp(time,self.math.time,q.values),q.unit) for name,q in self.math.signals.items()})
            lines.append(f'A/B window: {left:.9g} to {right:.9g} s (endpoints linearly interpolated)')
        for fn in ("min","max","pp","mean","rms"):
            q=engine.evaluate(f"{fn}({expr})");lines.append(f"{fn}: {q.values:.9g} [{q.unit}]")
        self.measurements.SetValue("\n".join(lines))

    def crossings(self):
        if not self.math:raise ValueError('No recorded data')
        with wx.TextEntryDialog(self,'Threshold in the expression unit; edge: rising/falling/either','Threshold crossings','0.5; rising') as dlg:
            if dlg.ShowModal()==wx.ID_OK:
                level,edge=dlg.GetValue().split(';');times=self.math.crossings(self.expression.GetValue(),float(level),edge.strip())
                self.measurements.SetValue('Crossing times [s]: '+', '.join(f'{t:.9g}' for t in times[:200])+f'\nTotal crossings: {len(times)}')

    def axis_options(self):
        if not self.axes:raise ValueError('Plot a trace first')
        with wx.SingleChoiceDialog(self,'Select the Y-axis scale for all panels','Plot axes',['linear','log','symlog']) as dlg:
            if dlg.ShowModal()==wx.ID_OK:
                scale=dlg.GetStringSelection()
                if scale=='log' and any(np.any(values<=0) for _,values,_ in self.traces):raise ValueError('Log axes require strictly positive trace values; use symlog for bipolar signals')
                for ax in self.axes:ax.set_yscale(scale)
                self.plot.draw()

    def solve_equation(self):
        if not self.math:raise ValueError("Run or load data to provide the equation context")
        with wx.TextEntryDialog(self,'Enter expression = 0; bracket left; bracket right',"Bracketed equation solve","cos(x)-x; 0; 1") as dlg:
            if dlg.ShowModal()==wx.ID_OK:
                expr,left,right=dlg.GetValue().split(";");root=self.math.solve(expr,float(left),float(right));self.measurements.SetValue(f"{expr} = 0\nx = {root:.12g}")

    def save_data(self):
        if not self.math:raise ValueError("No recorded data")
        path=self.choose_path("Save result archive (new file)","SPIKES results (*.spkdata)|*.spkdata",True)
        if path:
            save_result(path,self.math,self.result.get("provenance",{}) if self.result else {})
            record=self.run_history.get(self.capture_record_id)
            if record:record['capture_archive']=str(path);self.manager.refresh_runs()

    def open_data(self):
        path=self.choose_path("Open results","SPIKES results (*.spkdata)|*.spkdata")
        if path:
            self.math,provenance=load_result(path);self.result={"provenance":provenance};self.capture_record_id=None;self.result_source=None
            self.run_results=[self.result];self.run_engines=[self.math];self.selected_run=0
            self.run_choice.Set(['Loaded capture · '+path.name]);self.run_choice.SetSelection(0)
            self.cursors.clear();self.cursor_bindings.clear();self.traces.clear();self.add_trace(next(iter(self.math.signals)));self.canvas.Refresh()

    def make_ide(self):
        panel=wx.Panel(self.book);box=wx.BoxSizer(wx.VERTICAL);row=wx.BoxSizer(wx.HORIZONTAL)
        self.language=wx.Choice(panel,choices=["Verilog","C++","C"]);self.language.SetSelection(0);row.Add(self.language,0,wx.ALL,4)
        self.top=wx.TextCtrl(panel,value="top");row.Add(self.top,0,wx.ALL,4)
        button(panel,"Open source",lambda e:self.guarded(self.open_code),row);button(panel,"Save source",lambda e:self.guarded(self.save_code),row)
        button(panel,"Check / compile",lambda e:self.guarded(lambda:self.build_code("check")),row)
        button(panel,"Synthesize",lambda e:self.guarded(lambda:self.build_code("synthesize")),row)
        button(panel,"Simulate testbench",lambda e:self.guarded(lambda:self.build_code("simulate")),row)
        button(panel,"Open VCD timing",lambda e:self.guarded(self.timing),row);box.Add(row,0,wx.EXPAND)
        self.code=text_editor(panel,"module top(input a, input b, output y);\n  assign y = a & b;\nendmodule\n")
        self.code.SetLexer(wx.stc.STC_LEX_VERILOG);self.code.SetKeyWords(0,"module endmodule input output wire reg always assign begin end if else")
        self.code.StyleSetForeground(wx.stc.STC_V_WORD,wx.Colour("#0758a0"));self.code.StyleSetForeground(wx.stc.STC_V_COMMENT,wx.Colour("#4b775b"))
        self.language.Bind(wx.EVT_CHOICE,lambda e:self.code.SetLexer(wx.stc.STC_LEX_VERILOG if self.language.GetStringSelection()=="Verilog" else wx.stc.STC_LEX_CPP))
        box.Add(self.code,2,wx.EXPAND)
        self.build_log=wx.TextCtrl(panel,style=wx.TE_MULTILINE|wx.TE_READONLY);box.Add(self.build_log,1,wx.EXPAND|wx.ALL,4)
        self.timing_figure=Figure(figsize=(8,2),layout="constrained");self.timing_canvas=FigureCanvasWxAgg(panel,-1,self.timing_figure)
        box.Add(NavigationToolbar2WxAgg(self.timing_canvas),0,wx.EXPAND);box.Add(self.timing_canvas,1,wx.EXPAND)
        panel.SetSizer(box);self.book.AddPage(panel,"C / C++ / Verilog IDE")

    def open_code(self):
        path=self.choose_path("Open code","Source|*.v;*.sv;*.c;*.cpp;*.h;*.hpp|All files|*.*")
        if path:self.code.SetText(path.read_text(encoding="utf-8"))
    def save_code(self):
        path=self.choose_path("Save code","Source|*.v;*.sv;*.c;*.cpp",True)
        if path:path.write_text(self.code.GetText(),encoding="utf-8")
    def build_code(self,mode):
        source,language,top=self.code.GetText(),self.language.GetStringSelection(),self.top.GetValue()
        def done(report):
            self.build_log.SetValue(f"Tool: {report['tool']}\nExit: {report['exit_code']}\n"+report["output"])
            self.SetStatusText(f"{mode} finished with exit code {report['exit_code']}")
            self.last_build=report
            if "timing" in report:self.draw_timing(report["timing"])
        self.background(lambda:analyze(source,language,mode,top),done,"Running compiler…")

    def timing(self):
        path=self.choose_path("Open real digital simulation timing","VCD (*.vcd)|*.vcd")
        if path:self.draw_timing(read_vcd(path.read_text(encoding="utf-8")))
    def draw_timing(self,data):
        self.timing_figure.clear();ax=self.timing_figure.add_subplot()
        names=[]
        for i,(name,signal) in enumerate(data["signals"].items()):
            names.append(name);trans=signal["transitions"]
            if not trans:continue
            times=[t for t,v in trans]+[data["end_time_s"]];values=[]
            for t,value in trans:
                values.append(i+(.65 if "x" not in value and "z" not in value and int(value,2)!=0 else .1))
                if signal["width"]>1 or "x" in value or "z" in value:ax.text(t,i+.3,value,fontsize=8)
            ax.step(times,values+[values[-1]],where="post")
        ax.set_yticks(range(len(names)),names);ax.set_xlabel("Time");ax.xaxis.set_major_formatter(EngFormatter(unit="s"));ax.set_title("VCD transitions · vector values annotated");self.timing_canvas.draw()
        figure_theme(self.timing_figure,self.palette,self.theme_name);self.timing_canvas.draw_idle()

    def make_parts(self):
        panel=wx.Panel(self.book);box=wx.BoxSizer(wx.VERTICAL);row=wx.BoxSizer(wx.HORIZONTAL)
        self.search=wx.SearchCtrl(panel);row.Add(self.search,1,wx.ALL|wx.EXPAND,4)
        button(panel,"Open library",lambda e:self.guarded(self.open_library),row);button(panel,"Save library",lambda e:self.guarded(self.save_library),row)
        button(panel,"Save symbol edits",lambda e:self.guarded(self.apply_symbol),row);button(panel,"New symbol",lambda e:self.new_symbol(),row)
        box.Add(row,0,wx.EXPAND)
        self.library_list=wx.ListBox(panel,size=(-1,130));box.Add(self.library_list,0,wx.EXPAND|wx.ALL,4)
        design=wx.BoxSizer(wx.HORIZONTAL)
        self.symbol_editor=text_editor(panel);design.Add(self.symbol_editor,1,wx.EXPAND)
        self.symbol_figure=Figure(figsize=(4,4),layout="constrained");self.symbol_canvas=FigureCanvasWxAgg(panel,-1,self.symbol_figure);design.Add(self.symbol_canvas,1,wx.EXPAND)
        box.Add(design,1,wx.EXPAND)
        self.library_list.Bind(wx.EVT_LISTBOX,lambda e:self.symbol_editor.SetText(json.dumps(self.symbols[self.library_list.GetStringSelection()],indent=2)))
        self.search.Bind(wx.EVT_TEXT,lambda e:self.filter_library())
        self.symbol_editor.Bind(wx.stc.EVT_STC_CHANGE,lambda e:self.preview_symbol())
        from .resources import resource_dir
        default_library=resource_dir('library')/'core-symbols-v1.json'
        self.symbols={s['id']:s for s in json.loads(default_library.read_text(encoding='utf-8'))['symbols']} if default_library.is_file() else {}
        self.new_symbol();panel.SetSizer(box);self.book.AddPage(panel,"Parts browser & designer")

    def new_symbol(self):
        ident="user.block"+str(len(self.symbols)+1)
        self.symbols[ident]={"id":ident,"name":"New block","family":"generic","standard":"common-convention","conformance":"unverified","grid":10,
            "body_keepout":{"min":[-20,-20],"max":[20,20]},"label_keepouts":[],
            "terminals":[{"id":"1","name":"IN","at":[-40,0],"leg_endpoint":[-20,0],"direction":"west","connection_indicator":True},{"id":"2","name":"OUT","at":[40,0],"leg_endpoint":[20,0],"direction":"east","connection_indicator":True}],
            "primitives":[{"kind":"polygon","points":[[-20,-20],[20,-20],[20,20],[-20,20],[-20,-20]]}]}
        self.filter_library();self.symbol_editor.SetText(json.dumps(self.symbols[ident],indent=2))

    def filter_library(self):self.library_list.Set([n for n in self.symbols if self.search.GetValue().lower() in (n+" "+self.symbols[n].get("name","")).lower()])
    def preview_symbol(self):
        try:symbol=json.loads(self.symbol_editor.GetText())
        except (ValueError,AttributeError):return
        from matplotlib.patches import Circle,Arc,Polygon,Rectangle
        self.symbol_figure.clear();ax=self.symbol_figure.add_subplot()
        try:
            for item in symbol.get("primitives",[]):
                kind=item.get("kind")
                if kind in ("line","polyline"):
                    points=np.array(item["points"]);ax.plot(points[:,0],points[:,1],color=self.palette['fg'])
                elif kind=="polygon":ax.add_patch(Polygon(item["points"],fill=item.get("fill",False),edgecolor=self.palette['fg'],facecolor=self.palette['selected']))
                elif kind=="circle":ax.add_patch(Circle(item["center"],item["radius"],fill=False,edgecolor=self.palette['fg']))
                elif kind=="arc":ax.add_patch(Arc(item["center"],2*item["radius"],2*item["radius"],theta1=item["start_deg"],theta2=item["start_deg"]+item["sweep_deg"],edgecolor=self.palette['fg']))
            for pin in symbol.get("terminals",[]):
                x,y=pin["at"];a,b=pin["leg_endpoint"];ax.plot([x,a],[y,b],color=self.palette['accent']);ax.plot([x],[y],marker="o",mfc=self.palette['canvas'],mec=self.palette['accent']);ax.annotate(pin["name"],(x,y),xytext=(0,8),textcoords="offset points")
            if "body_keepout" in symbol:
                x,y=symbol["body_keepout"]["min"];a,b=symbol["body_keepout"]["max"];ax.add_patch(Rectangle((x,y),a-x,b-y,fill=False,linestyle=":",edgecolor="#999999"))
            ax.set_title(symbol.get("name","Symbol preview"));ax.set_aspect("equal",adjustable="datalim");ax.autoscale();ax.margins(.4);ax.grid(alpha=.2);ax.invert_yaxis();self.symbol_canvas.draw_idle()
            figure_theme(self.symbol_figure,self.palette,self.theme_name)
        except (KeyError,TypeError,ValueError):return
    def apply_symbol(self):
        from .symbol_validation import validate_symbol
        symbol=json.loads(self.symbol_editor.GetText());validate_symbol(symbol)
        self.symbols[symbol["id"]]=symbol;self.filter_library();self.SetStatusText("Symbol saved in library memory; save library to persist")
    def open_library(self):
        path=self.choose_path("Open symbol library","JSON symbol library|*.json")
        if path:
            from .symbol_validation import validate_symbol
            data=json.loads(path.read_text(encoding="utf-8"))
            if data.get("contract")!="spikes/studio-symbol-library/v1":raise ValueError("Unsupported library")
            for symbol in data["symbols"]:validate_symbol(symbol)
            self.symbols={s["id"]:s for s in data["symbols"]};self.filter_library()
    def save_library(self):
        self.apply_symbol();path=self.choose_path("Save symbol library","JSON symbol library|*.json",True)
        if path:write_json(path,{"contract":"spikes/studio-symbol-library/v1","library_id":"user.local","version":"1.0.0","license":"User-supplied; review before redistribution","symbols":list(self.symbols.values())})

    def shortcuts(self):
        with wx.Dialog(self,title="Editable keyboard profiles",size=(720,550),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
            box=wx.BoxSizer(wx.VERTICAL);profile=wx.Choice(dlg,choices=["SPIKES","KiCad-inspired","LTspice-inspired"]);profile.SetSelection(0);box.Add(profile,0,wx.ALL,5)
            hint=wx.StaticText(dlg,label='R / C / L / D place basic parts. Set part_shortcuts to false to disable.\nLink a preset with "part:generic.resistor.001": "Alt+R", or use its browser context menu.');box.Add(hint,0,wx.ALL,5)
            editor=wx.TextCtrl(dlg,value=json.dumps(self.keymap.to_data(),indent=2),style=wx.TE_MULTILINE);box.Add(editor,1,wx.EXPAND|wx.ALL,5)
            profile.Bind(wx.EVT_CHOICE,lambda e:editor.SetValue(json.dumps(Keymap.preset(profile.GetStringSelection()).to_data(),indent=2)))
            row=wx.BoxSizer(wx.HORIZONTAL)
            def apply(e):
                def work():
                    old=self.keymap
                    try:self.keymap=Keymap.from_data(json.loads(editor.GetValue()));self.install_keys();self.part_keys_item.Check(self.keymap.part_shortcuts)
                    except Exception:self.keymap=old;self.install_keys();raise
                    dlg.EndModal(wx.ID_OK)
                self.guarded(work)
            def load(e):
                def work():
                    path=self.choose_path("Load shortcuts","Shortcut profile|*.spkkeys;*.json")
                    if path:editor.SetValue(json.dumps(Keymap.load(path).to_data(),indent=2))
                self.guarded(work)
            def save(e):
                def work():
                    keys=Keymap.from_data(json.loads(editor.GetValue()));path=self.choose_path("Save shortcuts","Shortcut profile|*.spkkeys",True)
                    if path:keys.save(path)
                self.guarded(work)
            button(dlg,"Load…",load,row);button(dlg,"Save…",save,row);button(dlg,"Apply",apply,row);box.Add(row,0,wx.ALIGN_RIGHT);dlg.SetSizer(box);dlg.ShowModal()

    def bom(self):
        with wx.Dialog(self,title="Bill of materials",size=(850,460),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
            box=wx.BoxSizer(wx.VERTICAL);table=wx.grid.Grid(dlg);rows=self.doc.bom();keys=["refs","quantity","kind","value","package","variant"]
            table.CreateGrid(len(rows),len(keys));table.EnableEditing(False)
            for c,key in enumerate(keys):table.SetColLabelValue(c,key.title())
            for r,row in enumerate(rows):
                for c,key in enumerate(keys):table.SetCellValue(r,c,str(row[key]))
            table.AutoSizeColumns();box.Add(table,1,wx.EXPAND|wx.ALL,8)
            def save(e):
                path=self.choose_path("Export BoM","CSV (*.csv)|*.csv",True)
                if path:
                    with path.open("w",newline="",encoding="utf-8-sig") as stream:
                        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)
            button(dlg,"Export CSV…",save,box);dlg.SetSizer(box);dlg.ShowModal()

    def make_help(self):
        panel=wx.Panel(self.book);box=wx.BoxSizer(wx.VERTICAL)
        text="""SPIKES Studio workbench\n\n1. Schematic: select a part, press E, edit its value or pins and apply. Drag moves parts in one undoable transaction. Every property tab has its own persisted fields. Ctrl+Z/Ctrl+Y undo/redo. Limits are declarations; this editor does not infer device failure from them.\n\n2. F5 validates/applies current circuit text and runs the C++ batch solver. Shift+F5 stops its worker. Ctrl+F5 starts Continuous with a 20,000-sample rolling window; F6 pauses/resumes actual solver state. Live DC source values apply at the next step. Continuous mode is best effort, not HIL qualified. Over-limit batch requests show a non-blocking error; reduce TSTOP/increase TSTEP or use Continuous. Plots display the result's actual timestamps, voltages, currents and powers. Click twice for delta cursors. Use the native plot toolbar to zoom, pan, fit and export PNG/SVG/PDF. Separate units get separate linked panels.\n\n3. P selects voltage probe placement; click a terminal. Shift+P selects differential voltage: click positive then negative. I / Shift+I attach current/power probes to a component. Saved probes are restored after Run; double-click a probe to add it to an existing plot.\n\n4. Edit > Keyboard shortcuts accepts JSON profiles, detects duplicate keys, and loads/saves .spkkeys. Inspired presets are a subset, not full copies of another application's mappings.\n\n5. C/C++/Verilog: edit source with line numbers and syntax highlighting. Check invokes a real compiler. Verilog synthesis invokes Yosys. Logs contain the actual command outcome; unavailable tools report an error. Open VCD for timing transitions, unknowns and vector values. This is waveform viewing, not target-specific static timing analysis.\n\n6. Import and canvas Ctrl+V detect native schematics, SPICE netlists, .MODEL cards and external drawing sources. Review prompts identify what can be translated. LTspice/KiCad drawing inventory and original source can be preserved; use SPICE netlists for executable exchange. QSPICE drawing conversion remains unsupported. File > Export writes the circuit's SPICE source.\n\n7. .spksch is versioned JSON with semantic components, source, probes and edits. .spkdata stores exact numeric arrays in independently compressed chunks, explicit timestamps, signal units and run provenance. Save new result files to avoid overwriting a capture.\n\n8. Parts browser & designer loads/saves the symbol geometry contract and validates terminal anchors, leg endpoints and body bounds. The current designer edits geometry as JSON. Component properties now include Value and Simulation model type controls for ideal R/C/L, DC/PULSE/PWL sources, diode model cards and smooth switches. Model-specific fields write validated netlist parameters. Arbitrary model source notes remain inert.\n\n"""+FUNCTION_HELP
        help_text=wx.TextCtrl(panel,value=text,style=wx.TE_MULTILINE|wx.TE_READONLY);box.Add(help_text,1,wx.EXPAND|wx.ALL,10)
        row=wx.BoxSizer(wx.HORIZONTAL)
        button(panel,'Illustrated guide',lambda e:self.open_help_file('WORKBENCH_GUIDE.md'),row)
        from .help_center import show as learning_center,examples as browse_examples
        button(panel,'Learning Center',lambda e:self.guarded(lambda:learning_center(self)),row)
        button(panel,'Example circuits',lambda e:self.guarded(lambda:browse_examples(self)),row)
        button(panel,'Designer / cursor controls',lambda e:self.open_help_file('DESIGNER_WORKSPACE.md'),row)
        button(panel,'Thermal margin reports',lambda e:self.open_help_file('THERMAL_MARGIN_REPORTS.md'),row)
        button(panel,'Audio / sensors / simulation families',lambda e:self.open_help_file('AUDIO_SENSOR_SIMULATION_FAMILIES.md'),row)
        button(panel,'Dashboard / visual symbols',lambda e:self.open_help_file('VISUAL_WORKSPACES.md'),row)
        button(panel,'Workflow roadmap / release gates',lambda e:self.open_help_file('WORKFLOW_REFERENCE.md'),row)
        button(panel,'Library / controller guide',lambda e:self.open_help_file('COMPONENT_LIBRARY.md'),row)
        button(panel,'Recorded walkthrough',lambda e:self.open_help_file('media/workbench-walkthrough.gif'),row)
        box.Add(row,0,wx.EXPAND);panel.SetSizer(box);self.book.AddPage(panel,"Help")

    def open_help_file(self,name):
        from .resources import resource_dir
        locations=[resource_dir('docs')]
        import sys
        locations.append(Path(sys.prefix)/'share/spikes/studio/docs')
        path=next((root/name for root in locations if (root/name).is_file()),None)
        if path:wx.LaunchDefaultApplication(str(path))
        else:wx.MessageBox('The illustrated guide is included in the standalone source package under studio/docs.','Help',parent=self)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--library",type=Path);parser.add_argument("--capture-dir",type=Path)
    parser.add_argument('--verify-controls-dir',type=Path)
    parser.add_argument('--verify-model-editor-dir',type=Path)
    parser.add_argument('--verify-setup-dir',type=Path)
    parser.add_argument('--verify-directives-dir',type=Path)
    parser.add_argument('--verify-frequency-dir',type=Path)
    parser.add_argument('--verify-upgrade-dir',type=Path)
    parser.add_argument('--verify-workspace-dir',type=Path)
    parser.add_argument('--verify-catalog-dir',type=Path)
    parser.add_argument('--verify-browser-dir',type=Path)
    parser.add_argument('--verify-editor-dir',type=Path)
    parser.add_argument('--verify-sequences-dir',type=Path)
    parser.add_argument('--verify-help-dir',type=Path)
    parser.add_argument('--verify-symbol-dir',type=Path)
    parser.add_argument('--verify-dashboard-dir',type=Path)
    parser.add_argument('--verify-collection-dir',type=Path)
    args=parser.parse_args(argv)
    app=wx.App(False)
    if args.verify_browser_dir:app.SetAssertMode(wx.APP_ASSERT_EXCEPTION)
    native_appearance(load_theme());frame=Studio(str(args.library) if args.library else None);frame.Show()
    if args.capture_dir:
        from .ui_evidence import capture_session
        wx.CallLater(500,capture_session,frame,args.capture_dir)
    if args.verify_controls_dir:
        from .ui_regression import verify_controls
        wx.CallLater(500,verify_controls,frame,args.verify_controls_dir)
    if args.verify_model_editor_dir:
        from .ui_model_evidence import verify_model_editor
        wx.CallLater(500,verify_model_editor,frame,args.verify_model_editor_dir)
    if args.verify_setup_dir:
        from .ui_setup_evidence import verify_setup
        wx.CallLater(500,verify_setup,frame,args.verify_setup_dir)
    if args.verify_directives_dir:
        from .ui_directive_evidence import verify_directives
        wx.CallLater(500,verify_directives,frame,args.verify_directives_dir)
    if args.verify_frequency_dir:
        from .ui_frequency_evidence import verify_frequency
        wx.CallLater(500,verify_frequency,frame,args.verify_frequency_dir)
    if args.verify_upgrade_dir:
        from .ui_upgrade_evidence import verify_upgrade
        wx.CallLater(500,verify_upgrade,frame,args.verify_upgrade_dir)
    if args.verify_workspace_dir:
        from .ui_workspace_evidence import verify_workspace
        wx.CallLater(500,verify_workspace,frame,args.verify_workspace_dir)
    if args.verify_catalog_dir:
        from .ui_catalog_evidence import verify_catalog
        wx.CallLater(500,verify_catalog,frame,args.verify_catalog_dir)
    if args.verify_browser_dir:
        from .ui_browser_evidence import verify_browser
        wx.CallLater(500,verify_browser,frame,args.verify_browser_dir)
    if args.verify_editor_dir:
        from .ui_editor_evidence import verify_editor
        wx.CallLater(500,verify_editor,frame,args.verify_editor_dir)
    if args.verify_sequences_dir:
        from .ui_sequence_evidence import verify_sequences
        wx.CallLater(500,verify_sequences,frame,args.verify_sequences_dir)
    if args.verify_help_dir:
        from .ui_help_evidence import verify_help
        wx.CallLater(500,verify_help,frame,args.verify_help_dir)
    if args.verify_symbol_dir:
        from .ui_symbol_evidence import verify
        wx.CallLater(500,verify,frame,args.verify_symbol_dir)
    if args.verify_dashboard_dir:
        from .dashboard_panel import verify_dashboard
        wx.CallLater(500,verify_dashboard,frame,args.verify_dashboard_dir)
    if args.verify_collection_dir:
        from .ui_collection_evidence import verify_collection
        wx.CallLater(500,verify_collection,frame,args.verify_collection_dir)
    app.MainLoop()
    return 1 if getattr(frame,'validation_failure',False) else 0


if __name__=="__main__":raise SystemExit(main())
