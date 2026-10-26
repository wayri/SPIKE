# SPDX-License-Identifier: Apache-2.0
"""Admission, source-retention and executable workflow checks; no measured data."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np

from python.spike_core.solvers.signal_integrity.networks.one_port_calibration import calibrate_one_port, OnePortCalibrationError, input_basis
from examples.one_port_calibration.run_calibration import demonstration


class CalibrationContractTests(unittest.TestCase):
    def test_example_retains_identity_and_recovers_physical_standards(self):
        request = demonstration()
        frozen = deepcopy(request)
        result = calibrate_one_port(request)
        self.assertEqual(request, frozen)
        self.assertEqual(result['source_request'], frozen)
        self.assertFalse(result['production_qualified'])
        self.assertFalse(result['measurement_qualified'])
        self.assertFalse(result['linearization_qualified'])
        self.assertEqual(result['derived_network']['port_names'], [request['port_name']])
        actual = [complex(v[0][0]['real'], v[0][0]['imag']) for v in result['derived_network']['s_parameters']]
        np.testing.assert_allclose(actual, [.2+.3j, -.4+.1j], rtol=2e-12, atol=2e-12)
        request['dut']['measured'][0]['real'] += 1
        self.assertEqual(result['source_request'], frozen)

    def test_structural_and_domain_failures(self):
        changes = [lambda r: r.update(extra=True), lambda r: r.update(contract='wrong'),
                   lambda r: r.update(reference_impedance_ohm=0),
                   lambda r: r.update(reference_impedance_ohm=True),
                   lambda r: r.update(frequencies_hz=[0, 1e9]),
                   lambda r: r.update(frequencies_hz=[1e9, 1e8]),
                   lambda r: r.update(frequencies_hz=[1e8]*17),
                   lambda r: r['standards'].pop(),
                   lambda r: r['standards'][1].update(id=r['standards'][0]['id']),
                   lambda r: r['standards'][0].update(provenance=''),
                   lambda r: r['dut']['measured'][1].update(imag=float('nan')),
                   lambda r: r['dut']['measured'][0].update(real=True),
                   lambda r: r['standards'][0]['reflection'].pop(),
                   lambda r: r['covariance']['basis'].reverse(),
                   lambda r: r['covariance'].update(provenance=''),
                   lambda r: r['covariance'].update(matrix=[])]
        for change in changes:
            r = demonstration(); change(r)
            with self.subTest(change=change), self.assertRaises(OnePortCalibrationError):
                calibrate_one_port(r)

    def test_covariance_rejects_indefinite_nonsymmetric_and_hidden_tiny_subblock(self):
        for kind in ('asymmetric', 'negative', 'zero_row', 'indefinite', 'tiny_indefinite'):
            r = demonstration(); c = np.zeros((28, 28))
            np.fill_diagonal(c, 1.)
            if kind == 'asymmetric': c[0, 1] = .1
            if kind == 'negative': c[0, 0] = -1
            if kind == 'zero_row': c[0, 0] = 0; c[0, 1] = c[1, 0] = .1
            if kind == 'indefinite': c[0, 1] = c[1, 0] = 2
            if kind == 'tiny_indefinite':
                c[0, 0] = c[1, 1] = 1e-30; c[0, 1] = c[1, 0] = 2e-30
            r['covariance']['matrix'] = c.tolist()
            with self.subTest(kind=kind), self.assertRaises(OnePortCalibrationError):
                calibrate_one_port(r)

    def test_rank_deficient_and_zero_covariance_are_not_inflated(self):
        for c in (np.zeros((28, 28)), np.outer(np.arange(28)*1e-6, np.arange(28)*1e-6)):
            r = demonstration(); r['covariance']['matrix'] = c.tolist()
            result = calibrate_one_port(r)
            jac = np.asarray(result['sensitivity'])
            np.testing.assert_allclose(result['covariance'], jac@c@jac.T, rtol=1e-12, atol=1e-22)

    def test_valid_first_invalid_later_has_no_returned_partial_result(self):
        r = demonstration()
        for standard in r['standards']:
            standard['reflection'][1] = {'real': 0., 'imag': 0.}
        with self.assertRaises(OnePortCalibrationError) as error:
            calibrate_one_port(r)
        self.assertEqual(error.exception.code, 'ONE_PORT_CALIBRATION_ILL_CONDITIONED')

    def test_resource_boundary_and_streamed_oversize_rejection(self):
        r = demonstration()
        r['frequencies_hz'] = [1e8*(k+1) for k in range(16)]
        for standard in r['standards']:
            for key in ('reflection', 'measured'):
                standard[key] = [deepcopy(standard[key][0]) for _ in range(16)]
        r['dut']['measured'] = [deepcopy(r['dut']['measured'][0]) for _ in range(16)]
        r['covariance']['basis'] = input_basis(16)
        r['covariance']['matrix'] = np.zeros((224, 224)).tolist()
        result = calibrate_one_port(r)
        self.assertEqual(np.shape(result['sensitivity']), (32, 224))
        self.assertEqual(np.shape(result['covariance']), (32, 32))
        r = demonstration(); r['dut']['provenance'] = 'x'*(9*1024*1024)
        with self.assertRaises(OnePortCalibrationError) as error:
            calibrate_one_port(r)
        self.assertEqual(error.exception.code, 'ONE_PORT_CALIBRATION_RESOURCE_LIMIT')

    def test_cancel_and_broken_callback_fail_closed(self):
        r = demonstration()
        with self.assertRaises(OnePortCalibrationError) as error:
            calibrate_one_port(r, cancel_check=lambda: True)
        self.assertEqual(error.exception.code, 'ONE_PORT_CALIBRATION_CANCELLED')
        def broken(): raise RuntimeError('callback')
        with self.assertRaises(OnePortCalibrationError) as error:
            calibrate_one_port(r, cancel_check=broken)
        self.assertEqual(error.exception.code, 'ONE_PORT_CALIBRATION_CANCEL_CHECK_FAILED')
        calls = []
        def later():
            calls.append(1)
            return len(calls) >= 4
        with self.assertRaises(OnePortCalibrationError): calibrate_one_port(r, cancel_check=later)
        with self.assertRaises(OnePortCalibrationError): input_basis(True)

    def test_executable_capture_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'capture.json'
            command = [sys.executable, str(Path(__file__).resolve().parents[2]/'examples/one_port_calibration/run_calibration.py'), '--output', str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            capture = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(capture['source'], capture['result']['source_request'])
            before = output.read_bytes()
            failed = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__': unittest.main()
