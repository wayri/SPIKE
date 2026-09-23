"""Review and atomically insert executable MODEL cards without replacing a sheet."""
from copy import deepcopy
import re
from .model_import import parse_model_statement
from .document import Document

PINS={'D':('D',('A','K')),'NPN':('Q',('C','B','E')),
      'NMOS':('M',('D','G','S','B')),'BSIMBULK':('M',('D','G','S','B')),
      'BSIMCMG':('M',('D','G','S','E'))}

def is_model_card(text):
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('*')]
    return bool(lines and re.match(r'(?i)^\.model\s',lines[0]) and all(line.startswith('+') for line in lines[1:]))

def prepare(document,text):
    model=parse_model_statement(text);kind=model['model_type'].upper()
    if kind not in PINS:raise ValueError(f'{kind} cannot yet be placed as a native executable model. No substitute model was inserted.')
    prefix,pins=PINS[kind];source=document.data['source']
    names={p['ref'].upper() for p in document.data['components']}
    index=1
    while prefix+str(index) in names:index+=1
    ref=prefix+str(index)
    existing={v.upper() for v in re.findall(r'(?im)^\s*\.model\s+(\S+)',source)}
    name=model['name'];index=1
    while name.upper() in existing:name=model['name']+'_paste'+str(index);index+=1
    statement=re.sub(r'(?i)^(\s*\.model\s+)\S+',lambda m:m[1]+name,model['normalized_statement'],count=1)
    used={str(n).lower() for p in document.data['components'] for n in p['nodes']}
    nodes=[]
    for pin in pins:
        base=f'paste_{ref.lower()}_{pin.lower()}';node=base;index=1
        while node in used:node=base+'_'+str(index);index+=1
        used.add(node);nodes.append(node)
    insertion=statement+'\n'+ref+' '+' '.join(nodes)+' '+name+'\n'
    ending=re.search(r'(?im)^\s*\.end\s*$',source)
    if ending is None:raise ValueError('Current sheet requires a final .end directive')
    candidate=source[:ending.start()]+insertion+source[ending.start():]
    parsed=Document.from_netlist(candidate) # Reject unsupported parameters before mutation.
    part=next(p for p in parsed.data['components'] if p['ref']==ref)
    return dict(source=candidate,base_source=source,part=part,model=statement,
                pin_order=list(zip(pins,nodes)),model_type=kind)

def insert(document,plan,position):
    if document.data['source']!=plan['base_source']:raise ValueError('Sheet changed since review; paste again')
    part=deepcopy(plan['part']);part.update(x=float(position[0]),y=float(position[1]),model_source=plan['model'])
    def mutate(data):
        data['source']=plan['source'];data['components'].append(part)
    document.commit(mutate)
    return part['id']
