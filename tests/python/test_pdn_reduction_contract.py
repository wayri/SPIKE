# SPDX-License-Identifier: Apache-2.0
"""Actual extracted samples to passive reduction through the owned worker."""
import copy
import json
import math
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.pdn_dielectric_ac import extract_pdn_dielectric_ac
from python.spike_core.pdn_admittance_reduction import dielectric_admittance_source
from python.spike_core.service import handle
from tests.python.test_pdn_dielectric_ac_contract import lossy_plate, EPSILON_0


def extracted_request():
    raw=lossy_plate()
    raw['electrodes'].insert(1,{'id':'middle','node':'middle-node',
        'vertices':[i for i,p in enumerate(raw['mesh']['vertices']) if p[0]==.5]})
    source=dielectric_admittance_source(extract_pdn_dielectric_ac(raw))
    return {'contract':'spike/pdn-admittance-reduction-request/v1','source':source,
            'retained_nodes':['load-terminal'],'eliminated_nodes':['middle-node'],
            'termination_admittance_s':[[[{'real':1e-6,'imag':0.}]]] * len(source['frequencies_hz'])}


class ReductionContractTests(unittest.TestCase):
    def test_actual_extraction_worker_and_schema(self):
        request=extracted_request()
        root=Path(__file__).resolve().parents[2]
        schema=json.loads((root/'schemas/pdn-admittance-reduction-request-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(request)
        old=copy.deepcopy(request)
        response=handle({'method':'reduce_pdn_admittance','params':{'request':request}})
        self.assertTrue(response['ok'],response)
        result=response['result']
        schema=json.loads((root/'schemas/pdn-admittance-reduction-result-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(result)
        self.assertEqual(request,old)
        self.assertEqual(result['model_status'],'experimental')
        self.assertIs(result['production_qualified'],False)
        self.assertEqual(result['nodes'],['load-terminal'])
        self.assertEqual(result['reference_node'],'return-terminal')
        for frequency,matrix in zip(result['frequencies_hz'],result['admittance_s']):
            gamma=1e-8+2*math.pi*frequency*4*EPSILON_0*complex(.02,1)
            expected=2*gamma-4*gamma*gamma/(4*gamma+1e-6)
            value=matrix[0][0]
            self.assertLess(abs(complex(value['real'],value['imag'])/expected-1),1e-10)

    def test_owned_worker_rejects_bad_partition_and_active_load(self):
        for mutation in ('partition','active','unknown_field'):
            raw=extracted_request()
            if mutation=='partition': raw['eliminated_nodes']=['load-terminal']
            elif mutation=='active': raw['termination_admittance_s'][0][0][0]['real']=-1.
            else: raw['repair']=True
            with self.subTest(mutation=mutation):
                response=handle({'method':'reduce_pdn_admittance','params':{'request':raw}})
                self.assertFalse(response['ok'],response)


if __name__=='__main__': unittest.main()
