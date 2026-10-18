# SPDX-License-Identifier: Apache-2.0
"""Native compact quick-insert palette at a clicked schematic coordinate."""
from copy import deepcopy
import wx
from .quick_insert import suggestions
from .themes import apply_window
from .flat_controls import ActionButton


def insert_component(owner,record,position):
    from .component_panel import InsertDialog
    with InsertDialog(owner.catalog_panel,record) as dialog:
        dialog.place.SetLabel('Place at the clicked search location');dialog.place.SetValue(True);dialog.place.Disable()
        manufacturer=record.get('_manufacturer_record')
        if manufacturer:
            index=next((i for i,r in enumerate(dialog.library_rows) if r and r['id']==manufacturer['id']),None)
            if index is None:raise ValueError('Exact library model is no longer available')
            dialog.part_choice.SetSelection(index);dialog.select_library()
        if dialog.ShowModal()!=wx.ID_OK:return
        chosen=dialog.edited_record();mapping={p:c.GetValue() for p,c in dialog.pins.items()}
        owner.catalog_panel.insert_recipe(chosen,mapping,count=dialog.count.GetValue(),position=position)


def insert_monitor(owner,kind,position,initial_expression=None):
    parts=owner.canvas.visible_parts()
    if not parts:raise ValueError('Place a circuit component before adding a monitoring block')
    choices={}
    for part in parts:
        for index,node in enumerate(part['nodes']):choices.setdefault(f'V({node})',(part['id'],index))
        choices[f'I({part["ref"]})']=(part['id'],None);choices[f'P({part["ref"]})']=(part['id'],None)
    prefix='I(' if kind=='Current meter' else 'P(' if kind=='Power meter' else 'V('
    names=sorted(choices,key=lambda name:(not name.startswith(prefix),name=='V(0)',name.casefold()))
    with wx.Dialog(owner,title='Bind '+kind,size=(470,220)) as dialog:
        root=wx.BoxSizer(wx.VERTICAL);root.Add(wx.StaticText(dialog,label='Signal / expression (actual circuit names; no demo values)'),0,wx.ALL,12)
        expression=wx.ComboBox(dialog,value=initial_expression or names[0],choices=names);root.Add(expression,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        expression.SetName('Monitoring expression')
        root.Add(dialog.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALIGN_RIGHT|wx.ALL,12);dialog.SetSizer(root)
        if dialog.ShowModal()!=wx.ID_OK:return
        text=expression.GetValue().strip()
        if not text:raise ValueError('Enter a monitoring expression')
        anchor,index=choices.get(text,(parts[0]['id'],None))
    import uuid
    item=dict(id=uuid.uuid4().hex,anchor=anchor,pin_index=index,expression=text,kind='Mini plot' if kind=='Mini scope' else 'Readout',source='Selected run',format='Engineering',frequency_hz=1000.,x=float(position[0]),y=float(position[1]))
    owner.doc.commit(lambda d:d['instruments'].append(item));owner.refresh_document()


class QuickInsert(wx.PopupTransientWindow):
    def __init__(self,owner,position):
        super().__init__(owner,wx.BORDER_SIMPLE);self.owner=owner;self.position=tuple(map(float,position));self.rows=[]
        from .discovery_index import DiscoveryIndex,manufacturer_text
        self.component_index=DiscoveryIndex(owner.catalog_panel.catalog['records'])
        self.manufacturer_index=DiscoveryIndex(owner.manufacturer_panel.catalog['records'],manufacturer_text)
        self.closed=False
        panel=wx.Panel(self);root=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(root)
        heading=wx.BoxSizer(wx.HORIZONTAL)
        title=wx.StaticText(panel,label='Insert into schematic');title.SetFont(title.GetFont().Bold())
        heading.Add(title,1,wx.ALIGN_CENTER_VERTICAL)
        library=ActionButton(panel,label='Full library');library.SetToolTip('Browse every preset, edit values and inspect model availability')
        library.Bind(wx.EVT_BUTTON,self.open_library);heading.Add(library,0)
        root.Add(heading,0,wx.EXPAND|wx.ALL,10)
        row=wx.BoxSizer(wx.HORIZONTAL)
        self.query=wx.SearchCtrl(panel,style=wx.TE_PROCESS_ENTER);self.query.SetDescriptiveText('Find a part, monitor, text or .SPICE directive');self.query.ShowCancelButton(True)
        self.category=wx.Choice(panel,choices=['All','Components','Circuit-ready','Favorites','Recent','Bench only','Monitors','Text','SPICE',*owner.catalog_panel.catalog['counts']]);self.category.SetSelection(0);self.category.SetName('Insert collection')
        row.Add(self.query,1);root.Add(row,0,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        collections=wx.BoxSizer(wx.HORIZONTAL);collections.Add(self.category,0,wx.RIGHT,8)
        self.count_label=wx.StaticText(panel,label='');collections.Add(self.count_label,1,wx.ALIGN_CENTER_VERTICAL)
        root.Add(collections,0,wx.EXPAND|wx.ALL,10)
        self.list=wx.ListCtrl(panel,style=wx.LC_REPORT|wx.LC_SINGLE_SEL|wx.LC_NO_HEADER,size=(590,240))
        self.list.InsertColumn(0,'Action',width=335);self.list.InsertColumn(1,'Availability',width=235)
        from .symbol_icons import SymbolImages
        self.images=SymbolImages(None,owner.palette);self.list.AssignImageList(self.images.image_list,wx.IMAGE_LIST_SMALL)
        root.Add(self.list,1,wx.EXPAND|wx.LEFT|wx.RIGHT,8)
        self.hint=wx.StaticText(panel,label='Up/Down selects · Tab completes · Enter adds · Escape cancels')
        self.hint.Wrap(590);root.Add(self.hint,0,wx.EXPAND|wx.ALL,8)
        layout=wx.BoxSizer(wx.VERTICAL);layout.Add(panel,1,wx.EXPAND);self.SetSizer(layout);self.SetSize((620,440))
        self.query.Bind(wx.EVT_TEXT,self.refresh);self.category.Bind(wx.EVT_CHOICE,self.refresh)
        self.query.Bind(wx.EVT_TEXT_ENTER,self.accept);self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED,self.accept)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED,self.selected)
        self.query.Bind(wx.EVT_KEY_DOWN,self.key);self.list.Bind(wx.EVT_KEY_DOWN,self.key)
        self.query.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN,lambda e:self.close())
        apply_window(self,owner.palette);self.refresh()

    def refresh(self,event=None):
        parts=self.owner.canvas.visible_parts();nets=[n for p in parts for n in p['nodes']];refs=[p['ref'] for p in parts]
        selected=self.list.GetFirstSelected()
        previous=(self.rows[selected]['kind'],self.rows[selected]['payload']) if 0<=selected<len(self.rows) else None
        preferences=self.owner.catalog_panel.preferences()
        self.rows=suggestions(self.query.GetValue(),self.owner.catalog_panel.catalog['records'],self.owner.manufacturer_panel.catalog['records'],nets,refs,self.category.GetStringSelection(),favorites=preferences.get('favorites',()),recent=preferences.get('recent',()),component_index=self.component_index,manufacturer_index=self.manufacturer_index)
        self.list.DeleteAllItems()
        for row in self.rows:
            index=self.list.InsertItem(self.list.GetItemCount(),row['label'],self.images.index(row['icon']));self.list.SetItem(index,1,row['detail'])
        if self.rows:
            selected=next((i for i,row in enumerate(self.rows) if (row['kind'],row['payload'])==previous),0)
            self.list.SetItemState(selected,wx.LIST_STATE_SELECTED,wx.LIST_STATE_SELECTED);self.list.EnsureVisible(selected)
            self.count_label.SetLabel(f'{len(self.rows)} suggestions - type to narrow')
            self.selected()
        else:
            self.count_label.SetLabel('No matching items')
            self.hint.SetLabel('Try another collection or search term. Favorites and recent inserts belong to this project.');self.hint.Wrap(590)
        self.Layout()

    def open_library(self,event=None):
        owner=self.owner;query=self.query.GetValue();self.close()
        def browse():
            owner.execute_command('view.component_catalog')
            owner.catalog_panel.reset_filters();owner.catalog_panel.search.SetValue(query)
            owner.catalog_panel.search.SetFocus()
        wx.CallAfter(lambda:owner.guarded(browse))

    def key(self,event):
        code=event.GetKeyCode()
        if code==wx.WXK_ESCAPE:self.close();return
        if code in (wx.WXK_UP,wx.WXK_DOWN,wx.WXK_PAGEUP,wx.WXK_PAGEDOWN):
            step={wx.WXK_UP:-1,wx.WXK_DOWN:1,wx.WXK_PAGEUP:-8,wx.WXK_PAGEDOWN:8}[code]
            index=self.list.GetFirstSelected();index=max(0,min(len(self.rows)-1,index+step))
            if self.rows:
                self.list.SetItemState(index,wx.LIST_STATE_SELECTED,wx.LIST_STATE_SELECTED);self.list.EnsureVisible(index)
            return
        if code==wx.WXK_TAB:
            index=self.list.GetFirstSelected()
            if index>=0 and self.rows[index]['completion']:self.query.SetValue(self.rows[index]['payload']);self.query.SetInsertionPointEnd();return
        if code in (wx.WXK_RETURN,wx.WXK_NUMPAD_ENTER):self.accept();return
        event.Skip()

    def selected(self,event=None):
        index=self.list.GetFirstSelected()
        detail=self.rows[index]['detail'] if 0<=index<len(self.rows) else ''
        self.hint.SetLabel(detail+'\nUp/Down selects · Tab completes · Enter adds · Escape cancels');self.hint.Wrap(590);self.Layout()

    def close(self):
        if self.closed:return
        self.closed=True
        self.Dismiss();self.owner.quick_insert_popup=None;self.Destroy()

    def OnDismiss(self):
        if not self.closed:
            self.closed=True;self.owner.quick_insert_popup=None
            wx.CallAfter(lambda:self.Destroy() if self else None)

    def accept(self,event=None):
        index=self.list.GetFirstSelected()
        if not 0<=index<len(self.rows):return
        row=deepcopy(self.rows[index]);kind=row['kind'];payload=row['payload'];owner=self.owner;position=self.position
        if row['completion']:
            self.query.SetValue(payload);self.query.SetInsertionPointEnd();return
        try:
            owner.require_clean_directive_source()
            if owner.job_running:raise ValueError('Stop simulation before placing items')
            if kind=='text':
                owner.doc.edit_annotation(x=position[0],y=position[1],text=payload,width=240,height=80);owner.refresh_document();self.close();return
            if kind=='spice':
                from .canvas_text import place
                place(owner.doc,payload,position);owner.refresh_document(force_source=True);self.close();return
            if kind in ('component','manufacturer'):
                if getattr(owner.canvas,'sheet_scope',None):raise ValueError('Component insertion into shared subsheet definitions requires Circuit text; switch to Flat view for top-level placement.')
                if kind=='component':record=owner.catalog_panel.index.by_id[payload]
                else:
                    from .manufacturer_parts import as_component_record
                    original=next(r for r in owner.manufacturer_panel.catalog['records'] if r['id']==payload)
                    record=as_component_record(original);record['_manufacturer_record']=deepcopy(original)
                self.close();wx.CallAfter(lambda:owner.guarded(lambda:insert_component(owner,record,position)));return
            if kind=='monitor':self.close();wx.CallAfter(lambda:owner.guarded(lambda:insert_monitor(owner,payload,position,row.get('expression'))));return
            if kind=='manufacturer_review':
                mpn=next(r['mpn'] for r in owner.manufacturer_panel.catalog['records'] if r['id']==payload)
                self.close();wx.CallAfter(lambda:owner.guarded(lambda:(owner.show_manufacturer_parts(),owner.manufacturer_panel.search.SetValue(mpn))));return
            elif kind=='review':
                self.close();wx.CallAfter(lambda:owner.guarded(lambda:(owner.execute_command('view.component_catalog'),owner.catalog_panel.search.ChangeValue('id:'+payload),owner.catalog_panel.filter())));return
        except Exception as error:
            if self.closed:owner.report_error(error)
            else:self.hint.SetLabel(str(error));self.hint.Wrap(590);self.Layout()


def show(owner,position,screen_position):
    existing=getattr(owner,'quick_insert_popup',None)
    if existing:
        try:existing.close()
        except RuntimeError:owner.quick_insert_popup=None
    owner.canvas.capture_lost();owner.canvas.wire_mode=False;owner.canvas.wire_start=None;owner.canvas.wire_corners=[]
    owner.canvas.label_mode=False;owner.canvas.designer_tool=None;owner.canvas.plot_drop=None;owner.canvas.probe_mode=None
    owner.pending_library_placement=None;owner.canvas.SetCursor(wx.NullCursor)
    popup=QuickInsert(owner,position);owner.quick_insert_popup=popup
    popup.Position(screen_position,(0,0));popup.Popup(popup.query);popup.query.SetFocus()
    return popup
