# SPDX-License-Identifier: Apache-2.0
"""Original retained-volume PWM admission, state rollback and energy oracles."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.pwm_volume_electrothermal import (
    REQUEST, DEVICES, run_pwm_volume_electrothermal, validate_pwm_volume_electrothermal,
)
from tests.python.test_assembly_tetra_thermal import request, cube, contact_request


def volume_request(cycles=4, **parameters):
    thermal = request(cube())
    thermal['boundaries'] = []
    # All four explicitly mapped dissipators, uniform total heat capacity .01 J/K.
    mappings = {name: [{'cell_id': cell['id'], 'weight': 1/6} for cell in thermal['mesh']['cells']]
                for name in DEVICES}
    return {'contract': REQUEST, 'parameters': {'cycles': cycles, **parameters},
            'coupling': {}, 'thermal': {'request': thermal,
                'material_heat_capacity': [{'material_id': 'k', 'density_kg_m3': 1., 'specific_heat_j_kgk': .01}],
                'initial_temperature_k': 300., 'device_cell_fractions': mappings}}


class AdmissionTests(unittest.TestCase):
    def test_explicit_maps_and_no_rcs(self):
        raw = volume_request()
        saved = copy.deepcopy(raw)
        self.assertEqual(validate_pwm_volume_electrothermal(raw)['status'], 'accepted')
        self.assertEqual(raw, saved)
        for change in ('mapping', 'rc', 'bool', 'unknown'):
            bad = copy.deepcopy(raw)
            if change == 'mapping': del bad['thermal']['device_cell_fractions']['SH']
            if change == 'rc': bad['parameters']['thermal_capacitance_j_per_k'] = .01
            if change == 'bool': bad['coupling']['maximum_iterations'] = True
            if change == 'unknown': bad['coupling']['native_code'] = 'x'
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'PWM_VOLUME_'):
                validate_pwm_volume_electrothermal(bad)

    def test_initial_boolean_and_fixed_temperature_rejected(self):
        raw = volume_request()
        raw['thermal']['initial_temperature_k'] = [True] * 8
        with self.assertRaises(ValueError):
            validate_pwm_volume_electrothermal(raw)

    def test_cancel_before_runtime_loading(self):
        with self.assertRaisesRegex(ValueError, 'PWM_VOLUME_CANCELLED'):
            run_pwm_volume_electrothermal(volume_request(), cancel_check=lambda: True)

    def test_unrepresentable_control_is_stable_admission_error(self):
        raw = volume_request()
        raw['coupling']['maximum_iterations'] = 10**400
        with self.assertRaisesRegex(ValueError, 'PWM_VOLUME_REQUEST'):
            validate_pwm_volume_electrothermal(raw)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('SPIKE_PWM_TEST_LIBRARY')
        if not path:
            raise unittest.SkipTest('SPIKE_PWM_TEST_LIBRARY required for real native integration')
        from python.spikes.native_abi import load_native_library
        cls.library = load_native_library(path)

    def run_case(self, raw=None, **kwargs):
        return run_pwm_volume_electrothermal(raw or volume_request(), library=self.library, **kwargs)

    def test_actual_native_adiabatic_energy_and_no_rc_capacity(self):
        raw = volume_request()
        saved = copy.deepcopy(raw)
        result = self.run_case(raw)
        self.assertEqual(raw, saved)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['completed_cycles'], 4)
        total_heat = sum(result['energy'][name] for name in DEVICES)
        np.testing.assert_allclose(result['frames'][-1]['node_temperatures_k'], 300 + total_heat/.01, atol=1e-9)
        self.assertLess(abs(result['energy']['electrical_balance_j']), 1e-12)
        self.assertLess(abs(result['thermal_energy_balance']['imbalance_j']), 1e-12)
        for w in result['windows']:
            self.assertGreaterEqual(w['iterations'], 2)
            self.assertLessEqual(w['temperature_defect_k'], 1e-6)
        json.dumps(result, allow_nan=False)
        import jsonschema
        root = Path(__file__).resolve().parents[2]
        for name, value in (('request', raw), ('result', result)):
            schema = json.loads((root / f'schemas/pwm-volume-electrothermal-{name}-v1.schema.json').read_text())
            jsonschema.Draft202012Validator(schema).validate(value)

    def test_retained_board_package_contact_maps_and_combined_energy(self):
        raw = volume_request(8)
        thermal = contact_request()
        thermal['boundaries'] = []
        raw['thermal']['request'] = thermal
        raw['thermal']['initial_temperature_k'] = [300.] * 8 + [310.] * 8
        for name in DEVICES:
            body = 'left' if name in ('Rw', 'Load') else 'right'
            cells = [c for c in thermal['mesh']['cells'] if c['source_object_ids'] == [body]]
            raw['thermal']['device_cell_fractions'][name] = [{'cell_id': c['id'], 'weight': 1/len(cells)} for c in cells]
        result = self.run_case(raw)
        temps = result['windows'][-1]['device_temperatures_k']
        self.assertGreater(temps['SH'], temps['Rw'])
        self.assertLess(abs(result['energy']['combined_balance_j']), 1e-10)
        self.assertEqual(len(result['frames'][-1]['node_temperatures_k']), 16)

    def test_owned_worker_public_dispatch(self):
        from python.spike_core.service import handle
        raw = volume_request(2)
        accepted = handle({'method': 'validate_pwm_volume_electrothermal', 'params': {'request': raw}})
        self.assertTrue(accepted['ok'], accepted)
        from python.spike_core import pwm_volume_electrothermal as backend
        actual = backend.run_pwm_volume_electrothermal
        with patch.object(backend, 'run_pwm_volume_electrothermal', side_effect=lambda request, **kwargs: actual(request, library=self.library, **kwargs)):
            response = handle({'method': 'run_pwm_volume_electrothermal', 'params': {'request': raw}})
        self.assertTrue(response['ok'], response)
        self.assertEqual(response['result']['completed_cycles'], 2)

    def test_cancelled_iteration_publishes_only_committed_window(self):
        stop = [False]
        result = self.run_case(cancel_check=lambda: stop[0], progress=lambda e: stop.__setitem__(0, e['completed_cycles'] == 1))
        reference = self.run_case(volume_request(1))
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['completed_cycles'], 1)
        self.assertEqual(result['windows'], reference['windows'])
        self.assertEqual(result['energy'], reference['energy'])
        self.assertEqual(result['frames'], reference['frames'])

    def test_mid_window_cancel_rolls_back_all_public_states(self):
        count = [0]
        def cancel():
            count[0] += 1
            return count[0] > 40
        result = self.run_case(cancel_check=cancel)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['completed_cycles'], 0)
        self.assertEqual(len(result['frames']), 1)
        self.assertTrue(all(value == 0 for value in result['energy'].values()))

    def test_nonconvergence_is_not_accepted_or_relaxation_hidden(self):
        raw = volume_request()
        raw['coupling'] = {'maximum_iterations': 2, 'temperature_tolerance_k': 1e-10,
                           'relative_energy_tolerance': 1e-10, 'relaxation': .05}
        with self.assertRaisesRegex(ValueError, 'PWM_VOLUME_COUPLING_CONVERGENCE'):
            self.run_case(raw)

    def test_feedback_and_deterministic_restore(self):
        warm = volume_request(8)
        warm['thermal']['initial_temperature_k'] = 320.
        warm_result = self.run_case(warm)
        cold_result = self.run_case(volume_request(8))
        self.assertNotEqual(warm_result['windows'][-1]['electrical_cycles'][-1]['output_voltage_v'],
                            cold_result['windows'][-1]['electrical_cycles'][-1]['output_voltage_v'])
        self.assertEqual(warm_result['windows'], self.run_case(warm)['windows'])
