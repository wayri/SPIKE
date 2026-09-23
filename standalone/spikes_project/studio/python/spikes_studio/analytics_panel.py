"""Integrated measurement reports, spectra and user-loadable safe expression recipes."""
import json
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg,NavigationToolbar2WxAgg
from .analytics import statistics,spectrum,load_extension,evaluate_extension,EXTENSION_CONTRACT
from .document import write_json
from .themes import figure_theme

class AnalyticsPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.last_report=None
        box=wx.BoxSizer(wx.VERTICAL);row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS&~wx.EXTEND_LAST_ON_EACH_LINE)
        self.expression=wx.TextCtrl(self,value='V(out)',size=(280,-1));row.Add(self.expression,1,wx.ALL,4)
        def button(label,fn):
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(fn));row.Add(b,0,wx.ALL,4)
        button('Statistics',self.stats);button('Amplitude spectrum',lambda:self.fft(False));button('PSD',lambda:self.fft(True))
        button('Thermal margins',self.thermal)
        self.resample=wx.CheckBox(self,label='Allow explicit linear resampling');row.Add(self.resample,0,wx.ALL,7)
        box.Add(row,0,wx.EXPAND)
        self.figure=Figure(figsize=(8,4));self.plot=FigureCanvasWxAgg(self,-1,self.figure);self.toolbar=NavigationToolbar2WxAgg(self.plot)
        box.Add(self.toolbar,0,wx.EXPAND);box.Add(self.plot,1,wx.EXPAND)
        self.report=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,155));box.Add(self.report,0,wx.EXPAND|wx.ALL,6)
        row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS&~wx.EXTEND_LAST_ON_EACH_LINE)
        self.extensions=wx.Choice(self,size=(240,-1));row.Add(self.extensions,0,wx.ALL,4)
        button('Load analytics extension…',self.load);button('Run selected extension',self.run_extension);button('Remove selected',self.remove)
        button('Export extension template…',self.template);button('Export report…',self.export);box.Add(row,0,wx.EXPAND)
        note=wx.StaticText(self,label='Analytics uses actual recorded time-domain results. User extensions are bounded expression recipes (x = selected signal), not executable Python/C code. Importing never runs a recipe.');note.Wrap(1000);box.Add(note,0,wx.ALL,7)
        self.SetSizer(box);ax=self.figure.add_subplot();ax.set_title('Run a circuit, then analyze its recorded signals');self.plot.draw()
    def refresh(self):
        selected=self.extensions.GetStringSelection();self.extensions.Set([e['name'] for e in self.owner.doc.data['analytics_extensions']])
        if not self.extensions.SetStringSelection(selected) and self.extensions.GetCount():self.extensions.SetSelection(0)
    def engine(self):
        if self.owner.math is None:raise ValueError('Run a transient circuit or open a recorded .spkdata capture first')
        return self.owner.math
    def stats(self):
        self.last_report=statistics(self.engine(),self.expression.GetValue())
        self.last_report['run_provenance']=self.owner.result.get('provenance',{}) if self.owner.result else {}
        self.report.SetValue(json.dumps(self.last_report,indent=2))

    def thermal(self):
        from .thermal_report import report
        if not self.owner.result:raise ValueError('Run a circuit first to associate the report with its captured configuration')
        snapshot=getattr(self.owner,'collection_snapshot',None)
        if snapshot is None:raise ValueError('No captured component configuration; run this circuit before thermal assessment')
        self.last_report=report(snapshot,self.owner.result);self.report.SetValue(json.dumps(self.last_report,indent=2))
    def fft(self,psd):
        data=spectrum(self.engine(),self.expression.GetValue(),self.resample.GetValue());self.figure.clear();ax=self.figure.add_subplot()
        ax.plot(data['frequency_hz'],data['psd' if psd else 'amplitude'],label=self.expression.GetValue());ax.set_xlabel('Frequency [Hz]')
        ax.set_ylabel(f"PSD [{data['unit']}²/Hz]" if psd else f"Amplitude [{data['unit']}]");ax.set_title('Hann-windowed single-record '+('PSD' if psd else 'amplitude spectrum'));ax.grid(alpha=.4)
        figure_theme(self.figure,self.owner.palette,self.owner.theme_name);self.plot.draw()
        self.last_report={k:v for k,v in data.items() if k not in ('frequency_hz','psd','amplitude')};self.report.SetValue(json.dumps(self.last_report,indent=2))
    def load(self):
        path=self.owner.choose_path('Load declarative analytics extension','Analytics extension|*.spkanalytics;*.json')
        if path:
            extension=load_extension(path)
            def mutate(data):
                if any(e['id']==extension['id'] for e in data['analytics_extensions']):raise ValueError('An extension with this ID is already installed in the project; remove it first')
                data['analytics_extensions'].append(extension)
            self.owner.doc.commit(mutate);self.owner.refresh_document()
    def run_extension(self):
        index=self.extensions.GetSelection()
        if index<0:raise ValueError('Load and select an analytics extension')
        result=evaluate_extension(self.engine(),self.expression.GetValue(),self.owner.doc.data['analytics_extensions'][index])
        self.last_report={'extension':result['id'],'measurements':{name:{'value':float(q.values),'unit':str(q.unit)} for name,q in result['measurements'].items()}}
        self.report.SetValue(json.dumps(self.last_report,indent=2))
        if result['traces']:
            import numpy as np
            self.figure.clear();units=list(dict.fromkeys(str(q.unit) for q in result['traces'].values()))
            if len(units)>8:raise ValueError('An extension plot can use at most 8 different units')
            for i,unit in enumerate(units):
                ax=self.figure.add_subplot(len(units),1,i+1)
                for name,q in result['traces'].items():
                    if str(q.unit)==unit:
                        from .plotting import extrema_indices
                        values=np.broadcast_to(q.values,self.engine().time.shape);indices=extrema_indices(values)
                        ax.plot(self.engine().time[indices],values[indices],label=name)
                ax.set_xlabel('Time [s]');ax.set_ylabel(unit);ax.legend();ax.grid(alpha=.3)
            self.figure.set_layout_engine('constrained');figure_theme(self.figure,self.owner.palette,self.owner.theme_name);self.plot.draw()
    def remove(self):
        index=self.extensions.GetSelection()
        if index<0:raise ValueError('Select an extension')
        self.owner.doc.commit(lambda d:d['analytics_extensions'].pop(index));self.owner.refresh_document()
    def template(self):
        path=self.owner.choose_path('Export editable expression extension','Analytics extension|*.spkanalytics',True)
        if path:write_json(path,{'contract':EXTENSION_CONTRACT,'id':'user.ripple','name':'Ripple and AC component',
            'measurements':[{'name':'ripple','expression':'pp(x)'},{'name':'rms','expression':'rms(x)'}],
            'traces':[{'name':'AC component','expression':'x-mean(x)'}]})
    def export(self):
        if self.last_report is None:raise ValueError('Calculate an analytics report first')
        path=self.owner.choose_path('Export analytics report','JSON|*.json',True)
        if path:write_json(path,self.last_report)
