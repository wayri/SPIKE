# SPDX-License-Identifier: Apache-2.0
"""Actual worker contracts for original analytic supplied-pole networks."""
import copy
import json
import math
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def pair(value):
    return {'real':value.real,'imag':value.imag}


def request():
    rate=2*math.pi*1000.
    frequencies=[0.,100.,1000.,10000.,100000.]
    return {'contract':'spike/sparameter-rational-fit-request/v1',
            'source':{'id':'original-one-pole-network','port_names':['input'],
                      'reference_impedance_ohm':50.,'frequencies_hz':frequencies,
                      's_parameters':[[[pair(.2+.6*rate/(rate+2j*math.pi*f))]] for f in frequencies]},
            'pole_rates_rad_s':[rate],'max_absolute_error':1e-12}


class RationalContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'sparameter-rational-fit-{kind}-v1.schema.json').read_text()))
                         for kind in ('request','result')]

    def worker(self,req):
        return handle({'method':'fit_sparameter_rational','params':{'request':req}})

    def test_actual_worker_schema_coefficients_source_and_error_limit(self):
        req=request(); before=copy.deepcopy(req)
        self.validators[0].validate(req)
        response=self.worker(req); self.assertTrue(response['ok'],response)
        result=response['result']; self.validators[1].validate(result)
        self.assertEqual(req,before); self.assertEqual(result['source']['network'],before['source'])
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['pole_rates_rad_s'],before['pole_rates_rad_s'])
        self.assertAlmostEqual(result['model']['direct'][0][0],.2,delta=2e-14)
        self.assertAlmostEqual(result['model']['residues'][0][0][0],.6,delta=2e-14)
        self.assertLessEqual(result['diagnostics']['max_absolute_error'],req['max_absolute_error'])
        self.assertAlmostEqual(result['diagnostics']['conservative_passivity_bound'],.8,delta=2e-14)

    def test_active_nonreciprocal_model_is_retained(self):
        req=request(); rate=req['pole_rates_rad_s'][0]
        req['source']['port_names']=['left','right']
        req['source']['s_parameters']=[[[pair(0j),pair(.4*rate/(rate+2j*math.pi*f))],
                                        [pair(1.4*rate/(rate+2j*math.pi*f)),pair(0j)]]
                                       for f in req['source']['frequencies_hz']]
        response=self.worker(req); self.assertTrue(response['ok'],response)
        result=response['result']; self.validators[1].validate(result)
        self.assertGreater(result['diagnostics']['sampled_smax_max'],1.)
        self.assertGreater(result['diagnostics']['conservative_passivity_bound'],1.)
        self.assertAlmostEqual(result['model']['residues'][0][1][0],1.4,delta=3e-14)
        self.assertAlmostEqual(result['model']['residues'][0][0][1],.4,delta=3e-14)

    def test_worker_rejects_bad_pole_dc_unknown_and_inaccurate_fit(self):
        for mutation in ('pole','dc','unknown','fit'):
            req=request()
            if mutation=='pole': req['pole_rates_rad_s'][0]=True
            elif mutation=='dc': req['source']['s_parameters'][0][0][0]['imag']=.01
            elif mutation=='unknown': req['extra']=1
            else: req['pole_rates_rad_s'][0]*=2
            response=self.worker(req)
            with self.subTest(mutation=mutation):
                self.assertFalse(response['ok'],response); self.assertNotIn('result',response)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))


if __name__=='__main__': unittest.main()
