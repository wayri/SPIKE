# SPDX-License-Identifier: Apache-2.0
"""Execute the existing registered PEEC extraction on the original spiral PCB."""
from pathlib import Path
import hashlib,json,sys,tempfile
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.script_runtime import run_python_script
from python.spike_core.service_project_handlers import handle_project_request
HERE=Path(__file__).parent;OUT=ROOT/'output/promo-planar-magnetics-20261023/aircore'
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'.tmp').mkdir(exist_ok=True);tempfile.tempdir=str(OUT/'.tmp')
    source=HERE/'windings/aircore_inductor/aircore_inductor.kicad_pcb'
    design=json.loads(json.dumps(import_kicad_design(str(source)).to_dict()))
    pads=design['pads'];assert len(pads)==2,pads
    terminals=[{'id':'winding-'+str(i),'net':'AIRCORE_WINDING','position_mm':p.get('center_mm',p.get('position_mm',p.get('position'))),'layer':'F.Cu'} for i,p in enumerate(pads)]
    # Native import uses center for legacy pad coordinates.
    for t,p in zip(terminals,pads):t['position_mm']=t['position_mm'] or p.get('at')
    # The spiral enters pin 1 on F.Cu and exits pin 2 on B.Cu. These
    # explicit surface contacts avoid claiming a qualified through-pin port.
    terminals[1]['layer']='B.Cu'
    assert all(t['position_mm'] is not None for t in terminals)
    spec={'mode':'ac','solver_id':'spike.peec_2_5d','formulation':'peec_2_5d','net_names':['AIRCORE_WINDING'],
      'sources':[terminals[0]],'loads':[terminals[1]],'frequency_start_hz':1000,'frequency_stop_hz':100000,'frequency_points':5,
      'mesh':{'target_size_mm':3.,'max_preview_cells':1200},'options':{'conductor_models':{'skin_effect':True,'surface_roughness_model':'none'}}}
    code='''# SPDX-License-Identifier: Apache-2.0
import spike,json
SPEC='''+repr(spec)+'''
assert spike.design and spike.design['design_id']=='''+repr(design['design_id'])+''', "Open the original aircore_inductor board"
result=spike.analysis.run('run_analysis',{'design':spike.design,'spec':SPEC})
print('RESULT_JSON='+json.dumps(result))
if result['status']=='completed':
    spike.publish_table('Actual air-core PEEC extraction',['Quantity','Value'],
      [[key,json.dumps(value)] for key,value in result['summary'].items()],
      provenance='Registered native PEEC, explicit F.Cu entry and B.Cu exit; partial inductance, no ferrite core')
'''
    (HERE/'02_aircore_peec_gui.py').write_text(code,encoding='utf-8')
    execution=run_python_script({'code':code,'design':design,'timeout_seconds':180})
    save(OUT/'python-workspace-execution.json',execution);save(OUT/'spec.json',spec)
    assert execution['status']=='completed',execution.get('stderr')
    result=json.loads(next(x.split('=',1)[1] for x in execution['stdout'].splitlines() if x.startswith('RESULT_JSON=')))
    save(OUT/'result.json',result)
    snapshot={'format':'spike-project-package/v2','project':{'name':'pcb-aircore-inductor.spike'},
      'design':{'source_file':source.name,'source_format':'kicad_pcb','source_board':source.read_text(encoding='utf-8')},
      'analysis':{'mode':'AC Impedance','pi_setup':{},'view_mode':'3D','show_models':False,'solver_id':'spike.peec_2_5d',
       'latest_result':None},'studies':[]}
    r=handle_project_request('write_project_package',{'path':str(OUT/'pcb-aircore-inductor.spike'),'snapshot':snapshot,'generate_geometry_tables':False},request_id='aircore',application_version='source')
    assert r and r['ok'],r
    save(OUT/'verification.json',{'status':'passed' if result['status']=='completed' else 'blocked',
      'registered_python_execution':execution['status'],'solver_status':result['status'],'issues':result.get('issues',[]),
      'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'summary':result.get('summary'),
      'core_included':False,'production_qualified':False})
    print(json.dumps({'solver_status':result['status'],'summary':result.get('summary'),'issues':result.get('issues')}))
if __name__=='__main__':main()
