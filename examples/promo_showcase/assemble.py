# SPDX-License-Identifier: Apache-2.0
"""Verify generated examples and assemble the attribution-preserving promo pack."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from python.spike_core.project_package import read_project
from python.spike_core.service_project import frontend_project_payload
from python.spike_core.project_state_artifacts import hydrate_result_state
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
BASE=ROOT/'output/promo-showcase-20261023';READY=BASE/'READY_TO_OPEN';HERE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def copytree(source,target):
    shutil.copytree(source,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.tmp'))
def copyfile(source,target):target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)

def main():
    READY.mkdir(parents=True,exist_ok=True)
    copytree(BASE/'boards',READY/'01-pcb-temperature')
    copytree(BASE/'thermal_flow',READY/'02-case-heatsink')
    copytree(BASE/'electrical/arduino-cc-by-sa',READY/'03-pi-si-arduino-cc-by-sa')
    copytree(HERE/'electrical/studio',READY/'04-circuit-and-controller/studio')
    copytree(HERE/'electrical/magnetics',READY/'05-em-machines')
    copytree(BASE/'field-imports',READY/'06-main-viewport-fields')
    for name in ('README.md','LICENSE','NOTICE','source-provenance.json'):
        copyfile(HERE/'electrical'/name,READY/'04-circuit-and-controller'/name)
        if name!='README.md':copyfile(HERE/'electrical'/name,READY/'05-em-machines'/name)
    copyfile(HERE/'boards/README.md',READY/'01-pcb-temperature/README.md')
    copyfile(HERE/'START_HERE.md',READY/'START_HERE.md')
    for name in ('LICENSE','NOTICE','THIRD_PARTY_NOTICES.md'):
        copyfile(ROOT/name,READY/'LICENSES'/name)
    copyfile(ROOT/'docs/DEMO_BOARD_PROVENANCE.md',READY/'LICENSES/DEMO_BOARD_PROVENANCE.md')
    for p in (BASE/'electrical').glob('*.json'):copyfile(p,READY/'EVIDENCE/electrical'/p.name)
    docs=['NUMERICAL_METHOD_EVIDENCE.md','ASSEMBLY_THERMAL_TRANSIENT.md','THERMAL_USER_GUIDE.md','MAGNETIC_MACHINE_STUDIES.md','MAGNETIC_THERMAL.md','EM_MACHINES.md','NATIVE_CFD.md','INTERNAL_AIRFLOW.md']
    sources=['python/spike_core/solvers/thermal_fluid/heat/board_thermal.py','python/spike_core/solvers/thermal_fluid/heat/layered_board_thermal.py','python/spike_core/solvers/execution/coupling/assembly_field_transient.py','python/spike_core/solvers/thermal_fluid/heat/assembly_tetra_transient.py','python/spike_core/solvers/electromagnetics/machines/magnetic_machine_study.py','python/spike_core/solvers/electromagnetics/machines/magnetic_thermal.py','python/spike_core/solvers/thermal_fluid/flow/native_airflow.py','python/spike_core/solvers/thermal_fluid/flow/laminar_channel_cht.py']
    reviewed=[]
    for p in [ROOT/'docs'/name for name in docs]+[ROOT/name for name in sources]:
        if not p.is_file():raise RuntimeError(f'Missing referenced evidence source: {p}')
        reviewed.append({'source':p.relative_to(ROOT).as_posix(),'sha256':sha(p)})
        if p.suffix=='.md':copyfile(p,READY/'EVIDENCE/method-records'/p.name)
    checks=[]
    for p in sorted(READY.rglob('*.spike')):
        opened=read_project(p,include_members=False)
        hydrated=hydrate_result_state(opened.payload,p,opened.manifest['manifest_payload_sha256'])
        front=frontend_project_payload(hydrated)
        assert isinstance(front.get('project'),dict) and isinstance(front.get('design'),dict)
        record={'project':p.relative_to(READY).as_posix(),'manifest_payload_sha256':opened.manifest['manifest_payload_sha256'],'native_readback':'passed'}
        if p.name.startswith('0') and 'ebrake' in p.name:
            scenario=front['thermal']['scenario'];r=scenario['board_thermal_result'];frames=r['transient']
            assert r['status']=='completed' and len(frames)==16
            times=[f['time_s'] for f in frames];assert times[0]==0 and times[-1]==600 and all(b>a for a,b in zip(times,times[1:]))
            assert abs(r['summary']['energy_balance_error_w'])<1e-8
            assert r['summary']['max_transient_energy_balance_error_w']<1e-8
            assert front['design']['source_board']==(ROOT/'app/public/demo/ebrake1.kicad_pcb').read_text(encoding='utf-8')
            record.update(saved_frames=len(frames),steady_energy_error_w=r['summary']['energy_balance_error_w'],maximum_step_energy_error_w=r['summary']['max_transient_energy_balance_error_w'])
        checks.append(record)
    assert len(checks)==10,len(checks)
    assert read(BASE/'field-imports/verification.json')['status']=='passed'
    assert read(BASE/'thermal_flow/independent-checks.json')['status']=='passed'
    assert read(BASE/'thermal_flow/verification.json')['status']=='passed'
    assert all(c['passed'] for c in read(BASE/'electrical/verification.json')['checks'])
    assert all(c['bound_result_readback']=='passed' for c in read(BASE/'electrical/arduino-cc-by-sa/verification.json')['checks'])
    (READY/'EVIDENCE/integration-verification.json').write_text(json.dumps({'status':'passed','native_projects':checks,'current_method_source_hashes':reviewed,'desktop_interaction':'not_performed','no_new_physics_implementation':True,'production_qualified':False},indent=2)+'\n')
    colocate_tree(READY)
    files=[p for p in sorted(READY.rglob('*')) if p.is_file() and p.name!='FILE_MANIFEST.json']
    manifest={'date':'2026-10-23','native_spike_projects':len(checks),'studio_projects':len(list(READY.rglob('*.spksch'))),'files':[{'path':p.relative_to(READY).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]}
    m=READY/'FILE_MANIFEST.json';m.write_text(json.dumps(manifest,indent=2)+'\n');files.append(m)
    archive=BASE/'SPIKE-promo-projects-20261023.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(READY).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for file in manifest['files']:assert hashlib.sha256(z.read(file['path'])).hexdigest()==file['sha256']
    print(json.dumps({'archive':str(archive),'archive_bytes':archive.stat().st_size,'native_projects':len(checks),'studio_projects':manifest['studio_projects'],'files':len(files),'integration_checks':'passed','archive_integrity':'passed'},indent=2))

if __name__=='__main__':main()
