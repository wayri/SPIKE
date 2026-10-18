# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema checks for original analytic prescribed-wave steps."""
import copy
import json
import math
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def request():
    rate=1000.
    def pair(value): return {'real':value.real,'imag':value.imag}
    frequencies=[0.,10.,100.,1000.]
    return {'contract':'spike/rational-network-transient-request/v1',
            'fit_request':{'contract':'spike/sparameter-rational-fit-request/v1',
                           'source':{'id':'original-step-witness','port_names':['input'],
                                     'reference_impedance_ohm':50.,'frequencies_hz':frequencies,
                                     's_parameters':[[[pair(.2+.6*rate/(rate+2j*math.pi*f))]] for f in frequencies]},
                           'pole_rates_rad_s':[rate],'max_absolute_error':1e-12},
            'incident_waves':[{'port_name':'input','points':[{'time_s':0.,'value_sqrt_w':1.},
                                                           {'time_s':.003,'value_sqrt_w':1.}]}],
            'output_times_s':[0.,.001,.003]}


class TransientContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'rational-network-transient-{kind}-v1.schema.json').read_text()))
                         for kind in ('request','result')]

    def worker(self,req):
        return handle({'method':'run_rational_network_transient','params':{'request':req}})

    def test_actual_worker_schema_step_feedthrough_voltage_current_and_snapshot(self):
        req=request(); before=copy.deepcopy(req); self.validators[0].validate(req)
        response=self.worker(req); self.assertTrue(response['ok'],response)
        out=response['result']; self.validators[1].validate(out)
        self.assertEqual(req,before); self.assertFalse(out['production_qualified'])
        self.assertEqual(out['fit_result']['source']['network'],req['fit_request']['source'])
        self.assertEqual(out['incident_waves'],req['incident_waves'])
        for row in out['points']:
            expected=.2+.6*(-math.expm1(-1000*row['time_s']))
            self.assertAlmostEqual(row['outgoing_wave_sqrt_w_by_port']['input'],expected,delta=3e-14)
            self.assertAlmostEqual(row['port_voltage_v_by_port']['input'],math.sqrt(50)*(1+expected),delta=3e-13)
            self.assertAlmostEqual(row['port_current_a_by_port']['input'],(1-expected)/math.sqrt(50),delta=3e-14)
        self.assertAlmostEqual(out['final_state_sqrt_w'][0][0],-math.expm1(-3),delta=3e-14)

    def test_actual_worker_rejects_port_time_boolean_unknown_and_failed_fit(self):
        for mutation in ('port','time','boolean','unknown','fit'):
            req=request()
            if mutation=='port': req['incident_waves'][0]['port_name']='elsewhere'
            elif mutation=='time': req['output_times_s'].append(.004)
            elif mutation=='boolean': req['incident_waves'][0]['points'][0]['value_sqrt_w']=True
            elif mutation=='unknown': req['extra']=1
            else: req['fit_request']['pole_rates_rad_s'][0]*=2
            response=self.worker(req)
            with self.subTest(mutation=mutation):
                self.assertFalse(response['ok'],response); self.assertNotIn('result',response)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))

    def test_actual_worker_simultaneous_inputs_preserve_source_port_order(self):
        req=request(); source=req['fit_request']['source']; source['port_names']=['A','B']
        direct=[[.1,.2],[.3,.05]]; residue=[[.4,.1],[-.2,.3]]
        def pair(value): return {'real':value.real,'imag':value.imag}
        source['s_parameters']=[[[pair(direct[i][j]+residue[i][j]*1000/(1000+2j*math.pi*f))
                                 for j in range(2)] for i in range(2)] for f in source['frequencies_hz']]
        req['incident_waves']=[{'port_name':port,'points':[{'time_s':0.,'value_sqrt_w':value},
                                                          {'time_s':.003,'value_sqrt_w':value}]}
                               for port,value in [('B',-.5),('A',1.)]]
        response=self.worker(req); self.assertTrue(response['ok'],response)
        out=response['result']; self.validators[1].validate(out)
        self.assertEqual(out['port_names'],['A','B'])
        self.assertEqual(out['incident_waves'],req['incident_waves'])
        for point in out['points']:
            growth=-math.expm1(-1000*point['time_s'])
            self.assertEqual(point['incident_wave_sqrt_w_by_port'],{'A':1.,'B':-.5})
            self.assertAlmostEqual(point['outgoing_wave_sqrt_w_by_port']['A'],.35*growth,delta=4e-14)
            self.assertAlmostEqual(point['outgoing_wave_sqrt_w_by_port']['B'],.275-.35*growth,delta=4e-14)


if __name__=='__main__': unittest.main()
