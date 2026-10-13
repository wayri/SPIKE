"""Run-qualified cursor math and native plot-workbench presentation helpers."""
import ast
import math
import numpy as np
from .fuzzy_search import matches, ranked
from .signal_math import SignalMath,Quantity,VOLT,AMP,SECOND,ExpressionError

FORMATS=('Engineering','Rectangular complex','Polar / degrees')
MAX_BROWSER_ROWS=512


def run_label(result,index):
    parameters=result.get('provenance',{}).get('step_parameters',{})
    return f'Run {index+1}'+(' · '+', '.join(f'{k}={v:g}' for k,v in parameters.items()) if parameters else '')


def _matches_filter(text,query):
    return matches(text,query)


def signal_browser_rows(owner,query='',limit=MAX_BROWSER_ROWS):
    """Return bounded available-signal rows without evaluating new curves."""
    if not isinstance(query,str):raise TypeError('Signal filter must be text')
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=MAX_BROWSER_ROWS:raise ValueError(f'Signal browser limit must be 1..{MAX_BROWSER_ROWS}')
    engine=getattr(owner,'math',None)
    if engine is None:return []
    rows=[]
    for expression,quantity in engine.signals.items():
        unit=str(quantity.unit)
        if _matches_filter(f'{expression} {unit}',query):rows.append((expression,unit))
    return ranked(sorted(rows,key=lambda row:row[0].casefold()),query,text=lambda r:' '.join(r))[:limit]


def trace_browser_rows(owner,query=''):
    """Return expression, unit and visibility for actual plotted traces."""
    if not isinstance(query,str):raise TypeError('Trace filter must be text')
    hidden=getattr(owner,'hidden_traces',set())
    rows=[]
    for expression,_values,unit in getattr(owner,'traces',[]):
        if _matches_filter(f'{expression} {unit}',query):rows.append((expression,unit,expression not in hidden))
    return ranked(rows,query,text=lambda r:f'{r[0]} {r[1]}')


def run_browser_rows(owner,query=''):
    """Describe retained runs with exact sample counts and recorded parameters."""
    if not isinstance(query,str):raise TypeError('Run filter must be text')
    rows=[]
    for index,result in enumerate(getattr(owner,'run_results',[])):
        label=run_label(result,index)
        data=result.get('data',{})
        samples=len(data.get('time_s',data.get('sweep',{}).get('values',[])))
        if _matches_filter(f'{label} {samples}',query):rows.append((index,label,samples))
    return ranked(rows,query,text=lambda r:f'{r[1]} {r[2]}')


def cursor_table_text(owner):
    """Tab-separated, clipboard-ready readings computed from retained run data."""
    from .plot_interactions import cursor_rows
    rows=cursor_rows(owner)
    header=('Cursor','Run','Signal / expression','Coordinate [s]','Value')
    return '\n'.join('\t'.join(row) for row in (header,*rows))


class PlotBrowserModel:
    """Headless action model shared by the wx workbench and focused tests."""
    def __init__(self,owner):self.owner=owner

    def signals(self,query=''):return signal_browser_rows(self.owner,query)
    def traces(self,query=''):return trace_browser_rows(self.owner,query)
    def runs(self,query=''):return run_browser_rows(self.owner,query)

    def add_signal(self,expression):
        available={name for name,_unit in self.signals()}
        if expression not in available:raise ValueError('Select an available recorded signal')
        self.owner.add_trace(expression)

    def set_trace_visible(self,expression,visible):
        plotted={name for name,_unit,_shown in self.traces()}
        if expression not in plotted:raise ValueError('Trace is not plotted')
        if visible:self.owner.hidden_traces.discard(expression)
        else:self.owner.hidden_traces.add(expression)
        self.owner.draw_plot(preserve_view=True)

    def activate_run(self,index):
        if index not in {row[0] for row in self.runs()}:raise ValueError('Run is unavailable')
        self.owner.select_run(index)

    def set_overlay_runs(self,indices):
        available={row[0] for row in self.runs()}
        chosen=set(indices)
        if not chosen<=available:raise ValueError('Overlay contains an unavailable run')
        self.owner.visible_runs=chosen
        self.owner.overlay_runs.SetValue(bool(chosen))
        self.owner.draw_plot(preserve_view=True)


class PlotWorkbench:
    """Compact wx plot chrome; importing this module remains headless-safe.

    Create this after ``owner.toolbar`` and ``owner.plot_interactions`` exist.
    Add ``command_bar`` and ``canvas_row(owner.plot)`` to the plot panel sizer.
    ``PlotInteractions.after_draw`` keeps the browser and cursor table current.
    """
    def __init__(self,owner,parent):
        import wx
        self.wx=wx;self.owner=owner;self.model=PlotBrowserModel(owner);self._syncing=False
        self.command_bar=wx.Panel(parent);self.sidebar=wx.Panel(parent)
        self._build_command_bar();self._build_sidebar()
        from .themes import apply_window
        apply_window(self.command_bar,owner.palette);apply_window(self.sidebar,owner.palette)

    def _button(self,parent,label,handler,sizer,tooltip=''):
        from .flat_controls import ActionButton
        button=ActionButton(parent,label=label)
        if tooltip:button.SetToolTip(tooltip)
        button.Bind(self.wx.EVT_BUTTON,lambda event:self._guard(handler))
        flags=self.wx.ALL
        if not hasattr(sizer,'GetOrientation') or sizer.GetOrientation()==self.wx.HORIZONTAL:flags|=self.wx.ALIGN_CENTER_VERTICAL
        sizer.Add(button,0,flags,2)
        return button

    def _guard(self,action):
        guarded=getattr(self.owner,'guarded',None)
        return guarded(action) if callable(guarded) else action()

    def _build_command_bar(self):
        from .flat_controls import ActionButton
        wx=self.wx;bar=wx.WrapSizer(wx.HORIZONTAL)
        self.sidebar_toggle=ActionButton(self.command_bar,label='Browser',toggle=True)
        self.sidebar_toggle.SetValue(True);self.sidebar_toggle.SetToolTip('Show or hide runs, recorded signals, plotted traces and cursor readings')
        self.sidebar_toggle.Bind(wx.EVT_TOGGLEBUTTON,lambda event:self.show_sidebar(event.IsChecked()))
        bar.Add(self.sidebar_toggle,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,2)
        bar.Add(wx.StaticText(self.command_bar,label='Layout'),0,wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL,4)
        self.layout_choice=wx.Choice(self.command_bar,choices=['Plot only','Side by side','Top / bottom'])
        self.layout_choice.SetName('Plot workspace layout');self.layout_choice.SetSelection(0)
        self.layout_choice.SetToolTip('Show only the plot or split it beside / below the schematic')
        self.layout_choice.Bind(wx.EVT_CHOICE,self._layout_changed)
        bar.Add(self.layout_choice,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,2)
        self._button(self.command_bar,'Fit all',lambda:self.owner.draw_plot(),bar,'Reset all plot limits')
        self._button(self.command_bar,'Fit Y',self.owner.fit_plot_y,bar,'Fit each pane to signals visible in the current time window')
        self._button(self.command_bar,'Pan',self.owner.toolbar.pan,bar,'Toggle Matplotlib pan mode')
        self._button(self.command_bar,'Box zoom',self.owner.toolbar.zoom,bar,'Toggle rectangle zoom mode')
        self._button(self.command_bar,'Cursors…',self.owner.plot_interactions.show_cursors,bar,'Open run-qualified A/B cursor readings and relative math')
        self._button(self.command_bar,'More…',self.owner.toggle_plot_details,bar,'Show analysis, sweep, archive and continuous-control tools')
        self._button(self.command_bar,'Sweep values…',self.owner.plot_interactions.show_sweep_values,bar,'Read all plotted expressions for every retained run at each cursor')
        def analysis():
            from .analysis_plot_window import show
            show(self.owner)
        self._button(self.command_bar,'Analysis plots…',analysis,bar,'Captured-run XY, FFT, PSD, eye, histogram and integral views')
        self.grid=wx.CheckBox(self.command_bar,label='Grid');self.grid.SetValue(self.owner.plot_grid)
        self.grid.Bind(wx.EVT_CHECKBOX,lambda event:self.owner.plot_interactions.set_grid(event.IsChecked()));bar.Add(self.grid,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        self.legends=wx.CheckBox(self.command_bar,label='Legends');self.legends.SetValue(True)
        self.legends.Bind(wx.EVT_CHECKBOX,lambda event:self.owner.plot_interactions.set_legends(event.IsChecked()));bar.Add(self.legends,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,4)
        self.crosshair=wx.CheckBox(self.command_bar,label='Linked crosshair')
        self.crosshair.SetValue(self.owner.plot_interactions.crosshair_enabled)
        self.crosshair.SetToolTip('Track one time coordinate across all waveform panes')
        self.crosshair.Bind(wx.EVT_CHECKBOX,lambda event:self.owner.plot_interactions.set_crosshair(event.IsChecked()))
        bar.Add(self.crosshair,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,5)
        self.status=wx.StaticText(self.command_bar,label='No recorded waveform')
        bar.Add(self.status,0,wx.ALL|wx.ALIGN_CENTER_VERTICAL,6)
        self.command_bar.SetSizer(bar)

    def _heading(self,parent,label,sizer):
        text=self.wx.StaticText(parent,label=label)
        font=text.GetFont();font.SetWeight(self.wx.FONTWEIGHT_BOLD);text.SetFont(font)
        sizer.Add(text,0,self.wx.LEFT|self.wx.RIGHT|self.wx.TOP,8)

    def _build_sidebar(self):
        wx=self.wx;box=wx.BoxSizer(wx.VERTICAL);self.sidebar.SetMinSize((270,-1))
        self._heading(self.sidebar,'RUNS',box)
        self.active_run=wx.Choice(self.sidebar);self.active_run.SetToolTip('Active run supplies newly added traces and cursor clicks')
        self.active_run.Bind(wx.EVT_CHOICE,self._activate_run);box.Add(self.active_run,0,wx.EXPAND|wx.ALL,6)
        self.run_list=wx.CheckListBox(self.sidebar,size=(-1,84));self.run_list.SetToolTip('Checked runs are overlaid when at least one run is checked')
        self.run_list.Bind(wx.EVT_CHECKLISTBOX,self._overlay_changed);box.Add(self.run_list,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM,6)
        self._heading(self.sidebar,'RECORDED SIGNALS',box)
        self.search=wx.SearchCtrl(self.sidebar,style=wx.TE_PROCESS_ENTER);self.search.ShowCancelButton(True)
        self.search.SetDescriptiveText('Filter by name or unit');self.search.Bind(wx.EVT_TEXT,lambda event:self.refresh_signals())
        box.Add(self.search,0,wx.EXPAND|wx.ALL,6)
        self.signals=wx.ListCtrl(self.sidebar,style=wx.LC_REPORT|wx.LC_SINGLE_SEL,size=(-1,130))
        self.signals.InsertColumn(0,'Signal',width=170);self.signals.InsertColumn(1,'Unit',width=65)
        self.signals.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda event:self._add_selected_signal())
        box.Add(self.signals,1,wx.EXPAND|wx.LEFT|wx.RIGHT,6)
        self._button(self.sidebar,'Plot selected signal',self._add_selected_signal,box,'Plot the selected retained channel without altering its samples')
        self._heading(self.sidebar,'PLOTTED TRACES',box)
        self.trace_list=wx.CheckListBox(self.sidebar,size=(-1,100));self.trace_list.SetToolTip('Uncheck a trace to hide it without discarding its expression')
        self.trace_list.Bind(wx.EVT_CHECKLISTBOX,self._trace_visibility_changed);box.Add(self.trace_list,0,wx.EXPAND|wx.ALL,6)
        self.trace_list.SetToolTip('Uncheck to hide; double-click to edit the signal or mathematical expression')
        def edit_trace(event):
            index=self.trace_list.GetSelection();rows=self.model.traces()
            if 0<=index<len(rows):
                from .waveform_editor import show
                self._guard(lambda:show(self.owner,rows[index][0]))
        self.trace_list.Bind(wx.EVT_LISTBOX_DCLICK,edit_trace)
        self._heading(self.sidebar,'CURSOR READINGS',box)
        self.cursor_list=wx.ListCtrl(self.sidebar,style=wx.LC_REPORT|wx.LC_SINGLE_SEL,size=(-1,100))
        for index,(label,width) in enumerate((('ID',34),('Run',42),('Time',82),('Value',105))):self.cursor_list.InsertColumn(index,label,width=width)
        self.cursor_list.SetToolTip('Readings use each cursor\'s bound run and expression')
        self.cursor_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda event:self._guard(self.owner.plot_interactions.show_cursors))
        box.Add(self.cursor_list,0,wx.EXPAND|wx.LEFT|wx.RIGHT,6)
        row=wx.BoxSizer(wx.HORIZONTAL)
        self._button(self.sidebar,'Details…',self.owner.plot_interactions.show_cursors,row)
        self._button(self.sidebar,'Copy',self.copy_cursor_readings,row,'Copy exact displayed cursor readings as tab-separated text')
        box.Add(row,0,wx.EXPAND|wx.ALL,4);self.sidebar.SetSizer(box)

    def canvas_row(self,canvas):
        row=self.wx.BoxSizer(self.wx.HORIZONTAL);row.Add(self.sidebar,0,self.wx.EXPAND);row.Add(canvas,1,self.wx.EXPAND)
        self.refresh();return row

    def show_sidebar(self,visible):
        self.sidebar.Show(bool(visible));self.sidebar_toggle.SetValue(bool(visible))
        parent=self.sidebar.GetParent();parent.Layout()

    def refresh_signals(self):
        query=self.search.GetValue() if hasattr(self,'search') else ''
        rows=self.model.signals(query);self.signals.Freeze();self.signals.DeleteAllItems()
        for expression,unit in rows:
            index=self.signals.InsertItem(self.signals.GetItemCount(),expression);self.signals.SetItem(index,1,unit)
        self.signals.Thaw()

    def refresh(self):
        if self._syncing:return
        self._syncing=True
        try:
            runs=self.model.runs();labels=[label for _index,label,_samples in runs]
            if list(self.active_run.GetStrings())!=labels:self.active_run.Set(labels)
            selected=getattr(self.owner,'selected_run',0)
            if labels:self.active_run.SetSelection(min(selected,len(labels)-1))
            if list(self.run_list.GetStrings())!=labels:self.run_list.Set(labels)
            visible=getattr(self.owner,'visible_runs',None);overlay=getattr(self.owner,'overlay_runs',None)
            enabled=bool(overlay and overlay.GetValue())
            for row,(index,_label,_samples) in enumerate(runs):self.run_list.Check(row,enabled and (visible is None or index in visible))
            traces=self.model.traces();trace_labels=[f'{name}  [{unit}]' for name,unit,_shown in traces]
            if list(self.trace_list.GetStrings())!=trace_labels:self.trace_list.Set(trace_labels)
            for index,(_name,_unit,shown) in enumerate(traces):self.trace_list.Check(index,shown)
            self.refresh_signals();self._refresh_cursors()
            samples=0
            math_engine=getattr(self.owner,'math',None)
            if math_engine is not None:samples=len(math_engine.time)
            self.status.SetLabel(f'{samples:,} retained samples · {len(traces)} plotted · display bounded')
        finally:self._syncing=False

    def _refresh_cursors(self):
        from .plot_interactions import cursor_rows
        from matplotlib.ticker import EngFormatter
        rows=cursor_rows(self.owner);self.cursor_list.Freeze();self.cursor_list.DeleteAllItems()
        for cursor,run,_expression,time,value in rows:
            index=self.cursor_list.InsertItem(self.cursor_list.GetItemCount(),cursor)
            for column,text in enumerate((run,EngFormatter(unit='s',places=4)(float(time)),value),1):self.cursor_list.SetItem(index,column,text)
        self.cursor_list.Thaw()

    def _add_selected_signal(self):
        index=self.signals.GetFirstSelected()
        if index<0:raise ValueError('Select a recorded signal first')
        self.model.add_signal(self.signals.GetItemText(index));self.refresh()

    def _activate_run(self,event):
        if self._syncing:return
        rows=self.model.runs();selection=event.GetSelection()
        if 0<=selection<len(rows):self._guard(lambda:self.model.activate_run(rows[selection][0]));self.refresh()

    def _overlay_changed(self,event):
        if self._syncing:return
        rows=self.model.runs();chosen={rows[index][0] for index in range(len(rows)) if self.run_list.IsChecked(index)}
        self._guard(lambda:self.model.set_overlay_runs(chosen));self.refresh()

    def _layout_changed(self,event):
        choice=event.GetString()
        if choice=='Plot only':
            if getattr(self.owner,'split_view',False):self._guard(self.owner.toggle_split)
        elif choice=='Side by side':self._guard(lambda:self.owner.set_split('side_by_side'))
        elif choice=='Top / bottom':self._guard(lambda:self.owner.set_split('top_bottom'))

    def _trace_visibility_changed(self,event):
        if self._syncing:return
        rows=self.model.traces();index=event.GetInt()
        if 0<=index<len(rows):
            name=rows[index][0];visible=self.trace_list.IsChecked(index)
            self._guard(lambda:self.model.set_trace_visible(name,visible));self.refresh()

    def copy_cursor_readings(self):
        text=cursor_table_text(self.owner)
        if len(getattr(self.owner,'cursors',[]))==0:raise ValueError('Place a cursor first')
        data=self.wx.TextDataObject(text)
        if not self.wx.TheClipboard.Open():raise RuntimeError('Clipboard is unavailable')
        try:
            if not self.wx.TheClipboard.SetData(data):raise RuntimeError('Could not copy cursor readings')
            self.wx.TheClipboard.Flush()
        finally:self.wx.TheClipboard.Close()


def sample(engine,expression,time):
    if not math.isfinite(time) or not engine.time[0]<=time<=engine.time[-1]:
        raise ValueError('Cursor is outside this run’s recorded interval')
    q=engine.evaluate(expression);values=np.broadcast_to(q.values,engine.time.shape)
    return Quantity(np.interp(time,engine.time,values),q.unit)


def cursor_math(engines,left,right,expression='b-a'):
    """Each cursor owns its run, expression and coordinate. Never clamp silently."""
    a=sample(engines[left['run']],left['expression'],left['time'])
    b=sample(engines[right['run']],right['expression'],right['time'])
    dt=Quantity(right['time']-left['time'],SECOND)
    answer=engines[left['run']].evaluate(expression,variables={'a':a,'b':b,'dt':dt})
    if np.ndim(answer.values):raise ValueError('Cursor math must produce a scalar; use a, b and dt')
    return answer


class OperatingPointMath(SignalMath):
    def __init__(self,result):
        self.time=np.array([]);self.signals={}
        for table,prefix,unit in (('node_voltage_v','v',VOLT),('element_current_a','i',AMP),('element_power_w','p',VOLT.mul(AMP))):
            for name,value in result['data'].get(table,{}).items():
                if np.ndim(value):raise ValueError('Not an operating-point scalar capture')
                self.signals[f'{prefix}({name})'.lower()]=Quantity(float(value),unit)

    def _visit(self,node,variables):
        if isinstance(node,ast.Name) and node.id=='t':raise ExpressionError('Operating points have no time axis')
        return super()._visit(node,variables)

    def _call(self,name,args):
        if name in ('integral','derivative','mean','rms'):raise ExpressionError('No time reductions on an operating point')
        return super()._call(name,args)


def format_value(q,style='Engineering'):
    value=complex(q.values)
    if not np.isfinite(value):raise ValueError('Non-finite instrument value')
    unit=str(q.unit)
    if style=='Polar / degrees':return f'{abs(value):.6g} ∠ {np.degrees(np.angle(value)):.4g}° {unit}'
    if style=='Rectangular complex' or value.imag:return f'{value.real:.6g} {value.imag:+.6g}j {unit}'
    from matplotlib.ticker import EngFormatter
    return EngFormatter(unit=unit,places=4)(value.real)


def _document_data(doc):
    """Accept the Document authority or its inert persisted dictionary."""
    return doc.data if hasattr(doc,'data') else doc


def attachment_node(doc,item):
    """Resolve an instrument's source-authoritative net without geometry inference."""
    data=_document_data(doc);parts={part['id']:part for part in data.get('components',[])}
    part=parts.get(item.get('anchor'))
    pin_index=item.get('pin_index')
    if part is not None and type(pin_index) is int and 0<=pin_index<len(part.get('nodes',[])):
        return part['nodes'][pin_index]
    expression=item.get('expression','').strip()
    if expression[:2].casefold()=='v(' and expression.endswith(')'):
        arguments=[value.strip() for value in expression[2:-1].split(',')]
        if len(arguments)==1 and arguments[0]:return arguments[0]
    return None


def attachment_point(doc,item):
    """Return the saved wire point or live transformed terminal for an instrument.

    Old component-only saves remain readable at their component center.  An even
    older voltage-expression-only item follows the first matching terminal.
    """
    point=item.get('attach_point')
    if isinstance(point,(list,tuple)) and len(point)==2:
        try:return tuple(float(value) for value in point)
        except (TypeError,ValueError):pass
    data=_document_data(doc);parts={part['id']:part for part in data.get('components',[])}
    part=parts.get(item.get('anchor'));pin_index=item.get('pin_index')
    if part is not None and type(pin_index) is int and 0<=pin_index<len(part.get('nodes',[])):
        from .editor_geometry import terminal
        return terminal(part,pin_index)
    if part is not None:return float(part['x']),float(part['y'])
    node=attachment_node(data,item)
    if node is not None:
        from .editor_geometry import terminal
        for candidate in data.get('components',[]):
            for index,value in enumerate(candidate.get('nodes',[])):
                if value.casefold()==node.casefold():return terminal(candidate,index)
    return float(item.get('x',0)),float(item.get('y',0))


def signal_color(doc,node,palette):
    """Return a stable theme-aware color for one attached named net."""
    import hashlib
    from .themes import TRACE_DARK,TRACE_LIGHT
    if not isinstance(node,str) or not node: return palette['accent']
    canvas=str(palette.get('canvas','#ffffff')).lstrip('#')
    try:
        rgb=tuple(int(canvas[index:index+2],16) for index in (0,2,4))
        dark=sum((.2126,.7152,.0722)[index]*value for index,value in enumerate(rgb))<128
    except (ValueError,TypeError):dark=True
    colors=TRACE_DARK if dark else TRACE_LIGHT
    digest=hashlib.sha256(node.casefold().encode('utf-8')).digest()
    return colors[int.from_bytes(digest[:4],'big')%len(colors)]


def add_attached_plot(doc,part_id,pin_index,position,attach_point=None):
    """Create one terminal/net-attached Mini plot as an atomic undoable edit."""
    import uuid
    data=_document_data(doc);part=next((row for row in data.get('components',[]) if row.get('id')==part_id),None)
    if part is None:raise ValueError('Choose an existing component terminal')
    if type(pin_index) is not int or not 0<=pin_index<len(part.get('nodes',[])):raise ValueError('Choose an existing component terminal')
    if not isinstance(position,(list,tuple)) or len(position)!=2:raise ValueError('Instrument position must contain X and Y')
    position=tuple(float(value) for value in position)
    if not all(math.isfinite(value) and abs(value)<=1e12 for value in position):raise ValueError('Invalid instrument position')
    if attach_point is not None:
        if not isinstance(attach_point,(list,tuple)) or len(attach_point)!=2:raise ValueError('Attachment point must contain X and Y')
        attach_point=tuple(float(value) for value in attach_point)
        if not all(math.isfinite(value) and abs(value)<=1e6 for value in attach_point):raise ValueError('Invalid attachment point')
    item={'id':uuid.uuid4().hex,'anchor':part_id,'pin_index':pin_index,
          'expression':f"V({part['nodes'][pin_index]})",'kind':'Mini plot',
          'source':'Selected run','format':'Engineering','frequency_hz':1000.0,
          'x':position[0],'y':position[1]}
    if attach_point is not None:item['attach_point']=list(attach_point)
    if not hasattr(doc,'commit'):raise TypeError('add_attached_plot requires a Document')
    doc.commit(lambda candidate:candidate['instruments'].append(item))
    return item['id']


def validate_instruments(items,components):
    if not isinstance(items,list) or len(items)>64:raise ValueError('At most 64 schematic instruments')
    ids=set();parts={part.get('id'):part for part in components}
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in ids:raise ValueError('Instrument IDs must be unique')
        ids.add(item['id'])
        # Detached anchors are retained through circuit edits; rendered unavailable.
        if not isinstance(item.get('anchor'),str):raise ValueError('Instrument anchor is required')
        if item.get('kind') not in ('Readout','Mini plot') or item.get('source') not in ('Selected run','AC frequency'):raise ValueError('Unknown instrument type / source')
        if item.get('format') not in FORMATS:raise ValueError('Unknown readout format')
        if not isinstance(item.get('expression'),str) or not 0<len(item['expression'])<=8192:raise ValueError('Instrument expression is required')
        for key in ('x','y','frequency_hz'):
            if type(item.get(key)) not in (float,int) or not math.isfinite(item[key]) or abs(item[key])>1e12:raise ValueError('Invalid instrument position / frequency')
        if item['frequency_hz']<=0:raise ValueError('AC readout requires positive frequency')
        pin_index=item.get('pin_index')
        if pin_index is not None and (type(pin_index) is not int or pin_index<0):raise ValueError('Invalid instrument terminal index')
        part=parts.get(item['anchor'])
        if part is not None and pin_index is not None and pin_index>=len(part.get('nodes',[])):raise ValueError('Invalid instrument terminal index')
        point=item.get('attach_point')
        if point is not None and (not isinstance(point,(list,tuple)) or len(point)!=2 or any(type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1e6 for value in point)):
            raise ValueError('Invalid instrument attachment point')


def instrument_data(owner,item):
    expression=item['expression']
    if item['source']=='AC frequency':
        from .frequency import FrequencyMath
        result=owner.frequency.result
        if result is None:raise ValueError('Run AC first')
        cached=getattr(owner.frequency,'_instrument_engine',None)
        if cached is None or cached[0] is not result:
            cached=(result,FrequencyMath.from_frequency(result));owner.frequency._instrument_engine=cached
        engine=cached[1]
        q=sample(engine,expression,item['frequency_hz'])
        label=f"AC {item['frequency_hz']:g} Hz · complex excitation"
    else:
        if owner.result is None:raise ValueError('Run circuit first')
        label=run_label(owner.result,getattr(owner,'selected_run',0))
        if owner.math:
            engine=owner.math
            time=owner.cursors[-1] if owner.cursors else engine.time[-1]
            q=sample(engine,expression,time);label+=f' · t={time:.6g}s'
        else:
            engine=None;q=OperatingPointMath(owner.result).evaluate(expression);label+=' · DC OP'
    if np.ndim(q.values):raise ValueError('Readout must be scalar')
    stale=owner.result_source and owner.result_source.get('document_source',owner.result_source['source'])!=owner.doc.data['source']
    if item['source']=='AC frequency':
        from python.spikes.netlist import parse_netlist
        stale=result.get('provenance',{}).get('circuit_source_sha256')!=parse_netlist(owner.doc.data['source'],native_extensions=True,transient_capture='rolling').source_sha256
    if stale:label+=' · STALE circuit'
    if item['kind']=='Mini plot':
        if engine is None:raise ValueError('OP has no waveform')
        answer=engine.evaluate(expression);values=np.broadcast_to(answer.values,engine.time.shape)
        if np.iscomplexobj(values):raise ValueError('Mini plot: use real(), abs() or angle()')
        return label,format_value(q,item['format']),(engine.time,values)
    return label,format_value(q,item['format']),None
