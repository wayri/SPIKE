# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from examples.calibrated_fixture_uq.run_study import demonstration
from python.spike_core.solvers.signal_integrity.networks.calibrated_fixture_uq import compose_calibrated_fixture,CalibratedFixtureUQError


class JointFixtureContractTests(unittest.TestCase):
    def test_source_and_output_ownership(self):
        r=demonstration();before=deepcopy(r);out=compose_calibrated_fixture(r)
        self.assertEqual(r,before);self.assertEqual(out['source_request'],before)
        for key in ('production_qualified','measurement_qualified','linearization_qualified'):self.assertFalse(out[key])
        out['derived_network']['port_names'][0]='changed';out['derived_network']['frequencies_hz'][0]=0
        self.assertEqual(out['source_request'],before)

    def test_strict_fields_joint_basis_and_leading_block(self):
        changes=[lambda r:r.update(extra=True),lambda r:r.update(contract='wrong'),
                 lambda r:r['covariance']['basis'].reverse(),lambda r:r['covariance'].update(provenance=''),
                 lambda r:r['calibration']['covariance']['matrix'][0].__setitem__(0,1.),
                 lambda r:r.update(external_ports=list(reversed(r['external_ports'])))]
        for change in changes:
            r=demonstration();change(r)
            with self.subTest(change=change),self.assertRaises(CalibratedFixtureUQError):compose_calibrated_fixture(r)

    def test_cancel_callback_and_budget(self):
        with self.assertRaises(CalibratedFixtureUQError) as error:compose_calibrated_fixture(demonstration(),cancel_check=lambda:True)
        self.assertEqual(error.exception.code,'CALIBRATED_FIXTURE_UQ_CANCELLED')
        calls=[]
        def later():calls.append(1);return len(calls)>10
        with self.assertRaises(CalibratedFixtureUQError) as error:compose_calibrated_fixture(demonstration(),cancel_check=later)
        self.assertEqual(error.exception.code,'CALIBRATED_FIXTURE_UQ_CANCELLED')
        def broken():raise RuntimeError('broken')
        with self.assertRaises(CalibratedFixtureUQError) as error:compose_calibrated_fixture(demonstration(),cancel_check=broken)
        self.assertEqual(error.exception.code,'CALIBRATED_FIXTURE_UQ_CANCEL_CHECK_FAILED')
        r=demonstration();r['covariance']['provenance']='x'*(9*1024*1024)
        with self.assertRaises(CalibratedFixtureUQError) as error:compose_calibrated_fixture(r)
        self.assertEqual(error.exception.code,'CALIBRATED_FIXTURE_UQ_RESOURCE_LIMIT')

    def test_actual_cli_capture_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'capture.json';script=Path(__file__).resolve().parents[2]/'examples/calibrated_fixture_uq/run_study.py'
            command=[sys.executable,str(script),'--output',str(p)];completed=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr)
            capture=json.loads(p.read_text(encoding='utf-8'));self.assertEqual(capture['source'],capture['result']['source_request'])
            before=p.read_bytes();failed=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertNotEqual(failed.returncode,0);self.assertEqual(before,p.read_bytes())


if __name__=='__main__':unittest.main()
