# SPDX-License-Identifier: Apache-2.0
"""Bounded canvas search/completion. Availability comes from installed records."""
from .directive_forms import SPECS,new_form
from .fuzzy_search import matches, ranked, score


PRIMITIVES=(('Resistor','resistor','R'),('Capacitor','capacitor','C'),('Inductor','inductor','L'),('Diode','diode','D'))
MONITORS=('Voltage meter','Current meter','Power meter','Mini scope')


def suggestions(query,records=(),manufacturers=(),nets=(),refs=(),category='All',limit=48):
    if not isinstance(query,str) or len(query)>8192:raise ValueError('Search text limit is 8192 characters')
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Suggestion limit must be 1..100')
    q=query.strip();rows=[]
    def match(text):return matches(text,q)
    def add(kind,label,payload='',icon='component',detail='',completion=False):rows.append(dict(kind=kind,label=label,payload=payload,icon=icon,detail=detail,completion=completion))
    if category in ('All','SPICE'):
        for spec in SPECS:
            token='.'+spec.key
            if not q or (q.startswith('.') and ' ' not in q and token.startswith(q.casefold())) or not q.startswith('.') and match(spec.label+' '+token):
                add('complete',token+' - '+spec.label,new_form(spec.key).render(),'analysis','Fill a template; Enter again to validate/place',True)
    if category in ('All','Components'):
        for name,family,alias in PRIMITIVES:
            if match(name) or q.casefold()==alias.casefold():add('component',name,'generic.'+family+'.001',family,'Configure values and pins before placement')
        if q and not q.startswith('.'):
            for record in ranked(manufacturers,q,text=lambda r:r['manufacturer']+' '+r['mpn']+' '+r['category']+' '+r['description']):
                if match(record['manufacturer']+' '+record['mpn']+' '+record['category']+' '+record['description']):
                    ready=record['model']['readiness']=='placeable_ideal_nominal'
                    add('manufacturer' if ready else 'manufacturer_review',record['manufacturer']+' '+record['mpn'],record['id'],record['category'],'Ideal nominal approximation' if ready else 'Review only - no runnable model installed')
            for record in ranked(records,q,text=lambda r:r['id']+' '+r['name']+' '+r['family']+' '+r['category'])[:limit]:
                if match(record['id']+' '+record['name']+' '+record['family']+' '+record['category']):
                    if record['id'] in {r['payload'] for r in rows}:continue
                    ready=record['status']=='native_subcircuit'
                    add('component' if ready else 'review',record['name'],record['id'],record['family'],'Native recipe' if ready else 'Equation bench only - opens review')
    if category in ('All','Monitors'):
        for name in MONITORS:
            if match(name) or q.casefold()=='monitor':add('monitor',name,name,'probe','Choose an actual net/component or signal expression')
    if q and category in ('All','Text','SPICE'):
        direct=dict(kind='spice',label='Add as SPICE directive',payload=q,icon='analysis',detail='Native syntax is validated before commit',completion=False)
        note=dict(kind='text',label='Add as text',payload=q,icon='note',detail='Annotation only; never executed',completion=False)
        if category in ('All','SPICE') and q.startswith('.'):
            if ' ' in q or q.casefold()=='.op':rows.insert(0,direct)
            else:rows.append(direct)
        if category in ('All','Text'):rows.append(note)
    # Expression completion does not create measurements from invented samples.
    if q and category in ('All','Monitors','SPICE'):
        for expression in [*(f'V({n})' for n in sorted(set(nets))),*(f'I({r})' for r in sorted(set(refs))),*(f'P({r})' for r in sorted(set(refs))), 'abs()', 'sqrt()', 'sin()', 'cos()', 'exp()', 'log()']:
            if expression.casefold().startswith(q.casefold()):add('complete',expression,expression,'probe','Insert known signal / function name',True)
        if q.endswith(')') and '(' in q and not q.startswith('.'):
            name='Current meter' if q.upper().startswith('I(') else 'Power meter' if q.upper().startswith('P(') else 'Voltage meter'
            rows.insert(0,dict(kind='monitor',label='Add meter for '+q,payload=name,icon='probe',detail='Review signal / mathematical expression',completion=False,expression=q))
    if not q:rows.sort(key=lambda r:{'component':0,'monitor':1,'complete':2}.get(r['kind'],3))
    else:
        # Explicit text/directive actions stay where authored; only discovery rows rank.
        discovery=[r for r in rows if r['kind'] not in ('spice','text')]
        def relevance(row):
            value=score(row['label']+' '+row['payload'],q)
            return 100000 if value is None else value
        discovery.sort(key=relevance)
        iterator=iter(discovery);rows=[r if r['kind'] in ('spice','text') else next(iterator) for r in rows]
        exact={'generic.'+family+'.001' for name,family,alias in PRIMITIVES if q.casefold() in (name.casefold(),alias.casefold())}
        if exact:rows.sort(key=lambda r:r['payload'] not in exact)
    return rows[:limit]
