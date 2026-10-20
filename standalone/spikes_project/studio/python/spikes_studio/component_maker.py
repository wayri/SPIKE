# SPDX-License-Identifier: Apache-2.0
"""Floating visual component, implementation and versioned user-library workbench."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import wx
import wx.stc

from . import component_package as packages
from .symbol_designer import SymbolDesignerPanel
from .themes import apply_window,preferences_path


class ComponentMaker(wx.Frame):
    def __init__(self,owner,value=None):
        super().__init__(owner,title='Component maker · symbol, pins and behavior',size=(1120,800))
        icon=owner.GetIcon()
        if icon.IsOk():self.SetIcon(icon)
        self.SetMinSize((800,560));self.owner=owner;self.palette=owner.palette
        self.store=packages.ComponentStore(preferences_path().parent/'components')
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='component-build')
        self.busy=False;self.closed=False;self.record=None;self.library_rows=[];self.library_cache=None;self.clean_snapshot=None
        root=wx.Panel(self);layout=wx.BoxSizer(wx.VERTICAL);root.SetSizer(layout)
        self.fields={};identity=wx.FlexGridSizer(cols=4,hgap=8,vgap=5);identity.AddGrowableCol(1);identity.AddGrowableCol(3)
        for key,label in [('id','Library ID'),('name','Component name'),('version','Version'),('license','License / redistribution terms')]:
            identity.Add(wx.StaticText(root,label=label),0,wx.ALIGN_CENTER_VERTICAL)
            self.fields[key]=wx.TextCtrl(root);identity.Add(self.fields[key],1,wx.EXPAND)
        layout.Add(identity,0,wx.EXPAND|wx.ALL,10)
        self.book=wx.Notebook(root);layout.Add(self.book,1,wx.EXPAND|wx.LEFT|wx.RIGHT,8)
        self.designer=SymbolDesignerPanel(self.book,owner,embedded=True);self.book.AddPage(self.designer,'Symbol & pins')
        self._behavior_page();self._library_page();self.book.AddPage(self.report_page,'Validation / build report')
        row=wx.WrapSizer(wx.HORIZONTAL)
        for label,handler,tip in [('Save component…',self.save,'Export source, pins and geometry as an inert .spkcmp package'),
                                  ('Add to user library',self.install,'Persist this exact component ID/version; imports never compile code'),
                                  ('Place / attach…',self.place,'Preflight SPICE insertion, load a sampled C++ controller, or open HDL source')]:
            button=wx.Button(root,label=label);button.SetToolTip(tip);button.Bind(wx.EVT_BUTTON,lambda event,fn=handler:self.guard(fn));row.Add(button,0,wx.ALL,4)
        layout.Add(row,0,wx.ALL,5);self.status=wx.StaticText(root,label='');layout.Add(self.status,0,wx.EXPAND|wx.ALL,8)
        self._menu();self.load_value(value or packages.new_component());apply_window(self,owner.palette)
        self.Bind(wx.EVT_CLOSE,self.close)
        if not hasattr(owner,'component_makers'):owner.component_makers=[]
        owner.component_makers.append(self)

    def _menu(self):
        menu=wx.MenuBar();file=wx.Menu();component=wx.Menu()
        for label,fn in [('New component',self.new),('Open component…',self.open),('Import SPICE model…',self.import_model),('Save component…\tCtrl+S',self.save)]:
            item=file.Append(wx.ID_ANY,label);self.Bind(wx.EVT_MENU,lambda event,f=fn:self.guard(f),item)
        for label,fn in [('Validate interface',self.validate),('Build trusted implementation…',self.build),('Place / attach…',self.place)]:
            item=component.Append(wx.ID_ANY,label);self.Bind(wx.EVT_MENU,lambda event,f=fn:self.guard(f),item)
        from .toolchains import show as configure_tools
        item=component.Append(wx.ID_ANY,'Configure compiler / HDL tools…');self.Bind(wx.EVT_MENU,lambda event:self.guard(lambda:configure_tools(self)),item)
        menu.Append(file,'File');menu.Append(component,'Component');self.SetMenuBar(menu)

    def _behavior_page(self):
        panel=wx.Panel(self.book);box=wx.BoxSizer(wx.VERTICAL);grid=wx.FlexGridSizer(cols=4,hgap=8,vgap=6);grid.AddGrowableCol(1);grid.AddGrowableCol(3)
        self.language=wx.Choice(panel,choices=list(packages.LANGUAGES));self.language.SetSelection(0)
        self.entry=wx.TextCtrl(panel);self.prefix=wx.TextCtrl(panel,value='X')
        self.step=wx.TextCtrl(panel,value='0.0001');self.states=wx.SpinCtrl(panel,min=1,max=64,initial=8)
        for label,widget in [('Implementation',self.language),('Entry / module',self.entry),('SPICE prefix',self.prefix),('Sample interval (s)',self.step),('C++ explicit states',self.states)]:
            grid.Add(wx.StaticText(panel,label=label),0,wx.ALIGN_CENTER_VERTICAL);grid.Add(widget,1,wx.EXPAND)
        box.Add(grid,0,wx.EXPAND|wx.ALL,8)
        box.Add(wx.StaticText(panel,label='SPICE: electrical equations / SUBCKT / MODEL. C++: sampled Controller ABI. Verilog: digital HDL artifact, not analog pin co-simulation.'),0,wx.EXPAND|wx.ALL,6)
        from .desktop import text_editor
        self.source=text_editor(panel);box.Add(self.source,2,wx.EXPAND|wx.ALL,6)
        self.description=wx.TextCtrl(panel,style=wx.TE_MULTILINE,size=(-1,50));self.description.SetHint('Model assumptions, units, validity and source provenance')
        box.Add(self.description,0,wx.EXPAND|wx.ALL,6)
        self.trust=wx.CheckBox(panel,label='I trust this exact source and pin interface. Compilers/native code can access my files/network; no hostile-code sandbox.')
        box.Add(self.trust,0,wx.ALL,6);row=wx.WrapSizer(wx.HORIZONTAL)
        for label,fn in [('New interface template…',self.template),('Validate interface',self.validate),('Build trusted implementation…',self.build)]:
            button=wx.Button(panel,label=label);button.Bind(wx.EVT_BUTTON,lambda event,f=fn:self.guard(f));row.Add(button,0,wx.ALL,3)
        box.Add(row,0,wx.EXPAND)
        self.report_page=wx.Panel(self.book);report_box=wx.BoxSizer(wx.VERTICAL)
        self.report=wx.TextCtrl(self.report_page,style=wx.TE_MULTILINE|wx.TE_READONLY)
        report_box.Add(self.report,1,wx.EXPAND|wx.ALL,8);self.report_page.SetSizer(report_box)
        panel.SetSizer(box);self.book.AddPage(panel,'Model / code')
        self.language.Bind(wx.EVT_CHOICE,self.language_changed)
        self.source.Bind(wx.stc.EVT_STC_CHANGE,lambda event:self.trust.SetValue(False))

    def _library_page(self):
        panel=wx.Panel(self.book);box=wx.BoxSizer(wx.VERTICAL)
        self.search=wx.SearchCtrl(panel);self.search.SetDescriptiveText('Fuzzy search user components by name, ID, version or language');box.Add(self.search,0,wx.EXPAND|wx.ALL,8)
        self.listing=wx.ListCtrl(panel,style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        for index,(label,width) in enumerate([('Component',250),('Library ID',240),('Version',90),('Implementation',110),('Pins',60),('Qualification',150)]):self.listing.InsertColumn(index,label,width=width)
        box.Add(self.listing,1,wx.EXPAND|wx.ALL,8)
        button=wx.Button(panel,label='Load selected into maker');button.Bind(wx.EVT_BUTTON,lambda event:self.guard(self.load_selected));box.Add(button,0,wx.ALL,8)
        reload=wx.Button(panel,label='Reload user library');reload.Bind(wx.EVT_BUTTON,lambda event:self.guard(lambda:self.refresh_library(rescan=True)));box.Add(reload,0,wx.LEFT|wx.BOTTOM,8)
        panel.SetSizer(box);self.book.AddPage(panel,'User library')
        self.search.Bind(wx.EVT_TEXT,lambda event:self.guard(self.refresh_library));self.listing.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda event:self.guard(self.load_selected))

    def guard(self,fn):
        try:
            if self.busy:raise ValueError('Wait for the current build to finish')
            return fn()
        except Exception as exc:self.status.SetLabel(str(exc));self.report.SetValue(str(exc));self.book.SetSelection(3);self.Layout()

    def load_value(self,value):
        packages.validate(value);self.record=deepcopy(value)
        for key,field in self.fields.items():field.ChangeValue(value[key])
        self.designer.symbol=deepcopy(value['symbol']);self.designer.selected=0;self.designer.history=[];self.designer.refresh()
        impl=value['implementation'];self.language.SetStringSelection(impl['language']);self.entry.ChangeValue(impl['entry']);self.prefix.ChangeValue(impl.get('prefix','X'))
        self.source.SetText(impl['source']);self.description.ChangeValue(value['description']);self.trust.SetValue(False)
        config=impl.get('controller',{});self.step.ChangeValue(str(config.get('step_s',1e-4)));self.states.SetValue(config.get('state_count',8))
        self.language_changed(None);self.status.SetLabel('Loaded without executing code. Qualification: not performed.');self.refresh_library()
        self.clean_snapshot=self.draft_snapshot()

    def draft_snapshot(self):
        return json.dumps({'fields':{k:v.GetValue() for k,v in self.fields.items()},'symbol':self.designer.symbol,
            'pending_pin':self.pending_pin(),'language':self.language.GetStringSelection(),
            'source':self.source.GetText(),'entry':self.entry.GetValue(),'prefix':self.prefix.GetValue(),
            'step':self.step.GetValue(),'states':self.states.GetValue(),'description':self.description.GetValue()},sort_keys=True)

    def pending_pin(self):
        editor=self.designer;pin=editor.symbol['terminals'][editor.selected];side=pin.get('direction','west')
        entered=(editor.fields['number'].GetValue(),editor.fields['pin_name'].GetValue(),editor.side.GetStringSelection(),editor.position.GetValue()*editor.symbol['grid'])
        expected=(pin['id'],pin['name'],side,pin['at'][1 if side in ('west','east') else 0])
        return entered if entered!=expected else None

    def confirm_replace(self):
        if self.clean_snapshot is None or self.draft_snapshot()==self.clean_snapshot:return True
        answer=wx.MessageBox('Save this component draft before replacing or closing it?','Unsaved component',wx.YES_NO|wx.CANCEL|wx.ICON_QUESTION,self)
        if answer==wx.CANCEL:return False
        if answer==wx.YES:return bool(self.save())
        return True

    def new(self):
        if self.confirm_replace():self.load_value(packages.new_component())

    def value(self):
        if self.pending_pin():self.designer.apply_pin()
        value=deepcopy(self.record)
        for key,field in self.fields.items():value[key]=field.GetValue().strip()
        symbol=self.designer.draft();symbol['id']=value['id']+'.symbol';symbol['name']=value['name'];value['symbol']=symbol
        impl={'language':self.language.GetStringSelection(),'entry':self.entry.GetValue().strip(),'source':self.source.GetText()}
        if impl['language']=='SPICE':impl['prefix']=self.prefix.GetValue().strip().upper()
        if impl['language']=='C++':impl['controller']=packages.controller_config(symbol,impl['source'],float(self.step.GetValue()),self.states.GetValue())
        value.update(implementation=impl,description=self.description.GetValue().strip())
        return packages.validate(value)

    def language_changed(self,event):
        language=self.language.GetStringSelection();self.prefix.Enable(language=='SPICE');self.step.Enable(language=='C++');self.states.Enable(language=='C++')
        self.source.SetLexer(wx.stc.STC_LEX_CPP if language=='C++' else wx.stc.STC_LEX_VERILOG if language=='Verilog' else wx.stc.STC_LEX_SPICE)
        self.trust.SetValue(False)
        if event is not None and language=='C++':self.entry.ChangeValue('control_step')

    def validate(self):
        value=self.value();self.report.SetValue('Interface valid; behavior SHA256: '+packages.behavior_digest(value)+'\nNo simulation or manufacturer qualification was performed.\nSPICE insertion additionally checks the current native parser. Compiled languages retain their explicit ABI/backend limits.')
        self.book.SetSelection(3);self.status.SetLabel('Validated source/pins/geometry, not physical accuracy.');return value

    def template(self):
        if wx.MessageBox('Replace the model editor with a new interface template?','Component maker',wx.YES_NO|wx.NO_DEFAULT,self)!=wx.YES:return
        language=self.language.GetStringSelection();name=self.entry.GetValue().strip();pins=self.designer.symbol['terminals']
        if language=='SPICE':text=f'.subckt {name} '+ ' '.join(p['name'] for p in pins)+f'\n* Add electrical elements or B-source equations here.\n.ends {name}\n';self.prefix.ChangeValue('X')
        elif language=='C++':
            from .controller_block import DEFAULT_CODE
            text=DEFAULT_CODE;self.entry.ChangeValue('control_step')
        else:
            for p in pins:p['mode']='DI' if p.get('mode','AI').endswith('I') else 'DO'
            declarations=[('input wire ' if p['mode']=='DI' else 'output wire ')+p['name'] for p in pins]
            text=f'module {name}('+', '.join(declarations)+');\n// Add digital behavior here.\nendmodule\n';self.designer.refresh()
        self.source.SetText(text);self.language_changed(None)

    def choose(self,title,wildcard,save=False):
        with wx.FileDialog(self,title,wildcard=wildcard,style=(wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) if save else (wx.FD_OPEN|wx.FD_FILE_MUST_EXIST)) as dialog:
            return Path(dialog.GetPath()) if dialog.ShowModal()==wx.ID_OK else None

    def save(self):
        value=self.value();path=self.choose('Save component package','SPIKES component (*.spkcmp)|*.spkcmp',True)
        if path:
            packages.save(path,value);self.clean_snapshot=self.draft_snapshot();self.status.SetLabel('Saved inert component package: '+str(path));return True
        return False

    def open(self):
        path=self.choose('Open component package','SPIKES component (*.spkcmp)|*.spkcmp')
        if path:
            value=packages.load(path)
            if self.confirm_replace():self.load_value(value)

    def import_model(self):
        path=self.choose('Import SPICE model source','SPICE models|*.lib;*.mod;*.cir;*.sp;*.spi;*.spice;*.sub;*.txt|All files|*.*')
        if not path:return
        with path.open('rb') as stream:raw=stream.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('Model import limit: 1 MiB')
        self.import_text(raw.decode('utf-8-sig'))

    def import_text(self,source):
        from .vendor_intake import inspect_text
        report=inspect_text(source);entries=report['subcircuits']+report['models']
        if not entries:raise ValueError('No .MODEL or .SUBCKT declaration was found. Wrap device equations in a named .SUBCKT before import.')
        if len(entries)>1:
            with wx.SingleChoiceDialog(self,'Select the public model entry. All source/dependencies remain preserved.','Model entry',[r['name'] for r in entries]) as choice:
                if choice.ShowModal()!=wx.ID_OK:return
                entry=entries[choice.GetSelection()]['name']
        else:entry=entries[0]['name']
        try:value=packages.from_spice(source,entry)
        except ValueError as error:
            if 'explicitly supply' not in str(error):raise
            with wx.TextEntryDialog(self,'Enter primitive prefix followed by ordered pin names, e.g. Z D G S B T','Unknown model interface') as dialog:
                if dialog.ShowModal()!=wx.ID_OK:return
                tokens=dialog.GetValue().split()
                if len(tokens)<2:raise ValueError('Enter a prefix and ordered pins')
                value=packages.from_spice(source,entry,tokens[0].upper(),tokens[1:])
        if self.confirm_replace():self.load_value(value);self.book.SetSelection(1)

    def install(self):
        path=self.store.install(self.value());self.refresh_library(rescan=True);self.clean_snapshot=self.draft_snapshot();self.status.SetLabel('Installed user component: '+str(path))

    def refresh_library(self,*,rescan=False):
        from .fuzzy_search import ranked
        root=str(self.store.root.resolve())
        if rescan or self.library_cache is None or self.library_cache[0]!=root:self.library_cache=(root,self.store.entries())
        rows=ranked(self.library_cache[1],self.search.GetValue(),text=lambda r:' '.join(str(r['component'].get(k,'')) for k in ('id','name','version'))+' '+r['component']['implementation']['language'])
        self.library_rows=rows;self.listing.DeleteAllItems()
        for row in rows:
            value=row['component'];index=self.listing.InsertItem(self.listing.GetItemCount(),value['name'])
            for col,text in enumerate([value['id'],value['version'],value['implementation']['language'],str(len(value['symbol']['terminals'])),'Not qualified'],1):self.listing.SetItem(index,col,text)

    def load_selected(self):
        index=self.listing.GetFirstSelected()
        if index<0:raise ValueError('Select a component version')
        value=self.library_rows[index]['component']
        if self.confirm_replace():self.load_value(value);self.book.SetSelection(0)

    def build(self):
        value=self.value()
        if not self.trust.GetValue():raise ValueError('Review and approve this exact source/interface before invoking compilers')
        with wx.DirDialog(self,'Choose build artifact directory') as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            destination=Path(dialog.GetPath())
        digest=packages.behavior_digest(value);self.busy=True;self.source.Enable(False);self.status.SetLabel('Building in a worker; imported packages never execute automatically…')
        def work():
            from .component_build import build_component
            return build_component(value,destination,trusted=True,approval_sha256=digest)
        future=self.executor.submit(work)
        def complete():
            if self.closed:return
            self.busy=False;self.source.Enable(True)
            try:
                result=future.result();self.report.SetValue(str(result['status'])+'\n'+result.get('log','')+'\nArtifact: '+str(result.get('artifact_path'))+'\n'+ '\n'.join(result.get('limitations',[])))
                self.status.SetLabel('Build '+result['status']+'; no automatic attachment or qualification.')
            except Exception as error:self.status.SetLabel(str(error));self.report.SetValue(str(error))
            self.book.SetSelection(3)
        future.add_done_callback(lambda future:wx.CallAfter(complete))

    def place(self):
        if self.owner.job_running:raise ValueError('Stop the active simulation before attaching components')
        value=self.value();language=value['implementation']['language']
        if language=='C++':
            self.owner.controller_panel.load_block(value['implementation']['controller']);self.owner.book.SetSelection(12)
            self.status.SetLabel('Loaded sampled C++ block. Review actual input/output source bindings, then explicitly trust/compile in Controller.');return
        if language=='Verilog':
            self.owner.code.SetText(value['implementation']['source']);self.owner.language.SetStringSelection('Verilog');self.owner.top.SetValue(value['implementation']['entry']);self.owner.book.SetSelection(3)
            self.status.SetLabel('Opened HDL source. Compile/synthesis/timing is separate from analog-MNA pin coupling.');return
        if self.owner.source.GetText()!=self.owner.doc.data['source']:raise ValueError('Apply circuit-text edits before inserting a component')
        with PinMappingDialog(self,value,self.owner.doc) as dialog:
            if dialog.ShowModal()!=wx.ID_OK:return
            mapping=dialog.result
        plan=packages.prepare_insert(self.owner.doc,value,mapping)
        packages.insert(self.owner.doc,plan);self.owner.refresh_document(force_source=True)
        self.owner.canvas.selected={'component-instance:'+plan['ref']} if value['implementation']['prefix']=='X' else set(plan['part_ids'])
        self.owner.book.SetSelection(self.owner.editor_page());self.owner.fit()
        self.status.SetLabel('Inserted '+plan['ref']+' in one undo transaction. Double-click a reusable block to enter its native subcircuit.')

    def close(self,event):
        if self.busy:self.status.SetLabel('Wait for the bounded build to finish before closing.');event.Veto();return
        try:
            if not self.confirm_replace():event.Veto();return
        except Exception as exc:
            self.guard(lambda:(_ for _ in ()).throw(exc));event.Veto();return
        self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True)
        if self in getattr(self.owner,'component_makers',[]):self.owner.component_makers.remove(self)
        self.Destroy()


class PinMappingDialog(wx.Dialog):
    def __init__(self,parent,value,document):
        super().__init__(parent,title='Component pins → circuit nets',size=(550,520),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.result=None;self.fields={};box=wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(self,label='Map every public pin explicitly. Literal 0 inside SPICE models remains\nglobal ground. A compact block retains its native subcircuit internally.'),0,wx.ALL,8)
        page=wx.ScrolledWindow(self);page.SetScrollRate(0,16);grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=6);grid.AddGrowableCol(1)
        nets=sorted({n for p in document.data['components'] for n in p['nodes']})
        for pin in value['symbol']['terminals']:
            grid.Add(wx.StaticText(page,label=pin['id']+' · '+pin['name']),0,wx.ALIGN_CENTER_VERTICAL)
            field=wx.ComboBox(page,value='part_'+pin['name'],choices=nets);self.fields[pin['id']]=field;grid.Add(field,1,wx.EXPAND)
        page.SetSizer(grid);box.Add(page,1,wx.EXPAND|wx.ALL,10);self.error=wx.StaticText(self);box.Add(self.error,0,wx.ALL,8)
        box.Add(self.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALL,8);self.SetSizer(box)
        self.Bind(wx.EVT_BUTTON,self.accept,id=wx.ID_OK);apply_window(self,parent.palette)
    def accept(self,event):
        result={key:field.GetValue().strip() for key,field in self.fields.items()}
        if any(not packages.NODE.fullmatch(v) for v in result.values()):self.error.SetLabel('Choose valid SPICE net names for every pin.');return
        self.result=result;self.EndModal(wx.ID_OK)


def show(owner,value=None):
    frame=ComponentMaker(owner,value);frame.Show();return frame


def prepare_owner_close(owner):
    makers=[frame for frame in getattr(owner,'component_makers',[]) if frame and not frame.closed]
    for frame in makers:
        if frame.busy:
            frame.Raise();frame.status.SetLabel('Wait for the component build before closing Studio.');return False
        try:
            if not frame.confirm_replace():frame.Raise();return False
        except Exception as exc:frame.status.SetLabel(str(exc));frame.Raise();return False
    return True


def capture(owner,subsheet=False):
    if owner.job_running:raise ValueError('Stop the simulation before capturing a component')
    if owner.source.GetText()!=owner.doc.data['source']:raise ValueError('Apply circuit-text edits before capturing a component')
    with wx.TextEntryDialog(owner,'Reusable SUBCKT entry name','Make circuit into component','UserCircuit') as dialog:
        if dialog.ShowModal()!=wx.ID_OK:return
        name=dialog.GetValue().strip()
    from .component_capture import capture_selection,capture_subsheet
    if subsheet:
        path=getattr(owner.canvas,'sheet_scope',None)
        if not path:raise ValueError('Enter an existing subsheet first')
        result=capture_subsheet(owner.doc,path,name)
    else:
        from .reusable_block_projection import resolve_selection
        result=capture_selection(owner.doc,resolve_selection(owner.doc.data,owner.canvas.selected),name)
    value=packages.from_spice(result['source'],name);value['origin']=result['origin'];return show(owner,value)
