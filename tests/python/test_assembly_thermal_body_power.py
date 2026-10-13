# SPDX-License-Identifier: Apache-2.0
"""Original watt conservation and source-edit lifecycle checks."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_field_handoff import prepare_assembly_field_handoff
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal
from python.spike_core.assembly_thermal_body_power import assign_assembly_thermal_body_power
from python.spike_core.service_assembly_field import handle_assembly_field_request
from tests.python.test_assembly_field_handoff import fixture
from tests.python.test_assembly_tetra_thermal import cube, exterior


class AssemblyThermalBodyPowerTests(unittest.TestCase):
    def setUp(self):
        self.request, self.problem = fixture()

    def assign(self, watts=7.0, **kwargs):
        parameters = dict(request=self.request, problem=self.problem, occurrence_id='board', power_w=watts,
                          expected_request_digest=prepare_assembly_field_handoff(self.request)['request_digest'])
        parameters.update(kwargs)
        return assign_assembly_thermal_body_power(**parameters)

    def test_watts_conserved_for_unequal_tetrahedra_and_mm_or_m(self):
        for units, scale in [('m', 1), ('mm', 1000)]:
            with self.subTest(units=units):
                self.request, self.problem = fixture()
                mesh = cube(n=2, owner='shared-source', unit=units)
                # Two column widths 1/4 and 3/4 m; exact total volume 1 m3.
                mesh['vertices'] = [[(x/2 if x <= .5 else 1.5*x-.5)*scale, y*scale, z*scale]
                                    for x, y, z in mesh['vertices']]
                body = self.request['bodies'][0]
                body['mesh'] = mesh
                body['boundary_faces'] = [{'id': str(i), 'vertices': f} for i, f in enumerate(exterior(mesh))]
                snapshot = copy.deepcopy(self.problem)
                result = self.assign()
                self.assertEqual(self.problem, snapshot)
                self.assertAlmostEqual(result['volume_m3'], 1.0, places=12)
                sources = {row['cell_id']: row['heat_source_w_m3'] for row in result['problem']['heat_sources']}
                points = np.array(mesh['vertices']) / scale
                volumes = [abs(float(np.linalg.det((points[c['vertices']][1:]-points[c['vertices']][0]).T)))/6
                           for c in mesh['cells']]
                self.assertGreater(max(volumes)/min(volumes), 2.9)
                deposited = math.fsum(sources[c['id']]*v for c, v in zip(mesh['cells'], volumes))
                self.assertAlmostEqual(deposited, 7.0, places=12)
                self.assertEqual(len(set(sources.values())), 1)

    def test_actual_solve_reports_exact_authored_watts(self):
        result = self.assign()
        solved = run_assembly_field_thermal(self.request, result['problem'])
        self.assertAlmostEqual(solved['field_result']['heat_balance']['source_w'], 7.0, places=12)
        self.assertLess(abs(solved['field_result']['heat_balance']['imbalance_w']), 1e-8)

    def test_other_occurrence_same_cell_ids_preserved_and_replace_required(self):
        cell = self.request['bodies'][0]['mesh']['cells'][0]['id']
        other = {'occurrence_id': 'case', 'cell_id': cell, 'heat_source_w_m3': 123.0}
        target = {'occurrence_id': 'board', 'cell_id': cell, 'heat_source_w_m3': 42.0}
        self.problem['heat_sources'] = [other, target]
        with self.assertRaisesRegex(ValueError, 'REPLACE'):
            self.assign()
        result = self.assign(replace_existing=True)
        self.assertEqual(result['problem']['heat_sources'][0], other)
        self.assertEqual(result['replaced_source_cells'], 1)
        self.assertEqual(self.assign(0, replace_existing=True)['problem']['heat_sources'], [other])
        self.assertEqual(self.problem['heat_sources'], [other, target])

    def test_invalid_watts_geometry_and_stale_request_rejected(self):
        for watts in [-1, float('nan'), float('inf'), True, '2']:
            with self.subTest(watts=watts), self.assertRaises(ValueError):
                self.assign(watts)
        digest = prepare_assembly_field_handoff(self.request)['request_digest']
        self.request['materials'][0]['thermal_conductivity_w_mk'] = 3
        with self.assertRaisesRegex(ValueError, 'STALE'):
            self.assign(expected_request_digest=digest)
        with self.assertRaisesRegex(ValueError, 'BODY'):
            self.assign(occurrence_id='missing')
        self.request['bodies'][0]['mesh']['vertices'][0][0] = float('nan')
        with self.assertRaises(ValueError):
            assign_assembly_thermal_body_power(self.request, self.problem, 'board', 1, digest)

    def test_unknown_duplicate_sources_and_budget_rejected(self):
        source = {'occurrence_id': 'case', 'cell_id': 'missing', 'heat_source_w_m3': 1}
        self.problem['heat_sources'] = [source]
        with self.assertRaisesRegex(ValueError, 'SOURCE'):
            self.assign()
        source['cell_id'] = self.request['bodies'][1]['mesh']['cells'][0]['id']
        self.problem['heat_sources'] = [source, source]
        with self.assertRaisesRegex(ValueError, 'SOURCE'):
            self.assign()
        self.problem['heat_sources'] = [source]*11
        with patch('python.spike_core.assembly_thermal_body_power.MAX_CELLS', 10), self.assertRaisesRegex(ValueError, 'LIMIT'):
            self.assign()

    def test_bulk_body_power_field_solve_conserves_authored_watts(self):
        mesh = cube(n=12, owner='shared-source')
        self.request['assembly']['thermal_contacts'] = []
        self.request['bodies'][0]['mesh'] = mesh
        self.request['bodies'][0]['boundary_faces'] = [
            {'id': str(i), 'vertices': f} for i, f in enumerate(exterior(mesh))]
        self.problem['contacts'] = []
        self.problem['boundaries'] = []
        for body in self.request['bodies']:
            for face in body['boundary_faces']:
                if all(body['mesh']['vertices'][v][0] == 0 for v in face['vertices']):
                    self.problem['boundaries'].append({
                        'face': {'occurrence_id': body['occurrence_id'], 'face_id': face['id']},
                        'type': 'temperature', 'temperature_k': 300})
        assigned = self.assign(watts=7)
        self.assertEqual(assigned['source_cells'], 10368)
        solved = run_assembly_field_thermal(self.request, assigned['problem'])
        result = solved['field_result']
        self.assertAlmostEqual(result['heat_balance']['source_w'], 7, places=9)
        self.assertAlmostEqual(result['heat_balance']['temperature_reaction_inward_w'], -7, places=7)
        self.assertLess(abs(result['heat_balance']['imbalance_w']), 1e-7)
        # Insulated x=1 slab: T=300+q*(x-x*x/2)/k, k=2 and q=7.
        self.assertAlmostEqual(solved['occurrence_temperatures']['board']['maximum_k'], 301.75, delta=0.01)

    def test_worker_route_and_exact_parameters(self):
        from python.spike_core.service import handle
        params = dict(request=self.request, problem=self.problem, occurrence_id='board', power_w=2,
                      expected_request_digest=prepare_assembly_field_handoff(self.request)['request_digest'],
                      replace_existing=False)
        response = handle_assembly_field_request('assign_assembly_thermal_body_power', params)
        self.assertTrue(response['ok'])
        self.assertEqual(response['result']['power_w'], 2)
        self.assertTrue(handle({'method': 'assign_assembly_thermal_body_power', 'params': params})['ok'])
        self.assertFalse(handle_assembly_field_request('assign_assembly_thermal_body_power',
                                                      {**params, 'surprise': True})['ok'])


if __name__ == '__main__':
    unittest.main()
