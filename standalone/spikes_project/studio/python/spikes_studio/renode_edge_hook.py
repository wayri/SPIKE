# SPDX-License-Identifier: Apache-2.0
"""Original internal IronPython collector, loaded only into trusted Renode.

Public API references: Renode Using Python / System bus hooks and Time
framework. No emulator implementation source is used. This intentionally uses
Python 2-compatible syntax for Renode 1.17's separately installed interpreter.
"""
import sys


class SpikesGpioCollector(object):
    def __init__(self, machine, ports, stm, capacity):
        self.machine = machine
        self.ports = ports
        self.stm = stm
        self.capacity = capacity
        self.records = []
        self.pending = None
        self.previous = {}
        self.writes = 0
        self.failed = False
        for port in ports:
            self.previous[port] = self.snapshot(port)

    def snapshot(self, port):
        peripheral = self.machine['sysbus.' + ('gpioPort' if self.stm else 'gpio') + port]
        offsets = [0, 4, 12, 8, 20] if self.stm else [4] + [512 + 4 * pin for pin in self.ports[port]]
        return tuple(int(peripheral.ReadDoubleWord(offset)) for offset in offsets)

    def flush(self):
        if self.failed:
            return
        if self.pending is None:
            return
        port, timestamp = self.pending
        current = self.snapshot(port)
        if current != self.previous[port]:
            if len(self.records) >= self.capacity:
                self.failed = True
                return
            self.records.append((timestamp, port, current))
            self.previous[port] = current
        self.pending = None

    def before(self, port):
        self.flush()
        if self.failed:
            return
        self.writes += 1
        if self.writes > 100000:
            self.failed = True
            return
        self.machine['sysbus.cpu'].SyncTime()
        self.pending = (port, int(self.machine.ElapsedVirtualTime.TimeElapsed.TotalNanoseconds))

    def reject(self):
        self.failed = True

    def drain(self):
        self.flush()
        # Do not throw on the native CPU callback thread: fail the batch only
        # after RunFor has paused. No incomplete records are ever published.
        if self.failed:
            print('SPIKES_GPIO_FAILED overflow, write budget or unsupported peripheral/reset')
            return
        for timestamp, port, values in self.records:
            print('SPIKES_GPIO_V1 %d %s %s' % (timestamp, port, ' '.join(str(x) for x in values)))
        print('SPIKES_GPIO_END %d %d' % (len(self.records),
              int(self.machine.ElapsedVirtualTime.TimeElapsed.TotalNanoseconds)))
        self.records = []
        self.writes = 0


sys._spikes_gpio_collector_type = SpikesGpioCollector
