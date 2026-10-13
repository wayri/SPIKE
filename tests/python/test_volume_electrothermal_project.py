# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound saved coupling and retained thermal contact authoring checks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples.assembly_field.run_examples import setup
from examples.assembly_field.run_multiboard_volume import request
from python.spike_core.assembly_field_thermal import run_assembly_field_thermal
from python.spike_core.assembly_thermal_contact_model import prepare_assembly_thermal_contact_model
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.multiboard_volume_electrothermal import run_multiboard_volume_electrothermal
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_volume_electrothermal import handle_volume_electrothermal_project_request
from python.spike_core.service_volume_electrothermal import handle_volume_electrothermal_request
from tests.python.test_project_assembly_field import MODEL_ARTIFACT, _write


def _call(method, path, manifest, **extra):
    return handle_volume_electrothermal_project_request(method, {
        'project_path': str(path), 'expected_manifest_payload_sha256': manifest['manifest_payload_sha256'],
        **extra}, request_id='volume-test', application_version='test')


def _rehash(result):
    result['result_digest'] = canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'})


class VolumeElectrothermalProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = request(mechanical_part=True, alpha=.004)
        cls.result = run_multiboard_volume_electrothermal(cls.request)
        cls.record = {'request': cls.request, 'result': cls.result}

    def test_descriptor_and_headless_worker_dispatch_use_real_identities(self):
        from python.spike_core.automation import SpikeAutomation
        automation = SpikeAutomation()
        described = automation.call('describe_volume_electrothermal_bindings', {
            'geometry': self.request['geometry'], 'circuit': self.request['circuit']})
        self.assertEqual(len(described['resistors']), 3)
        self.assertEqual({row['occurrence_id'] for row in described['occurrences']}, {'board', 'case'})
        self.assertEqual(sum(len(row['cell_ids']) for row in described['occurrences']), 12)
        prepared = automation.call('prepare_multiboard_volume_electrothermal', {'request': self.request})
        self.assertEqual(prepared['handoff']['handoff_digest'], self.result['thermal']['handoff_digest'])
        verified = automation.call('verify_multiboard_volume_electrothermal_result', {'request': self.request, 'result': self.result})
        self.assertEqual(verified['result_digest'], self.result['result_digest'])
        changed = copy.deepcopy(self.request['circuit'])
        changed['assembly']['name'] = 'different assembly'
        rejected = handle_volume_electrothermal_request('describe_volume_electrothermal_bindings', {
            'geometry': self.request['geometry'], 'circuit': changed})
        self.assertFalse(rejected['ok'])

    def test_save_without_results_retains_coupling_setup(self):
        from python.spike_core.service_project_persistence import without_saved_results
        payload = {'analyses': {'assembly_volume_electrothermal': self.record}}
        clean = without_saved_results(payload)
        self.assertIsNone(clean['analyses']['assembly_volume_electrothermal']['result'])
        self.assertEqual(clean['analyses']['assembly_volume_electrothermal']['request'], self.request)
        self.assertIsNotNone(payload['analyses']['assembly_volume_electrothermal']['result'])

    def test_real_solution_save_read_offline_reopen_and_unique_members_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'volume.spike'
            manifest = _write(path, self.request['geometry'])
            saved = _call('save_volume_electrothermal_in_project', path, manifest, record=self.record)
            self.assertTrue(saved['ok'], saved)
            opened = read_project(path, include_members=True)
            with patch('python.spike_core.multiboard_volume_electrothermal.run_native_mna',
                       side_effect=AssertionError('offline reopen invoked electrical solver')):
                with patch('python.spike_core.multiboard_volume_electrothermal.run_assembly_field_thermal',
                           side_effect=AssertionError('offline reopen invoked thermal solver')):
                    loaded = _call('read_volume_electrothermal_in_project', path, opened.manifest)
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['state'], 'current')
            self.assertNotIn('manifest', loaded['result'])  # read must not downgrade native authenticated binding
            self.assertEqual(json.loads(json.dumps(loaded['result']['record'])), json.loads(json.dumps(self.record)))
            self.assertEqual(opened.members['models/artifacts/original-case.step'], MODEL_ARTIFACT)
            self.assertFalse(loaded['result']['record']['result']['production_qualified'])
            self.assertEqual(opened.payload['audit'][-1]['event'], 'volume_electrothermal_saved')

    def test_stale_assembly_is_withheld_and_rejected_save_does_not_mutate_package(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'stale.spike'
            manifest = _write(path, self.request['geometry'])
            saved = _call('save_volume_electrothermal_in_project', path, manifest, record=self.record)
            self.assertTrue(saved['ok'], saved)
            opened = read_project(path, include_members=True)
            payload = copy.deepcopy(opened.payload)
            transform = list(payload['assembly_ir']['parts'][0]['frame']['transform'])
            transform[3] += 1
            payload['assembly_ir']['parts'][0]['frame']['transform'] = transform
            changed = write_spike_package(path, payload, preserved_members=opened.members)
            loaded = _call('read_volume_electrothermal_in_project', path, changed)
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['state'], 'stale')
            self.assertIsNone(loaded['result']['record'])
            rejected = _call('save_volume_electrothermal_in_project', path, changed, record=self.record)
            self.assertFalse(rejected['ok'], rejected)
            self.assertEqual(read_project(path).manifest['manifest_payload_sha256'], changed['manifest_payload_sha256'])

    def test_stale_manifest_read_and_save_are_rejected_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'race.spike'
            manifest = _write(path, self.request['geometry'])
            saved = _call('save_volume_electrothermal_in_project', path, manifest, record=self.record)
            self.assertTrue(saved['ok'], saved)
            for method, extra in [('read_volume_electrothermal_in_project', {}),
                                  ('save_volume_electrothermal_in_project', {'record': self.record})]:
                response = _call(method, path, manifest, **extra)
                self.assertFalse(response['ok'], response)
            self.assertEqual(read_project(path).manifest['manifest_payload_sha256'],
                             saved['result']['manifest']['manifest_payload_sha256'])

    def test_corrupted_digest_is_rejected_without_replacing_saved_result(self):
        corrupt = copy.deepcopy(self.record)
        corrupt['result']['loss_balance']['deposited_power_w'] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'corrupt.spike'
            manifest = _write(path, self.request['geometry'])
            rejected = _call('save_volume_electrothermal_in_project', path, manifest, record=corrupt)
            self.assertFalse(rejected['ok'], rejected)
            self.assertEqual(read_project(path).manifest['manifest_payload_sha256'], manifest['manifest_payload_sha256'])
            opened = read_project(path, include_members=True)
            payload = copy.deepcopy(opened.payload)
            payload['analyses']['assembly_volume_electrothermal'] = corrupt
            changed = write_spike_package(path, payload, preserved_members=opened.members)
            self.assertFalse(_call('read_volume_electrothermal_in_project', path, changed)['ok'])

    def test_setup_only_and_strict_worker_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'setup.spike'
            manifest = _write(path, self.request['geometry'])
            missing = _call('read_volume_electrothermal_in_project', path, manifest)
            self.assertEqual(missing['result']['state'], 'missing')
            saved = _call('save_volume_electrothermal_in_project', path, manifest,
                          record={'request': self.request, 'result': None})
            self.assertTrue(saved['ok'], saved)
            self.assertIsNone(_call('read_volume_electrothermal_in_project', path, saved['result']['manifest'])['result']['record']['result'])
        rejected = handle_volume_electrothermal_request('run_multiboard_volume_electrothermal',
                                                       {'request': self.request, 'executable': 'shell'})
        self.assertFalse(rejected['ok'])

    def test_rehashed_inconsistent_electrical_voltages_are_not_admitted(self):
        changed = copy.deepcopy(self.result)
        voltages = changed['electrical']['native_result']['data']['node_voltage_v']
        for node in voltages:
            voltages[node] = 0.
        _rehash(changed)
        admitted = handle_volume_electrothermal_request('verify_multiboard_volume_electrothermal_result',
                                                       {'request': self.request, 'result': changed})
        self.assertFalse(admitted['ok'], 'Saved source voltage contradicts ideal excitation and returned resistor powers')

    def test_offline_admission_rejects_source_current_power_and_ac_display_corruption(self):
        dc_source = self.result['circuit_maps']['element_map']['board']['supply']
        mutations = [lambda r: r['electrical']['native_result']['data']['element_current_a'].__setitem__(dc_source, 0.),
                     lambda r: r['electrical']['native_result']['data']['element_power_w'].__setitem__(dc_source, 0.),
                     lambda r: r['electrical']['native_result'].update(mode='ac')]
        for mutation in mutations:
            changed = copy.deepcopy(self.result)
            mutation(changed)
            _rehash(changed)
            self.assertFalse(handle_volume_electrothermal_request('verify_multiboard_volume_electrothermal_result',
                {'request': self.request, 'result': changed})['ok'])
        raw = request('si')
        solved = run_multiboard_volume_electrothermal(raw)
        self.assertTrue(handle_volume_electrothermal_request('verify_multiboard_volume_electrothermal_result',
            {'request': raw, 'result': json.loads(json.dumps(solved))})['ok'])
        for field in ('real', 'magnitude', 'phase_deg'):
            changed = copy.deepcopy(solved)
            node = next(iter(changed['electrical']['native_result']['data']['node_voltage_v'].values()))
            node[field][0] += 1
            _rehash(changed)
            self.assertFalse(handle_volume_electrothermal_request('verify_multiboard_volume_electrothermal_result',
                {'request': raw, 'result': changed})['ok'])


class ThermalContactModelTests(unittest.TestCase):
    def test_matching_resistance_authors_same_contacts_and_actual_solution(self):
        geometry, problem = setup()
        original = copy.deepcopy(problem)
        prepared = prepare_assembly_thermal_contact_model(geometry, problem, 'contact', .25)
        self.assertEqual(problem, original)
        self.assertEqual(prepared['problem'], problem)
        self.assertEqual(prepared['face_pair_count'], 2)
        self.assertAlmostEqual(prepared['thermal_contact_conductance_w_m2k'], 4)
        solved = run_assembly_field_thermal(geometry, prepared['problem'])
        self.assertAlmostEqual(solved['occurrence_temperatures']['board']['maximum_k'], 340, places=8)
        self.assertAlmostEqual(solved['occurrence_temperatures']['case']['minimum_k'], 360, places=8)
        self.assertLess(abs(solved['field_result']['heat_balance']['imbalance_w']), 1e-8)

    def test_retained_resistance_area_mismatch_and_missing_match_rejected(self):
        geometry, problem = setup()
        with self.assertRaisesRegex(ValueError, 'resistance disagrees'):
            prepare_assembly_thermal_contact_model(geometry, problem, 'contact', 2)
        geometry['assembly']['thermal_contacts'][0]['contact_area_mm2'] *= 2
        with self.assertRaisesRegex(ValueError, 'area disagrees'):
            prepare_assembly_thermal_contact_model(geometry, problem, 'contact', .25)
        geometry, problem = setup()
        transform = list(geometry['assembly']['parts'][0]['frame']['transform'])
        transform[3] += 1000
        geometry['assembly']['parts'][0]['frame']['transform'] = transform
        with self.assertRaisesRegex(ValueError, 'matching triangles'):
            prepare_assembly_thermal_contact_model(geometry, problem, 'contact', .25)

    def test_contact_faces_already_used_by_boundary_are_rejected(self):
        geometry, problem = setup()
        problem['boundaries'].append({'face': copy.deepcopy(problem['contacts'][0]['face_pairs'][0]['left']),
                                      'type': 'temperature', 'temperature_k': 300})
        with self.assertRaisesRegex(ValueError, 'boundary|assigned|used|duplicate'):
            prepare_assembly_thermal_contact_model(geometry, problem, 'contact', .25)

    def test_contact_faces_used_by_another_contact_are_rejected(self):
        geometry, problem = setup()
        geometry['assembly']['thermal_contacts'].append(dict(geometry['assembly']['thermal_contacts'][0], id='other'))
        problem['contacts'].append(dict(copy.deepcopy(problem['contacts'][0]), contact_id='other'))
        with self.assertRaisesRegex(ValueError, 'contact|used|duplicate'):
            prepare_assembly_thermal_contact_model(geometry, problem, 'contact', .25)


if __name__ == '__main__':
    unittest.main()
