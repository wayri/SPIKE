# SPDX-License-Identifier: Apache-2.0
"""Navigate actual native subcircuit instances without inventing sheet connections."""
from .part_properties import parse


def instances(source):return list(parse(source).hierarchy)


def members(parts,path):
    if not path:return list(parts)
    prefix=path.upper()+':'
    return [p for p in parts if p['ref'].upper().startswith(prefix)]


def open_sheet(owner,path=None):
    if path is not None:
        match=next((h for h in instances(owner.doc.data['source']) if h.path.upper()==path.upper()),None)
        if match is None:raise ValueError('Subsheet instance no longer exists')
        path=match.path.upper()
    owner.canvas.sheet_scope=path;owner.canvas.sheet_document_id=owner.doc.data['id'];owner.canvas.selected.clear();owner.canvas.capture_lost()
    owner.canvas.wire_mode=False;owner.canvas.wire_start=None;owner.canvas.label_mode=False
    owner.book.SetSelection(owner.editor_page());owner.fit();owner.refresh_inspector();owner.canvas.Refresh()
    owner.SetStatusText('Subsheet '+path+' - instance-scoped native nets; shared definitions edit in Circuit text' if path else 'Flat schematic view - all native instances')


def choose(owner):
    import wx
    rows=instances(owner.doc.data['source'])
    choices=['Flat view (all instances)']+[h.path+' | '+h.definition+' | '+', '.join(f'{p}={n}' for p,n in zip(h.pins,h.nodes)) for h in rows]
    with wx.SingleChoiceDialog(owner,'Select a real SPICE subsheet instance. Nested descendants are included.\nPorts are the native parser mappings, not geometrically inferred nets.','Schematic hierarchy',choices) as dialog:
        if dialog.ShowModal()==wx.ID_OK:open_sheet(owner,None if dialog.GetSelection()==0 else rows[dialog.GetSelection()-1].path)


def parent(owner):
    path=getattr(owner.canvas,'sheet_scope',None)
    open_sheet(owner,path.rpartition(':')[0] or None if path else None)
