# SPDX-License-Identifier: Apache-2.0
"""Explicit, run-only lumped leaf-wire parasitics; drawings remain symbolic."""
from copy import deepcopy
import hashlib
import math
from .part_properties import rewrite_nodes

CONTRACT='spikes/wire-rlc/v1'


def extraction_request(document):
    return dict(contract=CONTRACT,source_sha256=hashlib.sha256(document.data['source'].encode()).hexdigest(),
                project_id=document.data['id'],wires=[dict(wire_id=w['id'],a=w['a'],b=w['b']) for w in document.data['wires']])


def import_extraction(document, payload):
    if not isinstance(payload,dict) or payload.get('contract')!=CONTRACT:
        raise ValueError('Unsupported wire extraction contract')
    binding=extraction_request(document)
    if payload.get('source_sha256')!=binding['source_sha256'] or payload.get('project_id')!=binding['project_id']:
        raise ValueError('Wire extraction belongs to a different project/circuit revision')
    rows=payload.get('wires')
    if not isinstance(rows,list) or not 1<=len(rows)<=10000:raise ValueError('Expected 1..10000 extracted wire models')
    candidate=deepcopy(document.data);wires={w['id']:w for w in candidate['wires']};seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('wire_id') not in wires or row['wire_id'] in seen:
            raise ValueError('Unknown or duplicate extracted wire ID')
        seen.add(row['wire_id']);model=row.get('model');validate(model)
        if not model.get('evidence'):raise ValueError('Extraction source/evidence is required')
        wires[row['wire_id']]['parasitics']=deepcopy(model)
    lower(deepcopy(candidate))
    document.commit(lambda data:data.__setitem__('wires',deepcopy(candidate['wires'])))


def exchange(owner, export=False):
    import json
    from .document import write_json
    path=owner.choose_path('Export wire extraction request' if export else 'Import extracted wire RLC',
                           'Wire extraction (*.json)|*.json',export)
    if not path:return
    if export:write_json(path,extraction_request(owner.doc));return
    if owner.job_running:raise ValueError('Stop simulation before importing wire models')
    if path.stat().st_size>4*1024*1024:raise ValueError('Wire extraction exceeds 4 MiB')
    import_extraction(owner.doc,json.loads(path.read_text(encoding='utf-8-sig')));owner.refresh_document()


def validate(model):
    if not isinstance(model,dict) or set(model)-{'enabled','r_ohm','l_h','c_f','reference','evidence'}:
        raise ValueError('Unknown wire model fields')
    if type(model.get('enabled',False)) is not bool:raise ValueError('Wire enabled flag must be boolean')
    for key in ('r_ohm','l_h','c_f'):
        value=model.get(key,0.)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('Wire R/L/C must be finite, nonnegative SI values')
    if not isinstance(model.get('reference','0'),str) or not model.get('reference','0'):
        raise ValueError('Shunt capacitance requires an explicit reference net')
    if not isinstance(model.get('evidence',''),str) or len(model.get('evidence',''))>4096:
        raise ValueError('Wire evidence must be bounded text')


def lower(snapshot):
    """Split an explicit terminal leaf and append R/L + endpoint shunt C.

    Branched/internal edges and hierarchical terminals fail closed. No geometry
    extraction or material inference is performed. Source remains owned by the
    snapshot, never the saved drawing. Component pin nodes in this run snapshot
    reflect the actual simulation node, so electrical-limit probes use it.
    """
    parts={part['id']:part for part in snapshot['components']}
    wires=snapshot.get('wires',[]);degrees={}
    for wire in wires:
        for endpoint in (wire['a'],wire['b']):degrees[tuple(endpoint)]=degrees.get(tuple(endpoint),0)+1
    source=snapshot['source'];added=[];records=[]
    refs={p['ref'].casefold() for p in parts.values()}
    original_nodes={n.casefold() for p in parts.values() for n in p['nodes']}
    split_pins=set()
    for wire in wires:
        model=wire.get('parasitics')
        if model is None:continue
        validate(model)
        if not model.get('enabled') or not any(model.get(k,0)>0 for k in ('r_ohm','l_h','c_f')):continue
        endpoint=wire['b'] if len(wire['b'])==2 and degrees[tuple(wire['b'])]==1 else wire['a']
        if len(endpoint)!=2 or degrees[tuple(endpoint)]!=1:
            raise ValueError('Hidden wire models currently require a terminal leaf, not a junction/branch edge')
        if tuple(endpoint) in split_pins:raise ValueError('Multiple wire models address one terminal')
        split_pins.add(tuple(endpoint));part=parts[endpoint[0]];pin=endpoint[1];net=part['nodes'][pin]
        if net.casefold()=='0':raise ValueError('Ground wire impedance requires explicit return-network modeling')
        token=hashlib.sha256(wire['id'].encode()).hexdigest()[:12]
        local='spkw_'+token;middle=local+'_mid';reference=model.get('reference','0')
        if reference.casefold() not in original_nodes|{'0'}:raise ValueError('Unknown wire capacitance reference')
        if {local.casefold(),middle.casefold()} & original_nodes:raise ValueError('Wire internal node name conflict')
        generated=['Rwire_'+token,'Lwire_'+token,'Cwire_'+token]
        if any(ref.casefold() in refs for ref in generated):raise ValueError('Wire instance name conflict')
        r=model.get('r_ohm',0.);l=model.get('l_h',0.);c=model.get('c_f',0.)
        if r>0 or l>0:
            changed=list(part['nodes']);changed[pin]=local
            source=rewrite_nodes(source,part['ref'],changed);part['nodes']=changed
            if r>0:added.append(f'{generated[0]} {net} {middle if l>0 else local} {r:.17g}')
            if l>0:added.append(f'{generated[1]} {middle if r>0 else net} {local} {l:.17g}')
        else:local=net
        if c>0:added.append(f'{generated[2]} {local} {reference} {c:.17g}')
        records.append(dict(wire_id=wire['id'],terminal=list(endpoint),original_node=net,
                            simulation_node=local,model=deepcopy(model)))
    lines=source.splitlines();end=next((i for i,line in enumerate(lines) if line.strip().lower()=='.end'),len(lines))
    lines[end:end]=added;snapshot['source']='\n'.join(lines)+'\n';snapshot['wire_models']=records
    return snapshot


def edit(owner, wire):
    import wx
    if owner.job_running:raise ValueError('Stop simulation before changing wire models')
    values=dict(enabled=False,r_ohm=0.,l_h=0.,c_f=0.,reference='0',evidence='')|wire.get('parasitics',{})
    with wx.Dialog(owner,title='Hidden wire parasitics · lumped terminal branch',size=(460,430)) as dialog:
        box=wx.BoxSizer(wx.VERTICAL);enabled=wx.CheckBox(dialog,label='Enable this wire model');enabled.SetValue(values['enabled']);box.Add(enabled,0,wx.ALL,10)
        fields={}
        for key,label in [('r_ohm','Series resistance (ohm)'),('l_h','Series inductance (H)'),('c_f','Endpoint shunt capacitance (F)'),('reference','Capacitance reference node'),('evidence','Extraction / measurement source')]:
            box.Add(wx.StaticText(dialog,label=label),0,wx.LEFT|wx.TOP,10)
            fields[key]=wx.TextCtrl(dialog,value=str(values[key]));box.Add(fields[key],0,wx.EXPAND|wx.LEFT|wx.RIGHT,10)
        note=wx.StaticText(dialog,label='Terminal leaves only. Not a PCB field extraction. Shunt C needs an explicit return. Result pin nodes may differ from original net labels.');note.Wrap(410);box.Add(note,0,wx.ALL,10)
        box.Add(dialog.CreateButtonSizer(wx.OK|wx.CANCEL),0,wx.EXPAND|wx.ALL,10);dialog.SetSizer(box)
        from .themes import apply_window
        apply_window(dialog,owner.palette)
        if dialog.ShowModal()!=wx.ID_OK:return
        model=dict(enabled=enabled.GetValue(),**{k:float(v.GetValue()) if k in ('r_ohm','l_h','c_f') else v.GetValue() for k,v in fields.items()})
        validate(model)
        candidate=deepcopy(owner.doc.data)
        next(w for w in candidate['wires'] if w['id']==wire['id'])['parasitics']=model
        lower(candidate)  # Review topology and source rewrite before committing.
        owner.doc.commit(lambda d:next(w for w in d['wires'] if w['id']==wire['id']).__setitem__('parasitics',model))
        owner.refresh_document()
