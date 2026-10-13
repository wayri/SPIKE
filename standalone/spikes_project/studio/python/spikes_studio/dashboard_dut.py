# SPDX-License-Identifier: Apache-2.0
"""Data-only future DUT pin mappings. No debug adapter or GPIO is accessed."""
import wx
from .dashboard import update_widget


def edit_binding(panel):
    if panel.mode!='Design':raise ValueError('Switch to Design mode to edit mappings')
    row=panel.selected_row()
    if not row:raise ValueError('Select a diagram block, control or instrument first')
    current=row.get('dut_binding',{})
    with wx.Dialog(panel,title='DUT pin mapping - future integration',size=(530,430),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        root=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(dlg,label='Mapping only: hardware is disconnected. This does not read or write a GPIO.\nFuture adapters require explicit connection, arming and disconnect-safe behavior.')
        note.Wrap(490);root.Add(note,0,wx.ALL,12)
        form=wx.FlexGridSizer(cols=2,vgap=8,hgap=10);form.AddGrowableCol(1);fields={}
        for key,label in [('device','Device / debug adapter'),('connector','Connector (e.g. J1)'),('pin','Connector pin (e.g. 3)'),('gpio','MCU GPIO (e.g. PA5)')]:
            form.Add(wx.StaticText(dlg,label=label),0,wx.ALIGN_CENTER_VERTICAL)
            fields[key]=wx.TextCtrl(dlg,value=current.get(key,''));form.Add(fields[key],1,wx.EXPAND)
        direction=wx.Choice(dlg,choices=['Read','Write']);direction.SetStringSelection(current.get('direction','Read'))
        safe=wx.Choice(dlg,choices=['0','1']);safe.SetSelection(current.get('safe_value',0))
        for label,control in [('Direction',direction),('Requested disconnect-safe level',safe)]:form.Add(wx.StaticText(dlg,label=label),0,wx.ALIGN_CENTER_VERTICAL);form.Add(control,1,wx.EXPAND)
        root.Add(form,1,wx.EXPAND|wx.ALL,12)
        clear=wx.CheckBox(dlg,label='Remove mapping');root.Add(clear,0,wx.ALL,12)
        root.Add(dlg.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALIGN_RIGHT|wx.ALL,10);dlg.SetSizer(root)
        if dlg.ShowModal()!=wx.ID_OK:return
        binding=None if clear.GetValue() else dict({key:f.GetValue().strip() for key,f in fields.items()},direction=direction.GetStringSelection(),safe_value=safe.GetSelection())
        panel.commit(update_widget(panel.data(),row['id'],dut_binding=binding));panel.select(panel.selected_row())
