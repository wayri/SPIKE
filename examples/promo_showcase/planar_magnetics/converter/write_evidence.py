# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json,hashlib,collections
HERE=Path(__file__).parent;ROOT=HERE.parents[3];OUT=ROOT/'output/promo-planar-magnetics-20261023/converter'
def record(p):return {'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
erc=json.loads((OUT/'erc.json').read_text());drc=json.loads((OUT/'drc.json').read_text())
e=[v for s in erc['sheets'] for v in s['violations']]
assert not e and not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']
model=HERE/'models/planar_transformer_assembly.step';export=OUT/'carrier-with-transformer.step'
assert model.read_text().count('MANIFOLD_SOLID_BREP')==225
assert export.read_text().count('MANIFOLD_SOLID_BREP')==226
sources=['python/spikes/native_runner.py','python/spikes/native_abi.py','standalone/spikes_project/studio/python/spikes_studio/document.py','standalone/spikes_project/studio/python/spikes_studio/run_control.py']
files=[record(p) for p in HERE.rglob('*') if p.is_file() and p.name!='source-provenance.json']
evidence={'kicad_version':erc['kicad_version'],'erc_violations':0,'drc_violations':0,'unconnected_items':0,'schematic_parity_issues':0,'all_severities_requested':True,'erc_ignored_checks':erc['ignored_checks'],'drc_ignored_checks':drc['ignored_checks'],'user_added_exclusions':[],'render_inspected':['carrier-schematic.png','carrier-board.png'],'native_model_reference_resolved':True,'native_export_manifold_records':226,'source_model_manifold_records':225,'current_rating':'unqualified','fabrication_ready':False,'production_qualified':False,'native_sources':files,'solver_sources':[record(ROOT/p) for p in sources],'evidence_files':[record(OUT/p) for p in ['erc.json','drc.json','checks.json','routing-attempt.json','carrier-schematic.pdf','carrier-board.svg','carrier-with-transformer.step']]}
(OUT/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
(HERE/'source-provenance.json').write_text(json.dumps({'license':'Apache-2.0, original demonstration geometry and code; no official vendor CAD model bundled','files':files,'solver_sources':evidence['solver_sources'],'model_source':record(ROOT/'output/promo-planar-magnetics-20261023/core/original-planar-module-full.step'),'model_copy':record(model),'unchanged_model_geometry':model.read_bytes()==(ROOT/'output/promo-planar-magnetics-20261023/core/original-planar-module-full.step').read_bytes(),'no_new_numerical_solver':True},indent=2)+'\n')
print(json.dumps({k:evidence[k] for k in ['erc_violations','drc_violations','unconnected_items','schematic_parity_issues','native_export_manifold_records']}))
