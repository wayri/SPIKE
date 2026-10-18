# SPDX-License-Identifier: Apache-2.0
"""Hand-computed virtual-time oracles for original, unqualified C++ models."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))

from spikes_studio.compiled_part_models import PWM_ID, SUPERVISOR_ID, catalog, configuration, records
from spikes_studio import compiled_ic_library
from spikes_studio.controller_block import Controller, FRESH_PROCESS, PERSISTENT_PROCESS
from spikes_studio.ide import find_tool
from python.spikes.compiled_blocks import CompiledBlockExecutionError


ROOT = Path(__file__).resolve().parents[4]
NATIVE_LIBRARY = Path(os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',
                                    ROOT / 'build-spikes-current-vs18-20260906/Release/spikes_c_api.dll'))


class CompiledPartDescriptorTests(unittest.TestCase):
    def test_portable_library_uses_the_same_parameter_and_output_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'portable.spkctl'
            compiled_ic_library.save(path, catalog())
            portable = compiled_ic_library.load(path)
        for identifier in (PWM_ID, SUPERVISOR_ID):
            with self.subTest(identifier=identifier):
                parameters = {'output_high_v': 12.0}
                overrides = {'duty': {'vdd': 2.0}} if identifier == PWM_ID else None
                imported = compiled_ic_library.configuration(identifier, parameters, overrides, library=portable)
                self.assertEqual(imported, configuration(identifier, parameters, overrides))
                for pin in imported['pins']:
                    if pin['mode'] == 'DO':
                        self.assertEqual(pin['vdd'], 12.0)
                    elif pin['name'] == 'duty':
                        self.assertEqual(pin['vdd'], 1.0)
        for identifier, parameters in [
            (PWM_ID, {'sample_period_s': 3e-6}), (PWM_ID, {'sample_period_s': 1e-4}),
            (PWM_ID, {'uvlo_off_v': 10.0}), (SUPERVISOR_ID, {'uvlo_off_v': 10.0}),
            (PWM_ID, {'thermal_reset_v': 3.0}), (PWM_ID, {'soft_start_s': 1e-9}),
            (SUPERVISOR_ID, {'trip_off_v': 3.0}),
        ]:
            with self.subTest(identifier=identifier, parameters=parameters), self.assertRaises(ValueError):
                compiled_ic_library.configuration(identifier, parameters, library=portable)

    def test_portable_metadata_cannot_dispatch_validator_code(self):
        portable = catalog()
        entry = portable['entries'][0]
        entry['id'] = 'custom.inert_metadata'
        entry['validator'] = 'raise RuntimeError("untrusted validator must not run")'
        result = compiled_ic_library.configuration(entry['id'], library=portable)
        self.assertEqual(result['language'], 'C++')
        incomplete = catalog()
        incomplete['entries'][0]['parameters'] = [p for p in incomplete['entries'][0]['parameters']
                                                   if p['name'] != 'output_high_v']
        with self.assertRaisesRegex(ValueError, 'missing required parameters'):
            compiled_ic_library.configuration(PWM_ID, library=incomplete)

    def test_detached_inert_sdk_records(self):
        first = records()
        self.assertEqual({r['descriptor']['id'] for r in first}, {PWM_ID, SUPERVISOR_ID})
        for record in first:
            self.assertIsNone(record['manufacturer_mpn'])
            self.assertEqual(record['license'], 'Apache-2.0')
            self.assertEqual(record['configuration']['language'], 'C++')
            self.assertNotIn('@', record['configuration']['source'])
            self.assertNotIn('static ', record['configuration']['source'])
            self.assertIn('unqualified', record['model_status'])
        first[0]['descriptor']['pins'][0]['node'] = 'mutated'
        self.assertEqual(catalog()['entries'][0]['pins'][0]['node'], 'vcc')
        with self.assertRaisesRegex(ValueError, 'trusted-code consent'):
            Controller(first[0]['configuration'])

    def test_parameters_bindings_and_invalid_contracts(self):
        config = configuration(PWM_ID, {'output_high_v': 12.0},
                               {'feedback': {'node': 'out'}, 'drive': {'source': 'VGATE'}})
        self.assertEqual(next(p for p in config['pins'] if p['name'] == 'drive')['vdd'], 12.0)
        self.assertEqual(next(p for p in config['pins'] if p['name'] == 'drive')['source'], 'VGATE')
        for identifier, parameters in [
            (PWM_ID, {'uvlo_off_v': 10.0}), (PWM_ID, {'thermal_reset_v': 3.0}),
            (PWM_ID, {'sample_period_s': 3e-6}), (PWM_ID, {'sample_period_s': 1e-4}),
            (PWM_ID, {'soft_start_s': 1e-9}), (PWM_ID, {'kp_per_v': float('nan')}),
            (PWM_ID, {'duty_max': True}), (PWM_ID, {'not_a_parameter': 1.0}),
            (SUPERVISOR_ID, {'trip_off_v': 3.0}),
        ]:
            with self.subTest(parameters=parameters), self.assertRaises(ValueError):
                configuration(identifier, parameters)


@unittest.skipUnless(find_tool('cl') or find_tool('clang++'), 'C++ compiler not configured')
class CompiledPartExecutionTests(unittest.TestCase):
    PWM_PARAMETERS = dict(sample_period_s=0.001, switching_period_s=0.01,
                          reference_v=1.0, kp_per_v=1.0, ki_per_v_s=0.0,
                          soft_start_s=0.004, duty_max=0.8)

    def make(self, identifier, parameters, mode=PERSISTENT_PROCESS):
        controller = Controller(configuration(identifier, parameters), trusted=True, execution_mode=mode)
        self.addCleanup(controller.close)
        return controller

    @staticmethod
    def pwm_tick(controller, **overrides):
        inputs = dict(vcc=12.0, enable=3.3, feedback=0.0, current_sense=0.0, temperature=0.0)
        inputs.update(overrides)
        dt = controller.config['step_s']
        return controller.step(inputs, controller.tick * dt, dt)

    @staticmethod
    def supervisor_tick(controller, **overrides):
        inputs = dict(vcc=12.0, sense=0.0, enable=3.3, reset=0.0)
        inputs.update(overrides)
        dt = controller.config['step_s']
        return controller.step(inputs, controller.tick * dt, dt)

    def test_pwm_soft_start_uvlo_thermal_and_fresh_persistent_parity(self):
        traces = []
        for mode in (FRESH_PROCESS, PERSISTENT_PROCESS):
            controller = self.make(PWM_ID, self.PWM_PARAMETERS, mode)
            trace = [self.pwm_tick(controller, vcc=9.0)]
            self.assertEqual(trace[-1]['VREADY'], 0.0)
            trace += [self.pwm_tick(controller) for _ in range(4)]
            for actual, expected in zip(trace[1:], (0.2, 0.4, 0.6, 0.8)):
                self.assertAlmostEqual(actual['VDUTY'], expected)
            self.assertEqual(self.pwm_tick(controller, vcc=9.0)['VREADY'], 5.0)
            self.assertEqual(self.pwm_tick(controller, vcc=8.0)['VDRIVE'], 0.0)
            self.assertEqual(controller.state['state_3'], 0.0)
            self.assertEqual(self.pwm_tick(controller, vcc=9.0)['VREADY'], 0.0)
            self.assertAlmostEqual(self.pwm_tick(controller)['VDUTY'], 0.2)
            self.assertEqual(self.pwm_tick(controller, temperature=3.0)['VREADY'], 0.0)
            self.assertEqual(self.pwm_tick(controller, temperature=2.7)['VREADY'], 0.0)
            self.assertAlmostEqual(self.pwm_tick(controller, temperature=2.5)['VDUTY'], 0.2)
            self.assertEqual(self.pwm_tick(controller, enable=0.0)['VDRIVE'], 0.0)
            traces.append(trace)
        self.assertEqual(traces[0], traces[1])

    def test_cycle_current_latch_and_no_pulse_retrigger(self):
        controller = self.make(PWM_ID, dict(self.PWM_PARAMETERS, soft_start_s=0.001))
        self.assertEqual(self.pwm_tick(controller)['VDRIVE'], 5.0)
        trip = self.pwm_tick(controller, current_sense=1.0)
        self.assertEqual((trip['VDRIVE'], trip['VCURRENT_TRIP']), (0.0, 5.0))
        for _ in range(8):
            self.assertEqual(self.pwm_tick(controller)['VDRIVE'], 0.0)
        reset = self.pwm_tick(controller)
        self.assertEqual((reset['VDRIVE'], reset['VCURRENT_TRIP']), (5.0, 0.0))
        # Once a pulse ends on low duty, higher duty cannot resurrect it mid-cycle.
        self.assertEqual(self.pwm_tick(controller, feedback=1.0)['VDRIVE'], 0.0)
        self.assertEqual(self.pwm_tick(controller)['VDRIVE'], 0.0)
        controller.reset()
        expected = [5.0] * 8 + [0.0] * 2
        self.assertEqual([self.pwm_tick(controller)['VDRIVE'] for _ in range(20)], expected * 2)

    def test_conditional_integrator_saturation_and_recovery(self):
        controller = self.make(PWM_ID, dict(self.PWM_PARAMETERS, soft_start_s=0.001,
                                          kp_per_v=0.5, ki_per_v_s=100.0))
        for expected in (0.6, 0.7, 0.8, 0.8, 0.8):
            self.assertAlmostEqual(self.pwm_tick(controller)['VDUTY'], expected)
        self.assertAlmostEqual(controller.state['state_3'], 0.3)
        self.assertAlmostEqual(self.pwm_tick(controller, feedback=1.0)['VDUTY'], 0.3)
        self.assertAlmostEqual(self.pwm_tick(controller, feedback=1.2)['VDUTY'], 0.18)
        self.assertAlmostEqual(controller.state['state_3'], 0.28)
        for _ in range(5):
            self.assertEqual(self.pwm_tick(controller, feedback=10.0)['VDUTY'], 0.0)
        self.assertAlmostEqual(controller.state['state_3'], 0.28)

    def test_decimal_carrier_and_debounce_do_not_add_a_tick(self):
        controller = self.make(PWM_ID, dict(self.PWM_PARAMETERS, sample_period_s=1e-6,
                                          switching_period_s=20e-6, soft_start_s=1e-6,
                                          kp_per_v=0.5))
        self.assertEqual([self.pwm_tick(controller)['VDRIVE'] for _ in range(40)],
                         ([5.0] * 10 + [0.0] * 10) * 2)
        supervisor = self.make(SUPERVISOR_ID, dict(sample_period_s=1e-6, debounce_s=20e-6))
        self.assertEqual([self.supervisor_tick(supervisor, sense=3.0)['VFAULT'] for _ in range(21)],
                         [0.0] * 20 + [5.0])

    def test_supervisor_hysteresis_debounce_latch_reset_and_mode_parity(self):
        traces = []
        for mode in (FRESH_PROCESS, PERSISTENT_PROCESS):
            controller = self.make(SUPERVISOR_ID, dict(sample_period_s=0.001, debounce_s=0.002), mode)
            self.assertEqual(self.supervisor_tick(controller, vcc=9.0)['VPERMIT'], 0.0)
            trace = [self.supervisor_tick(controller, sense=v) for v in (3.0, 2.9, 2.8, 3.0, 2.9, 2.9)]
            self.assertEqual([v['VFAULT'] for v in trace], [0.0] * 5 + [5.0])
            self.assertEqual([v['VCOMPARATOR'] for v in trace], [5.0, 5.0, 0.0, 5.0, 5.0, 5.0])
            self.assertEqual(self.supervisor_tick(controller, sense=2.9, reset=3.3)['VFAULT'], 5.0)
            self.assertEqual(self.supervisor_tick(controller, sense=2.8)['VFAULT'], 5.0)
            self.assertEqual(self.supervisor_tick(controller, sense=2.8, reset=3.3)['VFAULT'], 0.0)
            self.assertEqual(self.supervisor_tick(controller, vcc=9.0)['VPERMIT'], 5.0)
            self.assertEqual(self.supervisor_tick(controller, vcc=8.0)['VPERMIT'], 0.0)
            self.assertEqual(controller.state, {f'state_{i}': 0.0 for i in range(4)})
            traces.append(trace)
        self.assertEqual(traces[0], traces[1])

    def test_debounce_grid_refinement_and_zero_delay(self):
        delay = 0.0025
        errors = []
        for dt in (0.001, 0.0005):
            controller = self.make(SUPERVISOR_ID, dict(sample_period_s=dt, debounce_s=delay))
            fault_time = None
            for index in range(8):
                if self.supervisor_tick(controller, sense=3.0)['VFAULT']:
                    fault_time = index * dt
                    break
            self.assertIsNotNone(fault_time)
            self.assertGreaterEqual(fault_time, delay)
            self.assertLess(fault_time - delay, dt)
            errors.append(fault_time - delay)
        self.assertLess(errors[1], errors[0])
        immediate = self.make(SUPERVISOR_ID, dict(debounce_s=0.0))
        self.assertEqual(self.supervisor_tick(immediate, sense=3.0)['VFAULT'], 5.0)

    def test_mismatched_timestep_rejected_without_accepting_state(self):
        controller = self.make(PWM_ID, self.PWM_PARAMETERS)
        state = dict(controller.state)
        with self.assertRaises(CompiledBlockExecutionError):
            controller.step(dict(vcc=12, enable=3.3, feedback=0, current_sense=0, temperature=0), 0.0, 0.002)
        self.assertEqual(controller.state, state)
        self.assertEqual(controller.tick, 0)

    @unittest.skipUnless(NATIVE_LIBRARY.is_file(), 'real SPIKES DLL unavailable')
    def test_native_circuit_supply_sensing_and_latched_source_outputs(self):
        from python.spikes.native_abi import load_native_library
        from python.spikes.native_runner import _populate
        from python.spikes.netlist import parse_netlist

        controller = self.make(SUPERVISOR_ID, dict(sample_period_s=0.001, debounce_s=0.0))
        project = parse_netlist('''* Generic supervisor native coupling
VCC vcc 0 12
VSENSE sense 0 0
VENABLE enable 0 3.3
VRESET reset 0 0
VPERMIT permit 0 0
VFAULT fault 0 0
VCOMPARATOR comparator 0 0
RLOAD permit 0 1000
.tran 0.001 0.01
.end
''')
        controller.bind(project)
        with load_native_library(NATIVE_LIBRARY).circuit() as circuit:
            _populate(circuit, project)
            with circuit.transient_session() as session:
                self.assertEqual(controller.advance(session), {})
                self.assertTrue(session.step(0.001), session.message)
                self.assertEqual(session.node_voltage('permit'), 0.0)
                self.assertEqual(controller.advance(session)['VPERMIT'], 5.0)
                self.assertTrue(session.step(0.001), session.message)
                self.assertAlmostEqual(session.node_voltage('permit'), 5.0)
                session.set_source_value('VSENSE', 3.0)
                self.assertTrue(session.step(0.001), session.message)
                self.assertEqual(controller.advance(session)['VFAULT'], 5.0)
                self.assertTrue(session.step(0.001), session.message)
                self.assertAlmostEqual(session.node_voltage('permit'), 0.0)
                self.assertAlmostEqual(session.node_voltage('fault'), 5.0)


if __name__ == '__main__':
    unittest.main()
