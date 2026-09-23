"""Direct waveform interaction. Numeric reads always use original run samples."""
import numpy as np

def axis_limits(text,scale='linear'):
    values=[float(v.strip()) for v in text.split(',')]
    if len(values)!=2 or not np.isfinite(values).all() or values[0]>=values[1]:
        raise ValueError('Enter two finite increasing limits: minimum, maximum')
    if scale=='log' and values[0]<=0:raise ValueError('Logarithmic limits must be positive')
    return tuple(values)


def nearest_cursor(axis, times, pixel_x, radius=9):
    if not times:return None
    pixels=axis.get_xaxis_transform().transform([(t,.5) for t in times])[:,0]
    index=int(np.argmin(abs(pixels-pixel_x)))
    return index if abs(pixels[index]-pixel_x)<=radius else None


def cursor_rows(owner):
    from .plot_workspace import sample,format_value
    rows=[]
    for index in range(len(owner.cursors)):
        item=owner.cursor_descriptor(index)
        try:value=format_value(sample(owner.run_engines[item['run']],item['expression'],item['time']))
        except Exception as exc:value='Unavailable: '+str(exc)
        rows.append((chr(65+index),str(item['run']+1),item['expression'],f"{item['time']:.12g}",value))
    return rows


class PlotInteractions:
    def __init__(self,owner):
        self.owner=owner;self.drag=None;self.window=None;self.notes=[];self.legend_visible=True

    def connect(self):
        canvas=self.owner.plot
        self.connections=[canvas.mpl_connect(name,handler) for name,handler in (
            ('button_press_event',self.press),('motion_notify_event',self.motion),('button_release_event',self.release))]

    def press(self,event):
        owner=self.owner
        if event.button==3:
            self.context_menu(event);return
        if event.button!=1 or event.inaxes not in owner.axes or owner.toolbar.mode:return
        index=nearest_cursor(event.inaxes,owner.cursors,event.x)
        if index is not None:
            self.drag=(index,event.inaxes);self.refresh_table();return
        owner.cursor(event)
        if owner.cursors:self.show_cursors()

    def motion(self,event):
        if self.drag is None:return
        if event.x is None or event.y is None:return
        owner=self.owner;index,axis=self.drag
        if index>=len(owner.cursors):self.drag=None;return
        item=owner.cursor_descriptor(index)
        engine=owner.run_engines[item['run']]
        time=axis.transData.inverted().transform((event.x,event.y))[0]
        if not np.isfinite(time):return
        time=float(np.clip(time,engine.time[0],engine.time[-1]))
        owner.put_cursor(time,item['run'],item['expression'],index)
        # Update existing artists, avoiding a full figure rebuild per mouse move.
        for ax in owner.axes:
            cursor_lines=[line for line in ax.lines if getattr(line,'_spikes_cursor',None)==index]
            for line in cursor_lines:line.set_xdata([time,time])
            for text in ax.texts:
                if getattr(text,'_spikes_cursor',None)==index:text.set_x(time)
        owner.plot.draw_idle();self.refresh_table()

    def release(self,event):
        if self.drag is None:return
        self.motion(event);self.drag=None
        self.owner.canvas.Refresh()

    def after_draw(self):
        # Existing native draw_plot emits each cursor after waveform lines.
        for pane,axis in enumerate(self.owner.axes):
            candidates=[line for line in axis.lines if getattr(line,'_spikes_samples',None) is None and line.get_linestyle()=='--']
            for index,line in enumerate(candidates[-len(self.owner.cursors):] if self.owner.cursors else []):line._spikes_cursor=index
            for text in axis.texts:
                label=text.get_text()
                if len(label)==1 and 'A'<=label<='P':text._spikes_cursor=ord(label)-65
            legend=axis.get_legend()
            if legend:legend.set_visible(self.legend_visible)
            for note in self.notes:
                if note['pane']==pane:axis.annotate(note['text'],note['point'],xycoords='data',bbox={'boxstyle':'round,pad=.3','fc':axis.get_facecolor(),'ec':'#7d9099'},color=axis.xaxis.label.get_color(),zorder=8)
        self.refresh_table()

    def show_cursors(self):
        import wx
        if self.window is None:
            frame=wx.Frame(self.owner,title='Waveform cursors — original run samples',size=(800,320),style=wx.DEFAULT_FRAME_STYLE|wx.FRAME_FLOAT_ON_PARENT)
            panel=wx.Panel(frame);layout=wx.BoxSizer(wx.VERTICAL)
            self.table=wx.ListCtrl(panel,style=wx.LC_REPORT|wx.LC_SINGLE_SEL)
            for index,(name,width) in enumerate((('Cursor',60),('Run',55),('Signal / expression',230),('Time [s]',155),('Value',235))):self.table.InsertColumn(index,name,width=width)
            layout.Add(self.table,1,wx.EXPAND|wx.ALL,8)
            row=wx.BoxSizer(wx.HORIZONTAL)
            self.left=wx.Choice(panel);self.right=wx.Choice(panel)
            self.formula=wx.TextCtrl(panel,value='b-a',style=wx.TE_PROCESS_ENTER)
            for text,ctrl in (('A:',self.left),('B:',self.right),('Math:',self.formula)):
                row.Add(wx.StaticText(panel,label=text),0,wx.ALIGN_CENTER_VERTICAL|wx.RIGHT,5);row.Add(ctrl,1,wx.RIGHT,8)
            layout.Add(row,0,wx.EXPAND|wx.ALL,8)
            self.delta=wx.StaticText(panel,label='Select two cursors. Variables: a, b, dt; example (b-a)/dt')
            layout.Add(self.delta,0,wx.EXPAND|wx.ALL,8)
            buttons=wx.BoxSizer(wx.HORIZONTAL)
            for label,handler in (('Edit bindings / time…',lambda e:self.owner.manage_cursors()),('Remove selected',self.remove_selected),('Hide',lambda e:frame.Hide())):
                button=wx.Button(panel,label=label);button.Bind(wx.EVT_BUTTON,handler);buttons.Add(button,0,wx.RIGHT,8)
            layout.Add(buttons,0,wx.ALL,8);panel.SetSizer(layout)
            self.left.Bind(wx.EVT_CHOICE,lambda e:self.refresh_delta());self.right.Bind(wx.EVT_CHOICE,lambda e:self.refresh_delta());self.formula.Bind(wx.EVT_TEXT,lambda e:self.refresh_delta())
            frame.Bind(wx.EVT_CLOSE,lambda e:frame.Hide() if e.CanVeto() else e.Skip())
            from .themes import apply_window
            apply_window(frame,self.owner.palette)
            self.window=frame
        self.refresh_table();self.window.Show();self.window.Raise()

    def refresh_table(self):
        if self.window is None:return
        rows=cursor_rows(self.owner)
        selected=self.table.GetFirstSelected()
        self.table.DeleteAllItems()
        for row in rows:
            index=self.table.InsertItem(self.table.GetItemCount(),row[0])
            for col,value in enumerate(row[1:],1):self.table.SetItem(index,col,value)
        if 0<=selected<len(rows):self.table.Select(selected)
        labels=[row[0] for row in rows]
        for ctrl,default in ((self.left,0),(self.right,1)):
            previous=ctrl.GetSelection()
            if list(ctrl.GetStrings())!=labels:
                ctrl.Set(labels)
                if labels:ctrl.SetSelection(min(previous if previous>=0 else default,len(labels)-1))
        self.refresh_delta()

    def refresh_delta(self):
        if self.window is None:return
        from .plot_workspace import cursor_math,format_value
        a,b=self.left.GetSelection(),self.right.GetSelection()
        if a<0 or b<0:self.delta.SetLabel('Place cursors on a waveform or use Edit bindings / time.');return
        try:
            left=self.owner.cursor_descriptor(a);right=self.owner.cursor_descriptor(b)
            value=cursor_math(self.owner.run_engines,left,right,self.formula.GetValue())
            text=f"Δt = {right['time']-left['time']:.12g} s    Result = {format_value(value)}"
        except Exception as exc:text=str(exc)
        self.delta.SetLabel(text)

    def remove_selected(self,event):
        index=self.table.GetFirstSelected()
        if index<0:return
        self.owner.cursors.pop(index)
        if index<len(self.owner.cursor_bindings):self.owner.cursor_bindings.pop(index)
        self.drag=None;self.owner.draw_plot(preserve_view=True);self.owner.canvas.Refresh()

    def context_menu(self,event):
        import wx
        owner=self.owner;menu=wx.Menu()
        def add(label,handler):
            item=menu.Append(wx.ID_ANY,label)
            menu.Bind(wx.EVT_MENU,lambda e:owner.guarded(handler),item)
        add('Cursor readings / relative math…',self.show_cursors)
        def expression():
            with wx.TextEntryDialog(owner,'Signal or expression, for example v(out) or v(out)-v(in)','Add waveform') as dialog:
                if dialog.ShowModal()==wx.ID_OK:owner.add_trace(dialog.GetValue())
        add('Add signal / mathematical expression…',expression)
        add('Y-axis scale…',owner.axis_options)
        add('Fit all waveforms',lambda:owner.draw_plot())
        add('Fit Y to visible time window',owner.fit_plot_y)
        add('Pan tool',owner.toolbar.pan);add('Rectangle zoom tool',owner.toolbar.zoom)
        menu.AppendSeparator()
        def grid():
            owner.plot_grid=not owner.plot_grid
            for axis in owner.axes:
                if owner.plot_grid:axis.grid(True,alpha=.25)
                else:axis.grid(False)
            owner.plot.draw_idle()
        def legend():
            self.legend_visible=not self.legend_visible
            for axis in owner.axes:
                if axis.get_legend():axis.get_legend().set_visible(self.legend_visible)
            owner.plot.draw_idle()
        add('Hide grid' if owner.plot_grid else 'Show grid',grid)
        add('Hide legends' if self.legend_visible else 'Show legends',legend)
        if event.inaxes in owner.axes:
            pane=owner.axes.index(event.inaxes);point=(event.xdata,event.ydata)
            axis=event.inaxes
            def limits(dimension):
                getter=axis.get_xlim if dimension=='X' else axis.get_ylim
                setter=axis.set_xlim if dimension=='X' else axis.set_ylim
                scale=axis.get_xscale() if dimension=='X' else axis.get_yscale()
                with wx.TextEntryDialog(owner,'Minimum, maximum (SI units). X range is shared across stacked panes.',f'{dimension}-axis limits',', '.join(f'{v:.12g}' for v in getter())) as dialog:
                    if dialog.ShowModal()==wx.ID_OK:
                        bounds=axis_limits(dialog.GetValue(),scale)
                        owner.toolbar.push_current();setter(bounds);owner.toolbar.push_current();owner.plot.draw_idle()
            add('Set shared time limits…',lambda:limits('X'))
            add('Set this pane’s Y limits…',lambda:limits('Y'))
            def note():
                with wx.TextEntryDialog(owner,'Plot note (current session; included in image exports)','Add waveform note') as dialog:
                    if dialog.ShowModal()==wx.ID_OK and dialog.GetValue().strip():
                        self.notes.append({'pane':pane,'point':point,'text':dialog.GetValue().strip()[:2000]});owner.draw_plot(preserve_view=True)
            add('Add note here…',note)
        def clear():self.notes.clear();owner.draw_plot(preserve_view=True)
        add('Clear plot notes',clear)
        owner.plot.PopupMenu(menu);menu.Destroy()
