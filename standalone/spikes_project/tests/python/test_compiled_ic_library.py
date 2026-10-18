# SPDX-License-Identifier: Apache-2.0
import os
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))

from spikes_studio.compiled_ic_library import catalog, configuration, load, save, validate
from spikes_studio.controller_block import Controller
from spikes_studio.ide import find_tool


class CompiledIcLibraryTests(unittest.TestCase):
    def test_catalog_has_explicit_sampled_contracts_and_detached_results(self):
        first = catalog()
        self.assertEqual({entry['id'] for entry in first['entries']}, {'generic.sampled_pwm', 'generic.sampled_pi'})
        for entry in first['entries']:
            self.assertTrue(entry['sampled_only'])
            self.assertTrue(entry['parameters'])
            self.assertTrue(entry['pins'])
            self.assertEqual([state['index'] for state in entry['state']], list(range(len(entry['state']))))
            self.assertIn('vendor', entry['limitations'].lower())
        first['entries'][0]['pins'][0]['node'] = 'changed'
        self.assertNotEqual(catalog()['entries'][0]['pins'][0]['node'], 'changed')

    def test_configuration_resolves_parameters_and_pin_bindings(self):
        config = configuration('generic.sampled_pwm',
            {'sample_period_s': 2e-5, 'switching_period_s': 1e-4, 'output_high_v': 5.0},
            {'duty': {'node': 'command'}, 'drive': {'source': 'VGATE'}})
        self.assertEqual(config['contract'], 'spikes/generic-controller/v1')
        self.assertEqual(config['step_s'], 2e-5)
        self.assertEqual(next(pin for pin in config['pins'] if pin['name'] == 'duty')['node'], 'command')
        output = next(pin for pin in config['pins'] if pin['name'] == 'drive')
        self.assertEqual((output['source'], output['vdd']), ('VGATE', 5.0))
        self.assertNotIn('@SWITCHING_PERIOD_S@', config['source'])
        with self.assertRaisesRegex(ValueError, 'integer multiple'):
            configuration('generic.sampled_pwm', {'sample_period_s': 3e-5, 'switching_period_s': 1e-4})
        with self.assertRaisesRegex(ValueError, 'Unknown compiled IC parameter'):
            configuration('generic.sampled_pwm', {'unreviewed': 1.0})

    def test_data_only_round_trip_and_malformed_import_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'controllers.spkiclib'
            save(path)
            restored = load(path)
            self.assertEqual(restored, catalog())
            path.write_text('{"contract":"spikes/compiled-ic-library/v1","contract":"duplicate"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                load(path)
        malformed = catalog()
        malformed['entries'][0]['state'][0]['index'] = 2
        with self.assertRaisesRegex(ValueError, 'contiguous'):
            validate(malformed)

    @unittest.skipUnless(find_tool('cl') or find_tool('clang'), 'C compiler not configured')
    def test_real_compiler_pwm_integer_ticks_do_not_drift_at_decimal_period(self):
        controller = Controller(configuration('generic.sampled_pwm', {
            'sample_period_s': 3e-4, 'switching_period_s': 3e-3, 'output_high_v': 5.0,
        }), trusted=True)
        try:
            samples = [controller.step({'duty': 0.5, 'enable': 3.3}, index * 3e-4, 3e-4)['VPWM'] for index in range(20)]
            cycle = [5.0] * 5 + [0.0] * 5
            self.assertEqual(samples, cycle + cycle)
            self.assertEqual(controller.state['state_0'], 0.0)
            self.assertEqual(controller.step({'duty': 1.0, 'enable': 0.0}, 6e-3, 3e-4), {'VPWM': 0.0})
        finally:
            controller.close()

    @unittest.skipUnless(find_tool('cl') or find_tool('clang'), 'C compiler not configured')
    def test_real_compiler_executes_pi_and_preserves_integral_state(self):
        controller = Controller(configuration('generic.sampled_pi', {
            'sample_period_s': 0.1, 'kp': 0.5, 'ki_per_s': 1.0,
            'output_min_v': 0.0, 'output_max_v': 1.0, 'output_envelope_v': 1.0,
        }), trusted=True)
        try:
            self.assertAlmostEqual(controller.step({'reference': 1.0, 'feedback': 0.0}, 0.0, 0.1)['VCOMMAND'], 0.6)
            self.assertAlmostEqual(controller.state['state_0'], 0.1)
            self.assertAlmostEqual(controller.step({'reference': 1.0, 'feedback': 0.0}, 0.1, 0.1)['VCOMMAND'], 0.7)
            self.assertAlmostEqual(controller.state['state_0'], 0.2)
        finally:
            controller.close()


if __name__ == '__main__':
    unittest.main()
