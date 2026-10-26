# SPDX-License-Identifier: Apache-2.0
"""Synthetic adversarial validator fixtures; never physical qualification."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from scripts import verify_multiport_calibration as gate


class MultiportCalibrationEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        for n in gate.SOURCES:
            p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic validator source',encoding='utf-8')
        self.log=self.root/'synthetic.log';self.log.write_text('SYNTHETIC VALIDATOR TEST\nRan 20 tests in 0 seconds\nOK\n',encoding='utf-8')
        self.capture=self.root/'synthetic.json';request=gate.demonstration()
        self.original={'source':request,'result':gate.calibrate_multiport(request)}
        self.capture.write_text(json.dumps(self.original),encoding='utf-8')
        snapshot={n:gate.digest(self.root/n) for n in gate.SOURCES}
        self.receipt={'contract':'spike/multiport-calibration-evidence/v1','stage_id':'SI08-S07','status':'passed',
                      'stage_complete':True,'workflow':'offline_reference',**{k:False for k in gate.FLAGS},
                      'sources_before':snapshot,'sources_after':deepcopy(snapshot),
                      'tests':{'names':gate.names(unittest.defaultTestLoader.loadTestsFromNames(gate.MODULES)),
                               'run':20,'failures':[],'errors':[],'skipped':[],'expected_failures':[],'unexpected_successes':[]},
                      'log':{'path':self.log.name,'sha256':gate.digest(self.log)},
                      'capture':{'path':self.capture.name,'sha256':gate.digest(self.capture)}}

    def test_synthetic_fixture_and_scope_execution_rejections(self):
        gate.validate_receipt(self.receipt,self.root)
        changes=[lambda r:r.update(stage_complete=False),lambda r:r.update(family_complete=True),
                 lambda r:r.update(measurement_qualified=True),lambda r:r.update(linearization_qualified=True),
                 lambda r:r.update(production_qualified=True),lambda r:r['tests'].update(run=19),
                 lambda r:r['tests'].update(skipped=['omitted']),lambda r:r['tests']['names'].pop(),
                 lambda r:r['sources_before'].pop(gate.SOURCES[0]),lambda r:r['sources_after'].update({gate.SOURCES[0]:'0'*64}),
                 lambda r:r['log'].update(sha256='0'*64),lambda r:r['capture'].update(path='../outside.json')]
        for change in changes:
            r=deepcopy(self.receipt);change(r)
            with self.subTest(change=change),self.assertRaises(ValueError):gate.validate_receipt(r,self.root)

    def test_changed_source_cannot_complete(self):
        (self.root/gate.SOURCES[0]).write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):gate.validate_receipt(self.receipt,self.root)

    def test_rebound_capture_still_checks_gains_error_box_jacobian_and_covariance(self):
        changes=[lambda c:c['result'].update(input_digest='0'*64),
                 lambda c:c['result'].update(production_qualified=True),
                 lambda c:c['source']['dut'].update(id='wrong'),
                 lambda c:c['result']['coefficients'][0]['outward_gain'][1].update(real=1.1),
                 lambda c:c['result']['error_box']['s_parameters'][0][0][3].update(real=.2),
                 lambda c:c['result']['derived_network']['s_parameters'][0][0][1].update(real=.8),
                 lambda c:c['result']['sensitivity'][0].__setitem__(0,2.),
                 lambda c:c['result']['covariance'][0].__setitem__(0,float('nan')),
                 lambda c:c['result']['covariance'][0].__setitem__(0,.2)]
        for change in changes:
            capture=deepcopy(self.original);change(capture);self.capture.write_text(json.dumps(capture),encoding='utf-8')
            self.receipt['capture']['sha256']=gate.digest(self.capture)
            with self.subTest(change=change),self.assertRaises(ValueError):gate.validate_receipt(self.receipt,self.root)


if __name__=='__main__':unittest.main()
