"""Sequence authoring and serialized native worker dispatch in the run manager."""
from copy import deepcopy
from pathlib import Path
import uuid
import wx
from .document import write_json
from .simulation_sequences import plan


class SequencePanel(wx.Panel):
    def __init__(self,parent,owner):
        super().__init__(parent);self.owner=owner;self.queue=[];self.current=None;self.directory=None;self.snapshot=None
        box=wx.BoxSizer(wx.VERTICAL);box.Add(wx.StaticText(self,label='Saved simulation sequences · independent runs, stop on first failure'),0,wx.ALL,5)
        self.names=wx.Choice(self);self.names.Bind(wx.EVT_CHOICE,lambda e:self.refresh_entries());box.Add(self.names,0,wx.EXPAND|wx.ALL,5)
        self.entries=wx.ListBox(self,size=(-1,110));box.Add(self.entries,0,wx.EXPAND|wx.ALL,5)
        row=wx.WrapSizer(wx.HORIZONTAL)
        for label,fn in [('New sequence',self.new),('Delete sequence',self.delete),('Add current profile',self.add),('Load entry into editor',self.load),('Replace from editor',self.replace),('Remove entry',self.remove),('Enable / disable',self.toggle),('Up',lambda:self.move(-1)),('Down',lambda:self.move(1)),('Run selected',lambda:self.start(True)),('Run all enabled',lambda:self.start(False)),('Stop sequence',self.stop)]:
            b=wx.Button(self,label=label);b.Bind(wx.EVT_BUTTON,lambda e,f=fn:owner.guarded(f));row.Add(b,0,wx.ALL,2)
        box.Add(row,0,wx.EXPAND);self.status=wx.StaticText(self,label='Sequences are saved with the schematic. Choose an output folder when running; each result is retained separately.')
        self.status.Wrap(800);box.Add(self.status,0,wx.ALL,5);self.SetSizer(box);self.refresh()

    def refresh(self):
        names=[s['name'] for s in self.owner.doc.data['simulation_sequences']];old=self.names.GetStringSelection()
        self.names.Set(names)
        if names:self.names.SetSelection(names.index(old) if old in names else 0)
        self.refresh_entries()

    def refresh_entries(self):
        i=self.names.GetSelection();old=self.entries.GetSelection()
        items=self.owner.doc.data['simulation_sequences'][i]['entries'] if i>=0 else []
        self.entries.Set([f"{'✓' if e['enabled'] else '—'} {n+1}. {e['profile']['name']} · {e['profile']['analysis']}" for n,e in enumerate(items)])
        if items:self.entries.SetSelection(min(max(old,0),len(items)-1))

    def edit(self,fn):
        if self.current is not None:raise ValueError('Stop the sequence before editing it')
        seq=deepcopy(self.owner.doc.data['simulation_sequences']);fn(seq)
        self.owner.doc.commit(lambda d:d.update(simulation_sequences=seq));self.owner.update_title();self.refresh()

    def indexes(self):
        i,j=self.names.GetSelection(),self.entries.GetSelection()
        if i<0 or j<0:raise ValueError('Select a sequence entry')
        return i,j

    def new(self):
        with wx.TextEntryDialog(self,'Sequence name','New simulation sequence') as dlg:
            if dlg.ShowModal()==wx.ID_OK:self.edit(lambda s:s.append({'name':dlg.GetValue().strip(),'entries':[]}));self.names.SetSelection(self.names.GetCount()-1);self.refresh_entries()

    def delete(self):
        i=self.names.GetSelection()
        if i<0:raise ValueError('Select a sequence')
        self.edit(lambda s:s.pop(i))

    def add(self):
        i=self.names.GetSelection()
        if i<0:raise ValueError('Create a sequence first')
        profile=self.owner.manager.profile();self.edit(lambda s:s[i]['entries'].append({'enabled':True,'profile':profile}))

    def load(self):
        i,j=self.indexes();self.owner.manager.set_fields(self.owner.doc.data['simulation_sequences'][i]['entries'][j]['profile'])

    def replace(self):
        i,j=self.indexes();profile=self.owner.manager.profile();self.edit(lambda s:s[i]['entries'][j].update(profile=profile))

    def remove(self):
        i,j=self.indexes();self.edit(lambda s:s[i]['entries'].pop(j))

    def toggle(self):
        i,j=self.indexes()
        def change(s):s[i]['entries'][j]['enabled']=not s[i]['entries'][j]['enabled']
        self.edit(change)

    def move(self,delta):
        i,j=self.indexes();target=j+delta
        if not 0<=target<len(self.owner.doc.data['simulation_sequences'][i]['entries']):return
        def change(s):s[i]['entries'].insert(target,s[i]['entries'].pop(j))
        self.edit(change);self.entries.SetSelection(target)

    def start(self,selected):
        owner=self.owner
        if owner.job_running or self.current is not None:raise ValueError('Stop the active job first')
        i,j=self.indexes();owner.apply_source()
        jobs=plan(owner.doc.data['source'],owner.doc.data['simulation_sequences'][i],j if selected else None)
        with wx.DirDialog(self,'Select parent folder for sequence results') as dlg:
            if dlg.ShowModal()!=wx.ID_OK:return
            directory=Path(dlg.GetPath())/('spikes-sequence-'+uuid.uuid4().hex)
        directory.mkdir();self.directory=directory;self.snapshot=deepcopy(owner.doc.data);self.queue=jobs
        write_json(directory/'sequence.json',{'sequence':owner.doc.data['simulation_sequences'][i],'jobs':jobs,'project_id':owner.doc.data['id']})
        self.advance()

    def advance(self):
        if not self.queue:self.current=None;self.status.SetLabel('Sequence finished. Results: '+str(self.directory));return
        from .run_control import BatchRun
        owner=self.owner;job=self.queue.pop(0);self.current=job
        try:
            owner.run_snapshot=deepcopy(self.snapshot);owner.run_snapshot.update(source=job['source'],document_source=self.snapshot['source'],run_profile=job['profile'])
            from .model_fidelity import preflight
            preflight(owner.run_snapshot)
            owner.active_run=BatchRun(owner.run_snapshot['source'],owner.library,method=job['profile']['method'])
            owner.active_record_id=owner.run_history.start(owner.run_snapshot,owner.library)
            owner.job_running=True;owner.manager.refresh_runs();owner.update_run_controls()
            self.status.SetLabel('Running '+job['profile']['name']+f' · {len(self.queue)} remaining')
        except Exception:
            self.queue=[];self.current=None;raise

    def finished(self,run):
        if self.current is None:return
        job=self.current;self.current=None
        try:
            path=self.directory/f"{job['index']+1:02d}-result.json"
            write_json(path,{'profile':job['profile'],'state':run.state,'error':run.error,'result':run.result})
            record=self.owner.run_history.get(self.owner.active_record_id)
            if record:record['capture_archive']=str(path)
        except Exception:
            self.queue=[];raise
        if run.state!='completed' or self.owner.closing:
            self.queue=[];self.status.SetLabel('Sequence stopped: '+run.state);return
        self.advance()

    def stop(self):
        self.queue=[]
        if self.current is not None:self.owner.stop_run()
