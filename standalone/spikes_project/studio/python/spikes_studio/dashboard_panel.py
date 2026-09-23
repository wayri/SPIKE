"""Native design/run dashboard with undoable geometry and validated source commands."""
from copy import deepcopy
import wx
import numpy as np
from .dashboard import KINDS,empty_dashboard,widget,validate_dashboard,update_widget,snap,read_signal,scope_bins

class DashboardPanel(wx.Panel):
    def __init__(self,owner,parent=None):
        super().__init__(parent or owner.book)
        self.owner=owner;self.selected=None;self.drag=None;self.mode='Design';self.pending={}
        outer=wx.BoxSizer(wx.VERTICAL);self.SetSizer(outer)
        bar=wx.BoxSizer(wx.HORIZONTAL);outer.Add(bar,0,wx.EXPAND|wx.ALL,8)
        self.mode_choice=wx.Choice(self,choices=['Design','Run']);self.mode_choice.SetSelection(0)
        bar.Add(self.mode_choice,0,wx.RIGHT,12);self.mode_choice.Bind(wx.EVT_CHOICE,self.change_mode)
        self.kind=wx.Choice(self,choices=list(KINDS));self.kind.SetSelection(0);bar.Add(self.kind,0,wx.RIGHT,6)
        self.add_button=wx.Button(self,label='Add instrument');bar.Add(self.add_button,0,wx.RIGHT,6);self.add_button.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.add))
        for title,fn in [('Start continuous',self.start),('Pause / resume',owner.pause_run),('Stop',owner.stop_run)]:
            b=wx.Button(self,label=title);bar.Add(b,0,wx.RIGHT,6);b.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f))
        self.status=wx.StaticText(self,label='Design: add instruments, drag to move; drag bottom-right handle to resize. Double-click to edit.')
        outer.Add(self.status,0,wx.LEFT|wx.RIGHT|wx.BOTTOM,10)
        self.run_state=wx.StaticText(self,label='No acquired data · no hardware I/O connected')
        outer.Add(self.run_state,0,wx.LEFT|wx.RIGHT|wx.BOTTOM,10)
        body=wx.BoxSizer(wx.HORIZONTAL);outer.Add(body,1,wx.EXPAND)
        self.canvas=wx.ScrolledWindow(self,style=wx.HSCROLL|wx.VSCROLL);self.canvas.SetScrollRate(20,20);self.canvas.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        body.Add(self.canvas,1,wx.EXPAND)
        self.canvas.Bind(wx.EVT_PAINT,self.paint);self.canvas.Bind(wx.EVT_LEFT_DOWN,self.down);self.canvas.Bind(wx.EVT_MOTION,self.motion);self.canvas.Bind(wx.EVT_LEFT_UP,self.up)
        self.canvas.Bind(wx.EVT_MOUSE_CAPTURE_LOST,lambda e:setattr(self,'drag',None));self.canvas.Bind(wx.EVT_LEFT_DCLICK,self.double_click)
        side=wx.Panel(self);s=wx.BoxSizer(wx.VERTICAL);side.SetSizer(s);body.Add(side,0,wx.EXPAND|wx.ALL,10)
        s.Add(wx.StaticText(side,label='INSTRUMENT PROPERTIES'),0,wx.BOTTOM,12)
        self.fields={}
        for key,label in [('title','Title'),('expression','Signal / expression'),('source','DC source reference'),('minimum','Low limit / control minimum'),('maximum','High limit / control maximum')]:
            s.Add(wx.StaticText(side,label=label),0,wx.TOP,8)
            field=wx.TextCtrl(side,size=(230,-1));self.fields[key]=field;s.Add(field,0,wx.EXPAND)
        s.Add(wx.StaticText(side,label='Signals from the selected run'),0,wx.TOP,12)
        self.signals=wx.Choice(side,size=(230,-1));s.Add(self.signals,0,wx.EXPAND);self.signals.Bind(wx.EVT_CHOICE,lambda e:self.fields['expression'].SetValue(self.signals.GetStringSelection()))
        self.apply_button=wx.Button(side,label='Apply properties');s.Add(self.apply_button,0,wx.EXPAND|wx.TOP,12);self.apply_button.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.apply))
        self.delete_button=wx.Button(side,label='Delete instrument');s.Add(self.delete_button,0,wx.EXPAND|wx.TOP,6);self.delete_button.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.delete))
        s.Add(wx.StaticText(side,label='Run control value (SI units)'),0,wx.TOP,22)
        self.control=wx.TextCtrl(side,value='0');s.Add(self.control,0,wx.EXPAND)
        self.send=wx.Button(side,label='Queue source value');s.Add(self.send,0,wx.EXPAND|wx.TOP,6);self.send.Bind(wx.EVT_BUTTON,lambda e:owner.guarded(self.command))
        self.send.Disable();self.control.Disable()
        report=wx.Button(side,label='Interactive result report…');s.Add(report,0,wx.EXPAND|wx.TOP,8)
        report.Bind(wx.EVT_BUTTON,lambda e:owner.execute_command('view.offline_report'))
        note=wx.StaticText(side,label='Controls affect independent DC sources in continuous mode only. Queued is not acknowledged. No hardware I/O is connected.');note.Wrap(230);s.Add(note,0,wx.TOP,12)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,self.tick,self.timer);self.timer.Start(200)
        self.Bind(wx.EVT_WINDOW_DESTROY,self.destroy);self.refresh()

    def destroy(self,event):
        if event.GetEventObject() is self:self.timer.Stop()
        event.Skip()
    def data(self):return self.owner.doc.data.get('dashboard',empty_dashboard())
    def commit(self,data):
        validate_dashboard(data);self.owner.doc.commit(lambda d:d.update(dashboard=deepcopy(data)));self.owner.update_title();self.refresh()
    def refresh(self):
        rows=self.data()['widgets'];self.canvas.SetVirtualSize((max([1000]+[int(r['x']+r['width']+40) for r in rows]),max([700]+[int(r['y']+r['height']+40) for r in rows])))
        if not any(r['id']==self.selected for r in rows):self.selected=None
        self.canvas.Refresh()
    def selected_row(self):return next((r for r in self.data()['widgets'] if r['id']==self.selected),None)
    def select(self,row):
        self.selected=row['id'] if row else None
        for key,field in self.fields.items():field.ChangeValue(str(row[key]) if row else '')
        self.canvas.Refresh()
    def add(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        data=deepcopy(self.data());row=widget(self.kind.GetStringSelection())
        rows=data['widgets']
        if rows:
            last=rows[-1];row['x']=last['x']+last['width']+20;row['y']=last['y']
            if row['x']+row['width']+20>max(600,self.canvas.GetClientSize().width):
                row['x']=20;row['y']=max(r['y']+r['height'] for r in rows)+20
        data['widgets'].append(row);self.commit(data);self.select(row)
    def apply(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        changes={k:f.GetValue() for k,f in self.fields.items()};changes['minimum']=float(changes['minimum']);changes['maximum']=float(changes['maximum'])
        self.commit(update_widget(self.data(),self.selected,**changes))
    def delete(self):
        if self.mode!='Design':raise ValueError('Switch to Design mode to edit')
        data=deepcopy(self.data());data['widgets']=[r for r in data['widgets'] if r['id']!=self.selected];self.commit(data);self.select(None)
    def change_mode(self,event=None):
        self.mode=self.mode_choice.GetStringSelection()
        for control in [self.add_button,self.apply_button,self.delete_button,*self.fields.values(),self.kind,self.signals]:control.Enable(self.mode=='Design')
        self.status.SetLabel('Design: drag instruments / resize handles. Layout changes are undoable.' if self.mode=='Design' else 'Run: readings use the selected acquired run. Source changes require a continuous session.')
        self.canvas.Refresh()
        self.tick()
    def start(self):
        self.owner.start_interactive()
        index=self.owner.book.FindPage(self)
        if index!=wx.NOT_FOUND:self.owner.book.SetSelection(index)
    def command(self):
        if self.mode!='Run':raise ValueError('Switch dashboard to Run mode first')
        row=self.selected_row()
        if not row or row['kind']!='Source control':raise ValueError('Select a Source control instrument')
        value=float(self.control.GetValue())
        if not np.isfinite(value) or not row['minimum']<=value<=row['maximum']:raise ValueError('Control value is outside its configured finite limits')
        from .run_control import InteractiveRun
        session=self.owner.active_run
        if not isinstance(session,InteractiveRun):raise ValueError('Start a continuous simulation first')
        session.set_source(row['source'],value)
        self.pending[row['id']]=f'Queued {value:g} (not acknowledged)';self.status.SetLabel(self.pending[row['id']]);self.canvas.Refresh()
    def tick(self,event=None):
        if not self.IsShownOnScreen():return
        from .run_control import InteractiveRun
        session=self.owner.active_run;row=self.selected_row()
        enabled=self.mode=='Run' and isinstance(session,InteractiveRun) and session.state in ('starting','running','paused') and row is not None and row['kind']=='Source control'
        self.send.Enable(enabled);self.control.Enable(enabled)
        state=getattr(session,'state','idle') if session else 'idle'
        sample=f't = {float(self.owner.math.time[-1]):.7g} s · {len(self.owner.math.time):,} retained samples' if self.owner.math is not None and len(self.owner.math.time) else 'no acquired data'
        self.run_state.SetLabel(f'Session: {state} · selected run: {sample} · no hardware I/O')
        names=list(self.owner.math.signals) if self.owner.math else []
        if names!=list(self.signals.GetItems()):self.signals.Set(names)
        self.canvas.Refresh()
    def position(self,event):return self.canvas.CalcUnscrolledPosition(event.GetPosition())
    def down(self,event):
        p=self.position(event);row=next((r for r in reversed(self.data()['widgets']) if wx.Rect(int(r['x']),int(r['y']),int(r['width']),int(r['height'])).Contains(p)),None)
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
        dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
        for original in self.data()['widgets']:
            dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
            row=original | ((self.preview() or {}) if self.drag and self.drag[1]['id']==original['id'] else {})
            x,y,w,h=[int(row[k]) for k in ('x','y','width','height')]
            dc.SetPen(wx.Pen(p['accent'] if row['id']==self.selected else p['grid'],2));dc.SetBrush(wx.Brush(p['panel']));dc.DrawRoundedRectangle(x,y,w,h,10)
            dc.SetTextForeground(p['fg']);dc.DrawText(row['title'][:40],x+12,y+10)
            dc.SetTextForeground(p['muted']);dc.DrawText(row['expression'][:40] if row['kind']!='Source control' else row['source'] or 'Bind a DC source',x+12,y+32)
            try:
                if row['kind']=='Source control':
                    dc.DrawText(self.pending.get(row['id'],'Select → enter value → Queue')[:42],x+12,y+66)
                else:
                    time,values,unit=read_signal(self.owner.math,row['expression']);latest=float(values[-1]);alarm=not row['minimum']<=latest<=row['maximum']
                    dc.SetTextForeground(p['danger'] if alarm else p['accent'])
                    dc.SetFont(wx.Font(20 if row['kind']=='Meter' else 12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_BOLD));dc.DrawText(f'{latest:.7g} {unit}',x+12,y+58)
                    dc.SetFont(wx.Font(10,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL,wx.FONTWEIGHT_NORMAL))
                    dc.SetTextForeground(p['muted']);dc.DrawText(f't = {float(time[-1]):.6g} s · selected run',x+12,y+h-25)
                    if row['kind']=='Indicator':dc.DrawText('OUTSIDE LIMITS' if alarm else 'WITHIN LIMITS',x+12,y+84)
                    if row['kind']=='Scope' and len(values)>1:
                        # Each display bin preserves min and max so narrow switching peaks remain visible.
                        lo=float(np.min(values));hi=float(np.max(values));span=hi-lo or 1.;dc.SetPen(wx.Pen(p['accent']))
                        for i,low,high in scope_bins(time,values,w-28):
                            xx=x+14+i;yy=lambda v:y+h-38-round((v-lo)/span*max(8,h-126))
                            dc.DrawLine(xx,yy(low),xx,yy(high))
            except (ValueError,KeyError,TypeError) as error:
                dc.SetTextForeground(p['muted']);dc.DrawText(str(error)[:42],x+12,y+65)
            if self.mode=='Design':dc.SetBrush(wx.Brush(p['accent']));dc.DrawRectangle(x+w-12,y+h-12,7,7)


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
