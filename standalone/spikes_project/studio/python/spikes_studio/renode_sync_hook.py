# SPDX-License-Identifier: Apache-2.0
"""Original bounded IronPython glue for Renode 1.17 instruction rendezvous.

Only public runtime APIs are used; no emulator implementation was consulted.
GPIO signals, not final register values, retain output transitions. Register
snapshots additionally retain configuration changes at instruction boundaries.
"""
import sys


class SpikesSyncCollector(object):
    def __init__(self, machine, ports, stm, capacity):
        self.machine = machine
        self.cpu = machine['sysbus.cpu']
        self.ports = ports
        self.stm = stm
        self.capacity = capacity
        self.records = []
        self.failed = False
        self.active = False
        self.step_ns = 10
        self.callbacks = []
        for port in ports:
            device = self.device(port)
            for pin in ports[port]:
                callback = self.callback(port, pin)
                self.callbacks.append(callback)
                device.Connections[pin].AddStateChangedHook(callback)

    def device(self, port):
        return self.machine['sysbus.' + ('gpioPort' if self.stm else 'gpio') + port]

    def now(self):
        return int(self.machine.ElapsedVirtualTime.TimeElapsed.TotalNanoseconds)

    def registers(self, port, pin):
        device = self.device(port)
        offsets = [0, 4, 12, 8, 20] if self.stm else [512 + 4 * pin, 4]
        return [int(device.ReadDoubleWord(offset)) for offset in offsets]

    def append(self, timestamp, port, pin, values):
        if len(self.records) >= self.capacity:
            self.failed = True
        elif not self.failed:
            self.records.append((timestamp, port, pin, values))

    def callback(self, port, pin):
        def changed(level):
            # Feedback injection is external input, never an output edge.
            if not self.active:
                return
            values = self.registers(port, pin)
            index = 4 if self.stm else 1
            values[index] = ((values[index] & ~(1 << pin)) |
                             ((1 << pin) if level else 0))
            self.append(self.now(), port, pin, values)
        return changed

    def reject(self):
        self.failed = True
        return 0

    def dma(self, offset, value):
        """Only DMA2 stream0 immediate SRAM-word -> captured GPIO BSRR.

        No peripheral-source reads, trigger-driven DMA, circular transfers,
        double buffers or other streams are admitted. Reject before enabling.
        """
        offset = int(offset)
        value = int(value)
        if offset not in (8, 12, 16, 20, 24, 28, 32, 36):
            return self.reject()
        if offset != 16 or not (value & 1):
            return value
        dma = self.machine['sysbus.dma2']
        count = int(dma.ReadDoubleWord(20))
        source = int(dma.ReadDoubleWord(24))
        destination = int(dma.ReadDoubleWord(28))
        targets = [0x40020018 + 0x400 * (ord(p) - ord('A')) for p in self.ports]
        if (value != 0x5281 or not 1 <= count <= self.capacity or
                source % 4 or not 0x20000000 <= source or
                source + 4 * count > 0x20020000 or destination not in targets):
            return self.reject()
        return value

    def step(self):
        self.records = []
        start = self.now()
        before_count = int(self.cpu.ExecutedInstructions)
        before = {}
        for port in self.ports:
            for pin in self.ports[port]:
                before[port, pin] = self.registers(port, pin)
        self.active = True
        try:
            self.cpu.Step(1)
        finally:
            self.active = False
        end = self.now()
        for port in self.ports:
            for pin in self.ports[port]:
                values = self.registers(port, pin)
                if values != before[port, pin]:
                    # These are configuration observations, not edge inference.
                    self.append(start, port, pin, values)
        if (self.failed or end - start != self.step_ns or
                int(self.cpu.ExecutedInstructions) - before_count != 1 or
                self.cpu.IsLockedUp):
            print('SPIKES_SYNC_FAILED failed=%r dt_ns=%d expected_ns=%d instructions=%d locked=%r' %
                  (self.failed,end-start,self.step_ns,
                   int(self.cpu.ExecutedInstructions)-before_count,self.cpu.IsLockedUp))
            return
        for timestamp, port, pin, values in self.records:
            print('SPIKES_SYNC_V1 %d %s %d %s' %
                  (timestamp, port, pin, ' '.join(str(x) for x in values)))
        print('SPIKES_SYNC_END %d %d %d' % (len(self.records), start, end))


sys._spikes_sync_collector_type = SpikesSyncCollector
