"""Native design/run dashboard with truthful run and source provenance."""
from copy import deepcopy
import wx
import numpy as np
from .flat_controls import ActionButton
from .dashboard import (
    INSTRUMENT_ACTIONS,
    KINDS,
    empty_dashboard,
    meter_fraction,
    read_signal,
    reconcile_control,
    run_provenance,
    scope_view,
    snap,
    starter_dashboard,
    update_widget,
    validate_dashboard,
    widget,
    connect_widgets,
    remove_widget,
)


def _instrument_icon(kind, palette, size=20):
    """Draw small theme-aware instrument glyphs without bundled image assets."""
    bitmap = wx.Bitmap(size, size, 32)
    dc = wx.MemoryDC(bitmap)
    dc.SetBackground(wx.Brush(palette['panel']))
    dc.Clear()
    dc.SetPen(wx.Pen(palette['accent'], 2))
    dc.SetBrush(wx.TRANSPARENT_BRUSH)
    if kind == 'Meter':
        dc.DrawArc(3, 15, 17, 15, 10, 10)
        dc.DrawLine(10, 14, 15, 7)
    elif kind == 'Scope':
        dc.DrawRectangle(2, 3, 16, 14)
        dc.DrawLines([wx.Point(4, 11), wx.Point(7, 11), wx.Point(9, 6), wx.Point(12, 14), wx.Point(16, 8)])
    elif kind == 'Indicator':
        dc.SetBrush(wx.Brush(palette['accent']))
        dc.DrawCircle(10, 10, 5)
    elif kind in ('Diagram block','Note'):
        dc.DrawRectangle(4,4,12,12)
        if kind=='Diagram block':dc.DrawLine(0,10,4,10);dc.DrawLine(16,10,20,10)
        else:dc.DrawLine(6,8,14,8);dc.DrawLine(6,12,12,12)
    else:
        dc.DrawLine(10, 2, 10, 8)
        dc.DrawArc(3, 7, 17, 7, 10, 10)
    dc.SelectObject(wx.NullBitmap)
    return bitmap


def _action_button(parent, label, tooltip, handler, bitmap=None):
    button = ActionButton(parent, label=label)
    button.SetName(label)
    button.SetToolTip(tooltip)
    if bitmap is not None:
        button.SetBitmap(bitmap)
    button.Bind(wx.EVT_BUTTON, handler)
    return button

class DashboardPanel(wx.Panel):
    def __init__(self,owner,parent=None):
        super().__init__(parent or owner.book)
        self.owner = owner
        self.selected = None
        self.drag = None
        self.mode = 'Design'
        self.pending = {}
        self.connect_from=None
        self._instrument_ids = []
        self._narrow = None

        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)
        bar = wx.WrapSizer(wx.HORIZONTAL)
        outer.Add(bar, 0, wx.EXPAND | wx.ALL, 8)
        bar.Add(wx.StaticText(self, label='Mode'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.mode_choice = wx.Choice(self, choices=['Design', 'Run'])
        self.mode_choice.SetName('Dashboard mode')
        self.mode_choice.SetSelection(0)
        self.mode_choice.SetToolTip('Design edits layout; Run reads the selected acquired simulation')
        bar.Add(self.mode_choice, 0, wx.RIGHT, 14)
        self.mode_choice.Bind(wx.EVT_CHOICE, self.change_mode)

        bar.Add(wx.StaticText(self, label='Instruments'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.palette_buttons = {}
        for kind, label, tooltip in INSTRUMENT_ACTIONS:
            button = _action_button(
                self,
                label,
                tooltip,
                lambda event, value=kind: owner.guarded(lambda: self.add(value)),
                _instrument_icon(kind, owner.palette),
            )
            self.palette_buttons[kind] = button
            bar.Add(button, 0, wx.RIGHT, 4)

        bar.AddStretchSpacer()
        self.connect_button=_action_button(self,'Connect','Select an item, then Connect, then click a target. Visual links only.',lambda e:owner.guarded(self.begin_connect))
        bar.Add(self.connect_button,0,wx.RIGHT,4)
        self.unlink_button=_action_button(self,'Unlink','Remove connectors attached to the selected item',lambda e:owner.guarded(self.unlink))
        bar.Add(self.unlink_button,0,wx.RIGHT,4)
        self.mapping_button=_action_button(self,'DUT mapping','Define a future hardware pin mapping; hardware remains disconnected',lambda e:owner.guarded(self.map_dut))
        bar.Add(self.mapping_button,0,wx.RIGHT,4)
        self.inspector_button = ActionButton(self, label='Inspector', toggle=True)
        self.inspector_button.SetName('Show dashboard inspector')
        self.inspector_button.SetValue(True)
        self.inspector_button.SetToolTip('Show or hide instrument properties')
        self.inspector_button.Bind(wx.EVT_TOGGLEBUTTON, self.toggle_inspector)
        bar.Add(self.inspector_button, 0, wx.LEFT, 8)

        from .themes import toolbar_icon
        self.start_button = _action_button(
            self, 'Start', 'Start a native continuous simulation (best effort, not HIL)',
            lambda event: owner.guarded(self.start), toolbar_icon('run.start', owner.palette),
        )
        self.pause_button = _action_button(
            self, 'Pause / resume', 'Request pause or resume at a native step boundary',
            lambda event: owner.guarded(owner.pause_run), toolbar_icon('run.pause', owner.palette),
        )
        self.stop_button = _action_button(
            self, 'Stop', 'Request stop and wait for the owned worker step boundary',
            lambda event: owner.guarded(owner.stop_run), toolbar_icon('run.stop', owner.palette),
        )
        # The application run bar is the single visible run-control surface.
        # Keep these controls alive for compatibility with automation and state
        # tests, but do not duplicate them in the dashboard toolbar.
        for button in (self.start_button, self.pause_button, self.stop_button):
            button.Hide()

        self.status = wx.StaticText(
            self,
            label='Design mode - add, select, drag, or resize instruments.',
        )
        self.status.Wrap(900)
        outer.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)
        self.run_state = wx.StaticText(self, label='Idle - no acquired data')
        outer.Add(self.run_state, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)
        self.provenance = wx.StaticText(
            self,
            label='Data source: disconnected - no acquired run | Hardware I/O: disconnected (simulation only)',
        )
        self.provenance.Wrap(900)
        self.provenance.Hide()

        self.body = wx.BoxSizer(wx.HORIZONTAL)
        outer.Add(self.body, 1, wx.EXPAND)
        self.canvas=wx.ScrolledWindow(self,style=wx.HSCROLL|wx.VSCROLL);self.canvas.SetScrollRate(20,20);self.canvas.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.canvas.SetName('Dashboard canvas')
        self.body.Add(self.canvas,1,wx.EXPAND)
        self.canvas.Bind(wx.EVT_PAINT,self.paint);self.canvas.Bind(wx.EVT_LEFT_DOWN,self.down);self.canvas.Bind(wx.EVT_MOTION,self.motion);self.canvas.Bind(wx.EVT_LEFT_UP,self.up)
        self.canvas.Bind(wx.EVT_MOUSE_CAPTURE_LOST,lambda e:setattr(self,'drag',None));self.canvas.Bind(wx.EVT_LEFT_DCLICK,self.double_click)
        self.canvas.Bind(wx.EVT_SCROLLWIN, self.canvas_scrolled)
        self.canvas.Bind(wx.EVT_SIZE, self.canvas_sized)
        from .dashboard_context import context
        self.canvas.Bind(wx.EVT_CONTEXT_MENU,lambda e:context(self,e))

        self.empty_title = wx.StaticText(self.canvas, label='Build a simulation dashboard')
        self.empty_detail = wx.StaticText(
            self.canvas,
            label='Acquire a run to create starter instruments from its real signals, or add an unbound instrument above.',
        )
        self.empty_detail.Wrap(430)
        self.starter_button = _action_button(
            self.canvas, 'Create starter scope + meter',
            'Create two instruments bound to signals in the selected acquired run',
            lambda event: owner.guarded(self.create_starters), _instrument_icon('Scope', owner.palette),
        )
        self.canvas_control = wx.TextCtrl(self.canvas, value='0', style=wx.TE_PROCESS_ENTER)
        self.canvas_control.SetName('Selected source value in SI units')
        self.canvas_control.SetToolTip('Finite value within the selected source control limits')
        self.canvas_send = _action_button(
            self.canvas, 'Apply next step',
            'Queue this value; acknowledgement appears only after the native session accepts it at a step boundary',
            lambda event: owner.guarded(lambda: self.command(self.canvas_control)),
        )

        side=wx.ScrolledWindow(self,style=wx.VSCROLL | wx.BORDER_SIMPLE);side.SetScrollRate(0,12);self.side=side
        s=wx.BoxSizer(wx.VERTICAL);side.SetSizer(s);self.body.Add(side,0,wx.EXPAND|wx.ALL,10)
        inspector_title=wx.StaticText(side,label='Inspector')
        inspector_title.SetFont(wx.Font(11,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_BOLD))
        s.Add(inspector_title,0,wx.ALL,12)
        self.instrument_list=wx.Choice(side,size=(240,-1));self.instrument_list.SetName('Instrument selection')
        self.instrument_list.SetToolTip('Select an instrument for canvas focus and property editing')
        self.instrument_list.Bind(wx.EVT_CHOICE,self.select_from_list);s.Add(self.instrument_list,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM,12)
        add_row=wx.BoxSizer(wx.HORIZONTAL)
        self.kind=wx.Choice(side,choices=list(KINDS));self.kind.SetSelection(0);self.kind.SetName('Instrument kind')
        add_row.Add(self.kind,1,wx.RIGHT,5)
        self.add_button=_action_button(side,'Add selected','Add the selected instrument kind to the canvas',lambda e:owner.guarded(self.add))
        add_row.Add(self.add_button,0);s.Add(add_row,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM,12)
        self.fields={}
        for key,label in [('title','Title'),('expression','Signal / expression'),('source','DC source reference'),('minimum','Low limit / control minimum'),('maximum','High limit / control maximum')]:
            s.Add(wx.StaticText(side,label=label),0,wx.LEFT|wx.RIGHT|wx.TOP,12)
            field=wx.TextCtrl(side,size=(240,-1));field.SetName(label);self.fields[key]=field;s.Add(field,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        s.Add(wx.StaticText(side,label='Signals from selected run'),0,wx.LEFT|wx.RIGHT|wx.TOP,12)
        self.signals=wx.Choice(side,size=(240,-1));self.signals.SetName('Recorded signal')
        self.signals.SetToolTip('Bind the selected real signal to this instrument')
        s.Add(self.signals,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12);self.signals.Bind(wx.EVT_CHOICE,lambda e:self.fields['expression'].SetValue(self.signals.GetStringSelection()))
        self.apply_button=_action_button(side,'Apply properties','Commit this instrument configuration as one undoable edit',lambda e:owner.guarded(self.apply))
        s.Add(self.apply_button,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP,12)
        self.delete_button=_action_button(side,'Delete instrument','Delete the selected instrument as one undoable edit',lambda e:owner.guarded(self.delete))
        s.Add(self.delete_button,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP,6)
        s.Add(wx.StaticText(side,label='Run control value (SI units)'),0,wx.LEFT|wx.RIGHT|wx.TOP,22)
        self.control=wx.TextCtrl(side,value='0',style=wx.TE_PROCESS_ENTER);self.control.SetName('Run control value in SI units');s.Add(self.control,0,wx.EXPAND|wx.LEFT|wx.RIGHT,12)
        self.send=_action_button(side,'Apply at next native step','Queue the selected DC source value and wait for a recorded native-step acknowledgement',lambda e:owner.guarded(self.command))
        s.Add(self.send,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP,6)
        self.control.Bind(wx.EVT_TEXT,lambda e:self.canvas_control.ChangeValue(self.control.GetValue()))
        self.canvas_control.Bind(wx.EVT_TEXT,lambda e:self.control.ChangeValue(self.canvas_control.GetValue()))
        self.control.Bind(wx.EVT_TEXT_ENTER,lambda e:owner.guarded(self.command))
        self.canvas_control.Bind(wx.EVT_TEXT_ENTER,lambda e:owner.guarded(lambda:self.command(self.canvas_control)))
        self.send.Disable();self.control.Disable()
        report=_action_button(side,'Interactive result report...','Open the offline report for the acquired snapshot',lambda e:owner.execute_command('view.offline_report'))
        s.Add(report,0,wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP,8)
        note=wx.StaticText(side,label='Source controls apply only to simulated DC sources. An applied value always has a matching native-step acknowledgement.');note.Wrap(216);s.Add(note,0,wx.ALL,12)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,self.tick,self.timer);self.timer.Start(200)
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroy);self.Bind(wx.EVT_SIZE,self.on_size)
        self.refresh();self.change_mode()

    def destroy(self,event):
        if event.GetEventObject() is self:self.timer.Stop()
        event.Skip()
    def data(self):return self.owner.doc.data.get('dashboard',empty_dashboard())
    def commit(self,data):
        validate_dashboard(data);self.owner.doc.commit(lambda d:d.update(dashboard=deepcopy(data)));self.owner.update_title();self.refresh()
    def on_size(self,event):
        self._set_narrow(event.GetSize().width < 780)
        event.Skip()
    def _set_narrow(self,narrow):
        if narrow==self._narrow:return
        self._narrow=narrow
        self.body.SetOrientation(wx.VERTICAL if narrow else wx.HORIZONTAL)
        self.side.SetMinSize((260,280) if narrow else (260,-1))
        self.status.Wrap(max(260,self.GetClientSize().width-30));self.provenance.Wrap(max(260,self.GetClientSize().width-30))
        self.Layout()
    def toggle_inspector(self,event=None):
        shown=self.inspector_button.GetValue()
        self.side.Show(shown)
        self.inspector_button.SetToolTip(('Hide' if shown else 'Show')+' instrument properties')
        self.body.Layout();self.Layout()
    def canvas_scrolled(self,event):
        event.Skip();wx.CallAfter(self.position_overlays)
    def canvas_sized(self,event):
        event.Skip();wx.CallAfter(self.position_overlays)
    def refresh(self):
        rows=self.data()['widgets'];self.canvas.SetVirtualSize((max([1000]+[int(r['x']+r['width']+40) for r in rows]),max([700]+[int(r['y']+r['height']+40) for r in rows])))
        if not any(r['id']==self.selected for r in rows):self.selected=None
        self._instrument_ids=[row['id'] for row in rows]
        labels=[f"{index+1}. {row['title'] or row['kind']} [{row['kind']}]" for index,row in enumerate(rows)]
        if labels!=list(self.instrument_list.GetItems()):self.instrument_list.Set(labels)
        if self.selected in self._instrument_ids:self.instrument_list.SetSelection(self._instrument_ids.index(self.selected))
        else:self.instrument_list.SetSelection(wx.NOT_FOUND)
        self.canvas.Refresh();self.position_overlays();self._enable_edit_controls()
    def selected_row(self):return next((r for r in self.data()['widgets'] if r['id']==self.selected),None)
    def select_from_list(self,event=None):
        index=self.instrument_list.GetSelection()
        ident=self._instrument_ids[index] if 0<=index<len(self._instrument_ids) else None
        self.select(next((row for row in self.data()['widgets'] if row['id']==ident),None))
    def select(self,row):
        self.selected=row['id'] if row else None
        for key,field in self.fields.items():field.ChangeValue(str(row[key]) if row else '')
        if self.selected in self._instrument_ids:self.instrument_list.SetSelection(self._instrument_ids.index(self.selected))
        else:self.instrument_list.SetSelection(wx.NOT_FOUND)
        self._enable_edit_controls();self.position_overlays();self.canvas.Refresh()
    def _enable_edit_controls(self):
        editing=self.mode=='Design';selected=self.selected_row() is not None
        for control in [self.add_button,self.kind,*self.palette_buttons.values()]:control.Enable(editing)
        for control in [self.apply_button,self.delete_button,*self.fields.values(),self.signals,self.connect_button,self.unlink_button,self.mapping_button]:control.Enable(editing and selected)
    def map_dut(self):
        from .dashboard_dut import edit_binding
        edit_binding(self)
    def begin_connect(self):
        if self.mode!='Design' or not self.selected:raise ValueError('Select an item in Design mode first')
        self.connect_from=self.selected;self.status.SetLabel('Click a target to add a visual connector; click empty space to cancel. Not an electrical net.')
    def unlink(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        data=deepcopy(self.data());data['connections']=[c for c in data.get('connections',[]) if self.selected not in (c['from'],c['to'])];self.commit(data)
    def add(self,kind=None):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        data=deepcopy(self.data());row=widget(kind or self.kind.GetStringSelection())
        rows=data['widgets']
        if rows:
            last=rows[-1];row['x']=last['x']+last['width']+20;row['y']=last['y']
            if row['x']+row['width']+20>max(600,self.canvas.GetClientSize().width):
                row['x']=20;row['y']=max(r['y']+r['height'] for r in rows)+20
        data['widgets'].append(row);self.commit(data);self.select(row)
    def create_starters(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        if self.data()['widgets']:raise ValueError('Starter instruments are available only on an empty dashboard')
        data=starter_dashboard(self.owner.math,self.canvas.GetClientSize().width)
        self.commit(data);self.select(data['widgets'][0])
    def apply(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        changes={k:f.GetValue() for k,f in self.fields.items()};changes['minimum']=float(changes['minimum']);changes['maximum']=float(changes['maximum'])
        self.commit(update_widget(self.data(),self.selected,**changes))
    def delete(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        self.commit(remove_widget(self.data(),self.selected));self.connect_from=None;self.select(None)
    def change_mode(self,event=None):
        self.mode=self.mode_choice.GetStringSelection()
        self.connect_from=None
        self._enable_edit_controls()
        self.status.SetLabel('Design mode - add, select, drag, or resize instruments.' if self.mode=='Design' else 'Run mode - displaying the selected acquired run.')
        self.canvas.Refresh()
        self.position_overlays();self.tick()
    def start(self):
        self.owner.start_interactive()
        index=self.owner.book.FindPage(self)
        if index!=wx.NOT_FOUND:self.owner.book.SetSelection(index)
    def command(self,value_control=None):
        if self.mode!='Run':raise ValueError('Switch dashboard to Run mode first')
        row=self.selected_row()
        if not row or row['kind']!='Source control':raise ValueError('Select a Source control instrument')
        value=float((value_control or self.control).GetValue())
        if not np.isfinite(value) or not row['minimum']<=value<=row['maximum']:raise ValueError('Control value is outside its configured finite limits')
        from .run_control import InteractiveRun
        session=self.owner.active_run
        if not isinstance(session,InteractiveRun):raise ValueError('Start a continuous simulation first')
        snapshot=session.snapshot();events=snapshot.get('provenance',{}).get('control_events',[]) if snapshot else []
        session.set_source(row['source'],value)
        self.pending[row['id']]={'source':row['source'],'value':value,'event_index':len(events),'session':id(session),
                                 'event_cursor':None if not events else (events[-1].get('time_s'),events[-1].get('source'),events[-1].get('value'),events[-1].get('origin')),
                                 'label':f'Queued {value:g}; waiting for native-step acknowledgement'}
        self.status.SetLabel(self.pending[row['id']]['label']);self.canvas.Refresh()
    def tick(self,event=None):
        from .run_control import InteractiveRun
        session=self.owner.active_run;row=self.selected_row()
        enabled=self.mode=='Run' and isinstance(session,InteractiveRun) and session.state in ('starting','running','paused') and row is not None and row['kind']=='Source control'
        self.send.Enable(enabled);self.control.Enable(enabled);self.canvas_send.Enable(enabled);self.canvas_control.Enable(enabled)
        interactive=isinstance(session,InteractiveRun);state=getattr(session,'state','idle') if session else 'idle'
        self.pause_button.Enable(interactive and state in ('starting','running','paused'))
        self.stop_button.Enable(session is not None and state not in ('completed','failed','stopped'))
        self.start_button.Enable(session is None or state in ('completed','failed','stopped'))
        sample=f't = {float(self.owner.math.time[-1]):.7g} s | {len(self.owner.math.time):,} retained samples' if self.owner.math is not None and len(self.owner.math.time) else 'no acquired data'
        self.run_state.SetLabel(f'{state.capitalize()} - {sample}')
        snapshot=session.snapshot() if interactive else None
        provenance=run_provenance(getattr(self.owner,'result',None),snapshot,state)
        self.provenance.SetLabel(provenance)
        self.run_state.SetToolTip(provenance)
        if snapshot:self._reconcile_pending(session,snapshot)
        if interactive and state in ('failed','stopped'):self._close_unacknowledged(session,state)
        names=list(self.owner.math.signals) if self.owner.math else []
        if names!=list(self.signals.GetItems()):self.signals.Set(names)
        self.position_overlays()
        if self.IsShownOnScreen():self.canvas.Refresh()
    def _reconcile_pending(self,session,snapshot):
        events=snapshot.get('provenance',{}).get('control_events',[])
        for ident,pending in self.pending.items():
            if pending.get('session')!=id(session):continue
            accepted=reconcile_control(pending,events)
            if accepted:
                pending['label']=f"Applied {float(accepted['value']):g} at t={float(accepted['time_s']):.7g} s (native step acknowledged)"
                pending['acknowledged']=True
                if ident==self.selected:self.status.SetLabel(pending['label'])
    def _close_unacknowledged(self,session,state):
        for pending in self.pending.values():
            if pending.get('session')==id(session) and not pending.get('acknowledged'):
                pending['label']=f'Not acknowledged before session {state}'
    def position_overlays(self):
        rows=self.data()['widgets'];empty=not rows
        can_start=empty and self.mode=='Design' and self.owner.math is not None and bool(self.owner.math.signals)
        for control in (self.empty_title,self.empty_detail,self.starter_button):control.Show(empty)
        self.starter_button.Enable(can_start)
        if empty:
            width=max(260,self.canvas.GetClientSize().width)
            self.empty_title.SetPosition((max(20,(width-self.empty_title.GetBestSize().width)//2),100))
            self.empty_detail.SetSize((min(430,width-40),-1));self.empty_detail.Wrap(min(430,width-40))
            self.empty_detail.SetPosition((max(20,(width-self.empty_detail.GetSize().width)//2),135))
            self.starter_button.SetSize(self.starter_button.GetBestSize())
            self.starter_button.SetPosition((max(20,(width-self.starter_button.GetBestSize().width)//2),205))
        row=self.selected_row();show_control=self.mode=='Run' and row is not None and row['kind']=='Source control'
        self.canvas_control.Show(show_control);self.canvas_send.Show(show_control)
        if show_control:
            x,y=self.canvas.CalcScrolledPosition(int(row['x']+12),int(row['y']+78))
            inner=max(80,int(row['width'])-24)
            if inner>=240:
                control_width=min(150,inner-131)
                self.canvas_control.SetSize((control_width,28));self.canvas_control.SetPosition((x,y))
                self.canvas_send.SetSize((125,28));self.canvas_send.SetPosition((x+control_width+6,y))
            else:
                x,y=self.canvas.CalcScrolledPosition(int(row['x']+12),int(row['y']+52))
                self.canvas_control.SetSize((inner,26));self.canvas_control.SetPosition((x,y))
                self.canvas_send.SetSize((inner,26));self.canvas_send.SetPosition((x,y+30))
        self.canvas.Layout()
    def position(self,event):return self.canvas.CalcUnscrolledPosition(event.GetPosition())
    def down(self,event):
        p=self.position(event);row=next((r for r in reversed(self.data()['widgets']) if wx.Rect(int(r['x']),int(r['y']),int(r['width']),int(r['height'])).Contains(p)),None)
        if self.connect_from:
            source=self.connect_from;self.connect_from=None
            if row:self.owner.guarded(lambda:self.commit(connect_widgets(self.data(),source,row['id'])))
            self.status.SetLabel('Design mode - visual connector editing finished.');return
        self.select(row)
        if row and self.mode=='Design':self.drag=(p,deepcopy(row),p.x>row['x']+row['width']-20 and p.y>row['y']+row['height']-20);self.drag_point=p;self.canvas.CaptureMouse()
    def motion(self,event):
        if self.drag and event.Dragging():self.drag_point=self.position(event);self.canvas.Refresh()
    def preview(self):
        if not self.drag:return None
        p,row,resize=self.drag;now=self.drag_point;dx,dy=now.x-p.x,now.y-p.y
        if resize:return dict(width=min(2000,snap(row['width']+dx,180)),height=min(2000,snap(row['height']+dy,120)))
        return dict(x=min(20000,snap(row['x']+dx)),y=min(20000,snap(row['y']+dy)))
    def up(self,event):
        if not self.drag:return
        self.drag_point=self.position(event);changes=self.preview();ident=self.drag[1]['id'];self.drag=None
        if self.canvas.HasCapture():self.canvas.ReleaseMouse()
        self.owner.guarded(lambda:self.commit(update_widget(self.data(),ident,**changes)))
    def double_click(self,event):
        self.fields['title'].SetFocus() if self.mode=='Design' else self.control.SetFocus()
    def paint(self,event):
        dc=wx.AutoBufferedPaintDC(self.canvas);self.canvas.PrepareDC(dc);p=self.owner.palette
        dc.SetBackground(wx.Brush(p['canvas']));dc.Clear()
        width,height=self.canvas.GetVirtualSize()
        dc.SetPen(wx.Pen(p['grid'],1))
        for xx in range(20,width+1,40):
            for yy in range(20,height+1,40):dc.DrawPoint(xx,yy)
        dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
        diagram_rows={r['id']:r | ((self.preview() or {}) if self.drag and self.drag[1]['id']==r['id'] else {}) for r in self.data()['widgets']}
        dc.SetPen(wx.Pen(p['accent'],2));dc.SetBrush(wx.Brush(p['accent']))
        for link in self.data().get('connections',[]):
            source,target=diagram_rows[link['from']],diagram_rows[link['to']]
            x1,y1=int(source['x']+source['width']),int(source['y']+source['height']/2)
            x2,y2=int(target['x']),int(target['y']+target['height']/2);middle=(x1+x2)//2
            dc.DrawLines([wx.Point(x1,y1),wx.Point(middle,y1),wx.Point(middle,y2),wx.Point(x2,y2)])
            dc.DrawCircle(x1,y1,3);dc.DrawPolygon([wx.Point(x2,y2),wx.Point(x2-7,y2-4),wx.Point(x2-7,y2+4)])
        for original in self.data()['widgets']:
            dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
            row=original | ((self.preview() or {}) if self.drag and self.drag[1]['id']==original['id'] else {})
            x,y,w,h=[int(row[k]) for k in ('x','y','width','height')]
            dc.SetPen(wx.Pen(p['accent'] if row['id']==self.selected else p['grid'],2 if row['id']==self.selected else 1));dc.SetBrush(wx.Brush(p['panel']));dc.DrawRoundedRectangle(x,y,w,h,8)
            dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_BOLD))
            dc.SetTextForeground(p['fg']);dc.DrawText(row['title'][:40],x+12,y+10)
            dc.SetFont(wx.Font(9,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
            binding='Visual diagram only' if row['kind'] in ('Diagram block','Note') else row['expression'] if row['kind']!='Source control' else row['source'] or 'Bind a DC source'
            dc.SetTextForeground(p['muted']);dc.DrawText(f"{row['kind']}  /  {binding}"[:58],x+12,y+32)
            try:
                if row['kind'] in ('Diagram block','Note'):
                    rect=wx.Rect(x+12,y+55,w-24,h-75);dc.SetClippingRegion(rect);dc.DrawLabel(row['expression'] or 'Double-click to edit description',rect,wx.ALIGN_LEFT);dc.DestroyClippingRegion()
                elif row['kind']=='Source control':
                    pending=self.pending.get(row['id'])
                    label=pending['label'] if pending else 'Select this control in Run mode to set a bounded SI value'
                    if not (self.mode=='Run' and row['id']==self.selected and w<264):dc.DrawText(label[:68],x+12,y+56)
                    if not (self.mode=='Run' and row['id']==self.selected and h<150):
                        dc.DrawText(f"Allowed: {row['minimum']:.7g} to {row['maximum']:.7g} SI | simulation source only"[:68],x+12,y+h-26)
                else:
                    time,values,unit=read_signal(self.owner.math,row['expression']);latest=float(values[-1]);alarm=not row['minimum']<=latest<=row['maximum']
                    dc.SetTextForeground(p['danger'] if alarm else p['accent'])
                    from matplotlib.ticker import EngFormatter
                    dc.SetFont(wx.Font(20 if row['kind']=='Meter' else 12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_BOLD));dc.DrawText(EngFormatter(unit=unit,places=4)(latest),x+12,y+54)
                    dc.SetFont(wx.Font(9,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
                    dc.SetTextForeground(p['muted'])
                    if row['kind']=='Meter':self._draw_meter(dc,row,latest,unit,p,x,y,w,h,alarm)
                    elif row['kind']=='Indicator':self._draw_indicator(dc,row,latest,unit,p,x,y,w,h,alarm)
                    elif row['kind']=='Scope' and len(values)>1:self._draw_scope(dc,row,time,values,unit,p,x,y,w,h)
                    dc.DrawText(f't = {float(time[-1]):.6g} s | selected acquired run',x+12,y+h-23)
            except (ValueError,KeyError,TypeError) as error:
                dc.SetTextForeground(p['muted']);dc.DrawText(str(error)[:42],x+12,y+65)
            if row.get('dut_binding'):
                binding=row['dut_binding'];dc.SetTextForeground(p['muted'])
                dc.DrawText(f"DUT draft: {binding['connector']}.{binding['pin']} / {binding['gpio']} (disconnected)"[:55],x+12,y+h-42)
            if self.mode=='Design':dc.SetBrush(wx.Brush(p['accent']));dc.DrawRectangle(x+w-12,y+h-12,7,7)

    def _draw_meter(self,dc,row,latest,unit,p,x,y,w,h,alarm):
        left,right=x+14,x+w-14;top=y+96
        dc.SetPen(wx.Pen(p['grid'],1));dc.SetBrush(wx.Brush(p['field']));dc.DrawRoundedRectangle(left,top,max(1,right-left),14,4)
        fraction=meter_fraction(latest,row['minimum'],row['maximum'])
        dc.SetPen(wx.TRANSPARENT_PEN);dc.SetBrush(wx.Brush(p['danger'] if alarm else p['accent']))
        fill=round((right-left-4)*fraction)
        if fill>0:dc.DrawRoundedRectangle(left+2,top+2,fill,10,3)
        dc.SetTextForeground(p['muted']);dc.DrawText(f"{row['minimum']:.5g}",left,top+20)
        high=f"{row['maximum']:.5g} {unit}";extent=dc.GetTextExtent(high)[0];dc.DrawText(high,max(left,right-extent),top+20)

    def _draw_indicator(self,dc,row,latest,unit,p,x,y,w,h,alarm):
        dc.SetPen(wx.Pen(p['danger'] if alarm else p['accent'],2));dc.SetBrush(wx.Brush(p['danger'] if alarm else p['accent']))
        dc.DrawCircle(x+22,y+98,8);dc.SetTextForeground(p['danger'] if alarm else p['accent'])
        dc.DrawText('OUTSIDE CONFIGURED LIMITS' if alarm else 'WITHIN CONFIGURED LIMITS',x+40,y+90)

    def _draw_scope(self,dc,row,time,values,unit,p,x,y,w,h):
        plot_x,plot_y=x+48,y+88;plot_w=max(40,w-62);plot_h=max(30,h-132)
        view=scope_view(time,values,plot_w)
        dc.SetPen(wx.Pen(p['grid'],1));dc.SetBrush(wx.Brush(p['field']));dc.DrawRectangle(plot_x,plot_y,plot_w,plot_h)
        for part in (1,2,3):
            yy=plot_y+round(plot_h*part/4);dc.DrawLine(plot_x,yy,plot_x+plot_w,yy)
        low,high=view['display_minimum'],view['display_maximum'];span=high-low
        def y_value(value):return plot_y+plot_h-round((value-low)/span*plot_h)
        for limit in (row['minimum'],row['maximum']):
            if low<=limit<=high:
                dc.SetPen(wx.Pen(p['danger'],1,wx.PENSTYLE_SHORT_DASH));yy=y_value(limit);dc.DrawLine(plot_x,yy,plot_x+plot_w,yy)
        dc.SetClippingRegion(plot_x,plot_y,plot_w,plot_h);dc.SetPen(wx.Pen(p['accent'],1))
        guide=[]
        for index,minimum,maximum in view['bins']:
            xx=plot_x+index;dc.DrawLine(xx,y_value(minimum),xx,y_value(maximum))
            guide.append(wx.Point(xx,y_value(.5*(minimum+maximum))))
        # A display guide joins envelope centers; exact extrema remain drawn
        # and all instrument measurements still use the original samples.
        if len(guide)>1:dc.DrawLines(guide)
        dc.DestroyClippingRegion();dc.SetTextForeground(p['muted'])
        dc.DrawText(f"{view['maximum']:.4g}",x+5,plot_y-5);dc.DrawText(f"{view['minimum']:.4g}",x+5,plot_y+plot_h-12)
        dc.DrawText(f"{view['time_start']:.4g}s",plot_x,plot_y+plot_h+3)
        end=f"{view['time_end']:.4g}s";dc.DrawText(end,plot_x+plot_w-dc.GetTextExtent(end)[0],plot_y+plot_h+3)


def verify_dashboard(frame,destination):
    """Self-closing evidence run: real RC solve, UI bindings, mouse layout, no fabricated curves."""
    from pathlib import Path
    import time as clock
    from .document import Document,RC_DECK,write_json
    from .run_control import native_batch
    from .signal_math import SignalMath
    from .ui_evidence import capture_window
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={};state={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def cleanup(error=None):
        if error is not None:
            frame.validation_failure=True;write_json(destination/'error.json',{'error':str(error),'checks':checks})
        session=state.get('session')
        if session:session.stop()
        state['cleanup_deadline']=clock.monotonic()+5
        def finish():
            if session and session.thread.is_alive() and clock.monotonic()<state['cleanup_deadline']:
                wx.CallLater(30,finish);return
            if session and session.thread.is_alive():
                frame.validation_failure=True;write_json(destination/'error.json',{'error':'Continuous worker failed to stop within five seconds','checks':checks})
            elif error is None:
                check(not session or session.state=='stopped','continuous worker stops cleanly')
                write_json(destination/'checks.json',checks)
            frame.timer.Stop();frame.Destroy()
        finish()
    def poll():
        try:
            session=state['session'];panel=frame.dashboard_panel
            if session.state=='failed':raise AssertionError(session.error)
            if clock.monotonic()>state['deadline']:raise AssertionError('Timed out waiting for '+state['phase'])
            snapshot=session.snapshot()
            if state['phase']=='changed':
                values=snapshot and snapshot['data']['node_voltage_v'].get('in',[])
                if values and abs(values[-1]-2)<1e-9:
                    check(True,'dashboard command changes actual native input voltage to 2 V')
                    check(any(e['source']=='V1' and e['value']==2 for e in snapshot['provenance']['control_events']),'native source-change event recorded')
                    frame.math=SignalMath.from_result(snapshot);panel.tick()
                    frame.pause_run();state['phase']='paused'
            elif state['phase']=='paused' and session.state=='paused':
                state['frozen']=session.total_samples;state['pause_until']=clock.monotonic()+.12;state['phase']='held'
            elif state['phase']=='held' and clock.monotonic()>=state['pause_until']:
                check(session.total_samples==state['frozen'],'pause holds acquired sample count stable')
                frame.pause_run();state['phase']='resumed'
            elif state['phase']=='resumed' and session.state=='running' and session.total_samples>state['frozen']:
                check(True,'resume advances native simulation samples')
                snapshot=session.snapshot();frame.math=SignalMath.from_result(snapshot);panel.tick()
                panel.canvas.Refresh();panel.canvas.Update();capture_window(frame,destination/'dashboard-live-source-control.png')
                write_json(destination/'continuous-native-result.json',snapshot)
                frame.stop_run();cleanup();return
            wx.CallLater(30,poll)
        except Exception as error:cleanup(error)
    def run():
        try:
            frame.set_theme('Dark',save=False)
            frame.doc=Document.from_netlist(RC_DECK);frame.refresh_document(force_source=True)
            panel=frame.dashboard_panel;frame.book.SetSelection(frame.book.FindPage(panel))
            panel.kind.SetStringSelection('Meter');panel.add();panel.fields['title'].SetValue('Output voltage');panel.fields['expression'].SetValue('v(out)');panel.apply()
            meter=deepcopy(panel.selected_row());check(meter['expression']=='v(out)','inspector persists signal binding')
            # Exercise the actual canvas mouse handlers, not a geometry-only stand-in.
            for event_type,point in [(wx.wxEVT_LEFT_DOWN,(40,40)),(wx.wxEVT_LEFT_UP,(100,80))]:
                event=wx.MouseEvent(event_type);event.SetPosition(wx.Point(*point));panel.canvas.GetEventHandler().ProcessEvent(event)
            check(panel.selected_row()['x']==80 and panel.selected_row()['y']==60,'drag snaps and commits position')
            frame.doc.undo();panel.refresh();check(panel.selected_row()['x']==20,'dashboard drag is undoable')
            panel.kind.SetStringSelection('Scope');panel.add();panel.fields['title'].SetValue('RC startup');panel.fields['expression'].SetValue('v(out)');panel.apply()
            result=native_batch(frame.doc.data['source'],frame.library)
            check(result['status']=='completed','RC startup solves in native engine')
            frame.math=SignalMath.from_result(result);time,values,unit=read_signal(frame.math,'v(out)')
            check(abs(float(values[-1])-(1-np.exp(-5)))<.003,'dashboard reading agrees with analytical RC response')
            panel.mode_choice.SetStringSelection('Run');panel.change_mode();panel.tick();check(not panel.send.IsEnabled(),'control disabled without interactive session')
            panel.canvas.Refresh();panel.canvas.Update();wx.Yield();capture_window(frame,destination/'dashboard-native-rc.png')
            panel.mode_choice.SetStringSelection('Design');panel.change_mode()
            panel.kind.SetStringSelection('Source control');panel.add();panel.fields['title'].SetValue('Input supply');panel.fields['source'].SetValue('V1');panel.apply()
            panel.mode_choice.SetStringSelection('Run');panel.change_mode();panel.start()
            state['session']=frame.active_run;check(state['session'] is not None,'dashboard starts real continuous session')
            panel.tick();check(panel.send.IsEnabled(),'source control enabled during continuous Run mode')
            panel.control.SetValue('2');panel.command()
            state['deadline']=clock.monotonic()+15;state['phase']='changed';wx.CallLater(30,poll)
        except Exception as error:cleanup(error)
    wx.CallLater(250,run)
