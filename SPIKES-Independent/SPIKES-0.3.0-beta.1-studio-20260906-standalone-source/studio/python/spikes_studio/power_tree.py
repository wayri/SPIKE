"""Power-budget tree and explicit real-subcircuit composition, never inferred converter physics."""
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import re
import uuid

CONTRACT='spikes/power-tree/v1'

def empty_tree():return {'contract':CONTRACT,'stages':[]}

def new_stage(kind='source',parent=None):
    return {'id':'n'+uuid.uuid4().hex[:12],'name':'Supply' if kind=='source' else 'Converter' if kind=='converter' else 'Load',
        'kind':kind,'parent':parent,'voltage_v':12. if kind=='source' else 3.3,'current_a':.1,'max_current_a':.2,
        'efficiency':1. if kind=='source' else .9,'quiescent_a':0.,'limit_a':1.,'model':None}

def read_model(path):
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('Subcircuit source exceeds 1 MiB')
    return model_from_text(path.read_text(encoding='utf-8-sig'),str(path.resolve()))

def model_from_text(source,path=''):
    if not isinstance(source,str) or len(source.encode())>1024*1024:raise ValueError('Subcircuit source exceeds 1 MiB')
    # Self-contained snapshots are reproducible and do not cause implicit file reads.
    if re.search(r'^\s*\.(?:include|inc|lib|control)\b',source,re.I|re.M):raise ValueError('Use a self-contained .SUBCKT file; includes/control scripts are not imported automatically')
    declarations=re.findall(r'^\s*\.subckt\s+(\S+)\s+([^\n]+)',source,re.I|re.M)
    if len(declarations)!=1:raise ValueError('Import one self-contained .SUBCKT definition per stage')
    name,tail=declarations[0];ports=[]
    for token in tail.split():
        if '=' in token or token.lower()=='params:':break
        ports.append(token)
    if not re.fullmatch(r'[A-Za-z_][\w.-]*',name) or not 2<=len(ports)<=64:raise ValueError('Subcircuit needs a valid name and 2..64 ports')
    if len(set(ports))!=len(ports):raise ValueError('Duplicate subcircuit ports')
    if len(re.findall(r'^\s*\.ends\b',source,re.I|re.M))!=1:raise ValueError('Expected one matching .ENDS')
    inside=False;model_card=False
    for raw in source.splitlines():
        line=raw.strip()
        if not line or line.startswith('*'):continue
        key=line.split()[0].lower()
        if key=='.subckt':inside=True;continue
        if key=='.ends':inside=False;continue
        if not inside:
            if key=='.model':model_card=True
            elif not (line.startswith('+') and model_card):raise ValueError('Outside .SUBCKT only comments and .MODEL cards are allowed (no top-level sources or .END)')
    if inside:raise ValueError('Unterminated subcircuit')
    roles={'IN':'{in}','INPUT':'{in}','VIN':'{in}','OUT':'{out}','OUTPUT':'{out}','VOUT':'{out}',
           'GND':'{gnd}','GROUND':'{gnd}','0':'{gnd}'}
    return {'name':name,'ports':ports,'source':source,'path':path,'sha256':hashlib.sha256(source.encode()).hexdigest(),
        'bindings':[roles.get(port.upper(),'') for port in ports]}

def validate(tree):
    if tree.get('contract')!=CONTRACT or not isinstance(tree['stages'],list) or len(tree['stages'])>256:raise ValueError('Invalid power tree; maximum 256 stages')
    stages=tree['stages'];by_id={s['id']:s for s in stages}
    if len(by_id)!=len(stages):raise ValueError('Duplicate stage ID')
    for s in stages:
        if not re.fullmatch(r'n[a-z0-9]{1,32}',s['id']):raise ValueError('Invalid stage ID')
        if not isinstance(s['name'],str) or not s['name'].strip() or len(s['name'])>128:raise ValueError('Stage name must be 1..128 characters')
        if s['kind'] not in ('source','converter','load'):raise ValueError('Invalid stage kind')
        if s['kind']=='source' and s['parent'] is not None:raise ValueError('Supply stages are roots')
        if s['kind']!='source' and (s['parent'] not in by_id or by_id[s['parent']]['kind']=='load'):raise ValueError('Converter/load must connect to a supply or converter parent')
        for key in ('voltage_v','current_a','max_current_a','efficiency','quiescent_a','limit_a'):
            value=s[key]
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError(f'{key} must be finite and nonnegative')
        if s['voltage_v']<=0 or not 0<s['efficiency']<=1 or s['limit_a']<=0 or s['max_current_a']<s['current_a']:raise ValueError('Require positive voltage/current limit, 0 < efficiency ≤ 1, and max demand ≥ typical')
        seen={s['id']};parent=s['parent']
        while parent is not None:
            if parent in seen:raise ValueError('Power tree contains a cycle')
            seen.add(parent);parent=by_id[parent]['parent']
        model=s['model']
        if model:
            actual=model_from_text(model['source'],model.get('path',''))
            if any(model[k]!=actual[k] for k in ('name','ports','sha256')):raise ValueError('Subcircuit snapshot metadata does not match its contents')
            if not isinstance(model['bindings'],list) or len(model['bindings'])!=len(model['ports']) or any(not isinstance(v,str) or (v not in ('{in}','{out}','{gnd}') and not re.fullmatch(r'[A-Za-z0-9_.$:-]+',v)) for v in model['bindings']):raise ValueError('Assign each port to {in}, {out}, {gnd}, or an explicit net name')

def budgets(tree,maximum=False):
    validate(tree);by_id={s['id']:s for s in tree['stages']};report={}
    def calculate(s):
        vin=by_id[s['parent']]['voltage_v'] if s['parent'] else s['voltage_v']
        if s['kind']=='load':
            current=s['max_current_a'] if maximum else s['current_a'];pin=vin*current
            item=dict(input_w=pin,output_w=pin,loss_w=0.,input_a=current,output_a=current,output_v=vin)
        else:
            pout=sum(calculate(c)['input_w'] for c in by_id.values() if c['parent']==s['id'])
            pin=pout/s['efficiency']+vin*s['quiescent_a'];iout=pout/s['voltage_v']
            item=dict(input_w=pin,output_w=pout,loss_w=pin-pout,input_a=pin/vin,output_a=iout,output_v=s['voltage_v'])
        item['over_limit']=item['output_a']>s['limit_a'];report[s['id']]=item;return item
    for s in by_id.values():
        if s['parent'] is None:calculate(s)
    return {'basis':'Declared steady-state budget assumptions, not SPICE results','case':'maximum' if maximum else 'typical','stages':report,
        'total_input_w':sum(report[s['id']]['input_w'] for s in by_id.values() if s['parent'] is None),
        'conversion_loss_w':sum(v['loss_w'] for v in report.values())}

def compile_tree(tree):
    validate(tree)
    if not tree['stages']:raise ValueError('Add power stages first')
    definitions={};lines=['SPIKES power tree — explicit stage models'];by_id={s['id']:s for s in tree['stages']}
    for s in tree['stages']:
        output='rail_'+s['id'];incoming='rail_'+s['parent'] if s['parent'] else output
        if s['model']:
            model=s['model'];key=model['name'].lower()
            if key in definitions and definitions[key]!=model['source']:raise ValueError('Two different subcircuits use the same model name; rename one explicitly')
            definitions[key]=model['source']
            nodes=[{'{in}':incoming,'{out}':output,'{gnd}':'0'}.get(v,v) for v in model['bindings']]
            lines.append('X'+s['id']+' '+' '.join(nodes)+' '+model['name'])
        elif s['kind']=='source':lines.append(f'V{s["id"]} {output} 0 {s["voltage_v"]:.12g}')
        elif s['kind']=='load':lines.append(f'I{s["id"]} {incoming} 0 {s["current_a"]:.12g}')
        else:raise ValueError(f'{s["name"]}: attach a real .SUBCKT model. Efficiency-budget numbers are not converter physics.')
    lines.extend(definitions.values());lines.extend(['.op','.end']);source='\n'.join(lines)+'\n'
    from python.spikes.netlist import parse_netlist
    parse_netlist(source,native_extensions=True,transient_capture='rolling')
    return source
