# SPDX-License-Identifier: Apache-2.0
"""Execute a real compiled sampled controller generated from a board pin map."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'standalone/spikes_project/studio/python'))
from spikes_studio.controller_boards import records
from spikes_studio.controller_board_blocks import create, controller_config
from spikes_studio.controller_block import Controller
from spikes_studio.ide import find_tool


class BoardCompiledTests(unittest.TestCase):
    @unittest.skipUnless(find_tool('cl') or find_tool('clang'), 'C compiler unavailable')
    def test_real_c_threshold_callback_uses_mapped_pin_identifiers(self):
        block = create(records()[0], 0, 0)
        ai = next(pin for pin in block['board']['pins'] if 'analog_input' in pin['capabilities'])
        do = next(pin for pin in block['board']['pins'] if 'digital_io' in pin['capabilities'] and pin != ai)
        block['bindings'][ai['id']].update(mode='AI', node='out', reference='0')
        block['bindings'][do['id']].update(mode='DO', source='VDRIVE')
        config = controller_config(block)
        input_name = block['bindings'][ai['id']]['code_name']
        output_name = block['bindings'][do['id']]['code_name']
        config['source'] = f'''void control_step(double time_s, double step_s,
const double *inputs, double *outputs, double *state) {{
    outputs[OUT_{output_name}] = inputs[IN_{input_name}] > 1.0 ? 1.0 : 0.0;
}}'''
        runtime = Controller(config, trusted=True)
        try:
            self.assertEqual(runtime.step({input_name: .5}, 0., .0001), {'VDRIVE': 0.})
            self.assertEqual(runtime.step({input_name: 2.}, .0001, .0001),
                             {'VDRIVE': block['bindings'][do['id']]['vdd']})
        finally:
            runtime.close()


if __name__ == '__main__':
    unittest.main()
