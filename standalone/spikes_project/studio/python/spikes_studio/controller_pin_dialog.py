"""Pin-property grid for the existing trusted sampled C/C++ bridge."""
from copy import deepcopy
import json
import wx
import wx.grid
from .controller_block import validate
from .themes import apply_window


def edit_pins(panel):
    if panel.owner.job_running:raise ValueError('Stop the active job before editing pins')
    config=deepcopy(panel.config());keys=('name','mode','node','reference','source','vdd')
    with wx.Dialog(panel,title='Programmable block pin properties',size=(860,510),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        box=wx.BoxSizer(wx.VERTICAL)
        box.Add(wx.StaticText(dlg,label='AI/DI read nodes; AO/DO drive an existing voltage source. Access inputs[IN_name] / outputs[OUT_name].\nChanges invalidate the compiled setup; compile again with explicit trust. Verilog co-simulation is not connected.'),0,wx.ALL,8)
        grid=wx.grid.Grid(dlg);grid.CreateGrid(len(config['pins']),len(keys))
        for c,key in enumerate(keys):grid.SetColLabelValue(c,key);grid.SetColSize(c,125)
        for r,pin in enumerate(config['pins']):
            for c,key in enumerate(keys):grid.SetCellValue(r,c,str(pin[key]))
        box.Add(grid,1,wx.EXPAND|wx.ALL,8);row=wx.BoxSizer(wx.HORIZONTAL)
        def add(event):
            if grid.GetNumberRows()>=64:return
            grid.AppendRows();r=grid.GetNumberRows()-1
            for c,value in enumerate((f'pin{r+1}','AI','out','0','','3.3')):grid.SetCellValue(r,c,value)
        def remove(event):
            if grid.GetNumberRows()>2:grid.DeleteRows(max(0,grid.GetGridCursorRow()))
        for label,fn in [('Add pin',add),('Remove current row',remove)]:
            b=wx.Button(dlg,label=label);b.Bind(wx.EVT_BUTTON,fn);row.Add(b,0,wx.ALL,4)
        box.Add(row);error=wx.StaticText(dlg,label='');box.Add(error,0,wx.ALL,8);box.Add(dlg.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALL,8)
        def accept(event):
            try:
                grid.SaveEditControlValue();pins=[]
                for r in range(grid.GetNumberRows()):
                    pin={key:grid.GetCellValue(r,c).strip() for c,key in enumerate(keys)};pin['vdd']=float(pin['vdd']);pins.append(pin)
                config['pins']=pins;validate(config);dlg.EndModal(wx.ID_OK)
            except Exception as exc:error.SetLabel(str(exc))
        dlg.Bind(wx.EVT_BUTTON,accept,id=wx.ID_OK);dlg.SetSizer(box);apply_window(dlg,panel.owner.palette)
        if dlg.ShowModal()!=wx.ID_OK:return
    panel.owner.doc.commit(lambda d:d.update(controller_setup=config));settings=deepcopy(config);settings.pop('source');panel.settings.SetValue(json.dumps(settings,indent=2));panel.owner.update_title()
