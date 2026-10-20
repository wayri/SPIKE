# SPDX-License-Identifier: Apache-2.0
"""Explicit experimental sampled firmware + owned native electrical GPIO pads.

Not the legacy ideal-source DI/DO bridge. Each physical GPIO has a bidirectional
electrical node and real VDD/VSS circuit rails; no output voltage source is added.
Python handles register transport/scheduling only; C++ solves all pad physics.
"""
from dataclasses import dataclass,asdict
import hashlib
import json
import math
import sys
from types import SimpleNamespace
from python.spikes.native_io_pad import PadProfile,PadState,add_pad,set_pad,receive
from .firmware_session import FirmwareSession


@dataclass(frozen=True)
class PadConnection:
    prefix: str
    port: str
    pin: int
    node: str
    vdd: str
    vss: str = '0'
    profile: PadProfile = PadProfile()
    vil_ratio: float = .3
    vih_ratio: float = .7


class ElectricalFirmwareController:
    close_after_run=True
    outputs=()  # No ideal independent source is controlled by this adapter.
    event_origin='firmware_electrical_pad'

    def __init__(self,runtime,image,target_id,pads,*,step_s=1e-4,
                 trusted=False,expected_sha256=None,pin_settings=None):
        self.pads=tuple(pads)
        if not self.pads or len(self.pads)>64 or any(not isinstance(p,PadConnection) for p in self.pads):
            raise ValueError('Supply 1..64 explicit electrical PadConnections')
        if len({p.prefix for p in self.pads})!=len(self.pads) or len({(p.port,p.pin) for p in self.pads})!=len(self.pads):
            raise ValueError('Duplicate GPIO or electrical prefix')
        if not math.isfinite(step_s) or not 1e-9<=step_s<=1 or abs(round(step_s*1e9)/1e9-step_s)>1e-15:
            raise ValueError('Firmware interval must be integer nanoseconds in 1 ns..1 s')
        for p in self.pads:
            if not 0<=p.vil_ratio<p.vih_ratio<=1:raise ValueError('Require 0 <= VIL ratio < VIH ratio <= 1')
            if not all(isinstance(n,str) and n.strip() for n in (p.prefix,p.node,p.vdd,p.vss)):
                raise ValueError('Explicit pad, supply and return net names required')
        self.config={'step_s':step_s}
        self.pin_settings=json.loads(json.dumps(pin_settings or {},allow_nan=False))
        if set(self.pin_settings)-{p.prefix for p in self.pads}:raise ValueError('Pin settings reference an unbound pad')
        self.previous={p.prefix:'unknown' for p in self.pads}
        self.session=FirmwareSession(runtime,image,target_id,trusted=trusted,expected_sha256=expected_sha256)
        try:
            for p in self.pads:self.session._gpio_device(p.port,p.pin)
        except BaseException:
            self.session.close();raise
        evidence={'firmware':self.session.provenance(),'pads':[asdict(p) for p in self.pads],
                  'pin_settings':self.pin_settings,'step_s':step_s}
        self.manifest=SimpleNamespace(manifest_sha256=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest())
        self._configured=False

    def reset(self):
        if self.session.time_ns or self._configured:raise ValueError('Create a fresh electrical firmware session for each run')

    def bind(self,project):
        if project.analysis.mode!='transient':raise ValueError('Electrical firmware coupling requires transient analysis')
        dt=project.analysis.time_step_s;ratio=self.config['step_s']/dt
        if ratio<1 or abs(ratio-round(ratio))>1e-9:raise ValueError('Firmware interval must be an integer multiple of plant timestep')
        self.stride=round(ratio)
        from python.spikes.native_runner import _nodes
        nodes=set(_nodes(project))|{'0'}
        for p in self.pads:
            if not {p.node,p.vdd,p.vss}<=nodes:raise ValueError('Electrical GPIO terminals must be existing circuit nets: '+p.prefix)

    @staticmethod
    def _state(config):
        return PadState(**config['state'])

    def resolved_state(self,pin,config):
        state=self._state(config)
        if pin.prefix in self.pin_settings:
            from .firmware_pad_settings import resolve_pad_state
            return resolve_pad_state(self.pin_settings[pin.prefix],state)
        return state

    def initial_pad_configuration(self,pin):
        return self.session.pad_configuration(pin.port,pin.pin)

    def configure_circuit(self,circuit,project):
        if self._configured:raise ValueError('Electrical pads already configured')
        result=[]
        for p in self.pads:
            config=self.initial_pad_configuration(p)
            result.extend(add_pad(circuit,p.prefix,p.node,p.vdd,p.vss,p.profile,self.resolved_state(p,config)))
        self._configured=True
        return result

    def advance(self,plant):
        if not plant.step_index or plant.step_index%self.stride:return {}
        quantum=round(self.config['step_s']*1e9)
        expected=self.session.time_ns+quantum
        expected_index=(self.session.time_ns//quantum+1)*self.stride
        # Integer tick identity rejects repeats/restore; the time cross-check
        # allows ordinary accumulated double-addition roundoff on long runs.
        tolerance=max(1e-15,self.config['step_s']*1e-8,
                      8*sys.float_info.epsilon*plant.step_index*abs(plant.time_s))
        if self.session.time_ns%quantum or plant.step_index!=expected_index or abs(plant.time_s-expected*1e-9)>tolerance:
            raise RuntimeError('Firmware/plant clock mismatch; repeated ticks or plant-only restore require a fresh firmware session')
        # Read die voltage, not external pin voltage across package R/L.
        for p in self.pads:
            config=self.session.pad_configuration(p.port,p.pin)
            if not config['input_enabled']:
                self.previous[p.prefix]='unknown'
                continue
            die=('@io_pad:'+p.prefix+':die') if (p.profile.package_resistance_ohm or p.profile.package_inductance_h) else p.node
            level=receive(plant,plant.node_voltage(die),plant.node_voltage(p.vdd),plant.node_voltage(p.vss),
                vil_ratio=p.vil_ratio,vih_ratio=p.vih_ratio,previous=self.previous[p.prefix])
            if level=='unknown':
                raise RuntimeError('Unresolved GPIO input or unpowered rail: '+p.prefix+'; binary instruction backend cannot consume X')
            self.previous[p.prefix]=level
            self.session.set_gpio(p.port,p.pin,level=='high')
        self.session.run_for(self.config['step_s'])
        self.session.uart_read()
        configurations=[self.session.pad_configuration(p.port,p.pin) for p in self.pads]
        for p,config in zip(self.pads,configurations):
            if not config['input_enabled']:self.previous[p.prefix]='unknown'
            set_pad(plant,p.prefix,self.resolved_state(p,config))
        return {}

    def provenance(self):
        return {**self.session.provenance(),'electrical_pin_physics':True,
            'electrical_backend':'SPIKES owned C++ finite R/C/L/diode MNA composition',
            'pad_qualification':'generic experimental; user-provided profile; no manufacturer fit',
            'manifest_sha256':self.manifest.manifest_sha256,'pads':[asdict(p) for p in self.pads],
            'pin_settings':self.pin_settings,
            'step_s':self.config['step_s'],
            'semantics':'sampled endpoint feedback; register states held until next firmware boundary; intra-tick GPIO edges not captured',
            'si_pi_qualified':False,'unknown_inputs':'stop; no invented binary level'}

    def close(self):self.session.close()
