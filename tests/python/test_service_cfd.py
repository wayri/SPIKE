# SPDX-License-Identifier: Apache-2.0
import unittest
from unittest.mock import patch
from python.spike_core.service_cfd import handle_cfd_request


class CfdServiceTests(unittest.TestCase):
    def test_runtime_paths_cannot_be_supplied_as_worker_parameters(self):
        for method in ('run_native_cfd', 'run_su2_cfd', 'run_su2_cht'):
            response = handle_cfd_request(method, {'request': {}, 'executable': 'bad.exe'})
            self.assertFalse(response['ok'])
            self.assertIn('exactly one request', str(response))

    def test_catalog_rejects_execution_parameters(self):
        self.assertFalse(handle_cfd_request('cfd_capabilities', {'request': {}})['ok'])

    def test_unrelated_methods_do_not_load_runtimes(self):
        self.assertIsNone(handle_cfd_request('other_method', {}))

    def test_rectilinear_openfoam_route_requires_explicit_proxy_mode(self):
        request = {'geometry_mode': 'exact_cad', 'config': {}, 'output_dir': 'case', 'allow_experimental': True}
        self.assertFalse(handle_cfd_request('run_openfoam_rectilinear_assembly', {'request': request})['ok'])
        request['geometry_mode'] = 'declared_axis_aligned_cuboids'
        with patch('python.spike_core.solvers.external_engines.openfoam.openfoam_rectilinear_assembly.run_rectilinear_assembly',
                   return_value={'status': 'completed', 'geometry_exact': False}) as run:
            response = handle_cfd_request('run_openfoam_rectilinear_assembly', {'request': request})
        self.assertTrue(response['ok'])
        self.assertFalse(response['result']['geometry_exact'])
        run.assert_called_once()
