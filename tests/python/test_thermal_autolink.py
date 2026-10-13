# SPDX-License-Identifier: Apache-2.0
"""Original conforming two-solid contact and ambiguous geometry oracles."""
import copy
import unittest

from examples.assembly_field.run_examples import setup
from python.spike_core.assembly_thermal_autolink import discover_assembly_thermal_links, autolink_assembly_thermal_contacts
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal
from python.spike_core.service_volume_electrothermal import handle_volume_electrothermal_request


class ThermalAutolinkTests(unittest.TestCase):
    def test_actual_interface_resistance_and_solution_preserved(self):
        request, problem = setup()
        original = copy.deepcopy(problem)
        preview = discover_assembly_thermal_links(request, problem)
        self.assertEqual(preview['proposals'][0]['face_pair_count'], 2)
        self.assertEqual(preview['proposals'][0]['contact_area_mm2'], 1e6)
        self.assertEqual(preview['proposals'][0]['status'], 'ready')
        problem['contacts'] = []
        linked = autolink_assembly_thermal_contacts(request, problem, ['contact'])
        self.assertEqual(problem['contacts'], [])
        self.assertEqual(linked['linked_contacts'][0]['thermal_contact_conductance_w_m2k'], 4)
        actual = run_assembly_field_thermal(request, linked['problem'])
        expected = run_assembly_field_thermal(request, original)
        self.assertEqual(actual['field_result']['node_temperatures_k'], expected['field_result']['node_temperatures_k'])

    def test_geometry_does_not_infer_a_link_or_resistance(self):
        request, problem = setup()
        request['assembly']['thermal_contacts'] = []
        preview = discover_assembly_thermal_links(request, problem)
        self.assertEqual(preview['proposals'][0]['status'], 'needs_review')
        self.assertIsNone(preview['proposals'][0]['thermal_resistance_k_per_w'])
        with self.assertRaisesRegex(ValueError, 'REVIEW'):
            autolink_assembly_thermal_contacts(request, problem, ['contact'])
        request, problem = setup()
        request['assembly']['thermal_contacts'][0]['thermal_resistance_k_per_w'] = None
        self.assertEqual(discover_assembly_thermal_links(request, problem)['proposals'][0]['status'], 'needs_review')

    def test_gaps_conflicting_boundaries_area_and_same_facing_overlap(self):
        request, problem = setup()
        request['assembly']['parts'][0]['frame']['transform'] = list(request['assembly']['parts'][0]['frame']['transform'])
        request['assembly']['parts'][0]['frame']['transform'][3] += .01
        preview = discover_assembly_thermal_links(request, problem)
        self.assertEqual(preview['proposals'], [])
        self.assertEqual(preview['unmatched_contact_ids'], ['contact'])
        request, problem = setup()
        problem['boundaries'].append({'face': problem['contacts'][0]['face_pairs'][0]['left'], 'type': 'adiabatic'})
        self.assertEqual(discover_assembly_thermal_links(request, problem)['proposals'][0]['status'], 'needs_review')
        request, problem = setup()
        problem['contacts'][0]['contact_id'] = 'another-contact'
        preview = discover_assembly_thermal_links(request, problem)
        self.assertEqual(preview['proposals'][0]['status'], 'needs_review')
        self.assertIn('another contact', preview['proposals'][0]['reason'])
        request, problem = setup()
        request['assembly']['thermal_contacts'][0]['contact_area_mm2'] = 2e6
        self.assertEqual(discover_assembly_thermal_links(request, problem)['proposals'][0]['status'], 'needs_review')
        request, problem = setup()
        request['assembly']['parts'][0]['frame']['transform'] = [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        with self.assertRaisesRegex(ValueError, 'ASSEMBLY_FIELD_OVERLAP'):
            discover_assembly_thermal_links(request, problem)

    def test_batch_is_bounded_unique_and_worker_fields_are_exact(self):
        request, problem = setup()
        for ids in [[], ['contact', 'contact'], ['missing'], ['contact']*65, [True]]:
            with self.assertRaises(ValueError):
                autolink_assembly_thermal_contacts(request, problem, ids)
        response = handle_volume_electrothermal_request('discover_assembly_thermal_links', {'request': request, 'problem': problem})
        self.assertTrue(response['ok'], response)
        response = handle_volume_electrothermal_request('discover_assembly_thermal_links', {'request': request, 'problem': problem, 'distance': 5})
        self.assertFalse(response['ok'])


if __name__ == '__main__':
    unittest.main()
