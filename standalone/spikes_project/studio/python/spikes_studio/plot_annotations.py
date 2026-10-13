# SPDX-License-Identifier: Apache-2.0
"""Saved data-coordinate plot annotations with bounded inert text."""
from copy import deepcopy
import math
import uuid


def validate(notes):
    if not isinstance(notes,list) or len(notes)>256:raise ValueError('At most 256 plot annotations')
    ids=set()
    for note in notes:
        if note.get('kind','text') not in ('text','arrow'):raise ValueError('Unknown plot annotation')
        if type(note.get('pane')) is not int or not 0<=note['pane']<16:raise ValueError('Invalid annotation pane')
        if not isinstance(note.get('text'),str) or not note['text'].strip() or len(note['text'])>2000:raise ValueError('Annotation text requires 1–2000 characters')
        for key in ('point','head') if note.get('kind')=='arrow' else ('point',):
            value=note.get(key)
            if not isinstance(value,(list,tuple)) or len(value)!=2 or any(type(v) not in (float,int) or not math.isfinite(v) for v in value):raise ValueError('Annotation coordinates must be finite')
        ident=note.get('id')
        if not isinstance(ident,str) or not ident or ident in ids:raise ValueError('Invalid annotation ID')
        ids.add(ident)


def create(pane,point,text,kind='text',head=None):
    note=dict(id=uuid.uuid4().hex,pane=pane,point=list(point),text=text.strip(),kind=kind)
    if kind=='arrow':note['head']=list(head if head is not None else point)
    validate([note]);return note


def commit(owner,notes):
    validate(notes)
    owner.doc.commit(lambda data:data['metadata'].__setitem__('plot_annotations',deepcopy(notes)))
    owner.update_title()


def sweep_cursor_rows(owner,all_traces=True):
    """Read all actual runs at cursor times; never extrapolate missing coverage."""
    from .plot_workspace import sample,format_value
    expressions=[t[0] for t in owner.traces]
    count=len(owner.cursors)*len(owner.run_engines)*(len(expressions) if all_traces else 1)
    if count>16384:raise ValueError('Sweep table exceeds 16,384 readings; reduce cursors/traces or runs')
    rows=[]
    for i in range(len(owner.cursors)):
        cursor=owner.cursor_descriptor(i)
        for run,engine in enumerate(owner.run_engines):
            if engine is None:continue
            result=owner.run_results[run] if run<len(owner.run_results) else {}
            parameters=result.get('provenance',{}).get('step_parameters',{})
            coordinate=', '.join(f'{key}={value:g}' if isinstance(value,(int,float)) else f'{key}={value}' for key,value in parameters.items()) or 'single run / no step coordinates'
            for expression in expressions if all_traces else [cursor['expression']]:
                try:value=format_value(sample(engine,expression,cursor['time']))
                except (ValueError,KeyError,IndexError) as error:value='Unavailable: '+str(error)
                rows.append((chr(65+i),str(run+1),coordinate,expression,f"{cursor['time']:.12g}",value))
    return rows
