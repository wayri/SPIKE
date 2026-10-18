# SPDX-License-Identifier: Apache-2.0
"""Read exact STEP solids via FreeCAD public Part API, without tessellation."""
import json
import os
from pathlib import Path
import FreeCAD as App
import Part

root=Path(os.environ.get('SPIKE_STEP_REFERENCE_ROOT',Path(__file__).resolve().parent))
repo=Path(os.environ.get('SPIKE_STEP_REFERENCE_REPO',Path(__file__).resolve().parents[2]))
paths=[repo/'benchmarks/parity-import/component-solid.step']+sorted(root.glob('*.step'))
result={'freecad_version':App.Version(), 'reader':'Part.Shape.read; Shape.Solids; Solid.Vertexes; Solid.BoundBox; Solid.Volume', 'files':{}}
for path in paths:
    shape=Part.Shape()
    shape.read(str(path))
    solids=[]
    for solid in shape.Solids:
        box=solid.BoundBox
        solids.append({'volume_mm3':solid.Volume,'valid':solid.isValid(),'bounds_mm':[box.XMin,box.YMin,box.ZMin,box.XMax,box.YMax,box.ZMax], 'vertices_mm':[[v.Point.x,v.Point.y,v.Point.z] for v in solid.Vertexes]})
    result['files'][path.name]={'solids':solids}
(root/'observed-solids.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:[{'volume':s['volume_mm3'],'bounds':s['bounds_mm'],'vertices':len(s['vertices_mm'])} for s in v['solids']] for k,v in result['files'].items()},indent=2))
