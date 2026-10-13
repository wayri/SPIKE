"""Virtualized interactive library browser; previews never imply solver support."""
from copy import deepcopy
import json
import time
import uuid
import wx
import wx.aui
import wx.adv
from .component_catalog import catalog,evaluate,native_recipe,validate_record,materialize
from .document import write_json
from .library_browser import CatalogIndex,SORTS,insertion_plan,apply_insertion
from .themes import apply_window
from .manufacturer_registry import capability_summary,source_report
from .library_pins import pin_contract,preview_height


def context_row(position,default_position,row_count,selected,screen_to_client,hit_test):
    """Resolve pointer context to its row; preserve focus for keyboard invocation."""
    if position==default_position:return selected
    row,_flags=hit_test(screen_to_client(position))
    return row if 0<=row<row_count else -1


class ResultsList(wx.ListCtrl):
    def __init__(self,parent):
        super().__init__(parent,style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL)
        self.browser=parent;self.rows=[]
        self.refresh_symbols(parent.owner.palette)
        for i,(label,width) in enumerate([('Preset',245),('Family',120),('Value',95),('Unit',65),('Execution',105)]):self.InsertColumn(i,label,width=width)
    def OnGetItemText(self,item,column):
        if not 0<=item<len(self.rows):return ''
        r=self.rows[item]
        return [('* ' if r['id'] in self.browser.preferences().get('favorites',[]) else '')+r['name'],r['family'],f"{self.browser.index.values[r['id']]:.7g}",r['parameter_unit'],'Native' if r['status']=='native_subcircuit' else 'Bench only'][column]
    def refresh_symbols(self,palette):
        from .symbol_icons import SymbolImages
        self.images=SymbolImages(None,palette);self.AssignImageList(self.images.image_list,wx.IMAGE_LIST_SMALL);self.Refresh()
    def OnGetItemImage(self,item):return self.images.index(self.rows[item]['family']) if 0<=item<len(self.rows) else -1
    def OnGetItemColumnImage(self,item,column):return self.OnGetItemImage(item) if column==0 else -1
    def set_rows(self,rows):
        self.SetSelection(-1);self.rows=rows;self.SetItemCount(len(rows));self.Refresh()
    def GetSelection(self):return self.GetFirstSelected()
    def SetSelection(self,index):
        old=self.GetFirstSelected()
        if old>=0:self.SetItemState(old,0,wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED)
        if 0<=index<len(self.rows):self.SetItemState(index,wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED,wx.LIST_STATE_SELECTED|wx.LIST_STATE_FOCUSED);self.EnsureVisible(index)


class SymbolPreview(wx.Panel):
    def __init__(self,parent,browser):
        super().__init__(parent,size=(-1,210));self.browser=browser;self.SetBackgroundStyle(wx.BG_STYLE_PAINT);self.Bind(wx.EVT_PAINT,self.paint)
    def paint(self,event):
        dc=wx.AutoBufferedPaintDC(self);p=self.browser.owner.palette;dc.SetBackground(wx.Brush(p['canvas']));dc.Clear()
        record=self.browser.record;dc.SetTextForeground(p['fg'])
        if not record:dc.DrawText('Select a preset to preview its symbol',12,18);return
        family=record['family'];native=record['status']=='native_subcircuit';w,h=self.GetClientSize();x,y=w//2,105
        contract=pin_contract(record)
        if contract:
            dc.SetPen(wx.Pen(p['fg'],2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
            left=max(70,x-110);right=left+220;top=52;bottom=h-48
            dc.DrawRectangle(left,top,right-left,bottom-top)
            dc.DrawText(family.replace('_',' ').upper(),left+8,top+6)
            for side in ('west','east'):
                pins=[pin for pin in contract['pins'] if pin['side']==side]
                for i,pin in enumerate(pins):
                    yy=top+40+i*28;edge=left if side=='west' else right;end=edge+(-28 if side=='west' else 28)
                    dc.SetPen(wx.Pen(p['accent'] if pin['role']=='power' else p['fg'],2))
                    dc.DrawLine(edge,yy,end,yy);dc.DrawCircle(end,yy,3)
                    label=pin['name'];width=dc.GetTextExtent(label).width
                    dc.DrawText(label,left+8 if side=='west' else right-width-8,yy-8)
                    dc.DrawText(pin['number'],end-18 if side=='west' else end+5,yy-8)
            dc.SetTextForeground(p['muted']);dc.DrawText('Generic logical pins · NOT a manufacturer pinout',10,12)
            dc.DrawText('Interface preview only · not connected to circuit MNA',10,h-25)
            return
        dc.SetPen(wx.Pen(p['fg'],2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
        def line(a,b,c,d):dc.DrawLine(x+a,y+b,x+c,y+d)
        pins=native_recipe(record)['pins'] if native else ['INPUT','OUTPUT']
        if family in ('capacitor','supercapacitor'):
            line(-72,0,-8,0);line(8,0,72,0);line(-8,-25,-8,25);line(8,-25,8,25)
        elif family=='inductor':
            line(-72,0,-36,0);line(36,0,72,0)
            for left in (-36,-12,12):dc.DrawEllipticArc(x+left,y-12,24,24,0,180)
        elif family in ('diode','led'):
            line(-72,0,-23,0);line(23,0,72,0);dc.DrawLines([wx.Point(x-23,y-22),wx.Point(x-23,y+22),wx.Point(x+23,y),wx.Point(x-23,y-22)]);line(23,-22,23,22)
        elif family=='voltage_reference':
            line(-72,0,-28,0);line(28,0,72,0);dc.DrawCircle(x,y,28);dc.DrawText('+  −',x-20,y-9)
        else:
            line(-72,0,-35,0);line(35,0,72,0);dc.DrawRectangle(x-35,y-22,70,44)
            if family not in ('resistor','termination','cable'):dc.DrawText('BLOCK',x-25,y-8)
        dc.SetPen(wx.Pen(p['accent'],2));dc.SetBrush(wx.Brush(p['canvas']))
        for i,pin in enumerate(pins):
            at=(x-72,y) if i==0 else (x+72,y) if i==1 else (x,y+60)
            if i==2:dc.DrawLine(x,y+22,*at)
            dc.DrawCircle(*at,4);dc.DrawText(f'{i+1}: {pin}',at[0]-15,at[1]+10)
        dc.SetTextForeground(p['muted']);dc.DrawText('Native pin preview' if native else 'Equation block — not an electrical pinout',10,12)
        dc.DrawText('Conventional symbol · conformance unverified',10,max(185,h-22))


class InsertDialog(wx.Dialog):
    def __init__(self,browser,record):
        parent=browser.owner if isinstance(browser.owner,wx.Window) else browser
        super().__init__(parent,title='Add component',size=(620,540),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.SetMinSize((580,480))
        self.browser=browser;self.record=record;model=native_recipe(record);box=wx.BoxSizer(wx.VERTICAL)
        self.base_record=deepcopy(record);self.library_record=None
        box.Add(wx.StaticText(self,label=record['family'].replace('_',' ').title()),0,wx.ALL,12)
        self.book=wx.Notebook(self);box.Add(self.book,1,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        values=wx.ScrolledWindow(self.book);values.SetScrollRate(0,12);value_box=wx.BoxSizer(wx.VERTICAL);values.SetSizer(value_box)
        value_box.Add(wx.StaticText(values,label='Component / library model'),0,wx.LEFT|wx.RIGHT|wx.TOP,12)
        self.part_search=wx.SearchCtrl(values);self.part_search.SetDescriptiveText('Filter matching library parts by MPN or manufacturer');value_box.Add(self.part_search,0,wx.EXPAND|wx.ALL,8)
        self.part_choice=wx.adv.BitmapComboBox(values,style=wx.CB_READONLY);self.part_choice.SetName('Component library model');value_box.Add(self.part_choice,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        self.library_status=wx.StaticText(values,label='Custom generic model');value_box.Add(self.library_status,0,wx.EXPAND|wx.ALL,10)
        self.part_search.Bind(wx.EVT_TEXT,self.filter_library);self.part_choice.Bind(wx.EVT_COMBOBOX,self.select_library)
        fields=wx.FlexGridSizer(cols=2,hgap=12,vgap=12);fields.AddGrowableCol(1);self.parameter_fields={}
        labels={'r':'Resistance [Ω]','c':'Capacitance [F]','l':'Inductance [H]','is':'Saturation current [A]','voltage':'Voltage [V]','frequency':'Frequency [Hz]','delay':'Delay [s]','loss_db':'Attenuation [dB]',
                'series_resistance_ohm':'Series R / ESR / DCR [Ω]','series_inductance_h':'Series L / ESL [H]',
                'parallel_capacitance_f':'Parallel capacitance [F]','leakage_resistance_ohm':'Leakage R [Ω; 0 = omitted]',
                'contact_resistance_ohm':'Each force contact R [Ω]', 'tolerance_percent':'Tolerance [%]',
                'corner':'Tolerance corner [-1 to +1]','temperature_c':'Model temperature [°C]',
                'reference_temperature_c':'Reference temperature [°C]','tc1_per_k':'Linear TC [1/K]','tc2_per_k2':'Quadratic TC [1/K²]'}
        detailed=record.get('model_type')=='lumped_passive_rlc_v1'
        if detailed:
            from .passive_catalog import PACKAGES,CONSTRUCTIONS
            self.package_choice=wx.Choice(values,choices=list(PACKAGES));self.package_choice.SetStringSelection(record['package_code'])
            self.construction_choice=wx.Choice(values,choices=list(CONSTRUCTIONS[record['passive_kind']]));self.construction_choice.SetStringSelection(record['construction'])
            for label,control in [('Package (inch code)',self.package_choice),('Construction label',self.construction_choice)]:
                fields.Add(wx.StaticText(values,label=label),0,wx.ALIGN_CENTER_VERTICAL);fields.Add(control,1,wx.EXPAND)
            self.standard_series=wx.Choice(values,choices=['E3','E6','E12','E24','E48','E96','E192']);self.standard_series.SetStringSelection('E192' if record['family']=='resistor' else 'E24')
            fields.Add(wx.StaticText(values,label='Preferred-value series'),0,wx.ALIGN_CENTER_VERTICAL);fields.Add(self.standard_series,1,wx.EXPAND)
            model_page=wx.ScrolledWindow(self.book);model_page.SetScrollRate(0,12);model_box=wx.BoxSizer(wx.VERTICAL);model_page.SetSizer(model_box)
            model_box.Add(wx.StaticText(model_page,label='Explicit user coefficients; package size does not guess these.\nZero parasitics are omitted. Temperature is static, not self-heating.'),0,wx.ALL,10)
            model_fields=wx.FlexGridSizer(cols=2,hgap=12,vgap=10);model_fields.AddGrowableCol(1);model_box.Add(model_fields,0,wx.EXPAND|wx.ALL,10)
        for key,value in record['parameters'].items():
            main=not detailed or key in ('r','c','l','tolerance_percent')
            target=values if main else model_page;grid=fields if main else model_fields
            grid.Add(wx.StaticText(target,label=labels.get(key,key)),0,wx.ALIGN_CENTER_VERTICAL)
            control=wx.TextCtrl(target,value=f'{value:.12g}');control.SetName('Component parameter '+key);self.parameter_fields[key]=control;grid.Add(control,1,wx.EXPAND)
        fields.Add(wx.StaticText(values,label='Instances'),0,wx.ALIGN_CENTER_VERTICAL);self.count=wx.SpinCtrl(values,min=1,max=100,initial=1);fields.Add(self.count,0)
        value_box.Add(fields,0,wx.EXPAND|wx.ALL,12)
        hint=wx.StaticText(values,label='Engineering values accepted: 4.7k, 100n, 2.2u. SPICE M means milli; use MEG for mega.\nPins retain their standard order. Wire the component after placing it.')
        hint.Wrap(510);value_box.Add(hint,0,wx.ALL,12);self.book.AddPage(values,'Value & parameters',True)
        if detailed:
            def recommend(event):
                from .passive_catalog import nearest
                from python.spikes.netlist import parse_spice_number
                key=next(iter(self.base_record['parameters']))
                try:
                    answer=nearest(parse_spice_number(self.parameter_fields[key].GetValue(),{'r':'resistor','c':'capacitor','l':'inductor'}[key]),self.standard_series.GetStringSelection())
                    self.parameter_fields[key].SetValue(f"{answer['value']:.12g}");self.error.SetLabel(f"Selected {answer['series']} value; change {answer['relative_error_percent']:+.5g}%. No manufacturer availability implied.")
                except ValueError as error:self.error.SetLabel(str(error))
            control=wx.Button(values,label='Use nearest preferred value');control.Bind(wx.EVT_BUTTON,recommend);value_box.Add(control,0,wx.ALL,10)
            self.book.AddPage(model_page,'Parasitics & temperature')
        connections=wx.Panel(self.book);connection_box=wx.BoxSizer(wx.VERTICAL);connections.SetSizer(connection_box)
        grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=8);grid.AddGrowableCol(1);self.pins={}
        prefix='part_'+uuid.uuid4().hex[:8]+'_{n}_'
        for pin in model['pins']:
            grid.Add(wx.StaticText(connections,label=pin+' → net'),0,wx.ALIGN_CENTER_VERTICAL)
            control=wx.TextCtrl(connections,value=prefix+pin.lower());grid.Add(control,1,wx.EXPAND);self.pins[pin]=control
        connection_box.Add(grid,0,wx.EXPAND|wx.ALL,12)
        note=wx.StaticText(connections,label='Optional net mapping; this does not change the model pin order.\nDefaults isolate every pin and each instance. No pin is automatically grounded.\nUse {n} for per-instance nodes; names without {n} intentionally share a net. Ground is 0.');note.Wrap(510);connection_box.Add(note,0,wx.ALL,12);self.book.AddPage(connections,'Pins & connections')
        self.place=wx.CheckBox(self,label='Click on schematic to choose placement (Escape cancels)');self.place.SetValue(True);box.Add(self.place,0,wx.ALL,10)
        self.error=wx.StaticText(self,label='');box.Add(self.error,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        buttons=self.CreateButtonSizer(wx.OK|wx.CANCEL);self.FindWindow(wx.ID_OK).SetLabel('Place / insert')
        self.FindWindow(wx.ID_OK).Bind(wx.EVT_BUTTON,self.accept)
        box.Add(buttons,0,wx.ALIGN_RIGHT|wx.ALL,10);self.SetSizer(box);apply_window(self,browser.owner.palette)
        self.filter_library()
        values.FitInside()
        self.CentreOnParent()

    def filter_library(self,event=None):
        from .component_library_choices import matching_parts,label
        previous=self.library_record['id'] if self.library_record else None
        self.library_rows=[None,*matching_parts(self.base_record['family'],self.part_search.GetValue())]
        if self.base_record.get('passive_kind')=='kelvin_shunt':self.library_rows=[None,*[r for r in self.library_rows[1:] if len(r['pins'])==4]]
        from .symbol_icons import bitmap
        self.part_choice.Clear()
        for record in self.library_rows:
            key=record['category'] if record else self.base_record['family']
            self.part_choice.Append(label(record) if record else 'Custom / generic',bitmap(key,self.browser.owner.palette))
        self.part_choice.SetSelection(next((i for i,r in enumerate(self.library_rows) if r and r['id']==previous),0))
        self.select_library()

    def select_library(self,event=None):
        from .manufacturer_parts import as_component_record,is_placeable
        if self.library_record is None:self.custom_draft={key:control.GetValue() for key,control in self.parameter_fields.items()}
        self.library_record=self.library_rows[self.part_choice.GetSelection()]
        ready=self.library_record is None or is_placeable(self.library_record)
        if self.library_record is None:
            self.record=deepcopy(self.base_record);message='Editable generic model; not a qualified manufacturer part.'
        elif ready:
            self.record=as_component_record(self.library_record);self.record['_manufacturer_record']=deepcopy(self.library_record)
            message='Sourced nominal value · ideal approximation only. Select Custom / generic to enter arbitrary values.'
        else:message='No runnable model is installed for this part. Review its vendor model in the manufacturer library before placement.'
        for key,control in self.parameter_fields.items():
            unsupported=(self.base_record.get('passive_kind')=='kelvin_shunt' and key in ('series_resistance_ohm','series_inductance_h','parallel_capacitance_f','leakage_resistance_ohm')) or (self.base_record.get('model_type') and self.base_record.get('passive_kind')!='kelvin_shunt' and key=='contact_resistance_ohm')
            control.Enable(self.library_record is None and not unsupported)
            if unsupported:control.SetToolTip('Unsupported for this terminal/model type; retained at zero, not silently approximated')
            if self.library_record is None:control.ChangeValue(self.custom_draft[key])
            elif ready and key in self.record['parameters']:control.ChangeValue(f"{self.record['parameters'][key]:.12g}")
            elif not ready:control.ChangeValue('')
        self.library_status.SetLabel(message);self.library_status.Wrap(510);self.FindWindow(wx.ID_OK).Enable(ready);self.Layout()
        if hasattr(self,'package_choice'):
            self.package_choice.Enable(self.library_record is None);self.construction_choice.Enable(self.library_record is None)

    def accept(self,event=None):
        try:
            record=self.edited_record()
            insertion_plan(self.browser.owner.doc,record,{pin:control.GetValue() for pin,control in self.pins.items()},count=self.count.GetValue())
            self.EndModal(wx.ID_OK)
        except (ValueError,KeyError) as error:self.error.SetLabel(str(error));self.error.Wrap(510);self.Layout()

    def edited_record(self):
        from python.spikes.netlist import parse_spice_number
        if self.library_record is not None:
            from .manufacturer_parts import source_pins
            source_pins(self.library_record)
            return deepcopy(self.record)
        quantities={'r':'resistor','c':'capacitor','l':'inductor','is':'current_source','voltage':'voltage_source','frequency':'scalar','delay':'time',
                    'series_resistance_ohm':'resistor','leakage_resistance_ohm':'resistor','contact_resistance_ohm':'resistor',
                    'series_inductance_h':'inductor','parallel_capacitance_f':'capacitor'}
        record=deepcopy(self.record)
        record['parameters']={key:parse_spice_number(control.GetValue(),quantities.get(key,'scalar')) for key,control in self.parameter_fields.items()}
        primary=next(iter(record['parameters']));record['name']=record['family'].replace('_',' ').title()+f" · {record['parameters'][primary]:.7g} {record['parameter_unit']}"
        if hasattr(self,'package_choice'):
            record['package_code']=self.package_choice.GetStringSelection();record['construction']=self.construction_choice.GetStringSelection()
        validate_record(record);native_recipe(record);return record


class ComponentPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.catalog=catalog(include_passives=True);self.index=CatalogIndex(self.catalog['records']);self.visible=[];self.record=None;self.state={};self.drafts={};self.pending=None;self.family_filter=None;self.filtering=False
        box=wx.BoxSizer(wx.VERTICAL)
        self.pin_button=wx.Button(self,label='Pin browser to side');self.pin_button.Bind(wx.EVT_BUTTON,lambda e:owner.pin_browser());box.Add(self.pin_button,0,wx.ALL,3)
        counts=capability_summary(self.catalog['records'])
        self.summary=wx.StaticText(self,label=f"{counts['presets']:,} generic presets · {counts['archetypes']} archetypes · {counts['native']:,} circuit-ready / {counts['bench_only']:,} bench-only · {counts['manufacturer_qualified']} qualified manufacturer models");box.Add(self.summary,0,wx.ALL,6)
        quick=wx.WrapSizer(wx.HORIZONTAL);self.add_button(quick,'Circuit-ready parts',self.circuit_ready);self.add_button(quick,'Manufacturer library…',self.manufacturer_library);self.add_button(quick,'Manufacturer model sources…',self.manufacturer_sources);box.Add(quick,0,wx.EXPAND)
        row=wx.WrapSizer(wx.HORIZONTAL);self.search=wx.SearchCtrl(self,size=(280,-1));self.search.SetDescriptiveText('Search words, family:resistor, -exclude…');row.Add(self.search,1,wx.ALL,3)
        self.category=wx.Choice(self,choices=['All categories']+list(self.catalog['counts']));self.category.SetSelection(0);row.Add(self.category,0,wx.ALL,3)
        self.status=wx.Choice(self,choices=['All execution types','Native subcircuits','Equation bench only']);self.status.SetSelection(0);row.Add(self.status,0,wx.ALL,3)
        self.sort=wx.Choice(self,choices=list(SORTS));self.sort.SetSelection(0);row.Add(self.sort,0,wx.ALL,3)
        self.descending=wx.CheckBox(self,label='Descending');row.Add(self.descending,0,wx.ALIGN_CENTER_VERTICAL|wx.ALL,4);box.Add(row,0,wx.EXPAND)
        row=wx.WrapSizer(wx.HORIZONTAL);self.unit=wx.Choice(self,choices=['Any unit']+sorted({r['parameter_unit'] for r in self.catalog['records']}));self.unit.SetSelection(0);row.Add(self.unit,0,wx.ALL,3)
        self.minimum=wx.TextCtrl(self,size=(80,-1));self.maximum=wx.TextCtrl(self,size=(80,-1))
        for label,control in [('Min SI',self.minimum),('Max SI',self.maximum)]:row.Add(wx.StaticText(self,label=label),0,wx.ALIGN_CENTER_VERTICAL|wx.ALL,3);row.Add(control,0,wx.ALL,3)
        self.favorite_only=wx.CheckBox(self,label='Favorites');self.recent_only=wx.CheckBox(self,label='Recent inserts')
        for c in (self.favorite_only,self.recent_only):row.Add(c,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        self.add_button(row,'Reset filters',self.reset_filters);self.add_button(row,'Search help',self.search_help);box.Add(row,0,wx.EXPAND)
        self.split=wx.SplitterWindow(self);self.split.SetMinimumPaneSize(120)
        self.tree=wx.TreeCtrl(self.split,style=wx.TR_HIDE_ROOT|wx.TR_HAS_BUTTONS|wx.TR_LINES_AT_ROOT);root=self.tree.AddRoot('Catalog');all_item=self.tree.AppendItem(root,'All categories');self.tree.SetItemData(all_item,(None,None))
        for category in self.catalog['counts']:
            item=self.tree.AppendItem(root,category+f" ({self.catalog['counts'][category]:,})");self.tree.SetItemData(item,(category,None))
            for family in sorted({r['family'] for r in self.catalog['records'] if r['category']==category}):
                child=self.tree.AppendItem(item,family.replace('_',' '));self.tree.SetItemData(child,(category,family))
        self.right=wx.SplitterWindow(self.split);self.right.SetMinimumPaneSize(200);self.list=ResultsList(self);self.list.Reparent(self.right)
        inspector=wx.Panel(self.right);self.inspector_panel=inspector;detail_box=wx.BoxSizer(wx.VERTICAL);self.notebook=wx.aui.AuiNotebook(inspector,style=wx.aui.AUI_NB_TOP|wx.aui.AUI_NB_SCROLL_BUTTONS|wx.aui.AUI_NB_WINDOWLIST_BUTTON)
        page=wx.ScrolledWindow(self.notebook);self.preview_page=page;page.SetScrollRate(0,12);s=wx.BoxSizer(wx.VERTICAL);self.preview=SymbolPreview(page,self);s.Add(self.preview,0,wx.EXPAND)
        self.details=wx.TextCtrl(page,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,95));s.Add(self.details,1,wx.EXPAND|wx.ALL,4)
        s.Add(wx.StaticText(page,label='Parameters (JSON; drafts retained while browsing)'),0,wx.ALL,5);self.parameters=wx.TextCtrl(page,style=wx.TE_MULTILINE,size=(-1,130));s.Add(self.parameters,1,wx.EXPAND|wx.ALL,4);page.SetSizer(s);self.notebook.AddPage(page,'Preview / parameters')
        self.recipe=wx.TextCtrl(self.notebook,style=wx.TE_MULTILINE|wx.TE_READONLY);self.notebook.AddPage(self.recipe,'SPICE / metadata')
        bench=wx.Panel(self.notebook);s=wx.BoxSizer(wx.VERTICAL);s.Add(wx.StaticText(bench,label='SI input map · equations, not circuit simulation'),0,wx.ALL,6)
        self.inputs=wx.TextCtrl(bench,value='{"x":0.1,"voltage":0.1,"current":0.01,"temperature_k":298.15,"frequency_hz":1000}',style=wx.TE_MULTILINE,size=(-1,100));s.Add(self.inputs,0,wx.EXPAND|wx.ALL,4)
        self.output=wx.TextCtrl(bench,style=wx.TE_MULTILINE|wx.TE_READONLY);s.Add(self.output,1,wx.EXPAND|wx.ALL,4)
        br=wx.WrapSizer(wx.HORIZONTAL);self.add_button(br,'Evaluate',self.evaluate,parent=bench);self.add_button(br,'Reset state',lambda:setattr(self,'state',{}),parent=bench);s.Add(br);bench.SetSizer(s);self.notebook.AddPage(bench,'Equation bench')
        detail_box.Add(self.notebook,1,wx.EXPAND);inspector.SetSizer(detail_box)
        self.right.SplitVertically(self.list,inspector,400);self.right.SetSashGravity(.5);self.split.SplitVertically(self.tree,self.right,160);self.split.SetSashGravity(0);box.Add(self.split,1,wx.EXPAND)
        self.match_label=wx.StaticText(self);box.Add(self.match_label,0,wx.ALL,5)
        row=wx.WrapSizer(wx.HORIZONTAL);self.insert_button=self.add_button(row,'Insert / multiple…',self.insert);self.favorite_button=self.add_button(row,'Favorite',self.toggle_favorite)
        self.add_button(row,'Reset parameter draft',self.reset_draft);self.add_button(row,'Export model…',self.export);self.add_button(row,'Physics models…',lambda:owner.open_physics_models());self.add_button(row,'Generate catalog…',self.generate);self.add_button(row,'Vendor intake…',self.vendor);box.Add(row,0,wx.EXPAND);self.SetSizer(box)
        self.search.Bind(wx.EVT_TEXT,self.debounce)
        self.parameters.Bind(wx.EVT_TEXT,lambda e:self.update_recipe())
        for c in (self.minimum,self.maximum):c.Bind(wx.EVT_TEXT,self.debounce)
        self.category.Bind(wx.EVT_CHOICE,lambda e:(setattr(self,'family_filter',None),self.safe_filter()))
        for c in (self.status,self.sort,self.unit):c.Bind(wx.EVT_CHOICE,lambda e:self.safe_filter())
        for c in (self.descending,self.favorite_only,self.recent_only):c.Bind(wx.EVT_CHECKBOX,lambda e:self.safe_filter())
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,self.tree_select);self.list.Bind(wx.EVT_LIST_ITEM_SELECTED,self.select);self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda e:owner.guarded(self.insert))
        self.list.Bind(wx.EVT_LIST_COL_CLICK,self.column_sort);self.list.Bind(wx.EVT_CONTEXT_MENU,self.context);self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)
        self.initial_layout=False;self.Bind(wx.EVT_SHOW,self.first_show);self.filter()
        self.refresh_symbols(owner.palette)

    def refresh_symbols(self,palette):
        from .symbol_icons import SymbolImages
        self.list.refresh_symbols(palette);self.tree_images=SymbolImages(None,palette);self.tree.AssignImageList(self.tree_images.image_list)
        def visit(parent):
            child,cookie=self.tree.GetFirstChild(parent)
            while child.IsOk():
                data=self.tree.GetItemData(child)
                self.tree.SetItemImage(child,self.tree_images.index(data[1] if data and data[1] else 'library'))
                visit(child);child,cookie=self.tree.GetNextChild(parent,cookie)
        visit(self.tree.GetRootItem())

    def set_compact(self,compact):
        self.pin_button.SetLabel('Unpin / full browser tab' if compact else 'Pin browser to side')
        self.summary.Show(not compact)
        if self.right.IsSplit():self.right.Unsplit(self.inspector_panel)
        self.inspector_panel.Show();self.right.SetMinimumPaneSize(120 if compact else 200)
        self.right.SetSashGravity(0 if compact else .5)
        if compact:
            if self.split.IsSplit():self.split.Unsplit(self.tree)
            self.right.SplitHorizontally(self.list,self.inspector_panel,180)
        else:
            if not self.split.IsSplit():self.tree.Show();self.split.SplitVertically(self.tree,self.right,165)
            self.right.SplitVertically(self.list,self.inspector_panel,400)
        self.Layout()
        self.preview_page.FitInside()

    def first_show(self,event):
        if event.IsShown() and not self.initial_layout:wx.CallAfter(self.fit_initial_layout)
        event.Skip()
    def fit_initial_layout(self):
        if not self or self.initial_layout or self.right.GetClientSize().width<650:return
        self.split.SetSashPosition(165);self.right.SetSashPosition(max(240,self.right.GetClientSize().width-390));self.initial_layout=True

    def add_button(self,row,label,callback,parent=None):
        b=wx.Button(parent or self,label=label);b.Bind(wx.EVT_BUTTON,lambda e:self.owner.guarded(callback));row.Add(b,0,wx.ALL,3);return b
    def preferences(self):return self.owner.doc.data['metadata'].get('library_browser',{})
    def destroyed(self,event):
        if event.GetEventObject() is self and self.pending:self.pending.Stop()
        event.Skip()
    def debounce(self,event):
        if self.pending:self.pending.Stop()
        self.pending=wx.CallLater(140,self.safe_filter)
    def safe_filter(self):
        try:self.filter()
        except (ValueError,TypeError) as exc:self.match_label.SetLabel('Filter: '+str(exc))
    def tree_select(self,event):
        value=self.tree.GetItemData(event.GetItem())
        if value is None:return
        category,self.family_filter=value;self.category.SetStringSelection(category or 'All categories');self.safe_filter()
    def column_sort(self,event):
        sort={0:'Name',1:'Family',2:'Primary value',4:'Execution'}.get(event.GetColumn())
        if sort is None:return
        self.descending.SetValue(not self.descending.GetValue() if self.sort.GetStringSelection()==sort else False);self.sort.SetStringSelection(sort);self.safe_filter()
    def reset_filters(self):
        self.search.ChangeValue('');self.minimum.ChangeValue('');self.maximum.ChangeValue('');self.category.SetSelection(0);self.status.SetSelection(0);self.unit.SetSelection(0);self.family_filter=None
        self.favorite_only.SetValue(False);self.recent_only.SetValue(False);self.sort.SetSelection(0);self.descending.SetValue(False);self.filter()
    def circuit_ready(self):
        self.reset_filters();self.status.SetSelection(1);self.filter();self.search.SetFocus()
    def manufacturer_sources(self):
        with wx.Dialog(self,title='Manufacturer model qualification',size=(780,610),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
            box=wx.BoxSizer(wx.VERTICAL)
            report=wx.TextCtrl(dialog,value=source_report(),style=wx.TE_MULTILINE|wx.TE_READONLY)
            box.Add(report,1,wx.EXPAND|wx.ALL,12)
            note=wx.StaticText(dialog,label='Use Vendor intake to inspect a model you have obtained. Intake is a review report, not installation or solver approval.');note.Wrap(730);box.Add(note,0,wx.ALL,12)
            box.Add(dialog.CreateButtonSizer(wx.OK),0,wx.ALIGN_RIGHT|wx.ALL,12);dialog.SetSizer(box);apply_window(dialog,self.owner.palette);dialog.ShowModal()
    def search_help(self):
        wx.MessageBox('Words are ANDed; ordinary words tolerate small typos, with literal matches first.\nQuoted phrases, -excluded terms and field values remain literal.\nFields: family:, category:, status:, unit:, id:, manufacturer:, qualification:, fidelity:.\nExample: family:resistor -cable\nThe generic catalog does not establish vendor-model qualification. Use the manufacturer browser for sourced part records and review.\nMin/max use primary-parameter SI values; select a family/unit first.\nValue sorting groups unlike units within match-quality tiers.\nFavorites/recent inserts save with the project. Parameter edits are session drafts until exported or inserted.','Catalog search',parent=self)
    def stash(self):
        if self.record:self.drafts[self.record['id']]=self.parameters.GetValue()
    def update_recipe(self):
        if self.record is None:return
        try:
            record=self.edited();text=native_recipe(record)['source']+'\n' if record['status']=='native_subcircuit' else 'NOT INSERTABLE: equation bench only.\n\n'
            self.recipe.SetValue(text+json.dumps(record,indent=2))
        except (ValueError,KeyError,TypeError) as exc:self.recipe.SetValue('Invalid parameter draft: '+str(exc))
    def filter(self):
        self.stash();selected=self.record['id'] if self.record else None;start=time.perf_counter();pref=self.preferences()
        low=float(self.minimum.GetValue()) if self.minimum.GetValue().strip() else None;high=float(self.maximum.GetValue()) if self.maximum.GetValue().strip() else None
        kind=self.status.GetSelection();recent=pref.get('recent',[]) if self.recent_only.GetValue() else ()
        rows=self.index.query(self.search.GetValue(),category=self.category.GetStringSelection() if self.category.GetSelection()>0 else None,family=self.family_filter,
            status=('native_subcircuit' if kind==1 else 'equation_bench_only') if kind else None,unit=self.unit.GetStringSelection() if self.unit.GetSelection()>0 else None,
            minimum=low,maximum=high,sort=self.sort.GetStringSelection(),descending=self.descending.GetValue(),favorites=pref.get('favorites',[]),only_favorites=self.favorite_only.GetValue(),recent=recent)
        if self.recent_only.GetValue() and not recent:rows=[]
        self.visible=rows;self.filtering=True;self.list.set_rows(rows);self.record=None;self.parameters.SetValue('');self.details.SetValue('Select a preset. Double-click a native row to insert.');self.recipe.SetValue('');self.state={}
        index=next((i for i,r in enumerate(rows) if r['id']==selected),-1);self.list.SetSelection(index);self.filtering=False
        if index>=0:self.select()
        else:self.insert_button.Disable();self.favorite_button.Disable();self.preview.Refresh()
        self.match_label.SetLabel(f'{len(rows):,} matches · query / list update {(time.perf_counter()-start)*1000:.1f} ms · '+(self.family_filter or 'all families'))
    def select(self,event=None):
        if self.filtering:return
        i=self.list.GetSelection()
        if i<0 or i>=len(self.visible):return
        record=self.visible[i]
        if self.record and self.record['id']==record['id']:return
        self.stash();self.record=deepcopy(record);self.state={};self.parameters.SetValue(self.drafts.get(record['id'],json.dumps(record['parameters'],indent=2)))
        self.details.SetValue(record['id']+'\n'+record['limitations']);self.update_recipe()
        contract=pin_contract(record)
        if contract:
            self.details.AppendText('\n\n'+contract['numbering']+'\n'+ '\n'.join(f"{p['number']}: {p['name']} [{p['role']}]" for p in contract['pins'])+'\n'+contract['power_behavior'])
        self.preview.SetMinSize((360 if contract else 200,preview_height(record)))
        self.preview_page.SetScrollRate(12,12)
        if contract and self.right.IsSplit():self.right.SetSashPosition(max(200,self.right.GetClientSize().width-400))
        self.preview_page.Layout();self.preview_page.FitInside()
        self.insert_button.Enable(record['status']=='native_subcircuit');self.favorite_button.Enable();self.favorite_button.SetLabel('Unfavorite' if record['id'] in self.preferences().get('favorites',[]) else 'Favorite');self.preview.Refresh()
    def reset_draft(self):
        if not self.record:return
        self.drafts.pop(self.record['id'],None);self.parameters.SetValue(json.dumps(self.record['parameters'],indent=2));self.state={}
    def toggle_favorite(self):
        if not self.record:raise ValueError('Select a preset')
        ident=self.record['id']
        def mutate(d):
            p=d['metadata'].setdefault('library_browser',{});favorites=set(p.get('favorites',[]));favorites.symmetric_difference_update({ident});p['favorites']=sorted(favorites)
        self.owner.doc.commit(mutate);self.owner.update_title();self.filter()
    def context(self,event):
        self._select_context_row(event)
        from .context_menus import ContextMenu
        menu=ContextMenu(self.owner);record=self.record
        selected=record is not None
        native=bool(selected and record['status']=='native_subcircuit')
        actions=menu.submenu('Use preset')
        actions.add('Insert / multiple…',self.insert,native,'This preset is equation-bench-only' if selected else 'Select a preset')
        actions.add('Assign placement shortcut…',self.assign_shortcut,native,'Only native insertable presets support placement shortcuts')
        menu.add('Unfavorite' if selected and record['id'] in self.preferences().get('favorites',[]) else 'Favorite',self.toggle_favorite,selected,'Select a preset')
        share=menu.submenu('Copy and export')
        share.add('Copy preset ID',self.copy_id,selected,'Select a preset')
        share.add('Export generic model…',self.export,selected,'Select a preset')
        menu.popup(self.list)

    def _select_context_row(self,event):
        """Target the pointer row; keyboard context menus retain focused selection."""
        position=event.GetPosition() if event is not None and hasattr(event,'GetPosition') else wx.DefaultPosition
        row=context_row(position,wx.DefaultPosition,len(self.visible),self.list.GetSelection(),self.list.ScreenToClient,self.list.HitTest)
        if row<0:
            self.list.SetSelection(-1);self.stash();self.record=None;self.state={}
            self.insert_button.Disable();self.favorite_button.Disable();self.preview.Refresh()
            return -1
        if row!=self.list.GetSelection():
            self.list.SetSelection(row);self.select()
        return row
    def assign_shortcut(self):
        if not self.record or self.record['status']!='native_subcircuit':raise ValueError('Only native insertable presets can have placement shortcuts')
        self.owner.assign_part_shortcut(self.record['id'])
    def copy_id(self):
        if self.record and wx.TheClipboard.Open():
            try:wx.TheClipboard.SetData(wx.TextDataObject(self.record['id']))
            finally:wx.TheClipboard.Close()
    def edited(self):
        if self.record is None:raise ValueError('Select a component preset')
        record=deepcopy(self.record);record['parameters']=json.loads(self.parameters.GetValue());validate_record(record);return record
    def evaluate(self):
        result=evaluate(self.edited(),json.loads(self.inputs.GetValue()),self.state);self.state=result['state'];self.output.SetValue(json.dumps(result,indent=2));self.notebook.SetSelection(2)
        self.output.SetForegroundColour(self.owner.palette['danger'] if result['alerts'] else self.owner.palette['fg'])
    def insert_recipe(self,record,mapping,*,count=1,position=None):
        if self.owner.job_running:raise ValueError('Stop simulation before inserting a model')
        if self.owner.source.GetText()!=self.owner.doc.data['source']:raise ValueError('Apply circuit text edits before inserting; the draft has been retained')
        if position is None:position=(140,180+160*((len(self.owner.doc.data['components'])+3)//4))
        if record.get('_manufacturer_record'):
            from .manufacturer_parts import install
            plan=install(self.owner.doc,record['_manufacturer_record'],mapping,count=count,x=float(position[0]),y=float(position[1]),primitive=True)
        else:
            plan=insertion_plan(self.owner.doc,record,mapping,count=count,x=float(position[0]),y=float(position[1]),primitive=True);apply_insertion(self.owner.doc,plan,record['id'])
        self.owner.refresh_document();self.owner.book.SetSelection(self.owner.editor_page());self.owner.SetStatusText(f"Inserted {count} instance(s): {', '.join(plan['refs'][:8])} · Ctrl+Z undoes the entire insertion");return plan
    def insert(self):
        record=self.edited();native_recipe(record)
        if self.owner.job_running:raise ValueError('Stop simulation before placing components')
        if self.owner.source.GetText()!=self.owner.doc.data['source']:raise ValueError('Apply circuit text edits before placing components')
        with InsertDialog(self,record) as dlg:
            if dlg.ShowModal()!=wx.ID_OK:return
            record=dlg.edited_record()
            mapping={p:c.GetValue() for p,c in dlg.pins.items()};count=dlg.count.GetValue();insertion_plan(self.owner.doc,record,mapping,count=count)
            if dlg.place.GetValue():
                self.owner.pending_library_placement=(deepcopy(record),mapping,count);self.owner.canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS));self.owner.book.SetSelection(self.owner.editor_page());self.owner.canvas.SetFocus();self.owner.canvas.Refresh();self.owner.SetStatusText(f'Click schematic to place {count} instance(s); Escape cancels')
            else:self.insert_recipe(record,mapping,count=count)
    def export(self):
        record=self.edited();path=self.owner.choose_path('Export generic model','SPIKES component (*.spkpart)|*.spkpart',True)
        if path:write_json(path,{'contract':'spikes/generic-component/v1','record':record})
    def generate(self):
        path=self.owner.choose_path('Generate local catalog','SPIKES catalog (*.json)|*.json',True)
        if path:
            payload=materialize(path);self.output.SetValue(f"Wrote {len(payload['records']):,} configurable presets to {path}; not qualified manufacturer models.");self.notebook.SetSelection(2)
    def manufacturer_library(self):
        """Separate real imported source from generic recipe catalog."""
        with wx.Dialog(self,title='Manufacturer library · project-local review shelf',size=(860,650),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
            box=wx.BoxSizer(wx.VERTICAL)
            note=wx.StaticText(dlg,label='Real source files with provenance and pin inventories. Review is NOT simulation qualification.\nStored with this project; do not redistribute without manufacturer permission.');box.Add(note,0,wx.ALL,10)
            query=wx.SearchCtrl(dlg);query.SetDescriptiveText('Search manufacturer, exact part number or model name');box.Add(query,0,wx.EXPAND|wx.ALL,6)
            from .symbol_text_list import SymbolTextList
            listing=SymbolTextList(dlg,self.owner.palette,resolver=lambda index,text:'ic',size=(-1,130));box.Add(listing,0,wx.EXPAND|wx.ALL,6)
            detail=wx.TextCtrl(dlg,style=wx.TE_READONLY|wx.TE_MULTILINE);box.Add(detail,1,wx.EXPAND|wx.ALL,6)
            rows=[]
            def refresh(event=None):
                from .fuzzy_search import ranked
                rows[:]=ranked(self.owner.doc.data['metadata'].get('manufacturer_models',{}).values(),query.GetValue(),text=lambda value:json.dumps(value.get('provenance',{}))+' '+str(value['subcircuits']))
                listing.Set([r['provenance']['manufacturer']+' · '+r['provenance']['part_number']+' · review only' for r in rows]);detail.SetValue('Import a manufacturer SPICE file to begin.' if not rows else 'Select a model to inspect pins, dependencies and source.')
            def select(event):
                if listing.GetSelection()>=0:detail.SetValue(json.dumps(rows[listing.GetSelection()],indent=2))
            button=wx.Button(dlg,label='Import manufacturer file…');button.Bind(wx.EVT_BUTTON,lambda e:(self.owner.guarded(self.vendor),refresh()));box.Add(button,0,wx.ALL,6)
            collection=wx.Button(dlg,label='Browse / index SPICE collection folder…');collection.Bind(wx.EVT_BUTTON,lambda e:self.owner.guarded(self.model_collections));box.Add(collection,0,wx.ALL,6)
            box.Add(dlg.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,8);dlg.SetSizer(box);query.Bind(wx.EVT_TEXT,refresh);listing.Bind(wx.EVT_LISTBOX,select);refresh();apply_window(dlg,self.owner.palette);dlg.ShowModal()

    def model_collections(self):
        from .collection_panel import CollectionDialog
        with CollectionDialog(self.owner) as dialog:dialog.ShowModal()

    def vendor(self):
        path=self.owner.choose_path('Import a manufacturer model for review','SPICE model|*.lib;*.cir;*.mod;*.sp;*.txt')
        if not path:return
        from .vendor_intake import intake,store_review
        report=intake(path);self.output.SetValue(json.dumps(report,indent=2));self.notebook.SetSelection(2)
        with wx.Dialog(self,title='Manufacturer provenance · no execution approval',size=(560,310)) as dlg:
            box=wx.BoxSizer(wx.VERTICAL);fields=[]
            for label in ('Manufacturer','Exact part number','HTTPS manufacturer model source URL'):
                box.Add(wx.StaticText(dlg,label=label),0,wx.LEFT|wx.TOP,8);control=wx.TextCtrl(dlg);box.Add(control,0,wx.EXPAND|wx.ALL,8);fields.append(control)
            box.Add(dlg.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALIGN_RIGHT|wx.ALL,8);dlg.SetSizer(box);apply_window(dlg,self.owner.palette)
            if dlg.ShowModal()!=wx.ID_OK:return
            store_review(self.owner.doc,report,*[c.GetValue() for c in fields]);self.owner.update_title()
        destination=self.owner.choose_path('Save local review package (not executable approval)','SPIKES review (*.spkmodel)|*.spkmodel',True)
        if destination:write_json(destination,report)
