# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Build and optionally execute the full retained Arduino copper study.

Uses prepared native derivative snapshots and the original planar meshes.
Connector dimensions/materials are explicitly specified study assumptions.
"""
from __future__ import annotations
import argparse
import copy
from collections import Counter
import itertools
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.spider_v2 import AssemblyIRV1


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path,value): path.write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8')


def rectangular_conductor(center,width,zmin,zmax):
    """Original six-tetra rectangular conductor; consistent sorted diagonal."""
    vertices=[[center[0]+(i-.5)*width,center[1]+(j-.5)*width,zmin+k*(zmax-zmin)]
              for i in range(2) for j in range(2) for k in range(2)]
    cells=[]; incidence={}
    for permutation in itertools.permutations(range(3)):
        p=[0,0,0];ids=[0]
        for axis in permutation:
            p[axis]+=1;ids.append(p[0]*4+p[1]*2+p[2])
        xyz=np.array([vertices[i] for i in ids])
        if np.linalg.det((xyz[1:]-xyz[0]).T)<0:ids[1],ids[2]=ids[2],ids[1]
        cells.append({'id':str(len(cells)),'kind':'tetrahedron','vertices':ids,
                      'material_id':'copper','source_object_ids':['idealized-pin']})
        for f in itertools.combinations(ids,3):
            key=tuple(sorted(f));incidence[key]=incidence.get(key,0)+1
    mesh={'contract':'spike/solver-mesh/v1','units':'mm','coordinate_system':'right_handed_xyz',
          'vertices':vertices,'cells':cells,'counts':{'vertices':8,'cells':6},
          'object_map':{'idealized-pin':{'kind':'specified_connector_conductor'}}}
    return {'mesh':mesh,'boundary_faces':[{'id':str(i),'vertices':list(f)}
            for i,(f,n) in enumerate(incidence.items()) if n==1],'material_map':{'copper':'copper'}}


def contact_area(job,pad,z,width):
    """Independent terminal-plane overlap against the admitted source job."""
    from shapely.geometry import Polygon,box
    from shapely.ops import unary_union
    x,y=pad['center_mm'];terminal=box(x-width/2,y-width/2,x+width/2,y+width/2)
    selected=[];other=[];holes=[]
    for solid in job['solids']:
        shape=solid['shape']
        if not shape['z_min_mm']<=z<=shape['z_max_mm']:continue
        polygon=Polygon(shape['outer_mm'],shape['holes_mm'])
        if not polygon.intersects(terminal):continue
        if solid['priority']==20:holes.append(polygon)
        elif solid['material_id']=='copper':
            net=job['object_metadata'][solid['id']].get('net')
            (selected if net==pad['net'] else other).append(polygon)
    contact=terminal.intersection(unary_union(selected)).difference(unary_union(holes))
    stray=terminal.intersection(unary_union(other)).difference(unary_union(holes))
    if contact.area<=0 or stray.area>1e-10:raise ValueError('Idealized connector fails source-net terminal contact check')
    return contact.area


def build(prepared):
    source=ROOT/'output/enclosed-assembly-20261010'
    assembly=read(source/'electrical/assembly.json')
    mappings=copy.deepcopy(assembly['connector_mappings'])
    # Actual idealized conductor occurrences below implement all three mapped
    # mates. Preserve source graph as evidence; it is not a second implied wire.
    assembly['connector_mappings']=[]
    assembly['metadata']['em_study_source_connector_mappings']=mappings
    assembly['name']='Arduino complete routed copper: specified enclosure/header EM study'
    bodies=[];snapshots={};jobs={};board_evidence={}
    for name,oid in [('uno','uno-r4-minima'),('shield','relay-shield')]:
        volume=read(prepared/name/'planar-volume-mesh.json')
        evidence=read(prepared/name/'prepared-volume.json')
        jobs[name]=evidence['job']
        snapshots[name]=read(prepared/name/'polygons.json')
        board_evidence[name]={'copper_objects':len(snapshots[name]['copper']),
            'drills':len(snapshots[name]['drills']),'pads':len(snapshots[name]['pads']),
            'mesh_counts':volume['mesh']['counts'],
            'native_drc_counts':dict(Counter(v['type'] for v in read(prepared/name/'drc.json')['violations'])),
            'native_drc_limit':'Converted project net-class fidelity is incomplete; findings are retained and not waived.',
            'stack':read(prepared/name/'study-stack.json')}
        occurrence=next(v for v in assembly['boards'] if v['id']==oid)
        bodies.append({'occurrence_id':oid,'reference_id':occurrence['design_id'],
            'source_sha256':snapshots[name]['filled_source_sha256'],
            'stack_binding':evidence['stack_binding'],
            **{key:volume[key] for key in ('mesh','boundary_faces','material_map')}})
    enclosure=read(source/'em/assembly-field-em-request.json')
    bodies.append(next(v for v in enclosure['bodies'] if v['occurrence_id']=='enclosure'))
    assembly['parts'].append(next(v for v in enclosure['assembly']['parts'] if v['id']=='enclosure'))
    connector_evidence=[];pin_bodies={}
    for pin,uno_ref,shield_ref,number in [('5v','JANALOG','POWER0','5'),('gnd','JANALOG','POWER0','6'),('d5','JDIGITAL','JLOW0','6')]:
        a=next(v for v in snapshots['uno']['pads'] if v['reference']==uno_ref and v['number']==number)
        b=next(v for v in snapshots['shield']['pads'] if v['reference']==shield_ref and v['number']==number)
        center=a['center_mm']; mapped=[b['center_mm'][0]+114.2111,b['center_mm'][1]+131.6736]
        if max(abs(x-y) for x,y in zip(center,mapped))>1e-9:raise ValueError('Mapped connector pad centers do not align')
        oid='study-header-'+pin;rid='specified-1p2mm-square-header-'+pin
        geometry=rectangular_conductor(center,1.2,1.656,11.)
        body={'occurrence_id':oid,'reference_id':rid,'source_sha256':canonical_json_digest(geometry),**geometry}
        bodies.append(body);pin_bodies[pin]=body
        assembly['parts'].append({'id':oid,'name':'Specified idealized header '+pin,'model_id':rid,
            'part_type':'connector','frame':{'frame_id':oid+'-frame'}})
        connector_evidence.append({'occurrence_id':oid,'source_mapped_pads':[a,b],
            'width_mm':1.2,'z_span_mm':[1.656,11.],
            'verified_terminal_contact_area_mm2':{'uno':contact_area(jobs['uno'],a,1.656,1.2),
                'shield':contact_area(jobs['shield'],b,0.,1.2)},
            'provenance':'Explicit idealized square contact column between board copper surfaces; not manufacturer connector geometry.'})
    from extensions.openems_suite.retained_volume_geometry import _inside_triangle
    # A line lumped port completely inside the inter-pin air gap. Native grid
    # checks decide representability; no transverse solid is fabricated.
    y=129.2336;z=5.0
    start=[(154.8511-.6)*.001,y*.001,z*.001]
    stop=[(152.3111+.6)*.001,y*.001,z*.001]
    def endpoint(pin,point):
        body=pin_bodies[pin]
        for face in body['boundary_faces']:
            triangle=[[x*.001 for x in body['mesh']['vertices'][i]] for i in face['vertices']]
            if _inside_triangle(point,triangle):return {'occurrence_id':body['occurrence_id'],'face_id':face['id']}
        raise ValueError('No explicit conductor face contains port endpoint')
    materials=[{'id':mid,'conductivity_s_m':sigma,'relative_permittivity':epsilon,'relative_permeability':1.,
                'provenance':provenance} for mid,sigma,epsilon,provenance in [
        ('copper',5.8e7,1.,'Study: homogeneous copper, 5.8e7 S/m, mu_r=1.'),
        ('aluminium',3.5e7,1.,'Study: homogeneous enclosure aluminium, 3.5e7 S/m, mu_r=1.'),
        ('fr4',0.,4.2,'Study: lossless homogeneous FR4 epsilon_r=4.2, mu_r=1; no manufacturer dielectric data asserted.'),
        ('air',0.,1.,'Study: vacuum-equivalent air epsilon_r=mu_r=1, sigma=0.')]]
    geometry={'contract':'spike/assembly-field-handoff-request/v1','domain':'em','resource_profile':'routed_pcb_em_v1',
        'assembly':AssemblyIRV1.from_dict(assembly).to_dict(),'bodies':bodies,'materials':materials,
        'ports':[{'id':'power-header','signal':endpoint('5v',stop),'return':endpoint('gnd',start),'reference_impedance_ohm':50.}]}
    request={'contract':'spike/assembly-em-request/v1','geometry':geometry,
        'ports':[{'id':'power-header','start_m':start,'stop_m':stop,'direction':'x','excite':True}],
        'settings':{'frequency_hz':[5e8,1e9,1.5e9],'mesh_resolution_m':.001,'air_margin_m':.006,
                    'mesh_policy':'cartesian_sampling_v1',
                    'max_timesteps':20000,'end_criteria':1e-6,'timeout_s':600,'threads':2}}
    evidence={'connector_geometry':connector_evidence,'source_connector_mappings':mappings,'board_evidence':board_evidence,
        'omissions':['Unmapped connector pins and connector housings; packaged component solids and lumped device electrical models.',
                     'Soldermask, dielectric loss/dispersion, conductor roughness, contact resistance and manufacturing tolerances.'],
        'grid_policy':'Explicit cartesian_sampling_v1: retain all polyhedra, material Z extrema and port terminals; sample XY at 1 mm target.',
        'sampling_limitations':['Many narrow traces, via holes and copper gaps are unresolved in XY; connectivity and impedance can change under FDTD rasterization.',
            'This bounded full-geometry execution is a diagnostic, not an Arduino accuracy or convergence qualification.'],
        'model_status':'unvalidated','production_qualified':False}
    return request,evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();request,evidence=build(args.prepared)
    write(args.output/'request.json',request);write(args.output/'geometry-evidence.json',evidence)
    write(args.output/'assembly.json',request['geometry']['assembly'])
    write(args.output/'study.json',{'contract':'spike/assembly-em-study/v1','request':request,'result':None})
    print(json.dumps({'request_path':str((args.output/'request.json').resolve()),'bytes':(args.output/'request.json').stat().st_size,'build_seconds':time.monotonic()-started}),flush=True)
    if args.run:
        from python.spike_core.assembly_em import run_assembly_em
        result=run_assembly_em(request,args.output/'run')
        write(args.output/'study.json',{'contract':'spike/assembly-em-study/v1','request':request,'result':result})
        print(json.dumps({'status':result.get('status'),'solver_executed':result.get('solver_executed')}),flush=True)


if __name__=='__main__':main()
