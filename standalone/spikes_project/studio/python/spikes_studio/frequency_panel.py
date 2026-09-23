"""Scientific complex-frequency and descriptor pole/zero workspace."""
import csv
import json
from copy import deepcopy
import numpy as np
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg,NavigationToolbar2WxAgg
from .frequency import VIEWS,validate_result,render,series,save_frequency,load_frequency


def button(parent,label,callback,sizer):
    control=wx.Button(parent,label=label);control.Bind(wx.EVT_BUTTON,lambda e:parent.owner.guarded(callback))
    sizer.Add(control,0,wx.ALL,3);return control


class FrequencyPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.result=None;self.plotted=[];self.marker=[]
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(self,label='Linear AC + SISO pole/zero analysis · Python/SciPy backend, not the C++ transient solver. R/L/C and linear sources only; no nonlinear bias linearization. Up to 256 MNA unknowns.')
        note.Wrap(990);box.Add(note,0,wx.ALL,8)
        row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE);self.fields={}
        for key,label,value in [('source','Excite source','V1'),('output','P/Z output','V(out)'),('start_hz','Start Hz','1'),('stop_hz','Stop Hz','1Meg'),('points','Points','401')]:
            row.Add(wx.StaticText(self,label=label),0,wx.ALIGN_CENTER_VERTICAL|wx.ALL,3)
            control=wx.TextCtrl(self,value=value,size=(95 if key!='output' else 125,-1));self.fields[key]=control;row.Add(control,0,wx.ALL,3)
        self.scale=wx.Choice(self,choices=['log','linear']);self.scale.SetSelection(0);row.Add(self.scale,0,wx.ALL,3)
        self.pz=wx.CheckBox(self,label='Calculate poles / zeros');self.pz.SetValue(True);row.Add(self.pz,0,wx.ALL,3)
        button(self,'Run AC / PZ',self.run,row);button(self,'Stop',owner.stop_run,row);box.Add(row,0,wx.EXPAND)
        row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE)
        self.view=wx.Choice(self,choices=list(VIEWS));self.view.SetSelection(0);row.Add(self.view,0,wx.ALL,3)
        self.expression=wx.TextCtrl(self,value='V(out)/V(in)',size=(265,-1),style=wx.TE_PROCESS_ENTER);row.Add(self.expression,1,wx.ALL,3)
        button(self,'Plot expression',self.draw,row);button(self,'Transfer preset',self.transfer,row);button(self,'Input impedance preset',self.impedance,row)
        self.rf_kind=wx.Choice(self,choices=['Impedance','Admittance','Reflection coefficient']);self.rf_kind.SetSelection(0);row.Add(self.rf_kind,0,wx.ALL,3)
        row.Add(wx.StaticText(self,label='Z₀ [Ω]'),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,3)
        self.z0=wx.TextCtrl(self,value='50',size=(65,-1));row.Add(self.z0,0,wx.ALL,3)
        self.mirror=wx.CheckBox(self,label='Nyquist conjugate mirror');row.Add(self.mirror,0,wx.ALL,3);box.Add(row,0,wx.EXPAND)
        self.view.Bind(wx.EVT_CHOICE,lambda e:owner.guarded(self.draw))
        self.expression.Bind(wx.EVT_TEXT_ENTER,lambda e:owner.guarded(self.draw))
        self.figure=Figure(figsize=(8,4));self.plot=FigureCanvasWxAgg(self,-1,self.figure)
        self.toolbar=NavigationToolbar2WxAgg(self.plot);box.Add(self.toolbar,0,wx.EXPAND);box.Add(self.plot,1,wx.EXPAND)
        self.report=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,105));box.Add(self.report,0,wx.EXPAND|wx.ALL,4)
        row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE)
        button(self,'Save frequency archive…',self.save,row);button(self,'Open frequency archive…',self.load,row)
        button(self,'Export expression CSV…',self.export_csv,row);button(self,'Pole-zero table',self.pole_table,row)
        button(self,'Save FRA block…',self.save_fra,row);button(self,'Run saved FRA block…',self.run_fra,row)
        box.Add(row,0,wx.EXPAND)
        note=wx.StaticText(self,label='Expressions: V(out)/V(in), V(in)/(-I(V1)), f [Hz]. Click a trace for frequency/value readout; circles/squares mark sweep start/end. Nyquist here is a sampled locus, not a closed-contour stability certificate.')
        note.Wrap(990);box.Add(note,0,wx.ALL,6);self.SetSizer(box)
        self.plot.mpl_connect('button_press_event',self.pick)
        ax=self.figure.add_subplot();ax.set_title('Run a linear circuit or open recorded frequency data');ax.set_xlabel('Frequency [Hz]');self.plot.draw()

    def settings(self):
        from .frequency import parse_hz
        return {'source':self.fields['source'].GetValue(),'output':self.fields['output'].GetValue(),
            'start_hz':parse_hz(self.fields['start_hz'].GetValue()),
            'stop_hz':parse_hz(self.fields['stop_hz'].GetValue()),
            'points':int(self.fields['points'].GetValue()),'scale':self.scale.GetStringSelection(),'pole_zero':self.pz.GetValue()}

    def run(self):self.owner.start_frequency(self.settings())

    def save_fra(self):
        settings=self.settings()
        if settings['start_hz']<=0 or settings['stop_hz']<=settings['start_hz'] or not 2<=settings['points']<=10000:
            raise ValueError('Invalid FRA sweep')
        with wx.TextEntryDialog(self,'Name this reusable linear FRA analysis block','Save FRA block') as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            name=dialog.GetValue().strip()
        if not name or len(name)>80:raise ValueError('FRA block name requires 1..80 characters')
        blocks=deepcopy(self.owner.doc.data['metadata'].get('fra_blocks',{}))
        if name in blocks:raise ValueError('Name exists; use a distinct name to preserve the previous block')
        if len(blocks)>=32:raise ValueError('At most 32 FRA blocks per document')
        blocks[name]={'contract':'spikes/studio-fra-block/v1','settings':settings}
        self.owner.doc.commit(lambda data:data['metadata'].__setitem__('fra_blocks',blocks))
        self.owner.refresh_document()

    def run_fra(self):
        blocks=self.owner.doc.data['metadata'].get('fra_blocks',{})
        names=sorted(blocks)
        if not names:raise ValueError('Save a linear FRA block first')
        with wx.SingleChoiceDialog(self,'Runs against the current circuit; not automatic loop-gain injection.','Run FRA block',names) as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            block=blocks[names[dialog.GetSelection()]]
        if block.get('contract')!='spikes/studio-fra-block/v1':raise ValueError('Unknown FRA block format')
        self.owner.start_frequency(deepcopy(block['settings']))

    def accept(self,result):
        validate_result(result);self.result=deepcopy(result)
        # Preserve user expressions; apply a source-aware transfer default on first run.
        if self.expression.GetValue()=='V(out)/V(in)':self.expression.SetValue(result['settings']['output']+'/'+result['settings']['input_voltage'])
        self.owner.book.SetSelection(8);self.owner.guarded(self.draw)

    def draw(self):
        if self.result is None:raise ValueError('Run AC / PZ or open a frequency archive first')
        self.plotted=render(self.figure,self.result,self.expression.GetValue(),self.view.GetStringSelection(),
            rf_kind=self.rf_kind.GetStringSelection(),z0=float(self.z0.GetValue()),mirror=self.mirror.GetValue())
        from .themes import figure_theme
        figure_theme(self.figure,self.owner.palette,self.owner.theme_name)
        self.plot.draw();self.report.SetValue('Captured source SHA256: '+self.result['provenance'].get('source_sha256','unknown')+'\n'+
            self.result['provenance'].get('backend','Imported frequency data')+'\nAC excitation: '+self.result['settings']['source']+' (unit phasor; other independent AC sources zero). dB magnitude floor: −300 dB.')
        if self.view.GetStringSelection()=='Pole-zero':self.pole_table()

    def transfer(self):
        if self.result is None:raise ValueError('Run AC first')
        self.expression.SetValue(self.result['settings']['output']+'/'+self.result['settings']['input_voltage']);self.view.SetStringSelection('Bode dB / phase');self.draw()

    def impedance(self):
        if self.result is None:raise ValueError('Run AC first')
        s=self.result['settings'];self.expression.SetValue(s['input_voltage']+'/('+s['input_current']+')')
        self.rf_kind.SetStringSelection('Impedance');self.view.SetStringSelection('Smith impedance');self.draw()

    def pick(self,event):
        if event.inaxes is None or self.toolbar.mode:return
        candidates=[]
        for ax,x,y,freq in self.plotted:
            if ax!=event.inaxes:continue
            xy=ax.transData.transform(np.column_stack((x,y)));distance=np.hypot(xy[:,0]-event.x,xy[:,1]-event.y)
            if not np.isfinite(distance).any():continue
            index=int(np.nanargmin(distance));candidates.append((distance[index],index,x,y,freq))
        if not candidates:return
        distance,index,x,y,freq=min(candidates,key=lambda v:v[0])
        if distance>25:return
        self.report.SetValue(f'Sample {index} · f={freq[index]:.12g} Hz\nPlot x={x[index]:.12g}, y={y[index]:.12g}\n'+self.expression.GetValue())
        engine=validate_result(self.result);values,unit=series(engine,self.expression.GetValue())
        self.report.AppendText(f' = {values[index]:.12g} [{unit}]\n|value|={abs(values[index]):.12g}; phase={np.degrees(np.angle(values[index])):.9g}°')

    def pole_table(self):
        if self.result is None or not self.result.get('pole_zero'):raise ValueError('No calculated pole-zero result')
        from .frequency import complex_values
        pz=self.result['pole_zero'];lines=['Descriptor-system poles and SISO zeros [rad/s]; no cancellation reduction or nonlinear bias model.']
        for key in ('poles_rad_s','zeros_rad_s'):
            values=complex_values(pz['data'][key]);lines.append(key+': '+(', '.join(f'{v:.10g}' for v in values) or '(none finite)'))
        lines.append('Infinite descriptor eigenvalues omitted: poles '+str(pz['data']['infinite_pole_count'])+', zeros '+str(pz['data']['infinite_zero_count']))
        self.report.SetValue('\n'.join(lines))

    def save(self):
        if self.result is None:raise ValueError('No frequency data')
        path=self.owner.choose_path('Save frequency archive (new file)','SPIKES frequency (*.spkfreq)|*.spkfreq',True)
        if path:
            result=deepcopy(self.result)
            result['plot_setup']={'expression':self.expression.GetValue(),'view':self.view.GetStringSelection(),
                'rf_kind':self.rf_kind.GetStringSelection(),'z0':float(self.z0.GetValue()),'mirror':self.mirror.GetValue()}
            save_frequency(path,result)
            record=self.owner.run_history.get(result['provenance'].get('run_id'))
            if record:record['frequency_archive']=str(path);self.owner.manager.refresh_runs()

    def load(self):
        path=self.owner.choose_path('Open frequency archive','SPIKES frequency (*.spkfreq)|*.spkfreq')
        if path:
            result=load_frequency(path);setup=result.get('plot_setup')
            if setup:
                self.expression.SetValue(setup['expression']);self.view.SetStringSelection(setup['view'])
                self.rf_kind.SetStringSelection(setup['rf_kind']);self.z0.SetValue(str(setup['z0']));self.mirror.SetValue(setup['mirror'])
            self.accept(result)

    def export_csv(self):
        if self.result is None:raise ValueError('No frequency data')
        engine=validate_result(self.result);values,unit=series(engine,self.expression.GetValue())
        path=self.owner.choose_path('Export evaluated complex data','CSV (*.csv)|*.csv',True)
        if path:
            with path.open('w',newline='',encoding='utf-8') as stream:
                writer=csv.writer(stream);writer.writerow(['frequency_hz',f'real [{unit}]',f'imaginary [{unit}]',f'magnitude [{unit}]','phase_deg'])
                writer.writerows(zip(engine.time,values.real,values.imag,abs(values),np.degrees(np.angle(values))))
