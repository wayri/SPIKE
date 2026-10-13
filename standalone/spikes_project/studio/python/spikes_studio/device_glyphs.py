# SPDX-License-Identifier: Apache-2.0
"""Conventional semiconductor bodies preserving existing v1 pin anchors."""
from copy import deepcopy
from functools import lru_cache
from .device_symbols import symbols


@lru_cache(maxsize=16)
def _body(kind):
    identifier={'nmos_level1':'mosfet.n_channel.4_terminal',
                'npn_ebers_moll':'bjt.npn.4_terminal'}.get(kind)
    if identifier is None:return None
    primitives=deepcopy(next(s for s in symbols() if s['id']==identifier)['primitives'])
    if kind=='npn_ebers_moll':
        # Existing native NPN is THREE terminals. Do not draw a substrate pin.
        omitted=[[[30,0],[50,0]],[[20,-8],[20,8]],[[20,0],[30,0]]]
        primitives=[item for item in primitives if item.get('points') not in omitted]
    # Map conventional vertical C/D and E/S onto the persisted horizontal
    # v1 anchors. Base/gate stays north, bulk stays south; no pin order changes.
    for item in primitives:
        if 'points' in item:item['points']=[[y*.55,(x-10)*.65] for x,y in item['points']]
    return primitives


def body(kind):
    return deepcopy(_body(kind))


def paint(dc,point,part,color):
    primitives=_body(part['kind'])
    if primitives is None:return False
    import wx
    for item in primitives:
        coordinates=[point(x,y) for x,y in item['points']]
        if item['kind']=='polygon':
            dc.SetBrush(wx.Brush(color) if item.get('fill') else wx.TRANSPARENT_BRUSH)
            dc.DrawPolygon(coordinates)
        else:dc.DrawLines(coordinates)
    dc.SetBrush(wx.TRANSPARENT_BRUSH)
    return True
