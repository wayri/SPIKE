# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Real solved histories through offline files and manifest-bound native saves."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from examples.assembly_field.run_examples import setup
from python.spike_core.assembly_field_study import export_assembly_field_study, import_assembly_field_study
from python.spike_core.assembly_field_transient import run_assembly_field_transient, verify_assembly_field_transient_result
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.multiboard_study import physical_assembly
from python.spike_core.project_package import read_project, write_spike_package
from python.spike_core.service_project_handlers import handle_project_request
from tests.python.test_assembly_tetra_transient import settings
from tests.python.test_project_assembly_field import _call, _write, MODEL_ARTIFACT


def rehash(record):
    if record.get('result'):
        result = record['result']
        result['result_digest'] = canonical_json_digest({k: v for k, v in result.items() if k != 'result_digest'})
    record['file_digest'] = canonical_json_digest({k: v for k, v in record.items() if k != 'file_digest'})
    return record


class AssemblyTransientPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request, cls.problem = setup()
        cls.problem['boundaries'] = []
        cls.problem['heat_sources'] = [{'occurrence_id': 'board', 'cell_id': c['id'], 'heat_source_w_m3': 40.}
                                        for c in cls.request['bodies'][0]['mesh']['cells']]
        cls.settings = settings()
        cls.result = run_assembly_field_transient(cls.request, cls.problem, cls.settings)
        cls.record = export_assembly_field_study(cls.request, cls.problem, cls.result,
                                                  transient_settings=cls.settings)

    def test_offline_result_and_setup_only_roundtrip(self):
        for include in (True, False):
            record = export_assembly_field_study(self.request, self.problem, self.result,
                                                  include_results=include, transient_settings=self.settings)
            admitted = import_assembly_field_study(json.loads(json.dumps(record)),
                                                     current_request=self.request, current_problem=self.problem)
            self.assertEqual(admitted['transient_settings'], self.settings)
            self.assertEqual(admitted['result'], self.result if include else None)
        setup_only = export_assembly_field_study(self.request, self.problem, transient_settings=self.settings)
        self.assertEqual(import_assembly_field_study(setup_only)['transient_settings'], self.settings)

    def test_rehashed_changed_settings_or_history_reject(self):
        changes = [lambda r: r['transient_settings'].update(time_step_s=.05),
                   lambda r: r['result']['field_result']['frames'][1].update(time_s=.19),
                   lambda r: r['result']['field_result']['frames'][0]['node_temperatures_k'].__setitem__(0, 301),
                   lambda r: r['result']['field_result']['frames'][1].update(stored_energy_change_j=999),
                   lambda r: r['result']['transient_settings'].update(initial_temperature_k=299)]
        for change in changes:
            altered = copy.deepcopy(self.record)
            change(altered)
            rehash(altered)
            with self.subTest(change=change), self.assertRaises(ValueError):
                import_assembly_field_study(altered)
        altered = copy.deepcopy(self.record)
        altered['transient_settings']['initial_temperature_k'] = 299
        altered['result']['transient_settings']['initial_temperature_k'] = 299
        altered['result']['transient_digest'] = canonical_json_digest(altered['transient_settings'])
        with self.assertRaises(ValueError):
            import_assembly_field_study(rehash(altered))

    def test_native_project_saves_and_reopens_real_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transient.spike'
            manifest = _write(path, self.request)
            saved = _call('save_assembly_field_study_in_project', path, manifest, record=self.record)
            self.assertTrue(saved['ok'], saved)
            opened = read_project(path, include_members=True)
            loaded = _call('read_assembly_field_study_in_project', path, opened.manifest)
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['state'], 'current')
            self.assertEqual(loaded['result']['record'], self.record)
            self.assertEqual(opened.members['models/artifacts/original-case.step'], MODEL_ARTIFACT)
            self.assertEqual(loaded['result']['record']['result']['field_result']['frames'], self.result['field_result']['frames'])

    def test_raw_assembly_defaults_bind_same_result_and_native_save_identity(self):
        raw = copy.deepcopy(self.request)
        # Keep original slab geometry, board+STEP identities and contacts; omit
        # legal AssemblyIR defaults as the retained original STEP mesher does.
        raw['assembly'] = {key: raw['assembly'][key] for key in
                           ('assembly_id', 'name', 'boards', 'parts', 'thermal_contacts')}
        raw['assembly']['boards'][0]['frame'] = {'frame_id': 'board-frame'}
        raw['assembly']['extensions'] = {'spike.multiboard-studies': {'thermal': {'status': 'old-output'}}}
        before = copy.deepcopy(raw)
        canonical = copy.deepcopy(raw)
        canonical['assembly'] = physical_assembly(raw['assembly'])
        result = run_assembly_field_transient(raw, self.problem, self.settings)
        self.assertEqual(raw, before)
        self.assertEqual(result['request_digest'], canonical_json_digest(canonical))
        self.assertEqual(verify_assembly_field_transient_result(canonical, self.problem, result), result)
        record = export_assembly_field_study(raw, self.problem, result, transient_settings=self.settings)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'raw-defaults.spike'
            manifest = _write(path, raw)
            saved = _call('save_assembly_field_study_in_project', path, manifest, record=record)
            self.assertTrue(saved['ok'], saved)
            opened = read_project(path, include_members=True)
            loaded = _call('read_assembly_field_study_in_project', path, opened.manifest)
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['state'], 'current')
            self.assertEqual(loaded['result']['record']['result'], result)
            self.assertEqual(loaded['result']['record']['request'], canonical)
            self.assertEqual(opened.members['models/artifacts/original-case.step'], MODEL_ARTIFACT)
        for mutate in [lambda r: r['materials'][0].update(thermal_conductivity_w_mk=3),
                       lambda r: r['bodies'][0].update(source_sha256='f'*64),
                       lambda r: r['assembly']['parts'][0]['frame'].update(
                           transform=[1,0,0,2000,0,1,0,0,0,0,1,0,0,0,0,1])]:
            changed = copy.deepcopy(raw)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                verify_assembly_field_transient_result(changed, self.problem, result)

    def test_normal_native_save_without_results_preserves_valid_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / 'source.spike'
            manifest = _write(base, self.request)
            saved = _call('save_assembly_field_study_in_project', base, manifest, record=self.record)
            self.assertTrue(saved['ok'], saved)
            opened = read_project(base)
            for include in (False, True):
                destination = Path(directory) / f'copy-{include}.spike'
                saved_copy = handle_project_request('write_project_package', {
                    'path': str(destination), 'snapshot': copy.deepcopy(opened.payload),
                    'base_package_path': str(base), 'include_results': include, 'generate_geometry_tables': False,
                }, request_id='transient-copy', application_version='test')
                self.assertTrue(saved_copy['ok'], saved_copy)
                loaded = _call('read_assembly_field_study_in_project', destination, saved_copy['result']['manifest'])
                self.assertTrue(loaded['ok'], loaded)
                record = loaded['result']['record']
                self.assertEqual(record['transient_settings'], self.settings)
                self.assertEqual(record['result'], self.result if include else None)

    def test_native_tampered_history_fails_atomically_and_geometry_becomes_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'atomic.spike'
            manifest = _write(path, self.request)
            altered = copy.deepcopy(self.record)
            altered['result']['field_result']['frames'][1]['stored_energy_change_j'] += 1
            response = _call('save_assembly_field_study_in_project', path, manifest, record=rehash(altered))
            self.assertFalse(response['ok'])
            self.assertEqual(read_project(path).manifest['manifest_payload_sha256'], manifest['manifest_payload_sha256'])
            response = _call('save_assembly_field_study_in_project', path, manifest, record=self.record)
            self.assertTrue(response['ok'], response)
            opened = read_project(path, include_members=True)
            payload = copy.deepcopy(opened.payload)
            payload['assembly_ir']['parts'][0]['frame']['transform'] = list(payload['assembly_ir']['parts'][0]['frame']['transform'])
            payload['assembly_ir']['parts'][0]['frame']['transform'][3] += 1
            moved = write_spike_package(path, payload, preserved_members=opened.members)
            loaded = _call('read_assembly_field_study_in_project', path, moved)
            self.assertTrue(loaded['ok'], loaded)
            self.assertEqual(loaded['result']['state'], 'stale')
            self.assertIsNone(loaded['result']['record'])


if __name__ == '__main__':
    unittest.main()
