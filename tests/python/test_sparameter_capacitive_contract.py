# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema acceptance with an independently derived RC load reference."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
from python.spike_core.service import handle
from examples.capacitive_network_transient.run_rc import request

ROOT=Path(__file__).resolve().parents[2]


class CapacitiveContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'capacitive-network-transient-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                         for kind in ('request','result')]

    def test_worker_rc_source_split_energy_power_and_original_provenance(self):
        raw=request();before=deepcopy(raw);self.validators[0].validate(raw)
        out=handle({'method':'run_capacitive_network_transient','params':{'request':raw}})
        self.assertTrue(out['ok'],out);result=out['result'];self.validators[1].validate(result)
        self.assertEqual(raw,before);self.assertFalse(result['production_qualified'])
        self.assertEqual(result['fit_result']['source']['network'],raw['fit_request']['source'])
        self.assertEqual(result['terminations'],raw['terminations'])
        digest=hashlib.sha256(json.dumps(raw,sort_keys=True,allow_nan=False,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'],digest)
        tau=(25.*75./100.)*1e-5
        for row in result['points']:
            t=row['time_s'];voltage=1.5*(-math.expm1(-t/tau))
            derivative=1.5/tau*math.exp(-t/tau)
            actual_v=row['port_voltage_v_by_port']['receiver'];network_i=row['port_current_a_by_port']['receiver']
            source_i=row['source_current_a_by_port']['receiver']
            self.assertAlmostEqual(actual_v,voltage,delta=2e-11)
            self.assertAlmostEqual(network_i,voltage/75.,delta=2e-12)
            self.assertAlmostEqual(source_i,(2-voltage)/25.,delta=2e-12)
            self.assertAlmostEqual(row['capacitor_voltage_derivative_v_per_s_by_port']['receiver'],derivative,delta=2e-8)
            self.assertAlmostEqual(row['capacitor_voltage_v_by_port']['receiver'],actual_v,delta=2e-12)
            self.assertAlmostEqual(source_i-network_i,1e-5*derivative,delta=2e-12)
            power=row['termination_resistor_power_w_by_port']['receiver']
            self.assertAlmostEqual(power,25.*source_i**2,delta=2e-12)
            self.assertAlmostEqual(row['capacitor_energy_j_by_port']['receiver'],.5e-5*voltage**2,delta=2e-15)
            self.assertAlmostEqual(2*source_i-actual_v*network_i-power-1e-5*actual_v*derivative,0.,delta=2e-12)

    def test_worker_and_schema_fail_closed_on_unsupported_capacitive_boundaries(self):
        for mutation in ('negative','boolean','infinite','zero','ideal','missing','unknown','port'):
            raw=request();term=raw['terminations'][0]
            if mutation=='negative':term['capacitance_f']=-1.
            if mutation=='boolean':term['capacitance_f']=True
            if mutation=='infinite':term['capacitance_f']=float('inf')
            if mutation=='zero':term['capacitance_f']=0.
            if mutation=='ideal':term['resistance_ohm']=0.
            if mutation=='missing':term.pop('capacitance_f')
            if mutation=='unknown':term['inductance_h']=1e-3
            if mutation=='port':term['port_name']='other'
            out=handle({'method':'run_capacitive_network_transient','params':{'request':raw}})
            with self.subTest(mutation=mutation):
                self.assertFalse(out['ok'],out);self.assertNotIn('result',out)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))
        raw=request();raw['terminations'][0]['resistance_ohm']=0.
        self.assertTrue(list(self.validators[0].iter_errors(raw)))

    def test_example_runs_and_public_contracts_are_registered(self):
        out=subprocess.run([sys.executable,str(ROOT/'examples/capacitive_network_transient/run_rc.py')],
                           cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(out.returncode,0,out.stderr)
        self.assertEqual(json.loads(out.stdout)['contract'],'spike/capacitive-network-transient-result/v1')
        catalog=json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request','result'):
            self.assertEqual(catalog[f'spike/capacitive-network-transient-{kind}/v1'],f'capacitive-network-transient-{kind}-v1.schema.json')
