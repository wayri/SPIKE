# SPDX-License-Identifier: Apache-2.0
"""Explicit supplied core heating only; no converter/core-loss constitutive model."""
from pathlib import Path
import sys,json,copy,hashlib,itertools,math
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from examples.promo_showcase.thermal_flow.build_thermal_flow import mesh
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.multiboard_identity import canonical_json_digest as digest
from python.spike_core.assembly_field_transient import run_assembly_field_transient
from python.spike_core.assembly_field_study import export_assembly_field_study,import_assembly_field_study
from python.spike_core.project_package import write_spike_package,read_project
from python.spike_core.service_project_assembly_field import save_assembly_field_study_in_project,read_assembly_field_study_in_project
from tests.python.test_project_assembly_field import _payload
OUT=ROOT/'output/promo-planar-magnetics-20261023/core'
def write(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def main():
 xs=[-15.875,-12.7,-3.175,3.175,12.7,15.875];ys=[-10.175,0,10.175]
 upper,uf=mesh(xs,ys,[0,3.2,6.35],lambda i,j,k:k==1 or i in (0,2,4));lower,lf=mesh(xs,ys,[-6.35,-3.2,0],lambda i,j,k:k==0 or i in (0,2,4))
 area=(3.175*2+6.35)*20.35*1e-6;h=10000.;step=(OUT/'original-nominal-elp32-core-pair.step').read_bytes()
 raw={'assembly_id':'original-core-only-thermal','name':'Original core-only supplied heating','boards':[],'parts':[{'id':oid,'model_id':'original-case','name':oid,'part_type':'magnetic_core','frame':{'frame_id':oid+'-frame'}} for oid in ['upper','lower']],'thermal_contacts':[{'id':'core-mating','endpoint_a':'upper','endpoint_b':'lower','contact_area_mm2':area*1e6,'thermal_resistance_k_per_w':1/(h*area)}]}
 r={'contract':'spike/assembly-field-handoff-request/v1','domain':'thermal','assembly':AssemblyIRV1.from_dict(raw).to_dict(),'materials':[{'id':'generic-ferrite-estimate','thermal_conductivity_w_mk':5.5,'provenance':'Selected generic TDK ferrite estimate; not N97-specific thermal data'}],'bodies':[]}
 for oid,m,fs in [('upper',upper,uf),('lower',lower,lf)]:r['bodies'].append({'occurrence_id':oid,'reference_id':'original-case','source_sha256':hashlib.sha256(step).hexdigest(),'mesh':m,'boundary_faces':fs,'material_map':{'bulk':'generic-ferrite-estimate'}})
 p={'contract':'spike/assembly-field-thermal-problem/v1','boundaries':[],'contacts':[],'heat_sources':[]};pairs=[];used=set()
 for f in uf:
  coords={tuple(upper['vertices'][v]) for v in f['vertices']}
  if all(v[2]==0 for v in coords):
   other=next(ff for ff in lf if {tuple(lower['vertices'][v]) for v in ff['vertices']}==coords);pairs.append({'left':{'occurrence_id':'upper','face_id':f['id']},'right':{'occurrence_id':'lower','face_id':other['id']}});used.update([('upper',f['id']),('lower',other['id'])])
 p['contacts']=[{'contact_id':'core-mating','face_pairs':pairs,'thermal_contact_conductance_w_m2k':h}]
 for oid,fs in [('upper',uf),('lower',lf)]:
  for f in fs:
   if (oid,f['id']) not in used:p['boundaries'].append({'face':{'occurrence_id':oid,'face_id':f['id']},'type':'convection','heat_transfer_coefficient_w_m2k':10.,'ambient_temperature_k':298.15})
 t={'contract':'spike/assembly-tetra-transient-settings/v1','duration_s':120.,'time_step_s':2.,'output_interval_s':5.,'initial_temperature_k':298.15,'material_heat_capacity':[{'material_id':'generic-ferrite-estimate','density_kg_m3':4850.,'specific_heat_j_kgk':700.}]}
 totalvol=2*(31.75*20.35*6.35-2*9.525*20.35*3.2)*1e-9;rows=[]
 for watts,label in [(1.,'core-supplied-1w'),(2.6,'core-reference-supplied-2p6w')]:
  problem=copy.deepcopy(p);problem['heat_sources']=[{'occurrence_id':b['occurrence_id'],'cell_id':c['id'],'heat_source_w_m3':watts/totalvol} for b in r['bodies'] for c in b['mesh']['cells']]
  result=run_assembly_field_transient(r,problem,t);record=export_assembly_field_study(r,problem,result,transient_settings=t);import_assembly_field_study(record)
  for suffix,value in [('request',r),('problem',problem),('transient',t),('result',result),('fieldstudy',record)]:write(label+'.'+suffix+'.json',value)
  payload=_payload(r);payload['project']['name']=label;payload['models']['models'][0]['digest']=hashlib.sha256(step).hexdigest();path=OUT/(label+'.spike');manifest=write_spike_package(path,payload,model_artifacts={'original-case.step':step});save_assembly_field_study_in_project({'project_path':str(path),'expected_manifest_payload_sha256':manifest['manifest_payload_sha256'],'record':record},application_version='promo-core');opened=read_project(path);loaded=read_assembly_field_study_in_project({'project_path':str(path),'expected_manifest_payload_sha256':opened.manifest['manifest_payload_sha256']},application_version='promo-core');assert loaded['state']=='current' and loaded['saved_result_present']
  e=result['field_result']['energy_balance'];assert abs(e['imbalance_j'])<=e['acceptance_tolerance_j'];assert len(result['field_result']['frames'])>=20
  rows.append({'case':label,'supplied_power_w':watts,'native_readback':'current with saved result','frames':len(result['field_result']['frames']),'temperatures':result['occurrence_temperatures'],'energy_balance':e})
 write('thermal-verification.json',{'status':'passed','production_qualified':False,'scope':'Core-only supplied heating, no winding/converter coupling','assumptions':{'k_w_mk':5.5,'cp_j_kgk':700,'density_kg_m3':4850,'mating_h_w_m2k':h,'exterior_h_w_m2k':10.,'ambient_k':298.15},'CAD_nominal_volume_m3':totalvol,'not_magnetic_effective_volume':True,'cases':rows,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()});print(json.dumps(rows))
if __name__=='__main__':main()
