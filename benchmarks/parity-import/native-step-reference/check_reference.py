# SPDX-License-Identifier: Apache-2.0
"""Original independent cuboid-corner arithmetic against actual native STEP."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

def rotate(p,axis,angle):
    c=math.cos(math.radians(angle)); s=math.sin(math.radians(angle))
    x,y,z=p
    if axis=='x':return [x,c*y-s*z,s*y+c*z]
    if axis=='y':return [c*x+s*z,y,-s*x+c*z]
    return [c*x-s*y,s*x+c*y,z]

def predict(p,case,model):
    q=[v*s for v,s in zip(p,model['scale'])]
    for axis,angle in zip('xyz',model['rotation_deg']):q=rotate(q,axis,-angle)
    q=[v+d for v,d in zip(q,model['offset_mm'])]
    if case['side']=='back':q=rotate(q,'x',180)
    q=rotate(q,'z',case['footprint_angle_deg'])
    x,y=case['footprint_position_mm']
    return [x+q[0],-y+q[1],(1.615 if case['side']=='front' else -.085)+q[2]]

def point_error(a,b):return max(abs(x-y) for x,y in zip(a,b))

def corners_error(actual,expected):
    assert len(actual)==len(expected)==8
    matches=[min(range(8),key=lambda i:point_error(p,actual[i])) for p in expected]
    assert len(set(matches))==8, 'Each expected cuboid corner must match a distinct observed vertex'
    return max(point_error(p,actual[i]) for p,i in zip(expected,matches))

def bounds(points):return [min(p[i] for p in points) for i in range(3)]+[max(p[i] for p in points) for i in range(3)]

p=argparse.ArgumentParser()
p.add_argument('--repo-root',type=Path,default=Path(__file__).resolve().parents[2])
p.add_argument('--output-root',type=Path,default=Path(__file__).resolve().parent)
a=p.parse_args();root=a.output_root.resolve();repo=a.repo_root.resolve()
data=json.loads((root/'observed-solids.json').read_text())
inputs=json.loads((root/'inputs.json').read_text())
tol=2e-6
source=data['files']['component-solid.step']['solids']
assert len(source)==1 and source[0]['valid']
source_points=list(itertools.product([0,2],[0,3],[0,4]))
assert corners_error(source[0]['vertices_mm'],source_points)<tol
assert point_error(source[0]['bounds_mm'],[0,0,0,2,3,4])<tol
assert abs(source[0]['volume_mm3']-24)<1e-8
results=[];boards=[]
for case in inputs['cases']:
    solids=data['files'][case['name']+'.step']['solids']
    assert len(solids)==4 and all(s['valid'] for s in solids)
    board=[s for s in solids if len(s['vertices_mm'])==16]
    assert len(board)==1
    board=board[0]
    assert point_error(board['bounds_mm'],[-1,-20,0,30,1,1.53])<tol
    assert abs(board['volume_mm3']-(31*21-2*2)*1.53)<1e-6
    boards.append({'name':case['name'],**board})
    used=[]
    for model in case['models']:
        expected=[predict(pt,case,model) for pt in source_points]
        candidates=[(i,s) for i,s in enumerate(solids) if len(s['vertices_mm'])==8 and i not in used]
        i,native=min(candidates,key=lambda item:point_error(item[1]['bounds_mm'],bounds(expected)))
        used.append(i)
        err=corners_error(native['vertices_mm'],expected)
        bound_error=point_error(native['bounds_mm'],bounds(expected))
        expected_volume=24*math.prod(model['scale'])
        volume_error=abs(native['volume_mm3']-expected_volume)
        assert err<tol and bound_error<tol and volume_error<1e-6,(case['name'],model['model_index'],err,bound_error,volume_error)
        results.append({'name':case['name'],'side':case['side'],'footprint_angle_deg':case['footprint_angle_deg'],'model_index':model['model_index'],'source_inputs':model,'native_solid_index':i,'native':native,'expected_vertices_mm':expected,'expected_bounds_mm':bounds(expected),'expected_volume_mm3':expected_volume,'max_vertex_error_mm':err,'max_bounds_error_mm':bound_error,'volume_error_mm3':volume_error,'spike_vertices_mm':[[v[0],-v[1],1.565-v[2]] for v in native['vertices_mm']]})

controls={}
for side in ['front','back']:
    standard=data['files'][side+'-90.step']['solids']
    no_extra=data['files'][side+'-90-no-extra.step']['solids']
    assert len(no_extra)==4
    for s,t in zip(standard,no_extra):
        assert point_error(s['bounds_mm'],t['bounds_mm'])<tol
    copper=data['files'][side+'-90-copper.step']['solids']
    assert len(copper)==6 and all(s['valid'] for s in copper)
    thin=[s for s in copper if abs(s['bounds_mm'][5]-s['bounds_mm'][2]-.035)<tol]
    assert len(thin)==2
    assert any(abs(s['bounds_mm'][2]-1.53)<tol and abs(s['bounds_mm'][5]-1.565)<tol for s in thin)
    if side=='back':assert any(abs(s['bounds_mm'][2]+.035)<tol and abs(s['bounds_mm'][5])<tol for s in thin)
    controls[side]={'no_extra_flag_changes_component_placement':False,'copper_solids':thin,'observed_mounting_clearance_mm':.05}

report={'contract':'spike/native-step-placement-reference/v1','status':'passed_local_black_box_reference','native_version':inputs['native_version'],'freecad_version':data['freecad_version'],'tolerance_mm':tol,'volume_tolerance_mm3':1e-6,'source_solid':source[0],'inputs':inputs,'cases':results,'board_bodies':boards,'datum_controls':controls,'frame':{'native_step':'millimetres; X=boardX, Y=-boardY; dielectric bottom Z=0, top Z=1.53','physical_copper_surfaces_mm':{'front':1.565,'back':-.035},'model_mounting_planes_mm':{'front':1.615,'back':-.085},'native_step_to_spike':'(x,y,z) -> (x,-y,1.565-z) mm; full stack top=0, depth positive','native_step_to_prior_vrml':'same XY and rotation; for identical mm-valued model corners, z_step=z_vrml+0.765+side*0.05 (side=+1 front,-1 back)','vrml_unit_difference':'prior source WRL coordinates use 2.54 mm/unit; source STEP solid is natively mm','formula':'p_step=(20,-10,z_mount)+B*offset+B*Rz(-rz)*Ry(-ry)*Rx(-rx)*diag(scale)*p_source_mm; B=Rz(footprintAngle) front, Rz(footprintAngle)*Rx(180) back'},'scope':'Original owned 2x3x4mm cuboid, three model vectors, front/back at 90/37 degrees, one 1.6mm stackup; no production adapter or physics/material qualification; overall WF01-S04C remains in progress','bindings':{'sources':{},'artifacts':{}},'exports':{}}
for name in ['models.kicad_pcb','component-solid.step']:
    path=repo/'benchmarks/parity-import'/name
    report['bindings']['sources'][path.relative_to(repo).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
for path in sorted(root.iterdir()):
    if path.suffix not in ['.py','.step','.kicad_pcb','.json'] or path.name in ['composition-reference.json','check-log.json']:continue
    report['bindings']['artifacts'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    if path.name.endswith('-export.json'):
        execution=json.loads(path.read_text())
        assert execution['returncode']==0
        report['exports'][path.name]=execution
(root/'composition-reference.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'status':report['status'],'cases':len(results),'max_vertex_error_mm':max(r['max_vertex_error_mm'] for r in results),'max_volume_error_mm3':max(r['volume_error_mm3'] for r in results)},indent=2))
