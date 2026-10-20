# SPDX-License-Identifier: Apache-2.0
"""Job-local library reuse must never reuse circuits or leak across jobs."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch
from python.spikes.netlist import parse_netlist
from python.spikes import native_runner as runner

ROOT=Path(__file__).resolve().parents[2]
LIBRARY=Path(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',ROOT/'build-spikes-native-analysis-20261013/Release/spikes_c_api.dll'))

@unittest.skipUnless(LIBRARY.is_file(),'owned DLL required')
class JobBindingTests(unittest.TestCase):
    def test_nested_step_dc_shares_binding_but_uses_independent_point_circuits(self):
        project=parse_netlist('Sweep\n.param r=1k\n.step param r 1k 2k 1k\n'
            'V1 in 0 0\nR1 in out {r}\nR2 out 0 1k\n.dc V1 0 4 1\n'
            '.meas dc mean AVG V(out)\n.end\n',native_extensions=True)
        loader=runner.load_native_library
        circuits=[]
        def load(path):
            library=loader(path);create=library.circuit
            def circuit():
                value=create();circuits.append(value);return value
            library.circuit=circuit
            return library
        with patch.object(runner,'load_native_library',side_effect=load) as loads:
            result=runner.run_native_project(project,LIBRARY).to_dict()
        self.assertEqual(loads.call_count,1)
        self.assertEqual(len(circuits),10)
        self.assertEqual(len({id(circuit) for circuit in circuits}),10)
        self.assertEqual(result['status'],'completed',result)
        means=result['measurements']['mean']['by_step']
        self.assertAlmostEqual(means[0]['result']['value'],1)
        self.assertAlmostEqual(means[1]['result']['value'],2/3)

    def test_separate_and_concurrent_jobs_reload_and_keep_results_separate(self):
        def solve(voltage):
            project=parse_netlist(f'Job\nV1 out 0 {voltage}\nR1 out 0 1k\n.op\n.end\n')
            return runner.run_native_project(project,LIBRARY).to_dict()['data']['node_voltage_v']['out']
        with patch.object(runner,'load_native_library',wraps=runner.load_native_library) as loads:
            self.assertEqual(solve(1),1)
            self.assertEqual(solve(3),3)
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(solve,[2,4])),[2,4])
        self.assertEqual(loads.call_count,4)

    def test_failed_sweep_closes_its_circuit_and_stops_before_next_point(self):
        project=parse_netlist('Floating\nV1 in 0 0\nR1 a b 1k\n'
            '.dc V1 0 4 1\n.end\n',native_extensions=True)
        loader=runner.load_native_library
        circuits=[]
        def load(path):
            library=loader(path);create=library.circuit
            def circuit():
                value=create();circuits.append(value);return value
            library.circuit=circuit
            return library
        with patch.object(runner,'load_native_library',side_effect=load) as loads:
            result=runner.run_native_project(project,LIBRARY).to_dict()
        self.assertEqual(result['status'],'failed',result)
        self.assertEqual(loads.call_count,1)
        self.assertEqual(len(circuits),1)
        self.assertFalse(circuits[0]._handle.value)

    def test_failed_load_is_retried_in_next_job(self):
        project=parse_netlist('Job\nV1 out 0 1\nR1 out 0 1k\n.op\n.end\n')
        original=runner.load_native_library
        with patch.object(runner,'load_native_library',side_effect=[OSError('failed load'),original(LIBRARY)]) as loads:
            with self.assertRaisesRegex(OSError,'failed load'):
                runner.run_native_project(project,LIBRARY)
            self.assertEqual(runner.run_native_project(project,LIBRARY).status,'completed')
        self.assertEqual(loads.call_count,2)
