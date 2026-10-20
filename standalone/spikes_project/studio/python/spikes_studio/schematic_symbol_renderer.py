# SPDX-License-Identifier: Apache-2.0
"""Shared placed/preview schematic symbol body painting."""
from __future__ import annotations

import numpy as np
import wx


def label_positions(part):
    """Return upright ref/value/identity anchors clear of the rotated body."""
    x,y=part['x'],part['y']
    if part.get('rotation',0)%180:
        return ((x+34,y-36),(x+34,y-16),(x+34,y+4))
    return ((x-28,y-43),(x-28,y+24),(x-28,y+44))


def paint_body(dc, world_point, point, part, zoom, symbol_color, text_color, muted_color):
    """Paint one component body and its identity text without registering hits."""
    custom=part.get('parameters',{}).get('component_symbol')
    if custom:
        dc.SetPen(wx.Pen(symbol_color,2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
        for primitive in custom['primitives']:
            if primitive['kind']=='circle':dc.DrawCircle(point(*primitive['center']),max(1,round(primitive['radius']*zoom)))
            else:dc.DrawLines([point(*p) for p in primitive['points']])
        dc.SetTextForeground(text_color)
        for terminal in custom['terminals']:
            at=point(*terminal['at']);dc.DrawLine(at,point(*terminal['leg_endpoint']))
            dc.DrawText(terminal['id']+' '+terminal['name'],at[0]+4,at[1]-15)
        top=custom['body_keepout']['min'];dc.DrawText(part['ref'],point(top[0],top[1]-25))
        dc.DrawText(part['value'],point(top[0],top[1]-12));return
    left, right = point(-55, 0), point(55, 0)
    dc.SetPen(wx.Pen(symbol_color, 2));dc.SetBrush(wx.TRANSPARENT_BRUSH)
    dc.DrawLine(left, point(-28, 0));dc.DrawLine(point(28, 0), right)
    from .pin_geometry import pins as component_pins
    for pin in component_pins(part)[2:]:
        dc.DrawLine(point(*pin.body), point(*pin.anchor))
    kind = part['kind']
    from .device_glyphs import paint as paint_device_body
    if paint_device_body(dc, point, part, symbol_color):
        pass
    elif kind == 'capacitor':
        dc.DrawLine(point(-28, 0), point(-7, 0));dc.DrawLine(point(7, 0), point(28, 0))
        dc.DrawLine(point(-7, -22), point(-7, 22));dc.DrawLine(point(7, -22), point(7, 22))
    elif kind == 'inductor':
        for center in (-18, 0, 18):
            dc.DrawLines([point(center-9*np.cos(t), -13*np.sin(t)) for t in np.linspace(0, np.pi, 15)])
        dc.DrawLine(point(-28, 0), point(-27, 0));dc.DrawLine(point(27, 0), point(28, 0))
    elif kind == 'diode':
        dc.DrawLine(point(-28, 0), point(-16, 0));dc.DrawLine(point(16, 0), point(28, 0))
        dc.DrawLines([point(-16, -18), point(-16, 18), point(16, 0), point(-16, -18)])
        dc.DrawLine(point(16, -18), point(16, 18))
    elif kind in ('voltage_source', 'current_source'):
        dc.DrawCircle(point(0, 0), round(28*zoom))
        if kind == 'voltage_source':
            dc.DrawLine(point(-19, 0), point(-7, 0));dc.DrawLine(point(-13, -6), point(-13, 6));dc.DrawLine(point(7, 0), point(19, 0))
        else:
            dc.DrawLine(point(-16, 0), point(16, 0));dc.DrawLines([point(7, -7), point(16, 0), point(7, 7)])
    else:
        body_height = 22 if len(part['nodes']) > 2 else 17
        dc.DrawLines([point(a, b) for a, b in ((-28, -body_height), (28, -body_height), (28, body_height), (-28, body_height), (-28, -body_height))])
        if kind != 'resistor':
            dc.DrawText(kind[:6], point(-24, -10))
    reference_at,value_at,identity_at=label_positions(part)
    dc.SetTextForeground(text_color)
    dc.DrawText(part['ref'], world_point(*reference_at))
    dc.DrawText(part['value'], world_point(*value_at))
    identity = part.get('parameters', {}).get('manufacturer_part', {})
    if identity:
        mpn = identity.get('mpn', '');dc.SetTextForeground(muted_color)
        dc.DrawText(mpn if len(mpn) <= 30 else mpn[:27]+'…', world_point(*identity_at))
