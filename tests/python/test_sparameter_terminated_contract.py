# SPDX-License-Identifier: Apache-2.0
"""Real worker/schema acceptance against an original physical capacitor circuit."""
import copy
import json
import math
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def request():
    reference,capacitance,resistance=50.,1e-6,100.
    rate=1/(reference*capacitance)
    frequencies=[0.,100.,1000.,10000.,100000.]
    def pair(value): return {'real':value.real,'imag':value.imag}
    return {'contract':'spike/terminated-network-transient-request/v1',
            'fit_request':{'contract':'spike/sparameter-rational-fit-request/v1',
                           'source':{'id':'original-capacitor-reflection','port_names':['capacitor'],
                                     'reference_impedance_ohm':reference,'frequencies_hz':frequencies,
                                     's_parameters':[[[pair((rate-2j*math.pi*f)/(rate+2j*math.pi*f))]] for f in frequencies]},
                           'pole_rates_rad_s':[rate],'max_absolute_error':1e-12},
            'terminations':[{'port_name':'capacitor','resistance_ohm':resistance,
                             'voltage_points':[{'time_s':0.,'voltage_v':1.},{'time_s':.001,'voltage_v':1.}]}],
            'output_times_s':[0.,.00005,.0001,.0002,.001]}


class TerminatedContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'terminated-network-transient-{kind}-v1.schema.json').read_text()))
                         for kind in ('request','result')]

    def worker(self,req):
        return handle({'method':'run_terminated_network_transient','params':{'request':req}})

    def test_actual_worker_capacitor_charging_current_boundary_and_provenance(self):
        req=request(); before=copy.deepcopy(req); self.validators[0].validate(req)
        response=self.worker(req); self.assertTrue(response['ok'],response)
        out=response['result']; self.validators[1].validate(out)
        self.assertEqual(req,before); self.assertFalse(out['production_qualified'])
        self.assertEqual(out['fit_result']['source']['network'],before['fit_request']['source'])
        self.assertEqual(out['terminations'],before['terminations'])
        for row in out['points']:
            expected=-math.expm1(-row['time_s']/1e-4)
            voltage=row['port_voltage_v_by_port']['capacitor']
            current=row['port_current_a_by_port']['capacitor']
            self.assertAlmostEqual(voltage,expected,delta=2e-12)
            self.assertAlmostEqual(current,(1-expected)/100,delta=2e-14)
            self.assertAlmostEqual(voltage+100*current,1.,delta=2e-12)
            self.assertEqual(row['source_voltage_v_by_port']['capacitor'],1.)

    def test_actual_worker_rejects_invalid_resistance_port_time_and_unsupported_loop(self):
        for mutation in ('negative','boolean','port','time','ideal','unknown'):
            req=request()
            if mutation=='negative': req['terminations'][0]['resistance_ohm']=-1.
            elif mutation=='boolean': req['terminations'][0]['resistance_ohm']=True
            elif mutation=='port': req['terminations'][0]['port_name']='elsewhere'
            elif mutation=='time': req['output_times_s'].append(.002)
            elif mutation=='ideal': req['terminations'][0]['resistance_ohm']=0.
            else: req['extra']=1
            response=self.worker(req)
            with self.subTest(mutation=mutation):
                self.assertFalse(response['ok'],response); self.assertNotIn('result',response)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))

    def test_actual_worker_through_resistive_divider_and_well_posed_ideal_source(self):
        for source_resistance in (0.,25.):
            req=request(); source=req['fit_request']['source']; source['port_names']=['source','load']
            through=[[{'real':0.,'imag':0.},{'real':1.,'imag':0.}],
                     [{'real':1.,'imag':0.},{'real':0.,'imag':0.}]]
            source['s_parameters']=[copy.deepcopy(through) for _ in source['frequencies_hz']]
            req['terminations']=[{'port_name':name,'resistance_ohm':resistance,
                                   'voltage_points':[{'time_s':0.,'voltage_v':voltage},
                                                     {'time_s':.001,'voltage_v':voltage}]}
                                  for name,resistance,voltage in [('load',75.,0.),('source',source_resistance,2.)]]
            response=self.worker(req); self.assertTrue(response['ok'],response)
            out=response['result']; self.validators[1].validate(out)
            self.assertEqual(out['port_names'],['source','load'])
            expected_current=2/(source_resistance+75.)
            for row in out['points']:
                for port in ('source','load'):
                    self.assertAlmostEqual(row['port_voltage_v_by_port'][port],75*expected_current,delta=3e-12)
                self.assertAlmostEqual(row['port_current_a_by_port']['source'],expected_current,delta=3e-14)
                self.assertAlmostEqual(row['port_current_a_by_port']['load'],-expected_current,delta=3e-14)


if __name__=='__main__': unittest.main()
