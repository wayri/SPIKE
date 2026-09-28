# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core import gmsh_occ_runtime as runtime
from tests.python.test_gmsh_occ_mesher import request


@unittest.skipUnless(sys.version_info[:2] == (3, 11) and importlib.util.find_spec("shapely"), "Local OCC adapter targets Windows CPython 3.11 with Shapely")
class OccRuntimeTests(unittest.TestCase):
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
