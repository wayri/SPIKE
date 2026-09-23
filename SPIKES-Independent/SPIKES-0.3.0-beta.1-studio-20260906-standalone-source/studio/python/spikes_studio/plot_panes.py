"""Persistent pane allocation; unlike-unit traces never share a single Y axis."""
import math

def default_layout():return {'mode':'units','panes':{},'heights':{}}

def validate_layout(layout):
    if layout['mode'] not in ('units','traces','custom'):raise ValueError('Unknown plot layout')
    if len(layout['panes'])>1024 or len(layout['heights'])>16:raise ValueError('Plot layout is too large')
    for expr,pane in layout['panes'].items():
        if not isinstance(expr,str) or len(expr)>8192 or isinstance(pane,bool) or not isinstance(pane,int) or not 1<=pane<=16:raise ValueError('Pane numbers must be 1..16')
    for key,value in layout['heights'].items():
        if key not in {str(i) for i in range(1,17)} or not isinstance(value,(int,float)) or not math.isfinite(value) or not .25<=value<=8:raise ValueError('Pane height weights must be 0.25..8')

def groups(traces,layout):
    validate_layout(layout);result={};units=list(dict.fromkeys(u for _,_,u in traces))
    for index,trace in enumerate(traces):
        name,_,unit=trace
        pane=units.index(unit)+1 if layout['mode']=='units' else index+1 if layout['mode']=='traces' else layout['panes'].get(name,units.index(unit)+1)
        if pane>16:raise ValueError('At most 16 visible plot panes; combine traces by unit')
        result.setdefault(pane,[]).append(trace)
    for pane,items in result.items():
        if len({v[2] for v in items})>1:raise ValueError(f'Pane {pane} combines different units; assign separate panes')
    return [(pane,items,float(layout['heights'].get(str(pane),1))) for pane,items in sorted(result.items())]

def edit_panes(owner):
    import wx
    import wx.grid
    from copy import deepcopy
    from .themes import apply_window
    with wx.Dialog(owner,title='Plot panes — linked time axes, independent Y axes',size=(780,530),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        box=wx.BoxSizer(wx.VERTICAL);layout=deepcopy(owner.doc.data['plot_layout'])
        mode=wx.Choice(dialog,choices=['Group by unit','One pane per trace','Custom pane assignments']);mode.SetSelection(('units','traces','custom').index(layout['mode']))
        box.Add(mode,0,wx.EXPAND|wx.ALL,10)
        box.Add(wx.StaticText(dialog,label='Assign the same pane to overlay like-unit traces. Separate panes share time and cursors. Height is a relative weight.'),0,wx.ALL,10)
        table=wx.grid.Grid(dialog);table.CreateGrid(len(owner.traces),4)
        for col,title in enumerate(('Expression','Unit','Pane (1–16)','Height (0.25–8)')):table.SetColLabelValue(col,title)
        units=list(dict.fromkeys(t[2] for t in owner.traces))
        for row,(name,_,unit) in enumerate(owner.traces):
            pane=layout['panes'].get(name,units.index(unit)+1)
            for col,value in enumerate((name,unit,str(pane),str(layout['heights'].get(str(pane),1)))):table.SetCellValue(row,col,value)
            table.SetReadOnly(row,0);table.SetReadOnly(row,1)
        table.SetColSize(0,330);table.SetColSize(1,75);table.SetColSize(2,120);table.SetColSize(3,140);box.Add(table,1,wx.EXPAND|wx.ALL,10)
        error=wx.StaticText(dialog,label='');box.Add(error,0,wx.ALL,10)
        row=wx.BoxSizer(wx.HORIZONTAL);cancel=wx.Button(dialog,label='Cancel');save=wx.Button(dialog,label='Apply layout')
        row.Add(cancel,0,wx.ALL,6);row.Add(save,0,wx.ALL,6);box.Add(row,0,wx.ALIGN_RIGHT)
        cancel.Bind(wx.EVT_BUTTON,lambda e:dialog.EndModal(wx.ID_CANCEL))
        def apply(event):
            try:
                table.SaveEditControlValue();new={'mode':('units','traces','custom')[mode.GetSelection()],'panes':{},'heights':{}}
                for r,(name,_,_) in enumerate(owner.traces):
                    pane=int(table.GetCellValue(r,2));height=float(table.GetCellValue(r,3));new['panes'][name]=pane
                    if str(pane) in new['heights'] and new['heights'][str(pane)]!=height:raise ValueError('Each pane must use one consistent height')
                    new['heights'][str(pane)]=height
                groups(owner.traces,new);owner.doc.commit(lambda data:data.__setitem__('plot_layout',new));owner.draw_plot();owner.update_title();dialog.EndModal(wx.ID_OK)
            except Exception as exc:error.SetLabel(str(exc));dialog.Layout()
        save.Bind(wx.EVT_BUTTON,apply);dialog.SetSizer(box);apply_window(dialog,owner.palette);dialog.ShowModal()
