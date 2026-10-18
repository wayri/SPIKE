# SPDX-License-Identifier: Apache-2.0
"""Searchable controller pinout library and explicit sampled-adapter bindings."""
from copy import deepcopy
import wx
import wx.grid
from .themes import apply_window
from .controller_board_blocks import create,validate,controller_config,_bindable,allowed_modes
from .controller_board_canvas import geometry


class PinoutPreview(wx.ScrolledWindow):
    def __init__(self,parent,palette):
        super().__init__(parent);self.palette=palette;self.record=None
        self.SetScrollRate(12,12);self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT,self.paint)
        self.Bind(wx.EVT_SIZE,self.rescale)

    def load(self,record):
        self.record=record;self.rescale();self.Scroll(0,0)

    def rescale(self,event=None):
        if self.record:
            w,h,_=geometry(self.record)
            self.scale=min(1,max(.35,self.GetClientSize().width/(w+100)))
            self.SetVirtualSize((max(1,round((w+100)*self.scale)),round((h+45)*self.scale)))
            self.Refresh()
        if event:event.Skip()

    def paint(self,event):
        dc=wx.AutoBufferedPaintDC(self);self.PrepareDC(dc);p=self.palette
        dc.SetBackground(wx.Brush(p['canvas']));dc.Clear()
        if not self.record:return
        dc.SetUserScale(self.scale,self.scale)
        width,height,pins=geometry(self.record);x,y=45,15
        dc.SetPen(wx.Pen(p['fg'],2));dc.SetBrush(wx.Brush(p['panel']));dc.DrawRoundedRectangle(x,y,width,height,5)
        dc.SetTextForeground(p['fg']);dc.DrawText(self.record['name'],x+10,y+10)
        dc.SetTextForeground(p['muted']);dc.DrawText('Pinout preview · execution configured separately',x+10,y+30)
        for pin,side,row in pins:
            edge=x+width if side else x;end=edge+24 if side else edge-24
            dc.SetPen(wx.Pen(p['accent'] if _bindable(pin) else p['muted'],1));dc.DrawLine(edge,y+row,end,y+row)
            dc.SetBrush(wx.Brush(p['canvas']));dc.DrawCircle(end,y+row,3);dc.SetTextForeground(p['fg'])
            label=f"{pin['header']}.{pin['position']}  {pin['label']}"
            rect=wx.Rect(x+width//2+8 if side else x+8,y+row-8,width//2-16,20)
            dc.SetClippingRegion(rect);dc.DrawLabel(label,rect,wx.ALIGN_RIGHT if side else wx.ALIGN_LEFT);dc.DestroyClippingRegion()


class ControllerBoardDialog(wx.Dialog):
    def __init__(self,owner,block=None):
        super().__init__(owner,title='Controller board library — labeled pins',size=(1120,800),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        from .controller_boards import records
        self.owner=owner;self.existing=deepcopy(block);self.draft=None;self.adapter=None;self.result=None;self.firmware=False
        self.catalog=records();self.visible=[];self.rows=[]
        box=wx.BoxSizer(wx.VERTICAL);filters=wx.BoxSizer(wx.HORIZONTAL)
        self.search=wx.SearchCtrl(self);self.search.SetDescriptiveText('Search board, MCU, manufacturer or pin name (fuzzy)');filters.Add(self.search,1,wx.ALL,8)
        self.family=wx.Choice(self,choices=['All manufacturers',*sorted({r['manufacturer'] for r in self.catalog})]);self.family.SetSelection(0);filters.Add(self.family,0,wx.ALL,8)
        box.Add(filters,0,wx.EXPAND)
        self.split=wx.SplitterWindow(self,style=wx.SP_LIVE_UPDATE);self.split.SetMinimumPaneSize(220)
        self.list=wx.ListCtrl(self.split,style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
        for i,(name,width) in enumerate((('Board / revision',235),('MCU',145),('Pins',48))):self.list.InsertColumn(i,name,width=width)
        self.tabs=wx.Notebook(self.split);self.preview=PinoutPreview(self.tabs,owner.palette);self.tabs.AddPage(self.preview,'Pinout preview')
        self.grid=wx.grid.Grid(self.tabs);self.grid.CreateGrid(0,8)
        for i,(label,width) in enumerate((('Connector',105),('Pin label',100),('Mode',62),('Read node',100),('Reference',90),('Drive source',100),('High / envelope [V]',120),('Code identifier',180))):
            self.grid.SetColLabelValue(i,label);self.grid.SetColSize(i,width)
        self.grid.SetRowLabelSize(0);self.tabs.AddPage(self.grid,'Pins & sampled bindings')
        self.info=wx.TextCtrl(self.tabs,style=wx.TE_MULTILINE|wx.TE_READONLY);self.tabs.AddPage(self.info,'Scope & sources')
        self.split.SplitVertically(self.list,self.tabs,350);self.split.SetSashGravity(.30);box.Add(self.split,1,wx.EXPAND|wx.ALL,8)
        self.notice=wx.StaticText(self,label='');box.Add(self.notice,0,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        step=wx.BoxSizer(wx.HORIZONTAL);step.Add(wx.StaticText(self,label='Sample interval [s]'),0,wx.ALIGN_CENTER_VERTICAL|wx.ALL,6)
        self.step=wx.TextCtrl(self,value='100u');step.Add(self.step,0,wx.ALL,6)
        self.adapter_button=wx.Button(self,label='Load C/C++ sampled adapter…');self.adapter_button.Enable(block is not None)
        step.Add(self.adapter_button,0,wx.ALL,6);box.Add(step,0,wx.EXPAND)
        from .firmware_image import TARGETS
        self.firmware_button=wx.Button(self,label='Native firmware emulation…')
        self.firmware_button.Enable(block is not None and block['board']['id'] in TARGETS)
        self.firmware_button.SetToolTip('Explicit Renode backend for admitted nRF52840 / STM32F407 binaries only. Place the board first. No automatic CPU substitution.')
        self.firmware_button.Bind(wx.EVT_BUTTON,self.open_firmware);step.Add(self.firmware_button,0,wx.ALL,6)
        self.error=wx.StaticText(self,label='');box.Add(self.error,0,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        actions=wx.BoxSizer(wx.HORIZONTAL)
        export=wx.Button(self,label='Export board pinout…');export.Bind(wx.EVT_BUTTON,self.export);actions.Add(export,0,wx.ALL,6)
        actions.AddStretchSpacer();ok=wx.Button(self,wx.ID_OK,label='Apply pin bindings' if block else 'Place labeled block')
        ok.Bind(wx.EVT_BUTTON,self.accept);actions.Add(ok,0,wx.ALL,6);actions.Add(wx.Button(self,wx.ID_CANCEL),0,wx.ALL,6)
        box.Add(actions,0,wx.EXPAND|wx.ALL,6);self.SetSizer(box);self.SetMinSize((800,600))
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED,self.select);self.search.Bind(wx.EVT_TEXT,self.filter);self.family.Bind(wx.EVT_CHOICE,self.filter)
        self.adapter_button.Bind(wx.EVT_BUTTON,self.load_adapter)
        self.Bind(wx.EVT_SIZE,self.resize);self.filter()
        if block:
            selected=next((i for i,record in enumerate(self.visible) if record['id']==block['board']['id']),None)
            for row in range(self.list.GetItemCount()):self.list.Select(row,row==selected)
            if selected is not None:self.list.EnsureVisible(selected)
            self.search.Disable();self.family.Disable();self.list.Disable();self.load(block['board'],block)
        apply_window(self,owner.palette)
        wx.CallAfter(self.balance_panes)

    def balance_panes(self):
        if not self.IsBeingDeleted():self.split.SetSashPosition(round(self.split.GetClientSize().width*.36))

    def resize(self,event):
        if hasattr(self,'notice'):self.notice.Wrap(max(500,self.GetClientSize().width-24))
        event.Skip()

    def filter(self,event=None):
        from .fuzzy_search import ranked
        family=self.family.GetStringSelection()
        self.visible=ranked([r for r in self.catalog if family=='All manufacturers' or r['manufacturer']==family],self.search.GetValue(),
                            text=lambda r:' '.join([r['name'],r['manufacturer'],r['family'],r['mcu'],
                                                    *[p['label']+' '+p['header']+' '+' '.join(p.get('aliases',[])) for p in r['pins']]]))
        self.list.DeleteAllItems()
        for row,board in enumerate(self.visible):
            self.list.InsertItem(row,board['name']);self.list.SetItem(row,1,board['mcu']);self.list.SetItem(row,2,str(len(board['pins'])))
        if self.visible:self.list.Select(0);self.load(self.visible[0])
        else:self.draft=None;self.notice.SetLabel('No matching controller boards. Clear the search or manufacturer filter.')

    def select(self,event):
        if not self.existing:self.load(self.visible[event.GetIndex()])

    def load(self,record,block=None):
        self.draft=deepcopy(block) if block else create(record,0,0)
        self.rows=record['pins'];self.preview.load(record)
        count=self.grid.GetNumberRows()
        if count:self.grid.DeleteRows(0,count)
        self.grid.AppendRows(len(self.rows))
        for row,pin in enumerate(self.rows):
            binding=self.draft['bindings'][pin['id']]
            values=(f"{pin['header']}.{pin['position']}",pin['label'],binding['mode'],binding['node'],binding['reference'],binding['source'],str(binding['vdd']),binding['code_name'])
            for col,value in enumerate(values):self.grid.SetCellValue(row,col,value)
            for col in (0,1,7):self.grid.SetReadOnly(row,col)
            modes=list(allowed_modes(pin))
            self.grid.SetCellEditor(row,2,wx.grid.GridCellChoiceEditor(modes,False))
            if not _bindable(pin):
                for col in range(2,8):self.grid.SetReadOnly(row,col)
        scope=record.get('connector_scope','Declared headers only')
        from .firmware_image import TARGETS
        native='Separate native firmware manager available for this exact board (functional, not cycle accurate).' if record['id'] in TARGETS else 'Native firmware execution is unsupported for this exact board.'
        self.notice.SetLabel(f"{record['name']} · {record['revision']} · {scope}\nAll pins default unbound (NC). Power, reset and debug pins are visual only. Mapped AI/DI read circuit nodes; AO/DO drive existing DC voltage sources. {native}")
        self.notice.Wrap(max(500,self.GetClientSize().width-24))
        self.info.SetValue('\n'.join([record['name'],f"Manufacturer: {record['manufacturer']}",f"MCU: {record['mcu']}",f"Revision: {record['revision']}",f"Connector coverage: {scope}",
                                      'Execution: pinout template / optional generic sampled adapter.',native,
                                      'Power draw, pin protection, ADC quantization, buses, clocks and peripheral timing are not inferred.','',*record['source_urls'],'',
                                      *[f"{p['header']}.{p['position']}  {p['label']}  ({p['role']})  "+', '.join(p.get('aliases',[])) for p in self.rows]]))
        self.Layout()

    def configuration(self):
        if not self.draft:raise ValueError('Select a controller board')
        self.grid.SaveEditControlValue();self.grid.DisableCellEditControl();draft=deepcopy(self.draft)
        from python.spikes.netlist import parse_spice_number
        for row,pin in enumerate(self.rows):
            binding=draft['bindings'][pin['id']]
            for col,key in ((2,'mode'),(3,'node'),(4,'reference'),(5,'source')):binding[key]=self.grid.GetCellValue(row,col).strip()
            binding['vdd']=parse_spice_number(self.grid.GetCellValue(row,6).strip(),'scalar')
        validate([draft]);return draft

    def accept(self,event=None):
        try:self.result=self.configuration();self.EndModal(wx.ID_OK)
        except ValueError as exc:self.error.SetLabel(str(exc));self.Layout()

    def open_firmware(self,event=None):
        try:
            self.result=self.configuration();self.firmware=True;self.EndModal(wx.ID_OK)
        except ValueError as exc:self.error.SetLabel(str(exc));self.Layout()

    def load_adapter(self,event=None):
        try:
            if self.owner.job_running:raise ValueError('Stop simulation before changing a controller')
            from .part_properties import parse
            from python.spikes.netlist import parse_spice_number
            draft=self.configuration();config=controller_config(draft,parse(self.owner.doc.data['source']),parse_spice_number(self.step.GetValue(),'time'))
            previous=self.owner.doc.data.get('metadata',{}).get('controller_board_detached_drafts',{}).get(draft['id'])
            try:
                live=self.owner.controller_panel.config()
                if live.get('board_block_id')==draft['id']:previous=live
            except ValueError:pass
            if previous:
                for key in ('source','language','state_count'):config[key]=previous[key]
            if wx.MessageBox('Load a new sampled C adapter draft? This replaces the controller editor draft and clears code trust. It does not upload or execute firmware. Save any current controller code first.',
                             'Load sampled adapter',wx.OK|wx.CANCEL,self)!=wx.OK:return
            self.result=draft;self.adapter=config;self.EndModal(wx.ID_OK)
        except ValueError as exc:self.error.SetLabel(str(exc));self.Layout()

    def export(self,event=None):
        try:
            import json
            from pathlib import Path
            if not self.draft:raise ValueError('Select a board first')
            with wx.FileDialog(self,'Export board pinout',defaultFile=self.draft['board']['id']+'.spkboard',wildcard='Controller board pinout (*.spkboard)|*.spkboard',style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dialog:
                if dialog.ShowModal()==wx.ID_OK:Path(dialog.GetPath()).write_text(json.dumps(self.draft['board'],indent=2)+'\n',encoding='utf-8')
        except (ValueError,OSError) as exc:self.error.SetLabel(str(exc));self.Layout()


def show(owner,block=None):
    if owner.job_running:raise ValueError('Stop simulation before editing controller board blocks')
    with ControllerBoardDialog(owner,block) as dialog:
        if dialog.ShowModal()!=wx.ID_OK:return
        if block:
            from .controller_board_blocks import update
            changed=block['bindings']!=dialog.result['bindings']
            update(owner.doc,block['id'],dialog.result)
            if changed and owner.controller_panel.settings.data.get('board_block_id')==block['id']:
                panel=owner.controller_panel
                panel.enabled.SetValue(False);panel.trust.SetValue(False)
                if panel.compiled:panel.compiled.close();panel.compiled=None
                panel.log.SetValue('Board bindings changed. Previous code is retained as a draft, but the adapter is detached. Load the updated sampled adapter, review and explicitly trust/compile again.')
            owner.refresh_document()
        else:owner.canvas.board_tools.start(dialog.result)
        if dialog.adapter:
            owner.controller_panel.load_block(dialog.adapter);owner.tool_windows.open(12)
        if dialog.firmware:
            from .firmware_window import show as show_firmware
            show_firmware(owner,dialog.result)
