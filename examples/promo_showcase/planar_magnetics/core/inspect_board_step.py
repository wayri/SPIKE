from pathlib import Path
import sys,os,ctypes.util,importlib.util,json
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from tests.python.test_assembly_joint_thermal_mesh import runtime
from unittest.mock import patch
with os.add_dll_directory(str(runtime.DLL.parent)):
 original=ctypes.util.find_library
 with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
  spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
 g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
 try:
  g.option.setNumber('General.Terminal',0)
  for name in ['primary','secondary']:
   g.clear();g.model.add(name);g.model.occ.importShapes(str(ROOT/'output/promo-planar-magnetics-20261023/windings'/f'{name}.step'));g.model.occ.synchronize();rows=sorted([{'tag':t,'mass_mm3':g.model.occ.getMass(3,t),'bbox_mm':g.model.occ.getBoundingBox(3,t)} for _,t in g.model.getEntities(3)],key=lambda r:r['mass_mm3'],reverse=True);print(name,json.dumps(rows[:5]),'solids',len(rows))
 finally:g.finalize()
