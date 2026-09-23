"""Large local model collections: background indexing, virtual rows, explicit review."""
import json
from pathlib import Path
import queue
import threading
import wx
from .document import write_json
from .themes import apply_window

class EntryList(wx.ListCtrl):
    def __init__(self,parent):
        super().__init__(parent,style=wx.LC_REPORT|wx.LC_VIRTUAL|wx.LC_SINGLE_SEL);self.rows=[]
        for index,(title,width) in enumerate([('Model / subcircuit',300),('Kind',80),('File',380),('Status',150)]):self.InsertColumn(index,title,width=width)
    def OnGetItemText(self,row,column):
        if not 0<=row<len(self.rows):return ''
        item=self.rows[row]
        return [item['name'],item['kind'],item['path'],'Not qualified'][column]

class CollectionDialog(wx.Dialog):
    def __init__(self,owner):
        super().__init__(owner,title='SPICE model collections · local source browser',size=(1040,760),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        self.owner=owner;self.index=None;self.messages=queue.Queue();self.busy=False
        box=wx.BoxSizer(wx.VERTICAL);bar=wx.WrapSizer(wx.HORIZONTAL,flags=wx.WRAPSIZER_DEFAULT_FLAGS & ~wx.EXTEND_LAST_ON_EACH_LINE);box.Add(bar,0,wx.EXPAND|wx.ALL,8)
        self.scan_button=wx.Button(self,label='Index folder…');bar.Add(self.scan_button,0,wx.RIGHT,6);self.scan_button.Bind(wx.EVT_BUTTON,lambda e:self.guard(self.choose_folder))
        for label,fn in [('Open saved index…',self.open_index),('Save index…',self.save_index),('Review selected source',self.review)]:
            control=wx.Button(self,label=label);control.Bind(wx.EVT_BUTTON,lambda e,f=fn:self.guard(f));bar.Add(control,0,wx.RIGHT,6)
        self.search=wx.SearchCtrl(self);self.search.SetDescriptiveText('Search model name, type, pin or source path');self.search.Bind(wx.EVT_TEXT,lambda e:self.filter());box.Add(self.search,0,wx.EXPAND|wx.ALL,8)
        self.status=wx.StaticText(self,label='Index a local collection. Source files stay in place; no includes or code are executed.');box.Add(self.status,0,wx.ALL,8)
        self.list=EntryList(self);box.Add(self.list,1,wx.EXPAND|wx.ALL,8);self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED,lambda e:self.guard(self.review))
        self.details=wx.TextCtrl(self,style=wx.TE_MULTILINE|wx.TE_READONLY,size=(-1,180));box.Add(self.details,0,wx.EXPAND|wx.ALL,8)
        note=wx.StaticText(self,label='Declaration counts are not distinct qualified parts. File hashes are checked before review. Licensing and solver compatibility require separate review.');note.Wrap(990);box.Add(note,0,wx.ALL,8)
        box.Add(self.CreateButtonSizer(wx.CLOSE),0,wx.ALIGN_RIGHT|wx.ALL,8);self.SetSizer(box);apply_window(self,owner.palette)
        self.timer=wx.Timer(self);self.Bind(wx.EVT_TIMER,self.poll,self.timer);self.timer.Start(100);self.Bind(wx.EVT_WINDOW_DESTROY,self.destroy)
    def destroy(self,event):
        if event.GetEventObject() is self:self.timer.Stop()
        event.Skip()
    def guard(self,fn):
        try:fn()
        except Exception as error:self.details.SetValue(str(error))
    def choose_folder(self):
        default=Path(__file__).resolve().parents[5]/'model-collections'
        with wx.DirDialog(self,'Select extracted SPICE library folder',defaultPath=str(default) if default.exists() else '') as dlg:
            if dlg.ShowModal()==wx.ID_OK:self.scan(dlg.GetPath())
    def scan(self,path):
        if self.busy:raise ValueError('An index operation is already running')
        self.busy=True;self.scan_button.Disable();self.status.SetLabel('Indexing in background… no simulation code will execute.')
        messages=self.messages
        def work():
            try:
                from .model_collection import scan_collection
                messages.put((scan_collection(path),None))
            except Exception as error:messages.put((None,str(error)))
        threading.Thread(target=work,daemon=True).start()
    def poll(self,event=None):
        try:index,error=self.messages.get_nowait()
        except queue.Empty:return
        self.busy=False;self.scan_button.Enable()
        if error:self.status.SetLabel('Index failed');self.details.SetValue(error);return
        self.accept(index)
    def accept(self,index):
        if not isinstance(index,dict) or not isinstance(index.get('entries'),list) or len(index['entries'])>100000:raise ValueError('Invalid collection index')
        for entry in index['entries']:
            if not all(isinstance(entry.get(k),str) for k in ('name','kind','path')):raise ValueError('Invalid collection entry')
        self.index=index;self.filter();self.details.SetValue(json.dumps(index.get('counts',{}),indent=2)+'\n'+json.dumps(index.get('issues',[])[:20],indent=2))
    def filter(self):
        from .model_collection import search_entries
        self.list.rows=search_entries(self.index,self.search.GetValue()) if self.index else []
        self.list.SetItemCount(len(self.list.rows));self.list.Refresh()
        self.status.SetLabel(f'{len(self.list.rows):,} matching declarations · not qualified for execution')
    def save_index(self):
        if self.index is None:raise ValueError('Index a collection first')
        with wx.FileDialog(self,'Save collection index',wildcard='SPIKES collection index|*.spkindex',style=wx.FD_SAVE|wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal()==wx.ID_OK:write_json(dlg.GetPath(),self.index)
    def open_index(self):
        with wx.FileDialog(self,'Open collection index',wildcard='SPIKES collection index|*.spkindex',style=wx.FD_OPEN|wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal()==wx.ID_OK:
                path=Path(dlg.GetPath())
                if path.stat().st_size>64*1024*1024:raise ValueError('Index exceeds 64 MiB')
                self.accept(json.loads(path.read_text(encoding='utf-8')))
    def review(self):
        selection=self.list.GetFirstSelected()
        if selection<0:raise ValueError('Select a model declaration')
        from .model_collection import read_entry
        report=read_entry(self.index,self.list.rows[selection]);source=report.pop('original_source')
        self.details.SetValue('ORIGINAL MODEL SOURCE — NOT EXECUTED\n\n'+source+'\n\nSTATIC REVIEW\n'+json.dumps(report,indent=2))
