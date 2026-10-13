# SPDX-License-Identifier: Apache-2.0
"""Floating derived-analysis plots bound to one retained run snapshot."""
from concurrent.futures import ThreadPoolExecutor
import wx
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg, NavigationToolbar2WxAgg
from .analysis_plots import VIEWS, derive, render, describe
from .themes import apply_window, figure_theme
from .flat_controls import ActionButton


class AnalysisPlotWindow(wx.Frame):
    def __init__(self,owner):
        if owner.math is None:raise ValueError('Run or load recorded time data first')
        run=getattr(owner,'selected_run',0)+1
        super().__init__(owner,title=f'Analysis plots - captured Run {run}',size=(1040,720))
        self.SetMinSize((760,560));self.owner=owner;self.engine=owner.math
        self.closed=False;self.busy=False;self.executor=ThreadPoolExecutor(max_workers=1)
        panel=wx.Panel(self);box=wx.BoxSizer(wx.VERTICAL);panel.SetSizer(box)
        box.Add(wx.StaticText(panel,label=f'Captured Run {run} | recorded samples only | no model qualification or live-state ownership'),0,wx.ALL,8)
        self.view=wx.Choice(panel,choices=list(VIEWS));self.view.SetSelection(0)
        box.Add(self.view,0,wx.EXPAND|wx.LEFT|wx.RIGHT,8)
        grid=wx.FlexGridSizer(cols=4,hgap=8,vgap=6);grid.AddGrowableCol(1);grid.AddGrowableCol(3)
        self.fields={}
        initial=owner.expression.GetValue() if hasattr(owner,'expression') else next(iter(owner.math.signals))
        for key,label,value in [('signal','Y / signal expression',initial),('x','X expression (XY)','t'),
                                ('start','Start time [s]',''),('stop','Stop time [s]',''),
                                ('period','Symbol period [s]','1e-6'),('bins','Histogram bins','64')]:
            grid.Add(wx.StaticText(panel,label=label),0,wx.ALIGN_CENTER_VERTICAL)
            field=wx.TextCtrl(panel,value=value);field.SetName(label);self.fields[key]=field;grid.Add(field,1,wx.EXPAND)
        box.Add(grid,0,wx.EXPAND|wx.ALL,8)
        row=wx.BoxSizer(wx.HORIZONTAL);self.window=wx.Choice(panel,choices=['Hann','Rectangular']);self.window.SetSelection(0)
        row.Add(wx.StaticText(panel,label='Spectral window'),0,wx.ALIGN_CENTER_VERTICAL|wx.RIGHT,6);row.Add(self.window,0,wx.RIGHT,10)
        self.calculate=ActionButton(panel,label='Calculate / plot');self.calculate.Bind(wx.EVT_BUTTON,lambda e:self.request());row.Add(self.calculate,0)
        box.Add(row,0,wx.ALL,8)
        self.figure=Figure();self.canvas=FigureCanvasWxAgg(panel,-1,self.figure)
        self.canvas.SetMinSize((240,160))
        self.toolbar=NavigationToolbar2WxAgg(self.canvas);box.Add(self.toolbar,0,wx.EXPAND);box.Add(self.canvas,1,wx.EXPAND)
        self.report=wx.TextCtrl(panel,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,100));box.Add(self.report,0,wx.EXPAND|wx.ALL,6)
        self.figure.add_subplot().set_title('Choose a view and calculate from retained samples')
        apply_window(self,owner.palette);figure_theme(self.figure,owner.palette,owner.theme_name);self.canvas.draw()
        self.view.Bind(wx.EVT_CHOICE,lambda e:self.reflect());self.reflect()
        self.canvas.Bind(wx.EVT_CONTEXT_MENU,self.context)
        self.Bind(wx.EVT_CLOSE,self.close);self.Show()
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroyed)

    def reflect(self):
        view=self.view.GetStringSelection()
        self.fields['x'].Enable(view=='XY / phase portrait')
        self.fields['period'].Enable(view=='Eye diagram');self.fields['bins'].Enable(view=='Histogram')
        self.window.Enable(view in ('FFT peak amplitude','Power spectral density'))

    def request(self):
        if self.busy:return
        try:
            selected=self.view.GetStringSelection()
            optional=lambda key:float(self.fields[key].GetValue()) if self.fields[key].GetValue().strip() else None
            args=dict(x_expression=self.fields['x'].GetValue(),
                      period_s=float(self.fields['period'].GetValue()) if selected=='Eye diagram' else 1e-6,
                      bins=int(self.fields['bins'].GetValue()) if selected=='Histogram' else 64,
                      start_s=optional('start'),stop_s=optional('stop'),window=self.window.GetStringSelection())
            self.busy=True;self.calculate.Enable(False);self.report.SetValue('Calculating captured samples...')
            future=self.executor.submit(derive,self.engine,self.fields['signal'].GetValue(),selected,**args)
            future.add_done_callback(lambda job:wx.CallAfter(self.complete,job))
        except (ValueError,TypeError) as error:self.report.SetValue(str(error))

    def complete(self,future):
        if self.closed or not self:return
        self.busy=False;self.calculate.Enable(True)
        try:
            data=future.result();self.draw(data)
            self.report.SetValue(describe(data['report']));self.last_data=data
        except Exception as error:self.report.SetValue('Analysis failed: '+str(error))

    def close(self,event):
        self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True);self.Destroy()

    def destroyed(self,event):
        if event.GetEventObject() is self:
            self.closed=True;self.executor.shutdown(wait=False,cancel_futures=True)
        event.Skip()

    def draw(self,data):
        from .plotting import install_navigation
        axis=render(self.figure,data);install_navigation(self.canvas,[axis])
        figure_theme(self.figure,self.owner.palette,self.owner.theme_name);self.canvas.draw()

    def context(self,event):
        from .context_menus import ContextMenu
        menu=ContextMenu(self.canvas)
        def fit():
            if hasattr(self,'last_data'):
                self.draw(self.last_data)
        def grid():
            for axis in self.figure.axes:axis.grid(not any(line.get_visible() for line in axis.get_xgridlines()))
            self.canvas.draw_idle()
        menu.add('Fit derived plot',fit,hasattr(self,'last_data'),'Calculate a view first')
        menu.add('Show / hide grid',grid)
        menu.add('Export PNG / SVG / PDF...',self.toolbar.save_figure)
        position=event.GetPosition()
        menu.popup(self.canvas,None if position==wx.DefaultPosition else self.canvas.ScreenToClient(position))


def show(owner):return AnalysisPlotWindow(owner)
