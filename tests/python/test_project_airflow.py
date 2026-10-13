# SPDX-License-Identifier: Apache-2.0
"""Portable airflow identity, stale-result and concurrent-save regressions."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from examples.assembly_field.run_examples import setup
from tests.python.test_project_assembly_field import _write
from python.spike_core.multiboard_identity import canonical_json_digest as digest
from python.spike_core.project_package import read_project, write_spike_package, ProjectPackageError
from python.spike_core.service_project_airflow import read_study, run_in_project, _geometry


class ProjectAirflowTests(unittest.TestCase):
    def test_save_reopen_and_request_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'air.spike'
            manifest = _write(path, setup()[0])
            solids = [{'id': 'body', 'material_id': 'fr4', 'shape': {'kind': 'polygon_prism'}}]
            request = {'geometry': {'solids': solids, 'mesh': {}}, 'power_w': 1}
            params = {'project_path': str(path), 'expected_manifest_payload_sha256': manifest['manifest_payload_sha256'],
                      'assignments': {}, 'mesh_options': {}, 'request': request}
            native = {'status': 'completed', 'fields': {'temperature_k': {'samples': []}}}
            with patch('python.spike_core.service_project_airflow._geometry', return_value=(solids, {'body': {}}, {})), \
                 patch('python.spike_core.assembly_airflow.run_assembly_airflow', return_value=native):
                result = run_in_project(params, application_version='test')
                identity = {key: params[key] for key in ('project_path', 'expected_manifest_payload_sha256')}
                identity['expected_manifest_payload_sha256'] = result['manifest']['manifest_payload_sha256']
                self.assertEqual(read_study(identity)['state'], 'current')
                opened = read_project(path, include_members=True)
                self.assertIn('models/artifacts/original-case.step', opened.members)
                payload = copy.deepcopy(opened.payload)
                record = payload['analyses']['assembly_airflow_study']
                record['request']['power_w'] = 2
                record['request_digest'] = digest(record['request'])
                changed = write_spike_package(path, payload, preserved_members=opened.members)
                identity['expected_manifest_payload_sha256'] = changed['manifest_payload_sha256']
                with self.assertRaisesRegex(ProjectPackageError, 'BINDING'):
                    read_study(identity)

    def test_final_save_guard_preserves_newer_project(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'air.spike'
            manifest = _write(path, setup()[0])
            opened = read_project(path, include_members=True)
            newer = copy.deepcopy(opened.payload)
            newer['project']['name'] = 'Concurrent work'
            write_spike_package(path, newer, preserved_members=opened.members)
            before = path.read_bytes()
            with self.assertRaisesRegex(ProjectPackageError, 'PROJECT_STALE'):
                write_spike_package(path, opened.payload, preserved_members=opened.members,
                                    expected_manifest_payload_sha256=manifest['manifest_payload_sha256'])
            self.assertEqual(path.read_bytes(), before)

    def test_unconsumed_encapsulation_has_explicit_blocker(self):
        with self.assertRaisesRegex(ProjectPackageError, 'AIRFLOW_ENCAPSULATION'):
            _geometry(None, None, {'encapsulation': [{'id': 'coat'}]}, {})


if __name__ == '__main__':
    unittest.main()
