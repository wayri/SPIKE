"""Preserve user-supplied vendor text and provenance; never auto-approve code."""
import hashlib
from pathlib import Path
import re

SOURCES=[
 {'manufacturer':'Texas Instruments','part':'LM358','url':'https://www.ti.com/product/LM358','kind':'Manufacturer product / model download page'},
 {'manufacturer':'Infineon','part':'2N7002','url':'https://www.infineon.com/part/2N7002','kind':'Manufacturer product / datasheet page'},
 {'manufacturer':'Infineon','part':None,'url':'https://www.infineon.com/de/design-resources/simulation-modeling/power-mosfet-simulation-models','kind':'Manufacturer model resource'},
 {'manufacturer':'Analog Devices','part':None,'url':'https://www.analog.com/en/resources/technical-articles/ltspice-how-to-import-third-party-models.html','kind':'Manufacturer model-import guidance'},
]


def intake(path):
    path=Path(path)
    if path.stat().st_size>2*1024*1024:raise ValueError('Model review input exceeds 2 MiB')
    raw=path.read_bytes();text=raw.decode('utf-8-sig')
    if '\x00' in text:raise ValueError('Binary / encrypted model files are not accepted as plain SPICE')
    models=[{'name':m[1],'type':m[2]} for m in re.finditer(r'(?im)^\s*\.model\s+(\S+)\s+(\w+)',text)]
    subcircuits=[{'name':m[1],'declared_header':m[2].strip()} for m in re.finditer(r'(?im)^\s*\.subckt\s+(\S+)([^\r\n]*)',text)]
    if not models and not subcircuits:raise ValueError('No .model or .subckt declarations found')
    dependencies=re.findall(r'(?im)^\s*\.(?:include|inc|lib)\s+([^\r\n]+)',text)
    return {'contract':'spikes/vendor-model-review/v1','filename':path.name,'content_sha256':hashlib.sha256(raw).hexdigest(),'original_source':text,
        'models':models,'subcircuits':subcircuits,'dependencies_not_loaded':dependencies,'execution':'not_approved','compatibility':'not_qualified',
        'redistribution':'not_reviewed; local user-supplied model only','datasheet_fit':'not_performed','manufacturer_sources':SOURCES,
        'next_steps':['Record the exact manufacturer URL, model version and applicable license.','Review pins, dependencies and unsupported syntax.','Qualify DC/transient behavior against source data before enabling circuit execution.']}
