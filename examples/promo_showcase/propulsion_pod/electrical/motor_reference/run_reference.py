# SPDX-License-Identifier: Apache-2.0
"""Execute and retain the existing original prescribed-current planar fixture."""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[5];sys.path.insert(0,str(ROOT))
from python.spike_core import magnetic_fem
from python.spike_core.magnetic_machine_study import run_magnetic_machine
from python.spike_core.contracts import SpiDeR
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.project_package import write_spike_package,read_project
from python.spike_core.service_project import frontend_project_payload
HERE=Path(__file__).parent;OUT=ROOT/'output/promo-propulsion-pod-20261023/electrical/motor_reference';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode(v):
    if hasattr(v,'tolist'):return v.tolist()
    if hasattr(v,'item'):return v.item()
    raise TypeError(type(v).__name__)
def save(name,v):(OUT/name).write_text(json.dumps(v,indent=2,default=encode,allow_nan=False)+'\n')
source=ROOT/'examples/em_machines/planar_pm_fem.json'
assert (HERE/'request.json').read_bytes()==source.read_bytes()
request=json.loads((HERE/'request.json').read_text())
frames=[];original=magnetic_fem.solve_magnetostatic
def observed_solve(**kwargs):
    # Observation-only wrapper: invoke established solver exactly once and return
    # its unmodified result; retain every actual accepted-position field solve.
    field=original(**kwargs)
    frames.append({'field_request':kwargs,'field_result':field})
    return field
magnetic_fem.solve_magnetostatic=observed_solve
try:result=run_magnetic_machine(request)
finally:magnetic_fem.solve_magnetostatic=original
assert result['model_status']=='experimental' and result['production_qualified'] is False
history=result['histories'];assert len(frames)==len(history['time_s'])==3
for i,frame in enumerate(frames):
    assert frame['field_result']['convergence']['converged']
    frame.update(time_s=history['time_s'][i],position_rad=history['position'][i],angular_velocity_rad_s=history['velocity'][i],torque_n_m=history['force_n_or_torque_nm'][i])
assert frames[-1]['field_result']['element_b_t']==result['field']['element_b_t']
save('request.json',request);save('result.json',result)
save('actual-field-history.json',{'scope':'actual prescribed-current quasi-static field solves at accepted motion positions; independent synthetic planar reference','frames':frames})
baseline=json.loads((ROOT/'examples/em_machines/motor.json').read_text())
study={'request':baseline,'result':None,'fieldStudy':{'request':request,'result':result}}
design=SpiDeRV2.from_v1(SpiDeR(design_id='pod-separate-planar-reference',name='Separate original planar motor reference',source_format='generated',source_path='')).to_dict()
project={'id':'pod-separate-planar-reference','name':'Separate prescribed-current planar motor reference'}
legacy={'format':'spike-project-package/v2','contract':'spike/project/v2','project':project,'design':SpiDeRV2.from_dict(design).to_v1().to_dict(),'analysis':{},'emi':{'setup':{'machine_study':study}}}
payload={'project':project,'design_ir':design,'extensions':{'legacy':legacy},'audit':[{'event':'separate_original_field_reference','request_sha256':result['request_sha256'],'linked_to_physical_pod':False}]}
path=HERE/'prescribed-current-planar-reference.spike';manifest=write_spike_package(path,payload)
opened=read_project(path);saved=frontend_project_payload(opened.payload)['emi']['setup']['machine_study']['fieldStudy']
assert saved['request']==request
# Native JSON transport canonicalizes tuples/NumPy values to JSON arrays/scalars.
assert saved['result']==json.loads(json.dumps(result,default=encode,allow_nan=False))
checks={'executed':True,'actual_field_solve_count':len(frames),'converged_fields':True,'final_history_matches_native_result':True,'native_package_readback':'passed','native_frontend_projection':'passed','request_sha256':result['request_sha256'],'manifest_payload_sha256':manifest['manifest_payload_sha256'],'time_s':history['time_s'],'position_rad':history['position'],'torque_n_m':history['force_n_or_torque_nm'],'nodes_per_frame':[len(f['field_request']['nodes_m']) for f in frames],'triangles_per_frame':[len(f['field_request']['triangles']) for f in frames],'production_qualified':False,'physical_pod_link':False,'controller_link':False,'ui_execution':'not_performed','field_playback_ui':'not_added; existing workbench displays final field plus motion histories'}
save('verification.json',checks)
sources=[source,ROOT/'python/spike_core/magnetic_machine_study.py',ROOT/'python/spike_core/magnetic_fem.py',ROOT/'python/spike_core/machine_geometry.py',ROOT/'python/spike_core/project_package.py']
(HERE/'source-provenance.json').write_text(json.dumps({'license':'Apache-2.0, original firstparty fixture and example glue','sources':[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':sha(p)} for p in sources],'request_exact_source_copy':True,'generator_sha256':sha(Path(__file__)),'native_project_sha256':sha(path),'no_new_physics':True,'field_history_capture':'observation wrapper retains actual unchanged results from existing solver calls'},indent=2)+'\n')
print(json.dumps(checks,indent=2))
