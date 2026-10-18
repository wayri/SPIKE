# SPDX-License-Identifier: Apache-2.0
"""Actual worker/CLI with independent physical spatial-chain references."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm
from jsonschema import Draft202012Validator

from examples.rlgc_line_cascade.run_line import request
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def value(p):return complex(p['real'],p['imag'])


class CascadeContractTests(unittest.TestCase):
    def validators(self):
        return [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlgc-line-cascade-{kind}-v1.schema.json').read_text(encoding='utf-8'))) for kind in ('request','result')]

    def test_worker_independent_spatial_chain_fields_loss_and_identity(self):
        raw=request();before=deepcopy(raw);validators=self.validators();validators[0].validate(raw)
        response=handle({'method':'run_rlgc_line_cascade','params':{'request':raw}})
        self.assertTrue(response['ok'],response);out=response['result'];validators[1].validate(out)
        self.assertEqual(raw,before);self.assertEqual(out['source_request'],raw);self.assertFalse(out['production_qualified'])
        digest=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest();self.assertEqual(out['input_digest'],digest)
        self.assertEqual([s['id'] for s in out['sections']],[s['id'] for s in raw['sections']])
        for original,child in zip(raw['sections'],out['sections']):
            self.assertEqual(child['result']['source_request']['line_request'],original['line_request'])
            self.assertEqual(child['result']['source_request']['probes'],original['probes'])
        ref=raw['sections'][0]['line_request']['reference_impedance_ohm'];root=np.sqrt(ref)
        for k,(drive,point,matrix) in enumerate(zip(raw['excitations'],out['points'],out['network']['s_parameters'])):
            operators=[];chains=[]
            for section in raw['sections']:
                line=section['line_request'];sample=line['samples'][k];w=2*np.pi*sample['frequency_hz']
                m=np.array([[0,sample['resistance_ohm_per_m']+1j*w*line['inductance_h_per_m']],[sample['conductance_s_per_m']+1j*w*line['capacitance_f_per_m'],0]],complex)
                operators.append(m);chains.append(expm(m*line['length_m']))
            chain=np.eye(2,dtype=complex)
            for local in chains:chain=chain@local
            boundary=np.vstack((np.array([1,ref])@chain,[1,-ref]))
            right_basis=np.linalg.solve(boundary,2*root*np.eye(2));left_basis=chain@right_basis
            reference=np.vstack(((np.array([1,-ref])@left_basis)/(2*root),(np.array([1,ref])@right_basis)/(2*root)))
            actual=np.array([[value(p) for p in row] for row in matrix]);np.testing.assert_allclose(actual,reference,atol=2e-12,rtol=1e-10)
            incident=np.array([value(drive['incident_left']),value(drive['incident_right'])]);left=left_basis@incident
            conductor=dielectric=0.
            for j,(section,child,m) in enumerate(zip(raw['sections'],out['sections'],operators)):
                line=section['line_request'];sample=line['samples'][k];length=line['length_m'];state=left.copy()
                def fields(x):return expm(-m*x)@state
                for p in child['result']['points'][k]['probe_values']:
                    v,i=fields(length*p['fractional_position'])
                    np.testing.assert_allclose([value(p['voltage_v']),value(p['current_left_to_right_a'])],[v,i],atol=3e-11,rtol=1e-10)
                conductor+=sample['resistance_ohm_per_m']*quad(lambda x:abs(fields(x)[1])**2,0,length,epsabs=1e-13)[0]
                dielectric+=sample['conductance_s_per_m']*quad(lambda x:abs(fields(x)[0])**2,0,length,epsabs=1e-13)[0]
                left=fields(length)
            ledger=point['power_balance']
            for key,expected in [('conductor_loss_w',conductor),('dielectric_loss_w',dielectric),('total_loss_w',conductor+dielectric)]:self.assertAlmostEqual(ledger[key],expected,delta=2e-12+1e-10*abs(expected))
            self.assertAlmostEqual(ledger['net_input_w'],float(np.vdot(incident,incident).real-np.vdot(reference@incident,reference@incident).real),delta=2e-11)
            self.assertEqual(ledger['residual_w'],ledger['net_input_w']-ledger['total_loss_w'])
            for junction in point['junctions']:
                self.assertLess(abs(value(junction['voltage_residual_v'])),3e-11)
                self.assertLess(abs(value(junction['current_residual_a'])),3e-12)
                self.assertLess(abs(junction['power_residual_w']),2e-11)

    def test_actual_cli_and_example_emit_registered_result(self):
        validators=self.validators();catalog=json.loads((ROOT/'schemas/manifest.json').read_text())
        for kind in ('request','result'):self.assertEqual(catalog['schemas'][f'spike/rlgc-line-cascade-{kind}/v1'],f'rlgc-line-cascade-{kind}-v1.schema.json')
        example=subprocess.run([sys.executable,str(ROOT/'examples/rlgc_line_cascade/run_line.py')],cwd=ROOT,capture_output=True,text=True,check=True,timeout=60);validators[1].validate(json.loads(example.stdout))
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as folder:
            output=Path(folder)/'result.json'
            completed=subprocess.run([sys.executable,'-m','python.spike_core.cli','--quiet','--output',str(output),'rlgc-cascade',str(ROOT/'examples/rlgc_line_cascade/three-sections.request.json')],cwd=ROOT,capture_output=True,text=True,timeout=60)
            self.assertEqual(completed.returncode,0,completed.stderr);validators[1].validate(json.loads(output.read_text()))

    def test_strict_schema_and_worker_fail_closed_on_invalid_section(self):
        validator=self.validators()[0]
        for mutation in ('empty','bool','extra','contract'):
            raw=request()
            if mutation=='empty':raw['sections']=[]
            elif mutation=='bool':raw['sections'][0]['line_request']['length_m']=True
            elif mutation=='extra':raw['sections'][0]['unknown']=0
            else:raw['contract']='unsupported'
            self.assertFalse(validator.is_valid(raw));self.assertFalse(handle({'method':'run_rlgc_line_cascade','params':{'request':raw}})['ok'])
        raw=request();raw['sections'][1]['line_request']['reference_impedance_ohm']=75
        self.assertFalse(handle({'method':'run_rlgc_line_cascade','params':{'request':raw}})['ok'])


if __name__=='__main__':unittest.main()
