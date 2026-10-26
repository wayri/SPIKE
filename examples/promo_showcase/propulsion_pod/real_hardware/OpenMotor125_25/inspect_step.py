import FreeCAD as App, Import, Part, json, hashlib
from pathlib import Path
base=Path(r'C:/Users/yawar/Documents/agws/KiCAD_plugins/SPIKE/examples/promo_showcase/propulsion_pod/real_hardware/OpenMotor125_25')
p=base/'CIAG_2_28 125_25.step'
doc=App.newDocument('OpenMotorReview');Import.insert(str(p),doc.Name)
rows=[]
for o in doc.Objects:
 if hasattr(o,'Shape') and not o.Shape.isNull():
  s=o.Shape;b=s.BoundBox
  rows.append(dict(name=o.Name,label=o.Label,solids=len(s.Solids),volume_mm3=s.Volume,bbox_mm=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax],valid=s.isValid()))
result=dict(source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),freecad_version=App.Version(),units='mm, mm^3',objects=rows,notes=['Geometric validity is not electromagnetic topology, material identity, measured resistance or manufacturing validation.','Shapes in assembly/group objects may include children; do not sum all object volumes to infer mass.'])
(base/'STEP_NATIVE_INSPECTION.json').write_text(json.dumps(result,indent=2))
print('REVIEW_OBJECTS',len(rows));print('REVIEW_LABELS',[(r['label'],r['solids']) for r in rows])
