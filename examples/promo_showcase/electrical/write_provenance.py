# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
def record(p):return {'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
copied=[]
for p in (HERE/'studio').iterdir():
    source=ROOT/'examples/spikes'/('studio_tutorials' if p.name[:2] in ('02','03') else 'advanced_systems')/p.name
    assert p.read_bytes()==source.read_bytes()
    copied.append({'copied':record(p),'source':record(source),'license':'Apache-2.0','modified':False})
for p in (HERE/'magnetics').glob('*.json'):
    source=ROOT/'examples/em_machines'/('electromagnet.json' if p.stem=='electromagnet-air' else p.name)
    copied.append({'copied':record(p),'source':record(source),'license':'Apache-2.0','modified':p.stem=='electromagnet-air','change':'relative permeability set to 1 for supplied linear reluctance comparison' if p.stem=='electromagnet-air' else ''})
solver_paths=['python/spike_core/em_machines.py','python/spike_core/magnetic_machine_study.py','python/spike_core/magnetic_fem.py','python/spike_core/magnetic_thermal.py','python/spike_core/machine_geometry.py','python/spike_core/multiboard_circuit.py','python/spike_core/multiboard_study.py','scripts/build_arduino_shield_acceptance.py']
data={'license':'Apache-2.0 for original firstparty contents; Arduino CAD output separately CC BY-SA 4.0','copied_examples':copied,'solver_sources':[record(ROOT/p) for p in solver_paths],'pack_files':[record(p) for p in HERE.rglob('*') if p.is_file() and p.name!='source-provenance.json'],'no_ui_execution_claimed':True,'no_new_physics':True}
(HERE/'source-provenance.json').write_text(json.dumps(data,indent=2)+'\n')
