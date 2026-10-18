"""Indexed catalog queries and atomic, explicit multi-instance insertion plans."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import math
import re
import shlex
from .component_catalog import native_recipe,FAMILIES
from .fuzzy_search import score

SORTS=('Name','Category','Family','Primary value','Execution')
_SUBCKT_HEADER=re.compile(r'^\s*\.subckt\s+([A-Za-z_][A-Za-z0-9_.$+-]*)\b',re.I)
_SUBCKT_END=re.compile(r'^\s*\.ends(?:\s|$)',re.I)


def _subcircuit_blocks(source):
    """Return exact top-level subcircuit blocks keyed case-insensitively."""
    blocks={};start=None;name=None;lines=source.splitlines(keepends=True)
    for index,line in enumerate(lines):
        header=_SUBCKT_HEADER.match(line)
        if header:
            if start is not None:raise ValueError('Nested .subckt definitions are not supported')
            start=index;name=header.group(1);continue
        if start is not None and _SUBCKT_END.match(line):
            block=''.join(lines[start:index+1]).replace('\r\n','\n').rstrip('\n')+'\n'
            blocks.setdefault(name.casefold(),[]).append((name,block));start=None;name=None
    if start is not None:raise ValueError(f'Unterminated .subckt definition: {name}')
    return blocks


def _verified_generated_reuse(document_source,generated_source):
    """Reuse only exact, complete generated definitions; never claim edited source."""
    expected=_subcircuit_blocks(generated_source)
    if not expected:raise ValueError('Generated catalog source has no .subckt definition')
    existing=_subcircuit_blocks(document_source)
    present={name for name in expected if name in existing}
    if not present:return False
    names=', '.join(expected[name][0][0] for name in sorted(expected))
    if present!=set(expected):
        raise ValueError(f'Catalog model definition conflict: only part of generated namespace {names} exists; source was not changed')
    for name,expected_blocks in expected.items():
        existing_blocks=existing[name]
        if len(expected_blocks)!=1 or len(existing_blocks)!=1 or existing_blocks[0][1]!=expected_blocks[0][1]:
            raise ValueError(f'Catalog model definition conflict: existing {expected_blocks[0][0]} is edited or duplicated; source was not changed')
    return True


def primary(record):
    if record.get('model_type')=='packaged_lumped_device_v1':
        from .packaged_device_library import primary_value
        return primary_value(record)
    if record.get('model_type')=='lumped_physics_part_v1':
        from .lumped_physics_library import primary_value
        return primary_value(record)
    key=next(row[1] for row in FAMILIES[record['category']] if row[0]==record['family'])
    return record['parameters'][key]


class CatalogIndex:
    def __init__(self,records):
        self.records=records;self.by_id={r['id']:r for r in records};self.cache=OrderedDict()
        self.text={r['id']:' '.join(str(r.get(k,'') or '') for k in ('id','name','category','family','status','parameter_unit','manufacturer','qualification','fidelity','package_code','construction','passive_kind')).casefold() for r in records}
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
        costs={}
        def match(r):
            if category and r['category']!=category or family and r['family']!=family or status and r['status']!=status or unit and r['parameter_unit']!=unit:return False
            if only_favorites and r['id'] not in favorites or recent and r['id'] not in recent:return False
            value=self.values[r['id']]
            if minimum is not None and value<minimum or maximum is not None and value>maximum:return False
            for exclude,field,term in predicates:
                candidate=str(r.get(field,'')).casefold() if field else self.text[r['id']]
                fuzzy=not field and not exclude and ' ' not in term
                cost=score(candidate,term) if fuzzy else None
                contains=(cost is not None) if fuzzy else term in candidate
                if contains==exclude:return False
                if cost is not None:costs[r['id']]=costs.get(r['id'],0)+cost
            return True
        result=[r for r in self.records if match(r)]
        field={'Name':'name','Category':'category','Family':'family','Execution':'status'}.get(sort)
        result.sort(key=lambda r:((str(r[field]).casefold() if field else (r['parameter_unit'],self.values[r['id']])),r['id']),reverse=descending)
        result.sort(key=lambda r:costs.get(r['id'],0))
        self.cache[key]=tuple(result)
        if len(self.cache)>32:self.cache.popitem(last=False)
        return result


def insertion_plan(document,record,mapping,*,count=1,x=140,y=180,spacing=220,primitive=False):
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
    plain=primitive and not record.get('model_type') and record['family'] in ('resistor','capacitor','inductor','termination','cable')
    generated=model['source'].replace(model['name'],name)
    if plain:insertion=''
    elif record.get('model_type'):
        insertion='' if _verified_generated_reuse(source,generated) else generated
    else:insertion='' if definitions else generated
    occupied=set(re.findall(r'(?im)^\s*([RXCL]\S+)\s',source));occupied={s.upper() for s in occupied};refs=[];number=1
    for i in range(count):
        prefix={'capacitor':'C','inductor':'L'}.get(record['family'],'R')+'NEW' if plain else 'XCAT'
        while f'{prefix}{number}' in occupied:number+=1
        ref=f'{prefix}{number}';refs.append(ref);occupied.add(ref)
        value=record['parameters'][{'capacitor':'c','inductor':'l'}.get(record['family'],'r')] if plain else None
        insertion+=ref+' '+' '.join(mapping[p].replace('{n}',str(i+1)) for p in model['pins'])+' '+(f'{value:.17g}' if plain else name)+'\n'
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
    plan={'source':candidate.data['source'],'components':candidate.data['components'],'title':candidate.data['title'],'refs':refs,'model':name}
    if record.get('model_type')=='lumped_passive_rlc_v1':
        plan['passive_model']={'record':deepcopy(record),'compiled_source_sha256':hashlib.sha256(model['source'].encode()).hexdigest()}
    elif record.get('model_type')=='lumped_physics_part_v1':
        plan['lumped_physics_model']={'record':deepcopy(record),'compiled_source_sha256':hashlib.sha256(model['source'].encode()).hexdigest(),
                                      'pins':list(model['pins']),'model_status':record['model_status']}
    elif record.get('model_type')=='packaged_lumped_device_v1':
        plan['packaged_device_model']={'record':deepcopy(record),'compiled_source_sha256':hashlib.sha256(model['source'].encode()).hexdigest(),
                                       'pins':list(model['pins']),'model_status':record['model_status'],
                                       'core_builder_kind':record['core_builder_kind'],'package_builder':record['package_builder']}
    return plan


def apply_insertion(document,plan,record_id):
    def mutate(data):
        for key in ('source','components','title'):data[key]=deepcopy(plan[key])
        preferences=data['metadata'].setdefault('library_browser',{})
        preferences['recent']=[record_id]+[i for i in preferences.get('recent',[]) if i!=record_id][:49]
        if 'passive_model' in plan:data['metadata'].setdefault('passive_models',{})[plan['model']]=deepcopy(plan['passive_model'])
        if 'lumped_physics_model' in plan:data['metadata'].setdefault('lumped_physics_models',{})[plan['model']]=deepcopy(plan['lumped_physics_model'])
        if 'packaged_device_model' in plan:data['metadata'].setdefault('packaged_device_models',{})[plan['model']]=deepcopy(plan['packaged_device_model'])
    document.commit(mutate)


def validate_preferences(value):
    if not isinstance(value,dict):raise ValueError('Library browser preferences must be an object')
    for field,limit in (('favorites',5000),('recent',50)):
        entries=value.get(field,[])
        if not isinstance(entries,list) or len(entries)>limit or any(not isinstance(v,str) or len(v)>128 for v in entries) or len(set(entries))!=len(entries):raise ValueError('Invalid '+field+' library list')
