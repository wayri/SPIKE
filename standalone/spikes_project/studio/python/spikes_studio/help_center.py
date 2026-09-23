"""Bundled illustrated help and reviewed example loading."""
from pathlib import Path
import sys
import wx
import wx.html
from .resources import resource_dir


def example_dir():
    if getattr(sys,'frozen',False):return Path(sys._MEIPASS)/'share/spikes/examples/studio_tutorials'
    return Path(__file__).resolve().parents[5]/'examples/spikes/studio_tutorials'


def examples(owner):
    paths=sorted(example_dir().glob('*.cir'))+sorted((example_dir().parent/'advanced_systems').glob('*.cir'))+sorted((example_dir().parent/'advanced_systems').glob('*.spksch'))
    if not paths:raise ValueError('Bundled example circuits are missing')
    with wx.SingleChoiceDialog(owner,'Choose a runnable tutorial; opening requires import review.','Example circuits',[p.stem.replace('_',' ') for p in paths]) as dlg:
        if dlg.ShowModal()!=wx.ID_OK:return
        path=paths[dlg.GetSelection()]
        if path.suffix=='.spksch':
            from .document import Document
            replacement=Document.load(path)
            if owner.confirm_replace():
                owner.doc=replacement;owner.path=None;owner.canvas.selected.clear();owner.refresh_document(force_source=True)
        else:owner.accept_import(path.read_text(encoding='utf-8'))


def show(owner):
    with wx.Dialog(owner,title='SPIKES Learning Center · verified workflows',size=(1050,800),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        box=wx.BoxSizer(wx.VERTICAL);row=wx.BoxSizer(wx.HORIZONTAL)
        for label,fn in [('Open example circuit',lambda:examples(owner)),('Tutorial instructions',lambda:wx.LaunchDefaultApplication(str(example_dir()/'README.md'))),('Qt-free workbench changes',lambda:wx.LaunchDefaultApplication(str(resource_dir('docs')/'QT_FREE_WORKBENCH_IMPLEMENTATION.md')))]:
            button=wx.Button(dlg,label=label);button.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f));row.Add(button,0,wx.ALL,5)
        box.Add(row);html=wx.html.HtmlWindow(dlg);html.LoadPage(str(resource_dir('docs')/'LEARNING_CENTER.html'));box.Add(html,1,wx.EXPAND|wx.ALL,5)
        box.Add(dlg.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,5);dlg.SetSizer(box);dlg.ShowModal()
