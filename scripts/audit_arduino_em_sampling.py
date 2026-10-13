# SPDX-License-Identifier: Apache-2.0
"""Attach observed native diagnostics and independently audit unsampled volumes."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from python.spike_core.assembly_em_diagnostics import native_material_sampling


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--study-dir',type=Path,required=True)
    ap.add_argument('--prepared',type=Path,required=True)
    ap.add_argument('--attach-diagnostics',action='store_true',help='Attach observed log diagnostics to the study result')
    args=ap.parse_args();p=args.study_dir
    study=read(p/'study.json');compiled=read(p/'compiled.json');result=study['result']
    if compiled['compiled_digest']!=result['compiled_digest']:raise ValueError('Compiled identity does not match native result')
    log=(p/'run/solver.log').read_text(encoding='utf-8',errors='replace')
    sampling=native_material_sampling(log,compiled)
    result['material_sampling']=sampling
    with (p/'run/solver.log').open('rb') as stream:result['artifact_sha256']['solver.log']=hashlib.file_digest(stream,'sha256').hexdigest()
    cap='Max. number of timesteps was reached before the end-criteria' in log
    result['termination']={'timestep_limit_detected':cap,'did_reach_end_criteria':False if cap else None,
        'evidence':'Native solver log timestep-limit warning' if cap else 'No structured decay measurement; inspect native log'}
    limitations=[f"Native grid did not sample {sampling['unused_conductive_primitive_count']} conductive and {sampling['unused_nonconductive_primitive_count']} nonconductive polyhedra; this run is not an accuracy-qualified board result."]
    if cap:limitations.append('Native solver reached timestep limit before requested energy decay; execution is complete but decay convergence failed.')
    for limitation in limitations:
        if limitation not in result['limitations']:result['limitations'].append(limitation)
    # Attach factual post-run log diagnostics without changing native results,
    # geometry, fields, response, trusted worker hash or compiled identity.
    if args.attach_diagnostics:
        write(p/'study.json',study);write(p/'result-with-diagnostics.json',result)
    trace={t['occurrence_id']:t for t in compiled['source_traceability']}
    volumes={}
    for body in study['request']['geometry']['bodies']:
        mesh=body['mesh'];points=np.asarray(mesh['vertices']);cells=mesh['cells']
        tets=points[np.asarray([c['vertices'] for c in cells])]
        values=np.linalg.det(np.transpose(tets[:,1:]-tets[:,0,None],(0,2,1)))/6
        if mesh['units']=='m':values*=1e9
        if not np.all(values>0):raise ValueError('Nonpositive source tetrahedron')
        mapping=trace[body['occurrence_id']]['cell_map']
        volumes.update((mapping[c['id']],float(v)) for c,v in zip(cells,values))
    unused={v['primitive_index'] for v in sampling['unresolved_primitives']}
    by_owner=defaultdict(lambda:{'total_conductive_volume_mm3':0.,'unused_conductive_volume_mm3':0.,'total_count':0,'unused_count':0})
    records=[];maximum_relative_error=0.;absolute_error=0.
    for index,primitive in enumerate(compiled['primitives']):
        if primitive['material']['conductivity_s_m']<=0:continue
        vertices=np.asarray(primitive['vertices_m'])*1000
        triangles=(vertices-vertices[0])[np.asarray(primitive['faces'])]
        terms=np.einsum('ij,ij->i',triangles[:,0],np.cross(triangles[:,1],triangles[:,2]))/6
        surface=math.fsum(map(float,terms));tetra=math.fsum(volumes[v] for v in primitive['cell_ids'])
        error=abs(surface-tetra);bound=64*np.finfo(float).eps*float(np.abs(terms).sum())+tetra*1e-6
        if not (surface>0 and error<=bound):raise ValueError('Signed surface/tetra volume certificate failed')
        maximum_relative_error=max(maximum_relative_error,error/tetra);absolute_error+=error
        owner=primitive['occurrence_id'];totals=by_owner[owner];totals['total_count']+=1;totals['total_conductive_volume_mm3']+=tetra
        if index in unused:
            totals['unused_count']+=1;totals['unused_conductive_volume_mm3']+=tetra
            reverse={v:k for k,v in trace[owner]['source_map'].items()}
            records.append({'primitive_index':index,'occurrence_id':owner,'volume_mm3':tetra,
                'signed_surface_volume_mm3':surface,'bbox_dimensions_mm':np.ptp(vertices,axis=0).tolist(),
                'source_region_ids':[reverse[v] for v in primitive['source_object_ids']]})
    for values in by_owner.values():values['unused_volume_percent']=100*values['unused_conductive_volume_mm3']/values['total_conductive_volume_mm3']
    top=sorted(records,key=lambda v:v['volume_mm3'],reverse=True)[:20]
    for name,oid in [('uno','uno-r4-minima'),('shield','relay-shield')]:
        generated=read(args.prepared/name/'planar-volume-mesh.json');regions={r['region_id']:r for r in generated['region_traceability']};del generated
        prepared=read(args.prepared/name/'prepared-volume.json');metadata=prepared['job']['object_metadata']
        solids={s['id']:s for s in prepared['job']['solids']}
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        matrix=np.asarray(trace[oid]['world_transform_mm']).reshape(4,4)
        for item in top:
            if item['occurrence_id']!=oid:continue
            ids=sorted({sid for rid in item['source_region_ids'] for sid in regions[rid]['candidate_source_ids']})
            primitive=compiled['primitives'][item['primitive_index']]
            local=(np.asarray(primitive['vertices_m'])*1000-matrix[:3,3])@matrix[:3,:3]
            footprint=unary_union([Polygon(local[face,:2]) for face in primitive['faces'] if Polygon(local[face,:2]).area>1e-14])
            # Region traceability intentionally names a priority group. Refine
            # these candidates by positive area on this actual component.
            ids=[sid for sid in ids if Polygon(solids[sid]['shape']['outer_mm'],solids[sid]['shape']['holes_mm']).intersection(footprint).area>1e-12]
            item['candidate_construction_sources']=[{'id':sid,**metadata[sid]} for sid in ids]
    summary={'contract':'spike/arduino-em-sampling-audit/v1','compiled_digest':compiled['compiled_digest'],
        'native_unused_counts':{'conductive':sampling['unused_conductive_primitive_count'],'nonconductive':sampling['unused_nonconductive_primitive_count']},
        'volume_certificate':{'method':'Shifted signed closed-surface volume against independent positive source-tetra determinant sum',
            'maximum_relative_difference':maximum_relative_error,'summed_absolute_difference_mm3':absolute_error,
            'relative_bound':1e-6,'bound_reason':'EM rigid-placement certificate plus64epsilon absolute determinant summation bound'},
        'by_occurrence':dict(by_owner),'unused_conductive_volume_bins':[],
        'minimum_unused_bbox_dimensions_mm':[min(v['bbox_dimensions_mm'][axis] for v in records) for axis in range(3)],
        'largest_unused_conductors':top,'all_unused_conductors':records,
        'limitations':['Unused warning counts do not measure error in sampled conductors.',
            'Small total volume does not imply negligible circuit or field impact; topology matters.',
            'Candidate construction sources identify region provenance groups, not exact per-triangle native primitive ownership.']}
    for low,high in [(0.,1e-9),(1e-9,1e-6),(1e-6,.001),(.001,float('inf'))]:
        group=[r for r in records if low<=r['volume_mm3']<high]
        summary['unused_conductive_volume_bins'].append({'minimum_mm3':low,'maximum_mm3':None if math.isinf(high) else high,
            'count':len(group),'volume_mm3':sum(v['volume_mm3'] for v in group)})
    write(p/'sampling-volume-audit.json',summary)
    print(json.dumps({key:summary[key] for key in ('by_occurrence','volume_certificate','unused_conductive_volume_bins')}),flush=True)


if __name__=='__main__':main()
