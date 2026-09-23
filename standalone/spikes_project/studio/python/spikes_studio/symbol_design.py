"""Pure, grid-based IC symbol editing. Geometry never implies electrical behavior."""
from copy import deepcopy
from .symbol_validation import validate_symbol


def new_symbol():
    return {'id':'user.ic','name':'Custom IC','family':'user','standard':'common-convention',
            'conformance':'unverified','grid':10,'body_keepout':{'min':[-40,-40],'max':[40,40]},
            'label_keepouts':[], 'primitives':[{'kind':'polygon','points':[[-40,-40],[40,-40],[40,40],[-40,40],[-40,-40]]}],
            'terminals':[pin('1','IN','west',0),pin('2','OUT','east',0)]}


def pin(number,name,side,position,bounds=None,grid=10):
    bounds=bounds or {'min':[-40,-40],'max':[40,40]};low,high=bounds['min'],bounds['max']
    position=round(position/grid)*grid
    if side in ('west','east'):
        position=max(low[1],min(high[1],position));x=low[0] if side=='west' else high[0]
        at=[x+(-2*grid if side=='west' else 2*grid),position];end=[x,position]
    elif side in ('north','south'):
        position=max(low[0],min(high[0],position));y=low[1] if side=='north' else high[1]
        at=[position,y+(-2*grid if side=='north' else 2*grid)];end=[position,y]
    else:raise ValueError('Choose a pin side')
    if not str(number).strip() or not str(name).strip():raise ValueError('Pin number and name are required')
    return {'id':str(number).strip(),'name':str(name).strip(),'at':at,'leg_endpoint':end,'direction':side,'connection_indicator':True}


def checked(symbol):
    validate_symbol(symbol)
    if len({tuple(p['at']) for p in symbol['terminals']})!=len(symbol['terminals']):raise ValueError('Pins cannot share a connection point')
    return symbol


def set_pin(symbol,index,number,name,side,position):
    result=deepcopy(symbol);p=pin(number,name,side,position,result['body_keepout'],result['grid'])
    if index is None:result['terminals'].append(p)
    else:result['terminals'][index]=p
    return checked(result)


def drag_pin(symbol,index,x,y):
    low=symbol['body_keepout']['min'];high=symbol['body_keepout']['max']
    def distance(side):
        if side in ('west','east'):return (x-(low[0] if side=='west' else high[0]))**2+(y-max(low[1],min(high[1],y)))**2
        return (y-(low[1] if side=='north' else high[1]))**2+(x-max(low[0],min(high[0],x)))**2
    side=min(('west','east','north','south'),key=distance)
    p=symbol['terminals'][index]
    return set_pin(symbol,index,p['id'],p['name'],side,y if side in ('west','east') else x)


def resize(symbol,width,height):
    result=deepcopy(symbol);g=result['grid'];w=max(g,round(width/(2*g))*g);h=max(g,round(height/(2*g))*g)
    result['body_keepout']={'min':[-w,-h],'max':[w,h]}
    result['primitives']=[{'kind':'polygon','points':[[-w,-h],[w,-h],[w,h],[-w,h],[-w,-h]]}]
    for i,p in enumerate(symbol['terminals']):
        side=p.get('direction','west');position=p['at'][1] if side in ('west','east') else p['at'][0]
        result['terminals'][i]=pin(p['id'],p['name'],side,position,result['body_keepout'],g)
    return checked(result)
