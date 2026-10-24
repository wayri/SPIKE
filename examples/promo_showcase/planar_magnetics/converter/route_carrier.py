# SPDX-License-Identifier: Apache-2.0
"""Bounded two-layer geometric candidate routing; native DRC remains authority.

0.5 mm tracks are demonstration geometry, not a 27.8 A thermal/current rating.
"""
from pathlib import Path
import pcbnew as k
import heapq,math,json,time
HERE=Path(__file__).parent;ROOT=HERE.parents[3];OUT=ROOT/'output/promo-planar-magnetics-20261023/converter'
board=k.LoadBoard(str(HERE/'carrier.kicad_pcb'))
step=.5;nx,ny=201,181
owners=[{},{}];pads=[];groups={}
def xy(p):return k.ToMM(p.x),k.ToMM(p.y)
def cell(x,y):return round(x/step),round(y/step)
def mark(layer,x,y,r,net):
    ix,iy=cell(x,y);radius=math.ceil((r+.35)/step)
    for dx in range(-radius,radius+1):
        for dy in range(-radius,radius+1):
            if ((ix+dx)*step-x)**2+((iy+dy)*step-y)**2 <= (r+.18)**2:
                owners[layer].setdefault((ix+dx,iy+dy),set()).add(net)
for f in board.GetFootprints():
    for p in f.Pads():
        x,y=xy(p.GetPosition());net=p.GetNetname();pads.append((net,x,y));groups.setdefault(net,[]).append((x,y))
        for layer in (0,1):mark(layer,x,y,1.5,net)
def okay(node,net,via=False):
    x,y,l=node
    if x<2 or y<2 or x>198 or y>178:return False
    # Physical internal cutout and clearance envelope.
    if 32.5<x*step<67.5 and 33.2<y*step<56.8:return False
    if owners[l].get((x,y),set())-{net}:return False
    if via and owners[1-l].get((x,y),set())-{net}:return False
    return True
def route(a,b,net):
    start=(*cell(*a),0);end=cell(*b);queue=[];dist={start:0};previous={}
    heapq.heappush(queue,(0,0,start));iterations=0
    while queue:
        _,cost,node=heapq.heappop(queue)
        if cost!=dist[node]:continue
        if node[:2]==end:
            path=[node]
            while path[-1] in previous:path.append(previous[path[-1]])
            return path[::-1]
        x,y,l=node
        for nxt,extra in [((x+1,y,l),1),((x-1,y,l),1),((x,y+1,l),1),((x,y-1,l),1),((x,y,1-l),8)]:
            if not okay(nxt,net,nxt[2]!=l):continue
            new=cost+extra
            if new>=dist.get(nxt,float('inf')):continue
            dist[nxt]=new;previous[nxt]=node
            heuristic=abs(nxt[0]-end[0])+abs(nxt[1]-end[1])
            heapq.heappush(queue,(new+heuristic,new,nxt))
        iterations+=1
        if iterations>250000:return None
    return None
def segment(a,b,layer,net):
    if a==b:return
    t=k.PCB_TRACK(board);t.SetStart(k.VECTOR2I(k.FromMM(a[0]),k.FromMM(a[1])));t.SetEnd(k.VECTOR2I(k.FromMM(b[0]),k.FromMM(b[1])));t.SetLayer(k.F_Cu if layer==0 else k.B_Cu);t.SetWidth(k.FromMM(.5));t.SetNetCode(board.GetNetcodeFromNetname(net));board.Add(t)
    length=math.dist(a,b);n=max(1,math.ceil(length/(step/2)))
    for i in range(n+1):mark(layer,a[0]+(b[0]-a[0])*i/n,a[1]+(b[1]-a[1])*i/n,.8,net)
records=[];vias=set()
# Larger buses first, nearest growth minimizes pointless crossing.
for net,points in sorted(groups.items(),key=lambda kv:(0 if kv[0].startswith(('/GP','/GS')) else 1,-len(kv[1]))):
    tree=[points[0]];todo=points[1:]
    while todo:
        _,a,b=min((math.dist(a,b),a,b) for a in tree for b in todo)
        path=route(a,b,net)
        if path is None:
            records.append({'net':net,'from':a,'to':b,'routed':False});todo.remove(b);tree.append(b);continue
        coords=[(x*step,y*step,l) for x,y,l in path]
        segment(a,coords[0][:2],coords[0][2],net)
        for prev,cur in zip(coords,coords[1:]):
            if prev[2]==cur[2]:segment(prev[:2],cur[:2],cur[2],net)
            else:
                key=(cur[0],cur[1],net)
                # An existing through-hole pad already joins both layers; no
                # extra drilled via is needed inside that pad's copper disk.
                existing_pth=any(pnet==net and math.dist((px,py),cur[:2])<.9 for pnet,px,py in pads)
                if key not in vias and not existing_pth:
                    via=k.PCB_VIA(board);via.SetPosition(k.VECTOR2I(k.FromMM(cur[0]),k.FromMM(cur[1])));via.SetWidth(k.FromMM(.8));via.SetDrill(k.FromMM(.4));via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNetCode(board.GetNetcodeFromNetname(net));board.Add(via);vias.add(key)
                for layer in (0,1):mark(layer,cur[0],cur[1],1.0,net)
        segment(coords[-1][:2],b,coords[-1][2],net)
        records.append({'net':net,'from':a,'to':b,'routed':True,'segments':len(path)-1});todo.remove(b);tree.append(b)
k.SaveBoard(str(HERE/'carrier.kicad_pcb'),board)
generation=json.loads((OUT/'native-generation.json').read_text());generation['unrouted']=any(not r['routed'] for r in records);generation['router_connections_routed']=sum(r['routed'] for r in records);(OUT/'native-generation.json').write_text(json.dumps(generation,indent=2)+'\n')
(OUT/'routing-attempt.json').write_text(json.dumps({'records':records,'routed_connections':sum(r['routed'] for r in records),'total_connections':len(records),'track_width_mm':.5,'current_rating':'unqualified','native_DRC_required':True},indent=2)+'\n')
print(json.dumps({'routed':sum(r['routed'] for r in records),'total':len(records)}))
