# SPDX-License-Identifier: Apache-2.0
"""Causal owned-C++ peripheral events coupled to owned-C++ finite GPIO pads."""
from collections import deque
from dataclasses import replace
from .firmware_electrical import ElectricalFirmwareController
from .firmware_synchronous import SynchronousFirmwareController
from .firmware_peripheral_transport import FirmwarePeripheralTransport,ROUTES
from python.spikes.native_peripheral import NativePeripheral
from python.spikes.native_io_pad import PadState,set_pad,receive,schedule_pad_edge


class PeripheralFirmwareController(SynchronousFirmwareController):
    def __init__(self,*args,**kwargs):
        self.native=None;self.transport=None;self._plant=None
        ElectricalFirmwareController.__init__(self,*args,**kwargs)
        self._pins={(p.port,p.pin):p for p in self.pads}
        self.edges=deque(maxlen=1000);self.peripheral_events=deque(maxlen=2000)
        self.edge_count=self.instruction_count=self.sample_count=0
        self.failed=False;self.boundary_control=None;self.levels={}
        try:
            self.transport=FirmwarePeripheralTransport(self.session,list(self._pins),self._mmio,self._inputs_native)
        except BaseException:self.close();raise

    def bind(self,project):
        ElectricalFirmwareController.bind(self,project)
        ns=project.analysis.time_step_s*1e9
        if project.analysis.use_initial_conditions or abs(ns-round(ns))>1e-6 or round(ns)%1000:
            raise ValueError('Owned peripheral mode requires non-UIC reporting on whole1us instruction boundaries')
        if not 1<=round(ns)//1000<=1000:raise ValueError('Reporting interval must contain1..1000 functional instructions')
        for setting in self.pin_settings.values():
            if setting.get('output_source','firmware')!='firmware':
                raise ValueError('Owned peripheral coupling requires firmware-controlled output states')

    def initial_pad_configuration(self,pin):
        # The frozen reset snapshot was obtained before proxy installation.
        # Querying MMIO here would require the plant we are still constructing.
        return self.transport.states[pin.port,pin.pin]

    def configure_circuit(self,circuit,project):
        ids=super().configure_circuit(circuit,project)
        self.native=NativePeripheral(circuit.library)
        return ids

    def _to(self,stamp):
        delta=stamp/1e9-self._plant.time_s
        if delta < -1e-16:raise RuntimeError('Peripheral event would rewind the accepted plant')
        if delta>=1e-18:
            if not self._plant.step(delta):raise RuntimeError(self._plant.message)
            self._record()

    def _pin(self,signal):
        route=self.transport.routes.get(signal)
        if route is None or route not in self._pins:
            raise RuntimeError('Connect/configure admitted alternate-function pad for signal '+str(signal))
        return self._pins[route]

    def _receiver(self,pin):
        if self._plant.time_s==0:values=self.initial_values[pin.prefix]
        else:
            die='@io_pad:'+pin.prefix+':die' if (pin.profile.package_resistance_ohm or pin.profile.package_inductance_h) else pin.node
            values=tuple(self._plant.node_voltage(n) for n in (die,pin.vdd,pin.vss))
        level=receive(self._plant,*values,vil_ratio=pin.vil_ratio,vih_ratio=pin.vih_ratio,
                      previous=self.previous[pin.prefix])
        if level=='unknown':raise RuntimeError('Unknown/unpowered peripheral receiver: '+pin.prefix)
        self.previous[pin.prefix]=level
        return level=='high'

    def _pump(self,deadline):
        for _ in range(10000):
            event=self.native.next(deadline)
            if event is None:self._to(deadline);return
            self._to(event['time_ns'])
            # Receiver barrier samples the accepted LEFT limit. For mode0 SPI
            # this is setup data immediately before the internal sampling edge.
            # Same-time output changes have no invented algebraic right solve.
            high=0
            for signal in ROUTES:
                if event['sample_mask']&signal:
                    if self._receiver(self._pin(signal)):high|=signal
                    self.sample_count+=1
            for signal in ROUTES:
                if event['drive_mask']&signal:
                    pin=self._pin(signal)
                    baseline=self.resolved_state(pin,self.transport.states[pin.port,pin.pin])
                    output='released' if event['release_mask']&signal else 'high' if event['high_mask']&signal else 'low'
                    state=PadState('open_drain' if signal in (16,32) else 'push_pull',output,
                                   baseline.drive_level,baseline.pull)
                    set_pad(self._plant,pin.prefix,state);self.levels[signal]=state
            self.native.resolve(high)
            self.peripheral_events.append({**event,'sampled_high_mask':high})
        raise RuntimeError('Owned peripheral event budget exceeded within one instruction')

    def _mmio(self,stamp,device,write,offset,value,width):
        # Invoked on the pipe service thread while the CPU monitor call blocks.
        # No other thread may mutate the plant until this reply completes.
        if self._plant is None or self.native is None:raise RuntimeError('Electrical plant not attached to MMIO')
        if stamp!=self.transport.time_ns:raise RuntimeError('MMIO timestamp not at admitted instruction start')
        self._pump(stamp)
        if write:self.native.write(device,offset,value,width);result=0
        else:result=self.native.read(device,offset,width)
        self._pump(stamp)
        if device>=3:return (result,*(self.native.read(device,n) for n in (0,4,12,8,20,32,36)))
        return result

    def _inputs_native(self,inputs):
        ports={}
        for port,pin,level in inputs:
            mask,high=ports.get(port,(0,0))
            ports[port]=(mask|(1<<pin),high|((1<<pin) if level else 0))
        for port,(mask,high) in ports.items():self.native.gpio_inputs(ord(port)-ord('A'),mask,high)

    def source_control_metadata(self,time_s):
        return {'input_visibility':'next accepted peripheral sample / next CPU instruction',
                'earliest_cpu_observation_time_s':time_s+self.transport.step_ns/1e9}

    def step_plant(self,plant,step_s,record):
        count=round(step_s*1e9/self.transport.step_ns)
        if not 1<=count<=1000 or abs(count*self.transport.step_ns/1e9-step_s)>1e-16:
            raise ValueError('Owned peripheral report requires whole functional instructions')
        self._plant=plant;self._record=record
        try:
            for _ in range(count):
                if self.boundary_control is not None and not self.boundary_control():return
                self.advance(plant);self._inputs(plant)
                batch=self.transport.step()
                if self.transport.pipe.error:raise RuntimeError('Owned MMIO: '+str(self.transport.pipe.error))
                for event in batch['events']:
                    pin=self._pins[event['port'],event['pin']]
                    state=self.resolved_state(pin,event['config'])
                    signal=event['config'].get('owned_peripheral_signal')
                    if signal in self.levels:
                        state=replace(self.levels[signal],drive_level=state.drive_level,pull=state.pull)
                    schedule_pad_edge(plant,pin.prefix,event['time_ns'],state)
                    self.edge_count+=1
                self._pump(batch['end_ns'])
                self.instruction_count+=1
        except BaseException as exc:
            self.failed=True
            if self.transport.pipe.error and not isinstance(self.transport.pipe.error,OSError):raise RuntimeError('Owned peripheral MMIO: '+str(self.transport.pipe.error)) from exc
            raise

    def close(self):
        if getattr(self,'session',None) is not None:self.session.close()
        if self.transport is not None:self.transport.close()
        if self.native is not None:self.native.close();self.native=None

    def provenance(self):
        return {**super().provenance(),'semantics':'owned MMIO, timestamped peripheral edges and electrical receiver barriers inside functional CPU instructions',
            'peripheral_events':list(self.peripheral_events),'peripheral_samples':self.sample_count,
            'continuous_input_coupling':False,
            'input_limit':'1ns I2C SCL observation grid; exact configured SPI sampling instants; CPU MMIO at functional instruction start',
            'source_controls':'next accepted timed peripheral sample, CPU feedback at next instruction',
            'capture':'accepted timed electrical events and functional instruction endpoints',
            'si_pi_qualified':False}
