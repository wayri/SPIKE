# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json,hashlib
HERE=Path(__file__).parent;ROOT=HERE.parents[3]
def record(p):return {'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
copies=[]
for name in ('current_sensing.cir','current_sensing.spksch'):
    src=ROOT/'examples/promo_showcase/esc/studio'/name
    assert (HERE/name).read_bytes()==src.read_bytes()
    copies.append({'source':record(src),'copy':record(HERE/name),'unchanged':True,'license':'Apache-2.0'})
paths=['python/spikes/native_runner.py','standalone/spikes_project/studio/python/spikes_studio/document.py','standalone/spikes_project/studio/python/spikes_studio/run_control.py','docs/EM_MACHINES.md','examples/spikes/advanced_systems/README.md']
data={'license':'Apache-2.0','copied_firstparty_files':copies,'files':[record(p) for p in HERE.iterdir() if p.is_file() and p.name!='source-provenance.json'],'runtime_and_capability_sources':[record(ROOT/p) for p in paths],'no_thirdparty_code':True,'no_new_physics':True}
(HERE/'source-provenance.json').write_text(json.dumps(data,indent=2)+'\n')
