"""Versioned dashboard layout and real recorded-signal readouts (no synthetic data)."""
from copy import deepcopy
import math
import uuid
import numpy as np

KINDS = ('Meter', 'Scope', 'Indicator', 'Source control')

def empty_dashboard():
    return {'version': 1, 'widgets': []}

def widget(kind, expression=''):
    if kind not in KINDS: raise ValueError('Unknown instrument')
    return dict(id=uuid.uuid4().hex, kind=kind, title=kind, expression=expression,
                x=20, y=20, width=480 if kind=='Scope' else 280, height=280 if kind=='Scope' else 160, minimum=0., maximum=5., source='')

def validate_dashboard(data):
    if not isinstance(data,dict) or data.get('version') != 1: raise ValueError('Unsupported dashboard version')
    rows=data.get('widgets')
    if not isinstance(rows,list) or len(rows)>200: raise ValueError('Dashboard supports up to 200 instruments')
    seen=set()
    for row in rows:
        if not isinstance(row,dict): raise ValueError('Invalid dashboard instrument')
        ident=row.get('id')
        if not isinstance(ident,str) or not ident or ident in seen: raise ValueError('Duplicate or missing instrument ID')
        seen.add(ident)
        if row.get('kind') not in KINDS: raise ValueError('Unsupported dashboard instrument')
        for key in ('title','expression','source'):
            if not isinstance(row.get(key),str) or len(row[key])>2048: raise ValueError('Invalid instrument text')
        for key in ('x','y','width','height','minimum','maximum'):
            value=row.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value): raise ValueError('Instrument dimensions/limits must be finite')
        if not 0<=row['x']<=20000 or not 0<=row['y']<=20000: raise ValueError('Instrument position is outside canvas bounds')
        if not 180<=row['width']<=2000 or not 120<=row['height']<=2000: raise ValueError('Instrument size must be 180–2000 × 120–2000')
        if row['minimum']>=row['maximum']: raise ValueError('Minimum must be less than maximum')
    return data

def update_widget(data,ident,**changes):
    result=deepcopy(data)
    row=next((r for r in result['widgets'] if r['id']==ident),None)
    if row is None: raise ValueError('Select an instrument first')
    row.update(changes)
    return validate_dashboard(result)

def snap(value, minimum=0): return max(minimum,round(value/20)*20)

def scope_bins(time,values,pixels):
    """Time-positioned extrema; retain narrow peaks even with adaptive sample spacing."""
    time=np.asarray(time);values=np.asarray(values)
    if len(time)!=len(values) or len(time)<2 or time[-1]<=time[0]:return []
    if np.any(np.diff(time)<0):raise ValueError('Scope timestamps must be ordered')
    pixels=max(1,min(2000,int(pixels)))
    indices=np.searchsorted(time,np.linspace(time[0],time[-1],pixels+1));indices[-1]=len(time)
    return [(i,float(np.min(values[a:b])),float(np.max(values[a:b])))
            for i,(a,b) in enumerate(zip(indices[:-1],indices[1:])) if b>a]

def read_signal(engine, expression):
    if engine is None: raise ValueError('Run a simulation to acquire data')
    if not expression.strip(): raise ValueError('Bind a signal or expression')
    quantity=engine.evaluate(expression)
    values=np.broadcast_to(quantity.values,engine.time.shape)
    if not len(values): raise ValueError('No acquired samples')
    if np.iscomplexobj(values): raise ValueError('Use abs(), real() or imag() for complex data')
    if not np.all(np.isfinite(values)): raise ValueError('Signal contains non-finite samples')
    return engine.time,values,str(quantity.unit)
