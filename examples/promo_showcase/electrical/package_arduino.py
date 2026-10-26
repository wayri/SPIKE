# SPDX-License-Identifier: Apache-2.0
"""Copy licensed cached Arduino CAD and rerun retained native PI/SI studies."""
from pathlib import Path
import sys,json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.project_package import read_project
from python.spike_core.project_state_artifacts import hydrate_result_state
from python.spike_core.solvers.circuits.models.multiboard_circuit import run_multiboard_circuit
from scripts.build_arduino_shield_acceptance import _persist_study
from python.spike_core.multiboard_study import validate_study_result, physical_assembly
SRC=ROOT/'build/curated-multiboard-20261005/arduino'
OUT=ROOT/'output/promo-showcase-20261023/electrical/arduino-cc-by-sa'
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
project=OUT/'arduino-r4-relay-shield.spike'
shutil.copy2(SRC/project.name,project)
for name in ('source-provenance.json',):shutil.copy2(SRC/name,OUT/name)
provenance=json.loads((SRC/'source-provenance.json').read_text())
for name in ('ABX00080-cad-files.zip','A000110-cad-files.zip'):
    key='uno' if name.startswith('ABX') else 'shield'
    assert sha(SRC/'sources'/name)==provenance[key]['archive_sha256']
    shutil.copy2(SRC/'sources'/name,OUT/name)
for sub,name in (('uno/ABX00080-cad-files','UNO-License.txt'),('shield/A000110-cad-files','SHIELD-License.txt')):
    shutil.copy2(SRC/'sources'/sub/'License.txt',OUT/name)
opened=read_project(project)
hydrated=hydrate_result_state(opened.payload,project,opened.manifest['manifest_payload_sha256'])
studies=hydrated['assembly_ir']['extensions']['spike.multiboard-studies']
results={};checks=[]
for domain in ('pi','si'):
    q=dict(studies[domain]['request']);q['assembly']=physical_assembly(hydrated['assembly_ir'])
    r=run_multiboard_circuit(q)
    assert r['status']=='completed' and not r['production_qualified']
    assert r['native_result']['diagnostics']['relative_residual_max']<1e-10
    save(domain+'-request.json',q);save(domain+'-result.json',r)
    _persist_study(project,domain,q,r);results[domain]=r
reopened=read_project(project)
hydrated=hydrate_result_state(reopened.payload,project,reopened.manifest['manifest_payload_sha256'])
for domain in ('pi','si'):
    study=hydrated['assembly_ir']['extensions']['spike.multiboard-studies'][domain]
    validate_study_result(hydrated['assembly_ir'],domain,study['request'],study['result'])
    assert study['result']==results[domain]
    checks.append({'domain':domain,'completed':True,'native_relative_residual':results[domain]['native_result']['diagnostics']['relative_residual_max'],'bound_result_readback':'passed'})
save('verification.json',{'checks':checks,'source_project_sha256':sha(SRC/project.name),'updated_project_sha256':sha(project),'fresh_domains':['pi','si'],'unchanged_older_studies':['thermal'],'production_qualified':False,'license':'Arduino CAD and derivatives CC BY-SA 4.0; original SPIKE simulation code Apache-2.0','source_files':[{'file':p.name,'sha256':sha(p)} for p in OUT.iterdir() if p.is_file() and p.suffix in ('.zip','.txt')]})
print(json.dumps(checks,indent=2))
