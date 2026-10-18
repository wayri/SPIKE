# SPDX-License-Identifier: Apache-2.0
"""Actual worker and schemas checked against an original matched-wave oracle."""
import cmath
import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def pair(value):
    return {'real':value.real,'imag':value.imag}


def request():
    frequencies=[0.,1e6,3.7e6]
    def network(identity,names,forward,reverse,delay):
        return {'id':identity,'port_names':names,'reference_impedance_ohm':50.,
                'frequencies_hz':frequencies[:],
                's_parameters':[[[pair(0j),pair(reverse*cmath.exp(-2j*cmath.pi*f*delay))],
                                 [pair(forward*cmath.exp(-2j*cmath.pi*f*delay)),pair(0j)]]
                                for f in frequencies]}
    return {'contract':'spike/two-port-deembedding-request/v1',
            'measured':network('measured',['outer-left','outer-right'],.8*1.2*.9,.8*.7*.9,6e-9),
            'left_fixture':network('left',['outer-left','dut-left'],.8,.8,2e-9),
            'right_fixture':network('right',['dut-right','outer-right'],.9,.9,3e-9)}


class DeembeddingContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'two-port-deembedding-{kind}-v1.schema.json').read_text()))
                         for kind in ('request','result')]

    def worker(self,req):
        return handle({'method':'deembed_two_port','params':{'request':req}})

    def test_actual_worker_schema_active_nonreciprocal_dut_and_source_preservation(self):
        req=request(); before=copy.deepcopy(req)
        self.validators[0].validate(req)
        response=self.worker(req); self.assertTrue(response['ok'],response)
        result=response['result']; self.validators[1].validate(result)
        self.assertEqual(req,before)
        self.assertFalse(result['production_qualified'])
        for key in ('measured','left_fixture','right_fixture'):
            self.assertEqual(result['sources'][key]['network'],before[key])
        self.assertTrue(all(row['smax']>1. for row in result['diagnostics']))
        self.assertTrue(all(row['reconstruction_residual']<=1e-10 for row in result['diagnostics']))
        network=result['derived_network']
        self.assertEqual(network['port_names'],['dut-left','dut-right'])
        self.assertEqual(network['frequencies_hz'],[0.,1e6,3.7e6])
        for f,matrix in zip(network['frequencies_hz'],network['s_parameters']):
            phase=cmath.exp(-2j*cmath.pi*f*1e-9)
            for r,c,value in ((0,0,0j),(1,1,0j),(1,0,1.2*phase),(0,1,.7*phase)):
                actual=complex(matrix[r][c]['real'],matrix[r][c]['imag'])
                self.assertAlmostEqual(abs(actual-value),0.,delta=2e-12)

    def test_actual_worker_rejects_orientation_grid_reference_and_unknown_fields(self):
        for mutation in ('orientation','grid','reference','unknown','boolean'):
            req=request()
            if mutation=='orientation': req['right_fixture']['port_names'].reverse()
            elif mutation=='grid': req['left_fixture']['frequencies_hz'][1]=2e6
            elif mutation=='reference': req['left_fixture']['reference_impedance_ohm']=75.
            elif mutation=='unknown': req['extra']=1
            else: req['measured']['s_parameters'][0][0][0]['real']=True
            response=self.worker(req)
            with self.subTest(mutation=mutation):
                self.assertFalse(response['ok'],response); self.assertNotIn('result',response)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))

    def test_ideal_through_fixtures_need_no_impedance_conversion(self):
        req=request()
        through=[[pair(0j),pair(1+0j)],[pair(1+0j),pair(0j)]]
        dut=[[pair(.2+0j),pair(.6+.1j)],[pair(.9-.1j),pair(-.1+0j)]]
        for fixture in ('left_fixture','right_fixture'):
            req[fixture]['s_parameters']=[copy.deepcopy(through) for _ in range(3)]
        req['measured']['s_parameters']=[copy.deepcopy(dut) for _ in range(3)]
        response=self.worker(req); self.assertTrue(response['ok'],response)
        self.validators[1].validate(response['result'])
        for sample in response['result']['derived_network']['s_parameters']:
            for row in range(2):
                for column in range(2):
                    for component in ('real','imag'):
                        self.assertAlmostEqual(sample[row][column][component],dut[row][column][component],delta=2e-15)


if __name__=='__main__': unittest.main()
