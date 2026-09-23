"""Real downloaded collection, native virtual list, original source review."""
import json
from pathlib import Path
import wx
from .collection_panel import CollectionDialog
from .document import write_json
from .ui_evidence import capture_window

def verify_collection(frame,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);checks={}
    def check(value,label):
        if not value:raise AssertionError(label)
        checks[label]=True
    try:
        frame.set_theme('Dark',save=False)
        source=Path(__file__).resolve().parents[5]/'model-collections'/'sky130-f62031a.spkindex'
        with CollectionDialog(frame) as dialog:
            dialog.accept(json.loads(source.read_text(encoding='utf-8')))
            check(len(dialog.list.rows)>1000,'actual downloaded library has over 1000 declarations')
            check(bool(dialog.list.GetWindowStyleFlag()&wx.LC_VIRTUAL),'large collection uses native virtual rows')
            def inspect():
                try:
                    dialog.search.SetValue('diode');dialog.filter();check(bool(dialog.list.rows),'model name search finds real diode declarations')
                    dialog.list.Select(0);dialog.review()
                    review=dialog.details.GetValue()
                    check('Copyright' in review and '\n.model' in review,'original upstream source and attribution retained')
                    check('"execution": "not_approved"' in review,'browsing does not approve native execution')
                    capture_window(dialog,folder/'open-collection-browser.png')
                except Exception as error:
                    frame.validation_failure=True;write_json(folder/'error.json',{'error':str(error)})
                finally:dialog.EndModal(wx.ID_CLOSE)
            wx.CallLater(300,inspect);dialog.ShowModal()
        write_json(folder/'checks.json',checks)
    except Exception as error:
        frame.validation_failure=True;write_json(folder/'error.json',{'error':str(error)})
    finally:frame.timer.Stop();frame.Destroy()
