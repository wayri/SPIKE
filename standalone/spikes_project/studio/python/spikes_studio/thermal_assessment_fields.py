# SPDX-License-Identifier: Apache-2.0
"""Labeled inputs for the existing thermal-margin screening report."""
from copy import deepcopy
import math
import wx

FIELDS=(('max_junction_c','Maximum junction rating [°C]'),
        ('warning_margin_c','Warning headroom [°C]'),
        ('supplied_temperature_c','Supplied junction temperature [°C; optional]'),
        ('theta_ja_k_w','Effective junction-to-ambient resistance [K/W]'),
        ('steady_power_w','Supplied steady dissipated power [W]'),
        ('ambient_c','Ambient temperature [°C]'),
        ('conditions_evidence','Cooling / power conditions and evidence'))


class ThermalAssessmentFields(wx.Panel):
    def __init__(self,parent,parts):
        super().__init__(parent);self.controls={}
        setups=[part.get('parameters',{}).get('thermal_assessment',{}) for part in parts]
        self.editable=all(isinstance(s,dict) for s in setups) and all(s==setups[0] for s in setups)
        self.initial=deepcopy(setups[0]) if self.editable else {}
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(self,label='Thermal margin report inputs — not a coupled self-heating model.\nLeave unknown values blank. A supplied junction temperature takes precedence over a steady-power estimate; recorded solver temperatures take precedence over both.')
        note.Wrap(310);box.Add(note,0,wx.ALL,8)
        for key,label in FIELDS:
            box.Add(wx.StaticText(self,label=label),0,wx.LEFT|wx.RIGHT|wx.TOP,8)
            control=wx.TextCtrl(self,value=str(self.initial.get(key,'')))
            control.Enable(self.editable);control.SetName(label);self.controls[key]=control
            box.Add(control,0,wx.EXPAND|wx.ALL,8)
        if not self.editable:box.Add(wx.StaticText(self,label='Mixed or structured thermal inputs: select one component to edit.'),0,wx.ALL,8)
        self.before={k:c.GetValue() for k,c in self.controls.items()};self.SetSizer(box)

    def dirty(self):
        return any(c.GetValue()!=self.before[k] for k,c in self.controls.items())

    def merge(self,parameters):
        if not self.dirty():return parameters
        if not self.editable:raise ValueError('Select one thermal configuration to edit')
        from python.spikes.netlist import parse_spice_number
        result=deepcopy(parameters);setup=deepcopy(self.initial)
        for key,control in self.controls.items():
            text=control.GetValue().strip()
            if text==self.before[key]:continue
            if not text:setup.pop(key,None);continue
            if key=='conditions_evidence':setup[key]=text;continue
            value=parse_spice_number(text,'scalar')
            if not math.isfinite(value):raise ValueError('Thermal inputs must be finite')
            if key in ('max_junction_c','supplied_temperature_c','ambient_c') and value<=-273.15:raise ValueError('Temperature must exceed absolute zero')
            if key=='theta_ja_k_w' and value<=0:raise ValueError('Thermal resistance must be positive')
            if key in ('warning_margin_c','steady_power_w') and value<0:raise ValueError('Power and warning headroom must be nonnegative')
            setup[key]=value
        if setup:result['thermal_assessment']=setup
        else:result.pop('thermal_assessment',None)
        return result
