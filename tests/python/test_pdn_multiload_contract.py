# SPDX-License-Identifier: Apache-2.0
"""Exercise JSON schema and actual owned worker for original shared-return loads."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.service import handle
from tests.python.test_pdn_network import basic, element


def shared_return_request():
    return basic([
        element('a','resistor',positive='A',negative='R',resistance_ohm=2.),
        element('b','resistor',positive='B',negative='R',resistance_ohm=3.),
        element('return','resistor',positive='R',negative='GND',resistance_ohm=.5)],
        nodes=['A','B','R'],ports=[{'id':p,'mode':'single','positive':p,'negative':'GND'} for p in ('A','B')],
        transient={'loads':[
            {'port_id':'A','points':[{'time_s':0.,'current_a':0.},{'time_s':1.,'current_a':1.},{'time_s':2.,'current_a':1.}]},
            {'port_id':'B','points':[{'time_s':0.,'current_a':0.},{'time_s':.5,'current_a':1.},{'time_s':2.,'current_a':1.}]}],
            'output_times_s':[0.,.5,1.,2.],'max_step_s':.125})


class MultiLoadContractTests(unittest.TestCase):
    def setUp(self):
        schema=Path(__file__).resolve().parents[2]/'schemas/pdn-network-request-v1.schema.json'
        self.validator=Draft202012Validator(json.loads(schema.read_text(encoding='utf-8')))

    def test_schema_and_owned_worker_shared_return(self):
        request=shared_return_request()
        self.validator.validate(request)
        for method in ('validate_pdn_network','evaluate_pdn_network'):
            response=handle({'method':method,'params':{'request':request}})
            self.assertTrue(response['ok'],response)
        transient=response['result']['load_transient']
        self.assertEqual(transient['load_port_ids'],['A','B'])
        point=transient['points'][-1]
        self.assertEqual(point['load_current_a_by_port'],{'A':1.,'B':1.})
        self.assertAlmostEqual(point['node_voltage_v']['R'],-1.)
        self.assertAlmostEqual(point['port_voltage_v']['A'],-3.)
        self.assertAlmostEqual(point['port_voltage_v']['B'],-4.)

    def test_schema_rejects_ambiguous_forms_and_typed_admission_rejects_identity(self):
        request=shared_return_request()
        invalid=copy.deepcopy(request); invalid['load_transient']['port_id']='A'
        self.assertTrue(list(self.validator.iter_errors(invalid)))
        for mutation in ('duplicate','unknown','horizon','initial'):
            invalid=copy.deepcopy(request); loads=invalid['load_transient']['loads']
            if mutation=='duplicate': loads[1]['port_id']='A'
            elif mutation=='unknown': loads[1]['port_id']='elsewhere'
            elif mutation=='horizon': loads[1]['points'][-1]['time_s']=3.
            else: loads[1]['points'][0]['current_a']=1.
            self.validator.validate(invalid)
            response=handle({'method':'validate_pdn_network','params':{'request':invalid}})
            with self.subTest(mutation=mutation): self.assertFalse(response['ok'],response)


if __name__=='__main__': unittest.main()
