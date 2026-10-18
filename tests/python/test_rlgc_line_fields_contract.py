# SPDX-License-Identifier: Apache-2.0
"""Independent driven spatial circuit and distributed RMS loss at worker boundary."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
import numpy as np
from scipy.integrate import quad
from scipy.linalg import expm

from examples.rlgc_line_fields.run_line import request
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


def complex_value(pair):return complex(pair['real'],pair['imag'])


class RLGCFieldsContractTests(unittest.TestCase):
    def validators(self):
        return [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlgc-line-fields-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                for kind in ('request','result')]

    def test_worker_independent_spatial_fields_quadrature_and_identity(self):
        raw=request();before=deepcopy(raw);validators=self.validators();validators[0].validate(raw)
        response=handle({'method':'run_rlgc_line_fields','params':{'request':raw}})
        self.assertTrue(response['ok'],response);result=response['result'];validators[1].validate(result)
        self.assertEqual(raw,before);self.assertEqual(result['source_request'],raw)
        digest=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'],digest);self.assertFalse(result['production_qualified'])
        self.assertEqual(result['network']['port_names'],['left','right'])
        line=raw['line_request'];ref=line['reference_impedance_ohm'];root=np.sqrt(ref)
        plus=np.array([root,1/root]);minus=np.array([root,-1/root]);length=line['length_m']
        for row,sample,drive in zip(result['points'],line['samples'],raw['excitations']):
            w=2*np.pi*sample['frequency_hz'];z=sample['resistance_ohm_per_m']+1j*w*line['inductance_h_per_m']
            y=sample['conductance_s_per_m']+1j*w*line['capacitance_f_per_m'];operator=np.array([[0,z],[y,0]],complex)
            transfer=expm(-length*operator)
            scattering=np.linalg.solve(np.column_stack((-transfer@minus,plus)),np.column_stack((transfer@plus,-minus)))
            incident=np.array([complex_value(drive['incident_left']),complex_value(drive['incident_right'])]);outgoing=scattering@incident
            initial=plus*incident[0]+minus*outgoing[0]
            def state(x):return expm(-x*operator)@initial
            for actual,probe in zip(row['probe_values'],raw['probes']):
                v,i=state(length*probe['fractional_position'])
                np.testing.assert_allclose([complex_value(actual['voltage_v']),complex_value(actual['current_left_to_right_a'])],[v,i],atol=2e-11,rtol=1e-10)
                for field,expected in [('transported_power_w',float((v*i.conjugate()).real)),('conductor_loss_w_per_m',sample['resistance_ohm_per_m']*abs(i)**2),('dielectric_loss_w_per_m',sample['conductance_s_per_m']*abs(v)**2),('electric_energy_j_per_m',.5*line['capacitance_f_per_m']*abs(v)**2),('magnetic_energy_j_per_m',.5*line['inductance_h_per_m']*abs(i)**2)]:
                    self.assertAlmostEqual(actual[field],expected,delta=1e-18+1e-10*abs(expected),msg=field)
            for name,x,sign in [('left',0.,1),('right',length,-1)]:
                v,i=state(x);actual=row['boundary_values'][name]
                np.testing.assert_allclose([complex_value(actual['voltage_v']),complex_value(actual['current_into_line_a'])],[v,sign*i],atol=2e-11,rtol=1e-10)
                self.assertAlmostEqual(actual['input_power_w'],float(sign*(v*i.conjugate()).real),delta=2e-11)
            conductor=sample['resistance_ohm_per_m']*quad(lambda x:abs(state(x)[1])**2,0,length,epsabs=1e-13)[0]
            dielectric=sample['conductance_s_per_m']*quad(lambda x:abs(state(x)[0])**2,0,length,epsabs=1e-13)[0]
            ledger=row['power_balance']
            for name,expected in [('conductor_loss_w',conductor),('dielectric_loss_w',dielectric),('total_loss_w',conductor+dielectric)]:
                self.assertAlmostEqual(ledger[name],expected,delta=2e-12+1e-10*abs(expected))
            net=float(np.vdot(incident,incident).real-np.vdot(outgoing,outgoing).real)
            self.assertAlmostEqual(ledger['net_input_w'],net,delta=2e-11)
            self.assertAlmostEqual(ledger['residual_w'],ledger['net_input_w']-ledger['total_loss_w'],delta=1e-15)

    def test_schema_worker_rejects_dc_unknown_or_malformed_drives(self):
        validator=self.validators()[0]
        for change in ('dc','bool','extra','unknown'):
            raw=request()
            if change=='dc':raw['line_request']['samples'][0]['frequency_hz']=0;raw['excitations'][0]['frequency_hz']=0
            elif change=='bool':raw['excitations'][0]['incident_left']['real']=True
            elif change=='extra':raw['excitations'][0]['extra']=1
            else:raw['contract']='spike/unsupported/v1'
            self.assertFalse(validator.is_valid(raw),change)
            self.assertFalse(handle({'method':'run_rlgc_line_fields','params':{'request':raw}})['ok'],change)
        raw=request();raw['excitations'][0]['frequency_hz']*=2
        self.assertFalse(handle({'method':'run_rlgc_line_fields','params':{'request':raw}})['ok'])

    def test_example_executes_and_schemas_registered(self):
        completed=subprocess.run([sys.executable,str(ROOT/'examples/rlgc_line_fields/run_line.py')],cwd=ROOT,capture_output=True,text=True,check=True)
        self.validators()[1].validate(json.loads(completed.stdout))
        catalog=json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))
        for kind in ('request','result'):self.assertEqual(catalog['schemas'][f'spike/rlgc-line-fields-{kind}/v1'],f'rlgc-line-fields-{kind}-v1.schema.json')


if __name__=='__main__':unittest.main()
