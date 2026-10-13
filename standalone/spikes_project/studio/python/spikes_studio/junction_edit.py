# SPDX-License-Identifier: Apache-2.0
"""Explicit wire split points preserve actual net identity and accepted routes."""
from copy import deepcopy
import uuid
from .editor_geometry import route,nearest_route_point


def split_at(document,wire_id,at,tolerance=12):
    data=deepcopy(document.data);parts={p['id']:p for p in data['components']};junctions={j['id']:j for j in data['junctions']}
    wire=next((w for w in data['wires'] if w['id']==wire_id),None)
    if wire is None:raise ValueError('Choose an existing wire')
    wire.setdefault('draw_order',data['wires'].index(wire))
    points=route(parts,wire,junctions);point,segment,distance=nearest_route_point(points,at)
    if distance>tolerance:raise ValueError('Click on the wire to add a junction')
    if point in (tuple(points[0]),tuple(points[-1])):raise ValueError('That point is already a wire endpoint')
    anchor=wire['a'] if len(wire['a'])==2 else junctions[wire['a'][0]]['source_terminal']
    node=parts[anchor[0]]['nodes'][anchor[1]]
    existing=next((j for j in junctions.values() if (j['x'],j['y'])==point and j['source_node'].casefold()==node.casefold()),None)
    if existing:return existing['id']
    ident=uuid.uuid4().hex;data['junctions'].append(dict(id=ident,x=point[0],y=point[1],source_terminal=list(anchor),source_node=node))
    other=deepcopy(wire['b']);wire.update(b=[ident],waypoints=[list(p) for p in points[1:segment+1]],manual=True)
    data['wires'].append(dict(id=uuid.uuid4().hex,a=[ident],b=other,waypoints=[list(p) for p in points[segment+1:-1]],bend=wire.get('bend','horizontal'),manual=True,draw_order=wire['draw_order']))
    data['revision']=document.data['revision'];document.commit(lambda d:d.update(data));return ident


def show(owner,wire,point):
    owner.require_clean_directive_source()
    if owner.job_running:raise ValueError('Stop simulation before editing junctions')
    split_at(owner.doc,wire['id'],point,12/owner.canvas.zoom);owner.refresh_document()
    owner.SetStatusText('Junction added on this net. A crossing of another net remains unconnected; use Wire to join it explicitly.')
