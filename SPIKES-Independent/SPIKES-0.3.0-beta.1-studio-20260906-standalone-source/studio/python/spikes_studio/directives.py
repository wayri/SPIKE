"""Source-backed top-level directive annotations; disabled drafts are SPICE comments."""
from copy import deepcopy
import math
import re
import uuid

OFF='* @spikes-off '
GROUPS=('Simulation','Observations','Processing','Models & libraries','Initial conditions','Other')
STRUCTURAL={'.end','.subckt','.ends','.control','.endc','.lib','.endl'}


def group_for(text):
    keyword=text.split()[0].lower()
    if keyword in ('.tran','.op','.ac','.dc','.noise','.pz','.tf','.sens','.disto','.temp','.options'):return 'Simulation'
    if keyword in ('.measure','.meas','.save','.print','.plot','.probe','.four'):return 'Observations'
    if keyword in ('.param','.func','.step'):return 'Processing'
    if keyword in ('.model','.include','.inc'):return 'Models & libraries'
    if keyword in ('.ic','.nodeset','.global'):return 'Initial conditions'
    return 'Other'


def valid_text(text):
    if not isinstance(text,str) or not text.strip() or len(text)>65536:raise ValueError('Enter one directive (maximum 64 KiB)')
    lines=text.strip().splitlines();first=lines[0].strip()
    if not re.match(r'^\.[A-Za-z]+(?:\s|$)',first):raise ValueError('A directive must begin with a dot keyword, e.g. .param')
    if first.split()[0].lower() in STRUCTURAL:raise ValueError('Edit structural .subckt/.control/.lib/.end blocks in Circuit text')
    if any(not line.lstrip().startswith('+') for line in lines[1:]):raise ValueError('One directive per item; subsequent lines must begin with +')
    return '\n'.join(line.strip() for line in lines)


def scan(source):
    lines=source.splitlines();items=[];depth=0;i=1  # first line is SPICE title
    while i<len(lines):
        line=lines[i].strip();disabled=line.startswith(OFF)
        text=line[len(OFF):] if disabled else line
        keyword=text.split()[0].lower() if text else ''
        if not disabled:
            if keyword in ('.subckt','.control') or (keyword=='.lib' and len(text.split())==2):depth+=1
            elif keyword in ('.ends','.endc','.endl'):depth=max(0,depth-1)
        if depth or not keyword.startswith('.') or keyword in STRUCTURAL:i+=1;continue
        start=i;i+=1;parts=[text]
        while i<len(lines):
            following=lines[i].strip()
            if disabled and following.startswith(OFF+'+'):
                parts.append(following[len(OFF):]);i+=1
            elif not disabled and following.startswith('+'):parts.append(following);i+=1
            else:break
        items.append({'text':'\n'.join(parts),'enabled':not disabled,'line':start+1,'end_line':i})
    return items


def reconcile(source,previous=()):
    items=scan(source);unused=list(previous);result=[]
    # Reserve exact matches before matching edited keywords, so inserting a card
    # cannot steal another card's identity or user-assigned group.
    assigned={}
    for index,item in enumerate(items):
        old=next((v for v in unused if v['text']==item['text'] and v['enabled']==item['enabled']),None)
        if old is not None:assigned[index]=old;unused.remove(old)
    for index,item in enumerate(items):
        old=assigned.get(index)
        if old is None:
            old=next((v for v in unused if v['text'].split()[0].lower()==item['text'].split()[0].lower()),None)
            if old is not None:unused.remove(old)
        metadata=deepcopy(old) if old else {'id':uuid.uuid4().hex,'group':group_for(item['text']),
            'title':'','visible':True,'x':100.,'y':420.+index*85.}
        metadata.update(item);result.append(metadata)
    return result


def validate(items,source):
    if len(items)>2000:raise ValueError('At most 2000 directive annotations are allowed')
    if len({v['id'] for v in items})!=len(items):raise ValueError('Duplicate directive ID')
    for item in items:
        for key in ('group','title'):
            if not isinstance(item[key],str) or len(item[key])>128:raise ValueError('Directive group/title must be bounded text')
        if not item['group'].strip():raise ValueError('Choose a directive group')
        if not isinstance(item['visible'],bool):raise ValueError('Canvas visibility must be boolean')
        if any(isinstance(item[k],bool) or not isinstance(item[k],(int,float)) or not math.isfinite(item[k]) or abs(item[k])>1e6 for k in ('x','y')):raise ValueError('Directive position must be finite and within canvas bounds')
    expected=scan(source)
    if [{k:v[k] for k in ('text','enabled','line','end_line')} for v in items]!=expected:raise ValueError('Directive annotations are out of sync with circuit source')


def rewrite(source,item,text,enabled):
    lines=source.splitlines()
    if text is None:replacement=[]
    else:
        text=valid_text(text)
        replacement=[('' if enabled else OFF)+line for line in text.splitlines()]
    if item is None:
        start=next((i for i,line in enumerate(lines) if re.match(r'^\s*\.end\s*(?:;.*)?$',line,re.I)),len(lines));end=start
    else:
        start=item['line']-1;end=item['end_line']
        following=end
        while following<len(lines) and (not lines[following].strip() or lines[following].lstrip().startswith('*')):following+=1
        if following<len(lines) and lines[following].lstrip().startswith('+'):raise ValueError('Continuation separated by comments/blank lines: edit this directive in Circuit text')
    lines[start:end]=replacement
    return '\n'.join(lines)+'\n',start+1
