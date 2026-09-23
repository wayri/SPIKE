"""Project thermal setup and a native-workbench run manager."""
from copy import deepcopy
import json
import wx
import wx.grid
from .document import write_json
from .simulation_setup import validate_profile


def button(parent,label,action,box):
    control=wx.Button(parent,label=label)
    control.Bind(wx.EVT_BUTTON,lambda e:action());box.Add(control,0,wx.ALL,4)
    return control


class ThermalSetup(wx.Dialog):
    def __init__(self,owner):
        super().__init__(owner,title='Project setup — board, enclosure & thermal environment',size=(850,720),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.SetMinSize((680,570));self.owner=owner;self.value=deepcopy(owner.doc.data['thermal_setup']);self.fields={}
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(self,label='Project assumptions only: this electrical runner does not derive temperatures or convection from board/enclosure geometry. Ambient is separate from electrical .TEMP.')
        note.Wrap(790);box.Add(note,0,wx.EXPAND|wx.ALL,12)
        self.error=wx.InfoBar(self);box.Add(self.error,0,wx.EXPAND)
        self.book=wx.Notebook(self);box.Add(self.book,1,wx.EXPAND|wx.ALL,8)
        groups=[('Board & stackup',[
            ('board.length_mm','Board length [mm]',None),('board.width_mm','Board width [mm]',None),
            ('board.thickness_mm','Total board thickness [mm]',None),('board.material','Dielectric / base-board material','text'),
            ('board.orientation','Orientation',('horizontal','vertical'))]),
            ('Enclosure',[(f'enclosure.{key}',label,kind) for key,label,kind in [
                ('type','Enclosure type',('open_air','ventilated','sealed')),('material','Material','text'),
                ('length_mm','Outer length [mm]',None),('width_mm','Outer width [mm]',None),
                ('height_mm','Outer height [mm]',None),('wall_mm','Wall thickness [mm]',None),('vent_area_mm2','Total vent area [mm²]',None)]]),
            ('Environment',[(f'environment.{key}',label,kind) for key,label,kind in [
                ('ambient_c','Ambient temperature [°C]',None),('airflow','Airflow mode',('still','natural','forced')),
                ('air_speed_m_s','Imposed air speed [m/s]; zero for natural/still',None),
                ('direction','Flow direction',('parallel_to_board','normal_to_board','unspecified')),
                ('convection_w_m2k','Known convection coefficient [W/(m²·K)]; blank = unknown','optional'),
                ('altitude_m','Altitude [m]',None)]])]
        for title,specs in groups:
            panel=wx.ScrolledWindow(self.book);panel.SetScrollRate(0,12);layout=wx.BoxSizer(wx.VERTICAL)
            grid=wx.FlexGridSizer(cols=2,hgap=12,vgap=10);grid.AddGrowableCol(1,1)
            for path,label,kind in specs:
                group,key=path.split('.');value=self.value[group][key]
                grid.Add(wx.StaticText(panel,label=label),0,wx.ALIGN_CENTER_VERTICAL)
                if isinstance(kind,tuple):
                    control=wx.Choice(panel,choices=[v.replace('_',' ') for v in kind]);control.SetSelection(kind.index(value))
                else:control=wx.TextCtrl(panel,value='' if value is None else str(value))
                self.fields[path]=(control,kind);grid.Add(control,1,wx.EXPAND)
            layout.Add(grid,0,wx.EXPAND|wx.ALL,10)
            if title=='Board & stackup':
                row=wx.BoxSizer(wx.HORIZONTAL);row.Add(wx.StaticText(panel,label='Number of copper layers'),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,6)
                self.layer_count=wx.SpinCtrl(panel,min=1,max=64,initial=len(self.value['board']['layers']));row.Add(self.layer_count,0,wx.ALL,4);layout.Add(row)
                self.layers=wx.grid.Grid(panel);self.layers.CreateGrid(0,3)
                for i,label in enumerate(('Layer name','Copper thickness [µm]','Copper coverage [%]')):self.layers.SetColLabelValue(i,label)
                for layer in self.value['board']['layers']:
                    self.layers.AppendRows();i=self.layers.GetNumberRows()-1
                    for col,key in enumerate(('name','copper_um','coverage_pct')):self.layers.SetCellValue(i,col,str(layer[key]))
                for col in range(3):self.layers.SetColSize(col,220)
                self.layers.SetMinSize((-1,210));layout.Add(self.layers,0,wx.EXPAND|wx.ALL,10)
                self.layer_count.Bind(wx.EVT_SPINCTRL,lambda e:self.resize_layers())
                layout.Add(wx.StaticText(panel,label='Values are explicit authoring assumptions, not extracted KiCad stackup data.'),0,wx.ALL,10)
            if title=='Enclosure':layout.Add(wx.StaticText(panel,label='Dimensions are retained for future models; they are not used for an open-air setup.'),0,wx.ALL,10)
            if title=='Environment':
                layout.Add(wx.StaticText(panel,label='Boundary conditions / mounting / heatsink notes'),0,wx.ALL,10)
                self.notes=wx.TextCtrl(panel,value=self.value['notes'],style=wx.TE_MULTILINE,size=(-1,120));layout.Add(self.notes,0,wx.EXPAND|wx.ALL,10)
            panel.SetSizer(layout);self.book.AddPage(panel,title)
        actions=wx.BoxSizer(wx.HORIZONTAL)
        button(self,'Cancel',lambda:self.EndModal(wx.ID_CANCEL),actions)
        button(self,'Apply project setup',self.apply,actions)
        box.Add(actions,0,wx.ALIGN_RIGHT|wx.ALL,8);self.SetSizer(box)
        from .themes import apply_window
        apply_window(self,owner.palette)

    def resize_layers(self):
        self.layers.SaveEditControlValue()
        count=self.layer_count.GetValue();current=self.layers.GetNumberRows()
        if count<current:self.layers.DeleteRows(count,current-count)
        elif count>current:
            self.layers.AppendRows(count-current)
            for i in range(current,count):
                for col,value in enumerate((f'L{i+1}','35','50')):self.layers.SetCellValue(i,col,value)

    def apply(self):
        try:
            value=deepcopy(self.value)
            for path,(control,kind) in self.fields.items():
                group,key=path.split('.')
                if isinstance(kind,tuple):item=kind[control.GetSelection()]
                else:
                    text=control.GetValue().strip()
                    item=text if kind=='text' else None if kind=='optional' and not text else float(text)
                value[group][key]=item
            self.resize_layers();self.layers.SaveEditControlValue()
            value['board']['layers']=[{'name':self.layers.GetCellValue(i,0).strip(),
                                      'copper_um':float(self.layers.GetCellValue(i,1)),
                                      'coverage_pct':float(self.layers.GetCellValue(i,2))} for i in range(self.layers.GetNumberRows())]
            value['notes']=self.notes.GetValue()
            self.owner.doc.update_setup('thermal_setup',value)
            self.owner.refresh_document();self.EndModal(wx.ID_OK)
        except Exception as exc:self.error.ShowMessage(str(exc),wx.ICON_ERROR);self.Layout()


class SimulationManager(wx.ScrolledWindow):
    def __init__(self,owner,parent):
        super().__init__(parent);self.SetScrollRate(0,12);self.owner=owner;self.fields={};self.record_ids=[];self.loaded=None
        box=wx.BoxSizer(wx.VERTICAL)
        heading=wx.StaticText(self,label='Simulation manager — one active simulation; bounded metadata history of the last 50 runs')
        box.Add(heading,0,wx.ALL,10)
        config=wx.FlexGridSizer(cols=4,hgap=10,vgap=7);config.AddGrowableCol(1,1);config.AddGrowableCol(3,1)
        specs=[('name','Profile name',None),('execution','Execution',('batch','continuous')),
               ('analysis','Analysis override',('from_netlist','transient','operating_point')),
               ('method','Integration',('hybrid_trapezoidal','backward_euler','bdf2')),
               ('time_step','Override timestep [s]',None),('stop_time','Override stop time [s]',None),
               ('capture_samples','Continuous capture samples',None),('speed_ratio','Simulated seconds / wall second',None),
               ('electrical_temperature_c','Electrical .TEMP [°C]; blank = deck',None),('uic','Override initial conditions','bool')]
        for key,label,kind in specs:
            config.Add(wx.StaticText(self,label=label),0,wx.ALIGN_CENTER_VERTICAL)
            if isinstance(kind,tuple):control=wx.Choice(self,choices=[v.replace('_',' ') for v in kind])
            elif kind=='bool':control=wx.CheckBox(self,label='Use UIC')
            else:control=wx.TextCtrl(self)
            self.fields[key]=(control,kind);config.Add(control,1,wx.EXPAND)
        box.Add(config,0,wx.EXPAND|wx.ALL,10)
        note=wx.StaticText(self,label='Timestep, stop and UIC override only when Transient is selected. Continuous ignores TSTOP and keeps a rolling window. Profile overrides do not rewrite the circuit editor. Ambient setup does not set .TEMP.')
        note.Wrap(800);box.Add(note,0,wx.EXPAND|wx.ALL,8)
        self.thermal_summary=wx.StaticText(self,label='');box.Add(self.thermal_summary,0,wx.EXPAND|wx.ALL,8)
        row=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE)
        button(self,'Board / thermal setup…',owner.thermal_setup,row)
        button(self,'Apply profile',lambda:owner.guarded(self.apply_profile),row)
        button(self,'Load profile…',lambda:owner.guarded(self.load_profile),row)
        button(self,'Export profile…',lambda:owner.guarded(self.export_profile),row)
        self.run_button=button(self,'Run profile',lambda:owner.guarded(self.run_profile),row)
        self.pause_button=button(self,'Pause / Resume',lambda:owner.guarded(owner.pause_run),row)
        self.stop_button=button(self,'Stop',owner.stop_run,row)
        box.Add(row,0,wx.EXPAND|wx.ALL,4)
        self.runs=wx.ListCtrl(self,style=wx.LC_REPORT|wx.LC_SINGLE_SEL,size=(-1,185))
        for i,(label,width) in enumerate((('Started UTC',150),('Profile',145),('State',90),('Mode / method',195),('Wall [s]',80),('Samples',85))):self.runs.InsertColumn(i,label,width=width)
        self.runs.Bind(wx.EVT_LIST_ITEM_SELECTED,lambda e:self.show_record());box.Add(self.runs,0,wx.EXPAND|wx.ALL,8)
        self.details=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,150));box.Add(self.details,0,wx.EXPAND|wx.ALL,8)
        row=wx.BoxSizer(wx.HORIZONTAL)
        button(self,'Export selected run report…',lambda:owner.guarded(self.export_record),row)
        button(self,'Plot latest capture',lambda:owner.book.SetSelection(1),row)
        button(self,'Export latest capture…',lambda:owner.guarded(owner.save_data),row)
        box.Add(row,0,wx.EXPAND|wx.ALL,4)
        footer=wx.StaticText(self,label='History is session-local metadata; export reports to retain it. Latest capture / bounded step collection is kept in memory; waveform export saves the selected run. Thermal setup is recorded but not coupled to the solver.')
        footer.Wrap(800);box.Add(footer,0,wx.ALL,8)
        self.SetSizer(box);self.reflect_document()

    def set_fields(self,profile):
        for key,(control,kind) in self.fields.items():
            value=profile[key]
            if isinstance(kind,tuple):control.SetSelection(kind.index(value))
            else:control.SetValue(value if kind=='bool' else '' if value is None else str(value))

    def reflect_document(self):
        doc=self.owner.doc.data;identity=(doc['id'],json.dumps(doc['run_profile'],sort_keys=True))
        if self.loaded!=identity:self.set_fields(doc['run_profile']);self.loaded=identity
        t=doc['thermal_setup'];b=t['board'];e=t['environment']
        self.thermal_summary.SetLabel(f"Board {b['length_mm']:g} × {b['width_mm']:g} × {b['thickness_mm']:g} mm · {len(b['layers'])} copper layers · {t['enclosure']['type']} · ambient {e['ambient_c']:g} °C · {e['airflow']} airflow (not solver-coupled)")
        self.FitInside()

    def profile(self):
        profile=deepcopy(self.owner.doc.data['run_profile'])
        for key,(control,kind) in self.fields.items():
            value=kind[control.GetSelection()] if isinstance(kind,tuple) else control.GetValue()
            if key=='capture_samples':value=int(value)
            elif key=='speed_ratio':value=float(value)
            elif key=='electrical_temperature_c':value=float(value) if value.strip() else None
            profile[key]=value
        validate_profile(profile);return profile

    def apply_profile(self):
        profile=self.profile()
        if profile!=self.owner.doc.data['run_profile']:self.owner.doc.update_setup('run_profile',profile)
        self.owner.refresh_document();return profile

    def run_profile(self):
        if self.owner.job_running:raise ValueError('Wait for or stop the active job first')
        profile=self.apply_profile()
        if profile['execution']=='continuous':self.owner.start_interactive()
        else:self.owner.run()

    def load_profile(self):
        path=self.owner.choose_path('Load run profile','Run profile (*.spkrun)|*.spkrun|JSON|*.json')
        if path:
            if path.stat().st_size>65536:raise ValueError('Profile exceeds 64 KiB')
            profile=json.loads(path.read_text(encoding='utf-8'));validate_profile(profile);self.set_fields(profile)

    def export_profile(self):
        profile=self.profile();path=self.owner.choose_path('Export run profile','Run profile (*.spkrun)|*.spkrun',True)
        if path:write_json(path,profile)

    def selected_id(self):
        index=self.runs.GetFirstSelected()
        return self.record_ids[index] if 0<=index<len(self.record_ids) else None

    def refresh_runs(self):
        selected=self.selected_id();records=list(reversed(self.owner.run_history.records));self.runs.Freeze()
        self.runs.DeleteAllItems();self.record_ids=[]
        for record in records:
            self.record_ids.append(record['id']);i=self.runs.InsertItem(self.runs.GetItemCount(),record['started_utc'][11:23])
            mode='frequency / Python-SciPy' if 'frequency_setup' in record else record['profile']['execution']+' / '+record['profile']['method']
            for col,text in enumerate((record['profile']['name'],record['state'],mode,f"{record['wall_seconds']:.3f}",str(record['samples'])),1):self.runs.SetItem(i,col,text)
            if record['id']==selected:self.runs.Select(i)
        if selected not in self.record_ids and records:self.runs.Select(0)
        self.runs.Thaw();self.show_record()

    def show_record(self):
        record=self.owner.run_history.get(self.selected_id())
        self.details.SetValue(json.dumps(record,indent=2) if record else 'Start a run to record its settings, status and thermal assumptions.')

    def export_record(self):
        record=self.owner.run_history.get(self.selected_id())
        if not record:raise ValueError('Select a run first')
        path=self.owner.choose_path('Export run report','JSON run report|*.json',True)
        if path:write_json(path,record)

    def update_controls(self):
        from .run_control import InteractiveRun
        run=self.owner.active_run
        self.run_button.Enable(not self.owner.job_running)
        self.pause_button.Enable(isinstance(run,InteractiveRun) and run.state in ('running','paused'))
        self.stop_button.Enable(run is not None)
