# SPDX-License-Identifier: Apache-2.0
"""Owned solves must not initialize optional reference/field solver stacks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
LIBRARY=Path(os.environ.get('SPIKES_TEST_LIBRARY',ROOT/'build-spikes-native-analysis-20261013/Release/spikes_c_api.dll'))


@unittest.skipUnless(LIBRARY.is_file(),'explicit owned native library required')
class OwnedStartupTests(unittest.TestCase):
    def solve(self,source):
        script='''import sys,json
class ReferenceStackBlocker:
    def find_spec(self,fullname,path=None,target=None):
        if any(fullname==name or fullname.startswith(name+'.') for name in
               ('numpy','scipy','python.spike_core','spike_core','python.spikes.runner')):
            raise AssertionError('Owned solve imported optional backend: '+fullname)
sys.meta_path.insert(0,ReferenceStackBlocker())
from python.spikes.netlist import parse_netlist
from python.spikes.native_runner import run_native_project
result=run_native_project(parse_netlist(sys.argv[1],native_extensions=True),sys.argv[2]).to_dict()
print(json.dumps(result))
'''
        run=subprocess.run([sys.executable,'-c',script,source,str(LIBRARY.resolve())],
                           cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        result=json.loads(run.stdout);self.assertEqual(result['status'],'completed',result)
        return result

    def test_operating_point_without_measurements_avoids_reference_imports(self):
        result=self.solve('Divider\nV1 in 0 5\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n')
        self.assertAlmostEqual(result['data']['node_voltage_v']['out'],2.5)
        self.assertEqual(result['measurements'],{})

    def test_transient_measurements_keep_exact_constant_signal_reductions(self):
        result=self.solve('Constant\nV1 out 0 3\nR1 out 0 1k\n.tran 1u 5u\n'
                          '.meas tran mean AVG V(out)\n.meas tran rms RMS V(out)\n'
                          '.meas tran point FIND V(out) AT=2.5u\n.end\n')
        for name in ('mean','rms','point'):
            self.assertEqual(result['measurements'][name]['status'],'completed')
            self.assertAlmostEqual(result['measurements'][name]['value'],3.0)
        self.assertEqual(result['measurements']['mean']['weighting'],'time')

    def test_dc_measurements_keep_sweep_reductions(self):
        result=self.solve('Sweep\nV1 out 0 0\nR1 out 0 1k\n.dc V1 0 4 1\n'
                          '.meas dc mean AVG V(out)\n.meas dc point FIND V(out) AT=1.5\n.end\n')
        self.assertAlmostEqual(result['measurements']['mean']['value'],2.0)
        self.assertAlmostEqual(result['measurements']['point']['value'],1.5)
