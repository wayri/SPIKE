# SPDX-License-Identifier: Apache-2.0
"""Independent event-contract and opt-in real runtime regression oracles."""
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'standalone/spikes_project/studio/python'))
sys.path.insert(0, str(ROOT))
from spikes_studio.firmware_edge_transport import FirmwareEdgeTransport, admit_events
from spikes_studio.firmware_pad_state import decode_stm32
from spikes_studio.firmware_session import FirmwareSession
from spikes_studio.renode_process import find_runtime
from scripts.make_spikes_firmware_examples import gpio_echo


def pulse_firmware():
    """Original linear Thumb program: PB0 high then low within one acquisition.

    At 100 MIPS and one instruction/block: MODER write20 ns, BSRR high50 ns,
    BSRR low100 ns. Three intervening NOPs make an independently counted50 ns
    pulse. No external compiler or firmware implementation is involved.
    """
    data = bytearray(256)
    struct.pack_into('<II', data, 0, 0x20020000, 0x08000101)
    literals = []
    def emit(word):
        data.extend(struct.pack('<H', word))
    def load(register, value):
        literals.append((len(data), register, value)); emit(0)
    load(0, 0x40020400); emit(0x2101); emit(0x6001)
    load(0, 0x40020418); emit(0x2101); emit(0x6001)
    for _ in range(3): emit(0xbf00)
    load(1, 0x10000); emit(0x6001)
    emit(0xe7fe)
    while len(data) % 4: data.append(0)
    for offset, register, value in literals:
        displacement = (len(data) - ((offset + 4) & ~3)) // 4
        struct.pack_into('<H', data, offset, 0x4800 | (register << 8) | displacement)
        data.extend(struct.pack('<I', value))
    return bytes(data)


class EdgeAdmissionTests(unittest.TestCase):
    def event(self, time=10, output=0):
        return {'time_ns': time, 'port': 'B', 'pin': 0,
                'config': decode_stm32(1, 0, 0, 0, output, 0)}

    def test_order_same_timestamp_and_deep_copy(self):
        source = [self.event(10, 1), self.event(10, 0)]
        admitted = admit_events(source, 0, 20)
        self.assertEqual([e['config']['state']['output'] for e in admitted], ['high', 'low'])
        admitted[0]['config']['state']['output'] = 'low'
        self.assertEqual(source[0]['config']['state']['output'], 'high')

    def test_reject_stale_unordered_future_fraction_bool_and_overflow(self):
        for events in ([self.event(9)], [self.event(12), self.event(11)],
                       [self.event(21)], [self.event(10.5)], [self.event(True)],
                       [self.event()] * 257):
            with self.subTest(events=events[:2]), self.assertRaises(ValueError):
                admit_events(events, 10, 20)

    def test_reject_invalid_drive_mode(self):
        event = self.event()
        event['config']['state']['mode'] = 'PWM'
        with self.assertRaises(ValueError): admit_events([event], 0, 20)

    def test_complete_batch_and_virtual_endpoint_required_before_state_commit(self):
        capture = FirmwareEdgeTransport.__new__(FirmwareEdgeTransport)
        capture.session = SimpleNamespace(is_stm=True)
        capture.capacity = 256
        capture.ports = {'B': [0]}
        capture.states = {('B', 0): decode_stm32(0, 0, 0, 0, 0, 0)}
        initial = capture.states.copy()
        for text in ('SPIKES_GPIO_V1 10 B 1 0 0 0 1\n',
                     'SPIKES_GPIO_V1 10 B invalid\nSPIKES_GPIO_END 0 20\n',
                     'SPIKES_GPIO_END 0 19\n',
                     'SPIKES_GPIO_V1 10 B 1 0 0 0 1\nSPIKES_GPIO_V1 9 B 1 0 0 0 0\nSPIKES_GPIO_END 2 20\n'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                capture._decode(text, 0, 20)
            self.assertEqual(capture.states, initial)


@unittest.skipUnless(os.environ.get('SPIKES_TEST_FIRMWARE') == '1', 'opt-in native Renode test')
class EdgeNativeTests(unittest.TestCase):
    def session(self, folder):
        image = Path(folder) / 'pulse.bin'; image.write_bytes(pulse_firmware())
        return FirmwareSession(find_runtime(), image, 'st-stm32f407g-disc1-mb997', trusted=True)

    def test_subinterval_pulse_exact_virtual_instruction_times(self):
        with tempfile.TemporaryDirectory() as folder, self.session(folder) as session:
            capture = FirmwareEdgeTransport(session, [('B', 0)])
            events = capture.run_for_ns(1000)
            self.assertEqual([e['time_ns'] for e in events], [20, 50, 100])
            self.assertEqual([e['config']['state']['output'] for e in events], ['low', 'high', 'low'])
            self.assertFalse(session.output_level('B', 0))
            self.assertEqual(capture.run_for_ns(1000), [])

    def test_queue_overflow_aborts_and_reaps_runtime(self):
        with tempfile.TemporaryDirectory() as folder, self.session(folder) as session:
            capture = FirmwareEdgeTransport(session, [('B', 0)], capacity=1)
            with self.assertRaises((RuntimeError, ValueError)):
                capture.run_for_ns(1000)
            self.assertIsNotNone(session.engine.process.poll())

    def test_partitioned_capture_preserves_same_instruction_timestamps(self):
        with tempfile.TemporaryDirectory() as folder, self.session(folder) as session:
            capture = FirmwareEdgeTransport(session, [('B', 0)])
            first = capture.run_for_ns(70)
            second = capture.run_for_ns(930)
            self.assertEqual([e['time_ns'] for e in first + second], [20, 50, 100])

    def test_unsupported_dma_fails_batch_without_partial_events(self):
        with tempfile.TemporaryDirectory() as folder, self.session(folder) as session:
            capture = FirmwareEdgeTransport(session, [('B', 0)])
            session.engine.command('sysbus WriteDoubleWord 0x40026010 0')
            with self.assertRaisesRegex(RuntimeError, 'unsupported'):
                capture.run_for_ns(1000)
            self.assertIsNotNone(session.engine.process.poll())

    def test_timestamped_controller_advances_native_plant_through_hidden_pulse(self):
        from spikes_studio.firmware_timestamped import TimestampedFirmwareController
        from spikes_studio.firmware_electrical import PadConnection
        from python.spikes.native_abi import load_native_library
        from python.spikes.native_runner import _populate
        from python.spikes.netlist import parse_netlist
        library=os.environ.get('SPIKES_TEST_NATIVE_LIBRARY',str(ROOT/'build-spikes-io-pad-20261019/Release/spikes_c_api.dll'))
        project=parse_netlist('Captured pulse\nVDD vdd 0 3.3\nRLOAD out 0 1k\nCLOAD out 0 1n\n.tran 100n 2u\n.end\n')
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'pulse.bin';image.write_bytes(pulse_firmware())
            bridge=TimestampedFirmwareController(find_runtime(),image,'st-stm32f407g-disc1-mb997',[
                PadConnection('PB0','B',0,'out','vdd')],step_s=1e-6,trusted=True)
            try:
                bridge.bind(project)
                with load_native_library(library).circuit() as c:
                    _populate(c,project);bridge.configure_circuit(c,project)
                    with c.transient_session(initialize_from_operating_point=True) as plant:
                        bridge.advance(plant);self.assertTrue(plant.step(100e-9),plant.message)
                        self.assertAlmostEqual(plant.node_voltage('out'),1.60975609756,delta=1e-7)
                        for _ in range(19):
                            bridge.advance(plant);self.assertTrue(plant.step(100e-9),plant.message)
                        self.assertEqual(bridge.edge_count,3)
                        self.assertEqual([e['time_ns'] for e in bridge.edges],[20,50,100])
                        self.assertGreater(plant.step_index,20) # internal event steps are real solver steps
                        self.assertEqual(bridge.session.time_ns,2000)
            finally:bridge.close()

    def test_nrf_configuration_and_output_edges_are_native(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'echo.bin'; image.write_bytes(gpio_echo())
            with FirmwareSession(find_runtime(), image,
                    'nordic-nrf52840-dk-pca10056-r3-0-2', trusted=True) as session:
                capture = FirmwareEdgeTransport(session, [('0', 3)])
                configuration = capture.run_for_ns(1000)
                self.assertEqual([e['time_ns'] for e in configuration], [20, 80])
                session.set_gpio('0', 2, True)
                edges = capture.run_for_ns(1000)
                self.assertEqual([e['time_ns'] for e in edges], [1130])
                self.assertEqual(edges[0]['config']['state']['output'], 'high')


if __name__ == '__main__': unittest.main()
