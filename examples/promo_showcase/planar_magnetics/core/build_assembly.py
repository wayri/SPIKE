# SPDX-License-Identifier: Apache-2.0
"""Original nominal module pins; optional located PCB STEP compound export."""
from pathlib import Path
import sys,os,ctypes.util,importlib.util,json,hashlib,argparse,math
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from tests.python.test_assembly_joint_thermal_mesh import runtime
from unittest.mock import patch
OUT=ROOT/'output/promo-planar-magnetics-20261023/core'
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--primary',type=Path);parser.add_argument('--secondary',type=Path);args=parser.parse_args()
 if bool(args.primary)!=bool(args.secondary):parser.error('Supply both correctly located board STEP files, or neither.')
 with os.add_dll_directory(str(runtime.DLL.parent)):
  original=ctypes.util.find_library
  with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
   spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
  g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
  try:
   g.option.setNumber('General.Terminal',0);g.model.add('Original square pin34 module terminals')
   pins=[('P1',-20.,-1.27,.8),('P2',-20.,1.27,.8)]
   xs=[-8.89,-6.35,-3.81,-1.27,1.27,3.81,6.35,8.89]
   for group,ys in [('S1',[20.,22.54]),('S2',[-20.,-22.54])]:
    for row,y in enumerate(ys):
     for col,x in enumerate(xs):pins.append((f'{group}-{row+1}-{col+1}',x,y,2.4))
   evidence=[]
   for name,x,y,top in pins:
    tag=g.model.occ.addBox(x-.32,y-.32,-8.2,.64,.64,top+8.2);evidence.append({'id':name,'x_mm':x,'y_mm':y,'z_min_mm':-8.2,'z_max_mm':top,'cross_section_mm':[.64,.64],'nominal_volume_mm3':.64*.64*(top+8.2),'occ_tag':tag})
   g.model.occ.synchronize();assert len(g.model.getEntities(3))==34
   for p in evidence:assert math.isclose(g.model.occ.getMass(3,p['occ_tag']),p['nominal_volume_mm3'],rel_tol=1e-12)
   g.write(str(OUT/'original-pin34-terminals.step'))
   original_core=OUT/'original-nominal-elp32-core-pair.step';core=g.model.occ.importShapes(str(original_core));g.model.occ.synchronize();assert len(g.model.getEntities(3))==36
   inputs=[{'path':original_core.name,'sha256':hashlib.sha256(original_core.read_bytes()).hexdigest()}]
   if args.primary:
    for kind,path in [('primary',args.primary),('secondary',args.secondary)]:
     entities=g.model.occ.importShapes(str(path.resolve()));g.model.occ.synchronize();solids=[(dim,t) for dim,t in entities if dim==3];assert solids
     body=max(solids,key=lambda item:g.model.occ.getMass(*item));bodybox=g.model.occ.getBoundingBox(*body)
     expected_xy=(44.,38.) if kind=='primary' else (50.,50.)
     if abs(bodybox[3]-bodybox[0]-expected_xy[0])>1e-4 or abs(bodybox[4]-bodybox[1]-expected_xy[1])>1e-4:raise ValueError(f'{kind} dominant board body bounds differ from contract')
     boxes=[g.model.occ.getBoundingBox(*item) for item in solids];low=min(b[2] for b in boxes);high=max(b[5] for b in boxes)
     if not .6<high-low<1.:raise ValueError(f'{kind} thickness {high-low} indicates unwanted component or wrong board')
     # Keep exported copper/dielectric thickness; no geometric scale or invented mask.
     bottom=0. if kind=='primary' else 1.
     transform=[-(bodybox[0]+bodybox[3])/2,-(bodybox[1]+bodybox[4])/2,bottom-low]
     g.model.occ.translate(solids,*transform);g.model.occ.synchronize()
     inputs.append({'kind':kind,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_body_bbox_mm':bodybox,'original_copper_envelope_z_mm':[low,high],'rigid_translation_mm':transform,'placed_copper_envelope_z_mm':[bottom,bottom+high-low],'nominal_board_thickness_mm':.8,'exported_thickness_mm':high-low,'note':'KiCad STEP Y=-PCB Y retained; core/pin layout symmetric. No component models; no rescale.'})
   all_entities=g.model.getEntities(3);g.model.occ.translate(all_entities,0,0,6.6);g.model.occ.synchronize()
   filename='original-planar-module-full.step' if args.primary else 'original-core-pin34-module.step';g.write(str(OUT/filename));count=len(all_entities);mass=sum(g.model.occ.getMass(3,t) for _,t in all_entities)
   g.clear();g.model.add('Full STEP readback');g.model.occ.importShapes(str(OUT/filename));g.model.occ.synchronize();assert len(g.model.getEntities(3))==count
   actual=sum(g.model.occ.getMass(3,t) for _,t in g.model.getEntities(3));assert math.isclose(actual,mass,rel_tol=1e-9)
   payload={'status':'passed','pcb_included':bool(args.primary),'assembly_step':filename,'units':'mm','pin_count':34,'pin_origin_contract':'core mating centre before final module transform','module_translation_z_mm':6.6,'final_secondary_pin_z_mm':[-1.6,9.0],'final_primary_pin_z_mm':[-1.6,7.4],'pin_geometry':'Original nominal Berg-style 0.64mm square terminals; no supplier pin rating or plating law','pins':evidence,'input_hashes':inputs,'solid_count':count,'STEP_reimport_total_volume_mm3':actual,'limitations':['No contact resistance/current rating, creepage or assembly fit qualification','Nominal square pins have no solder, bevel, plating or housing geometry','Full module compound preserves separate solids; is not coupled physics evidence']}
   (OUT/('assembly-verification.json' if args.primary else 'pin34-verification.json')).write_text(json.dumps(payload,indent=2)+'\n')
  finally:g.finalize()
 print('Original34 terminal pins and compound STEP readback passed; PCBs included:',bool(args.primary))
if __name__=='__main__':main()
