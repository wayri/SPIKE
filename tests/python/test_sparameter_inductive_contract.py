# SPDX-License-Identifier: Apache-2.0
"""Actual worker/schema acceptance with an independently derived physical RLC."""
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
from examples.inductive_network_transient.run_rlc import request

ROOT=Path(__file__).resolve().parents[2]


class InductiveContractTests(unittest.TestCase):
    def setUp(self):
        self.validators=[Draft202012Validator(json.loads((ROOT/'schemas'/f'inductive-network-transient-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                         for kind in ('request','result')]

    def test_actual_worker_rlc_voltage_current_derivative_energy_and_lineage(self):
        raw=request();before=deepcopy(raw)
        self.validators[0].validate(raw)
        out=handle({'method':'run_inductive_network_transient','params':{'request':raw}})
        self.assertTrue(out['ok'],out);result=out['result'];self.validators[1].validate(result)
        self.assertEqual(raw,before)
        self.assertFalse(result['production_qualified'])
        self.assertEqual(result['fit_result']['source']['network'],raw['fit_request']['source'])
        self.assertEqual(result['terminations'],raw['terminations'])
        expected_digest=hashlib.sha256(json.dumps(raw,sort_keys=True,allow_nan=False,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'],expected_digest)
        resistance,inductance,capacitance=10.,100e-6,1e-6
        alpha=resistance/(2*inductance);wd=math.sqrt(1/(inductance*capacitance)-alpha**2)
        for row in result['points']:
            t=row['time_s'];decay=math.exp(-alpha*t)
            v=1-decay*(math.cos(wd*t)+alpha/wd*math.sin(wd*t))
            current=decay*math.sin(wd*t)/(inductance*wd)
            actual_v=row['port_voltage_v_by_port']['capacitor'];actual_i=row['port_current_a_by_port']['capacitor']
            self.assertAlmostEqual(actual_v,v,delta=2e-11)
            self.assertAlmostEqual(actual_i,current,delta=2e-12)
            self.assertAlmostEqual(row['inductor_current_a_by_port']['capacitor'],actual_i,delta=2e-13)
            derivative=row['inductor_current_derivative_a_per_s_by_port']['capacitor']
            self.assertAlmostEqual(actual_v+resistance*actual_i+inductance*derivative,1.,delta=2e-11)
            self.assertAlmostEqual(row['termination_resistor_power_w_by_port']['capacitor'],resistance*current**2,delta=2e-12)
            self.assertAlmostEqual(row['inductor_energy_j_by_port']['capacitor'],.5*inductance*current**2,delta=2e-15)
            self.assertAlmostEqual(actual_i-actual_v*actual_i-
                                   row['termination_resistor_power_w_by_port']['capacitor']-
                                   inductance*row['inductor_current_a_by_port']['capacitor']*derivative,
                                   0.,delta=2e-12)

    def test_worker_rejects_invalid_boundary_and_does_not_return_partial_result(self):
        for mutation in ('negative','boolean','infinite','all_zero','missing','unknown','port','marginal'):
            raw=request();term=raw['terminations'][0]
            if mutation=='negative':term['inductance_h']=-1.
            if mutation=='boolean':term['inductance_h']=True
            if mutation=='infinite':term['inductance_h']=float('inf')
            if mutation=='all_zero':term['inductance_h']=0.
            if mutation=='missing':term.pop('inductance_h')
            if mutation=='unknown':term['capacitance_f']=1e-6
            if mutation=='port':term['port_name']='other'
            if mutation=='marginal':term['resistance_ohm']=0.
            out=handle({'method':'run_inductive_network_transient','params':{'request':raw}})
            with self.subTest(mutation=mutation):
                self.assertFalse(out['ok'],out);self.assertNotIn('result',out)
        self.assertTrue(list(self.validators[0].iter_errors(request()|{'extra':1})))

    def test_example_executes_and_schema_catalog_registers_both_contracts(self):
        out=subprocess.run([sys.executable,str(ROOT/'examples/inductive_network_transient/run_rlc.py')],
                           cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(out.returncode,0,out.stderr)
        result=json.loads(out.stdout);self.assertEqual(result['contract'],'spike/inductive-network-transient-result/v1')
        self.assertEqual(len(result['points']),10)
        catalog=json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))['schemas']
        for kind in ('request','result'):
            name=f'inductive-network-transient-{kind}-v1.schema.json'
            self.assertEqual(catalog[f'spike/inductive-network-transient-{kind}/v1'],name)
