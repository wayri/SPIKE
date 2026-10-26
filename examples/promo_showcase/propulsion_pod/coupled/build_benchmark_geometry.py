# SPDX-License-Identifier: Apache-2.0
"""Original visual CAD matching the experimental coupled benchmark dimensions.

Flat-plate blades are an illustrative BEM visualization, not validated CFD CAD.
"""
from pathlib import Path
import sys,os,ctypes.util,importlib.util,json,hashlib,math,copy
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT))
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod import DEFAULT_REQUEST
from python.spike_core.solvers.electromagnetics.propulsion.propulsion_pod_field import validate_field_spec
from tests.python.test_assembly_joint_thermal_mesh import runtime
from unittest.mock import patch
OUT=ROOT/'output/promo-propulsion-pod-20261023/coupled_geometry';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(n,v):(OUT/n).write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def linear(xs,values,x):
 for i in range(len(xs)-1):
  if x<=xs[i+1]:
   w=(x-xs[i])/(xs[i+1]-xs[i]);return (1-w)*values[i]+w*values[i+1]
 return values[-1]
def main():
 request=copy.deepcopy(DEFAULT_REQUEST);field=validate_field_spec(request['field_motor']);prop=request['propeller']
 if prop['blade_count']!=2:raise ValueError('This original visual generator admits the coupled two-blade default only')
 R=prop['radial_stations_m'][-1]*1000;hub=prop['radial_stations_m'][0]*1000;depth=field['stack_depth_m']*1000;rotor=field['rotor_radius_m']*1000;wi=field['winding_inner_radius_m']*1000;wo=field['winding_outer_radius_m']*1000
 if wo>=22.5 or abs(depth-20)>1e-9 or R>151:raise ValueError('Benchmark geometry changed; review stand/motor clearances explicitly')
 sourcefiles=[ROOT/'python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod.py',ROOT/'python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_field.py',ROOT/'python/spike_core/solvers/electromagnetics/propulsion/propulsion_pod_propeller.py'];before={str(p.relative_to(ROOT)):sha(p) for p in sourcefiles}
 binding={'coupled_request_contract':request['contract'],'field_motor':field,'propeller':prop};write('benchmark-geometry-binding.json',{'parameters':binding,'sha256':digest(binding),'source_files':before})
 with os.add_dll_directory(str(runtime.DLL.parent)):
  original=ctypes.util.find_library
  with patch.object(ctypes.util,'find_library',side_effect=lambda n:str(runtime.DLL) if n in ('gmsh','gmsh-4.15') else original(n)):
   spec=importlib.util.spec_from_file_location('gmsh',runtime.API);g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
  g.initialize(['gmsh','-nopopup'],readConfigFiles=False)
  try:
   g.option.setNumber('General.Terminal',0);records=[]
   def fresh(name):g.clear();g.model.add(name)
   def save(name,count,expected=None):
    g.model.occ.synchronize();solids=g.model.getEntities(3);assert len(solids)==count,(name,solids);volumes=[g.model.occ.getMass(*s) for s in solids];assert all(v>0 and math.isfinite(v) for v in volumes)
    if expected is not None:assert math.isclose(sum(volumes),expected,rel_tol=1e-9),(name,volumes,expected)
    bbox=[g.model.occ.getBoundingBox(*s) for s in solids];g.write(str(OUT/name));records.append({'file':name,'closed_solids':count,'volumes_mm3':volumes,'bbox_mm':bbox,'sha256':sha(OUT/name)})
   fresh('Original high-axis restrained benchmark stand')
   base=g.model.occ.addBox(-60,-50,0,120,100,6);stem=g.model.occ.addBox(-12,-15,6,24,30,164);cradle=g.model.occ.addBox(-15,-32,165,30,64,35);parts=g.model.occ.fuse([(3,base)],[(3,stem),(3,cradle)])[0];hole=g.model.occ.addCylinder(-16,0,200,32,0,0,25);g.model.occ.cut(parts,[(3,hole)]);save('benchmark-stand.step',1)
   def ring(x,length,outer,inner):
    a=g.model.occ.addCylinder(x,0,200,length,0,0,outer);b=g.model.occ.addCylinder(x,0,200,length,0,0,inner);return g.model.occ.cut([(3,a)],[(3,b)])[0]
   fresh('Original nominal motor housing envelope');ring(-10,depth,25,22.5);save('benchmark-motor-housing.step',1,math.pi*(25**2-22.5**2)*depth)
   fresh('Original uniform PM rotor reference');g.model.occ.addCylinder(-10,0,200,depth,0,0,rotor);save('benchmark-motor-rotor.step',1,math.pi*rotor**2*depth)
   fresh('Original winding region envelope');ring(-10,depth,wo,wi);save('benchmark-motor-winding-annulus.step',1,math.pi*(wo**2-wi**2)*depth)
   fresh('Motor envelope region assembly')
   for n in ['benchmark-motor-housing.step','benchmark-motor-rotor.step','benchmark-motor-winding-annulus.step']:g.model.occ.importShapes(str(OUT/n))
   save('benchmark-motor-envelope.step',3)
   fresh('Original reference shaft');g.model.occ.addCylinder(10,0,200,70,0,0,3);save('benchmark-shaft.step',1,math.pi*9*70)
   fresh('Original flat-plate BEM visual propeller')
   ring(78,14,hub,3.2);stations=sorted(set(prop['radial_stations_m']+[prop['radial_stations_m'][0]+i*(prop['radial_stations_m'][-1]-prop['radial_stations_m'][0])/8 for i in range(9)]));sections=[]
   thickness=.6
   for blade in range(2):
    azimuth=math.pi/2+blade*math.pi;er=(0,math.cos(azimuth),math.sin(azimuth));et=(0,-math.sin(azimuth),math.cos(azimuth));wires=[]
    for radius in stations:
     chord=linear(prop['radial_stations_m'],prop['chord_m'],radius)*1000;theta=linear(prop['radial_stations_m'],prop['twist_rad'],radius);r=radius*1000;centre=(85,r*er[1],200+r*er[2]);ec=(math.sin(theta),math.cos(theta)*et[1],math.cos(theta)*et[2]);en=(math.cos(theta),-math.sin(theta)*et[1],-math.sin(theta)*et[2]);points=[]
     for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]:points.append(g.model.occ.addPoint(*[centre[k]+a*chord/2*ec[k]+b*thickness/2*en[k] for k in range(3)]))
     lines=[g.model.occ.addLine(points[k],points[(k+1)%4]) for k in range(4)];wires.append(g.model.occ.addWire(lines,checkClosed=True));sections.append({'blade':blade+1,'radial_station_m':radius,'chord_m':chord/1000,'twist_rad':theta,'section_center_mm':centre,'flat_plate_thickness_mm':thickness})
    g.model.occ.addThruSections(wires,makeSolid=True,makeRuled=True)
   save('benchmark-propeller-flat-plate-visual.step',3)
   write('blade-sections.json',{'geometry_binding_sha256':digest(binding),'sections':sections,'scope':'Original ruled flat-plate visual loft; no measured airfoil or CFD surface qualification'})
   fresh('Original complete high-axis coupled benchmark display')
   for name in ['benchmark-stand.step','benchmark-motor-envelope.step','benchmark-shaft.step','benchmark-propeller-flat-plate-visual.step']:g.model.occ.importShapes(str(OUT/name))
   save('benchmark-complete-visual-assembly.step',8)
   before_import=sum(g.model.occ.getMass(*s) for s in g.model.getEntities(3));fresh('STEP roundtrip');g.model.occ.importShapes(str(OUT/'benchmark-complete-visual-assembly.step'));g.model.occ.synchronize();solids=g.model.getEntities(3);assert len(solids)==8;after_import=sum(g.model.occ.getMass(*s) for s in solids);assert math.isclose(before_import,after_import,rel_tol=1e-9)
   assert {str(p.relative_to(ROOT)):sha(p) for p in sourcefiles}==before,'Coupled source changed during geometry generation; rerun against current definitions'
   lower_sweep=200-math.hypot(R,max(prop['chord_m'])*500+thickness/2);assert lower_sweep>6
   write('verification.json',{'status':'passed','production_qualified':False,'units':'mm','geometry_binding_sha256':digest(binding),'independent_original_parts':records,'full_assembly_closed_solids':8,'STEP_reimport_volume_mm3':after_import,'motor_axis':{'origin_mm':[0,0,200],'direction':[1,0,0]},'motor_outer_diameter_mm':50,'field_outer_air_domain_radius_mm':field['outer_radius_m']*1000,'field_air_domain_is_not_solid':True,'propeller_plane_x_mm':85,'shaft_x_mm':[10,80],'conservative_rotor_sweep_lowest_z_mm':lower_sweep,'base_top_z_mm':6,'sweep_clearance_to_base_mm':lower_sweep-6,'source_files':before,'scope':'Original visual geometry matching BEM radial/chord/twist and field reference region dimensions; not CAD-authenticated FEM, structural restraint or resolved blade CFD'})
  finally:g.finalize()
 print('Original high-axis benchmark STEP geometry and8-solid roundtrip passed')
if __name__=='__main__':main()
