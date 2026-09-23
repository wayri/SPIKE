"""Self-closing wx integration test of the actual paste handler (test consent)."""
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'standalone/spikes_project/studio/python'),str(ROOT/'.tmp/studio-deps')]
import wx
from spikes_studio.desktop import Studio
from spikes_studio.document import write_json

def main():
    app=wx.App(False);app.SetAssertMode(wx.APP_ASSERT_EXCEPTION)
    frame=Studio(str(ROOT/'build-spikes-current-vs18-20260906/Release/spikes_c_api.dll'))
    frame.Show();checks={};error=None
    def exercise():
        nonlocal error
        try:
            original=frame.doc.data['source'];count=len(frame.doc.data['components'])
            with patch.object(wx,'MessageBox',return_value=wx.OK):
                frame.accept_import('.model paste_demo D(IS=1n N=1.7)')
            assert len(frame.doc.data['components'])==count+1
            assert len(frame.canvas.selected)==1
            assert frame.source.GetText()==frame.doc.data['source']
            checks['paste creates selected component and synchronizes source']=True
            frame.canvas.Refresh();frame.canvas.Update()
            checks['canvas refresh completes']=True
            frame.doc.undo();assert frame.doc.data['source']==original
            checks['one undo restores source']=True
        except Exception:
            import traceback
            error=traceback.format_exc()
        finally:
            write_json(ROOT/'artifacts/model-paste-workflow-check.json',dict(passed=error is None,checks=checks,error=error))
            frame.timer.Stop();frame.Destroy()
    wx.CallLater(400,exercise);app.MainLoop()
    return int(error is not None)

if __name__=='__main__':raise SystemExit(main())
