# SPDX-License-Identifier: Apache-2.0
"""Actual schema/worker admission for an original finite dielectric plate."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.service import handle
from tests.python.test_pdn_electrostatic import plate, EPSILON_0


def lossy_plate():
    request=plate(2)
    request['contract']='spike/pdn-dielectric-ac-request/v1'
    request['frequencies_hz']=[1e3,1e6]
    request['materials'][0].update(conductivity_s_m=1e-8,loss_tangent=.02)
    return request


class DielectricAcContractTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[2]/'schemas/pdn-dielectric-ac-request-v1.schema.json'
        self.validator=Draft202012Validator(json.loads(path.read_text(encoding='utf-8')))

    def test_actual_plate_worker_and_offline_schema(self):
        request=lossy_plate(); self.validator.validate(request)
        response=handle({'method':'extract_pdn_dielectric_ac','params':{'request':request}})
        self.assertTrue(response['ok'],response)
        result=response['result']
        path=Path(__file__).resolve().parents[2]/'schemas/pdn-dielectric-ac-result-v1.schema.json'
        Draft202012Validator(json.loads(path.read_text(encoding='utf-8'))).validate(result)
        self.assertEqual(result['contract'],'spike/pdn-dielectric-ac-result/v1')
        self.assertEqual(result['model_status'],'experimental')
        self.assertIs(result['production_qualified'],False)
        self.assertEqual(result['nodes'],['load-terminal'])
        import math
        for point in result['ac']:
            expected=1e-8+2*math.pi*point['frequency_hz']*4*EPSILON_0*complex(.02,1)
            actual=point['admittance_s'][0][0]
            self.assertAlmostEqual(actual['real']/expected.real,1.,places=10)
            self.assertAlmostEqual(actual['imag']/expected.imag,1.,places=10)

    def test_schema_rejections_and_worker_error_boundary(self):
        request=lossy_plate()
        for mutation in ('missing_loss','negative_sigma','dc','unknown_field'):
            raw=copy.deepcopy(request)
            if mutation=='missing_loss': del raw['materials'][0]['loss_tangent']
            elif mutation=='negative_sigma': raw['materials'][0]['conductivity_s_m']=-1
            elif mutation=='dc': raw['frequencies_hz'][0]=0
            else: raw['repair_passivity']=True
            with self.subTest(mutation=mutation):
                self.assertTrue(list(self.validator.iter_errors(raw)))
                response=handle({'method':'extract_pdn_dielectric_ac','params':{'request':raw}})
                self.assertFalse(response['ok'],response)
        response=handle({'method':'extract_pdn_dielectric_ac','params':{'request':request,'executable':'untrusted'}})
        self.assertFalse(response['ok'])


if __name__=='__main__': unittest.main()
