# SPDX-License-Identifier: Apache-2.0
"""Actual worker contracts and independent small discrete selection oracle."""
import copy
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def request():
    prov={'kind':'supplied','source_id':'original-discrete-selection'}
    options=[{'id':part,'part_id':part,'unit_cost_minor':cost,'provenance':prov,
              'corners':[{'corner_id':'nominal','capacitance_f':cap,'esr_ohm':0.,'esl_h':0.}]}
             for part,cost,cap in [('small',1,100e-6),('large',3,470e-6)]]
    return {'contract':'spike/pdn-decap-selection-request/v1',
            'base_request':{'contract':'spike/pdn-network-request/v1','reference':'GND','nodes':['V'],
                            'elements':[{'id':'source','type':'resistor','positive':'V','negative':'GND',
                                         'resistance_ohm':1.,'provenance':prov}],
                            'ports':[{'id':'load','mode':'single','positive':'V','negative':'GND'}],
                            'frequencies_hz':[1000.,10000.],'load_transient':None},
            'corners':[{'id':'nominal','bias_voltage_v':1.,'temperature_k':300.}],
            'target_impedance_ohm_by_port':{'load':.5},
            'sites':[{'id':f'site{i}','positive':'V','negative':'GND','options':copy.deepcopy(options)}
                     for i in range(2)],
            'inventory':[{'part_id':'small','max_quantity':2},{'part_id':'large','max_quantity':1}],
            'budget_minor':3,'max_capacitors':2}


class DecapSelectionContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'pdn-decap-selection-{kind}-v1.schema.json').read_text()))
                         for kind in ('request','result')]

    def run_worker(self, req):
        return handle({'method':'run_pdn_decap_selection','params':{'request':req}})

    def test_actual_worker_complete_search_schema_and_independent_ranking(self):
        req=request(); before=copy.deepcopy(req)
        self.validators[0].validate(req)
        response=self.run_worker(req)
        self.assertTrue(response['ok'],response)
        result=response['result']; self.validators[1].validate(result)
        self.assertEqual(req,before)
        self.assertEqual(len(result['configurations']),8)
        self.assertFalse(result['production_qualified'])
        self.assertTrue(result['meets_target'])
        evaluated=[c for c in result['configurations'] if c['status']=='evaluated']
        self.assertEqual(len(evaluated),5)
        for config in evaluated:
            quantities=config['part_quantities']
            c=quantities.get('small',0)*100e-6+quantities.get('large',0)*470e-6
            ratio=1/math.sqrt(1+(2*math.pi*1000*c)**2)/.5
            self.assertAlmostEqual(config['worst_case']['target_ratio'],ratio,delta=1e-11)
            self.assertEqual(config['meets_target'],ratio<=1)
        feasible=[c for c in evaluated if c['meets_target']]
        winner=min(feasible,key=lambda c:(c['cost_minor'],c['worst_case']['target_ratio'],c['capacitor_count']))
        self.assertEqual(result['selected_id'],winner['id'])
        self.assertEqual(winner['part_quantities'],{'large':1})
        for config in result['configurations']:
            if config['status']=='constraint_rejected':
                self.assertIsNone(config['meets_target']); self.assertIsNone(config['worst_case'])
                self.assertIn('budget_exceeded',config['constraint_violations'])

    def test_unsatisfied_targets_retained_and_no_constraint_feasible_error(self):
        req=request(); req['target_impedance_ohm_by_port']['load']=.01
        response=self.run_worker(req); self.assertTrue(response['ok'],response)
        self.validators[1].validate(response['result'])
        self.assertFalse(response['result']['meets_target'])
        req['budget_minor']=0
        response=self.run_worker(req); self.assertFalse(response['ok'],response)
        self.assertNotIn('result',response)

    def test_schema_and_worker_reject_unknown_boolean_inconsistent_and_missing_part(self):
        for mutation in ('unknown','bool','inconsistent','inventory'):
            req=request()
            if mutation=='unknown': req['extra']=True
            elif mutation=='bool': req['budget_minor']=True
            elif mutation=='inconsistent': req['sites'][1]['options'][0]['unit_cost_minor']=2
            else: req['inventory'].pop()
            with self.subTest(mutation=mutation):
                self.assertFalse(self.run_worker(req)['ok'])
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))


if __name__=='__main__': unittest.main()
