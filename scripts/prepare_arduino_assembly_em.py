# SPDX-License-Identifier: Apache-2.0
"""Retain Arduino source repairs, filled copper and explicit EM study jobs.

Preparation fails closed with a retained report when the original converted
geometry cannot satisfy complete material-volume or numerical resource gates.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.assembly_em_board_geometry import prepare_routed_board_volume


def write(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')


def repair_shield(source, eagle, destination):
    """Restore source restrict wires as explicit copper-pour keepout polygons."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    text=source.read_text(encoding='utf-8')
    root=ET.parse(eagle).getroot()
    # Independent native-conversion receipt for every original board edge,
    # including the three curved corners; ignore duplicate drawing instances.
    dimensions={tuple(sorted(((float(w['x1']),-float(w['y1'])),(float(w['x2']),-float(w['y2']))))):w
                for w in (item.attrib for item in root.findall('.//board/plain/wire')) if w['layer']=='20'}
    outline=set();outline_instances=0
    for row in re.findall(r'\t\(gr_(?:line|arc)\n.*?\n\t\)',text,flags=re.S):
        if '(layer "Edge.Cuts")' not in row:continue
        ends=[tuple(map(float,re.search(r'\('+key+r' ([^ ]+) ([^)]+)\)',row).groups())) for key in ('start','end')]
        key=tuple(sorted(ends));wire=dimensions.get(key)
        if wire is None:raise ValueError('Converted outline edge has no original Eagle dimension match')
        theta=math.radians(-float(wire.get('curve',0)))
        if theta:
            if '(gr_arc' not in row:raise ValueError('Original curved board edge lost during conversion')
            a=(float(wire['x1']),-float(wire['y1']));b=(float(wire['x2']),-float(wire['y2']))
            expected=[(a[0]+b[0])/2+math.tan(theta/4)*(b[1]-a[1])/2,
                      (a[1]+b[1])/2-math.tan(theta/4)*(b[0]-a[0])/2]
            mid=list(map(float,re.search(r'\(mid ([^ ]+) ([^)]+)\)',row).groups()))
            if max(abs(x-y) for x,y in zip(mid,expected))>1e-6:raise ValueError('Original curved board edge midpoint differs')
        elif '(gr_line' not in row:raise ValueError('Original straight board edge changed shape')
        outline.add(key);outline_instances+=1
    if outline!=set(dimensions):raise ValueError('Incomplete original Eagle dimension coverage')
    wires={layer:[w.attrib for w in root.findall('.//board/plain/wire') if w.attrib['layer']==layer]
           for layer in ('41','42')}
    coordinates={tuple(sorted(((float(w['x1']),-float(w['y1'])),(float(w['x2']),-float(w['y2'])))))
                 for group in wires.values() for w in group}
    repaired=[]
    def replace(match):
        row=match.group()
        if '(layer "UNDEFINED")' not in row:
            return row
        endpoints=[tuple(map(float,re.search(r'\('+k+r' ([^ ]+) ([^)]+)\)',row).groups()))
                   for k in ('start','end')]
        if tuple(sorted(endpoints)) not in coordinates:
            raise ValueError('Undefined layer object has no exact source restrict-wire match')
        repaired.append(endpoints)
        return row.replace('(layer "UNDEFINED")','(layer "Cmts.User")')
    text=re.sub(r'\t\(gr_line\n.*?\n\t\)',replace,text,flags=re.S)
    if '"UNDEFINED"' in text:
        raise ValueError('Unresolved undefined source layer remains')
    zones=[]; evidence=[]
    for layer,items in wires.items():
        if any(float(w.get('curve','0')) != 0 for w in items):
            raise ValueError('Curved restrict wires need explicit source conversion')
        lines=[LineString([(float(w['x1']),-float(w['y1'])),(float(w['x2']),-float(w['y2']))]) for w in items]
        closed=list(polygonize(unary_union(lines)))
        if not closed:
            raise ValueError('No source-backed closed restrict contour')
        # Retain the original stroke extent as well as the enclosed restrict
        # regions. Dangling wires therefore remain copper-exclusion geometry.
        shape=unary_union([*closed,*[line.buffer(float(w['width'])/2,cap_style='square',join_style='mitre')
                                    for line,w in zip(lines,items) if float(w['width'])>0]])
        polygons=list(shape.geoms) if shape.geom_type=='MultiPolygon' else [shape]
        for polygon in polygons:
            if polygon.interiors:
                raise ValueError('Restricted polygon holes require explicit conversion')
            coords=list(polygon.exterior.coords)[:-1]
            pts=' '.join('(xy '+format(x,'.9f')+' '+format(y,'.9f')+')' for x,y in coords)
            uid=str(uuid.uuid5(uuid.NAMESPACE_URL,'arduino-restrict:'+layer+':'+repr(coords)))
            zones.append('(zone (net 0) (net_name "") (layer "'+('F.Cu' if layer=='41' else 'B.Cu')+
                '") (uuid "'+uid+'") (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.0254) '
                '(keepout (tracks allowed) (vias allowed) (pads allowed) (copperpour not_allowed) '
                '(footprints allowed)) (polygon (pts '+pts+')))')
        evidence.append({'source_eagle_layer':layer,'source_wires':len(items),
                         'closed_regions':len(closed),'rule_regions':len(polygons),'area_mm2':shape.area})
    end=text.rfind(')')
    destination.write_text(text[:end]+'\n'+'\n'.join(zones)+'\n'+text[end:],encoding='utf-8')
    return {'converted_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'original_eagle_sha256':hashlib.sha256(eagle.read_bytes()).hexdigest(),
            'repaired_undefined_lines':len(repaired),'restrictions':evidence,
            'outline_source_check':{'eagle_dimension_edges':len(dimensions),'converted_edge_instances':outline_instances,
                'unique_exact_endpoint_matches':len(outline),'arc_midpoint_tolerance_mm':1e-6},
            'interpretation':'Closed restrict contours plus finite-width restrict strokes; source lines retained on Cmts.User.'}


def stack_for(name):
    thickness=1.656 if name=='uno' else 1.57
    return {'layers':[{'id':'top-surface','z_min_mm':0.,'z_max_mm':.035,'material_id':'air'},
        {'id':'core','z_min_mm':.035,'z_max_mm':thickness-.035,'material_id':'fr4'},
        {'id':'bottom-surface','z_min_mm':thickness-.035,'z_max_mm':thickness,'material_id':'air'}],
        'copper_layer_spans':{'F.Cu':[0.,.035],'B.Cu':[thickness-.035,thickness]},
        'copper_material_id':'copper','air_material_id':'air','plated_hole_wall_mm':.025,
        'provenance':('UNO total 1.656 mm from converted source; 35 um copper and 25 um plating are study assumptions.'
            if name=='uno' else 'Shield Eagle declares 35 um copper, 1.5 mm dielectric; 25 um plating is a study assumption.')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kicad-python',type=Path,default=Path('C:/Program Files/KiCad/10.0/bin/python.exe'))
    parser.add_argument('--mesh',action='store_true',help='Attempt bounded native OCC meshing after source admission')
    parser.add_argument('--planar-mesh',action='store_true',help='Generate full source-contour EM material prism meshes')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    source=ROOT/'build/curated-multiboard-20261005/arduino'
    summary={'contract':'spike/arduino-em-preparation/v1','status':'preparing','solver_executed':False,
             'production_qualified':False,'boards':{},'blockers':[]}
    derivative=args.output/'shield-source.kicad_pcb'
    try:
        write(args.output/'shield-repair.json',repair_shield(source/'converted/shield.kicad_pcb',
            source/'sources/shield/A000110-cad-files/4RelaysShieldV2.0.brd',derivative))
    except ValueError as error:
        summary['blockers'].append({'board':'shield','stage':'source_repair','message':str(error)})
    for name in ('uno','shield'):
        path=source/'converted/uno.kicad_pcb' if name=='uno' else derivative
        if not path.exists(): continue
        directory=args.output/name
        try:
            result=subprocess.run([str(args.kicad_python),str(ROOT/'scripts/extract_arduino_em_copper.py'),
                '--source',str(path.resolve()),'--output',str(directory.resolve())],capture_output=True,
                text=True,timeout=240)
            (args.output/(name+'-extraction.log')).write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
            if result.returncode:
                raise ValueError('Native extraction failed; inspect '+name+'-extraction.log')
            snapshot=json.loads((directory/'polygons.json').read_text(encoding='utf-8'))
            drc=json.loads((directory/'drc.json').read_text(encoding='utf-8'))
            summary['boards'][name]={'copper_objects':len(snapshot['copper']),'drills':len(snapshot['drills']),
                'pads':len(snapshot['pads']),'source_sha256':snapshot['source_sha256'],
                'drc_counts':dict(Counter(item['type'] for item in drc['violations']))}
            stack=stack_for(name); write(directory/'study-stack.json',stack)
            prepared=prepare_routed_board_volume(snapshot,stack)
            write(directory/'prepared-volume.json',prepared)
            if args.planar_mesh:
                from python.spike_core.assembly_em_planar_mesher import mesh_material_prisms
                generated=mesh_material_prisms(prepared['job'],max_cells=600000,max_vertices=200000)
                write(directory/'planar-volume-mesh.json',generated)
            if args.mesh:
                from python.spike_core.gmsh_occ_runtime import run_occ_case
                generated=run_occ_case(prepared['job'],directory/'occ-mesh',timeout_s=180,memory_limit_mb=2048)
                write(directory/'volume-mesh.json',generated)
        except (ValueError,RuntimeError,subprocess.TimeoutExpired) as error:
            summary['blockers'].append({'board':name,'stage':'geometry_admission','message':str(error)})
    summary['status']='blocked' if summary['blockers'] else 'board_volumes_prepared'
    summary['remaining_assembly_inputs']=['Retained conductive enclosure material assignment and geometry',
        'Explicit connector solids joining mapped board pads and conductor-face excitation',
        'Complete assembly EM admission and actual solver execution']
    write(args.output/'preparation.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
