# SPDX-License-Identifier: Apache-2.0
"""Project inventory, freshness and bounded artifact admission regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from examples.assembly_field.run_examples import setup
from tests.python.test_project_assembly_field import _write
from python.spike_core.project_package import read_project, ProjectPackageError
from python.spike_core.service_project_thermal_mesh import (
    read_assembly_thermal_mesh_setup, run_assembly_thermal_mesh_in_project, _artifact_reader,
)

class ThermalMeshProjectTests(unittest.TestCase):
    def test_inventory_and_stale_identity(self):
        request, _ = setup()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'study.spike'
            manifest = _write(path, request)
            params = dict(project_path=str(path), expected_manifest_payload_sha256=manifest['manifest_payload_sha256'])
            result = read_assembly_thermal_mesh_setup(params)
            self.assertEqual(len(result['boards']), 1)
            self.assertEqual(len(result['parts']), 1)
            params['expected_manifest_payload_sha256'] = '0'*64
            with self.assertRaises(ProjectPackageError):
                read_assembly_thermal_mesh_setup(params)

    def test_package_only_artifact_and_missing_member(self):
        request, _ = setup()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'study.spike'
            _write(path, request)
            opened = read_project(path)
            reader = _artifact_reader(path, opened)
            self.assertTrue(reader('package:models/artifacts/original-case.step').startswith(b'ISO'))
            for invalid in ['C:/secrets.step', 'package:../secret.step', 'package:models/missing.step']:
                with self.subTest(invalid=invalid), self.assertRaises(ProjectPackageError):
                    reader(invalid)
            opened.manifest['members'][0]['size'] = 128*1024*1024
            uri = 'package:'+opened.manifest['members'][0]['path']
            with self.assertRaisesRegex(ProjectPackageError, 'BUDGET'):
                _artifact_reader(path, opened)(uri)

    def test_fixed_bridge_receives_canonical_assembly_and_preserves_project(self):
        request, _ = setup()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'study.spike'
            manifest = _write(path, request)
            before = path.read_bytes()
            params = dict(project_path=str(path), expected_manifest_payload_sha256=manifest['manifest_payload_sha256'], assignments={}, mesh_options={})
            with patch('python.spike_core.assembly_thermal_meshing.run_assembly_thermal_mesh', return_value={'status':'blocked','blockers':[]}) as run:
                self.assertEqual(run_assembly_thermal_mesh_in_project(params)['status'],'blocked')
                self.assertEqual(run.call_args.args[0]['assembly_ir']['boards'][0]['id'], request['assembly']['boards'][0]['id'])
            self.assertEqual(path.read_bytes(), before)

if __name__ == '__main__':
    unittest.main()
