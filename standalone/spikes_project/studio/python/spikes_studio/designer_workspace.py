"""Tab-free workspace stack and draggable, explicit schematic tools."""
import json
import wx

class WorkspaceStack(wx.Simplebook):
    def SetSelection(self,index):
        previous=super().SetSelection(index)
        callback=getattr(self,'on_selection',None)
        if callback:callback(index)
        return previous

ITEMS={
    'Components': [('Resistor',{'part':'part.resistor'}),('Capacitor',{'part':'part.capacitor'}),('Inductor',{'part':'part.inductor'}),('Diode',{'part':'part.diode'})],
    'Analysis / SPICE': [('Operating point',{'directive':'.op'}),('Transient',{'directive':'.tran 10u 5m uic'}),('AC sweep',{'directive':'.ac dec 20 1 1meg'}),('Parameter',{'directive':'.param gain=1'}),('Measurement',{'directive':'.measure tran avg_out AVG V(out) FROM=1m TO=5m'})],
    'Drawing': [('Note',{'annotation':'note'}),('Rectangle',{'annotation':'rect'}),('Ellipse',{'annotation':'ellipse'})],
}

class DesignerPalette(wx.TreeCtrl):
    def __init__(self,parent,owner):
        super().__init__(parent,style=wx.TR_HIDE_ROOT|wx.TR_HAS_BUTTONS|wx.TR_NO_LINES,size=(-1,205));self.owner=owner
        root=self.AddRoot('Designer')
        for group,items in ITEMS.items():
            branch=self.AppendItem(root,group)
            for label,payload in items:self.SetItemData(self.AppendItem(branch,label),payload)
            self.Expand(branch)
        first,_=self.GetFirstChild(root)
        self.EnsureVisible(first)
        self.Bind(wx.EVT_TREE_BEGIN_DRAG,self.drag);self.Bind(wx.EVT_TREE_ITEM_ACTIVATED,self.activate)
        self.SetToolTip('Drag onto the schematic. Double-click arms placement. Analysis blocks open a reviewable directive editor.')
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
