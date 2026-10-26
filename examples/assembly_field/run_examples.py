# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original one-metre slab oracles, not imported/qualified PCB geometry."""
import copy
import itertools
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.solvers.execution.coupling.assembly_field_handoff import prepare_assembly_field_handoff
from python.spike_core.solvers.execution.coupling.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from python.spike_core.solvers.execution.coupling.assembly_field_thermal import run_assembly_field_thermal
from python.spike_core.solvers.thermal_fluid.heat.assembly_view_factors import derive_assembly_view_factors
from python.spike_core.solvers.geometry_meshing.preparation.tetra_mesh_refinement import refine_tetra_mesh
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.spider_v2 import AssemblyIRV1


def mesh_fixture(refined=False):
    vertices = [list(p) for p in itertools.product((0., 1.), repeat=3)]
    index = {tuple(p): i for i, p in enumerate(vertices)}
    cells = []
    for axes in itertools.permutations(range(3)):
        p, nodes = [0,0,0], [0]
        for axis in axes:
            p[axis] = 1
            nodes.append(index[tuple(p)])
        xyz = np.array([vertices[v] for v in nodes])
        if np.linalg.det((xyz[1:]-xyz[0]).T) < 0:
            nodes[1], nodes[2] = nodes[2], nodes[1]
        cells.append({'id':str(len(cells)), 'kind':'tetrahedron', 'vertices':nodes,
                      'material_id':'bulk', 'source_object_ids':['original-solid']})
    mesh = {'contract':'spike/solver-mesh/v1', 'units':'m', 'coordinate_system':'right_handed_xyz',
            'vertices':vertices, 'cells':cells, 'counts':{'vertices':8,'cells':6},
            'object_map':{'original-solid':{'kind':'solid'}}}
    counts = {}
    for cell in cells:
        for face in itertools.combinations(cell['vertices'],3):
            key = tuple(sorted(face))
            counts[key] = counts.get(key,0)+1
    boundary = [{'vertices':list(f), 'label':'face-'+str(i)} for i,(f,count) in enumerate(counts.items()) if count == 1]
    if refined:
        candidate = refine_tetra_mesh(mesh, [[0,4]], boundary)
        mesh, boundary = candidate['mesh'], candidate['boundary_triangles']
    return mesh, [{'id':'face-'+str(i), 'vertices':f['vertices']} for i,f in enumerate(boundary)]


def setup(refined=False):
    mesh, faces = mesh_fixture(refined)
    raw = {'assembly_id':'original-field-example', 'name':'Board case exact slab',
           'boards':[{'id':'board', 'design_id':'original-board', 'frame':{'frame_id':'board-frame'}}],
           'parts':[{'id':'case', 'model_id':'original-case', 'part_type':'enclosure',
                     'frame':{'frame_id':'case-frame','transform':[1,0,0,1000,0,1,0,0,0,0,1,0,0,0,0,1]}}],
           'thermal_contacts':[{'id':'contact', 'endpoint_a':'board','endpoint_b':'case',
                                'contact_area_mm2':1e6,'thermal_resistance_k_per_w':.25}]}
    assembly = AssemblyIRV1.from_dict(raw).to_dict()
    bodies = []
    for oid,reference in [('board','original-board'),('case','original-case')]:
        body = {'occurrence_id':oid, 'reference_id':reference, 'source_sha256':canonical_json_digest([reference,'original-parametric-slab']),
                'mesh':copy.deepcopy(mesh), 'boundary_faces':copy.deepcopy(faces), 'material_map':{'bulk':'k'}}
        if oid == 'board':
            body['stack_binding'] = {'id':'original-homogeneous-stack','source_sha256':canonical_json_digest(['homogeneous',2])}
        bodies.append(body)
    request = {'contract':'spike/assembly-field-handoff-request/v1','assembly':assembly,'domain':'thermal',
               'bodies':bodies,'materials':[{'id':'k','thermal_conductivity_w_mk':2,'provenance':'Original analytical slab'}]}
    problem = {'contract':'spike/assembly-field-thermal-problem/v1','boundaries':[],'contacts':[],'heat_sources':[]}
    endpoint = lambda oid,f: {'occurrence_id':oid,'face_id':f['id']}
    for oid,x,t in [('board',0,300),('case',1,400)]:
        for f in faces:
            if all(mesh['vertices'][v][0] == x for v in f['vertices']):
                problem['boundaries'].append({'face':endpoint(oid,f),'type':'temperature','temperature_k':t})
    pairs = []
    for left in faces:
        points = [mesh['vertices'][v] for v in left['vertices']]
        if all(p[0] == 1 for p in points):
            positions = {(0,p[1],p[2]) for p in points}
            right = next(f for f in faces if {tuple(mesh['vertices'][v]) for v in f['vertices']} == positions)
            pairs.append({'left':endpoint('board',left),'right':endpoint('case',right)})
    problem['contacts'] = [{'contact_id':'contact','face_pairs':pairs,'thermal_contact_conductance_w_m2k':4}]
    return request,problem


def run_examples():
    summaries = []
    for refined in (False,True):
        request, problem = setup(refined)
        result = run_assembly_field_thermal(request, problem)
        assert abs(result['occurrence_temperatures']['board']['maximum_k']-340) < 1e-7
        assert abs(result['occurrence_temperatures']['case']['minimum_k']-360) < 1e-7
        assert abs(sum(c['left_to_right_heat_w'] for c in result['field_result']['contacts'])+80) < 1e-7
        assert abs(result['field_result']['heat_balance']['imbalance_w']) < 1e-8
        record = export_assembly_field_study(request, problem, result)
        import_assembly_field_study(json.loads(json.dumps(record)), current_request=request, current_problem=problem)
        summaries.append({'case':'locally-refined' if refined else 'base', 'request_digest':result['request_digest'],
                          'result_digest':result['result_digest'],'temperatures':result['occurrence_temperatures'],
                          'heat_balance':result['field_result']['heat_balance'],'resources':result['field_result']['resources']})
    em = copy.deepcopy(request)
    em['domain'] = 'em'
    em['materials'] = [{'id':'k','conductivity_s_m':5.8e7,'relative_permittivity':1,'relative_permeability':1,'provenance':'Original idealized conductor'}]
    em['ports'] = [{'id':'feed','signal':{'occurrence_id':'board','face_id':faces_id(em,0)},
                    'return':{'occurrence_id':'case','face_id':faces_id(em,1)},'reference_impedance_ohm':50}]
    handoff = prepare_assembly_field_handoff(em)
    assert not handoff['ports'][0]['executable']
    square = [[[0,0,0],[1,0,0],[1,1,0]],[[0,0,0],[1,1,0],[0,1,0]]]
    opposing = [[[x,y,1] for x,y,_ in reversed(t)] for t in square]
    view = derive_assembly_view_factors({'contract':'spike/assembly-view-factor-request/v1','units':'m',
             'surfaces':[{'id':'bottom','triangles':square},{'id':'top','triangles':opposing}],
             'quadrature':{'level':5,'max_pair_evaluations':10000000,'max_visibility_tests':50000000,'max_geometry_pairs':32768}})
    assert abs(view['view_factors'][0][1]-.199824895698) < 4e-5
    return {'thermal_examples':summaries,'em_handoff_issues':handoff['execution_issues'],
            'view_factor':view['view_factors'][0][1],'view_factor_error_bound':view['error_bound']}


def faces_id(request,index):
    return request['bodies'][index]['boundary_faces'][0]['id']


if __name__ == '__main__':
    print(json.dumps(run_examples(),indent=2,allow_nan=False))
