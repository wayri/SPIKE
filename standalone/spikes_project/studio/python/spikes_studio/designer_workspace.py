"""Tab-free workspace stack and draggable, explicit schematic tools."""
import json
import wx
from .fuzzy_search import ranked

class WorkspaceStack(wx.Simplebook):
    def SetSelection(self,index):
        tools=getattr(self,'floating_tools',None)
        if tools and index in tools.entries:
            tools.open(index);return self.GetSelection()
        previous=super().SetSelection(index)
        callback=getattr(self,'on_selection',None)
        if callback:callback(index)
        return previous

    def FindPage(self,page):
        tools=getattr(self,'floating_tools',None)
        index=tools.find_page(page) if tools else wx.NOT_FOUND
        return index if index!=wx.NOT_FOUND else super().FindPage(page)

ITEMS={
    'Power / grounds': [('Reference ground (node 0)',{'power_symbol':'reference_ground'}),('Signal ground (named net)',{'power_symbol':'signal_ground'}),('Chassis ground',{'power_symbol':'chassis_ground'}),('Protective earth',{'power_symbol':'earth_ground'}),('Power flag',{'power_symbol':'power_flag'})],
    'Components': [('Resistor',{'part':'part.resistor'}),('Capacitor',{'part':'part.capacitor'}),('Inductor',{'part':'part.inductor'}),('Diode',{'part':'part.diode'})],
    'Analysis / SPICE': [('Operating point',{'directive':'.op'}),('Transient',{'directive':'.tran 10u 5m uic'}),('AC sweep',{'directive':'.ac dec 20 1 1meg'}),('Parameter',{'directive':'.param gain=1'}),('Measurement',{'directive':'.measure tran avg_out AVG V(out) FROM=1m TO=5m'})],
    'Drawing': [('Note',{'annotation':'note'}),('Rectangle',{'annotation':'rect'}),('Ellipse',{'annotation':'ellipse'})],
}

class DesignerPalette(wx.TreeCtrl):
    def __init__(self,parent,owner):
        super().__init__(parent,style=wx.TR_HIDE_ROOT|wx.TR_HAS_BUTTONS|wx.TR_NO_LINES,size=(-1,205));self.owner=owner
        root=self.AddRoot('Designer')
        self.symbol_items=[]
        for group,items in ITEMS.items():
            branch=self.AppendItem(root,group)
            self.symbol_items.append((branch,'library'))
            for label,payload in items:
                item=self.AppendItem(branch,label);self.SetItemData(item,payload)
                key=payload.get('power_symbol') or payload.get('part','').replace('part.','') or payload.get('directive','').split()[0].lstrip('.') if 'annotation' not in payload else payload['annotation']
                self.symbol_items.append((item,key))
            self.Expand(branch)
        first,_=self.GetFirstChild(root)
        self.EnsureVisible(first)
        self.refresh_symbols(owner.palette)
        self.Bind(wx.EVT_TREE_BEGIN_DRAG,self.drag);self.Bind(wx.EVT_TREE_ITEM_ACTIVATED,self.activate)
        self.SetToolTip('Drag onto the schematic. Double-click arms placement. Analysis blocks open a reviewable directive editor.')

    def refresh_symbols(self,palette):
        from .symbol_icons import SymbolImages
        self.images=SymbolImages(None,palette);self.AssignImageList(self.images.image_list)
        for item,key in self.symbol_items:self.SetItemImage(item,self.images.index(key))
    def drag(self,event):
        payload=self.GetItemData(event.GetItem())
        if not payload:return
        source=wx.DropSource(self);source.SetData(wx.TextDataObject('SPIKES_TOOL:'+json.dumps(payload)));source.DoDragDrop(wx.Drag_CopyOnly)
    def activate(self,event):
        payload=self.GetItemData(event.GetItem())
        if payload:self.owner.guarded(lambda:self.owner.arm_designer_tool(payload))

class SchematicDropTarget(wx.TextDropTarget):
    def __init__(self,canvas):super().__init__();self.canvas=canvas
    def OnDropText(self,x,y,text):
        if not text.startswith('SPIKES_TOOL:') or len(text)>4096:return False
        try:payload=json.loads(text[len('SPIKES_TOOL:'):])
        except (ValueError,TypeError):return False
        if payload not in [p for items in ITEMS.values() for _,p in items]:return False
        self.canvas.owner.guarded(lambda:self.canvas.owner.place_designer_tool(payload,self.canvas.world(wx.Point(x,y))))
        return True


class NetNavigator(wx.Dialog):
    """Read-only connectivity cross-probing; geometry never defines a net."""
    def __init__(self, owner):
        super().__init__(owner, title='Schematic nets and pins', size=(780, 560),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.owner = owner
        self.SetMinSize((620, 400))
        self.rows = owner.doc.connectivity()
        self.visible = []
        box = wx.BoxSizer(wx.VERTICAL)
        self.search = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText('Find net, reference or pin')
        self.search.SetToolTip('Search electrical net names and connected component references')
        box.Add(self.search, 0, wx.EXPAND | wx.ALL, 8)
        self.nets = wx.Choice(self)
        box.Add(self.nets, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        self.summary = wx.StaticText(self)
        box.Add(self.summary, 0, wx.EXPAND | wx.ALL, 8)
        self.pins = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for index, (label, width) in enumerate((('Component', 180), ('Terminal index (1-based)', 180), ('Electrical net', 260))):
            self.pins.InsertColumn(index, label, width=width)
        self.pins.SetToolTip('Double-click a terminal row to locate its component on the schematic')
        box.Add(self.pins, 1, wx.EXPAND | wx.ALL, 8)
        controls = wx.BoxSizer(wx.HORIZONTAL)
        self.locate_button = wx.Button(self, label='Locate component')
        self.probe_button = wx.Button(self, label='Add voltage probe')
        self.clear_button = wx.Button(self, label='Clear highlight')
        close = wx.Button(self, wx.ID_CLOSE, 'Close')
        for control in (self.locate_button, self.probe_button, self.clear_button, close):
            controls.Add(control, 0, wx.ALL, 4)
        box.Add(controls, 0, wx.ALIGN_RIGHT | wx.ALL, 4)
        self.SetSizer(box)
        self.search.Bind(wx.EVT_TEXT, lambda event: self.filter())
        self.nets.Bind(wx.EVT_CHOICE, lambda event: self.select())
        self.pins.Bind(wx.EVT_LIST_ITEM_ACTIVATED, lambda event: self.locate())
        self.pins.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda event: self.locate_button.Enable(True))
        self.locate_button.Bind(wx.EVT_BUTTON, lambda event: self.locate())
        self.probe_button.Bind(wx.EVT_BUTTON, lambda event: owner.guarded(self.add_probe))
        self.clear_button.Bind(wx.EVT_BUTTON, lambda event: self.highlight(None))
        close.Bind(wx.EVT_BUTTON, lambda event: self.Close())
        self.Bind(wx.EVT_CLOSE, self.close)
        from .themes import apply_window
        apply_window(self, owner.palette)
        self.filter()

    def filter(self):
        self.visible = ranked(
            self.rows, self.search.GetValue(),
            text=lambda row: row['name']+' '+' '.join(
                pin['ref']+' '+str(pin['pin_index']+1) for pin in row['pins']))
        self.nets.Set([f"{row['name']} — {row['terminal_count']} terminals" for row in self.visible])
        self.nets.SetSelection(0 if self.visible else wx.NOT_FOUND)
        self.select()

    def select(self):
        index = self.nets.GetSelection()
        self.active = self.visible[index] if index != wx.NOT_FOUND else None
        self.pins.DeleteAllItems()
        self.locate_button.Enable(False)
        self.probe_button.Enable(self.active is not None)
        if self.active is None:
            self.summary.SetLabel('No matching electrical nets.');self.highlight(None);return
        for pin in self.active['pins']:
            item = self.pins.InsertItem(self.pins.GetItemCount(), pin['ref'])
            self.pins.SetItem(item, 1, str(pin['pin_index']+1))
            self.pins.SetItem(item, 2, pin['node'])
        self.summary.SetLabel(f"{self.active['terminal_count']} terminals; {len(self.active['wire_ids'])} drawn routes; "
                              f"{self.active['drawing_groups']} drawing groups. Named nets are electrically connected even without drawn routes.")
        self.summary.Wrap(max(250, self.GetClientSize().width-32))
        self.highlight(self.active['name'])

    def highlight(self, name):
        self.owner.canvas.highlighted_net = name
        self.owner.canvas.Refresh()

    def locate(self):
        index = self.pins.GetFirstSelected()
        if self.active is None or index < 0:return
        ident = self.active['pins'][index]['component_id']
        part = next((part for part in self.owner.doc.data['components'] if part['id'] == ident), None)
        if part is None:return
        canvas = self.owner.canvas
        self.owner.book.SetSelection(0)
        canvas.selected = {ident}
        width, height = canvas.GetClientSize()
        canvas.offset[:] = (width/2-part['x']*canvas.zoom, height/2-part['y']*canvas.zoom)
        canvas.Refresh();self.owner.refresh_inspector()

    def add_probe(self):
        if self.active is not None:
            self.owner.doc.add_probe('V('+self.active['name']+')')
            self.owner.refresh_document()

    def close(self, event):
        self.highlight(None)
        event.Skip()
