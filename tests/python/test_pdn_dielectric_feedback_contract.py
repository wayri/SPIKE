# SPDX-License-Identifier: Apache-2.0
"""Actual worker and schema checks for temperature-dependent dielectric loss."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
from python.spike_core.service import handle
from tests.python.test_pdn_dielectric_thermal_contract import coupled_request


def feedback_request():
    return {'contract':'spike/pdn-dielectric-feedback-request/v1','base_request':coupled_request(),
        'conductivity_laws':[{'material_id':'k','reference_temperature_k':300.,
            'temperature_coefficient_per_k':.02,'temperature_range_k':[290.,350.]}],
        'iteration':{'initial_temperature_k':300.,'max_iterations':50,'relaxation':.7,
                     'temperature_tolerance_k':1e-6,'power_relative_tolerance':1e-8}}


class DielectricFeedbackContractTests(unittest.TestCase):
    def test_schema_and_actual_feedback_worker(self):
        request=feedback_request(); before=copy.deepcopy(request)
        root=Path(__file__).resolve().parents[2]
        schema=json.loads((root/'schemas/pdn-dielectric-feedback-request-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(request)
        response=handle({'method':'run_pdn_dielectric_feedback','params':{'request':request}})
        self.assertTrue(response['ok'],response)
        result=response['result']
        schema=json.loads((root/'schemas/pdn-dielectric-feedback-result-v1.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema).validate(result)
        self.assertEqual(request,before)
        self.assertEqual(result['model_status'],'experimental')
        self.assertIs(result['production_qualified'],False)
        self.assertEqual(result['coupling_mode'],'two_way_conductivity_temperature')
        self.assertLessEqual(result['diagnostics']['temperature_residual_k'],request['iteration']['temperature_tolerance_k'])
        self.assertLessEqual(result['diagnostics']['power_relative_change'],request['iteration']['power_relative_tolerance'])
        coupled=result['last_coupled_result']
        self.assertGreater(coupled['total_dielectric_power_w'],1.)
        self.assertAlmostEqual(coupled['total_dielectric_power_w'],coupled['port_power_w'],delta=1e-9)

    def test_worker_rejects_uncovered_materials_ranges_and_bad_iteration(self):
        for mutation in ('law','range','iterations','unknown'):
            request=feedback_request()
            if mutation=='law': request['conductivity_laws'][0]['material_id']='unknown'
            elif mutation=='range': request['conductivity_laws'][0]['temperature_range_k']=[310.,350.]
            elif mutation=='iterations': request['iteration']['max_iterations']=True
            else: request['automatic_extrapolation']=True
            with self.subTest(mutation=mutation):
                response=handle({'method':'run_pdn_dielectric_feedback','params':{'request':request}})
                self.assertFalse(response['ok'],response)


if __name__=='__main__':unittest.main()
