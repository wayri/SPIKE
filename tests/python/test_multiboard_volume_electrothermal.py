# SPDX-License-Identifier: Apache-2.0
"""Original KVL, sinusoidal mean power and conservative cell transfer oracles."""
import copy
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from examples.assembly_field.run_multiboard_volume import request
from python.spike_core.multiboard_identity import canonical_json_digest
from python.spike_core.multiboard_volume_electrothermal import (
    prepare_multiboard_volume_electrothermal, run_multiboard_volume_electrothermal,
    verify_multiboard_volume_electrothermal_result)


class MultiboardVolumeTests(unittest.TestCase):
    def test_dc_real_mna_loss_conservation_and_part_coverage(self):
        for part in (False, True):
            raw = request(mechanical_part=part)
            original = copy.deepcopy(raw)
            result = run_multiboard_volume_electrothermal(raw)
            self.assertEqual(raw, original)
            expected = 12**2/6.3
            self.assertAlmostEqual(result['loss_balance']['deposited_power_w'], expected, places=10)
            self.assertLess(abs(result['loss_balance']['thermal_imbalance_w']), 1e-8)
            self.assertLess(abs(result['loss_balance']['mapping_residual_w']), 1e-12)
            self.assertEqual(set(result['thermal']['occurrence_temperatures']), {'board', 'case'})
            self.assertEqual(len(result['electrical']['losses']), 3)
            self.assertFalse(result['production_qualified'])
            prepared = prepare_multiboard_volume_electrothermal(raw)
            json.dumps(prepared, allow_nan=False)
            self.assertEqual(prepared['handoff']['handoff_digest'], result['thermal']['handoff_digest'])
            self.assertEqual(verify_multiboard_volume_electrothermal_result(raw, result), result)

    def test_ac_rms_peak_and_inductive_analytic_loss(self):
        raw = request('si')
        raw['circuit']['link_models'][0]['pins'][0]['inductance_h'] = .001
        rms = run_multiboard_volume_electrothermal(raw)
        expected = 6.3/(6.3**2+(2*math.pi*1000*.001)**2)
        self.assertAlmostEqual(rms['loss_balance']['deposited_power_w'], expected, places=12)
        raw['ac_heating']['phasor_convention'] = 'peak'
        peak = run_multiboard_volume_electrothermal(raw)
        self.assertAlmostEqual(peak['loss_balance']['deposited_power_w'], expected/2, places=12)

    def test_feedback_and_unrelaxed_nonconvergence(self):
        result = run_multiboard_volume_electrothermal(request(alpha=.004))
        self.assertLess(result['loss_balance']['deposited_power_w'], 12**2/6.3)
        self.assertLess(result['history'][-1]['power_relative_defect'], 1e-9)
        raw = request(alpha=.004)
        raw['iteration'].update(relaxation=1e-12, max_iterations=1)
        with self.assertRaisesRegex(ValueError, 'NONCONVERGENCE'):
            run_multiboard_volume_electrothermal(raw)
        with self.assertRaisesRegex(ValueError, 'CANCELLED'):
            run_multiboard_volume_electrothermal(request(), cancel_check=lambda: True)

    def test_contacts_change_electrical_power_and_thermal_interface_jump(self):
        raw = request()
        raw['circuit']['link_models'][0]['pins'][0].update(contact_a_resistance_ohm=.4, contact_b_resistance_ohm=.5)
        # Deposit all losses in the load board so a physical thermal contact
        # temperature jump is necessary; every electrical loss remains covered.
        for binding in raw['loss_bindings']:
            binding['distribution'] = [dict(row, weight=1/6) for row in binding['distribution'] if row['occurrence_id'] == 'case']
        before = run_multiboard_volume_electrothermal(raw)
        self.assertAlmostEqual(before['loss_balance']['deposited_power_w'], 144/7.2, places=10)
        for assembly in [raw['geometry']['assembly'], raw['circuit']['assembly']]:
            assembly['thermal_contacts'][0]['thermal_resistance_k_per_w'] = 2.5
        raw['thermal_problem']['contacts'][0]['thermal_contact_conductance_w_m2k'] = .4
        after = run_multiboard_volume_electrothermal(raw)
        self.assertGreater(after['thermal']['occurrence_temperatures']['case']['maximum_k'],
                           before['thermal']['occurrence_temperatures']['case']['maximum_k'])
        self.assertLess(abs(after['loss_balance']['thermal_imbalance_w']), 1e-8)

    def test_fail_closed_identity_coverage_background_weights_and_envelope(self):
        mutations = [
            lambda r: r['circuit']['assembly'].update(name='changed'),
            lambda r: r['loss_bindings'].pop(),
            lambda r: r['loss_bindings'].__setitem__(1, copy.deepcopy(r['loss_bindings'][0])),
            lambda r: r['loss_bindings'][0]['distribution'][0].update(weight=.3),
            lambda r: r['loss_bindings'][0]['distribution'][0].update(occurrence_id='missing'),
            lambda r: r['thermal_problem']['heat_sources'].append(
                {'occurrence_id': 'board', 'cell_id': '0', 'heat_source_w_m3': 1}),
            lambda r: r['loss_bindings'][0]['temperature_law'].update(temperature_range_k=[299, 300.01]),
            lambda r: r['circuit']['link_models'][0]['pins'].pop(),
            lambda r: r['circuit']['board_models'][0]['elements'].append(
                {'id': 'controlled', 'type': 'vccs', 'positive_node': 'J:1', 'negative_node': 'J:2',
                 'control_positive_node': 'J:1', 'control_negative_node': 'J:2', 'transconductance_s': .1})]
        for mutation in mutations:
            raw = request()
            mutation(raw)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                run_multiboard_volume_electrothermal(raw)

    def test_si_requires_explicit_convention_frequency_and_no_unaccounted_dc(self):
        for mutation in [lambda r: r.pop('ac_heating'),
                         lambda r: r['ac_heating'].update(frequency_hz=2000),
                         lambda r: r['ac_heating'].update(phasor_convention='implicit'),
                         lambda r: r['circuit']['board_models'][0]['elements'][0].update(dc_value=12)]:
            raw = request('si')
            mutation(raw)
            with self.assertRaises(ValueError):
                run_multiboard_volume_electrothermal(raw)

    def test_offline_admission_checks_rehashed_loss_and_geometry_without_solving(self):
        raw = request()
        result = run_multiboard_volume_electrothermal(raw)
        with patch('python.spike_core.multiboard_volume_electrothermal.run_native_mna', side_effect=AssertionError('solver forbidden')):
            verify_multiboard_volume_electrothermal_result(raw, result)
        for mutation in [lambda r: r['loss_balance'].update(deposited_power_w=1000),
                         lambda r: r['thermal_geometry']['assembly'].update(name='changed'),
                         lambda r: r['cell_deposited_power_w'].clear()]:
            changed = copy.deepcopy(result)
            mutation(changed)
            changed['result_digest'] = canonical_json_digest({k: v for k, v in changed.items() if k != 'result_digest'})
            with self.assertRaises(ValueError):
                verify_multiboard_volume_electrothermal_result(raw, changed)

    def test_real_calculix_when_available(self):
        from python.spike_core.calculix_runtime import probe_calculix_runtime
        if not probe_calculix_runtime()['available']:
            self.skipTest('Separately installed CalculiX unavailable')
        raw = request()
        raw.update(thermal_engine='calculix', thermal_engine_options={'threads': 1, 'timeout_seconds': 60})
        raw['iteration'].update(relaxation=1., temperature_tolerance_k=.002)
        result = run_multiboard_volume_electrothermal(raw)
        self.assertEqual(result['thermal']['solver_id'], 'external.calculix')
        self.assertEqual(result['loss_balance']['thermal_balance_status'], 'not_reported')
        self.assertEqual(prepare_multiboard_volume_electrothermal(raw)['handoff']['handoff_digest'],
                         result['thermal']['handoff_digest'])
        verify_multiboard_volume_electrothermal_result(raw, result)

    def test_schema_admits_examples_and_rejects_extra_heat(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from python.spike_core.spider_v2 import AssemblyIRV1
        root = Path(__file__).resolve().parents[2]
        registry = Registry()
        for name in ('assembly-ir-v1', 'design-ir-v2', 'assembly-placement-policy-v1', 'solver-mesh-v1',
                     'assembly-field-handoff-request-v1', 'assembly-field-thermal-problem-v1',
                     'assembly-electrothermal-request-v1', 'multiboard-circuit-request-v1',
                     'multiboard-volume-electrothermal-request-v1'):
            schema = json.loads((root/'schemas'/f'{name}.schema.json').read_text())
            registry = registry.with_resource(schema['$id'], Resource.from_contents(schema))
            registry = registry.with_resource(f'https://spike.local/schemas/{name}.schema.json', Resource.from_contents(schema))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, registry=registry)
        for domain in ('pi', 'si'):
            raw = request(domain)
            for owner in ('geometry', 'circuit'):
                raw[owner]['assembly'] = json.loads(json.dumps(AssemblyIRV1.from_dict(raw[owner]['assembly']).to_dict()))
            validator.validate(raw)
            raw['thermal_problem']['heat_sources'] = [{'occurrence_id': 'board', 'cell_id': '0', 'heat_source_w_m3': 1}]
            self.assertTrue(list(validator.iter_errors(raw)))


if __name__ == '__main__':
    unittest.main()
