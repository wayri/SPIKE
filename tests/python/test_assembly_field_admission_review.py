# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original adversarial retained-contact and saved-result admission fixtures."""
import copy
import unittest

from python.spike_core.solvers.execution.coupling.assembly_field_thermal import run_assembly_field_thermal, verify_assembly_field_result
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.spider_v2 import AssemblyIRV1, BoardInstance, AssemblyContact
from python.spike_core.spider_v2_schema import CoordinateFrame
from tests.python.test_assembly_field_geometry import assembly_at, body_from_mesh
from tests.python.test_assembly_tetra_thermal import cube


def _request(assembly, bodies):
    return {'contract': 'spike/assembly-field-handoff-request/v1', 'assembly': assembly.to_dict(),
            'domain': 'thermal', 'bodies': bodies,
            'materials': [{'id': 'physical', 'provenance': 'original review fixture',
                           'thermal_conductivity_w_mk': 2.}]}


def _bind_body(body, board):
    return {**body, 'occurrence_id': board.id, 'reference_id': board.design_id,
            'source_sha256': 'a'*64, 'stack_binding': {'id': 'stack', 'source_sha256': 'b'*64}}


def simple_case():
    assembly, board = assembly_at()
    body = _bind_body(body_from_mesh([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
                                    [[0, 1, 2, 3]], units='m'), board)
    problem = {'contract': 'spike/assembly-field-thermal-problem/v1', 'heat_sources': [], 'contacts': [],
               'boundaries': [{'face': {'occurrence_id': board.id, 'face_id': body['boundary_faces'][0]['id']},
                               'type': 'temperature', 'temperature_k': 300.}]}
    return _request(assembly, [body]), problem


def contact_case():
    boards = [BoardInstance(id=oid, design_id=oid, frame=CoordinateFrame(frame_id=oid))
              for oid in ('left', 'right')]
    assembly = AssemblyIRV1('contact-review', 'Original two-cube review', boards=boards,
                           thermal_contacts=[AssemblyContact(id='join', endpoint_a='left', endpoint_b='right',
                                                              contact_area_mm2=1e6, thermal_resistance_k_per_w=.25)])
    bodies = []
    for index, board in enumerate(boards):
        mesh = cube(origin=index, owner=board.id)
        bodies.append(_bind_body(body_from_mesh(mesh['vertices'], [c['vertices'] for c in mesh['cells']],
                                               units='m'), board))

    def at(body, x):
        return [f for f in body['boundary_faces'] if all(body['mesh']['vertices'][i][0] == x for i in f['vertices'])]

    def endpoint(body, face):
        return {'occurrence_id': body['occurrence_id'], 'face_id': face['id']}

    boundaries = [{'face': endpoint(b, f), 'type': 'temperature', 'temperature_k': 300.+100*i}
                  for i, b in enumerate(bodies) for f in at(b, 2*i)]
    pairs = []
    for left in at(bodies[0], 1):
        points = {tuple(bodies[0]['mesh']['vertices'][i]) for i in left['vertices']}
        right = next(f for f in at(bodies[1], 1)
                     if {tuple(bodies[1]['mesh']['vertices'][i]) for i in f['vertices']} == points)
        pairs.append({'left': endpoint(bodies[0], left), 'right': endpoint(bodies[1], right)})
    problem = {'contract': 'spike/assembly-field-thermal-problem/v1', 'boundaries': boundaries,
               'heat_sources': [], 'contacts': [{'contact_id': 'join', 'face_pairs': pairs,
                                                'thermal_contact_conductance_w_m2k': 4.}]}
    return _request(assembly, bodies), problem


class AssemblyFieldAdmissionReviewTests(unittest.TestCase):
    def test_correctly_bound_contact_properties(self):
        request, problem = contact_case()
        result = run_assembly_field_thermal(request, problem)
        heat = sum(contact['left_to_right_heat_w'] for contact in result['field_result']['contacts'])
        # Two L/(k A)=.5 K/W cubes plus the retained .25 K/W interface.
        self.assertAlmostEqual(heat, -100/1.25, delta=1e-8)

    def test_retained_area_and_resistance_cannot_be_silently_overridden(self):
        for key, value in (('contact_area_mm2', 1.), ('thermal_resistance_k_per_w', 999.),
                           ('thermal_resistance_k_per_w', 0.)):
            request, problem = contact_case()
            request['assembly']['thermal_contacts'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                run_assembly_field_thermal(request, problem)

    def test_rehashed_invalid_nested_results_are_rejected(self):
        request, problem = simple_case()
        valid = run_assembly_field_thermal(request, problem)
        verify_assembly_field_result(request, problem, valid)
        mutations = [('contract', 'wrong'), ('production_qualified', True), ('status', 'validated'),
                     ('model_status', 'validated'), ('node_temperatures_k', [-9000.]*4),
                     ('node_temperatures_k', [300.]), ('node_temperatures_k', [True]*4),
                     ('cell_heat_flux_w_m2', [])]
        for key, value in mutations:
            result = copy.deepcopy(valid)
            result['field_result'][key] = value
            result['result_digest'] = canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'})
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify_assembly_field_result(request, problem, result)


if __name__ == '__main__':
    unittest.main()
