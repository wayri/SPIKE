# SPDX-License-Identifier: Apache-2.0
"""Experimental instruction-boundary electrical feedback, not cycle-accurate I/O.

The CPU never executes the next instruction until the owned C++ plant catches
up and receiver values have been delivered. Asynchronous input edges inside an
instruction are not admitted; this is distinct from the older held-interval mode.
"""
from collections import deque
from .firmware_electrical import ElectricalFirmwareController
from .firmware_sync_transport import FirmwareSyncTransport
from python.spikes.native_io_pad import receive, schedule_pad_edge


class SynchronousFirmwareController(ElectricalFirmwareController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.transport = FirmwareSyncTransport(self.session, [(p.port, p.pin) for p in self.pads])
        except BaseException:
            self.close()
            raise
        self._pins = {(p.port, p.pin): p for p in self.pads}
        self.edges = deque(maxlen=1000)
        self.edge_count = 0
        self.instruction_count = 0
        self.failed = False
        self.boundary_control = None

    def set_boundary_control(self, callback):
        """Cooperative worker pause/stop at aligned CPU/plant boundaries."""
        self.boundary_control = callback

    def source_control_metadata(self, time_s):
        # A source setter changes the next integration interval; it does not
        # recompute the already accepted algebraic solution at its left edge.
        return {'input_visibility':'next accepted instruction boundary',
                'earliest_input_observation_time_s':time_s+self.transport.step_ns/1e9}

    def bind(self, project):
        super().bind(project)
        ns = project.analysis.time_step_s * 1e9
        if project.analysis.use_initial_conditions:
            raise ValueError('Synchronous firmware startup requires an operating point; remove UIC')
        if abs(ns-round(ns)) > 1e-6 or round(ns) % self.transport.step_ns:
            raise ValueError('Instruction coupling reporting step must be a multiple of 10 ns')
        if not 1 <= round(ns)//self.transport.step_ns <= 1000:
            raise ValueError('Instruction coupling permits 1..1000 instructions per report (10 ns..10 us)')

    def configure_circuit(self, circuit, project):
        ids = super().configure_circuit(circuit, project)
        with circuit.solve_operating_point() as op:
            if op.status != 'converged':
                raise ValueError('Electrical startup operating point failed: '+op.message)
            self.initial_values = {}
            for p in self.pads:
                die = '@io_pad:'+p.prefix+':die' if (p.profile.package_resistance_ohm or p.profile.package_inductance_h) else p.node
                self.initial_values[p.prefix] = (op.node_voltage(die), op.node_voltage(p.vdd), op.node_voltage(p.vss))
        return ids

    def advance(self, plant):
        if self.failed:
            raise RuntimeError('Combined session failed; restart firmware and plant together')
        if abs(plant.time_s-self.transport.time_ns/1e9) > 1e-16:
            raise RuntimeError('Instruction/plant clock mismatch; combined rollback is unavailable')
        return {}

    def _inputs(self, plant):
        inputs = []
        for p in self.pads:
            config = self.transport.states[p.port, p.pin]
            if not config['input_enabled']:
                self.previous[p.prefix] = 'unknown'
                continue
            if self.transport.time_ns == 0:
                values = self.initial_values[p.prefix]
            else:
                die = '@io_pad:'+p.prefix+':die' if (p.profile.package_resistance_ohm or p.profile.package_inductance_h) else p.node
                values = (plant.node_voltage(die), plant.node_voltage(p.vdd), plant.node_voltage(p.vss))
            level = receive(plant, *values, vil_ratio=p.vil_ratio,
                            vih_ratio=p.vih_ratio, previous=self.previous[p.prefix])
            if level == 'unknown':
                raise RuntimeError('Unresolved instruction-boundary GPIO input: '+p.prefix)
            self.previous[p.prefix] = level
            inputs.append((p.port, p.pin, level == 'high'))
        self.transport.set_inputs(inputs)

    def step_plant(self, plant, step_s, record):
        count = round(step_s*1e9/self.transport.step_ns)
        if not 1 <= count <= 1000 or abs(count*self.transport.step_ns/1e9-step_s) > 1e-16:
            raise ValueError('Instruction coupling step must contain 1..1000 whole instructions')
        try:
            for _ in range(count):
                boundary = getattr(self, 'boundary_control', None)
                if boundary is not None and not boundary():
                    return
                self.advance(plant)
                self._inputs(plant)
                batch = self.transport.step()
                for event in batch['events']:
                    pin = self._pins[event['port'], event['pin']]
                    schedule_pad_edge(plant, pin.prefix, event['time_ns'], self.resolved_state(pin, event['config']))
                    self.edges.append({'time_ns':event['time_ns'], 'pad':pin.prefix, 'state':event['config']['state']})
                self.edge_count += len(batch['events'])
                # Target the absolute integer boundary. Repeated floating-point
                # additions of10ns otherwise drift past the clock guard.
                remaining = batch['end_ns']/1e9-plant.time_s
                if remaining <= 0:
                    raise RuntimeError('Non-increasing instruction endpoint')
                if not plant.step(remaining):
                    raise RuntimeError(plant.message)
                self.instruction_count += 1
                record()
        except BaseException:
            # Plant-only rollback cannot undo executed MCU instructions.
            self.failed = True
            raise

    def provenance(self):
        return {**super().provenance(), **self.transport.provenance(),
                'semantics':'feedback before every CPU instruction; C++ plant catches up before the next instruction',
                'instruction_count':self.instruction_count, 'edge_count':self.edge_count,
                'edge_events':list(self.edges), 'si_pi_qualified':False,
                'continuous_input_coupling':False,
                'input_limit':'instruction-boundary sampling; asynchronous within-instruction input capture unsupported',
                'source_controls':'edits drive the next electrical interval; firmware sees them at the next accepted boundary, not an unsolved right limit',
                'capture':'accepted instruction boundaries; finite RLC pad model, no transmission-line qualification'}
