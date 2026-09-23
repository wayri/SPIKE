"""Capture the actual rendered help window, including bundled screenshots."""
from pathlib import Path
import wx
import wx.html
from .help_center import show,example_dir
from .ui_evidence import capture_window
from .document import write_json


def verify_help(frame,destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    def inspect():
        dialog=next(w for w in wx.GetTopLevelWindows() if isinstance(w,wx.Dialog) and w.GetTitle().startswith('SPIKES Learning Center'))
        try:
            html=next(w for w in dialog.GetChildren() if isinstance(w,wx.html.HtmlWindow))
            assert 'First simulation' in html.ToText()
            assert len(list(example_dir().glob('*.cir')))==9
            capture_window(dialog,destination/'learning-center.png')
            write_json(destination/'checks.json',{'rendered_help':True,'nine_example_decks':True})
        except Exception as exc:frame.validation_failure=True;write_json(destination/'error.json',{'error':repr(exc)})
        finally:dialog.EndModal(wx.ID_CLOSE)
    wx.CallLater(400,inspect);show(frame);frame.timer.Stop();frame.Destroy()
