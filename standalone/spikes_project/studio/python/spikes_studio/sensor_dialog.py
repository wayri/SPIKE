"""Explicit recorded-input authoring; no implicit microphone permission."""
import wx
from .document import Document
from .sensor_input import load_recording,apply_recording
from .themes import apply_window


def import_sensor(owner):
    if owner.job_running:raise ValueError('Stop the simulation before changing recorded inputs')
    if owner.source.GetText()!=owner.doc.data['source']:raise ValueError('Apply circuit text edits first')
    path=owner.choose_path('Import audio / sensor recording','Recordings (*.wav;*.csv)|*.wav;*.csv')
    if not path:return
    with wx.Dialog(owner,title='Recorded audio / sensor → electrical source',size=(640,480),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dialog:
        box=wx.BoxSizer(wx.VERTICAL)
        note=wx.StaticText(dialog,label='Replace an existing independent V/I source with a simulation-time PWL signal.\nWAV is normalized PCM, NOT calibrated pressure. CSV begins time_s,<signal>.\nGain converts input units to volts or amperes; offset uses output units.\n2–20000 samples; final value is held. No microphone or speaker is opened.')
        box.Add(note,0,wx.ALL,12);grid=wx.FlexGridSizer(cols=2,hgap=8,vgap=8);grid.AddGrowableCol(1)
        fields={}
        for key,label,value in [('source','Existing source reference','V1'),('channel','Channel index (zero based)','0'),('gain','Gain [V or A / input unit]','1'),('offset','Offset [V or A]','0'),('unit','Input unit label','normalized')]:
            grid.Add(wx.StaticText(dialog,label=label),0,wx.ALIGN_CENTER_VERTICAL);fields[key]=wx.TextCtrl(dialog,value=value);grid.Add(fields[key],1,wx.EXPAND)
        box.Add(grid,1,wx.EXPAND|wx.ALL,12);box.Add(dialog.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALIGN_RIGHT|wx.ALL,12);dialog.SetSizer(box);apply_window(dialog,owner.palette)
        if dialog.ShowModal()!=wx.ID_OK:return
        recording=load_recording(path,channel=int(fields['channel'].GetValue()),gain=float(fields['gain'].GetValue()),offset=float(fields['offset'].GetValue()),unit=fields['unit'].GetValue())
        ref=fields['source'].GetValue().strip()
        source=apply_recording(owner.doc.data['source'],ref,recording)
        candidate=Document(owner.doc.data);candidate.apply_source(source)
        candidate.data['metadata'].setdefault('recorded_inputs',{})[ref.upper()]=recording['provenance']
        owner.doc.commit(lambda d:d.update(candidate.data));owner.refresh_document(force_source=True)
        owner.SetStatusText(f"Imported {recording['provenance']['samples']} samples into {ref}; Ctrl+Z undoes. Choose a transient step small enough for the recording bandwidth.")
