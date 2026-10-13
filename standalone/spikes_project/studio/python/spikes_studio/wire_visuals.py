# SPDX-License-Identifier: Apache-2.0
"""Source-net-aware orthogonal crossings. Geometry never merges nets."""
from bisect import bisect_left,bisect_right
from collections import defaultdict


def crossings(routes,limit=20000):
    """Sweep horizontal/vertical segments; preserve endpoint/interior distinction."""
    events=[];ys=set();horizontal={};vertical=[]
    for order,row in enumerate(routes):
        for segment,(a,b) in enumerate(zip(row['points'],row['points'][1:])):
            if a==b:continue
            item=dict(wire=row['id'],node=row['node'].casefold(),order=row.get('draw_order',order),segment=segment,a=a,b=b)
            if a[1]==b[1]:
                ident=len(horizontal);horizontal[ident]=item;ys.add(a[1]);lo,hi=sorted((a[0],b[0]))
                events.extend([(lo,0,ident),(hi,2,ident)])
            elif a[0]==b[0]:
                ident=len(vertical);vertical.append(item);events.append((a[0],1,ident))
            else:raise ValueError('Wire visualization needs orthogonal segments')
    ys=sorted(ys);active=defaultdict(set);result=[];seen=set()
    for x,kind,ident in sorted(events):
        if kind!=1:
            item=horizontal[ident];bucket=active[item['a'][1]]
            bucket.add(ident) if kind==0 else bucket.discard(ident);continue
        v=vertical[ident];low,high=sorted((v['a'][1],v['b'][1]))
        for y in ys[bisect_left(ys,low):bisect_right(ys,high)]:
            for hid in active[y]:
                h=horizontal[hid]
                if h['wire']==v['wire']:continue
                key=(tuple(sorted((h['wire'],v['wire']))),(x,y))
                if key in seen:continue
                seen.add(key);point=(x,y);same=h['node']==v['node']
                # A dot requires >=3 distinct outgoing directions on one actual net.
                directions=set()
                for item in (h,v):
                    for end in (item['a'],item['b']):
                        dx,dy=end[0]-x,end[1]-y
                        if dx or dy:directions.add((0 if not dx else 1 if dx>0 else -1,0 if not dy else 1 if dy>0 else -1))
                if same and len(directions)>=3:
                    result.append(dict(kind='junction',point=point,node=h['node']))
                elif not same and point not in (h['a'],h['b'],v['a'],v['b']):
                    top=max((h,v),key=lambda r:r['order'])
                    result.append(dict(kind='hop',point=point,node=top['node'],under_node=(v if top is h else h)['node'],horizontal=top is h))
                if len(result)>limit:raise ValueError('Wire crossing display exceeds 20,000 markers')
    return result


def endpoint_junctions(routes):
    """Dot shared routed endpoints with three or more outgoing ray directions."""
    endpoints=defaultdict(set)
    for row in routes:
        points=row['points']
        if len(points)<2:continue
        for point,other in ((points[0],points[1]),(points[-1],points[-2])):
            dx,dy=other[0]-point[0],other[1]-point[1]
            endpoints[(row['node'].casefold(),tuple(point))].add((0 if not dx else 1 if dx>0 else -1,0 if not dy else 1 if dy>0 else -1))
    return [dict(kind='junction',point=point,node=node) for (node,point),directions in endpoints.items() if len(directions)>=3]


def paint_markers(canvas,dc,routes,palette,net_color,highlighted,hops=True,cache_key=None):
    import wx
    import math
    cached=getattr(canvas,'wire_marker_cache',None)
    if cached and cache_key is not None and cached[0]==cache_key:markers=cached[1]
    else:
        markers=crossings(routes)+endpoint_junctions(routes)
        if cache_key is not None:canvas.wire_marker_cache=(cache_key,markers)
    for item in markers:
        point=canvas.point(*item['point']);color=net_color(item['node']);radius=max(4,round(6*canvas.zoom))
        if item['kind']=='hop' and hops:
            dc.SetPen(wx.Pen(palette['canvas'],3))
            if item['horizontal']:dc.DrawLine(point.x-radius,point.y,point.x+radius,point.y)
            else:dc.DrawLine(point.x,point.y-radius,point.x,point.y+radius)
            dc.SetPen(wx.Pen(net_color(item['under_node']),4 if item['under_node'] in highlighted else 2))
            if item['horizontal']:dc.DrawLine(point.x,point.y-radius-4,point.x,point.y+radius+4)
            else:dc.DrawLine(point.x-radius-4,point.y,point.x+radius+4,point.y)
            coordinates=[]
            for i in range(17):
                t=math.pi-i*math.pi/16
                coordinates.append(wx.Point(round(point.x+radius*(math.cos(t) if item['horizontal'] else math.sin(t))),round(point.y+radius*(-math.sin(t) if item['horizontal'] else math.cos(t)))))
            dc.SetPen(wx.Pen(palette['canvas'],6));dc.DrawLines(coordinates)
            dc.SetPen(wx.Pen(color,4 if item['node'] in highlighted else 2));dc.DrawLines(coordinates)
        elif item['kind']=='junction':
            hover=getattr(canvas,'junction_hover',None)
            active=item['node'] in highlighted or hover is not None and math.hypot(hover[0]-item['point'][0],hover[1]-item['point'][1])<8/canvas.zoom
            dc.SetPen(wx.Pen(color,1));dc.SetBrush(wx.Brush(color));dc.DrawCircle(point,max(3,round(4*canvas.zoom)))
            if active:dc.SetBrush(wx.TRANSPARENT_BRUSH);dc.SetPen(wx.Pen(palette['accent'],2));dc.DrawCircle(point,max(8,round(8*canvas.zoom)))
    return markers
