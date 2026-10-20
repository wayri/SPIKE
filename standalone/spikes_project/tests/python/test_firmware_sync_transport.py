# SPDX-License-Identifier: Apache-2.0
"""Original instruction/feedback and native DMA-output regression fixtures."""
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'standalone/spikes_project/studio/python'))
from spikes_studio.firmware_pad_state import decode_stm32
from spikes_studio.firmware_session import FirmwareSession
from spikes_studio.firmware_sync_transport import FirmwareSyncTransport
from spikes_studio.renode_process import find_runtime
from spikes_studio.renode_sync_hook import SpikesSyncCollector


class ThumbFixture:
    """Tiny original Cortex-M fixture encoder, not a production compiler."""
    def __init__(self):
        self.data = bytearray(256)
        struct.pack_into('<II', self.data, 0, 0x20020000, 0x08000101)
        self.literals = []

    def emit(self, word):
        self.data.extend(struct.pack('<H', word))

    def load(self, register, value):
        self.literals.append((len(self.data), register, value))
        self.emit(0)

    def write(self, address, value):
        self.load(0, address)
        self.load(1, value)
        self.emit(0x6001)  # STR r1,[r0].

    def finish(self):
        self.emit(0xe7fe)
        while len(self.data) % 4:
            self.data.append(0)
        for offset, register, value in self.literals:
            displacement = (len(self.data) - ((offset + 4) & ~3)) // 4
            assert 0 <= displacement <= 255
            struct.pack_into('<H', self.data, offset,
                             0x4800 | (register << 8) | displacement)
            self.data.extend(struct.pack('<I', value))
        return bytes(self.data)


def feedback_firmware():
    fixture = ThumbFixture()
    fixture.write(0x40020400, 1)       # PB0 output, PB2 input.
    fixture.write(0x40020418, 1)       # Output high at instruction 5 / 50 ns.
    fixture.load(0, 0x40020410)        # IDR address at 60 ns.
    fixture.emit(0x6802)              # LDR r2,[r0] at 70 ns.
    fixture.emit(0x6803)              # LDR r3,[r0] at 80 ns.
    fixture.write(0x40020418, 65536)   # Output low.
    return fixture.finish()


def dma_firmware(control=0x5281, count=2):
    fixture = ThumbFixture()
    fixture.write(0x40020400, 1)
    fixture.write(0x20000000, 1)
    fixture.write(0x20000004, 65536)
    fixture.write(0x40026414, count)
    fixture.write(0x40026418, 0x20000000)
    fixture.write(0x4002641c, 0x40020418)
    fixture.write(0x40026410, control)
    return fixture.finish()


def nordic_feedback_firmware():
    fixture = ThumbFixture()
    struct.pack_into('<II', fixture.data, 0, 0x20040000, 0x101)
    fixture.write(0x50000708, 0)       # P0.02 input connected.
    fixture.write(0x5000070c, 1)       # P0.03 output.
    fixture.load(0, 0x50000510)
    fixture.emit(0x6802)
    fixture.emit(0x6803)
    return fixture.finish()


class SyncProtocolTests(unittest.TestCase):
    def transport(self):
        transport = FirmwareSyncTransport.__new__(FirmwareSyncTransport)
        transport.session = SimpleNamespace(is_stm=True)
        transport.capacity = 256
        transport.time_ns = 0
        transport.states = {('B', 0): decode_stm32(1, 0, 0, 0, 0, 0)}
        return transport

    def test_native_signal_pulse_survives_identical_end_state(self):
        transport = self.transport()
        result = transport._decode(
            'SPIKES_SYNC_V1 0 B 0 1 0 0 0 1\n'
            'SPIKES_SYNC_V1 0 B 0 1 0 0 0 0\n'
            'SPIKES_SYNC_END 2 0 10\n')
        self.assertEqual([e['config']['state']['output'] for e in result['events']],
                         ['high', 'low'])

    def test_reject_incomplete_outside_instruction_and_noninteger_grid(self):
        for text in (
                'SPIKES_SYNC_V1 0 B 0 1 0 0 0 1\n',
                'SPIKES_SYNC_END 0 0 11\n',
                'SPIKES_SYNC_END 0 10 20\n',
                'SPIKES_SYNC_V1 1 B 0 1 0 0 0 1\nSPIKES_SYNC_END 1 0 10\n',
                'SPIKES_SYNC_V1 x\nSPIKES_SYNC_END 0 0 10\n',
                'SPIKES_SYNC_FAILED\n'):
            transport = self.transport()
            initial = transport.states.copy()
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                transport._decode(text)
            self.assertEqual(transport.states, initial)

    def test_input_batch_is_validated_before_any_injection(self):
        transport = self.transport()
        commands = []
        transport.session.time_ns = 0
        transport.session.engine = SimpleNamespace(command=commands.append)
        transport.session._gpio_device = lambda p, i: 'gpioPort' + p
        with self.assertRaises(ValueError):
            transport.set_inputs([('B', 0, True), ('B', 0, False)])
        self.assertEqual(commands, [])

    def test_dma_guard_rejects_nonmemory_sources_ranges_and_streams(self):
        for source, count, destination, offset, control in (
                (0x40020410, 2, 0x40020418, 16, 0x5281),
                (0x2001fffc, 2, 0x40020418, 16, 0x5281),
                (0x20000001, 2, 0x40020418, 16, 0x5281),
                (0x20000000, 257, 0x40020418, 16, 0x5281),
                (0x20000000, 2, 0x40020400, 16, 0x5281),
                (0x20000000, 2, 0x40020418, 40, 0x5281),
                (0x20000000, 2, 0x40020418, 16, 0x5481)):
            collector = SpikesSyncCollector.__new__(SpikesSyncCollector)
            values = {20: count, 24: source, 28: destination}
            collector.machine = {'sysbus.dma2': SimpleNamespace(
                ReadDoubleWord=values.__getitem__)}
            collector.ports = {'B': [0]}
            collector.capacity = 256
            collector.failed = False
            with self.subTest(source=source, count=count, offset=offset, control=control):
                self.assertEqual(collector.dma(offset, control), 0)
                self.assertTrue(collector.failed)


@unittest.skipUnless(os.environ.get('SPIKES_TEST_FIRMWARE') == '1', 'opt-in native Renode test')
class SyncNativeTests(unittest.TestCase):
    def session(self, folder, payload):
        image = Path(folder) / 'original.bin'
        image.write_bytes(payload)
        return FirmwareSession(find_runtime(), image,
                               'st-stm32f407g-disc1-mb997', trusted=True)

    def test_feedback_between_consecutive_native_input_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.session(folder, feedback_firmware()) as session:
                transport = FirmwareSyncTransport(session, [('B', 0), ('B', 2)])
                events = []
                for _ in range(7):
                    events.extend(transport.step()['events'])
                self.assertEqual(session.time_ns, 70)
                transport.set_inputs([('B', 2, True)])
                transport.step()  # First input read consumes committed t=70 ns.
                transport.set_inputs([('B', 2, False)])
                transport.step()  # Next read consumes committed t=80 ns.
                registers = session.engine.command(
                    'python "print int(monitor.Machine[\'sysbus.cpu\'].GetRegisterUlong(2)); '
                    'print int(monitor.Machine[\'sysbus.cpu\'].GetRegisterUlong(3))"')
                import re
                values = [int(v) for v in re.findall(r'^\s*(\d+)\s*$', registers, re.M)]
                self.assertEqual([value & 4 for value in values], [4, 0])
                self.assertEqual([e['time_ns'] for e in events], [20, 50])

    def test_native_dma_two_events_not_final_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.session(folder, dma_firmware()) as session:
                transport = FirmwareSyncTransport(session, [('B', 0)])
                events = []
                for _ in range(21):
                    events.extend(transport.step()['events'])
                pulse = [e for e in events if e['time_ns'] == 200]
                self.assertEqual([e['config']['state']['output'] for e in pulse],
                                 ['high', 'low'])
                self.assertEqual(session.gpio_state('B')['output'], 0)
                self.assertEqual(session.read32(0x40026414), 0)

    def test_both_nordic_targets_receive_between_consecutive_reads(self):
        for target in ('nordic-nrf52840-dk-pca10056-r3-0-2',
                       'arduino-nano-33-ble-abx00030'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as folder:
                image = Path(folder) / 'original.bin'
                image.write_bytes(nordic_feedback_firmware())
                with FirmwareSession(find_runtime(), image, target, trusted=True) as session:
                    transport = FirmwareSyncTransport(session, [('0', 2), ('0', 3)])
                    for _ in range(7):
                        transport.step()
                    transport.set_inputs([('0', 2, True)])
                    transport.step()
                    transport.set_inputs([('0', 2, False)])
                    transport.step()
                    registers = session.engine.command(
                        'python "print int(monitor.Machine[\'sysbus.cpu\'].GetRegisterUlong(2)); '
                        'print int(monitor.Machine[\'sysbus.cpu\'].GetRegisterUlong(3))"')
                    import re
                    values = [int(v) for v in re.findall(r'^\s*(\d+)\s*$', registers, re.M)]
                    self.assertEqual([value & 4 for value in values], [4, 0])

    def test_dma_input_source_or_nonadmitted_control_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.session(folder, dma_firmware(control=0x5283)) as session:
                transport = FirmwareSyncTransport(session, [('B', 0)])
                for _ in range(20):
                    transport.step()
                with self.assertRaisesRegex(RuntimeError, 'unsupported'):
                    transport.step()
                self.assertIsNotNone(session.engine.process.poll())

    def test_event_and_instruction_budgets_reap_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.session(folder, feedback_firmware()) as session:
                transport = FirmwareSyncTransport(session, [('B', 0)], max_steps=1)
                transport.step()
                with self.assertRaisesRegex(RuntimeError, 'budget'):
                    transport.step()
                self.assertIsNotNone(session.engine.process.poll())


if __name__ == '__main__':
    unittest.main()
