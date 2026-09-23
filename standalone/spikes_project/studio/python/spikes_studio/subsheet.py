"""Native subcircuit authoring with explicit ordered hierarchy ports."""
import re


def add_subsheet(source,name,instance,ports,nodes,body):
    token=r'[A-Za-z][A-Za-z0-9_]*'
    if not re.fullmatch(token,name) or not re.fullmatch(r'[Xx][A-Za-z0-9_]+',instance):raise ValueError('Use a simple subcircuit name and an X-prefixed instance reference')
    if not 1<=len(ports)<=64 or len(ports)!=len(nodes) or len(set(p.lower() for p in ports))!=len(ports):raise ValueError('Map 1..64 unique ordered ports to the same number of parent nodes')
    if any(not re.fullmatch(token,p) for p in ports):raise ValueError('Ports require simple identifiers')
    if any(not re.fullmatch(r'[A-Za-z0-9_.$:+-]+',n) for n in nodes):raise ValueError('Invalid parent node name')
    if not body.strip() or re.search(r'(?im)^\s*\.(?:end|ends|subckt|include|lib|control)\b',body):raise ValueError('Enter subcircuit contents only; nested definitions/includes are not supported in this editor')
    if re.search(r'(?im)^\s*\.subckt\s+'+re.escape(name)+r'\b',source) or re.search(r'(?im)^\s*'+re.escape(instance)+r'\s',source):raise ValueError('Definition or instance name already exists')
    insertion=f'.subckt {name} '+ ' '.join(ports)+'\n'+body.rstrip()+f'\n.ends {name}\n{instance} '+ ' '.join(nodes)+f' {name}\n'
    ends=list(re.finditer(r'(?im)^\s*\.end\s*$',source))
    if len(ends)!=1:raise ValueError('Require one top-level .end line')
    position=ends[0].start();candidate=source[:position]+insertion+source[position:]
    from .document import Document
    Document.from_netlist(candidate)
    return candidate


def create(owner):
    import wx
    from .themes import apply_window
    if owner.job_running:raise ValueError('Stop the simulation before adding a subcircuit')
    if owner.source.GetText()!=owner.doc.data['source']:raise ValueError('Apply circuit text edits first')
    with wx.Dialog(owner,title='Create SPICE subsheet · ordered hierarchy ports',size=(740,560),style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER) as dlg:
        box=wx.BoxSizer(wx.VERTICAL);fields={}
        for key,label,value in [('name','Definition name','SUBSHEET'),('instance','Instance reference','X1'),('ports','Hierarchy pins, ordered','IN OUT REF'),('nodes','Parent node mapping, same order','in out 0')]:
            box.Add(wx.StaticText(dlg,label=label),0,wx.LEFT|wx.TOP,8);fields[key]=wx.TextCtrl(dlg,value=value);box.Add(fields[key],0,wx.EXPAND|wx.ALL,8)
        box.Add(wx.StaticText(dlg,label='SPICE contents using the port names above. Native flattened execution; not a nested drawing canvas.'),0,wx.ALL,8)
        body=wx.TextCtrl(dlg,style=wx.TE_MULTILINE);box.Add(body,1,wx.EXPAND|wx.ALL,8)
        error=wx.StaticText(dlg,label='');box.Add(error,0,wx.ALL,8);box.Add(dlg.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.ALL,8);candidate=[]
        def accept(event):
            try:
                candidate.append(add_subsheet(owner.doc.data['source'],fields['name'].GetValue().strip(),fields['instance'].GetValue().strip(),fields['ports'].GetValue().split(),fields['nodes'].GetValue().split(),body.GetValue()));dlg.EndModal(wx.ID_OK)
            except Exception as exc:error.SetLabel(str(exc))
        dlg.Bind(wx.EVT_BUTTON,accept,id=wx.ID_OK);dlg.SetSizer(box);apply_window(dlg,owner.palette)
        if dlg.ShowModal()!=wx.ID_OK:return
    owner.doc.apply_source(candidate[-1]);owner.refresh_document(force_source=True)


def enter(owner,ref):
    """Jump to an existing top-level instance's real shared definition."""
    instance=ref.split(':',1)[0]
    if instance==ref:return False
    lines=owner.source.GetText().splitlines()
    matches=[line.split() for line in lines if line.split() and line.split()[0].lower()==instance.lower()]
    if len(matches)!=1:return False
    names={line.split()[1].lower():i for i,line in enumerate(lines) if len(line.split())>1 and line.split()[0].lower()=='.subckt'}
    target=next((names[t.lower()] for t in reversed(matches[0][1:]) if t.lower() in names),None)
    if target is None:return False
    owner.book.SetSelection(2);owner.source.GotoLine(target);owner.source.SetFocus()
    owner.SetStatusText('Shared subcircuit definition: header lists hierarchy pins. Edits affect all instances; validate/apply before running.')
    return True
