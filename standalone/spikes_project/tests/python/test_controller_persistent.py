# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import json
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'studio/python'))

from python.spikes.compiled_blocks import CompiledBlockExecutionError, CompiledBlockRuntimeLimits
from spikes_studio.controller_block import Controller, default_config
from spikes_studio.ide import find_tool


COMPILER_AVAILABLE = bool(find_tool('cl') or find_tool('clang'))


def controller_config(source, language='C'):
    config = default_config()
    config['language'] = language
    config['pins'][1].update(mode='AO', vdd=1000.0)
    config['source'] = source
    return config


@unittest.skipUnless(COMPILER_AVAILABLE, 'C/C++ compiler not configured')
class PersistentControllerTests(unittest.TestCase):
    def test_opt_in_persists_native_statics_and_reset_restarts_process(self):
        source = '''static int native_ticks = 0;
void control_step(double time_s, double step_s, const double *inputs,
                  double *outputs, double *state) {
    (void)time_s; (void)step_s;
    native_ticks += 1;
    state[0] += inputs[0];
    outputs[0] = (double)native_ticks;
}
'''
        for language in ('C', 'C++'):
            config = controller_config(source, language)
            legacy = Controller(config, trusted=True)
            persistent = Controller(config, trusted=True, execution_mode='persistent_process')
            try:
                self.assertEqual(legacy.execution_mode, 'fresh_process')
                self.assertEqual(legacy.step({'sense': 2.0}, 0.0, 0.1), {'V1': 1.0})
                self.assertEqual(legacy.step({'sense': 3.0}, 0.1, 0.1), {'V1': 1.0})
                self.assertEqual(legacy.state['state_0'], 5.0)

                self.assertEqual(persistent.step({'sense': 2.0}, 0.0, 0.1), {'V1': 1.0})
                self.assertEqual(persistent.step({'sense': 3.0}, 0.1, 0.1), {'V1': 2.0})
                self.assertEqual(persistent.state['state_0'], 5.0)
                persistent.reset()
                self.assertEqual(persistent.step({'sense': 4.0}, 0.0, 0.1), {'V1': 1.0})
                self.assertEqual(persistent.state['state_0'], 4.0)
            finally:
                legacy.close()
                persistent.close()

    def test_malformed_output_is_rejected_and_worker_is_stopped(self):
        controller = Controller(controller_config('''void control_step(double t, double dt, const double *inputs, double *outputs, double *state) {
    (void)t; (void)dt; (void)inputs; printf("{}\\n"); outputs[0] = 1.0; state[0] += 1.0;
}
'''), trusted=True, execution_mode='persistent_process')
        try:
            with self.assertRaisesRegex(CompiledBlockExecutionError, 'invalid_response_schema'):
                controller.step({'sense': 0.0}, 0.0, 0.1)
            self.assertIsNone(controller._process)
        finally:
            controller.close()

    def test_timeout_and_native_crash_stop_the_worker(self):
        timeout_controller = Controller(controller_config('''void control_step(double t, double dt, const double *inputs, double *outputs, double *state) {
    (void)t; (void)dt; (void)inputs; (void)outputs; (void)state;
    for (volatile unsigned long long i = 0;; ++i) {}
}
'''), trusted=True, execution_mode='persistent_process')
        timeout_controller._limits = CompiledBlockRuntimeLimits(timeout_s=0.1)
        try:
            with self.assertRaisesRegex(CompiledBlockExecutionError, 'process_timeout'):
                timeout_controller.step({'sense': 0.0}, 0.0, 0.1)
            self.assertIsNone(timeout_controller._process)
        finally:
            timeout_controller.close()

        crash_controller = Controller(controller_config('''void control_step(double t, double dt, const double *inputs, double *outputs, double *state) {
    (void)t; (void)dt; (void)inputs; (void)outputs; (void)state; exit(9);
}
'''), trusted=True, execution_mode='persistent_process')
        try:
            with self.assertRaises(CompiledBlockExecutionError) as raised:
                crash_controller.step({'sense': 0.0}, 0.0, 0.1)
            self.assertIn(raised.exception.code, {'process_failed', 'process_io_failed'})
            self.assertIsNone(crash_controller._process)
        finally:
            crash_controller.close()

    def test_request_write_and_response_share_one_deadline(self):
        config = default_config()
        config['state_count'] = 64
        config['pins'] = [
            {'name': f'input_{index:02d}_' + 'x' * 23, 'mode': 'AI', 'node': f'n{index}',
             'reference': '0', 'source': '', 'vdd': 3.3}
            for index in range(63)
        ] + [{'name': 'drive', 'mode': 'AO', 'node': '', 'reference': '0', 'source': 'V1', 'vdd': 1000.0}]
        manual_response = json.dumps({
            'contract': 'spikes/compiled-block-response/v1', 'request_id': 'tick_0',
            'ports': {'drive': 0.0}, 'state': {f'state_{index}': 0.0 for index in range(64)},
        }, separators=(',', ':'))
        c_response = manual_response.replace('\\', '\\\\').replace('"', '\\"')
        config['source'] = f'''void control_step(double t, double dt, const double *inputs, double *outputs, double *state) {{
    (void)t; (void)dt; (void)inputs; (void)outputs; (void)state;
    printf("{c_response}\\n"); fflush(stdout);
    for (volatile unsigned long long i = 0;; ++i) {{}}
}}
'''
        controller = Controller(config, trusted=True, execution_mode='persistent_process')
        controller._limits = CompiledBlockRuntimeLimits(timeout_s=0.2)
        values = {pin['name']: 1.2345678901234567e+300 for pin in config['pins'] if pin['mode'] == 'AI'}
        try:
            self.assertEqual(controller.step(values, 0.0, 0.1), {'V1': 0.0})
            oversized = json.dumps({
                'contract': 'spikes/compiled-block-request/v1', 'request_id': 'tick_1',
                'time_s': 0.1, 'step_s': 0.1, 'ports': values, 'state': controller.state,
            }, sort_keys=True, separators=(',', ':')).encode() + b'\n'
            self.assertGreater(len(oversized), 4096)
            native_writer = controller._writer_thread

            outcome = {}
            def blocked_step():
                try:controller.step(values, 0.1, 0.1)
                except Exception as exc:outcome['error'] = exc
            worker = threading.Thread(target=blocked_step, daemon=True)
            started = time.perf_counter();worker.start();worker.join(timeout=2.0)
            if worker.is_alive() and controller._process is not None:
                controller._process.kill();worker.join(timeout=2.0)
            self.assertFalse(worker.is_alive(), 'bounded request write did not return')
            self.assertLess(time.perf_counter() - started, 1.5)
            self.assertIsInstance(outcome.get('error'), CompiledBlockExecutionError)
            self.assertEqual(outcome['error'].code, 'process_timeout')
            self.assertIsNone(controller._process)
            self.assertIsNotNone(native_writer)
            self.assertFalse(native_writer.is_alive())
        finally:
            controller.close()

    def test_close_terminates_worker_and_rejects_more_steps(self):
        controller = Controller(default_config(), trusted=True, execution_mode='persistent_process')
        controller.step({'sense': 0.0}, 0.0, 0.1)
        process = controller._process
        self.assertIsNotNone(process)
        controller.close()
        self.assertIsNotNone(process.poll())
        with self.assertRaisesRegex(CompiledBlockExecutionError, 'controller_closed'):
            controller.step({'sense': 0.0}, 0.1, 0.1)
        controller.close()

    def test_50_tick_actual_process_comparison(self):
        ticks = 50
        config = default_config()
        fresh = Controller(config, trusted=True)
        persistent = Controller(config, trusted=True, execution_mode='persistent_process')
        try:
            fresh_start = time.perf_counter()
            fresh_values = [fresh.step({'sense': float(index % 2)}, index * 1e-4, 1e-4) for index in range(ticks)]
            fresh_seconds = time.perf_counter() - fresh_start

            persistent_start = time.perf_counter()
            persistent_values = [persistent.step({'sense': float(index % 2)}, index * 1e-4, 1e-4) for index in range(ticks)]
            persistent_seconds = time.perf_counter() - persistent_start

            self.assertEqual(persistent_values, fresh_values)
            self.assertEqual(persistent.state, fresh.state)
            self.assertGreater(fresh_seconds, 0.0)
            self.assertGreater(persistent_seconds, 0.0)
            print(f'controller benchmark: ticks={ticks}; fresh cold={ticks}, warm=0, seconds={fresh_seconds:.6f}, ticks/s={ticks/fresh_seconds:.1f}; '
                  f'persistent cold=1, warm={ticks-1}, seconds={persistent_seconds:.6f}, ticks/s={ticks/persistent_seconds:.1f}')
        finally:
            fresh.close()
            persistent.close()


if __name__ == '__main__':
    unittest.main()
