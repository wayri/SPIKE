"""Actual-window regression: native stepped RC, split editor and run-aware cursors."""
from pathlib import Path
from types import SimpleNamespace
import time
import wx
from .document import RC_DECK,write_json
from .plot_workspace import cursor_math,instrument_data
from .ui_evidence import capture_window


def verify_workspace(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);checks={};deadline=time.monotonic()+60
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop()
        write_json(destination/'error.json',{'error':str(exc),'checks':checks});frame.timer.Stop();frame.Destroy()
    def dialog_check(callback,name):
        def inspect():
            dialogs=[w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetParent()==frame]
            if not dialogs:return
            dlg=dialogs[-1]
            try:
                if name=='cursor-manager':
                    control=next(w for w in dlg.GetChildren() if isinstance(w,wx.Button) and w.GetLabel()=='Evaluate cursor math')
                    control.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED,control.GetId()))
                    check(any(isinstance(w,wx.TextCtrl) and 'Δt =' in w.GetValue() and 'b-a =' in w.GetValue() for w in dlg.GetChildren()),'cursor dialog Evaluate button computes recorded cross-run math')
                capture_window(dlg,destination/(name+'.png'));check(dlg.IsShown(),name+' is a real themed dialog')
            finally:dlg.EndModal(wx.ID_CLOSE)
        wx.CallLater(200,inspect);callback()
    def begin():
        try:
            frame.source.SetText(RC_DECK.replace('R1 in out 1k','R1 in out {res}').replace('V1 in','.param res=1k\n.step param res list 1k 2k 4k\nV1 in'))
            frame.run();wx.CallLater(150,after_sweep)
        except Exception as exc:fail(exc)
    def after_sweep():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Native sweep timed out')
            if frame.job_running:wx.CallLater(150,after_sweep);return
            check(len(frame.run_results)==3,'three actual native step captures')
            check(frame.run_results[0]['status']=='completed','native step completion')
            frame.traces.clear()
            for expr in ('V(out)','I(R1)'):frame.add_trace(expr)
            frame.overlay_runs.SetValue(True);frame.draw_plot()
            check(len(frame.axes)==2,'voltage and current in linked stacked panes')
            check(len(frame.axes[0].lines)==3,'three step runs overlaid on voltage pane')
            from matplotlib.backend_bases import MouseEvent
            ax=frame.axes[0];before=ax.get_xlim();px,py=ax.transData.transform(((before[0]+before[1])/2,sum(ax.get_ylim())/2))
            event=MouseEvent('scroll_event',frame.plot,px,py,button='up',step=1)
            frame.plot.callbacks.process('scroll_event',event)
            check(ax.get_xlim()[1]-ax.get_xlim()[0]<before[1]-before[0],'real plot wheel event zooms time')
            check(frame.axes[1].get_xlim()==ax.get_xlim(),'wheel zoom keeps stacked time axes linked')
            frame.fit_plot_y();check(hasattr(ax.lines[0],'_spikes_samples'),'visible fit retains original samples')
            frame.draw_plot()
            frame.visible_runs={1};frame.draw_plot();check(len(frame.axes[0].lines)==2,'individual overlay runs can be filtered');frame.visible_runs=None
            frame.put_cursor(.001,0,'V(out)');frame.put_cursor(.002,1,'V(out)');frame.put_cursor(.003,2,'I(R1)');frame.put_cursor(.004,0,'V(out)')
            frame.draw_plot();check(len(frame.cursors)==4,'four linked run-specific cursors')
            value=cursor_math(frame.run_engines,frame.cursor_descriptor(0),frame.cursor_descriptor(1))
            check(abs(value.values)<.004,'equal RC time-constant ratios agree across runs')
            frame.select_run(2);check(frame.selected_run==2 and len(frame.traces)==2,'run selector preserves trace expressions')
            check(frame.cursor_descriptor(0)['run']==0,'run selector does not rebind existing cursors')
            frame.plot_interactions.show_cursors();frame.plot.draw();wx.Yield()
            axis=frame.axes[0];before=frame.cursor_descriptor(0).copy()
            for name,t in [('button_press_event',before['time']),('motion_notify_event',.0015),('button_release_event',.0015)]:
                px,py=axis.transData.transform((t,sum(axis.get_ylim())/2))
                frame.plot.callbacks.process(name,MouseEvent(name,frame.plot,px,py,button=1))
            after=frame.cursor_descriptor(0)
            check(abs(after['time']-.0015)<.00003 and after['run']==before['run'] and after['expression']==before['expression'],'mouse drag moves cursor without rebinding its run or signal')
            check(frame.plot_interactions.table.GetItemCount()==4,'dedicated cursor window lists all four cursors')
            capture_window(frame.plot_interactions.window,destination/'draggable-cursor-window.png');frame.plot_interactions.window.Hide()
            frame.plot_grid=False;frame.grid_control.SetValue(False);frame.draw_plot()
            check(not any(line.get_visible() for line in frame.axes[0].get_xgridlines()),'plot grid really hides')
            frame.toggle_canvas_grid();check(not frame.canvas_grid,'canvas grid toggles separately')
            frame.toggle_split();check(frame.plot_splitter.IsSplit() and frame.canvas.GetParent()==frame.plot_splitter,'actual schematic reparented into resizable split view')
            anchor=frame.doc.data['components'][1]['id']
            items=[{'id':str(i),'anchor':anchor,'kind':kind,'expression':expr,'source':'Selected run','format':'Engineering','frequency_hz':1000,'x':100+i*400,'y':220} for i,(kind,expr) in enumerate([('Readout','V(out)'),('Mini plot','I(R1)')])]
            frame.doc.commit(lambda d:d['instruments'].extend(items));frame.canvas.zoom=.7;frame.canvas.Refresh()
            label,value,curve=instrument_data(frame,items[1]);check(curve is not None and 'Run 3' in label,'embedded waveform reads selected real run')
            frame.plot_splitter.SetSashPosition(300);frame.Layout();capture_window(frame,destination/'split-stepped-cursors.png')
            item=dict(frame.doc.data['instruments'][0]);start=frame.canvas.point(item['x']+10,item['y']+10);end=wx.Point(start.x+28,start.y)
            for kind,point,down in [(wx.wxEVT_LEFT_DOWN,start,True),(wx.wxEVT_MOTION,end,True),(wx.wxEVT_LEFT_UP,end,False)]:
                event=wx.MouseEvent(kind);event.SetPosition(point);event.SetLeftDown(down);frame.canvas.GetEventHandler().ProcessEvent(event)
            check(frame.doc.data['instruments'][0]['x']>item['x'],'instrument drag updates saved canvas coordinates')
            frame.doc.undo();frame.canvas.Refresh();check(frame.doc.data['instruments'][0]['x']==item['x'],'instrument drag is undoable')
            dialog_check(frame.manage_cursors,'cursor-manager');dialog_check(frame.manage_instruments,'instrument-manager')
            frame.toggle_split();check(frame.canvas.GetParent()==frame.schematic_host and not frame.plot_splitter.IsSplit(),'split view restores original editor')
            frame.source.SetText(RC_DECK.replace('.tran 10u 5m uic','.op'));frame.run();wx.CallLater(150,after_op)
        except Exception as exc:fail(exc)
    def after_op():
        try:
            if time.monotonic()>deadline:raise TimeoutError('OP test timed out')
            if frame.job_running:wx.CallLater(150,after_op);return
            check(frame.math is None and frame.result['status']=='completed','actual DC operating point')
            label,value,curve=instrument_data(frame,frame.doc.data['instruments'][0]);check('DC OP' in label and '1.0000 V' in value,'attached OP voltage readout uses native scalar')
            frame.book.SetSelection(0);frame.canvas.Refresh();capture_window(frame,destination/'operating-point-readout.png')
            frame.start_frequency({'source':'V1','output':'V(out)','start_hz':100,'stop_hz':10000,'points':101,'scale':'log','pole_zero':False});wx.CallLater(150,after_ac)
        except Exception as exc:fail(exc)
    def after_ac():
        try:
            if time.monotonic()>deadline:raise TimeoutError('AC readout timed out')
            if frame.job_running:wx.CallLater(150,after_ac);return
            item=dict(frame.doc.data['instruments'][0],id='ac',source='AC frequency',format='Polar / degrees',x=850)
            frame.doc.commit(lambda d:d['instruments'].append(item))
            label,value,curve=instrument_data(frame,item)
            check('AC 1000 Hz' in label and '∠' in value and '-80.' in value,'AC phasor readout uses solved complex RC response')
            frame.book.SetSelection(0);frame.canvas.Refresh();capture_window(frame,destination/'ac-phasor-readout.png')
            write_json(destination/'checks.json',checks);frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)
    begin()
