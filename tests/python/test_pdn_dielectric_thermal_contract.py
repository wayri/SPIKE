# SPDX-License-Identifier: Apache-2.0
"""Actual owned-worker electrical loss to conservative thermal-source execution."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.service import handle
from tests.python.test_pdn_dielectric_ac import plate
from tests.python.test_assembly_tetra_thermal import request as thermal_request


def coupled_request():
    electrical=plate(2,sigma=1.,tangent=0.,frequencies=[1000.])
    thermal=thermal_request(copy.deepcopy(electrical['mesh']))
    thermal['materials'][0]['thermal_conductivity_w_mk']=1.
    for boundary in thermal['boundaries']: boundary['temperature_k']=300.
    return {'contract':'spike/pdn-dielectric-thermal-request/v1','electrical_request':electrical,
            'drive':{'frequency_hz':1000.,'voltages_v':{'load-terminal':{'real':1.,'imag':0.}}},
            'thermal_request':thermal}


class DielectricThermalContractTests(unittest.TestCase):
    def test_reproducible_example_actual_worker(self):
        from examples.pdn_dielectric_thermal.run_slab import setup
        import math
        response=handle({'method':'run_pdn_dielectric_thermal','params':{'request':setup()}})
        self.assertTrue(response['ok'],response)
        result=response['result']
        expected=100*(.5+2*math.pi*1000*.05*1e-6)
        self.assertAlmostEqual(result['total_dielectric_power_w'],expected,delta=1e-8)
        peak=max(result['thermal_result']['node_temperatures_k'])
        self.assertGreater(peak,300.)
        self.assertLess(peak,310.)

    def test_schema_and_actual_worker_power_to_temperature(self):
        raw=coupled_request(); before=copy.deepcopy(raw)
        root=Path(__file__).resolve().parents[2]
        schema=json.loads((root/'schemas/pdn-dielectric-thermal-request-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(raw)
        response=handle({'method':'run_pdn_dielectric_thermal','params':{'request':raw}})
        self.assertTrue(response['ok'],response)
        result=response['result']
        self.assertEqual(raw,before)
        schema=json.loads((root/'schemas/pdn-dielectric-thermal-result-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(result)
        self.assertEqual(result['model_status'],'experimental')
        self.assertIs(result['production_qualified'],False)
        self.assertAlmostEqual(result['total_dielectric_power_w'],1.,delta=1e-10)
        self.assertAlmostEqual(result['port_power_w'],1.,delta=1e-10)
        self.assertAlmostEqual(result['thermal_result']['heat_balance']['source_w'],1.,delta=1e-10)
        self.assertLess(abs(result['thermal_result']['heat_balance']['imbalance_w']),1e-8)
        self.assertGreater(max(result['thermal_result']['node_temperatures_k']),300.)

    def test_worker_rejects_mismatched_mesh_and_ambiguous_drives(self):
        for mutation in ('mesh','drive','sources','tone'):
            raw=coupled_request()
            if mutation=='mesh': raw['thermal_request']['mesh']['vertices'][0][0]=.1
            elif mutation=='drive': raw['drive']['voltages_v']['unknown']={'real':1.,'imag':0.}
            elif mutation=='sources': raw['thermal_request']['heat_sources_w_m3']={'solid-0':1.}
            else: raw['electrical_request']['frequencies_hz'].append(2000.)
            with self.subTest(mutation=mutation):
                result=handle({'method':'run_pdn_dielectric_thermal','params':{'request':raw}})
                self.assertFalse(result['ok'],result)


if __name__=='__main__': unittest.main()
