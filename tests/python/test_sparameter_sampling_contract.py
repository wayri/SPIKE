# SPDX-License-Identifier: Apache-2.0
"""Actual worker and schemas for explicit supplied-DC sampled network grids."""
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
    # Original one-port RC reflection samples: S=(Z-R0)/(Z+R0), Z=1/(jwC).
    def rc(f):
        term=2j*3.141592653589793*f*50e-6
        return (1-term)/(1+term)
    return {'contract':'spike/sparameter-resampling-request/v1',
            'source':{'id':'original-rc-reflection','port_names':['input'],
                      'reference_impedance_ohm':50.,'frequencies_hz':[1000.,3000.],
                      's_parameters':[[[pair(rc(f))]] for f in (1000.,3000.)]},
            'target_frequencies_hz':[0.,500.,1000.,2000.,3000.],
            'dc_policy':{'mode':'supplied','s_parameters':[[pair(1+0j)]]}}


class SamplingContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'sparameter-resampling-{kind}-v1.schema.json').read_text()))
                         for kind in ('request','result')]

    def worker(self,req):
        return handle({'method':'resample_sparameter_network','params':{'request':req}})

    def test_actual_worker_schema_dc_provenance_and_exact_samples(self):
        req=request(); before=copy.deepcopy(req)
        self.validators[0].validate(req)
        response=self.worker(req); self.assertTrue(response['ok'],response)
        result=response['result']; self.validators[1].validate(result)
        self.assertEqual(req,before)
        self.assertEqual(result['source']['network'],before['source'])
        self.assertEqual(result['dc_policy'],before['dc_policy'])
        self.assertFalse(result['production_qualified'])
        samples=result['derived_network']['s_parameters']
        self.assertEqual(samples[0],req['dc_policy']['s_parameters'])
        self.assertEqual(samples[2],req['source']['s_parameters'][0])
        self.assertEqual(samples[4],req['source']['s_parameters'][1])
        for component in ('real','imag'):
            low=req['source']['s_parameters'][0][0][0][component]
            high=req['source']['s_parameters'][1][0][0][component]
            self.assertAlmostEqual(samples[3][0][0][component],(low+high)/2,delta=1e-15)
        self.assertEqual([row['kind'] for row in result['diagnostics']],
                         ['supplied_dc','linear_interpolation','source_sample','linear_interpolation','source_sample'])
        self.assertTrue(all(row['smax']<=1+1e-14 for row in result['diagnostics']))

    def test_actual_worker_rejects_extrapolation_implicit_dc_and_invalid_policy(self):
        for mutation in ('high','missing_dc','complex_dc','unknown','boolean','shape'):
            req=request()
            if mutation=='high': req['target_frequencies_hz'][-1]=4000.
            elif mutation=='missing_dc': req['dc_policy']={'mode':'require_source'}
            elif mutation=='complex_dc': req['dc_policy']['s_parameters'][0][0]['imag']=.1
            elif mutation=='unknown': req['extra']=1
            elif mutation=='boolean': req['source']['s_parameters'][0][0][0]['real']=True
            else: req['dc_policy']['s_parameters'].append([pair(0j)])
            response=self.worker(req)
            with self.subTest(mutation=mutation):
                self.assertFalse(response['ok'],response); self.assertNotIn('result',response)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))


if __name__=='__main__': unittest.main()
