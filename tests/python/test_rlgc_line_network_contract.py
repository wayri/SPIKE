# SPDX-License-Identifier: Apache-2.0
"""Original worker/schema/circuit references for supplied uniform sampled lines."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
import numpy as np
from scipy.linalg import expm

from examples.rlgc_line_network.run_line import request
from python.spike_core.service import handle

ROOT=Path(__file__).resolve().parents[2]


class RLGCLineContractTests(unittest.TestCase):
    def validators(self):
        return [Draft202012Validator(json.loads((ROOT/'schemas'/f'rlgc-line-network-{kind}-v1.schema.json').read_text(encoding='utf-8')))
                for kind in ('request','result')]

    def test_worker_spatial_reference_source_identity_and_network_handoff(self):
        raw=request(); before=deepcopy(raw); validators=self.validators(); validators[0].validate(raw)
        response=handle({'method':'build_rlgc_line_network','params':{'request':raw}})
        self.assertTrue(response['ok'],response); result=response['result']; validators[1].validate(result)
        self.assertEqual(raw,before); self.assertEqual(result['source_request'],raw)
        digest=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        self.assertEqual(result['input_digest'],digest); self.assertFalse(result['production_qualified'])
        network=result['network']; self.assertEqual(network['port_names'],['left','right'])
        for sample,matrix in zip(raw['samples'],network['s_parameters']):
            # Independent spatial state transition; solve boundary V/I wave
            # equations directly instead of using the kernel's scaled formula.
            w=2*np.pi*sample['frequency_hz']; z=sample['resistance_ohm_per_m']+1j*w*raw['inductance_h_per_m']
            y=sample['conductance_s_per_m']+1j*w*raw['capacitance_f_per_m']
            transfer=expm(-raw['length_m']*np.array([[0,z],[y,0]],dtype=complex))
            ref=raw['reference_impedance_ohm']; scale=np.sqrt(ref)
            v=np.array([scale,1/scale]); r=np.array([scale,-1/scale])
            # Right-port current into line is negative spatial current.
            unknown=np.column_stack((-transfer@r,v)); known=np.column_stack((transfer@v,-r))
            oracle=np.linalg.solve(unknown,known)
            actual=np.array([[complex(p['real'],p['imag']) for p in row] for row in matrix])
            np.testing.assert_allclose(actual,oracle,rtol=1e-10,atol=2e-12)
        forwarded=handle({'method':'resample_sparameter_network','params':{'request':{
            'contract':'spike/sparameter-resampling-request/v1','source':network,
            'target_frequencies_hz':network['frequencies_hz'],'dc_policy':{'mode':'require_source'}}}})
        self.assertTrue(forwarded['ok'],forwarded)
        self.assertEqual(forwarded['result']['derived_network']['s_parameters'],network['s_parameters'])

    def test_strict_schema_and_worker_reject_unsupported_requests(self):
        validator=self.validators()[0]
        for mutate in ('negative','bool','extra','unknown','reference'):
            raw=request()
            if mutate=='negative':raw['samples'][0]['resistance_ohm_per_m']=-1
            elif mutate=='bool':raw['length_m']=True
            elif mutate=='extra':raw['samples'][0]['invented']=0
            elif mutate=='unknown':raw['contract']='spike/unsupported/v1'
            else:raw['reference_impedance_ohm']=0
            self.assertFalse(validator.is_valid(raw),mutate)
            self.assertFalse(handle({'method':'build_rlgc_line_network','params':{'request':raw}})['ok'],mutate)
        self.assertFalse(handle({'method':'build_rlgc_line_network','params':{'request':request(),'extra':True}})['ok'])

    def test_example_executes_and_schemas_registered(self):
        result=subprocess.run([sys.executable,str(ROOT/'examples/rlgc_line_network/run_line.py')],cwd=ROOT,capture_output=True,text=True,check=True)
        self.validators()[1].validate(json.loads(result.stdout))
        catalog=json.loads((ROOT/'schemas/manifest.json').read_text(encoding='utf-8'))
        for kind in ('request','result'):
            self.assertEqual(catalog['schemas'][f'spike/rlgc-line-network-{kind}/v1'],f'rlgc-line-network-{kind}-v1.schema.json')


if __name__=='__main__':unittest.main()
