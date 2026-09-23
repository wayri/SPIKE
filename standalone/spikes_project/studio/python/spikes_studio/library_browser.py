"""Indexed catalog queries and atomic, explicit multi-instance insertion plans."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import math
import re
import shlex
from .component_catalog import native_recipe,FAMILIES

SORTS=('Name','Category','Family','Primary value','Execution')


def primary(record):
    key=next(row[1] for row in FAMILIES[record['category']] if row[0]==record['family'])
    return record['parameters'][key]


class CatalogIndex:
    def __init__(self,records):
        self.records=records;self.by_id={r['id']:r for r in records};self.cache=OrderedDict()
        self.text={r['id']:' '.join(str(r.get(k,'') or '') for k in ('id','name','category','family','status','parameter_unit','manufacturer','qualification','fidelity')).casefold() for r in records}
        self.values={r['id']:primary(r) for r in records}

    def query(self,text='',category=None,family=None,status=None,unit=None,minimum=None,maximum=None,sort='Name',descending=False,favorites=(),only_favorites=False,recent=()):
        if len(text)>512:raise ValueError('Search is limited to 512 characters')
        if sort not in SORTS:raise ValueError('Unknown catalog sort')
        for v in (minimum,maximum):
            if v is not None and not math.isfinite(v):raise ValueError('Filter bounds must be finite')
        if minimum is not None and maximum is not None and minimum>maximum:raise ValueError('Minimum exceeds maximum')
        terms=shlex.split(text.casefold());favorites=frozenset(favorites);recent=tuple(recent)
        key=(text,category,family,status,unit,minimum,maximum,sort,descending,favorites,only_favorites,recent)
        if key in self.cache:self.cache.move_to_end(key);return list(self.cache[key])
        predicates=[]
        for term in terms:
            exclude=term.startswith('-');term=term[1:] if exclude else term
            field,value=term.split(':',1) if ':' in term else ('',term)
            if field and field not in ('family','category','status','unit','id','manufacturer','qualification','fidelity'):raise ValueError('Search fields: family:, category:, status:, unit:, id:, manufacturer:, qualification:, fidelity:')
            predicates.append((exclude,'parameter_unit' if field=='unit' else field,value))
        def match(r):
            if category and r['category']!=category or family and r['family']!=family or status and r['status']!=status or unit and r['parameter_unit']!=unit:return False
            if only_favorites and r['id'] not in favorites or recent and r['id'] not in recent:return False
            value=self.values[r['id']]
            if minimum is not None and value<minimum or maximum is not None and value>maximum:return False
            for exclude,field,term in predicates:
                contains=term in (str(r.get(field,'')).casefold() if field else self.text[r['id']])
                if contains==exclude:return False
            return True
        result=[r for r in self.records if match(r)]
        field={'Name':'name','Category':'category','Family':'family','Execution':'status'}.get(sort)
        result.sort(key=lambda r:((str(r[field]).casefold() if field else (r['parameter_unit'],self.values[r['id']])),r['id']),reverse=descending)
        self.cache[key]=tuple(result)
        if len(self.cache)>32:self.cache.popitem(last=False)
        return result


def insertion_plan(document,record,mapping,*,count=1,x=140,y=180,spacing=220):
    """{n} in a node name expands to its 1-based instance index.

    Nodes without {n} are intentionally shared. No guessed parallel wiring.
    Returns candidate source/components without mutating the user's document.
    """
    from .document import Document
    if type(count) is not int or not 1<=count<=100:raise ValueError('Insert 1..100 instances per transaction')
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in (x,y,spacing)) or spacing<100:raise ValueError('Invalid canvas placement')
    model=native_recipe(record)
    if not isinstance(mapping,dict) or set(mapping)!=set(model['pins']):raise ValueError('Map every declared pin exactly once')
    for node in mapping.values():
        if not isinstance(node,str) or not re.fullmatch(r'[A-Za-z0-9_.$:/+-]{1,128}',node.replace('{n}','1')):raise ValueError('Invalid node name; only {n} is expanded for per-instance nets')
    source=document.data['source'];suffix=hashlib.sha256(model['source'].encode()).hexdigest()[:12];name=model['name']+'_'+suffix
    definitions=re.search(r'(?im)^\.subckt\s+'+re.escape(name)+r'\s',source)
    insertion='' if definitions else model['source'].replace(model['name'],name)
    occupied=set(re.findall(r'(?im)^\s*(X\S+)\s',source));occupied={s.upper() for s in occupied};refs=[];number=1
    for i in range(count):
        while f'XCAT{number}' in occupied:number+=1
        ref=f'XCAT{number}';refs.append(ref);occupied.add(ref)
        insertion+=ref+' '+' '.join(mapping[p].replace('{n}',str(i+1)) for p in model['pins'])+' '+name+'\n'
    changed=re.sub(r'(?im)^\s*\.end\s*$',lambda m:insertion+'.end',source)
    if changed==source:changed=source.rstrip()+'\n'+insertion+'.end\n'
    candidate=Document(document.data);candidate.apply_source(changed)
    if len(candidate.data['components'])-len(document.data['components'])>5000:raise ValueError('Insertion exceeds 5,000 flattened primitives')
    groups={ref:[] for ref in refs}
    for part in candidate.data['components']:
        ref=part['ref'].split(':',1)[0].upper()
        if ref in groups:groups[ref].append(part)
    if any(not group for group in groups.values()):raise ValueError('Could not locate flattened inserted instances')
    columns=max(1,min(5,1000//max(spacing,300)));group_width=max(spacing,300)
    for index,ref in enumerate(refs):
        group=groups[ref]
        for j,part in enumerate(group):
            part['x']=x+(index%columns)*group_width+(j%2)*140;part['y']=y+(index//columns)*(180+80*len(group))+(j//2)*130
    return {'source':candidate.data['source'],'components':candidate.data['components'],'title':candidate.data['title'],'refs':refs,'model':name}


def apply_insertion(document,plan,record_id):
    def mutate(data):
        for key in ('source','components','title'):data[key]=deepcopy(plan[key])
        preferences=data['metadata'].setdefault('library_browser',{})
        preferences['recent']=[record_id]+[i for i in preferences.get('recent',[]) if i!=record_id][:49]
    document.commit(mutate)


def validate_preferences(value):
    if not isinstance(value,dict):raise ValueError('Library browser preferences must be an object')
    for field,limit in (('favorites',5000),('recent',50)):
        entries=value.get(field,[])
        if not isinstance(entries,list) or len(entries)>limit or any(not isinstance(v,str) or len(v)>128 for v in entries) or len(set(entries))!=len(entries):raise ValueError('Invalid '+field+' library list')
