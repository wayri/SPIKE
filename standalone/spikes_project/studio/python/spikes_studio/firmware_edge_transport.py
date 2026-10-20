# SPDX-License-Identifier: Apache-2.0
"""Bounded, instruction-time software GPIO capture for native Renode 1.17.

This is not end-sample edge inference. A hook saves each CPU GPIO write's
virtual timestamp, then reads the resulting native register state before the
next GPIO write (or while paused after RunFor). Single-instruction translation
blocks prevent block-start timestamp quantization. Hardware alternate/PWM,
DMA GPIO writes, reset during capture and continuously coupled inputs are not
supported. Inputs must remain held for each bounded lookahead interval.

Public references (reviewed 2026-10-19):
https://renode.readthedocs.io/en/latest/basic/using-python.html#system-bus-hooks
https://renode.readthedocs.io/en/latest/advanced/time_framework.html
Renode 1.17.0 public monitor: MaximumBlockSize, SyncTime, ReadDoubleWord.
This independently authored adapter imports no upstream implementation code.
"""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import math
import re

from .firmware_pad_state import decode_nrf, decode_stm32


MAX_EVENTS = 256
MAX_PINS = 32
MAX_INTERVAL_NS = 1_000_000


def _integer(value, name, maximum=(1 << 63) - 1):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(name + ' must be a bounded nonnegative integer')
    return value


def admit_events(events, start_ns, end_ns, *, capacity=MAX_EVENTS):
    """Validate a complete ordered batch before any plant mutation.

    Equal timestamps preserve transport order; they are never sorted by pin.
    This admission primitive does not assert that supplied events were captured.
    """
    _integer(start_ns, 'start_ns'); _integer(end_ns, 'end_ns')
    if end_ns < start_ns:
        raise ValueError('Reversed event interval')
    if type(capacity) is not int or not 1 <= capacity <= MAX_EVENTS:
        raise ValueError('Invalid event capacity')
    if not isinstance(events, (list, tuple)) or len(events) > capacity:
        raise ValueError('GPIO event queue overflow')
    previous = start_ns
    admitted = []
    for event in events:
        if not isinstance(event, dict) or set(event) != {'time_ns', 'port', 'pin', 'config'}:
            raise ValueError('Malformed GPIO event')
        timestamp = _integer(event['time_ns'], 'time_ns')
        if not previous <= timestamp <= end_ns:
            raise ValueError('GPIO event is stale, unordered or beyond the interval')
        if not isinstance(event['port'], str) or not re.fullmatch('[A-I01]', event['port']):
            raise ValueError('Invalid GPIO port')
        _integer(event['pin'], 'pin', 31 if event['port'].isdigit() else 15)
        if event['port'] == '1' and event['pin'] > 15:
            raise ValueError('nRF P1 pin exceeds implemented range')
        config = event['config']
        if not isinstance(config, dict) or not isinstance(config.get('state'), dict):
            raise ValueError('Missing GPIO configuration')
        state = config['state']
        if (set(state) != {'mode', 'output', 'drive_level', 'pull'} or
            state['mode'] not in ('input', 'push_pull', 'open_drain', 'open_source') or
            state['output'] not in ('low', 'high', 'released') or
            state['drive_level'] not in ('weak', 'strong') or
            state['pull'] not in ('none', 'up', 'down')):
            raise ValueError('Invalid GPIO configuration state')
        if ((state['mode'] == 'input' and state['output'] != 'released') or
            (state['mode'] == 'push_pull' and state['output'] == 'released') or
            (state['mode'] == 'open_drain' and state['output'] == 'high') or
            (state['mode'] == 'open_source' and state['output'] == 'low')):
            raise ValueError('Inconsistent GPIO drive state')
        admitted.append(dict(event, config=deepcopy(config)))
        previous = timestamp
    return admitted


class FirmwareEdgeTransport:
    """Explicit opt-in transport attached to an already trusted paused session."""

    def __init__(self, session, pins, *, capacity=MAX_EVENTS):
        if getattr(session, 'edge_transport', None) is not None:
            raise ValueError('Session already has GPIO edge capture')
        if type(capacity) is not int or not 1 <= capacity <= MAX_EVENTS:
            raise ValueError('Invalid edge capacity')
        if not isinstance(pins, (list, tuple)) or not 1 <= len(pins) <= MAX_PINS:
            raise ValueError('GPIO capture requires 1..32 distinct pins')
        if len(set(pins)) != len(pins):
            raise ValueError('Duplicate GPIO capture pin')
        self.session = session
        self.capacity = capacity
        self.ports = {}
        for port, pin in pins:
            session._gpio_device(port, pin)
            self.ports.setdefault(port, []).append(pin)
        self.time_ns = session.time_ns
        hook = Path(__file__).with_name('renode_edge_hook.py')
        name = str(hook.resolve()).replace('\\', '/').replace(' ', '\\ ')
        try:
            self.states = {(port, pin): session.pad_configuration(port, pin) for port, pin in pins}
            session.engine.command('include @' + name)
            session.engine.command('sysbus.cpu MaximumBlockSize 1')
            command = ('import sys; sys._spikes_gpio_edges = sys._spikes_gpio_collector_type('
                       'monitor.Machine, %r, %r, %d)' % (self.ports, session.is_stm, capacity))
            session.engine.command('python "' + command + '"')
            for port in self.ports:
                device = session._gpio_device(port, 0)
                session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.' + device +
                    ' "import sys; sys._spikes_gpio_edges.before(\'' + port + '\')"')
            # These engines can alter GPIO without a CPU GPIO-register write.
            # Reject their configuration rather than silently omit such edges.
            for device in (('dma1', 'dma2') if session.is_stm else ('gpiote', 'ppi')):
                session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.' + device +
                    ' "import sys; sys._spikes_gpio_edges.reject()"')
            session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.nvic '
                '"import sys; sys._spikes_gpio_edges.reject() if offset == 3340 and value & 4 else None"')
            if session.is_stm:
                session.engine.command('sysbus SetHookBeforePeripheralWrite sysbus.rcc '
                    '"import sys; sys._spikes_gpio_edges.reject() if offset == 16 and value & 511 else None"')
            session.edge_transport = self
        except BaseException:
            session.close()
            raise

    def run_for(self, seconds):
        if type(seconds) not in (int, float) or not math.isfinite(seconds):
            raise ValueError('Firmware interval must be finite seconds')
        interval_ns = round(seconds * 1e9)
        if abs(interval_ns / 1e9 - seconds) > 1e-15:
            raise ValueError('Firmware interval must be integer nanoseconds')
        return self.run_for_ns(interval_ns)

    def provenance(self):
        return {'timing_mode': 'timestamped_software_gpio',
                'timestamp_source': 'Renode virtual instruction-start time; integer nanoseconds',
                'maximum_translation_block_instructions': 1,
                'capture_event_capacity': self.capacity, 'maximum_interval_ns': MAX_INTERVAL_NS,
                'input_semantics': 'held throughout each lookahead interval',
                'excluded': ['alternate function', 'PWM', 'DMA', 'GPIOTE', 'PPI', 'reset'],
                'cycle_accurate': False, 'performance': 'single-instruction blocks and per-write hooks are expensive'}

    def run_for_ns(self, interval_ns):
        """Run ahead with held inputs and return actual software-GPIO changes.

        Consumers must advance the plant to each timestamp BEFORE applying the
        returned configuration. Do not use the interval-end state at its start.
        The caller must not advance this session outside this transport.
        """
        _integer(interval_ns, 'interval_ns', MAX_INTERVAL_NS)
        if not interval_ns:
            raise ValueError('Capture interval must be positive')
        if self.session.time_ns != self.time_ns:
            raise RuntimeError('Firmware advanced outside GPIO edge transport')
        start = self.time_ns
        try:
            self.session.run_for(interval_ns / 1e9)
            text = self.session.engine.command('python "import sys; sys._spikes_gpio_edges.drain()"')
            result = self._decode(text, start, self.session.time_ns)
            self.time_ns = self.session.time_ns
            return result
        except BaseException:
            self.session.close()
            raise

    def _decode(self, text, start, end):
        if 'SPIKES_GPIO_FAILED' in text:
            raise RuntimeError('GPIO capture rejected overflow, write budget or unsupported peripheral/reset')
        matches = re.findall(r'^\s*SPIKES_GPIO_V1 ([0-9]+) ([A-I01]) ([0-9 ]+)\s*$', text, re.M)
        ends = re.findall(r'^\s*SPIKES_GPIO_END ([0-9]+) ([0-9]+)\s*$', text, re.M)
        if (len(ends) != 1 or int(ends[0][0]) != len(matches) or
                int(ends[0][1]) != end or len(matches) > self.capacity or
                len(re.findall(r'^\s*SPIKES_GPIO_V1\b', text, re.M)) != len(matches)):
            raise RuntimeError('Incomplete or overflowing GPIO capture batch')
        staged = dict(self.states)
        events = []
        previous = start
        for time_text, port, words in matches:
            timestamp = int(time_text)
            if not previous <= timestamp <= end or port not in self.ports:
                raise RuntimeError('GPIO capture contains invalid time or port')
            previous = timestamp
            registers = [int(value) for value in words.split()]
            expected = 5 if self.session.is_stm else 1 + len(self.ports[port])
            if len(registers) != expected:
                raise RuntimeError('GPIO capture register shape mismatch')
            for index, pin in enumerate(self.ports[port]):
                config = (decode_stm32(*registers, pin) if self.session.is_stm else
                          decode_nrf(registers[1 + index], registers[0], pin))
                if config != staged[port, pin]:
                    events.append({'time_ns': timestamp, 'port': port, 'pin': pin, 'config': config})
                    staged[port, pin] = config
        result = admit_events(events, start, end, capacity=self.capacity)
        self.states = staged
        return result


def attach(session, pins, *, capacity=MAX_EVENTS):
    return FirmwareEdgeTransport(session, pins, capacity=capacity)
