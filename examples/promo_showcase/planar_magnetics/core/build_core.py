# SPDX-License-Identifier: Apache-2.0
"""Original simplified nominal ELP32 CAD; no supplier CAD/undimensioned detail."""
from pathlib import Path
import sys,json,hashlib,math,ctypes.util,importlib.util,os
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/promo-planar-magnetics-20261023/core';OUT.mkdir(parents=True,exist_ok=True)
from tests.python.test_assembly_joint_thermal_mesh import runtime
from unittest.mock import patch

def write(name,v):(OUT/name).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def main():
 with os.add_dll_directory(str(runtime.DLL.parent)):
  original=ctypes.util.find_library
  with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
   spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
  g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
  try:
   g.option.setNumber('General.Terminal',0);g.model.add('Original nominal ELP32 simplification')
   shape=g.model.occ.addBox(-15.875,-10.175,0,31.75,20.35,6.35)
   cuts=[(3,g.model.occ.addBox(x,-10.175,0,9.525,20.35,3.2)) for x in (-12.7,3.175)]
   upper=g.model.occ.cut([(3,shape)],cuts)[0];lower=g.model.occ.copy(upper);g.model.occ.rotate(lower,0,0,0,1,0,0,math.pi);g.model.occ.synchronize()
   assert len(g.model.getEntities(3))==2
   checks=[]
   for label,entities,z0,z1 in [('upper',upper,0,6.35),('lower',lower,-6.35,0)]:
    tag=entities[0][1];volume=g.model.occ.getMass(3,tag);bbox=g.model.occ.getBoundingBox(3,tag)
    expected=31.75*20.35*6.35-2*9.525*20.35*3.2
    assert math.isclose(volume,expected,rel_tol=1e-12)
    assert all(abs(a-b)<1e-5 for a,b in zip(bbox,[-15.875,-10.175,z0,15.875,10.175,z1]))
    checks.append({'part':label,'volume_mm3':volume,'bbox_mm':bbox,'expected_rectilinear_volume_mm3':expected})
   g.write(str(OUT/'original-nominal-elp32-core-pair.step'))
   # Independent STEP import recovers both closed solids and their volumes.
   g.clear();g.model.add('STEP readback');readback=g.model.occ.importShapes(str(OUT/'original-nominal-elp32-core-pair.step'));g.model.occ.synchronize();solids=g.model.getEntities(3);assert len(solids)==2
   masses=[g.model.occ.getMass(3,t) for _,t in solids];assert all(math.isclose(v,expected,rel_tol=1e-9) for v in masses)
   write('geometry-verification.json',{'status':'passed','units':'mm','closed_solids':2,'checks':checks,'step_readback_volumes_mm3':masses,'scope':'Original rectilinear nominal shape; omits undimensioned radii/bevels/clamp recess','physical_effective_volume_mm3':5390,'cad_pair_volume_mm3':sum(masses),'volume_distinction':'CAD solid volume is not effective magnetic Ve; never substitute one for the other','generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
  finally:g.finalize()
 print('Two nominal original ELP32 halves and STEP import checks passed')
if __name__=='__main__':main()
