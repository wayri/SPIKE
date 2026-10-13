# SPDX-License-Identifier: Apache-2.0
"""Original coupled DC/thermal engine selection and actual CalculiX oracles."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.assembly_electrothermal import run_assembly_electrothermal
from python.spike_core.assembly_electrothermal_setup import prepare_electrothermal
from python.spike_core.calculix_runtime import probe_calculix_runtime, run_calculix_deck
from python.spike_core.calculix_thermal import verify_calculix_thermal_result
from python.spike_core.multiboard_identity import canonical_json_digest
from tests.python.test_assembly_electrothermal import request


class ThermalEngineAdmissionTests(unittest.TestCase):
    def test_internal_default_and_explicit_choice(self):
        raw = request()
        self.assertEqual(prepare_electrothermal(raw)['thermal_engine'],'internal')
        raw['thermal_engine'] = 'internal'
        self.assertEqual(prepare_electrothermal(raw)['thermal_engine'],'internal')

    def test_unknown_engine_and_options_rejected_before_electrical_solve(self):
        for changes in ({'thermal_engine':'other'}, {'thermal_engine':True},
                        {'thermal_engine_options':{'threads':1}},
                        {'thermal_engine':'calculix','thermal_engine_options':{'command':'ccx'}},
                        {'thermal_engine':'calculix','thermal_engine_options':{'timeout_seconds':0}},
                        {'thermal_engine':'calculix','thermal_engine_options':{'threads':True}}):
            raw = request()
            raw.update(changes)
            with self.subTest(changes=changes), patch('python.spike_core.assembly_tetra_electrical.solve_assembly_tetra_electrical') as electrical:
                with self.assertRaises(ValueError):
                    run_assembly_electrothermal(raw)
                electrical.assert_not_called()

    def test_thermal_link_metadata_must_match_physical_contact(self):
        for key,value in [('thermal_resistance_k_per_w',.5),('contact_area_mm2',2e6),('endpoint_a','missing')]:
            raw = request()
            raw['geometry']['assembly']['thermal_contacts'][0][key] = value
            with self.subTest(key=key),patch('python.spike_core.assembly_tetra_electrical.solve_assembly_tetra_electrical') as electrical:
                with self.assertRaises(ValueError):
                    run_assembly_electrothermal(raw)
                electrical.assert_not_called()

    def test_missing_runtime_and_cancel_do_not_fall_back(self):
        raw = request()
        raw['thermal_engine'] = 'calculix'
        with patch.dict(os.environ,{'SPIKE_CALCULIX_EXECUTABLE':'C:/missing/no-ccx.exe'}):
            with self.assertRaisesRegex(ValueError,'CALCULIX_UNAVAILABLE'):
                run_assembly_electrothermal(raw)
        with self.assertRaisesRegex(ValueError,'CANCELLED'):
            run_assembly_electrothermal(raw,cancel_check=lambda:True)
        with self.assertRaisesRegex(ValueError,'CALCULIX_CANCELLED'):
            run_calculix_deck({},cancel_check=lambda:True)


@unittest.skipUnless(probe_calculix_runtime()['available'],'Separately installed CalculiX unavailable')
class CalculixCoupledExecutionTests(unittest.TestCase):
    def test_schema_and_actual_worker_external_phase(self):
        from jsonschema import Draft202012Validator, ValidationError
        from referencing import Registry, Resource
        from python.spike_core.spider_v2 import AssemblyIRV1
        raw = request(multi_board=True)
        raw['geometry']['assembly'] = json.loads(json.dumps(AssemblyIRV1.from_dict(raw['geometry']['assembly']).to_dict()))
        raw.update(thermal_engine='calculix',thermal_engine_options={'timeout_seconds':30})
        raw['iteration']['relaxation']=1
        root = Path(__file__).resolve().parents[2]
        registry = Registry()
        for name in ('assembly-ir-v1','design-ir-v2','assembly-placement-policy-v1','solver-mesh-v1',
                     'assembly-field-handoff-request-v1','assembly-field-thermal-problem-v1',
                     'electrical-heat-source-v1','assembly-electrothermal-request-v1'):
            schema = json.loads((root/'schemas'/f'{name}.schema.json').read_text())
            registry = registry.with_resource(schema['$id'],Resource.from_contents(schema))
        validator = Draft202012Validator(schema,registry=registry)
        validator.validate(raw)
        with self.assertRaises(ValidationError):
            validator.validate({**raw,'thermal_engine_options':{'executable':'arbitrary'}})
        response = subprocess.run([sys.executable,'-W','error','-m','python.spike_core.service'],
            input=json.dumps({'id':'ccx-coupled','method':'run_assembly_electrothermal','params':{'request':raw}})+'\n',
            text=True,capture_output=True,cwd=root,timeout=60,check=True)
        answer = json.loads(response.stdout)
        self.assertTrue(answer['ok'],answer)
        self.assertEqual(answer['result']['thermal_engine'],'calculix')
        self.assertEqual(answer['result']['thermal']['contract'],'spike/calculix-thermal-result/v1')

    def test_two_board_series_current_and_real_external_thermal_iteration(self):
        raw = request(multi_board=True)
        raw['iteration']['relaxation'] = 1
        internal = run_assembly_electrothermal(raw)
        raw.update(thermal_engine='calculix',thermal_engine_options={'timeout_seconds':30,'threads':1})
        before = copy.deepcopy(raw)
        external = run_assembly_electrothermal(raw)
        self.assertEqual(raw,before)
        # 2 V through two 0.5-ohm volumes plus a 0.25-ohm contact:
        # 1.6 A, 3.2 W total, of which 0.64 W is contact dissipation.
        self.assertAlmostEqual(external['electrical']['source_power_w'],3.2,places=8)
        self.assertAlmostEqual(external['electrical']['contact_power_w'],.64,places=8)
        self.assertAlmostEqual(sum(external['cell_deposited_power_w'].values()),3.2,places=8)
        self.assertEqual(external['thermal']['contract'],'spike/calculix-thermal-result/v1')
        self.assertEqual(set(external['thermal']['occurrence_temperatures']),{'board','case'})
        np.testing.assert_allclose(external['thermal']['field_result']['node_temperatures_k'],
                                   internal['thermal']['field_result']['node_temperatures_k'],atol=2e-4,rtol=0)
        self.assertIsNone(external['conservation']['thermal_imbalance_w'])
        self.assertEqual(external['conservation']['thermal_balance_status'],'not_reported')
        self.assertGreaterEqual(len(external['history']),2)
        self.assertTrue(all(len(row['thermal_result_digest'])==64 for row in external['history']))
        self.assertEqual(external['request_digest'],canonical_json_digest(raw))
        self.assertNotEqual(external['request_digest'],internal['request_digest'])
        geometry = prepare_electrothermal(raw)['geometry']
        verify_calculix_thermal_result(geometry,external['thermal_problem'],external['thermal'])
        changed = copy.deepcopy(external['thermal_problem'])
        changed['heat_sources'][0]['heat_source_w_m3'] += .1
        with self.assertRaisesRegex(ValueError,'STALE'):
            verify_calculix_thermal_result(geometry,changed,external['thermal'])

    def test_temperature_dependent_feedback_and_nonconvergence(self):
        raw = request(alpha=.004,multi_board=True)
        raw.update(thermal_engine='calculix',thermal_engine_options={'timeout_seconds':30})
        raw['iteration']['relaxation']=1
        result = run_assembly_electrothermal(raw)
        self.assertLess(result['electrical']['source_power_w'],3.2)
        self.assertGreater(len(result['history']),2)
        self.assertLessEqual(result['history'][-1]['unrelaxed_temperature_defect_k'],raw['iteration']['temperature_tolerance_k'])
        self.assertLessEqual(result['history'][-1]['power_relative_defect'],raw['iteration']['power_relative_tolerance'])
        raw['iteration']['max_iterations']=1
        with self.assertRaisesRegex(ValueError,'NONCONVERGENCE'):
            run_assembly_electrothermal(raw)


if __name__=='__main__':
    unittest.main()
