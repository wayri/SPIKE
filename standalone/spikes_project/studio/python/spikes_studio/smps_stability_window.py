# SPDX-License-Identifier: Apache-2.0
"""Floating explicit SMPS analytical design workspace with bounded background work."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg,NavigationToolbar2WxAgg
from python.spikes.smps_stability import default_config,analyze,validate
from .smps_stability_view import VIEWS,describe,render
from .themes import apply_window,figure_theme
from .flat_controls import ActionButton

TOPOLOGIES=('buck','boost','buck_boost','flyback')
TOPOLOGY_LABELS=('Buck','Boost','Inverting buck-boost (magnitude)','Flyback (isolated)')
CONTROLLERS=('pi','type_ii','type_iii')
CONTROLLER_LABELS=('PI','Type II','Type III')
FIELDS=(('input_voltage_v','Input voltage [V]'),('duty_cycle','Duty [0..1]'),
        ('inductance_h','Inductance / primary Lm [H]'),('capacitance_f','Output capacitance [F]'),
        ('load_resistance_ohm','Resistive load [ohm]'),('switching_frequency_hz','Switching frequency [Hz]'),
        ('turns_ratio','Turns Ns/Np (flyback)'),('controller_gain','Controller K [1/s]'),
        ('zero1_hz','Controller zero 1 [Hz]'),('zero2_hz','Controller zero 2 [Hz]'),
        ('pole1_hz','Controller pole 1 [Hz]'),('pole2_hz','Controller pole 2 [Hz]'),
        ('feedback_gain','Feedback gain [V/V]'),('pwm_gain','PWM gain [duty/V]'),
        ('start_hz','Sweep start [Hz]'),('stop_hz','Sweep stop [Hz]'),('points','Sweep points'))


class SMPSStabilityWindow(wx.Frame):
    def __init__(self,owner):
        config=validate(deepcopy(owner.doc.data['metadata'].get('smps_stability_setup',default_config())))
        super().__init__(owner,title='SMPS stability - averaged CCM design',size=(1200,820))
        self.SetMinSize((880,650));self.owner=owner;self.closed=False;self.busy=False;self.result=None
        self.executor=ThreadPoolExecutor(max_workers=1)
        panel=wx.Panel(self);box=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(box)
        note=wx.StaticText(panel,label='Explicit ideal CCM voltage-mode model. Not extracted from the schematic. No DCM, ESR/DCR, switching harmonics, current-mode or hardware qualification.')
        note.Wrap(1100);box.Add(note,0,wx.ALL,8)
        middle=wx.BoxSizer(wx.HORIZONTAL);form=wx.ScrolledWindow(panel,size=(310,-1));form.SetScrollRate(0,10)
        controls=wx.BoxSizer(wx.VERTICAL);form.SetSizer(controls)
        self.topology=wx.Choice(form,choices=list(TOPOLOGY_LABELS));self.topology.SetSelection(0)
        self.controller=wx.Choice(form,choices=list(CONTROLLER_LABELS));self.controller.SetSelection(1)
        for label,choice in [('Power stage',self.topology),('Compensator',self.controller)]:
            controls.Add(wx.StaticText(form,label=label),0,wx.LEFT|wx.TOP,8);controls.Add(choice,0,wx.EXPAND|wx.ALL,8)
        self.fields={}
        for key,label in FIELDS:
            controls.Add(wx.StaticText(form,label=label),0,wx.LEFT|wx.TOP,8)
            field=wx.TextCtrl(form,value=str(config.get(key,default_config()[key])));field.SetName(label)
            self.fields[key]=field;controls.Add(field,0,wx.EXPAND|wx.ALL,8)
        self.topology.SetSelection(TOPOLOGIES.index(config['topology']));self.controller.SetSelection(CONTROLLERS.index(config['controller_type']))
        self.fields['controller_gain'].SetToolTip('K in C(s)=K/s times configured zeros/poles. Default 100 is an unstable demonstration, not a tuned recommendation.')
        middle.Add(form,0,wx.EXPAND|wx.RIGHT,8)
        right=wx.BoxSizer(wx.VERTICAL);row=wx.WrapSizer(wx.HORIZONTAL)
        self.calculate=ActionButton(panel,label='Analyze model');self.calculate.Bind(wx.EVT_BUTTON,lambda e:self.request());row.Add(self.calculate,0,wx.ALL,4)
        self.backend=wx.Choice(panel,choices=['C++ native','Python reference']);self.backend.SetSelection(0);row.Add(self.backend,0,wx.ALL,4)
        self.view=wx.Choice(panel,choices=list(VIEWS));self.view.SetSelection(0);row.Add(self.view,0,wx.ALL,4)
        for label,fn in [('Save setup in project',self.save_setup),('Export analysis…',self.export)]:
            button=ActionButton(panel,label=label);button.Bind(wx.EVT_BUTTON,lambda e,action=fn:owner.guarded(action));row.Add(button,0,wx.ALL,4)
        right.Add(row,0,wx.EXPAND)
        self.figure=Figure();self.canvas=FigureCanvasWxAgg(panel,-1,self.figure);self.canvas.SetMinSize((300,200))
        right.Add(NavigationToolbar2WxAgg(self.canvas),0,wx.EXPAND);right.Add(self.canvas,1,wx.EXPAND)
        self.report=wx.TextCtrl(panel,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,175));right.Add(self.report,0,wx.EXPAND|wx.TOP,6)
        middle.Add(right,1,wx.EXPAND);box.Add(middle,1,wx.EXPAND|wx.ALL,8)
        self.figure.add_subplot().set_title('Enter explicit parameters, then Analyze model')
        self.topology.Bind(wx.EVT_CHOICE,lambda e:self.reflect());self.controller.Bind(wx.EVT_CHOICE,lambda e:self.reflect())
        self.view.Bind(wx.EVT_CHOICE,lambda e:owner.guarded(self.draw));self.reflect()
        apply_window(self,owner.palette);figure_theme(self.figure,owner.palette,owner.theme_name);self.canvas.draw()
        self.Bind(wx.EVT_CLOSE,self.close);self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed);self.Show()

    def reflect(self):
        self.fields['turns_ratio'].Enable(TOPOLOGIES[self.topology.GetSelection()]=='flyback')
        control=CONTROLLERS[self.controller.GetSelection()]
        self.fields['zero2_hz'].Enable(control=='type_iii')
        self.fields['pole1_hz'].Enable(control!='pi');self.fields['pole2_hz'].Enable(control=='type_iii')

    def config(self):
        from python.spikes.netlist import parse_spice_number
        result=default_config()
        for key,field in self.fields.items():
            if field.IsEnabled():result[key]=int(field.GetValue()) if key=='points' else parse_spice_number(field.GetValue(),'scalar')
        result.update(topology=TOPOLOGIES[self.topology.GetSelection()],controller_type=CONTROLLERS[self.controller.GetSelection()])
        return result

    def request(self):
        if self.busy:return
        try:
            config=self.config();self.busy=True;self.calculate.Enable(False)
            self.report.SetValue('Analyzing explicit averaged model...')
            if self.backend.GetSelection()==0:
                if not self.owner.library:raise ValueError('Select a native library with SMPS API or explicitly choose Python reference')
                from python.spikes.native_smps import analyze as native_analyze
                future=self.executor.submit(native_analyze,config,self.owner.library)
            else:future=self.executor.submit(analyze,config)
            future.add_done_callback(lambda task:wx.CallAfter(self.complete,task))
        except ValueError as error:
            self.busy=False;self.calculate.Enable(True);self.report.SetValue(str(error))

    def complete(self,future):
        if self.closed or not self:return
        self.busy=False;self.calculate.Enable(True)
        try:self.accept(future.result())
        except Exception as error:self.report.SetValue('Analysis failed: '+str(error)+'\nPrevious graph retained; it is not a result of the failed setup.')

    def accept(self,result):
        self.result=deepcopy(result);self.report.SetValue(describe(result));self.draw()

    def draw(self):
        if self.result is None:return
        axes=render(self.figure,self.result,self.view.GetStringSelection())
        from .plotting import install_navigation
        install_navigation(self.canvas,axes)
        figure_theme(self.figure,self.owner.palette,self.owner.theme_name);self.canvas.draw()

    def save_setup(self):
        if self.owner.job_running:raise ValueError('Stop the active circuit job before changing project settings')
        config=validate(self.config())
        self.owner.doc.commit(lambda data:data['metadata'].__setitem__('smps_stability_setup',config))
        self.owner.update_title()

    def export(self):
        if self.result is None:raise ValueError('Analyze the model before exporting')
        with wx.FileDialog(self,'Export SMPS analytical report',defaultFile='smps-stability.json',wildcard='JSON (*.json)|*.json',style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal()==wx.ID_OK:
                from .document import write_json
                write_json(dialog.GetPath(),self.result)

    def close(self,event):self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True);self.Destroy()

    def destroyed(self,event):
        if event.GetEventObject() is self:self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True)
        event.Skip()
