# SPDX-License-Identifier: Apache-2.0
"""Original illustrative PCB/hollow-case transient; no real-board material claim."""
from pathlib import Path
import sys,json,copy,itertools,hashlib,ctypes.util,importlib.util,os
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from python.spike_core.spider_v2 import AssemblyIRV1
from python.spike_core.multiboard_identity import canonical_json_digest as digest
from python.spike_core.solvers.execution.coupling.assembly_field_transient import run_assembly_field_transient
from python.spike_core.solvers.execution.coupling.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from python.spike_core.project_package import write_spike_package, read_project
from python.spike_core.service_project_assembly_field import save_assembly_field_study_in_project, read_assembly_field_study_in_project
from tests.python.test_project_assembly_field import _payload
OUT=ROOT/'output/promo-showcase-20261023/thermal_flow';OUT.mkdir(parents=True,exist_ok=True)
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def mesh(xs,ys,zs,include):
    points=[];lookup={};cells=[]
    def node(p):
        p=tuple(p)
        if p not in lookup:lookup[p]=len(points);points.append(list(p))
        return lookup[p]
    for i,j,k in itertools.product(range(len(xs)-1),range(len(ys)-1),range(len(zs)-1)):
        if not include(i,j,k):continue
        for axes in itertools.permutations(range(3)):
            bits=[0,0,0];ids=[node((xs[i],ys[j],zs[k]))]
            for a in axes:
                bits[a]=1;ids.append(node(([xs[i],xs[i+1]][bits[0]],[ys[j],ys[j+1]][bits[1]],[zs[k],zs[k+1]][bits[2]])))
            xyz=np.asarray([points[v] for v in ids])
            if np.linalg.det((xyz[1:]-xyz[0]).T)<0:ids[1],ids[2]=ids[2],ids[1]
            cells.append({'id':str(len(cells)),'kind':'tetrahedron','vertices':ids,'material_id':'bulk','source_object_ids':['original-solid']})
    counts={}
    for c in cells:
        for f in itertools.combinations(c['vertices'],3):
            f=tuple(sorted(f));counts[f]=counts.get(f,0)+1
    faces=[{'id':'face-'+str(i),'vertices':list(f)} for i,(f,n) in enumerate(counts.items()) if n==1]
    return {'contract':'spike/solver-mesh/v1','units':'mm','coordinate_system':'right_handed_xyz','vertices':points,'cells':cells,'counts':{'vertices':len(points),'cells':len(cells)},'object_map':{'original-solid':{'kind':'solid'}}},faces

def create_step():
    from tests.python.test_assembly_joint_thermal_mesh import runtime
    from unittest.mock import patch
    with os.add_dll_directory(str(runtime.DLL.parent)):
        original=ctypes.util.find_library
        with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
            spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
        g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
        try:
            g.option.setNumber('General.Terminal',0);g.model.add('Original hollow illustrative case')
            a=g.model.occ.addBox(-4,-4,-2,28,28,12);b=g.model.occ.addBox(-2,-2,0,24,24,8)
            g.model.occ.cut([(3,a)],[(3,b)]);g.model.occ.synchronize();g.write(str(OUT/'original-hollow-case.step'))
        finally:g.finalize()
    return (OUT/'original-hollow-case.step').read_bytes()

def setup():
    board,bf=mesh([0,10,20],[0,10,20],[0,.8,1.6],lambda i,j,k:True)
    axes=[-4,-2,0,10,20,22,24];z=[-2,0,.8,1.6,8,10]
    case,cf=mesh(axes,axes,z,lambda i,j,k:k in (0,4) or i in (0,5) or j in (0,5))
    raw={'assembly_id':'promo-original-hollow-case','name':'Illustrative PCB inside hollow case','boards':[{'id':'board','design_id':'original-board','name':'Original homogeneous PCB','frame':{'frame_id':'board-frame'}}],'parts':[{'id':'case','model_id':'original-case','name':'Original hollow case heat sink','part_type':'enclosure','frame':{'frame_id':'case-frame'}}],'thermal_contacts':[{'id':'board-case','endpoint_a':'board','endpoint_b':'case','contact_area_mm2':400.,'thermal_resistance_k_per_w':5.}]}
    r={'contract':'spike/assembly-field-handoff-request/v1','domain':'thermal','assembly':AssemblyIRV1.from_dict(raw).to_dict(),'materials':[{'id':'pcb','thermal_conductivity_w_mk':.5,'provenance':'Illustrative homogeneous effective PCB, not actual laminate'},{'id':'case-material','thermal_conductivity_w_mk':150.,'provenance':'Illustrative constant case conductivity, not certified alloy'}],'bodies':[]}
    for oid,m,f,mid in [('board',board,bf,'pcb'),('case',case,cf,'case-material')]:
        body={'occurrence_id':oid,'reference_id':'original-board' if oid=='board' else 'original-case','source_sha256':digest([oid,m]),'mesh':m,'boundary_faces':f,'material_map':{'bulk':mid}}
        if oid=='board':body['stack_binding']={'id':'homogeneous','source_sha256':digest(['homogeneous',1.6])}
        r['bodies'].append(body)
    p={'contract':'spike/assembly-field-thermal-problem/v1','boundaries':[],'contacts':[],'heat_sources':[]}
    pairs=[];used=set()
    for f in bf:
        coords={tuple(board['vertices'][v]) for v in f['vertices']}
        if all(v[2]==0 for v in coords):
            other=next(ff for ff in cf if {tuple(case['vertices'][v]) for v in ff['vertices']}==coords)
            pairs.append({'left':{'occurrence_id':'board','face_id':f['id']},'right':{'occurrence_id':'case','face_id':other['id']}});used.add(other['id'])
    p['contacts']=[{'contact_id':'board-case','face_pairs':pairs,'thermal_contact_conductance_w_m2k':500.}]
    for f in cf:
        pts=[case['vertices'][v] for v in f['vertices']]
        external=any(all(v[a]==value for v in pts) for a,value in [(0,-4),(0,24),(1,-4),(1,24),(2,-2),(2,10)])
        if external:p['boundaries'].append({'face':{'occurrence_id':'case','face_id':f['id']},'type':'convection','heat_transfer_coefficient_w_m2k':10.,'ambient_temperature_k':300.})
    # Board volume 20*20*1.6 mm3 = 6.4e-7 m3, total source 0.2 W.
    p['heat_sources']=[{'occurrence_id':'board','cell_id':c['id'],'heat_source_w_m3':.2/6.4e-7} for c in board['cells']]
    t={'contract':'spike/assembly-tetra-transient-settings/v1','duration_s':120.,'time_step_s':2.,'output_interval_s':5.,'initial_temperature_k':300.,'material_heat_capacity':[{'material_id':'pcb','density_kg_m3':1800.,'specific_heat_j_kgk':1000.},{'material_id':'case-material','density_kg_m3':2700.,'specific_heat_j_kgk':900.}]}
    return r,p,t

def main():
    step=create_step();r,p,t=setup();results={}
    for name,h in [('case-contact',500.),('poor-contact',5.)]:
        problem=copy.deepcopy(p);problem['contacts'][0]['thermal_contact_conductance_w_m2k']=h
        req=copy.deepcopy(r);req['assembly']['thermal_contacts'][0]['thermal_resistance_k_per_w']=1/(h*.0004)
        result=run_assembly_field_transient(req,problem,t);results[name]=result
        record=export_assembly_field_study(req,problem,result,transient_settings=t);import_assembly_field_study(record)
        for suffix,value in [('request',req),('problem',problem),('transient',t),('result',result),('fieldstudy',record)]:write(OUT/f'{name}.{suffix}.json',value)
        payload=_payload(req);payload['project']['name']='Original PCB + hollow case: '+name
        d=payload['design_ir'];d['name']='Original illustrative homogeneous PCB';d['metadata']={'board_bounds_mm':[0.,0.,20.,20.],'board_outline_drawings':[{'kind':'polygon','points':[[0.,0.],[20.,0.],[20.,20.],[0.,20.],[0.,0.]]}]};d['layers']=[{'id':'homogeneous','name':'Homogeneous PCB','layer_type':'dielectric','order':0,'z_mm':0.,'thickness_mm':1.6}]
        payload['models']['models'][0]['digest']=hashlib.sha256(step).hexdigest()
        path=OUT/f'{name}.spike';manifest=write_spike_package(path,payload,model_artifacts={'original-case.step':step})
        save_assembly_field_study_in_project({'project_path':str(path),'expected_manifest_payload_sha256':manifest['manifest_payload_sha256'],'record':record},application_version='promo-original')
        reopened=read_project(path,include_members=True);loaded=read_assembly_field_study_in_project({'project_path':str(path),'expected_manifest_payload_sha256':reopened.manifest['manifest_payload_sha256']},application_version='promo-original')
        assert loaded['state']=='current' and loaded['saved_result_present']
        print(name,result['occurrence_temperatures'],flush=True)
    assert results['poor-contact']['occurrence_temperatures']['board']['maximum_k']>results['case-contact']['occurrence_temperatures']['board']['maximum_k']
    for result in results.values():
        energy=result['field_result']['energy_balance'];assert abs(energy['imbalance_j'])<=energy['acceptance_tolerance_j'];assert len(result['field_result']['frames'])>=20
    write(OUT/'verification.json',{'status':'passed','production_qualified':False,'native_reopen':'current with saved transient result','checks':['contact comparison: improved contact reduces board peak','solver energy balance within unchanged tolerance','at least 20 actual physical-time frames','fieldstudy import verifies retained digests'],'source_power_w':.2,'duration_s':120,'models':{k:v['occurrence_temperatures'] for k,v in results.items()},'source_sha256':{str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}})
if __name__=='__main__':main()
