"""Native directive editor and categorized source-backed manager."""
import wx
from .directives import GROUPS,group_for

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
        self.template=wx.Choice(self,choices=list(TEMPLATES));self.template.SetSelection(0)
        row.Add(self.template,1,wx.ALL,4);action(self,'Insert template',self.use_template,row);box.Add(row,0,wx.EXPAND|wx.ALL,6)
        grid=wx.FlexGridSizer(cols=2,hgap=10,vgap=10);grid.AddGrowableCol(1,1)
        grid.Add(wx.StaticText(self,label='Group (or type your own)'),0,wx.ALIGN_CENTER_VERTICAL)
        self.group=wx.ComboBox(self,choices=list(GROUPS),value=item['group'] if item else 'Processing');grid.Add(self.group,1,wx.EXPAND)
        grid.Add(wx.StaticText(self,label='Annotation title'),0,wx.ALIGN_CENTER_VERTICAL)
        self.title=wx.TextCtrl(self,value=item['title'] if item else '');grid.Add(self.title,1,wx.EXPAND)
        box.Add(grid,0,wx.EXPAND|wx.ALL,10)
        self.text=wx.TextCtrl(self,value=item['text'] if item else TEMPLATES['Parameter'],style=wx.TE_MULTILINE|wx.TE_DONTWRAP)
        self.text.SetFont(wx.Font(11,wx.FONTFAMILY_TELETYPE,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL));box.Add(self.text,1,wx.EXPAND|wx.ALL,10)
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

    def use_template(self):
        name=self.template.GetStringSelection();text=TEMPLATES[name]
        self.text.SetValue(text);self.group.SetValue(group_for(text));self.enabled.SetValue(name!='Custom / disabled draft')

    def apply(self):
        try:
            self.owner.require_clean_directive_source()
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
        group=self.group_filter.GetStringSelection();needle=self.search.GetValue().lower()
        self.rows.Freeze();self.rows.DeleteAllItems();self.ids=[]
        for item in items:
            if group!='All groups' and item['group']!=group:continue
            if needle not in (item['text']+' '+item['title']+' '+item['group']).lower():continue
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
