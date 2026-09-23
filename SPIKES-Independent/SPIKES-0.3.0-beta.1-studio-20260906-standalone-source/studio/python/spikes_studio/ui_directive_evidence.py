"""Actual-window directive editor/manager/canvas and native measurement checks."""
from copy import deepcopy
from pathlib import Path
import time
import wx
from .document import Document,write_json
from .directive_manager import DirectiveEditor
from .ui_evidence import capture_window


def verify_directives(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    checks={};deadline=time.monotonic()+35

    def check(condition,label):
        if not condition:raise AssertionError(label)
        checks[label]=True

    def fail(exc):
        frame.validation_failure=True
        if frame.active_run:frame.active_run.stop()
        write_json(destination/'error.json',{'error':str(exc),'checks':checks})
        frame.timer.Stop();frame.Destroy()

    def dialog_edit(dialog,fn):
        def callback():
            try:fn()
            except Exception as exc:
                if dialog.IsModal():dialog.EndModal(wx.ID_CANCEL)
                fail(exc)
        wx.CallLater(120,callback);dialog.ShowModal();dialog.Destroy()
        if getattr(frame,'validation_failure',False):raise RuntimeError('Dialog test failed')

    def select(ids):
        manager=frame.directives
        for index,ident in enumerate(manager.ids):manager.rows.Select(index,ident in ids)

    def begin():
        try:
            check(frame.directives.rows.GetItemCount()==1,'manager discovers existing .tran')
            dialog=DirectiveEditor(frame,position=(100,510))
            def add():
                dialog.template.SetStringSelection('Measure average');dialog.use_template()
                dialog.title.SetValue('Output settling average')
                capture_window(dialog,destination/'01-directive-editor.png');dialog.apply()
                check(not hasattr(dialog,'last_error'),'measurement template passes parser validation')
            dialog_edit(dialog,add);ident=dialog.ident
            check('.measure tran average_out' in frame.doc.data['source'],'editor adds actual measurement to source')
            check(frame.source.GetText()==frame.doc.data['source'],'circuit text synchronizes after directive edit')
            frame.book.SetSelection(7);select([ident]);frame.directives.group_target.SetValue('Observations');frame.directives.organize(group='Observations')
            capture_window(frame,destination/'02-directive-manager.png')
            frame.directives.locate();frame.canvas.Refresh();frame.canvas.Update();wx.YieldIfNeeded()
            rect,item=next((r,v) for r,v in frame.canvas.directive_hits if v['id']==ident)
            check(item['group']=='Observations','manager locates categorized canvas annotation')
            start=wx.Point(rect.x+10,rect.y+10);end=wx.Point(start.x+50,start.y+30)
            for kind,point in ((wx.wxEVT_LEFT_DOWN,start),(wx.wxEVT_MOTION,end),(wx.wxEVT_LEFT_UP,end)):
                event=wx.MouseEvent(kind);event.SetPosition(point)
                if kind==wx.wxEVT_MOTION:event.SetLeftDown(True)
                frame.canvas.GetEventHandler().ProcessEvent(event)
            moved=next(v for v in frame.doc.data['directives'] if v['id']==ident)
            check((moved['x'],moved['y'])==(150,540),'directive drag commits canvas position')
            frame.doc.undo();frame.refresh_document()
            check(next(v['x'] for v in frame.doc.data['directives'] if v['id']==ident)==100,'directive drag undo restores position')
            frame.doc.redo();frame.refresh_document();frame.fit()
            capture_window(frame,destination/'03-directives-on-canvas.png')
            frame.book.SetSelection(7);select([ident]);frame.directives.enable(False)
            check(not next(v['enabled'] for v in frame.doc.data['directives'] if v['id']==ident),'manager disables directive as a comment')
            frame.directives.enable(True)
            before=deepcopy(frame.doc.data)
            dialog=DirectiveEditor(frame,ident)
            def reject():
                dialog.text.SetValue('.invented broken');dialog.apply()
                check(hasattr(dialog,'last_error') and frame.doc.data==before,'invalid edit is rejected without changing document')
                dialog.EndModal(wx.ID_CANCEL)
            dialog_edit(dialog,reject)
            frame.source.SetText(frame.doc.data['source']+'* pending edit\n')
            try:frame.require_clean_directive_source()
            except ValueError:check(True,'unapplied source edits are protected')
            else:raise AssertionError('Unapplied source was not protected')
            frame.source.SetText(frame.doc.data['source'])
            frame.path=destination/'directives.spksch';frame.save_document()
            check(Document.load(frame.path).data['directives']==frame.doc.data['directives'],'directive organization survives project save/load')
            frame.run();wx.CallLater(150,await_run)
        except Exception as exc:
            if not getattr(frame,'validation_failure',False):fail(exc)

    def await_run():
        try:
            if time.monotonic()>deadline:raise TimeoutError('Native directive run timed out')
            if frame.job_running:wx.CallLater(150,await_run);return
            check(frame.run_history.records[-1]['state']=='completed','native circuit with managed measurement runs')
            write_json(destination/'native-result.json',frame.result)
            measurements=frame.result.get('measurements',frame.result.get('data',{}).get('measurements'))
            check(measurements and measurements['average_out']['status']=='completed','native run returns successful measurement results')
            check(.9<measurements['average_out']['value']<.92,'measured RC settling average has expected value')
            write_json(destination/'checks.json',checks);frame.timer.Stop();frame.Destroy()
        except Exception as exc:fail(exc)

    begin()
