# SPDX-License-Identifier: Apache-2.0
"""Original restrained-pod geometry plus supplied-loss solid thermal reference."""
from pathlib import Path
import sys,os,ctypes.util,importlib.util,json,hashlib,math
import numpy as np
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from examples.promo_showcase.thermal_flow.build_thermal_flow import mesh
from tests.python.test_assembly_joint_thermal_mesh import runtime
from unittest.mock import patch
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.solvers.execution.coupling.assembly_field_transient import run_assembly_field_transient
from python.spike_core.solvers.execution.coupling.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from python.spike_core.project_package import write_spike_package, read_project
from python.spike_core.service_project_assembly_field import save_assembly_field_study_in_project, read_assembly_field_study_in_project
from tests.python.test_project_assembly_field import _payload
OUT=ROOT/'output/promo-propulsion-pod-20261023/thermal_geometry';OUT.mkdir(parents=True,exist_ok=True)
def write(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def geometry():
 with os.add_dll_directory(str(runtime.DLL.parent)):
  original=ctypes.util.find_library
  with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
   spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
  g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
  try:
   g.option.setNumber('General.Terminal',0);g.model.add('Original pod support')
   boxes=[(-60,-50,0,120,100,6),(-60,-50,6,3,100,84),(57,-50,6,3,100,84),(-57,47,6,114,3,84),(-10,-10,6,20,20,30)]
   parts=[(3,g.model.occ.addBox(*b)) for b in boxes];stand=g.model.occ.fuse(parts[:1],parts[1:])[0];g.model.occ.synchronize();assert len(stand)==1
   standvol=g.model.occ.getMass(*stand[0]);g.write(str(OUT/'original-pod-stand.step'))
   expected=120*100*6+2*3*100*84+114*3*84+20*20*30;assert math.isclose(standvol,expected,rel_tol=1e-12)
   g.clear();g.model.add('Original motor case envelope');motor=g.model.occ.addBox(-20,-20,36,40,40,30);g.model.occ.synchronize();assert math.isclose(g.model.occ.getMass(3,motor),48000,rel_tol=1e-12);g.write(str(OUT/'original-motor-case-envelope.step'))
   g.clear();g.model.add('Original restrained single motor pod assembly');g.model.occ.importShapes(str(OUT/'original-pod-stand.step'));g.model.occ.importShapes(str(OUT/'original-motor-case-envelope.step'));g.model.occ.addCylinder(20,0,51,20,0,0,3);g.model.occ.synchronize();g.write(str(OUT/'original-single-motor-stand-assembly.step'))
   total=sum(g.model.occ.getMass(d,t) for d,t in g.model.getEntities(3));g.clear();g.model.add('STEP reimport');g.model.occ.importShapes(str(OUT/'original-single-motor-stand-assembly.step'));g.model.occ.synchronize();assert len(g.model.getEntities(3))==3;assert math.isclose(sum(g.model.occ.getMass(d,t) for d,t in g.model.getEntities(3)),total,rel_tol=1e-9)
   write('geometry-verification.json',{'status':'passed','units':'mm','closed_solids':3,'stand_volume_mm3':standvol,'stand_analytic_volume_mm3':expected,'motor_envelope_volume_mm3':48000,'shaft_radius_mm':3,'shaft_length_mm':20,'STEP_readback_total_volume_mm3':total,'scope':'Original nominal geometry only, no mechanical load or restraint-strength qualification'})
  finally:g.finalize()

def main():
 geometry();xs=[-60,-57,-20,-10,10,20,57,60];ys=[-50,-47,-20,-10,10,20,47,50]
 stand,sf=mesh(xs,ys,[0,6,36,90],lambda i,j,k:k==0 or i in (0,6) or j==6 or (k==1 and i==3 and j==3));motor,mf=mesh([-20,-10,10,20],[-20,-10,10,20],[36,51,66],lambda i,j,k:True)
 area=400e-6;hcontact=500.;raw={'assembly_id':'original-restrained-pod','name':'Original supplied-loss motor-case and stand thermal','boards':[],'parts':[{'id':oid,'model_id':oid+'-model','name':oid,'part_type':'mechanical','frame':{'frame_id':oid+'-frame'}} for oid in ['stand','motor-case']],'thermal_contacts':[{'id':'mount-interface','endpoint_a':'stand','endpoint_b':'motor-case','contact_area_mm2':400.,'thermal_resistance_k_per_w':1/(area*hcontact)}]}
 r={'contract':'spike/assembly-field-handoff-request/v1','domain':'thermal','assembly':AssemblyIRV1.from_dict(raw).to_dict(),'materials':[{'id':'illustrative-metal','thermal_conductivity_w_mk':150.,'provenance':'Supplied illustrative constant metal conductivity; not characterized motor/stand material'}],'bodies':[]}
 for oid,m,fs,file in [('stand',stand,sf,'original-pod-stand.step'),('motor-case',motor,mf,'original-motor-case-envelope.step')]:r['bodies'].append({'occurrence_id':oid,'reference_id':oid+'-model','source_sha256':sha(OUT/file),'mesh':m,'boundary_faces':fs,'material_map':{'bulk':'illustrative-metal'}})
 p={'contract':'spike/assembly-field-thermal-problem/v1','boundaries':[],'contacts':[],'heat_sources':[]};pairs=[];used=set()
 for f in sf:
  coords={tuple(stand['vertices'][v]) for v in f['vertices']}
  if all(v[2]==36 and -10<=v[0]<=10 and -10<=v[1]<=10 for v in coords):
   other=next(ff for ff in mf if {tuple(motor['vertices'][v]) for v in ff['vertices']}==coords);pairs.append({'left':{'occurrence_id':'stand','face_id':f['id']},'right':{'occurrence_id':'motor-case','face_id':other['id']}});used.update([('stand',f['id']),('motor-case',other['id'])])
 assert len(pairs)==2;p['contacts']=[{'contact_id':'mount-interface','face_pairs':pairs,'thermal_contact_conductance_w_m2k':hcontact}]
 for oid,fs in [('stand',sf),('motor-case',mf)]:
  for f in fs:
   if (oid,f['id']) not in used:p['boundaries'].append({'face':{'occurrence_id':oid,'face_id':f['id']},'type':'convection','heat_transfer_coefficient_w_m2k':10.,'ambient_temperature_k':298.15})
 watts=5.;p['heat_sources']=[{'occurrence_id':'motor-case','cell_id':c['id'],'heat_source_w_m3':watts/(48000e-9)} for c in motor['cells']]
 t={'contract':'spike/assembly-tetra-transient-settings/v1','duration_s':120.,'time_step_s':2.,'output_interval_s':5.,'initial_temperature_k':298.15,'material_heat_capacity':[{'material_id':'illustrative-metal','density_kg_m3':2700.,'specific_heat_j_kgk':900.}]}
 result=run_assembly_field_transient(r,p,t);record=export_assembly_field_study(r,p,result,transient_settings=t);import_assembly_field_study(record)
 for suffix,v in [('request',r),('problem',p),('transient',t),('result',result),('fieldstudy',record)]:write('pod-supplied-5w.'+suffix+'.json',v)
 payload=_payload(r);payload['project']['name']='Original restrained pod: supplied5W thermal only';payload['models']['models']=[];artifacts={}
 for oid,file in [('stand','original-pod-stand.step'),('motor-case','original-motor-case-envelope.step')]:
  payload['models']['models'].append({'id':oid+'-model','name':oid,'model_type':'step','uri':'package:models/artifacts/'+file,'digest':sha(OUT/file),'transform':[],'extensions':{}});artifacts[file]=(OUT/file).read_bytes()
 path=OUT/'pod-supplied-5w.spike';manifest=write_spike_package(path,payload,model_artifacts=artifacts);save_assembly_field_study_in_project({'project_path':str(path),'expected_manifest_payload_sha256':manifest['manifest_payload_sha256'],'record':record},application_version='pod-reference');opened=read_project(path);loaded=read_assembly_field_study_in_project({'project_path':str(path),'expected_manifest_payload_sha256':opened.manifest['manifest_payload_sha256']},application_version='pod-reference');assert loaded['state']=='current' and loaded['saved_result_present']
 # Independent tetra-volume/capacity integration, separate from solver balance assembly.
 temp=np.asarray(result['field_result']['node_temperatures_k']);storage=0.;offset=0;volumes={}
 for b in r['bodies']:
  xyz=np.asarray(b['mesh']['vertices'])*.001;vol=0.
  for c in b['mesh']['cells']:
   ids=c['vertices'];v=abs(np.linalg.det((xyz[ids[1:]]-xyz[ids[0]]).T))/6;vol+=v;storage+=v*2700*900*(temp[np.asarray(ids)+offset].mean()-298.15)
  volumes[b['occurrence_id']]=vol;offset+=len(xyz)
 energy=result['field_result']['energy_balance'];error=abs(600-energy['convection_outward_j']-storage);assert error<1e-6;assert abs(energy['imbalance_j'])<=energy['acceptance_tolerance_j'];assert len(result['field_result']['frames'])==25
 write('verification.json',{'status':'passed','production_qualified':False,'native_readback':'current with saved result','physical_frames':25,'supplied_loss_w':watts,'duration_s':120,'mesh_volumes_m3':volumes,'independent_stored_energy_j':storage,'input_energy_j':600,'reported_convection_energy_j':energy['convection_outward_j'],'independent_energy_error_j':error,'temperatures_k':result['occurrence_temperatures'],'source_sha256':sha(Path(__file__)),'scope':'Supplied-loss solid conduction only, not motor/controller/rotor/CFD/thrust coupling'});print(json.dumps(result['occurrence_temperatures']))
if __name__=='__main__':main()
