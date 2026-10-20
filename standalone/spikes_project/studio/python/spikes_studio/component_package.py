# SPDX-License-Identifier: Apache-2.0
"""Versioned, inert user components. A symbol is not evidence of executability."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from .document import Document,write_json
from .symbol_validation import validate_symbol
from .symbol_design import new_symbol,pin

CONTRACT='spikes/component-package/v1'
MAX_BYTES=2*1024*1024
IDENT=re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,95}\Z')
NODE=re.compile(r'[A-Za-z0-9_.$:/+-]{1,128}\Z')
LANGUAGES=('SPICE','C++','Verilog')


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')


def symbol_for_pins(names,name='User component'):
    if not 1<=len(names)<=256:raise ValueError('Components need 1..256 pins')
    symbol=new_symbol();symbol.update(name=name)
    rows=(len(names)+1)//2;half=max(40,rows*10+10)
    symbol['body_keepout']={'min':[-50,-half],'max':[50,half]}
    symbol['primitives']=[{'kind':'polygon','points':[[-50,-half],[50,-half],[50,half],[-50,half],[-50,-half]]}]
    symbol['terminals']=[]
    for index,name in enumerate(names):
        side='west' if index<rows else 'east';row=index if index<rows else index-rows
        item=pin(str(index+1),name,side,(row-(rows//2))*20,symbol['body_keepout'],10)
        item['mode']='AI' if side=='west' else 'AO';symbol['terminals'].append(item)
    return symbol


def new_component():
    return {'contract':CONTRACT,'id':'user.component','name':'User component','version':'1.0.0',
        'description':'User-defined model; qualification not performed.',
        'license':'User-supplied; review before redistribution',
        'symbol':symbol_for_pins(['IN','OUT']),
        'implementation':{'language':'SPICE','entry':'UserPart','prefix':'X',
            'source':'.subckt UserPart IN OUT\nR1 IN OUT 1k\n.ends UserPart\n'}}


def _symbol(symbol):
    validate_symbol(symbol)
    if len({p['name'].casefold() for p in symbol['terminals']})!=len(symbol['terminals']):raise ValueError('Pin names must be unique')
    for item in symbol['terminals']:
        if not isinstance(item.get('name'),str) or not NODE.fullmatch(item['name']):raise ValueError('Pin names must be safe SPICE net identifiers')
        if item.get('mode','AI') not in ('AI','DI','AO','DO'):raise ValueError('Pin modes are AI/DI/AO/DO')
    def point(p):
        if not isinstance(p,list) or len(p)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>100000 for x in p):raise ValueError('Invalid symbol coordinate')
    if len(symbol['primitives'])>1024:raise ValueError('Symbol geometry limit: 1024 shapes')
    for primitive in symbol['primitives']:
        if primitive.get('kind')=='circle':
            point(primitive['center']);radius=primitive['radius']
            if type(radius) not in (int,float) or not math.isfinite(radius) or not 0<radius<=100000:raise ValueError('Invalid circle radius')
        elif primitive.get('kind') in ('line','polyline','polygon'):
            pts=primitive.get('points')
            if not isinstance(pts,list) or not 2<=len(pts)<=4096:raise ValueError('Invalid shape points')
            for p in pts:point(p)
        else:raise ValueError('Supported shapes: line, polyline, polygon and circle')


def validate(value):
    if not isinstance(value,dict) or value.get('contract')!=CONTRACT:raise ValueError('Unsupported component package')
    if set(value)-{'contract','id','name','version','description','license','symbol','implementation','origin'}:raise ValueError('Unknown component fields')
    if not IDENT.fullmatch(value.get('id','')):raise ValueError('Use a bounded component ID, e.g. user.my_part')
    if not isinstance(value.get('version'),str) or len(value['version'])>64 or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',value['version']):raise ValueError('Use a semantic version such as 1.0.0')
    for key in ('name','license','description'):
        if not isinstance(value.get(key),str) or not value[key].strip() or len(value[key])>4096:raise ValueError('Missing or oversized '+key)
    _symbol(value['symbol'])
    impl=value['implementation']
    if not isinstance(impl,dict) or set(impl)-{'language','entry','prefix','source','controller'}:raise ValueError('Unknown implementation fields')
    if impl.get('language') not in LANGUAGES:raise ValueError('Choose SPICE, C++ or Verilog')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.$-]{0,95}',impl.get('entry','')):raise ValueError('Invalid model/module entry name')
    if not isinstance(impl.get('source'),str) or not impl['source'].strip() or '\x00' in impl['source'] or len(impl['source'].encode())>1024*1024:raise ValueError('Model source must be nonempty text, at most 1 MiB')
    if impl['language']=='SPICE':
        from .vendor_intake import inspect_text
        inventory=inspect_text(impl['source'])
        declarations=[(row,kind) for kind in ('models','subcircuits') for row in inventory[kind] if row['name'].casefold()==impl['entry'].casefold()]
        if len(declarations)!=1:raise ValueError('Select exactly one declared MODEL/SUBCKT entry')
        declaration,kind=declarations[0]
        if not re.fullmatch(r'[A-Z]',impl.get('prefix','')):raise ValueError('Choose an explicit one-letter SPICE instance prefix')
        if kind=='subcircuits':
            if impl['prefix']!='X':raise ValueError('A SUBCKT uses prefix X')
            if [p['name'].casefold() for p in value['symbol']['terminals']]!=[n.casefold() for n in declaration['pins']]:raise ValueError('Symbol pin names/order must match the selected SUBCKT header')
        elif impl['prefix']=='X':raise ValueError('MODEL cards require a primitive prefix, not X')
    elif impl['language']=='C++':
        from .controller_block import validate as validate_controller
        config=impl.get('controller')
        if not isinstance(config,dict) or config.get('source')!=impl['source'] or config.get('language')!='C++':raise ValueError('C++ components require their matching sampled-controller configuration')
        validate_controller(config)
        if impl['entry']!='control_step':raise ValueError('The sampled C++ ABI entry is control_step')
        if [(p['name'],p['mode']) for p in config['pins']]!=[(p['name'],p.get('mode','AI')) for p in value['symbol']['terminals']]:raise ValueError('Controller pins and symbol pins differ')
    if len(_canonical(value))>MAX_BYTES:raise ValueError('Component package limit: 2 MiB')
    return value


def behavior_digest(value):
    validate(value)
    return hashlib.sha256(_canonical({'implementation':value['implementation'],
        'pins':[(p['id'],p['name'],p.get('mode','AI')) for p in value['symbol']['terminals']]})).hexdigest()


def load(path):
    with Path(path).open('rb') as stream:data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('Component package exceeds 2 MiB')
    def pairs(rows):
        result={}
        for key,item in rows:
            if key in result:raise ValueError('Duplicate component JSON key')
            result[key]=item
        return result
    return validate(json.loads(data.decode('utf-8-sig'),object_pairs_hook=pairs))


def save(path,value):
    validate(value);write_json(path,value)


def from_spice(source,entry=None,prefix=None,pin_names=None):
    from .vendor_intake import inspect_text
    report=inspect_text(source)
    choices=[(r,'X') for r in report['subcircuits']]+[(r,None) for r in report['models']]
    matches=[(r,p) for r,p in choices if entry is None or r['name'].casefold()==entry.casefold()]
    if len(matches)!=1:raise ValueError('Choose a model entry explicitly when the source has multiple declarations')
    row,default_prefix=matches[0];entry=row['name']
    if default_prefix=='X':names=row['pins'];prefix='X'
    else:
        # Only infer known conventional mappings; unknown families remain user-defined.
        types={'D':('D',['A','K']),'NPN':('Q',['C','B','E']),'PNP':('Q',['C','B','E']),
               'NMOS':('M',['D','G','S','B']),'PMOS':('M',['D','G','S','B'])}
        inferred=types.get(row['type'].upper())
        prefix=prefix or (inferred[0] if inferred else None)
        names=pin_names or (inferred[1] if inferred else None)
        if not prefix or not names:raise ValueError('For this MODEL family, explicitly supply its prefix and ordered pins')
    value=new_component();safe=re.sub(r'[^A-Za-z0-9_.-]','_',entry)
    value.update(id='user.'+safe[:80],name=entry,symbol=symbol_for_pins(names,entry))
    value['implementation']={'language':'SPICE','entry':entry,'prefix':prefix,'source':source}
    return validate(value)


def controller_config(symbol,source,step_s=1e-4,state_count=8):
    from .controller_block import CONTRACT as CC
    return {'contract':CC,'language':'C++','step_s':step_s,'state_count':state_count,'source':source,
        'pins':[{'name':p['name'],'mode':p.get('mode','AI'),'node':p['name'],
                 'reference':'0','source':'V'+p['name'],'vdd':3.3} for p in symbol['terminals']]}


class ComponentStore:
    """Separate versioned user components, not hard-coded generic family presets."""
    def __init__(self,root):self.root=Path(root)
    def install(self,value):
        validate(value);target=self.root/(value['id']+'--'+value['version']+'.spkcmp')
        if target.is_symlink():raise ValueError('Linked library entries are not accepted')
        if target.exists() and _canonical(load(target))!=_canonical(value):raise ValueError('This ID/version exists with different content; bump the version or fork the ID')
        self.root.mkdir(parents=True,exist_ok=True);save(target,value);return target
    def entries(self):
        result=[]
        for path in sorted(self.root.glob('*.spkcmp'))[:1001]:
            if len(result)>=1000:raise ValueError('User library limit: 1000 component versions')
            if path.is_symlink():raise ValueError('Linked library entries are not accepted')
            value=load(path);result.append({'path':path,'component':value})
        return result


def portable_spice_source(model):
    # Storage accepts unknown dialects; executable insertion never runs host commands.
    directives=re.findall(r'(?im)^\s*(\.\w+)',model)
    allowed={'.model','.subckt','.ends','.param','.func'}
    if any(d.casefold() not in allowed for d in directives):raise ValueError('Inline model dependencies and remove analyses/global/host directives before circuit insertion; original package is preserved')
    depth=0
    for line in model.splitlines():
        tokens=line.split()
        if not tokens or tokens[0].startswith(('*',';','+')):continue
        head=tokens[0].casefold()
        if head=='.subckt':depth+=1
        elif head=='.ends':depth-=1
        elif depth==0 and not head.startswith('.'):raise ValueError('Remove top-level testbench instances before insertion; model source remains preserved')
        if depth<0:raise ValueError('Unmatched .ends in model source')
    if depth:raise ValueError('Unclosed SUBCKT in model source')


def prepare_insert(document,value,mapping,position=(140,180)):
    validate(value);impl=value['implementation']
    if impl['language']!='SPICE':raise ValueError('C++ uses sampled-controller attachment; Verilog uses the HDL workspace, not analog-MNA insertion')
    pins=value['symbol']['terminals']
    if set(mapping)!={p['id'] for p in pins} or any(not isinstance(n,str) or not NODE.fullmatch(n) for n in mapping.values()):raise ValueError('Map every symbol pin to an explicit valid circuit node')
    if len(position)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in position):raise ValueError('Invalid placement coordinates')
    source=document.data['source'];model=impl['source'];portable_spice_source(model)
    key=hashlib.sha256(_canonical(value)).hexdigest()
    installed=document.data['metadata'].get('component_packages',{})
    if key in installed:
        if installed[key]!=value or model.strip() not in source:raise ValueError('The previously inserted component definition was modified')
        definitions=''
    else:
        old={n.casefold() for n in re.findall(r'(?im)^\s*\.(?:model|subckt)\s+(\S+)',source)}
        new={n.casefold() for n in re.findall(r'(?im)^\s*\.(?:model|subckt)\s+(\S+)',model)}
        if old&new:raise ValueError('Model names conflict with this circuit: '+', '.join(sorted(old&new)))
        definitions=model.rstrip()+'\n'
    used={n.casefold() for n in re.findall(r'(?m)^\s*(\S+)',source)};serial=1
    while (impl['prefix']+'CMP'+str(serial)).casefold() in used:serial+=1
    ref=impl['prefix']+'CMP'+str(serial)
    instance=ref+' '+' '.join(mapping[p['id']] for p in pins)+' '+impl['entry']+'\n'
    ends=list(re.finditer(r'(?im)^[ \t]*\.end[ \t]*\r?$',source))
    if len(ends)!=1:raise ValueError('Current circuit needs one final .end')
    index=ends[0].start();candidate=Document(deepcopy(document.data))
    candidate.apply_source(source[:index]+definitions+instance+source[index:])
    parts=[p for p in candidate.data['components'] if p['ref'].casefold()==ref.casefold() or p['ref'].casefold().startswith(ref.casefold()+':')]
    if not parts:raise ValueError('The model produced no native components')
    for index,part in enumerate(parts):
        part.update(x=position[0]+index%4*140,y=position[1]+index//4*120)
    if impl['prefix']!='X' and len(parts)==1 and len(parts[0]['nodes'])==len(pins):
        symbol=deepcopy(value['symbol'])
        if parts[0]['kind'] in ('npn_ebers_moll','nmos_level1','bsim_bulk','bsim_cmg','gan_hemt','sic_mosfet') and len(pins)>=3:
            symbol['terminals']=[symbol['terminals'][0],symbol['terminals'][2],symbol['terminals'][1],*symbol['terminals'][3:]]
        parts[0]['parameters']['component_symbol']=symbol
    candidate.data['metadata'].setdefault('component_packages',{})[key]=deepcopy(value)
    record={'ref':ref,'package_sha256':key,'pins':dict(mapping)}
    if impl['prefix']=='X':record['projection']={'x':position[0],'y':position[1],'rotation':0,'mirror_x':False,'mirror_y':False}
    candidate.data['metadata'].setdefault('component_instances',[]).append(record)
    candidate.validate()
    return {'data':candidate.data,'base_source':source,'base_revision':document.data['revision'],'part_ids':[p['id'] for p in parts],'ref':ref}


def insert(document,plan):
    if document.data['source']!=plan['base_source'] or document.data['revision']!=plan['base_revision']:raise ValueError('Circuit changed since component preview; prepare again')
    def apply(data):
        revision=data['revision'];data.clear();data.update(deepcopy(plan['data']));data['revision']=revision
    document.commit(apply);return plan['part_ids']
