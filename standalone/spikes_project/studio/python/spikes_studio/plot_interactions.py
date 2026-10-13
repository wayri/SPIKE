"""Direct waveform interaction. Numeric reads always use original run samples."""
import numpy as np

CURSOR_COLORS=('#e85d75','#4ea8de','#f4a261','#70c1b3','#c77dff','#ffca3a','#90be6d','#ff85a1')

def axis_limits(text,scale='linear'):
    values=[float(v.strip()) for v in text.split(',')]
    if len(values)!=2 or not np.isfinite(values).all() or values[0]>=values[1]:
        raise ValueError('Enter two finite increasing limits: minimum, maximum')
    if scale=='log' and values[0]<=0:raise ValueError('Logarithmic limits must be positive')
    return tuple(values)


def nearest_cursor(axis, times, pixel_x, radius=9):
    if len(times)==0:return None
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
        self.owns_capture=False
        self.annotation_drag=None;self.annotation_artists=[];self.sweep_window=None
        self.crosshair_enabled=True;self.crosshair=[];self.crosshair_axis=None

    def connect(self):
        canvas=self.owner.plot
        self.connections=[canvas.mpl_connect(name,handler) for name,handler in (
            ('button_press_event',self.press),('motion_notify_event',self.motion),('button_release_event',self.release),
            ('axes_leave_event',self.leave),('key_press_event',self.key_press))]
        if hasattr(canvas,'Bind'):
            import wx
            canvas.Bind(wx.EVT_MOUSE_CAPTURE_LOST,self.capture_lost)
            canvas.Bind(wx.EVT_CONTEXT_MENU,self.keyboard_context)

    def keyboard_context(self,event):
        import wx
        if event.GetPosition()!=wx.DefaultPosition:event.Skip();return
        from matplotlib.backend_bases import MouseEvent
        owner=self.owner
        x,y=owner.axes[0].transAxes.transform((.5,.5)) if owner.axes else (20,20)
        self.context_menu(MouseEvent('button_press_event',owner.plot,x,y,button=3))

    def heading_at(self,event):
        for axis in self.owner.axes:
            legend=axis.get_legend()
            if legend and legend.get_visible():
                for text in legend.get_texts():
                    if text.contains(event)[0]:return text
        return None

    def cursor_hit(self,event):
        for axis in self.owner.axes:
            for text in axis.texts:
                if hasattr(text,'_spikes_cursor') and text.contains(event)[0]:return text._spikes_cursor,axis
        if event.inaxes in self.owner.axes and event.x is not None:
            index=nearest_cursor(event.inaxes,self.owner.cursors,event.x)
            if index is not None:return index,event.inaxes
        return None

    def begin_drag(self,index,axis):
        self.drag=(index,axis);self.drag_pane=self.owner.axes.index(axis)
        canvas=self.owner.plot
        if hasattr(canvas,'HasCapture') and not canvas.HasCapture():canvas.CaptureMouse();self.owns_capture=True
        self.refresh_table()

    def cancel_drag(self):
        self.drag=None
        canvas=self.owner.plot
        if self.owns_capture and canvas.HasCapture():canvas.ReleaseMouse()
        self.owns_capture=False

    def capture_lost(self,event):self.drag=None;self.annotation_drag=None;self.owns_capture=False;event.Skip()

    def annotation_hit(self,event):
        for artist,note in reversed(self.annotation_artists):
            if note.get('kind')=='arrow' and event.x is not None and event.y is not None:
                if np.linalg.norm(artist.axes.transData.transform(note['head'])-np.array([event.x,event.y]))<=10:return artist,note
            if artist.contains(event)[0]:return artist,note
        return None

    def press(self,event):
        owner=self.owner
        if event.button==3:
            self.context_menu(event);return
        if event.button!=1:return
        heading=self.heading_at(event)
        if heading is not None:
            self.cancel_drag()
            from .waveform_editor import show
            owner.guarded(lambda:show(owner,getattr(heading,'_spikes_expression',heading.get_text())))
            return
        annotation=self.annotation_hit(event)
        if annotation is not None and event.inaxes in owner.axes:
            artist,note=annotation
            self.annotation_drag=(artist,note,event.inaxes,(event.xdata,event.ydata),dict(note))
            self.annotation_head_only=note.get('kind')=='arrow' and np.linalg.norm(event.inaxes.transData.transform(note['head'])-np.array([event.x,event.y]))<=10
            if hasattr(owner.plot,'HasCapture') and not owner.plot.HasCapture():owner.plot.CaptureMouse();self.owns_capture=True
            return
        hit=self.cursor_hit(event)
        if hit is not None:
            if owner.toolbar.mode:owner.toolbar.pan() if 'pan' in str(owner.toolbar.mode).lower() else owner.toolbar.zoom()
            self.begin_drag(*hit);return
        if event.inaxes not in owner.axes or owner.toolbar.mode:return
        if getattr(event,'dblclick',False):
            owner.fit_plot_y();return
        pane=owner.axes.index(event.inaxes);previous=len(owner.cursors)
        owner.cursor(event)
        if len(owner.cursors)>previous:self.begin_drag(len(owner.cursors)-1,owner.axes[pane])

    def motion(self,event):
        self.update_crosshair(event)
        if self.annotation_drag is not None and event.x is not None and event.y is not None:
            artist,note,axis,start,original=self.annotation_drag
            now=axis.transData.inverted().transform((event.x,event.y));delta=now-np.asarray(start)
            if not np.isfinite(delta).all():return
            if not self.annotation_head_only:
                note['point']=(np.asarray(original['point'])+delta).tolist();artist.set_position(note['point'])
            if note.get('kind')=='arrow':note['head']=(np.asarray(original['head'])+delta).tolist();artist.xy=note['head']
            else:artist.xy=note['point']
            self.owner.plot.draw_idle();return
        if self.drag is None or event.x is None or event.y is None:return
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
        if self.annotation_drag is not None:
            self.motion(event)
            from .plot_annotations import commit
            self.annotation_drag=None;self.cancel_drag();commit(self.owner,self.notes);self.owner.draw_plot(preserve_view=True);return
        if self.drag is None:return
        self.motion(event);self.cancel_drag()
        self.owner.canvas.Refresh()

    def key_press(self,event):
        if event.key=='escape':
            if self.annotation_drag is not None:
                _,note,_,_,original=self.annotation_drag;note.update(original);self.annotation_drag=None
                self.owner.draw_plot(preserve_view=True)
            self.cancel_drag()

    def leave(self,event):
        self._show_crosshair(False)

    def set_crosshair(self,enabled):
        self.crosshair_enabled=bool(enabled)
        if not enabled:self._show_crosshair(False)

    def _show_crosshair(self,visible):
        changed=False
        for vertical,horizontal,label in self.crosshair:
            for artist in (vertical,horizontal,label):
                if artist.get_visible()!=visible:artist.set_visible(visible);changed=True
        if changed:self.owner.plot.draw_idle()

    def update_crosshair(self,event):
        owner=self.owner
        inaxes=getattr(event,'inaxes',None);xdata=getattr(event,'xdata',None);ydata=getattr(event,'ydata',None)
        if not self.crosshair_enabled or inaxes not in owner.axes or xdata is None or ydata is None:
            self._show_crosshair(False);return
        if len(self.crosshair)!=len(owner.axes):return
        time=float(xdata);active=owner.axes.index(inaxes)
        for index,(axis,(vertical,horizontal,label)) in enumerate(zip(owner.axes,self.crosshair)):
            vertical.set_xdata([time,time]);vertical.set_visible(True)
            is_active=index==active
            horizontal.set_ydata([ydata,ydata]);horizontal.set_visible(is_active)
            if is_active:
                x_text='t='+self._format_coordinate(time,'s')
                y_text=self._format_coordinate(float(ydata),axis.get_ylabel().strip('[]'))
                label.set_text(f'{x_text}   y={y_text}');label.set_visible(True)
            else:label.set_visible(False)
        owner.plot.draw_idle()

    @staticmethod
    def _format_coordinate(value,unit=''):
        from matplotlib.ticker import EngFormatter
        return EngFormatter(unit=unit,places=4)(value)

    def after_draw(self):
        self.annotation_artists=[]
        metadata=getattr(getattr(self.owner,'doc',None),'data',{}).get('metadata',{})
        if self.annotation_drag is None:
            from copy import deepcopy
            self.notes=deepcopy(metadata.get('plot_annotations',[]))
        if self.drag is not None and self.drag[1] not in self.owner.axes:
            if self.drag[0]<len(self.owner.cursors) and getattr(self,'drag_pane',0)<len(self.owner.axes):self.drag=(self.drag[0],self.owner.axes[self.drag_pane])
            else:self.cancel_drag()
        # Existing native draw_plot emits each cursor after waveform lines.
        for pane,axis in enumerate(self.owner.axes):
            candidates=[line for line in axis.lines if getattr(line,'_spikes_samples',None) is None and line.get_linestyle()=='--']
            for index,line in enumerate(candidates[-len(self.owner.cursors):] if self.owner.cursors else []):
                line._spikes_cursor=index;line.set_color(CURSOR_COLORS[index%len(CURSOR_COLORS)]);line.set_linewidth(1.05);line.set_alpha(.9)
            for text in axis.texts:
                label=text.get_text()
                if len(label)==1 and 'A'<=label<='P':
                    index=ord(label)-65;text._spikes_cursor=index;text.set_color(CURSOR_COLORS[index%len(CURSOR_COLORS)])
                    text.set_bbox({'boxstyle':'round,pad=.22','fc':axis.get_facecolor(),'ec':CURSOR_COLORS[index%len(CURSOR_COLORS)],'alpha':.92})
            legend=axis.get_legend()
            if legend:legend.set_visible(self.legend_visible)
            for note in self.notes:
                if note['pane']==pane:
                    arrow=note.get('kind')=='arrow'
                    artist=axis.annotate(note['text'],note['head'] if arrow else note['point'],xytext=note['point'],xycoords='data',textcoords='data',arrowprops={'arrowstyle':'->','color':axis.xaxis.label.get_color()} if arrow else None,bbox={'boxstyle':'round,pad=.3','fc':axis.get_facecolor(),'ec':'#7d9099'},color=axis.xaxis.label.get_color(),zorder=8)
                    self.annotation_artists.append((artist,note))
        self._install_crosshair()
        self.refresh_table()
        workbench=getattr(self.owner,'plot_workbench',None)
        if workbench is not None:workbench.refresh()

    def _install_crosshair(self):
        self.crosshair=[]
        color=getattr(self.owner,'palette',{}).get('accent','#65d5ed')
        for axis in self.owner.axes:
            vertical=axis.axvline(0,color=color,linewidth=.7,alpha=.7,linestyle=':',visible=False,zorder=7)
            horizontal=axis.axhline(0,color=color,linewidth=.55,alpha=.45,linestyle=':',visible=False,zorder=7)
            label=axis.text(.01,.02,'',transform=axis.transAxes,ha='left',va='bottom',visible=False,zorder=9,
                            bbox={'boxstyle':'round,pad=.25','fc':axis.get_facecolor(),'ec':color,'alpha':.9},color=axis.xaxis.label.get_color())
            vertical._spikes_crosshair=True;horizontal._spikes_crosshair=True;label._spikes_crosshair=True
            self.crosshair.append((vertical,horizontal,label))

    def show_cursors(self):
        import wx
        if self.window is None:
            frame=wx.Frame(self.owner,title='Waveform cursors — original run samples',size=(800,320),style=wx.DEFAULT_FRAME_STYLE|wx.FRAME_FLOAT_ON_PARENT)
            from .app_identity import set_window_icons
            set_window_icons(frame)
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

    def show_sweep_values(self):
        import wx
        if self.sweep_window is None:
            frame=wx.Frame(self.owner,title='Cursor values across all retained runs',size=(1040,440),style=wx.DEFAULT_FRAME_STYLE|wx.FRAME_FLOAT_ON_PARENT)
            from .app_identity import set_window_icons
            set_window_icons(frame)
            panel=wx.Panel(frame);layout=wx.BoxSizer(wx.VERTICAL)
            self.all_sweep_traces=wx.CheckBox(panel,label='All plotted expressions (otherwise each cursor’s bound expression)');self.all_sweep_traces.SetValue(True)
            self.all_sweep_traces.Bind(wx.EVT_CHECKBOX,lambda event:self.refresh_sweep_table());layout.Add(self.all_sweep_traces,0,wx.ALL,8)
            self.sweep_table=wx.ListCtrl(panel,style=wx.LC_REPORT)
            for i,(name,width) in enumerate((('Cursor',55),('Run',50),('Step parameters',200),('Expression',240),('Time [s]',150),('Value',200))):self.sweep_table.InsertColumn(i,name,width=width)
            layout.Add(self.sweep_table,1,wx.EXPAND|wx.ALL,8);self.sweep_status=wx.StaticText(panel,label='');layout.Add(self.sweep_status,0,wx.ALL,8)
            panel.SetSizer(layout);frame.Bind(wx.EVT_CLOSE,lambda e:frame.Hide() if e.CanVeto() else e.Skip())
            from .themes import apply_window
            apply_window(frame,self.owner.palette);self.sweep_window=frame
        self.sweep_window.Show();self.refresh_sweep_table();self.sweep_window.Raise()

    def refresh_sweep_table(self):
        if self.sweep_window is None or not self.sweep_window.IsShown():return
        from .plot_annotations import sweep_cursor_rows
        try:rows=sweep_cursor_rows(self.owner,self.all_sweep_traces.GetValue());self.sweep_status.SetLabel(f'{len(rows):,} original-sample readings · unavailable data is not extrapolated')
        except ValueError as error:rows=[];self.sweep_status.SetLabel(str(error))
        self.sweep_table.Freeze();self.sweep_table.DeleteAllItems()
        for row in rows:
            index=self.sweep_table.InsertItem(self.sweep_table.GetItemCount(),row[0])
            for column,value in enumerate(row[1:],1):self.sweep_table.SetItem(index,column,value)
        self.sweep_table.Thaw()

    def set_grid(self,visible):
        self.owner.plot_grid=bool(visible)
        for axis in self.owner.axes:
            if visible:axis.grid(True,alpha=.25)
            else:axis.grid(False)
        control=getattr(self.owner,'grid_control',None)
        if control is not None:control.SetValue(bool(visible))
        workbench=getattr(self.owner,'plot_workbench',None)
        if workbench is not None:workbench.grid.SetValue(bool(visible))
        self.owner.plot.draw_idle()

    def set_legends(self,visible):
        self.legend_visible=bool(visible)
        for axis in self.owner.axes:
            if axis.get_legend():axis.get_legend().set_visible(bool(visible))
        workbench=getattr(self.owner,'plot_workbench',None)
        if workbench is not None:workbench.legends.SetValue(bool(visible))
        self.owner.plot.draw_idle()

    def refresh_table(self):
        workbench=getattr(self.owner,'plot_workbench',None)
        if workbench is not None:workbench._refresh_cursors()
        self.refresh_sweep_table()
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

    def copy_cursor_readings(self):
        import wx
        from .plot_workspace import cursor_table_text
        if not self.owner.cursors:raise ValueError('Place a cursor first')
        data=wx.TextDataObject(cursor_table_text(self.owner))
        if not wx.TheClipboard.Open():raise RuntimeError('Clipboard is unavailable')
        try:
            if not wx.TheClipboard.SetData(data):raise RuntimeError('Could not copy cursor readings')
            wx.TheClipboard.Flush()
        finally:wx.TheClipboard.Close()

    def _place_at(self,event):
        owner=self.owner
        if event.inaxes not in owner.axes or event.xdata is None or owner.math is None:raise ValueError('Point inside a waveform pane')
        names=[line.get_label() for line in event.inaxes.lines if line.get_visible() and getattr(line,'_spikes_samples',None) is not None]
        expression=next((name for name,_values,_unit in owner.traces if name in names),owner.expression.GetValue())
        time=float(np.clip(event.xdata,owner.math.time[0],owner.math.time[-1]))
        owner.put_cursor(time,owner.selected_run,expression);owner.draw_plot(preserve_view=True);owner.canvas.Refresh()

    def _remove_nearest(self,event):
        index=nearest_cursor(event.inaxes,self.owner.cursors,event.x)
        if index is None:raise ValueError('Right-click closer to a cursor marker')
        self.owner.cursors.pop(index)
        if index<len(self.owner.cursor_bindings):self.owner.cursor_bindings.pop(index)
        self.drag=None;self.owner.draw_plot(preserve_view=True);self.owner.canvas.Refresh()

    def context_menu(self,event):
        import wx
        from .context_menus import ContextMenu
        owner=self.owner;menu=ContextMenu(owner)
        from .waveform_editor import show
        annotation=self.annotation_hit(event)
        if annotation is not None:
            _,note=annotation
            from .plot_annotations import commit
            def edit_note():
                with wx.TextEntryDialog(owner,'Annotation text','Edit plot annotation',note['text']) as dialog:
                    if dialog.ShowModal()==wx.ID_OK:
                        updated=[dict(n,text=dialog.GetValue()) if n['id']==note['id'] else n for n in self.notes]
                        commit(owner,updated);owner.draw_plot(preserve_view=True)
            def remove_note():commit(owner,[n for n in self.notes if n['id']!=note['id']]);owner.draw_plot(preserve_view=True)
            annotation_menu=menu.submenu('Selected annotation')
            annotation_menu.add('Edit text…',edit_note)
            annotation_menu.add('Delete',remove_note)
        heading=self.heading_at(event)
        if heading is not None:
            expression=getattr(heading,'_spikes_expression',heading.get_text())
            waveform=menu.submenu('Waveform')
            waveform.add('Edit expression / signal…',lambda:show(owner,expression))
            waveform.add('Hide / show',lambda:owner.pick_trace(type('Pick',(),{'artist':heading})()))
        menu.add('Add signal / mathematical expression…',lambda:show(owner))
        from .analysis_plot_window import show as show_analysis
        menu.add('Analysis plots (FFT / eye / XY)…',lambda:show_analysis(owner),owner.math is not None,'Run or load retained time samples first')
        cursors=menu.submenu('Cursors and measurements')
        cursors.add('Readings / relative math…',self.show_cursors)
        cursors.add('All .step runs at cursors…',self.show_sweep_values,bool(owner.cursors),'Place a cursor first')
        can_place=event.inaxes in owner.axes and event.xdata is not None and owner.math is not None
        cursors.add('Place cursor here',lambda:self._place_at(event),can_place,'Point inside a waveform pane with run data')
        near=nearest_cursor(event.inaxes,owner.cursors,event.x) if event.inaxes in owner.axes and event.x is not None else None
        cursors.add('Remove nearest cursor',lambda:self._remove_nearest(event),near is not None,'Right-click near a cursor marker')
        cursors.add('Copy original-sample readings',self.copy_cursor_readings,bool(owner.cursors),'Place a cursor first')
        view=menu.submenu('View')
        view.add('Y-axis scale…',owner.axis_options)
        view.add('Fit all waveforms',lambda:owner.draw_plot())
        view.add('Fit Y to visible time window',owner.fit_plot_y)
        view.add('Pan tool',owner.toolbar.pan)
        view.add('Rectangle zoom tool',owner.toolbar.zoom)
        def grid():
            self.set_grid(not owner.plot_grid)
        def legend():
            self.set_legends(not self.legend_visible)
        view.add('Grid',grid,checked=bool(owner.plot_grid))
        view.add('Legends',legend,checked=self.legend_visible)
        def crosshair():
            self.set_crosshair(not self.crosshair_enabled)
            workbench=getattr(owner,'plot_workbench',None)
            if workbench is not None:workbench.crosshair.SetValue(self.crosshair_enabled)
        view.add('Linked crosshair',crosshair,checked=self.crosshair_enabled)
        annotations=menu.submenu('Annotations')
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
            view.add('Set shared time limits…',lambda:limits('X'))
            view.add('Set this pane’s Y limits…',lambda:limits('Y'))
            def note():
                with wx.TextEntryDialog(owner,'Plot note (current session; included in image exports)','Add waveform note') as dialog:
                    if dialog.ShowModal()==wx.ID_OK and dialog.GetValue().strip():
                        from .plot_annotations import create,commit
                        commit(owner,[*self.notes,create(pane,point,dialog.GetValue())]);owner.draw_plot(preserve_view=True)
            annotations.add('Add note here…',note,event.xdata is not None and event.ydata is not None,'Point inside a waveform pane')
            def arrow():
                with wx.TextEntryDialog(owner,'Arrow label; drag annotation to move it','Add arrow') as dialog:
                    if dialog.ShowModal()==wx.ID_OK:
                        from .plot_annotations import create,commit
                        tail=(point[0]-.12*np.diff(axis.get_xlim())[0],point[1]+.12*np.diff(axis.get_ylim())[0])
                        commit(owner,[*self.notes,create(pane,tail,dialog.GetValue(),kind='arrow',head=point)]);owner.draw_plot(preserve_view=True)
            annotations.add('Add arrow / label here…',arrow,event.xdata is not None and event.ydata is not None,'Point inside a waveform pane')
        else:
            annotations.add('Add note here…',lambda:None,False,'Point inside a waveform pane')
            annotations.add('Add arrow / label here…',lambda:None,False,'Point inside a waveform pane')
        def clear():
            from .plot_annotations import commit
            commit(owner,[]);owner.draw_plot(preserve_view=True)
        annotations.add('Clear all',clear,bool(self.notes),'No plot annotations')
        save=getattr(owner.toolbar,'save_figure',None)
        menu.add('Export plot image…',save,callable(save),'The active plot toolbar cannot export images')
        menu.popup(owner.plot)
