"""Self-closing real wx integration test, including an owned C++ RC acquisition.

No mocked waveform, browser or solver. A failed WebView render is a failed check,
not replaced with a fabricated plot. Artifacts are development evidence only.
"""
from copy import deepcopy
from pathlib import Path
import sys
import time
import os
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python'),str(ROOT/'.tmp/studio-deps')]
import wx
from spikes_studio.desktop import Studio
from spikes_studio.document import write_json
from spikes_studio.workbench_layout import PRESETS


def main():
    preferences=tempfile.TemporaryDirectory(prefix='spikes-gui-test-')
    os.environ['LOCALAPPDATA']=preferences.name
    app=wx.App(False);app.SetAssertMode(wx.APP_ASSERT_EXCEPTION)
    frame=Studio(str(ROOT/'build-spikes-current-vs18-20260906/Release/spikes_c_api.dll'))
    out=ROOT/'artifacts/workbench-stage-a';out.mkdir(parents=True,exist_ok=True)
    checks={};state='editing';started=time.monotonic();finished=False
    frame.Show()
    frame.autosave_timer.Stop()

    def capture(name):
        # Capture the actual client window after paint, not a generated mockup.
        frame.Update();size=frame.GetClientSize();bitmap=wx.Bitmap(size.width,size.height)
        target=wx.MemoryDC(bitmap);target.Blit(0,0,size.width,size.height,wx.ClientDC(frame),0,0)
        target.SelectObject(wx.NullBitmap);bitmap.SaveFile(str(out/name),wx.BITMAP_TYPE_PNG)

    def finish(error=None):
        nonlocal finished
        if finished:return
        finished=True
        write_json(out/'checks.json',dict(passed=error is None,checks=checks,error=error,scope='Stage A development checks; not release qualification'))
        frame.timer.Stop();frame.autosave_timer.Stop()
        if frame.active_run:frame.active_run.stop()
        if error is None and '--visual-review' in sys.argv:
            wx.CallLater(120000,frame.Destroy)
        else:frame.Destroy()

    def advance():
        nonlocal state
        if finished:return
        try:
            if time.monotonic()-started>25:
                panel=frame.offline_report
                debug=(panel.web.GetCurrentURL(),panel.web.GetCurrentTitle()) if panel.web else None
                raise TimeoutError('Timed out in '+state+'; '+panel.status.GetLabel()+'; '+str(debug))
            if state=='editing':
                before=deepcopy(frame.doc.data)
                with patch.object(wx,'MessageBox',return_value=wx.OK):
                    frame.accept_import('.model gui_nmos NMOS(LEVEL=1 VTO=1 KP=1m)')
                frame.canvas.Refresh();frame.canvas.Update()
                mos=frame.doc.data['components'][-1]
                self_pins=[entry for entry in frame.canvas.wire_pins if entry[1]==mos['id']]
                assert len(self_pins)==4,'Not all semiconductor terminals rendered/hit-testable'
                frame.refresh_inspector()
                rotate=next(control for control,command in frame.command_controls if command=='edit.rotate')
                assert rotate.IsEnabled(),'Ribbon did not update when selection changed'
                voltage=frame.doc.data['components'][0]
                frame.doc.connect((voltage['id'],0),(mos['id'],2))
                frame.refresh_document();frame.canvas.Update()
                checks['MODEL paste, all pins hit-testable, gate wire']=True
                path=out/'multi-terminal.spksch';frame.doc.save(path)
                from spikes_studio.document import Document
                assert Document.load(path).data==frame.doc.data
                capture('multi-terminal-canvas.png')
                frame.doc.undo();frame.doc.undo();assert frame.doc.data==before
                frame.refresh_document()
                checks['save/reopen and two atomic undo transactions']=True
                for name in PRESETS:frame.apply_workspace_preset(name)
                frame.apply_workspace(dict(contract='spikes/workspace/v1',name='test',page='Schematic',split=False,browser=False,properties=False))
                frame.canvas.selected.clear()
                assert frame.commands.reason('edit.rotate')
                assert frame.commands.search('continuous')[0]['id']=='run.interactive'
                checks['workspace presets and shared command availability']=True
                frame.run();state='native run'
            elif state=='native run' and not frame.job_running:
                assert frame.math is not None,'C++ run did not produce acquired data'
                assert len(frame.math.time)>100
                voltage=frame.math.evaluate('v(out)').values
                assert 0.98<float(voltage[-1])<1.01
                checks['owned C++ RC transient acquired and checked']=True
                frame.commands.execute('view.offline_report')
                frame.offline_report.refresh_snapshot();state='offline report'
            elif state=='offline report' and frame.offline_report.report is not None:
                panel=frame.offline_report
                if panel.web is None:raise RuntimeError('Embedded WebView unavailable')
                title=panel.web.GetCurrentTitle()
                if title=='SPIKES report failed':raise RuntimeError('Plotly rejected the generated figure')
                if title=='SPIKES report ready':
                    checks['real offline WebView Plotly render']=True
                    from spikes_studio.offline_report import write_report
                    write_report(out/'rc-acquired-report.html',panel.report)
                    checks['self-contained acquired HTML export']=True
                    finish();return
            wx.CallLater(200,advance)
        except Exception:
            import traceback
            finish(traceback.format_exc())
    wx.CallLater(500,advance);app.MainLoop()
    import json
    result=json.loads((out/'checks.json').read_text(encoding='utf-8'))
    print(result)
    return int(not result['passed'])


if __name__=='__main__':raise SystemExit(main())
