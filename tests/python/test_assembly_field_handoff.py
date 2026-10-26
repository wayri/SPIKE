# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original retained-volume ownership, thermal and offline lifecycle oracles."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

import numpy as np
from python.spike_core.solvers.execution.coupling.assembly_field_handoff import prepare_assembly_field_handoff
from python.spike_core.solvers.execution.coupling.assembly_field_thermal import run_assembly_field_thermal, verify_assembly_field_result
from python.spike_core.solvers.execution.coupling.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from python.spike_core.service_assembly_field import handle_assembly_field_request
from tests.python.test_assembly_tetra_thermal import cube, exterior


def fixture():
    assembly = {'contract': 'spike/assembly-ir/v1', 'assembly_id': 'field-assembly', 'name': 'Original slab fixture',
                'boards': [{'id': 'board', 'design_id': 'board-design', 'frame': {'frame_id': 'board-frame'}}],
                'parts': [{'id': 'case', 'model_id': 'case-source', 'part_type': 'enclosure',
                           'frame': {'frame_id': 'case-frame', 'transform': [1,0,0,1000,0,1,0,0,0,0,1,0,0,0,0,1]}}],
                'thermal_contacts': [{'id': 'interface', 'endpoint_a': 'board', 'endpoint_b': 'case'}]}
    bodies = []
    for oid, reference in [('board', 'board-design'), ('case', 'case-source')]:
        mesh = cube(owner='shared-source')
        bodies.append({'occurrence_id': oid, 'reference_id': reference, 'source_sha256': 'a'*64,
                       'mesh': mesh, 'boundary_faces': [{'id': str(i), 'vertices': f} for i, f in enumerate(exterior(mesh))],
                       'material_map': {'k': 'slab'}, **({'stack_binding': {'id': 'fixture-stack', 'source_sha256': 'b'*64}} if oid == 'board' else {})})
    request = {'contract': 'spike/assembly-field-handoff-request/v1', 'assembly': assembly, 'domain': 'thermal',
               'bodies': bodies, 'materials': [{'id': 'slab', 'thermal_conductivity_w_mk': 2, 'provenance': 'Original exact slab oracle'}]}
    problem = {'contract': 'spike/assembly-field-thermal-problem/v1', 'boundaries': [], 'heat_sources': [], 'contacts': []}

    def endpoint(body, f):
        return {'occurrence_id': body['occurrence_id'], 'face_id': f['id']}

    for body, side, temperature in [(bodies[0], 0, 300), (bodies[1], 1, 400)]:
        for f in body['boundary_faces']:
            if all(body['mesh']['vertices'][v][0] == side for v in f['vertices']):
                problem['boundaries'].append({'face': endpoint(body, f), 'type': 'temperature', 'temperature_k': temperature})
    pairs = []
    for left in bodies[0]['boundary_faces']:
        points = [bodies[0]['mesh']['vertices'][v] for v in left['vertices']]
        if not all(p[0] == 1 for p in points):
            continue
        projected = {tuple([p[0]-1, p[1], p[2]]) for p in points}
        right = next(f for f in bodies[1]['boundary_faces'] if {tuple(bodies[1]['mesh']['vertices'][v]) for v in f['vertices']} == projected)
        pairs.append({'left': endpoint(bodies[0], left), 'right': endpoint(bodies[1], right)})
    problem['contacts'] = [{'contact_id': 'interface', 'face_pairs': pairs, 'thermal_contact_conductance_w_m2k': 4}]
    return request, problem


class AssemblyFieldHandoffTests(unittest.TestCase):
    def test_namespaces_occurrences_without_welding_or_guessing(self):
        request, _ = fixture()
        before = copy.deepcopy(request)
        result = prepare_assembly_field_handoff(request)
        self.assertEqual(request, before)
        self.assertEqual(result['mesh']['counts'], {'cells': 12, 'vertices': 16})
        self.assertEqual({t['occurrence_id'] for t in result['source_traceability']}, {'board', 'case'})
        self.assertTrue(all(set(m) <= {'kind','net','layer'} for m in result['mesh']['object_map'].values()))
        self.assertEqual(len(set(c['id'] for c in result['mesh']['cells'])), 12)
        self.assertEqual(len(result['materials']), 2)
        self.assertEqual(result['source_traceability'][1]['world_transform_mm'][3], 1000)
        self.assertFalse(result['production_qualified'])

    def test_exact_contact_temperature_flux_and_conservation(self):
        request, problem = fixture()
        result = run_assembly_field_thermal(request, problem)
        # R_bulk=1/2+1/2 K/W, R_contact=1/4 K/W, so Q=100/1.25=80 W.
        self.assertAlmostEqual(result['occurrence_temperatures']['board']['maximum_k'], 340, places=8)
        self.assertAlmostEqual(result['occurrence_temperatures']['case']['minimum_k'], 360, places=8)
        field = result['field_result']
        self.assertAlmostEqual(sum(c['left_to_right_heat_w'] for c in field['contacts']), -80, places=8)
        np.testing.assert_allclose([v['heat_flux_w_m2'] for v in field['cell_heat_flux_w_m2']], np.tile([-80, 0, 0], (12, 1)), atol=1e-8)
        self.assertLess(abs(field['heat_balance']['imbalance_w']), 1e-8)
        self.assertTrue(result['adiabatic_face_ids'])
        self.assertEqual(verify_assembly_field_result(request, problem, result), result)

    def test_anisotropy_rotates_once_in_nested_frames(self):
        request, _ = fixture()
        request['materials'][0]['thermal_conductivity_w_mk'] = [[2,0,0],[0,3,0],[0,0,4]]
        request['assembly']['parts'].append({'id': 'group', 'part_type': 'subassembly',
                                           'frame': {'frame_id': 'group-frame', 'transform': [0,-1,0,0,1,0,0,0,0,0,1,0,0,0,0,1]}})
        request['assembly']['parts'][0]['frame']['parent_frame_id'] = 'group-frame'
        result = prepare_assembly_field_handoff(request)
        np.testing.assert_allclose(result['materials'][1]['thermal_conductivity_w_mk'], np.diag([3,2,4]))
        self.assertEqual(result['excluded_hierarchy'][0]['id'], 'group')

    def test_coverage_hashes_frames_overlaps_and_fields_reject(self):
        mutations = [lambda r: r['bodies'].pop(), lambda r: r['bodies'][0].update(reference_id='wrong'),
                     lambda r: r['bodies'][0].update(source_sha256='broken'),
                     lambda r: r['bodies'][0].pop('stack_binding'), lambda r: r.update(extra=1),
                     lambda r: r['assembly']['parts'][0]['frame']['transform'].__setitem__(3, 500),
                     lambda r: r['assembly']['parts'][0]['frame']['transform'].__setitem__(0, True),
                     lambda r: r['assembly'].update(frame={'frame_id': 'assembly', 'transform': [1,0,0,1,0,1,0,0,0,0,1,0,0,0,0,1]}),
                     lambda r: r['bodies'][0]['mesh']['object_map'].update(unused={'kind': 'solid'}),
                     lambda r: r['materials'][0].update(thermal_conductivity_w_mk=-1)]
        for mutation in mutations:
            request, _ = fixture()
            mutation(request)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                prepare_assembly_field_handoff(request)

    def test_unsupported_links_contact_incompleteness_and_invalid_face_fail(self):
        mutations = [lambda r,p: p['contacts'].clear(), lambda r,p: p['contacts'][0]['face_pairs'][0]['right'].update(occurrence_id='board'),
                     lambda r,p: p['boundaries'][0]['face'].update(face_id='unknown'),
                     lambda r,p: p['contacts'][0].update(thermal_contact_conductance_w_m2k=0),
                     lambda r,p: r['assembly'].update(electrical_bonds=[{'id':'bond', 'endpoint_a':'board', 'endpoint_b':'case'}])]
        for mutation in mutations:
            request, problem = fixture()
            mutation(request, problem)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                run_assembly_field_thermal(request, problem)

    def test_em_si_ports_preserve_return_mapping_but_do_not_advertise_execution(self):
        for domain in ('em', 'si'):
            request, _ = fixture()
            request['domain'] = domain
            request['materials'] = [{'id': 'slab', 'conductivity_s_m': 5.8e7, 'relative_permittivity': 1,
                                     'relative_permeability': 1, 'provenance': 'Original metallic fixture'}]
            request['ports'] = [{'id': 'p1', 'signal': {'occurrence_id':'board', 'face_id':'0'},
                                'return': {'occurrence_id':'case', 'face_id':'0'}, 'reference_impedance_ohm':50}]
            result = prepare_assembly_field_handoff(request)
            self.assertFalse(result['ports'][0]['executable'])
            self.assertEqual(result['execution_issues'][-1]['code'], 'ASSEMBLY_FIELD_BACKEND_UNAVAILABLE')
            request['materials'][0]['conductivity_s_m'] = 0
            with self.assertRaisesRegex(ValueError, 'conductor face'):
                prepare_assembly_field_handoff(request)

    def test_worker_dispatch_unknown_fields_and_numerical_execution(self):
        request, problem = fixture()
        response = handle_assembly_field_request('run_assembly_field_thermal', {'request':request, 'problem':problem}, request_id=42)
        self.assertTrue(response['ok'], response)
        self.assertFalse(handle_assembly_field_request('run_assembly_field_thermal', {'request':request, 'problem':problem, 'executable':'bad'})['ok'])
        self.assertIsNone(handle_assembly_field_request('unrelated', {}))

    def test_offline_export_roundtrip_numeric_spelling_and_stale_mutations(self):
        request, problem = fixture()
        result = run_assembly_field_thermal(request, problem)
        file = export_assembly_field_study(request, problem, result)
        reopened = import_assembly_field_study(json.loads(json.dumps(file)), current_request=request, current_problem=problem)
        self.assertEqual(reopened['result'], result)
        self.assertIsNone(export_assembly_field_study(request, problem, result, include_results=False)['result'])
        altered = copy.deepcopy(result)
        altered['field_result']['node_temperatures_k'][0] += 1
        with self.assertRaisesRegex(ValueError, 'RESULT_DIGEST'):
            verify_assembly_field_result(request, problem, altered)
        same = copy.deepcopy(request)
        same['materials'][0]['thermal_conductivity_w_mk'] = 2.0
        verify_assembly_field_result(same, problem, result)
        for mutation in [lambda r: r['materials'][0].update(thermal_conductivity_w_mk=3),
                         lambda r: r['bodies'][0].update(source_sha256='c'*64),
                         lambda r: r['assembly']['parts'][0]['frame']['transform'].__setitem__(3, 2000)]:
            current = copy.deepcopy(request)
            mutation(current)
            with self.assertRaisesRegex(ValueError, 'STALE'):
                import_assembly_field_study(file, current_request=current)
        changed_problem = copy.deepcopy(problem)
        changed_problem['boundaries'][0]['temperature_k'] += 1
        with self.assertRaisesRegex(ValueError, 'STALE'):
            verify_assembly_field_result(request, changed_problem, result)

    def test_offline_spike_package_preserves_setup_and_bound_field_output(self):
        from python.spike_core.project_package import write_spike_package, read_spike_package
        from python.spike_core.contracts import SpiDeR
        from python.spike_core.spider_v2 import SpiDeRV2
        request, problem = fixture()
        result = run_assembly_field_thermal(request, problem)
        record = export_assembly_field_study(request, problem, result)
        payload = {'project': {'id':'field-project', 'name':'Field test'},
                   'workspace': {'contract':'spike/workspace-state/v1', 'assemblyFieldStudy':record},
                   'analyses': {'jobs':[]}, 'results': {'runs':[]}, 'audit':[]}
        payload['design_ir'] = SpiDeRV2.from_v1(SpiDeR(design_id='board-design', name='Original board',
                                                     source_format='spike-fixture')).to_dict()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'assembly-field.spike'
            write_spike_package(path, payload)
            reopened = read_spike_package(path)
        saved = reopened.payload['workspace']['assemblyFieldStudy']
        self.assertEqual(import_assembly_field_study(saved, current_request=request, current_problem=problem)['result'], result)

    def test_json_schemas_and_real_worker_process(self):
        from jsonschema import Draft202012Validator, ValidationError
        from referencing import Registry, Resource
        from python.spike_core.spider_v2 import AssemblyIRV1
        root = Path(__file__).resolve().parents[2]
        registry = Registry()
        for name in ('assembly-ir-v1','design-ir-v2','assembly-placement-policy-v1','solver-mesh-v1','assembly-field-handoff-request-v1','assembly-field-thermal-problem-v1'):
            raw = json.loads((root/'schemas'/f'{name}.schema.json').read_text())
            registry = registry.with_resource(raw['$id'], Resource.from_contents(raw))
        request, problem = fixture()
        request['assembly'] = json.loads(json.dumps(AssemblyIRV1.from_dict(request['assembly']).to_dict()))
        for name, value in [('assembly-field-handoff-request-v1',request),('assembly-field-thermal-problem-v1',problem)]:
            schema = json.loads((root/'schemas'/f'{name}.schema.json').read_text())
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema,registry=registry)
            validator.validate(value)
            with self.assertRaises(ValidationError):
                validator.validate({**value,'unexpected':True})
        response = subprocess.run([sys.executable,'-m','python.spike_core.service'],
            input=json.dumps({'id':'field-test','method':'run_assembly_field_thermal','params':{'request':request,'problem':problem}})+'\n',
            text=True,capture_output=True,cwd=root,timeout=60,check=True)
        output = json.loads(response.stdout)
        self.assertTrue(output['ok'],output)
        self.assertEqual(output['result']['contract'],'spike/assembly-field-thermal-result/v1')

    def test_guided_example_runs_original_and_manually_refined_cases(self):
        from examples.assembly_field.run_examples import run_examples
        output = run_examples()
        self.assertEqual([r['resources']['tetrahedra'] for r in output['thermal_examples']], [12,16])
        self.assertNotEqual(output['thermal_examples'][0]['request_digest'], output['thermal_examples'][1]['request_digest'])
        self.assertIsNone(output['view_factor_error_bound'])


if __name__ == '__main__':
    unittest.main()
