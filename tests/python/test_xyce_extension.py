# SPDX-License-Identifier: Apache-2.0
"""Independent fixtures for the Xyce adapter; mocks never qualify native physics."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from extensions.xyce_suite.cases import admit_inputs, prepare, verify_case, waveform
from extensions.xyce_suite.extension import execute
from extensions.xyce_suite.runner import inspect_case, run, runtime
from python.spike_core.circuit_worker_supervisor import SupervisionResult

NETLIST = """SPIKE independently authored divider
Vdrive source 0 3
Rupper source sense 1200
Rlower sense 0 600
.DC Vdrive 0 3 0.5
.PRINT DC FORMAT=CSV V(sense)
.END
"""


class XyceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'SPIKE_STATE_HOME': self.temp.name})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def request(self, contribution, **params):
        return execute({'contract': 'spike/extension/v1', 'contribution_id': contribution,
                        'context': {'parameters': params}})

    def test_prepare_inspect_and_input_tampering(self):
        result = self.request('xyce-circuit', netlist=NETLIST)
        self.assertEqual(result['data']['status'], 'prepared')
        self.assertFalse(result['data']['solved'])
        case_id = result['data']['case_id']
        inspected = self.request('xyce-inspect', case_id=case_id)
        self.assertEqual(inspected['data']['status'], 'prepared')
        from extensions.xyce_suite.cases import case_path
        (case_path(case_id) / 'circuit.cir').write_text(NETLIST.replace('1200', '900'))
        self.assertEqual(self.request('xyce-inspect', case_id=case_id)['data']['status'], 'failed')

    def test_native_subset_admission_and_libraries(self):
        library = {'name': 'parts.lib', 'text': '.MODEL DLOCAL D IS=2e-13\n'}
        admit_inputs(NETLIST.replace('Rupper', '.include parts.lib\nRupper'), [library])
        for bad in ('.include ../private.lib', '.include "C:/secret.lib"',
                    '.CONTROL', '.PRINT DC FORMAT=CSV FILE=outside.csv V(sense)',
                    'YEXT bridge externalcode', 'Vread n 0 PWL FILE secret.csv'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                admit_inputs(NETLIST.replace('.END', bad + '\n.END'), [])
        with self.assertRaises(ValueError):
            admit_inputs(NETLIST, [{'name': 'loop.lib', 'text': '.include loop.lib'}])
        with self.assertRaises(ValueError):
            admit_inputs(NETLIST, [{'name': 'A.lib', 'text': ''}, {'name': 'a.lib', 'text': ''}])

    def test_csv_exact_values_units_and_failures(self):
        path = Path(self.temp.name) / 'fixture.csv'
        path.write_text('TIME,V(sense),I(Vdrive)\n0,1,-0.0016666666666666668\n0.1,1,-0.0016666666666666668\n')
        result = waveform(path)
        self.assertEqual([c['unit'] for c in result['columns']], ['s', 'V', 'A'])
        self.assertEqual(result['rows'][0][1], 1)
        path.write_text('FREQ,VP(sense),VDB(sense),VR(sense),VI(sense),IP(Vdrive)\n100,90,6,0,2,-90\n')
        phase = waveform(path)
        self.assertEqual([c['unit'] for c in phase['columns']], ['Hz', 'deg', 'dB', 'V', 'V', 'deg'])
        for content in ('TIME,V(x)\n0,nan\n', 'TIME,V(x)\n0,1,2\n',
                        'TIME,V(x)\n', 'TIME,TIME\n0,1\n', 'TIME,V(x)\n0,no\n'):
            path.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                waveform(path)

    def test_missing_runtime_and_budgets_do_not_solve(self):
        result = self.request('xyce-run', netlist=NETLIST,
                              engine_options={'executable': str(Path(self.temp.name) / 'Xyce.exe')})
        self.assertEqual(result['data']['status'], 'runtime_unavailable')
        self.assertEqual(result['data']['waveforms'], [])
        for options in ({'timeout_seconds': 301}, {'memory_limit_mib': True}, {'plugins': ['x.dll']}):
            result = self.request('xyce-circuit', operation='preflight', engine_options=options)
            self.assertEqual(result['data']['status'], 'failed')

    def test_fixed_supervisor_calls_and_real_return_states(self):
        path = prepare(NETLIST, [])
        selected = runtime({'executable': str(Path(sys.executable).resolve())})
        def complete(program, arguments, **kwargs):
            self.assertFalse(any(a in {'-plugin', '-r'} for a in arguments))
            self.assertEqual(kwargs['cwd'], path.resolve())
            (path / 'wave.csv').write_text('VDRIVE,V(sense)\n0,0\n3,1\n')
            return SupervisionResult('completed', 0, 0.1, 'fixture_mock')
        with patch('extensions.xyce_suite.runner.supervise_process', side_effect=complete):
            result = run(path, selected, {}, False)
        self.assertTrue(result['solved'])
        self.assertEqual(inspect_case(path)['waveforms'][0]['rows'][1], [3.0, 1.0])
        (path / 'wave.csv').write_text('VDRIVE,V(sense)\n3,999\n')
        with self.assertRaises(ValueError):
            inspect_case(path)
        with patch('extensions.xyce_suite.runner.supervise_process',
                   return_value=SupervisionResult('completed', 3, 0.1, 'fixture_mock')):
            failed = run(path, selected, {}, False)
        self.assertFalse(failed['solved'])
        self.assertEqual(failed['waveforms'], [])
        self.assertFalse((path / 'wave.csv').exists())

    def test_syntax_cancel_timeout_and_no_waveform(self):
        selected = runtime({'executable': str(Path(sys.executable).resolve())})
        for outcome, validate, expected in (
            (SupervisionResult('completed', 0, 0.1, 'mock'), True, 'validated_syntax'),
            (SupervisionResult('cancelled', -9, 0.1, 'mock'), False, 'cancelled'),
            (SupervisionResult('timeout', -9, 0.1, 'mock'), False, 'timeout'),
            (SupervisionResult('completed', 0, 0.1, 'mock'), False, 'completed_without_waveforms')):
            with self.subTest(expected=expected):
                path = prepare(NETLIST, [])
                with patch('extensions.xyce_suite.runner.supervise_process', return_value=outcome):
                    result = run(path, selected, {}, validate)
                self.assertEqual(result['status'], expected)
                self.assertFalse(result['solved'])

    def test_native_dialect_errors_and_live_resource_callback(self):
        selected = runtime({'executable': str(Path(sys.executable).resolve())})
        path = prepare(NETLIST, [])
        def error(program, arguments, **kwargs):
            (path / 'xyce.log').write_text('Netlist error: unsupported model parameter\n')
            return SupervisionResult('completed', 0, 0.1, 'mock')
        with patch('extensions.xyce_suite.runner.supervise_process', side_effect=error):
            result = run(path, selected, {}, False)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['diagnostics'][0]['severity'], 'error')
        def excessive(program, arguments, **kwargs):
            with (path / 'oversize.csv').open('wb') as stream:
                stream.truncate(9 * 1024 * 1024)
            self.assertTrue(kwargs['cancelled']())
            return SupervisionResult('cancelled', -9, 0.1, 'mock')
        with patch('extensions.xyce_suite.runner.supervise_process', side_effect=excessive):
            with self.assertRaisesRegex(ValueError, 'budget'):
                run(path, selected, {}, False)

    @unittest.skipUnless(shutil.which('Xyce') or shutil.which('Xyce.exe'), 'Xyce separately installed runtime absent')
    def test_actual_xyce_independent_divider(self):
        path = prepare(NETLIST, [])
        result = run(path, runtime({}), {}, False)
        self.assertTrue(result['solved'], result)
        wave = result['waveforms'][0]
        column = [c['name'].upper() for c in wave['columns']].index('V(SENSE)')
        self.assertAlmostEqual(wave['rows'][-1][column], 1.0, delta=1e-8)
        self.assertFalse(result.get('production_qualified', False))


if __name__ == '__main__':
    unittest.main()
