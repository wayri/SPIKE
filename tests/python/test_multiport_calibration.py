# SPDX-License-Identifier: Apache-2.0
"""Source, admission, interoperability and executable calibration checks."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import numpy as np
from examples.multiport_calibration.run_calibration import demonstration
from python.spike_core.solvers.signal_integrity.networks.multiport_calibration import calibrate_multiport, MultiportCalibrationError, input_basis
from python.spike_core.solvers.signal_integrity.networks.sparameter_multiport_deembedding import deembed_multiport


def complex_samples(network):
    return np.array([[[complex(z['real'],z['imag']) for z in row] for row in sample] for sample in network['s_parameters']])


class MultiportCalibrationContractTests(unittest.TestCase):
    def test_example_recovery_and_all_source_arrays_are_independent(self):
        request = demonstration(); before = deepcopy(request)
        result = calibrate_multiport(request)
        wanted = [[.1+.02j,.2-.03j,-.12+.07j],[.35+.04j,.15-.01j,.22j],[-.08j,.18+.06j,-.1]]
        np.testing.assert_allclose(complex_samples(result['derived_network']),[wanted,wanted],atol=2e-12,rtol=2e-12)
        self.assertEqual(request,before); self.assertEqual(result['source_request'],before)
        for key in ('production_qualified','measurement_qualified','linearization_qualified','model_consistency_qualified'):
            self.assertFalse(result[key])
        result['derived_network']['port_names'][0]='changed'
        result['derived_network']['frequencies_hz'][0]=2
        result['error_box']['frequencies_hz'][0]=3
        result['error_box_maps']['physical_ports'][0]='changed'
        self.assertEqual(result['source_request'],before)

    def test_error_box_interoperates_with_supplied_fixture_removal(self):
        r=demonstration(); result=calibrate_multiport(r); maps=result['error_box_maps']
        transformed=deembed_multiport({'contract':'spike/multiport-deembedding-request/v1',
            'external_ports':maps['exterior_ports'],'dut_ports':maps['dut_ports'],
            'fixture':result['error_box'],
            'measured':{'id':'external-dut','port_names':maps['exterior_ports'],'reference_impedance_ohm':50.,
                        'frequencies_hz':r['frequencies_hz'],'s_parameters':r['dut']['measured']}})
        np.testing.assert_allclose(complex_samples(transformed['derived_network']),complex_samples(result['derived_network']),atol=2e-12,rtol=2e-12)

    def test_strict_shapes_identities_wave_basis_and_covariance_basis(self):
        changes=[lambda r:r.update(extra=True),lambda r:r.update(contract='wrong'),
                 lambda r:r.update(measurement_basis='uncorrected_switched_s_parameters'),
                 lambda r:r.update(reference_impedance_ohm=True),lambda r:r.update(reference_impedance_ohm=0),
                 lambda r:r.update(port_names=['same']*3),lambda r:r.update(gain_reference_port='missing'),
                 lambda r:r.update(frequencies_hz=[0,1e9]),lambda r:r.update(frequencies_hz=[1e9,1e8]),
                 lambda r:r['dut'].update(id=r['coupling_standard']['id']),lambda r:r['reflection_standards'].pop(),
                 lambda r:r['reflection_standards'][0]['reflection'][0].pop(),
                 lambda r:r['coupling_standard']['s_parameters'][0].pop(),
                 lambda r:r['dut']['measured'][0][0][0].update(imag=float('nan')),
                 lambda r:r['dut']['measured'][0][0][0].update(real=True),
                 lambda r:r['covariance']['basis'].reverse(),lambda r:r['covariance'].update(provenance='')]
        for change in changes:
            r=demonstration();change(r)
            with self.subTest(change=change),self.assertRaises(MultiportCalibrationError):calibrate_multiport(r)

    def test_atomic_late_unidentifiable_path_rejection(self):
        r=demonstration()
        r['coupling_standard']['s_parameters'][1]=[[{'real':0.,'imag':0.} for _ in range(3)] for _ in range(3)]
        before=deepcopy(r)
        with self.assertRaises(MultiportCalibrationError) as error:calibrate_multiport(r)
        self.assertEqual(error.exception.code,'MULTIPORT_CALIBRATION_UNIDENTIFIABLE')
        self.assertEqual(r,before)

    def test_rank_deficient_covariance_and_diagnostic_only_redundant_data(self):
        r=demonstration();size=len(r['covariance']['basis']);v=1e-5*np.cos(np.arange(size))
        r['covariance']['matrix']=np.outer(v,v).tolist()
        baseline=calibrate_multiport(r)
        r['coupling_standard']['measured'][0][0][2]['real']+=.02
        changed=calibrate_multiport(r)
        np.testing.assert_array_equal(complex_samples(changed['derived_network']),complex_samples(baseline['derived_network']))
        self.assertGreater(changed['diagnostics'][0]['coupling_standard_consistency_residual'],.001)
        self.assertFalse(changed['model_consistency_qualified'])

    def test_cancel_resource_and_callback_failures(self):
        r=demonstration()
        with self.assertRaises(MultiportCalibrationError):calibrate_multiport(r,cancel_check=lambda:True)
        def broken():raise RuntimeError('callback')
        with self.assertRaises(MultiportCalibrationError) as error:calibrate_multiport(r,cancel_check=broken)
        self.assertEqual(error.exception.code,'MULTIPORT_CALIBRATION_CANCEL_CHECK_FAILED')
        calls=[]
        def later():calls.append(1);return len(calls)>15
        with self.assertRaises(MultiportCalibrationError):calibrate_multiport(r,cancel_check=later)
        with self.assertRaises(MultiportCalibrationError):input_basis(['p0','p1'],3)
        r['dut']['provenance']='x'*(9*1024*1024)
        with self.assertRaises(MultiportCalibrationError) as error:calibrate_multiport(r)
        self.assertEqual(error.exception.code,'MULTIPORT_CALIBRATION_RESOURCE_LIMIT')

    def test_rejects_indefinite_and_nonsymmetric_covariance(self):
        for kind in ('asymmetric','indefinite','zero_row'):
            r=demonstration();size=len(r['covariance']['basis']);c=np.eye(size)*1e-10
            if kind=='asymmetric':c[0,1]=1e-11
            if kind=='indefinite':c[0,1]=c[1,0]=2e-10
            if kind=='zero_row':c[0,0]=0;c[0,1]=c[1,0]=1e-11
            r['covariance']['matrix']=c.tolist()
            with self.subTest(kind=kind),self.assertRaises(MultiportCalibrationError):calibrate_multiport(r)

    def test_actual_example_cli_preserves_existing_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'capture.json';script=Path(__file__).resolve().parents[2]/'examples/multiport_calibration/run_calibration.py'
            command=[sys.executable,str(script),'--output',str(p)]
            completed=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr)
            capture=json.loads(p.read_text(encoding='utf-8'));self.assertEqual(capture['source'],capture['result']['source_request'])
            old=p.read_bytes();failed=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(failed.returncode,0);self.assertEqual(p.read_bytes(),old)


if __name__=='__main__':unittest.main()
