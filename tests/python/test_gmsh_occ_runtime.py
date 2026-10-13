# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core import gmsh_occ_runtime as runtime
from tests.python.test_gmsh_occ_mesher import request


class OccFixedLaunchTests(unittest.TestCase):
    def test_fixed_launch_skips_site_processing_and_keeps_single_process_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)/'case'

            def process(argv, **options):
                self.assertEqual(argv[1:], ['-I', '-S', '-'])
                self.assertEqual(options['windows_active_process_limit'], 1)
                self.assertIn('sys.path.extend(', options['stdin_payload'].decode())
                self.assertNotIn('site.addsitedir', options['stdin_payload'].decode())
                digest = hashlib.sha256((case/'request.json').read_bytes()).hexdigest()
                (case/'result.json').write_text(json.dumps({'request_sha256': digest, 'runtime_provenance': {}}))
                (case/'environment.json').write_text(json.dumps({'status': 'passed', 'isolated': True, 'site_disabled': True}))
                return {'return_code': 0, 'stdout': '', 'stderr': ''}

            with patch.object(runtime, 'verify_installation', return_value={}), \
                    patch.object(runtime, 'run_adapter_process', side_effect=process):
                runtime.run_occ_case(request(), case)
            evidence = json.loads((case/'process.json').read_text())
            self.assertEqual(len(evidence['worker_interpreter_sha256']), 64)

    def test_missing_trusted_interpreter_never_creates_case(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)/'case'
            with patch.object(runtime, 'verify_installation', return_value={}), \
                    patch.object(runtime.sys, 'executable', str(Path(directory)/'absent.exe')), \
                    patch.object(runtime.sys, 'prefix', runtime.sys.base_prefix), \
                    patch.object(runtime, 'run_adapter_process') as process:
                with self.assertRaisesRegex(ValueError, 'trusted interpreter'):
                    runtime.run_occ_case(request(), case)
                process.assert_not_called()
                self.assertFalse(case.exists())


@unittest.skipUnless(sys.version_info[:2] == (3, 11) and importlib.util.find_spec("shapely"), "Local OCC adapter targets Windows CPython 3.11 with Shapely")
class OccRuntimeTests(unittest.TestCase):
    def test_venv_launch_uses_base_without_relaxing_process_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root/'python.exe'
            base.write_bytes(b'fixture')
            packages = root/'packages'
            packages.mkdir()
            with patch.object(runtime.sys, 'prefix', str(root/'venv')), \
                    patch.object(runtime.sys, 'base_prefix', str(root)), \
                    patch.object(runtime.sys, '_base_executable', str(base)), \
                    patch.object(runtime.sysconfig, 'get_path', return_value=str(packages)):
                executable, paths = runtime._worker_interpreter()
            self.assertEqual(executable, base.resolve())
            self.assertEqual(paths, [str(packages.resolve())])

    def test_tampered_installation_never_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory)/'vendor.py'
            fake.write_text('not the admitted artifact')
            with patch.object(runtime, 'ARTIFACTS', {fake:'0'*64}), patch.object(runtime, 'run_adapter_process') as run:
                with self.assertRaisesRegex(ValueError, 'GMSH_HASH'):
                    runtime.run_occ_case(request(), Path(directory)/'case')
                run.assert_not_called()
                self.assertFalse((Path(directory)/'case').exists())

    def test_bad_input_and_budgets_never_launch(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, 'verify_installation', return_value={}), patch.object(runtime, 'run_adapter_process') as run:
            value = request()
            value['script'] = 'untrusted'
            with self.assertRaises(ValueError):
                runtime.run_occ_case(value, Path(directory)/'case')
            for options in ({'timeout_s':True}, {'timeout_s':0}, {'memory_limit_mb':1}):
                with self.assertRaises(ValueError):
                    runtime.run_occ_case(request(), Path(directory)/'case', **options)
            run.assert_not_called()

    def test_existing_case_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runtime, 'verify_installation', return_value={}), patch.object(runtime, 'run_adapter_process') as run:
            with self.assertRaises(FileExistsError):
                runtime.run_occ_case(request(), directory)
            run.assert_not_called()

    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError):
            runtime._unique([('solids', []), ('solids', [])])


if __name__ == '__main__':
    unittest.main()
