# SPDX-License-Identifier: Apache-2.0
"""Package an executed geometry loop with its exact inputs and native sources.

No numerical or physical qualification is inferred from successful packaging.
The original prepared project is preserved. GUI verification remains pending.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from python.spike_core.project_package import read_project, write_spike_package
from examples.promo_showcase.colocate_kicad_sources import colocate_tree
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_thermal import validate_thermal_spec


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def validate_capture_inputs(result,request,magnetic,fluid,file_hashes):
    if result.get('contract')!='spike/geometry-propulsion-loop-result/v1' or result.get('status')!='completed':
        raise ValueError('An executed complete geometry loop is required')
    if result.get('production_qualified') is not False or result.get('physical_load_qualified') is not False:
        raise ValueError('This experimental package must retain unqualified status')
    effective=copy.deepcopy(request)
    if 'thermal' in effective:effective['thermal']=validate_thermal_spec(effective['thermal'])
    if result.get('request')!=effective:raise ValueError('Result and exact request differ')
    if result.get('input_file_sha256')!=file_hashes:raise ValueError('Executed input-file identities differ')
    for key,table in (('field_table_sha256',magnetic),('fluid_port_sha256',fluid)):
        if result.get(key)!=canonical_hash(table):raise ValueError('Constitutive source identity differs: '+key)
    steps=result.get('accepted_steps');history=result.get('history')
    if type(steps) is not int or not 1<=steps<=20000 or not isinstance(history,list) or len(history)!=steps+1:
        raise ValueError('Incomplete accepted history')
    final_time=history[-1].get('time_s')
    if history[0].get('time_s')!=0 or type(final_time) not in (int,float) or not math.isclose(final_time,request['transient']['duration_s'],rel_tol=0,abs_tol=1e-12):
        raise ValueError('Accepted history does not span the requested duration')
    # Serialization is a finite-number gate, not a conservation/convergence test.
    json.dumps(result,allow_nan=False)


def validate_native_sources(preparation,magnetic,fluid,asset_directory):
    """Bind retained physics ports to this project's original STEP/STL assets."""
    files=preparation.get('asset_manifest',{}).get('files',{})
    motor=files.get('CIAG_2_28 125_25.step')
    propeller=files.get('CASALINO_D30cm_pitch+5deg.stl')
    valid=lambda value:isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
    if not valid(motor) or not valid(propeller):raise ValueError('Native original motor/propeller identities required')
    evidence=magnetic.get('source_field_evidence')
    if not isinstance(evidence,list) or not evidence or any(not isinstance(row,dict) or row.get('source_sha256')!=motor for row in evidence):
        raise ValueError('Field source differs from the native motor STEP')
    if fluid.get('evidence',{}).get('source_geometry_sha256')!=propeller:
        raise ValueError('Fluid source differs from the native original propeller STL')
    for name,expected in files.items():
        path=Path(asset_directory)/name
        if Path(name).name!=name or not valid(expected) or not path.is_file() or digest(path)!=expected:
            raise ValueError('Native adjacent asset bytes differ: '+name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-project','result','magnetic-table','cfd-table','request','output-directory'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--evidence-root',action='append',type=Path,required=True,
                   help='Retained numerical evidence tree; may be repeated')
    p.add_argument('--reference-audit',type=Path,help='Source-table-bound motor reference comparison')
    p.add_argument('--study-assumptions',type=Path,help='Exact request-file-bound assumptions')
    a=p.parse_args()
    if a.output_directory.exists():raise ValueError('Choose a new package directory')
    paths={'magnetic_table':a.magnetic_table,'cfd_table':a.cfd_table,'request':a.request}
    inputs={key:json.loads(path.read_bytes()) for key,path in paths.items()}
    result=json.loads(a.result.read_bytes())
    validate_capture_inputs(result,inputs['request'],inputs['magnetic_table'],inputs['cfd_table'],
                            {key:digest(path) for key,path in paths.items()})
    notices=[]
    if a.reference_audit:
        audit=json.loads(a.reference_audit.read_bytes())
        if audit.get('contract')!='spike/retained-motor-constant-convention-audit/v1' or audit.get('source_table_sha256')!=digest(a.magnetic_table) or audit.get('physical_qualified') is not False or not isinstance(audit.get('finding'),str):
            raise ValueError('Reference audit differs from the retained field table')
        notices.append(audit['finding'])
    if a.study_assumptions:
        assumptions=json.loads(a.study_assumptions.read_bytes())
        if assumptions.get('request_file_sha256')!=digest(a.request) or assumptions.get('physical_qualified') is not False or not isinstance(assumptions.get('assumptions'),list) or not all(isinstance(x,str) for x in assumptions['assumptions']):
            raise ValueError('Study assumptions differ from the executed request file')
        notices.extend(assumptions['assumptions'])
    native=read_project(a.source_project,include_members=True)
    preparation=native.payload.get('extensions',{}).get('spike.propulsion-real-source-preparation')
    if not preparation or preparation.get('gui_verified') is not False:
        raise ValueError('Expected the retained, GUI-unverified real-source project')
    validate_native_sources(preparation,inputs['magnetic_table'],inputs['cfd_table'],a.source_project.parent/'assets')
    for evidence in a.evidence_root:
        if not evidence.is_dir() or any(x.is_symlink() for x in evidence.rglob('*')):
            raise ValueError('Evidence must be an ordinary retained directory: '+str(evidence))
        if a.output_directory.resolve().is_relative_to(evidence.resolve()):
            raise ValueError('Output cannot be inside an evidence source tree')
    a.output_directory.parent.mkdir(parents=True,exist_ok=True)
    scratch=ROOT/'output/.tmp';scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pod-package-',dir=scratch) as temporary:
        stage=Path(temporary)
        # The native archive retains embedded visual assets and exact ECAD bytes.
        payload=native.payload
        payload.setdefault('analysis',{})['propulsion_pod_three_phase']={
            'contract':'spike/geometry-propulsion-ui-study/v1','request':result['request'],'result':result,
            'inputs':{'magnetic_table':inputs['magnetic_table'],'cfd_table':inputs['cfd_table'],
                'field_table_sha256':result['field_table_sha256'],'fluid_port_sha256':result['fluid_port_sha256']}}
        if notices:payload['analysis']['propulsion_pod_three_phase']['notices']=notices
        preparation.update(state='coupled_result_captured_gui_pending',complete_loop=True,gui_verified=False,
                           numerical_qualification='See retained evidence; packaging does not admit convergence.',
                           physical_load_qualified=False)
        preparation['limitations']=[message for message in preparation.get('limitations',[])
            if message!='Motor/CFD load convergence and real coupled result remain pending.']
        payload.setdefault('project',{})['name']='Restrained OpenMotor / ENOLA coupled capture - GUI verification pending'
        project=stage/'restrained-pod-real-geometry-loop.spike'
        write_spike_package(project,payload,preserved_members=native.members,application_version='source')
        retained=stage/'coupled';retained.mkdir()
        for key,path in {**paths,'result':a.result}.items():shutil.copy2(path,retained/(key+'.json'))
        for name,path in (('motor-reference-audit.json',a.reference_audit),('study-assumptions.json',a.study_assumptions)):
            if path:shutil.copy2(path,retained/name)
        for index,evidence in enumerate(a.evidence_root):
            shutil.copytree(evidence,stage/'evidence'/f'{index:02d}-{evidence.name}')
        for name in ('assets','KiCad'):
            source=a.source_project.parent/name
            if source.is_dir():shutil.copytree(source,stage/name)
        hardware=ROOT/'examples/promo_showcase/propulsion_pod/real_hardware'
        selected={
            'OpenMotor125_25':('CIAG_2_28 125_25_datasheet.pdf','CIAG_2_28 125_25_test_propeller_30x14.csv',
                'LICENSE.txt','UPSTREAM_README.md','source-provenance.json','SHA256SUMS.json'),
            'ENOLA_Casalino30cm':('00_Generalnfo.xlsx','Casalino_SLA_Pitch+5deg_exp_0_90_deg.csv',
                'DATABASE_README.txt','README.txt','LICENSE_CC_BY_SA_4.0.txt',
                'ZENODO_RECORD_20111572.json','source-provenance.json','SHA256SUMS.json')}
        for folder,names in selected.items():
            target=stage/'hardware_reference'/folder;target.mkdir(parents=True)
            for name in names:shutil.copy2(hardware/folder/name,target/name)
        colocate_tree(stage)
        (stage/'README_GUI_VERIFICATION.txt').write_text(
            'Restrained OpenMotor / ENOLA coupled capture\n'
            'Open restrained-pod-real-geometry-loop.spike in the updated SPIKE source build.\n'
            'Open Coupled propulsion benchmark to inspect the separate geometry capture.\n'
            'Replay reads saved states; Run coupled geometry loop reruns fixed C plus retained ports.\n'
            'A rerun does not solve new spatial FEM/CFD fields. Field snapshots are separately retained re-solves.\n'
            'GUI visual verification and physical hardware qualification remain pending.\n'
            'See coupled/ for exact inputs/result and source-bound assumptions/reference audit.\n'
            'See assets/source_inventory.json and adjacent licenses for pinned motor/propeller attribution.\n'
            'See hardware_reference/ for original datasheet/test/reference records and their licenses.\n'
            'See KiCad/ for original available native board/project/schematic/library companions.\n'
            'Evidence directories preserve declared-model numerical studies, including their limitations.\n',encoding='utf-8')
        reopened=read_project(project,include_members=True)
        captured=reopened.payload['analysis']['propulsion_pod_three_phase']['result']
        if canonical_hash(captured)!=canonical_hash(result):raise ValueError('Native result retention failed')
        inventory={x.relative_to(stage).as_posix():digest(x) for x in sorted(stage.rglob('*')) if x.is_file()}
        (stage/'PACKAGE_INVENTORY.json').write_text(json.dumps({'contract':'spike/pod-gui-verification-package/v1',
            'files':inventory,'native_reopen_passed':True,'gui_verified':False,
            'source_project_sha256':digest(a.source_project),'physical_load_qualified':False},indent=2)+'\n')
        shutil.copytree(stage,a.output_directory)
    print(json.dumps({'directory':str(a.output_directory.resolve()),'native_reopen_passed':True,
                      'gui_verified':False,'physical_load_qualified':False}))


if __name__=='__main__':main()
