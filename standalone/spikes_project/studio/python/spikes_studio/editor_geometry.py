"""Quarter-turn component geometry shared by rendering and electrical routes."""
from heapq import heappop, heappush
def transform(part,x,y):
    if part.get('mirror_x',False):x=-x
    if part.get('mirror_y',False):y=-y
    for _ in range(part.get('rotation',0)//90):x,y=-y,x
    return part['x']+x,part['y']+y


def select_box(parts,start,end):
    """Select component centers in a world-coordinate rectangle, boundary included."""
    left,right=sorted((start[0],end[0]));top,bottom=sorted((start[1],end[1]))
    return [p['id'] for p in parts if left<=p['x']<=right and top<=p['y']<=bottom]


def select_lasso(parts,polygon):
    """Select component centers inside a polygon; on-edge centers are included."""
    if len(polygon)<3:return []
    def contains(x,y):
        inside=False
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            ax,ay=a;bx,by=b
            cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax)
            if abs(cross)<=1e-9*max(1,abs(bx-ax)+abs(by-ay)) and min(ax,bx)<=x<=max(ax,bx) and min(ay,by)<=y<=max(ay,by):return True
            if (ay>y)!=(by>y) and x<(bx-ax)*(y-ay)/(by-ay)+ax:inside=not inside
        return inside
    return [p['id'] for p in parts if contains(p['x'],p['y'])]


def terminal(part,index):
    from .pin_geometry import pins
    if type(index) is not int or not 0<=index<len(pins(part)):raise ValueError('Unknown terminal index')
    return transform(part,*pins(part)[index].anchor)


def route(parts,wire):
    """Route around endpoint symbol envelopes, preserving outward terminal leads.

    This is a small orthogonal visibility graph, not a complete schematic router:
    other components, labels and wires are not obstacles. Overlapping endpoint
    envelopes cannot always be routed without a collision.
    """
    a,b=(parts[e[0]] for e in (wire['a'],wire['b']))
    i,j=wire['a'][1],wire['b'][1];start=terminal(a,i);end=terminal(b,j)
    if wire.get('waypoints'):
        points=[start]
        for target in [*map(tuple,wire['waypoints']),end]:
            if points[-1][0]!=target[0] and points[-1][1]!=target[1]:points.append((target[0],points[-1][1]))
            if points[-1]!=target:points.append(target)
        return points
    boxes=[]
    for part in (a,b):
        from .pin_geometry import pins
        anchors=[pin.anchor for pin in pins(part)]
        xs=[-55,55]+[p[0] for p in anchors];ys=[-30,30]+[p[1] for p in anchors]
        corners=[transform(part,x,y) for x in (min(xs),max(xs)) for y in (min(ys),max(ys))]
        boxes.append((min(p[0] for p in corners),min(p[1] for p in corners),
                      max(p[0] for p in corners),max(p[1] for p in corners)))
    def stub(part,index,point,other):
        from .pin_geometry import pins
        pin=pins(part)[index]
        vx,vy=pin.anchor[0]-pin.body[0],pin.anchor[1]-pin.body[1]
        length=abs(vx)+abs(vy)
        far=transform(part,pin.anchor[0]+25*vx/length,pin.anchor[1]+25*vy/length)
        dx,dy=(far[0]-point[0])/25,(far[1]-point[1])/25
        left,top,right,bottom=other;distance=25
        # Shorten the lead when two distinct bodies are closely packed.
        if dx and top<point[1]<bottom:
            entry=((left if dx>0 else right)-point[0])/dx
            if entry>0:distance=min(distance,entry/2)
        if dy and left<point[0]<right:
            entry=((top if dy>0 else bottom)-point[1])/dy
            if entry>0:distance=min(distance,entry/2)
        return point[0]+dx*distance,point[1]+dy*distance
    sa=stub(a,i,start,boxes[1]);sb=stub(b,j,end,boxes[0])
    def clear(p,q):
        for left,top,right,bottom in boxes:
            if p[0]==q[0] and left<p[0]<right and max(min(p[1],q[1]),top)<min(max(p[1],q[1]),bottom):return False
            if p[1]==q[1] and top<p[1]<bottom and max(min(p[0],q[0]),left)<min(max(p[0],q[0]),right):return False
        return True
    xs=sorted({sa[0],sb[0]}|{x for l,t,r,d in boxes for x in (l-10,r+10)})
    ys=sorted({sa[1],sb[1]}|{y for l,t,r,d in boxes for y in (t-10,d+10)})
    origin=(xs.index(sa[0]),ys.index(sa[1]));target=(xs.index(sb[0]),ys.index(sb[1]))
    queue=[(0,origin)];cost={origin:0};previous={}
    while queue:
        distance,node=heappop(queue)
        if distance!=cost[node]:continue
        if node==target:break
        x,y=node;p=(xs[x],ys[y])
        for nx,ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if not (0<=nx<len(xs) and 0<=ny<len(ys)):continue
            q=(xs[nx],ys[ny]);neighbor=(nx,ny)
            if not clear(p,q):continue
            candidate=distance+abs(p[0]-q[0])+abs(p[1]-q[1])
            if candidate<cost.get(neighbor,float('inf')):
                cost[neighbor]=candidate;previous[neighbor]=node;heappush(queue,(candidate,neighbor))
    if target not in cost:
        # Keep the drawing usable for physically overlapping symbols; moving the
        # symbols apart is required to make the route unambiguous.
        return [start,sa,(sa[0],sb[1]),sb,end]
    nodes=[target]
    while nodes[-1]!=origin:nodes.append(previous[nodes[-1]])
    points=[start]+[(xs[x],ys[y]) for x,y in reversed(nodes)]+[end]
    result=[]
    for point in points:
        if result and point==result[-1]:continue
        while len(result)>1 and ((result[-2][0]==result[-1][0]==point[0]) or
                                 (result[-2][1]==result[-1][1]==point[1])):
            # Do not erase a reversal; it exposes an overlapping-symbol route.
            p,q=result[-2:]
            if (q[0]-p[0])*(point[0]-q[0])+(q[1]-p[1])*(point[1]-q[1])<0:break
            result.pop()
        result.append(point)
    return result
