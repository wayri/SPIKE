# SPDX-License-Identifier: Apache-2.0
"""Semantic terminal-bound supply markers; geometry never creates a net."""
from copy import deepcopy
import uuid

KINDS = ('reference_ground', 'signal_ground', 'chassis_ground', 'earth_ground', 'power_flag')


def validate(markers, parts):
    if not isinstance(markers, list) or len(markers) > 10000: raise ValueError('Invalid power symbol list')
    by_id = {p['id']: p for p in parts}; seen = set()
    for marker in markers:
        ident = marker.get('id'); endpoint = marker.get('terminal', [])
        if not isinstance(ident, str) or not ident or ident in seen: raise ValueError('Invalid power symbol ID')
        seen.add(ident)
        if marker.get('kind') not in KINDS: raise ValueError('Unknown power symbol')
        if len(endpoint) != 2 or endpoint[0] not in by_id or type(endpoint[1]) is not int or not 0 <= endpoint[1] < len(by_id[endpoint[0]]['nodes']): raise ValueError('Power symbol requires an existing terminal')
        if marker['kind'] == 'reference_ground' and by_id[endpoint[0]]['nodes'][endpoint[1]] != '0': raise ValueError('Reference ground must bind SPICE node 0')


def attach(document, kind, terminal):
    if kind not in KINDS: raise ValueError('Unknown power symbol')
    candidate = type(document)(document.data)
    parts = {p['id']: p for p in candidate.data['components']}
    if len(terminal) != 2 or terminal[0] not in parts or type(terminal[1]) is not int or not 0 <= terminal[1] < len(parts[terminal[0]]['nodes']): raise ValueError('Choose an existing terminal')
    if kind == 'reference_ground' and parts[terminal[0]]['nodes'][terminal[1]] != '0':
        ground = next(((p['id'], i) for p in parts.values() for i, node in enumerate(p['nodes']) if node == '0'), None)
        if ground is None: raise ValueError('Define a SPICE node 0 in the source before placing reference ground')
        candidate.connect(ground, terminal)
        candidate.data['wires'].pop()  # Global net merge; no fictitious route.
    if any(m['kind'] == kind and m['terminal'] == list(terminal) for m in candidate.data['power_symbols']): raise ValueError('This terminal already has that symbol')
    marker = dict(id=uuid.uuid4().hex, kind=kind, terminal=list(terminal))
    candidate.data['power_symbols'].append(marker)
    candidate.validate(); candidate.data['revision'] = document.data['revision']
    document.commit(lambda data: data.update(deepcopy(candidate.data)))
    return marker


def remove(document, ident):
    if not any(m['id'] == ident for m in document.data['power_symbols']): raise ValueError('Power symbol no longer exists')
    document.commit(lambda data: data.__setitem__('power_symbols', [m for m in data['power_symbols'] if m['id'] != ident]))


def draw(canvas, dc, palette):
    import wx
    from .pin_geometry import pins as component_pins
    from .editor_geometry import transform
    parts = {p['id']: p for p in canvas.owner.doc.data['components']}
    canvas.power_hits = []
    for marker in canvas.owner.doc.data['power_symbols']:
        ident, index = marker['terminal']; part = parts[ident]
        pin = component_pins(part)[index]
        x, y = transform(part, *pin.anchor)
        direction=-1 if y<part['y'] else 1
        point = lambda a, b: canvas.point(x + a, y + direction*b)
        dc.SetPen(wx.Pen(palette['fg'], 2)); dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.DrawLine(point(0, 0), point(0, 18))
        kind = marker['kind']
        if kind in ('reference_ground', 'earth_ground'):
            for offset, half in ((18, 14), (24, 9), (30, 4)): dc.DrawLine(point(-half, offset), point(half, offset))
        elif kind == 'signal_ground': dc.DrawLines([point(-13, 18), point(13, 18), point(0, 31), point(-13, 18)])
        elif kind == 'chassis_ground':
            dc.DrawLine(point(-14, 18), point(14, 18))
            for at in (-10, 0, 10): dc.DrawLine(point(at, 18), point(at - 6, 29))
        else: dc.DrawLines([point(0, 18), point(0, 32), point(21, 25), point(0, 18)])
        node = part['nodes'][index]
        label = {'reference_ground': '0', 'earth_ground': 'PE: ', 'signal_ground': 'SG: ', 'chassis_ground': 'CH: ', 'power_flag': 'PWR: '}[kind]
        dc.SetTextForeground(palette['muted']); dc.DrawText(label + (node if kind != 'reference_ground' else ''), point(17, 20))
        a, b = point(-16, 12), point(34, 36)
        canvas.power_hits.append((wx.Rect(min(a.x,b.x),min(a.y,b.y),max(1,abs(b.x-a.x)),max(1,abs(b.y-a.y))), marker))
