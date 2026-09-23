"""Preserve user-supplied vendor text and provenance; never auto-approve code."""
import hashlib
from pathlib import Path
import re
from collections import Counter

SOURCES=[
 {'manufacturer':'Texas Instruments','part':'LM358','url':'https://www.ti.com/product/LM358','kind':'Manufacturer product / model download page'},
 {'manufacturer':'Infineon','part':'2N7002','url':'https://www.infineon.com/part/2N7002','kind':'Manufacturer product / datasheet page'},
 {'manufacturer':'Infineon','part':None,'url':'https://www.infineon.com/de/design-resources/simulation-modeling/power-mosfet-simulation-models','kind':'Manufacturer model resource'},
 {'manufacturer':'Analog Devices','part':None,'url':'https://www.analog.com/en/resources/technical-articles/ltspice-how-to-import-third-party-models.html','kind':'Manufacturer model-import guidance'},
]


def inspect_text(text, filename='pasted-model.lib'):
    """Static review only: never follow includes or evaluate embedded expressions."""
    raw=text.encode('utf-8')
    if len(raw)>2*1024*1024:raise ValueError('Model review input exceeds 2 MiB')
    if '\x00' in text:raise ValueError('Binary / encrypted model files are not accepted as plain SPICE')
    lines=[]
    for number,line in enumerate(text.splitlines(),1):
        stripped=line.strip()
        if not stripped or stripped.startswith('*'):continue
        if stripped.startswith('+') and lines:lines[-1][1]+=' '+stripped[1:]
        else:lines.append([number,stripped])
    models=[];subcircuits=[];elements=Counter();features=set();dependencies=[];calls=[]
    for number,line in lines:
        fields=line.split();head=fields[0].lower()
        if head=='.model' and len(fields)>=3:
            models.append({'name':fields[1],'type':re.split(r'[ (]',fields[2])[0],'line':number})
        elif head=='.subckt' and len(fields)>=3:
            pins=[]
            for field in fields[2:]:
                if '=' in field or field.lower().startswith('params:'):break
                pins.append(field)
            subcircuits.append({'name':fields[1],'declared_header':' '.join(fields[2:]),'pins':pins,'line':number})
        elif head in ('.include','.inc','.lib'):dependencies.append(' '.join(fields[1:]))
        elif not head.startswith('.'):
            elements[head[0].upper()]+=1
            if head.startswith('x'):
                plain=[f for f in fields[1:] if '=' not in f and not f.lower().startswith('params:')]
                if plain:calls.append(plain[-1])
        for token,pattern in [('behavioral VALUE',r'\bVALUE\s*='),('TABLE',r'\bTABLE\b'),('parameters',r'^\.param\b'),('VSWITCH',r'\bVSWITCH\b'),('noise parameters',r'\b(?:KF|AF)\s*='),('compiled/encrypted content',r'\b(?:encrypt|protect|dll|osdi)\b')]:
            if re.search(pattern,line,re.I):features.add(token)
    if not models and not subcircuits:raise ValueError('No .model or .subckt declarations found')
    declared={s['name'].lower() for s in subcircuits}
    return {'contract':'spikes/vendor-model-review/v1','filename':filename,'content_sha256':hashlib.sha256(raw).hexdigest(),'original_source':text,
        'models':models,'subcircuits':subcircuits,'dependencies_not_loaded':dependencies,
        'inventory':{'element_prefix_counts':dict(sorted(elements.items())),'features_requiring_review':sorted(features),'unresolved_subcircuits':sorted({c for c in calls if c.lower() not in declared})},
        'execution':'not_approved','compatibility':'not_qualified','redistribution':'not_reviewed; local user-supplied model only','datasheet_fit':'not_performed',
        'next_steps':['Verify model pin order against the exact package datasheet.','Review dependencies, manufacturer provenance and license.','Run DC, AC, transient and limit tests before execution approval.']}


def store_review(document,report,manufacturer,part_number,source_url):
    """Persist a content-addressed review with project undo, without enabling it."""
    from copy import deepcopy
    from urllib.parse import urlparse
    if not manufacturer.strip() or not part_number.strip():raise ValueError('Manufacturer and exact part number are required')
    parsed=urlparse(source_url)
    if parsed.scheme!='https' or not parsed.netloc:raise ValueError('Use the HTTPS manufacturer source URL')
    clean=inspect_text(report['original_source'],report.get('filename','model.lib'))
    clean['provenance']={'manufacturer':manufacturer.strip(),'part_number':part_number.strip(),'source_url':source_url}
    key=clean['content_sha256']
    def mutate(data):data['metadata'].setdefault('manufacturer_models',{})[key]=deepcopy(clean)
    document.commit(mutate)
    return key


def intake(path):
    path=Path(path)
    if path.stat().st_size>2*1024*1024:raise ValueError('Model review input exceeds 2 MiB')
    raw=path.read_bytes();text=raw.decode('utf-8-sig')
    if '\x00' in text:raise ValueError('Binary / encrypted model files are not accepted as plain SPICE')
    report=inspect_text(text,path.name)
    report['content_sha256']=hashlib.sha256(raw).hexdigest()
    return report
