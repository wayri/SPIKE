# SPDX-License-Identifier: Apache-2.0
import unittest
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
