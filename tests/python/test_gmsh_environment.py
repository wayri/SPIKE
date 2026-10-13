# SPDX-License-Identifier: Apache-2.0
"""Actual fresh isolated dependency checks and declared venv inheritance."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from python.spike_core import gmsh_occ_runtime as runtime
from python.spike_core.gmsh_environment import isolated_preflight_source


class MesherEnvironmentTests(unittest.TestCase):
    def test_each_missing_dependency_and_no_path_or_pth_execution(self):
        executable, _ = runtime._worker_interpreter()
        root = Path(__file__).resolve().parents[2]
        for missing in ('scipy', 'shapely', None):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                job = Path(directory)
                packages, poison = job/'packages', job/'poison'
                packages.mkdir()
                poison.mkdir()
                marker = job/'unexpected-execution'
                (packages/'executable.pth').write_text('import pathlib; pathlib.Path('+repr(str(marker))+').touch()')
                (poison/'numpy.py').write_text('import pathlib; pathlib.Path('+repr(str(marker))+').touch()\n__version__="poison"')
                names = ('numpy',) if missing == 'scipy' else ('numpy', 'scipy') if missing == 'shapely' else ('numpy', 'scipy', 'shapely')
                for name in names:
                    (packages/(name+'.py')).write_text('__version__="original-preflight-test-fixture"')
                process = subprocess.run([str(executable), '-I', '-S', '-'], cwd=job, capture_output=True,
                    input=isolated_preflight_source(root, [packages]).encode(), timeout=30,
                    env={**os.environ, 'PYTHONPATH': str(poison)})
                evidence = json.loads((job/'environment.json').read_text())
                self.assertFalse(marker.exists(), 'Neither PYTHONPATH nor executable .pth is admitted')
                if missing:
                    self.assertNotEqual(process.returncode, 0)
                    self.assertIn('GMSH_DEPENDENCY: '+missing, evidence['diagnostic'])
                else:
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertEqual(evidence['status'], 'passed')
    def test_fresh_isolated_child_and_incomplete_environment(self):
        executable, packages = runtime._worker_interpreter()
        root = Path(__file__).resolve().parents[2]
        for admitted, expected in ((packages, 'passed'), ([], 'failed')):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                code = isolated_preflight_source(root, admitted)
                process = subprocess.run([str(executable), '-I', '-S', '-'], input=code.encode(),
                                         cwd=directory, capture_output=True, timeout=30)
                evidence = json.loads((Path(directory)/'environment.json').read_text())
                self.assertEqual(evidence['status'], expected, process.stderr)
                self.assertTrue(evidence['isolated'])
                self.assertTrue(evidence['site_disabled'])
                if expected == 'passed':
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertEqual(set(evidence['dependencies']), {'numpy', 'scipy', 'shapely'})
                    for item in evidence['dependencies'].values():
                        self.assertTrue(item['version'])
                        self.assertTrue(any(Path(item['origin']).is_relative_to(Path(p)) for p in packages))
                else:
                    self.assertNotEqual(process.returncode, 0)
                    self.assertIn('GMSH_DEPENDENCY: numpy', evidence['diagnostic'])

    def test_only_declared_base_package_inheritance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            venv, base_packages, venv_packages = root/'venv', root/'basepkgs', root/'venvpkgs'
            for path in (venv, base_packages, venv_packages):
                path.mkdir()
            executable = root/'python.exe'
            executable.write_bytes(b'fixture')
            def path(_kind, vars=None):
                return str(base_packages if vars else venv_packages)
            with patch.object(runtime.sys, 'platform', 'win32'), patch.object(runtime.sys, 'prefix', str(venv)), \
                 patch.object(runtime.sys, 'base_prefix', str(root)), patch.object(runtime.sys, '_base_executable', str(executable)), \
                 patch.object(runtime.sysconfig, 'get_path', side_effect=path):
                for flag, count in (('false', 1), ('true', 2)):
                    (venv/'pyvenv.cfg').write_text('include-system-site-packages = '+flag)
                    selected, packages = runtime._worker_interpreter()
                    self.assertEqual(selected, executable.resolve())
                    self.assertEqual(len(packages), count)
                    self.assertEqual(packages[0], str(venv_packages.resolve()))
                (venv/'pyvenv.cfg').write_text('include-system-site-packages=true\ninclude-system-site-packages=false')
                with self.assertRaisesRegex(ValueError, 'ambiguous'):
                    runtime._worker_interpreter()

    def test_environment_variable_cannot_select_bridge_executable(self):
        from python.spike_core import gmsh_extension_runtime as bridge
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root/'Programs'/'Python'/'Python311'
            (base/'Lib'/'site-packages').mkdir(parents=True)
            (base/'python.exe').write_bytes(b'fixture')
            with patch.object(bridge.sys, 'platform', 'win32'), patch.object(bridge.sys, 'version_info', (3, 12)), \
                 patch.object(bridge, '_local_appdata', return_value=root), \
                 patch.dict(bridge.os.environ, {'LOCALAPPDATA': str(root/'poisoned')}):
                self.assertEqual(bridge._interpreter(), (base/'python.exe').resolve())
