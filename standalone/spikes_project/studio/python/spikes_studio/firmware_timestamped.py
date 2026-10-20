# SPDX-License-Identifier: Apache-2.0
"""Captured software GPIO edges -> native piecewise pad states.

Explicit bounded lookahead: analog inputs are held at the start of each CPU
interval. Not continuously synchronized input events, hardware PWM or SI/PI
qualification. Output edges are captured, never inferred from end snapshots.
"""
from collections import deque
from .firmware_electrical import ElectricalFirmwareController
from .firmware_edge_transport import FirmwareEdgeTransport,MAX_INTERVAL_NS
from python.spikes.native_io_pad import receive,schedule_pad_edge


class TimestampedFirmwareController(ElectricalFirmwareController):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.quantum_ns=round(self.config['step_s']*1e9)
        try:
            if self.quantum_ns>MAX_INTERVAL_NS:raise ValueError('Timestamped GPIO interval must be at most 1 ms')
            self.transport=FirmwareEdgeTransport(self.session,[(p.port,p.pin) for p in self.pads])
        except BaseException:
            self.close();raise
        self.interval_end_ns=0;self.edge_count=0;self.edges=deque(maxlen=1000)
        self._capture_times=deque()
        self._pins={(p.port,p.pin):p for p in self.pads}

    def bind(self,project):
        super().bind(project)
        if project.analysis.use_initial_conditions:
            raise ValueError('Timestamped firmware startup currently requires an operating point; remove UIC')
        dt_ns=project.analysis.time_step_s*1e9
        if dt_ns<1 or abs(dt_ns-round(dt_ns))>1e-6:
            raise ValueError('Timestamped firmware reporting step must be integer nanoseconds (>=1 ns)')

    def configure_circuit(self,circuit,project):
        ids=super().configure_circuit(circuit,project)
        with circuit.solve_operating_point() as op:
            if op.status!='converged':raise ValueError('Electrical startup operating point failed: '+op.message)
            self.initial_values={}
            for p in self.pads:
                die=('@io_pad:'+p.prefix+':die') if (p.profile.package_resistance_ohm or p.profile.package_inductance_h) else p.node
                self.initial_values[p.prefix]=(op.node_voltage(die),op.node_voltage(p.vdd),op.node_voltage(p.vss))
        return ids

    def advance(self,plant):
        now_ns=round(plant.time_s*1e9)
        if now_ns<self.interval_end_ns:return {}
        if now_ns!=self.interval_end_ns or self.session.time_ns!=now_ns:
            raise RuntimeError('Timestamped GPIO clock mismatch; combined firmware rollback is unavailable')
        while self._capture_times and self._capture_times[0]<=now_ns:
            self._capture_times.popleft()
        for p in self.pads:
            config=self.transport.states[p.port,p.pin]
            if not config['input_enabled']:
                self.previous[p.prefix]='unknown';continue
            if now_ns==0:values=self.initial_values[p.prefix]
            else:
                die=('@io_pad:'+p.prefix+':die') if (p.profile.package_resistance_ohm or p.profile.package_inductance_h) else p.node
                values=(plant.node_voltage(die),plant.node_voltage(p.vdd),plant.node_voltage(p.vss))
            level=receive(plant,*values,vil_ratio=p.vil_ratio,vih_ratio=p.vih_ratio,previous=self.previous[p.prefix])
            if level=='unknown':raise RuntimeError('Unresolved timestamped GPIO input: '+p.prefix)
            self.previous[p.prefix]=level;self.session.set_gpio(p.port,p.pin,level=='high')
        batch=self.transport.run_for_ns(self.quantum_ns)
        for event in batch:
            p=self._pins[event['port'],event['pin']]
            schedule_pad_edge(plant,p.prefix,event['time_ns'],self.resolved_state(p,event['config']))
            if not event['config']['input_enabled']:self.previous[p.prefix]='unknown'
            self.edges.append({'time_ns':event['time_ns'],'pad':p.prefix,'state':event['config']['state']})
            if not self._capture_times or self._capture_times[-1]!=event['time_ns']:
                self._capture_times.append(event['time_ns'])
        self.edge_count+=len(batch);self.interval_end_ns+=self.quantum_ns
        self.session.uart_read()
        return {}

    def step_plant(self,plant,step_s,record):
        """Retain accepted edge-time points as well as the reporting-grid end."""
        end=plant.time_s+step_s
        while self._capture_times and self._capture_times[0]/1e9<=end:
            edge=self._capture_times.popleft()/1e9
            remaining=edge-plant.time_s
            if remaining>=1e-18:
                if not plant.step(remaining):raise RuntimeError(plant.message)
                record()
        remaining=end-plant.time_s
        if remaining>=1e-18:
            if not plant.step(remaining):raise RuntimeError(plant.message)
            record()

    def provenance(self):
        return {**super().provenance(),'semantics':'actual software GPIO timestamps; bounded lookahead with inputs held at interval start',
            'edge_count':self.edge_count,'edge_events':list(self.edges),'timestamp_resolution_ns':1,
            'instruction_block_size':1,'peripheral_edges':False,'continuous_input_coupling':False,
            'capture':'accepted software-edge points plus reporting grid; edge currents are left-limit samples',
            'si_pi_qualified':False}
