"""Native directive editor and categorized source-backed manager."""
import wx
from .fuzzy_search import ranked
from .directives import GROUPS,group_for
from .directive_forms import SPEC_BY_KEY,SPECS,new_form,parse_directive

TEMPLATES={
    'Parameter':'.param gain=1',
    'Transient':'.tran 10u 5m uic',
    'Operating point':'.op',
    'Measure average':'.measure tran average_out AVG V(out) FROM=1m TO=5m',
    'Temperature':'.temp 25',
    'Initial voltage':'.ic V(out)=0',
    'Diode model':'.model rect D(IS=1p N=1)',
    'Custom / disabled draft':'.save V(out)',
}
TYPE_CHOICES=list(dict.fromkeys([spec.label for spec in SPECS]+list(TEMPLATES)+['Raw / other']))
TYPE_TO_KEY={spec.label:spec.key for spec in SPECS}
TYPE_TO_KEY.update({'Measure average':'measure','Initial voltage':'ic'})


def action(parent,label,fn,box):
    control=wx.Button(parent,label=label);control.Bind(wx.EVT_BUTTON,lambda e:fn())
    box.Add(control,0,wx.ALL,4);return control


class DirectiveEditor(wx.Dialog):
    def __init__(self,owner,ident=None,position=None):
        super().__init__(owner,title='SPICE directive — edit netlist and canvas annotation',size=(760,630),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.SetMinSize((620,500));self.owner=owner;self.ident=ident;self.position=position
        item=next((v for v in owner.doc.data['directives'] if v['id']==ident),None)
        self.item=item;box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(self,label='Enabled directives modify the actual circuit. Unsupported syntax is rejected. Disabled drafts are comments, not executable processing. One directive per item; use + for continuation lines.')
        note.Wrap(700);box.Add(note,0,wx.ALL,10)
        self.error=wx.InfoBar(self);box.Add(self.error,0,wx.EXPAND)
        row=wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self,label='Directive type'),0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        self.template=wx.Choice(self,choices=TYPE_CHOICES)
        row.Add(self.template,1,wx.ALL,4);box.Add(row,0,wx.EXPAND|wx.ALL,6)
        grid=wx.FlexGridSizer(cols=2,hgap=10,vgap=10);grid.AddGrowableCol(1,1)
        grid.Add(wx.StaticText(self,label='Group (or type your own)'),0,wx.ALIGN_CENTER_VERTICAL)
        self.group=wx.ComboBox(self,choices=list(GROUPS),value=item['group'] if item else 'Processing');grid.Add(self.group,1,wx.EXPAND)
        grid.Add(wx.StaticText(self,label='Annotation title'),0,wx.ALIGN_CENTER_VERTICAL)
        self.title=wx.TextCtrl(self,value=item['title'] if item else '');grid.Add(self.title,1,wx.EXPAND)
        box.Add(grid,0,wx.EXPAND|wx.ALL,10)
        self.tabs=wx.Notebook(self);self.form_page=wx.ScrolledWindow(self.tabs);self.form_page.SetScrollRate(0,10)
        self.form_box=wx.FlexGridSizer(cols=2,hgap=10,vgap=10);self.form_box.AddGrowableCol(1,1);self.form_page.SetSizer(self.form_box)
        raw=wx.Panel(self.tabs);raw_box=wx.BoxSizer(wx.VERTICAL)
        self.text=wx.TextCtrl(raw,value=item['text'] if item else TEMPLATES['Parameter'],style=wx.TE_MULTILINE|wx.TE_DONTWRAP)
        self.text.SetFont(wx.Font(11,wx.FONTFAMILY_TELETYPE,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL));raw_box.Add(self.text,1,wx.EXPAND|wx.ALL,8);raw.SetSizer(raw_box)
        self.tabs.AddPage(self.form_page,'Form');self.tabs.AddPage(raw,'Raw SPICE');box.Add(self.tabs,1,wx.EXPAND|wx.ALL,10)
        self.form=None;self.form_controls=[]
        parsed=parse_directive(self.text.GetValue())
        if parsed:
            self.template.SetStringSelection(parsed.spec.label);self.set_form(parsed)
        else:
            self.template.SetStringSelection('Raw / other');self.tabs.SetSelection(1);self.show_raw_reason()
        self.template.Bind(wx.EVT_CHOICE,self.type_changed);self.tabs.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED,self.page_changed)
        self.text.Bind(wx.EVT_TEXT,self.raw_edited)
        row=wx.BoxSizer(wx.HORIZONTAL)
        self.enabled=wx.CheckBox(self,label='Enabled in netlist');self.enabled.SetValue(item['enabled'] if item else True)
        self.visible=wx.CheckBox(self,label='Show on canvas');self.visible.SetValue(item['visible'] if item else True)
        row.Add(self.enabled,0,wx.ALL,8);row.Add(self.visible,0,wx.ALL,8);box.Add(row)
        hint=wx.StaticText(self,label='Simulation profile overrides can supersede .tran/.op/.temp at run time. Groups are organizational labels; they do not change execution order. Structural blocks remain in Circuit text.')
        hint.Wrap(700);box.Add(hint,0,wx.ALL,10)
        row=wx.BoxSizer(wx.HORIZONTAL);action(self,'Cancel',lambda:self.EndModal(wx.ID_CANCEL),row)
        self.apply_button=action(self,'Validate & apply',self.apply,row);box.Add(row,0,wx.ALIGN_RIGHT|wx.ALL,6);self.SetSizer(box)
        from .themes import apply_window
        apply_window(self,owner.palette)
        def resize(event):
            width=max(300,self.GetClientSize().width-32)
            note.Wrap(width);hint.Wrap(width);self.Layout();event.Skip()
        self.Bind(wx.EVT_SIZE,resize)

    def use_template(self):
        name=self.template.GetStringSelection()
        if name=='Raw / other':self.tabs.SetSelection(1);return
        key=TYPE_TO_KEY.get(name)
        if key:
            self.set_form(new_form(key));text=self.form.render();self.tabs.SetSelection(0)
        else:
            text=TEMPLATES[name];self.tabs.SetSelection(1)
        self.text.SetValue(text);self.group.SetValue(group_for(text));self.enabled.SetValue(name!='Custom / disabled draft')

    def type_changed(self,event=None):self.use_template()

    def show_raw_reason(self):
        self.form_box.Clear(True)
        message=wx.StaticText(self.form_page,label='This directive is not safely representable as labeled fields. Edit it on the Raw SPICE tab; its text will not be rewritten.')
        message.Wrap(620);self.form_box.Add(message,0,wx.ALL,8);self.form_page.Layout()

    def set_form(self,form):
        self.form=form;self.form_controls=[];self.form_box.Clear(True)
        if not form.spec.fields:
            self.form_box.Add(wx.StaticText(self.form_page,label='This directive has no parameters.'),0,wx.ALL,8)
        for label,value in zip(form.spec.fields,form.values):
            self.form_box.Add(wx.StaticText(self.form_page,label=label),0,wx.ALIGN_CENTER_VERTICAL|wx.ALL,4)
            control=wx.TextCtrl(self.form_page,value=value);control.Bind(wx.EVT_TEXT,self.form_edited)
            self.form_box.Add(control,1,wx.EXPAND|wx.ALL,4);self.form_controls.append(control)
        self.form_page.Layout();self.form_page.FitInside()

    def form_edited(self,event=None):
        if self.form:
            self.form.values=[control.GetValue() for control in self.form_controls]
            try:self.text.ChangeValue(self.form.render())
            except ValueError:pass
        if event:event.Skip()

    def page_changed(self,event):
        if event.GetSelection()==0:
            parsed=parse_directive(self.text.GetValue())
            if parsed:
                self.template.SetStringSelection(parsed.spec.label);self.set_form(parsed)
            else:
                self.template.SetStringSelection('Raw / other');self.show_raw_reason();wx.CallAfter(self.tabs.SetSelection,1)
        event.Skip()

    def raw_edited(self,event):
        if self.tabs.GetSelection()==0:
            parsed=parse_directive(self.text.GetValue())
            if parsed:self.template.SetStringSelection(parsed.spec.label);self.set_form(parsed)
            else:self.form=None;self.show_raw_reason();self.template.SetStringSelection('Raw / other');self.tabs.SetSelection(1)
        event.Skip()

    def apply(self):
        try:
            self.owner.require_clean_directive_source()
            if self.tabs.GetSelection()==0 and self.form:
                self.form.values=[control.GetValue() for control in self.form_controls]
                self.text.SetValue(self.form.render())
            coordinates={} if self.position is None else dict(zip(('x','y'),map(float,self.position)))
            self.ident=self.owner.doc.edit_directive(self.ident,text=self.text.GetValue(),enabled=self.enabled.GetValue(),
                group=self.group.GetValue(),title=self.title.GetValue(),visible=self.visible.GetValue(),**coordinates)
            self.owner.refresh_document();self.owner.canvas.selected_directive=self.ident
            self.EndModal(wx.ID_OK)
        except Exception as exc:self.last_error=str(exc);self.error.ShowMessage(str(exc),wx.ICON_ERROR);self.Layout()


class DirectiveManager(wx.Panel):
    def __init__(self,owner,parent):
        super().__init__(parent);self.owner=owner;self.ids=[];self.signature=None
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(self,label='SPICE directives — source order is preserved. Group/filter directives without changing their electrical meaning.')
        box.Add(note,0,wx.ALL,10)
        row=wx.BoxSizer(wx.HORIZONTAL)
        self.group_filter=wx.Choice(self,choices=['All groups',*GROUPS]);self.group_filter.SetSelection(0)
        row.Add(self.group_filter,0,wx.ALL,4);self.group_filter.Bind(wx.EVT_CHOICE,lambda e:self.refresh(force=True))
        self.search=wx.SearchCtrl(self);row.Add(self.search,1,wx.ALL|wx.EXPAND,4);self.search.Bind(wx.EVT_TEXT,lambda e:self.refresh(force=True))
        action(self,'Add directive…',lambda:owner.guarded(owner.edit_directive),row)
        action(self,'Edit…',lambda:owner.guarded(self.edit),row);box.Add(row,0,wx.EXPAND)
        self.rows=wx.ListCtrl(self,style=wx.LC_REPORT)
        for i,(label,width) in enumerate((('Group',140),('State',85),('Canvas',65),('Line',50),('Title',150),('Directive',450))):self.rows.InsertColumn(i,label,width=width)
        self.rows.Bind(wx.EVT_LIST_ITEM_SELECTED,lambda e:self.preview_selection())
        self.rows.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda e:owner.guarded(self.edit))
        box.Add(self.rows,1,wx.EXPAND|wx.ALL,8)
        self.preview=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,150));box.Add(self.preview,0,wx.EXPAND|wx.ALL,8)
        row=wx.WrapSizer(wx.HORIZONTAL)
        self.group_target=wx.ComboBox(self,choices=list(GROUPS),value='Observations');row.Add(self.group_target,0,wx.ALL,4)
        action(self,'Move selected to group',lambda:owner.guarded(lambda:self.organize(group=self.group_target.GetValue())),row)
        action(self,'Show on canvas',lambda:owner.guarded(lambda:self.organize(visible=True)),row)
        action(self,'Hide on canvas',lambda:owner.guarded(lambda:self.organize(visible=False)),row)
        action(self,'Enable',lambda:owner.guarded(lambda:self.enable(True)),row)
        action(self,'Disable',lambda:owner.guarded(lambda:self.enable(False)),row)
        action(self,'Locate on canvas',lambda:owner.guarded(self.locate),row)
        action(self,'Delete selected…',lambda:owner.guarded(self.delete),row)
        action(self,'Circuit text',lambda:owner.book.SetSelection(2),row)
        box.Add(row,0,wx.EXPAND|wx.ALL,4)
        note=wx.StaticText(self,label='Select multiple rows for grouping, visibility or deletion. .measure runs after native batch capture (sample-weighted AVG/RMS). Continuous does not execute .measure/.step; .step batch sweeps are also unsupported here. Structural blocks stay in Circuit text.')
        note.Wrap(880);box.Add(note,0,wx.ALL,10);self.SetSizer(box)

    def selected(self):
        result=[];index=self.rows.GetFirstSelected()
        while index!=-1:
            if index<len(self.ids):result.append(self.ids[index])
            index=self.rows.GetNextSelected(index)
        return result

    def refresh(self,force=False):
        items=self.owner.doc.data['directives'];signature=repr(items)
        if signature==self.signature and not force:return
        self.signature=signature;selected=self.selected();group=self.group_filter.GetStringSelection()
        groups=list(dict.fromkeys([*GROUPS,*[v['group'] for v in items]]))
        self.group_filter.Set(['All groups',*groups]);self.group_filter.SetStringSelection(group if group in groups else 'All groups')
        group=self.group_filter.GetStringSelection()
        visible=ranked(
            [item for item in items if group=='All groups' or item['group']==group],
            self.search.GetValue(),text=lambda item:item['text']+' '+item['title']+' '+item['group'])
        self.rows.Freeze();self.rows.DeleteAllItems();self.ids=[]
        for item in visible:
            self.ids.append(item['id']);index=self.rows.InsertItem(self.rows.GetItemCount(),item['group'])
            for col,value in enumerate(('Enabled' if item['enabled'] else 'Draft / off','Yes' if item['visible'] else 'No',str(item['line']),item['title'],item['text'].replace('\n',' ')),1):self.rows.SetItem(index,col,value)
            if item['id'] in selected:self.rows.Select(index)
        self.rows.Thaw();self.preview_selection()

    def preview_selection(self):
        ids=self.selected();items=[v for v in self.owner.doc.data['directives'] if v['id'] in ids]
        self.preview.SetValue('\n\n'.join(f"{v['group']} · line {v['line']} · {'enabled' if v['enabled'] else 'disabled comment'}\n{v['text']}" for v in items))

    def one(self):
        ids=self.selected()
        if len(ids)!=1:raise ValueError('Select exactly one directive')
        return ids[0]

    def edit(self):self.owner.edit_directive(self.one())

    def organize(self,**changes):
        self.owner.doc.organize_directives(self.selected(),**changes);self.owner.refresh_document()

    def enable(self,enabled):
        self.owner.require_clean_directive_source()
        self.owner.doc.enable_directives(self.selected(),enabled);self.owner.refresh_document()

    def locate(self):
        ident=self.one();item=next(v for v in self.owner.doc.data['directives'] if v['id']==ident)
        self.owner.doc.organize_directives([ident],visible=True)
        canvas=self.owner.canvas;canvas.selected_directive=ident;canvas.selected.clear()
        canvas.offset[:]=[80-item['x']*canvas.zoom,100-item['y']*canvas.zoom]
        self.owner.refresh_document();self.owner.book.SetSelection(0)

    def delete(self):
        ids=self.selected()
        if not ids:raise ValueError('Select directives to delete')
        self.owner.require_clean_directive_source()
        if wx.MessageBox(f'Delete {len(ids)} directive(s) from the netlist? This can be undone.','Delete directives',wx.YES_NO|wx.NO_DEFAULT,self)!=wx.YES:return
        self.owner.doc.remove_directives(ids);self.owner.refresh_document()
