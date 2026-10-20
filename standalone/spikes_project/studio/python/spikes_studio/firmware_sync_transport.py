# SPDX-License-Identifier: Apache-2.0
"""Experimental causal, one-instruction Renode 1.17 GPIO rendezvous.

The plant supplies input at instruction START, then the CPU executes exactly
one instruction and returns native GPIO output events. No future CPU read is
allowed before the caller advances the plant and supplies its next inputs.
This is a functional instruction timing model, not continuous-time hardware
co-simulation. Alternate-function peripheral pin mux and WFI are unsupported.

Primary interface references reviewed 2026-10-20:
https://renode.readthedocs.io/en/latest/basic/control.html
https://renode.readthedocs.io/en/latest/basic/using-python.html
https://renode.readthedocs.io/en/latest/advanced/time_framework.html
The installed 1.17 monitor, not latest-doc spelling, defines SingleStep.
"""
from copy import deepcopy
from pathlib import Path
import re

from .firmware_edge_transport import MAX_EVENTS, MAX_PINS, admit_events
from .firmware_pad_state import decode_nrf, decode_stm32


class FirmwareSyncTransport:
    step_ns = 10

    def __init__(self, session, pins, *, capacity=MAX_EVENTS, max_steps=100000):
        if session.time_ns != 0:
            raise ValueError('Synchronous transport must attach before firmware execution')
        if any(getattr(session, name, None) is not None for name in ('edge_transport', 'sync_transport')):
            raise ValueError('Session already has a GPIO transport')
        if type(capacity) is not int or not 1 <= capacity <= MAX_EVENTS:
            raise ValueError('Invalid synchronous event capacity')
        if type(max_steps) is not int or not 1 <= max_steps <= 100000:
            raise ValueError('Synchronous instruction budget must be 1..100000')
        if not isinstance(pins, (list, tuple)) or not 1 <= len(pins) <= MAX_PINS:
            raise ValueError('Synchronous transport requires 1..32 pins')
        self.session = session
        self.capacity = capacity
        self.max_steps = max_steps
        self.steps = 0
        self.time_ns = 0
        self.ports = {}
        self.states = {}
        for port, pin in pins:
            session._gpio_device(port, pin)
            if (port, pin) in self.states:
                raise ValueError('Duplicate synchronous pin')
            self.ports.setdefault(port, []).append(pin)
            self.states[port, pin] = session.pad_configuration(port, pin)
        try:
            hook = str(Path(__file__).with_name('renode_sync_hook.py').resolve())
            session.engine.command('include @' + hook.replace('\\', '/').replace(' ', '\\ '))
            session.engine.command('sysbus.cpu MaximumBlockSize 1')
            session.engine.command('sysbus.cpu PerformanceInMips 100')
            session.engine.command('sysbus.cpu ExecutionMode SingleStep')
            session.engine.command('emulation SingleStepBlocking true')
            session.engine.command('sysbus.cpu DisableInterruptsWhileStepping false')
            session.engine.command('python "import sys; sys._spikes_sync = '
                'sys._spikes_sync_collector_type(monitor.Machine, %r, %r, %d)"' %
                (self.ports, session.is_stm, capacity))
            session.engine.command('sysbus.cpu SetHookAtBlockBegin "self.SyncTime()"')
            # Nordic peripheral PSEL ownership is not the GPIO PIN_CNF
            # direction. This transport has no admitted AF routing model:
            # reject these owners rather than publish GPIO state as pad state.
            rejected = (('dma1',) if session.is_stm else
                        ('gpiote', 'ppi', 'i2s', 'pdm', 'spi2', 'twi0', 'twi1',
                         'uart0', 'uart1', 'wdt'))
            for device in rejected:
                session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.' + device +
                    ' "import sys; value = sys._spikes_sync.reject()"')
            if session.is_stm:
                session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.dma2 '
                    '"import sys; value = sys._spikes_sync.dma(offset, value)"')
                session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.rcc '
                    '"import sys; value = sys._spikes_sync.reject() if offset == 16 and value & 511 else value"')
            session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.nvic '
                '"import sys; value = sys._spikes_sync.reject() if offset == 3340 and value & 4 else value"')
            session.sync_transport = self
        except BaseException:
            session.close()
            raise

    def set_inputs(self, inputs):
        """Inject one validated input batch while native execution is blocked."""
        if self.session.time_ns != self.time_ns:
            raise RuntimeError('Firmware advanced outside synchronous transport')
        if not isinstance(inputs, (list, tuple)) or len(inputs) > MAX_PINS:
            raise ValueError('Input batch exceeds pin limit')
        seen = set()
        commands = []
        for port, pin, level in inputs:
            if (port, pin) not in self.states or (port, pin) in seen or type(level) is not bool:
                raise ValueError('Invalid synchronous input batch')
            seen.add((port, pin))
            commands.append("monitor.Machine['sysbus.%s'].OnGPIO(%d, %r)" %
                            (self.session._gpio_device(port, pin), pin, level))
        if commands:
            try:
                self.session.engine.command('python "' + '; '.join(commands) + '"')
            except BaseException:
                self.session.close()
                raise

    def step(self):
        if self.steps >= self.max_steps:
            self.session.close()
            raise RuntimeError('Synchronous firmware instruction budget exhausted')
        if self.session.time_ns != self.time_ns:
            self.session.close()
            raise RuntimeError('Firmware advanced outside synchronous transport')
        try:
            text = self.session.engine.command('python "import sys; sys._spikes_sync.step()"')
            result = self._decode(text)
            self.time_ns = result['end_ns']
            self.session.time_ns = self.time_ns
            self.steps += 1
            return result
        except BaseException:
            self.session.close()
            raise

    def _decode(self, text):
        if 'SPIKES_SYNC_FAILED' in text:
            raise RuntimeError('Synchronous firmware rejected unsupported state, timing or event capacity')
        rows = re.findall(r'^\s*SPIKES_SYNC_V1 (\d+) ([A-I01]) (\d+) ([0-9 ]+)\s*$', text, re.M)
        ends = re.findall(r'^\s*SPIKES_SYNC_END (\d+) (\d+) (\d+)\s*$', text, re.M)
        if (len(ends) != 1 or int(ends[0][0]) != len(rows) or
                len(rows) > self.capacity or
                len(re.findall(r'^\s*SPIKES_SYNC_V1\b', text, re.M)) != len(rows)):
            raise RuntimeError('Incomplete synchronous firmware response')
        _, start, end = map(int, ends[0])
        if start != self.time_ns or end != start + self.step_ns:
            raise RuntimeError('Synchronous firmware clock mismatch')
        staged = deepcopy(self.states)
        events = []
        for stamp, port, pin_text, word_text in rows:
            pin, timestamp = int(pin_text), int(stamp)
            if (port, pin) not in staged or timestamp != start:
                # The admitted subset has no autonomous pad transitions between
                # instruction boundaries. Do not quantize a peripheral timestamp.
                raise RuntimeError('Unsupported autonomous GPIO event timing or pin')
            words = [int(w) for w in word_text.split()]
            if len(words) != (5 if self.session.is_stm else 2):
                raise RuntimeError('Synchronous register shape mismatch')
            config = (decode_stm32(*words, pin) if self.session.is_stm else
                      decode_nrf(*words, pin))
            if config != staged[port, pin]:
                events.append({'time_ns': timestamp, 'port': port, 'pin': pin, 'config': config})
                staged[port, pin] = config
        events = admit_events(events, start, end, capacity=self.capacity)
        self.states = staged
        return {'start_ns': start, 'end_ns': end, 'events': events}

    def provenance(self):
        return {'timing_mode': 'synchronous_instruction_boundary_gpio',
                'instruction_period_ns': self.step_ns, 'instructions': self.steps,
                'input_semantics': 'feedback before every native instruction',
                'output_capture': 'native GPIO signals plus boundary configuration changes',
                'admitted_dma': 'STM32 DMA2 stream0 immediate SRAM word burst to captured GPIO BSRR only',
                'excluded': ['alternate-function pin mux', 'PWM', 'WFI', 'reset',
                             'triggered DMA', 'DMA input reads', 'GPIOTE', 'PPI',
                             'Nordic serial/audio peripheral pin ownership'],
                'continuous_time_coupling': False, 'cycle_accurate': False,
                'max_steps': self.max_steps, 'capture_event_capacity': self.capacity}
