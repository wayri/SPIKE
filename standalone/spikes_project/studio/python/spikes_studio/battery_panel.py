# SPDX-License-Identifier: Apache-2.0
"""Explicit battery reference studies and evidence-aware market-cell browsing."""
from dataclasses import asdict
import csv
import json
from pathlib import Path
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from .flat_controls import ActionButton
from .resources import resource_dir
from .themes import apply_window, figure_theme
from .document import write_json
from .fuzzy_search import ranked


def parse_current_profile(path):
    path=Path(path)
    if path.stat().st_size>4*1024*1024:raise ValueError('Battery profile is limited to 4 MiB')
    with path.open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=['time_s','current_a']:raise ValueError('CSV headers must be time_s,current_a; positive current discharges')
        rows=list(reader)
    if not 2<=len(rows)<=10001:raise ValueError('Profile requires 2–10,001 rows')
    times=[float(row['time_s']) for row in rows];currents=[float(row['current_a']) for row in rows]
    import math
    if any(not math.isfinite(v) for v in times+currents) or times[0]<0 or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Profile times must be finite, nonnegative and strictly increasing; current must be finite')
    return times,currents[:-1]


class BatteryPanel(wx.Panel):
    def __init__(self,parent,owner):
        super().__init__(parent);self.owner=owner;self.result=None;self.profile=None
        from python.spikes.battery import CHEMISTRIES,generic_model
        self.chemistry_ids=list(CHEMISTRIES)
        outer=wx.BoxSizer(wx.VERTICAL);self.SetSizer(outer)
        title=wx.StaticText(self,label='Battery reference laboratory')
        title.SetFont(wx.Font(13,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_BOLD))
        outer.Add(title,0,wx.ALL,10)
        notice=wx.StaticText(self,label='Prescribed-current, reduced-order study · NOT coupled to circuit MNA · unqualified cell/aging assumptions')
        notice.SetName('Battery model scope');outer.Add(notice,0,wx.LEFT|wx.RIGHT|wx.BOTTOM,10)
        row=wx.WrapSizer(wx.HORIZONTAL)
        self.chemistry=wx.Choice(self,choices=list(CHEMISTRIES.values()),size=(290,-1));self.chemistry.SetSelection(self.chemistry_ids.index('custom'))
        self.chemistry.SetToolTip('Chemistry label is not a validated parameter set. Review OCV, impedance, thermal and aging evidence.')
        row.Add(self.chemistry,0,wx.ALL,4)
        self.chemistry.Bind(wx.EVT_CHOICE,self.reset_template)
        for label,handler in [('Run study',self.run),('Load current CSV',self.load_profile),('Constant current',self.clear_profile),('Import model',self.import_model),('Export model',self.export_model),('Export results',self.export_results)]:
            button=ActionButton(self,label=label);button.Bind(wx.EVT_BUTTON,lambda event,action=handler:owner.guarded(action));row.Add(button,0,wx.ALL,3)
        outer.Add(row,0,wx.EXPAND)
        body=wx.BoxSizer(wx.HORIZONTAL);outer.Add(body,1,wx.EXPAND)
        side=wx.ScrolledWindow(self,style=wx.VSCROLL);side.SetScrollRate(0,15);side.SetMinSize((340,-1));form=wx.BoxSizer(wx.VERTICAL);side.SetSizer(form)
        self.fields={}
        for key,label,value in [('soc','Initial state of charge [0–1]','1'),('temperature_k','Initial temperature [K]','298.15'),('ambient_k','Ambient temperature [K]','298.15'),('duration_s','Duration [s]','3600'),('current_a','Discharge current [A]; negative = charge','0.25'),('max_step_s','Maximum internal step [s]','10')]:
            form.Add(wx.StaticText(side,label=label),0,wx.LEFT|wx.TOP,8)
            field=wx.TextCtrl(side,value=value);field.SetName(label);self.fields[key]=field;form.Add(field,0,wx.EXPAND|wx.ALL,8)
        form.Add(wx.StaticText(side,label='Cell model parameters (SI; capacity in Ah)'),0,wx.ALL,8)
        self.model=wx.TextCtrl(side,value=json.dumps(asdict(generic_model()),indent=2),style=wx.TE_MULTILINE,size=(-1,320));self.model.SetName('Battery equations and parameters')
        form.Add(self.model,1,wx.EXPAND|wx.ALL,8)
        form.Add(wx.StaticText(side,label='Editable OCV/SOC table, RC polarization, thermal network, charge efficiency, self-discharge and empirical aging. Defaults are synthetic, not manufacturer fits.'),0,wx.EXPAND|wx.ALL,8)
        body.Add(side,0,wx.EXPAND)
        self.figure=Figure(figsize=(8,6),layout='constrained');self.plot=FigureCanvasWxAgg(self,-1,self.figure);self.plot.SetMinSize((100,100));body.Add(self.plot,1,wx.EXPAND)
        self.status=wx.StaticText(self,label='No battery study acquired. Model input is editable JSON, not executable code.');outer.Add(self.status,0,wx.EXPAND|wx.ALL,8)
        self.market=wx.CollapsiblePane(self,label='Market cells — source metadata, not qualified models',style=wx.CP_DEFAULT_STYLE|wx.CP_NO_TLW_RESIZE);outer.Add(self.market,0,wx.EXPAND|wx.ALL,8)
        content=self.market.GetPane();market_box=wx.BoxSizer(wx.HORIZONTAL);content.SetSizer(market_box)
        self.search=wx.SearchCtrl(content,size=(180,-1));self.search.SetDescriptiveText('Find a market cell');self.search.SetToolTip('Search manufacturer, part number, chemistry or cell size');market_box.Add(self.search,0,wx.ALIGN_TOP|wx.ALL,4)
        from .symbol_text_list import SymbolTextList
        self.parts=SymbolTextList(content,owner.palette,resolver=lambda index,text:'battery',size=(280,110));market_box.Add(self.parts,0,wx.EXPAND|wx.ALL,4)
        self.evidence=wx.TextCtrl(content,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,110));market_box.Add(self.evidence,1,wx.EXPAND|wx.ALL,4)
        path=resource_dir('library')/'battery-market-catalog.json'
        self.records=json.loads(path.read_text(encoding='utf-8'))['records'] if path.is_file() else []
        self.search.Bind(wx.EVT_TEXT,self.filter_parts);self.parts.Bind(wx.EVT_LISTBOX,self.select_part)
        self.market.Bind(wx.EVT_COLLAPSIBLEPANE_CHANGED,lambda event:self.Layout())
        self.bound_document=None;self.filter_parts();self.restore();self.draw()
        self.Bind(wx.EVT_SIZE,self.resized)

    def resized(self,event):
        event.Skip()
        wx.CallAfter(self.redraw_if_alive)

    def redraw_if_alive(self):
        if self and not self.IsBeingDeleted() and self.result:self.draw()

    def restore(self):
        if self.bound_document==self.owner.doc.data['id']:return
        self.bound_document=self.owner.doc.data['id'];self.profile=None;self.result=None
        saved=self.owner.doc.data['metadata'].get('battery_study')
        if saved:
            from python.spikes.battery import BatteryModel
            model=BatteryModel(**saved['model'])
            self.model.ChangeValue(json.dumps(asdict(model),indent=2));self.chemistry.SetSelection(self.chemistry_ids.index(model.chemistry))
            for key,value in saved['inputs'].items():
                if key in self.fields:self.fields[key].ChangeValue(str(value))
            self.profile=saved.get('profile')
        else:self.reset_template()
        self.draw()

    def reset_template(self,event=None):
        from python.spikes.battery import generic_model
        self.model.SetValue(json.dumps(asdict(generic_model(self.chemistry_ids[self.chemistry.GetSelection()])),indent=2))
        self.status.SetLabel('Synthetic template loaded. Review all coefficients; chemistry selection supplies no measured curves.')

    def filter_parts(self,event=None):
        self.filtered=ranked(self.records,self.search.GetValue(),text=lambda r:json.dumps(r))
        self.parts.Set([r['manufacturer']+' '+r['mpn'] for r in self.filtered])

    def select_part(self,event=None):
        index=self.parts.GetSelection()
        if index>=0:self.evidence.SetValue(json.dumps(self.filtered[index],indent=2))

    def configuration(self):
        from python.spikes.battery import BatteryModel,BatteryState
        value=json.loads(self.model.GetValue());model=BatteryModel(**value)
        inputs={key:float(field.GetValue()) for key,field in self.fields.items()}
        state=BatteryState(soc=inputs['soc'],temperature_k=inputs['temperature_k'])
        return model,state,inputs

    def run(self):
        if self.owner.job_running:raise ValueError('A simulation or study is already running')
        from python.spikes.battery import simulate
        model,state,inputs=self.configuration()
        if self.profile:times,currents=self.profile
        else:
            import math
            duration=inputs['duration_s']
            if not math.isfinite(duration) or not 0<duration<=1e9:raise ValueError('Duration must be finite, positive and <= 1e9 s')
            times=[duration*i/1000 for i in range(1001)];currents=inputs['current_a']
        configuration=json.loads(json.dumps(dict(model=asdict(model),initial_state=asdict(state),inputs=inputs,profile=self.profile)))
        self.owner.doc.commit(lambda data:data['metadata'].__setitem__('battery_study',configuration))
        self.owner.update_title()
        self.owner.background(lambda:simulate(model,times,currents,inputs['ambient_k'],state,max_step_s=inputs['max_step_s']),self.accept,'Running unqualified battery reference study…')

    def accept(self,result):
        self.result=result;self.draw()
        self.status.SetLabel(f"{len(result['samples']):,} samples · {result['model_status']} · prescribed current, no circuit coupling")

    def draw(self):
        self.figure.clear()
        if not self.result:
            ax=self.figure.add_subplot();ax.set_axis_off();ax.text(.5,.5,'Configure a cell and run a reference study',ha='center',va='center',transform=ax.transAxes)
        else:
            samples=self.result['samples'];time=[s['time_s']/3600 for s in samples]
            compact=self.plot.GetClientSize().height<440
            for index,(key,label) in enumerate((('voltage_v','Voltage [V]'),('soc','SOC [–]'),('temperature_k','Temperature [K]'),('capacity_soh','Capacity SOH [–]'))):
                ax=self.figure.add_subplot(2,2,index+1) if compact else self.figure.add_subplot(4,1,index+1)
                ax.plot(time,[s[key] for s in samples],label=label,linewidth=1.3);ax.set_title(label,loc='left',fontsize=9,pad=5);ax.grid(True,alpha=.25)
                from matplotlib.ticker import MaxNLocator
                ax.xaxis.set_major_locator(MaxNLocator(3 if compact else 7));ax.yaxis.set_major_locator(MaxNLocator(3))
                ax.ticklabel_format(axis='y',style='plain',useOffset=False)
                if index==3 or compact and index==2:ax.set_xlabel('Elapsed time [h]',fontsize=9)
        figure_theme(self.figure,self.owner.palette,self.owner.theme_name);self.plot.draw_idle()

    def load_profile(self):
        path=self.owner.choose_path('Load battery current profile','CSV (*.csv)|*.csv')
        if path:self.profile=parse_current_profile(path);self.status.SetLabel('Zero-order-held CSV current profile loaded; final row supplies the stop time.')
    def clear_profile(self):self.profile=None;self.status.SetLabel('Constant-current input selected.')
    def import_model(self):
        path=self.owner.choose_path('Import battery parameter model','JSON (*.json)|*.json')
        if path:
            from python.spikes.battery import BatteryModel
            if path.stat().st_size>1024*1024:raise ValueError('Model limited to 1 MiB')
            model=BatteryModel(**json.loads(path.read_text(encoding='utf-8')))
            self.model.SetValue(json.dumps(asdict(model),indent=2));self.chemistry.SetSelection(self.chemistry_ids.index(model.chemistry))
    def export_model(self):
        model,_,_=self.configuration();path=self.owner.choose_path('Export unqualified cell parameters','JSON (*.json)|*.json',True)
        if path:write_json(path,asdict(model))
    def export_results(self):
        if self.result is None:raise ValueError('Run a battery study first')
        path=self.owner.choose_path('Export battery reference result','JSON (*.json)|*.json',True)
        if path:write_json(path,self.result)
