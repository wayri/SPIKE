"""Virtualized interactive library browser; previews never imply solver support."""
from copy import deepcopy
import json
import time
import wx
import wx.aui
from .component_catalog import catalog,evaluate,native_recipe,validate_record,materialize
from .document import write_json
from .library_browser import CatalogIndex,SORTS,insertion_plan,apply_insertion
from .themes import apply_window


class ResultsList(wx.ListCtrl):
    def __init__(self,parent):
        super().__init__(parent,style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL)
        self.browser=parent;self.rows=[]
        for i,(label,width) in enumerate([('Preset',245),('Family',120),('Value',95),('Unit',65),('Execution',105)]):self.InsertColumn(i,label,width=width)
    def OnGetItemText(self,item,column):
        if not 0<=item<len(self.rows):return ''
        r=self.rows[item]
        return [('* ' if r['id'] in self.browser.preferences().get('favorites',[]) else '')+r['name'],r['family'],f"{self.browser.index.values[r['id']]:.7g}",r['parameter_unit'],'Native' if r['status']=='native_subcircuit' else 'Bench only'][column]
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
            dc.DrawCircle(*at,4);dc.DrawText(pin,at[0]-15,at[1]+10)
        dc.SetTextForeground(p['muted']);dc.DrawText('Native pin preview' if native else 'Equation block — not an electrical pinout',10,12)
        dc.DrawText('Conventional symbol · conformance unverified',10,max(185,h-22))


class InsertDialog(wx.Dialog):
    def __init__(self,browser,record):
        super().__init__(browser,title='Insert native model · explicit connections',size=(540,470),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.browser=browser;self.record=record;model=native_recipe(record);box=wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(self,label=record['name']),0,wx.ALL,10);grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=8);grid.AddGrowableCol(1);self.pins={}
        for pin in model['pins']:
            grid.Add(wx.StaticText(self,label=pin),0,wx.ALIGN_CENTER_VERTICAL)
            control=wx.TextCtrl(self,value='0' if pin in ('N','REF') else 'part_{n}_'+pin.lower());grid.Add(control,1,wx.EXPAND);self.pins[pin]=control
        grid.Add(wx.StaticText(self,label='Instances'),0,wx.ALIGN_CENTER_VERTICAL);self.count=wx.SpinCtrl(self,min=1,max=100,initial=1);grid.Add(self.count,1,wx.EXPAND);box.Add(grid,0,wx.EXPAND|wx.ALL,10)
        note=wx.StaticText(self,label='Use {n} for per-instance nodes: out_{n} becomes out_1, out_2…\nNames without {n} are shared intentionally. Ground is 0.\nInternal primitives are inserted; no compact hierarchy symbol yet.\nAll copies form one undoable transaction.');note.Wrap(490);box.Add(note,0,wx.ALL,10)
        self.place=wx.CheckBox(self,label='Click on schematic to choose placement (Escape cancels)');self.place.SetValue(True);box.Add(self.place,0,wx.ALL,10)
        buttons=self.CreateButtonSizer(wx.OK|wx.CANCEL);self.FindWindow(wx.ID_OK).SetLabel('Place / insert');box.Add(buttons,0,wx.ALIGN_RIGHT|wx.ALL,10);self.SetSizer(box);apply_window(self,browser.owner.palette)


class ComponentPanel(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.catalog=catalog();self.index=CatalogIndex(self.catalog['records']);self.visible=[];self.record=None;self.state={};self.drafts={};self.pending=None;self.family_filter=None;self.filtering=False
        box=wx.BoxSizer(wx.VERTICAL)
        self.pin_button=wx.Button(self,label='Pin browser to side');self.pin_button.Bind(wx.EVT_BUTTON,lambda e:owner.pin_browser());box.Add(self.pin_button,0,wx.ALL,3)
        self.summary=wx.StaticText(self,label='5,000 presets · 100 archetypes · 650 native / 4,350 bench-only · 0 qualified vendor models');box.Add(self.summary,0,wx.ALL,6)
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
            item=self.tree.AppendItem(root,category+' (500)');self.tree.SetItemData(item,(category,None))
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
        self.add_button(row,'Reset parameter draft',self.reset_draft);self.add_button(row,'Export model…',self.export);self.add_button(row,'Generate catalog…',self.generate);self.add_button(row,'Vendor intake…',self.vendor);box.Add(row,0,wx.EXPAND);self.SetSizer(box)
        self.search.Bind(wx.EVT_TEXT,self.debounce)
        self.parameters.Bind(wx.EVT_TEXT,lambda e:self.update_recipe())
        for c in (self.minimum,self.maximum):c.Bind(wx.EVT_TEXT,self.debounce)
        self.category.Bind(wx.EVT_CHOICE,lambda e:(setattr(self,'family_filter',None),self.safe_filter()))
        for c in (self.status,self.sort,self.unit):c.Bind(wx.EVT_CHOICE,lambda e:self.safe_filter())
        for c in (self.descending,self.favorite_only,self.recent_only):c.Bind(wx.EVT_CHECKBOX,lambda e:self.safe_filter())
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED,self.tree_select);self.list.Bind(wx.EVT_LIST_ITEM_SELECTED,self.select);self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda e:owner.guarded(self.insert))
        self.list.Bind(wx.EVT_LIST_COL_CLICK,self.column_sort);self.list.Bind(wx.EVT_CONTEXT_MENU,self.context);self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)
        self.initial_layout=False;self.Bind(wx.EVT_SHOW,self.first_show);self.filter()

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
    def search_help(self):
        wx.MessageBox('Words are ANDed; quoted phrases and -excluded terms work.\nFields: family:, category:, status:, unit:, id:.\nExample: family:resistor -cable\nMin/max use primary-parameter SI values; select a family/unit first.\nValue sorting groups unlike units.\nFavorites/recent inserts save with the project. Parameter edits are session drafts until exported or inserted.','Catalog search',parent=self)
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
        menu=wx.Menu()
        for label,fn in [('Insert / multiple…',self.insert),('Assign placement shortcut…',self.assign_shortcut),('Toggle favorite',self.toggle_favorite),('Export model…',self.export),('Copy preset ID',self.copy_id)]:
            item=menu.Append(wx.ID_ANY,label);self.Bind(wx.EVT_MENU,lambda e,f=fn:self.owner.guarded(f),item)
            if label.startswith('Insert'):item.Enable(bool(self.record and self.record['status']=='native_subcircuit'))
        self.PopupMenu(menu);menu.Destroy()
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
        plan=insertion_plan(self.owner.doc,record,mapping,count=count,x=float(position[0]),y=float(position[1]));apply_insertion(self.owner.doc,plan,record['id'])
        self.owner.refresh_document();self.owner.book.SetSelection(0);self.owner.SetStatusText(f"Inserted {count} instance(s): {', '.join(plan['refs'][:8])} · Ctrl+Z undoes the entire insertion");return plan
    def insert(self):
        record=self.edited();native_recipe(record)
        if self.owner.job_running:raise ValueError('Stop simulation before placing components')
        if self.owner.source.GetText()!=self.owner.doc.data['source']:raise ValueError('Apply circuit text edits before placing components')
        with InsertDialog(self,record) as dlg:
            if dlg.ShowModal()!=wx.ID_OK:return
            mapping={p:c.GetValue() for p,c in dlg.pins.items()};count=dlg.count.GetValue();insertion_plan(self.owner.doc,record,mapping,count=count)
            if dlg.place.GetValue():
                self.owner.pending_library_placement=(deepcopy(record),mapping,count);self.owner.canvas.SetCursor(wx.Cursor(wx.CURSOR_CROSS));self.owner.book.SetSelection(0);self.owner.canvas.SetFocus();self.owner.canvas.Refresh();self.owner.SetStatusText(f'Click schematic to place {count} instance(s); Escape cancels')
            else:self.insert_recipe(record,mapping,count=count)
    def export(self):
        record=self.edited();path=self.owner.choose_path('Export generic model','SPIKES component (*.spkpart)|*.spkpart',True)
        if path:write_json(path,{'contract':'spikes/generic-component/v1','record':record})
    def generate(self):
        path=self.owner.choose_path('Generate local catalog','SPIKES catalog (*.json)|*.json',True)
        if path:materialize(path);self.output.SetValue(f'Wrote 5,000 presets to {path}. Counts are presets, not qualified models.');self.notebook.SetSelection(2)
    def vendor(self):
        path=self.owner.choose_path('Import a manufacturer model for review','SPICE model|*.lib;*.cir;*.mod;*.sp;*.txt')
        if not path:return
        from .vendor_intake import intake
        report=intake(path);self.output.SetValue(json.dumps(report,indent=2));self.notebook.SetSelection(2)
        destination=self.owner.choose_path('Save local review package (not executable approval)','SPIKES review (*.spkmodel)|*.spkmodel',True)
        if destination:write_json(destination,report)
