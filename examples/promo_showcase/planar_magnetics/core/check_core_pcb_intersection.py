# SPDX-License-Identifier: Apache-2.0
"""Check selected final assembly core-vs-PCB solid intersections with OCC."""
from pathlib import Path
import sys,os,ctypes.util,importlib.util,json
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from tests.python.test_assembly_joint_thermal_mesh import runtime
from unittest.mock import patch
OUT=ROOT/'output/promo-planar-magnetics-20261023/core'
with os.add_dll_directory(str(runtime.DLL.parent)):
 original=ctypes.util.find_library
 with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
  spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
 g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
 try:
  g.option.setNumber('General.Terminal',0);g.model.add('Core PCB collision check');g.model.occ.importShapes(str(OUT/'original-planar-module-full.step'));g.model.occ.synchronize()
  solids=g.model.getEntities(3);cores=[];boards=[]
  for item in solids:
   b=g.model.occ.getBoundingBox(*item);vol=g.model.occ.getMass(*item)
   if abs(b[3]-b[0]-31.75)<1e-4 and abs(b[4]-b[1]-20.35)<1e-4 and vol>2000:cores.append(item)
   elif 6.5999<=b[2] and b[5]<=8.4001:boards.append(item)
  assert len(cores)==2
  # Pin solids start below carrier and are excluded by the board z envelope.
  intersections=[]
  for core in cores:
   c=g.model.occ.copy([core]);b=g.model.occ.copy(boards);common=g.model.occ.intersect(c,b,removeObject=True,removeTool=True)[0];g.model.occ.synchronize();v=sum(g.model.occ.getMass(dim,t) for dim,t in common if dim==3);intersections.append(v)
  report={'status':'passed' if max(intersections)<1e-6 else 'failed','check':'OCC solid-volume intersection of2corehalves against all PCB-body/copper solids; pins excluded','core_PCB_intersection_volume_mm3':intersections,'tolerance_mm3':1e-6,'PCB_solids_checked':len(boards),'scope':'Nominal collision only, not clearance/tolerance/creepage qualification'}
  (OUT/'core-pcb-intersection-check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));assert report['status']=='passed'
 finally:g.finalize()
