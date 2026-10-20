# SPDX-License-Identifier: Apache-2.0
"""Owned C++ GPIO pad network. No Python electrical solver or implicit backend.

Profiles are generic/user-characterized, not manufacturer-qualified defaults.
All values are SI. Generated branches are observable through the native session.
"""
from dataclasses import dataclass, asdict
import ctypes as C
from .native_abi import NativeABIError, _text


@dataclass(frozen=True)
class PadProfile:
    high_strong_resistance_ohm: float = 50.
    high_weak_resistance_ohm: float = 500.
    low_strong_resistance_ohm: float = 50.
    low_weak_resistance_ohm: float = 500.
    pull_up_resistance_ohm: float = 50000.
    pull_down_resistance_ohm: float = 50000.
    off_resistance_ohm: float = 1e12
    package_resistance_ohm: float = 0.
    package_inductance_h: float = 0.
    capacitance_to_vss_f: float = 0.
    capacitance_to_vdd_f: float = 0.
    enable_clamp_to_vdd: bool = False
    enable_clamp_to_vss: bool = False
    clamp_saturation_current_a: float = 1e-14
    clamp_emission_coefficient: float = 1.
    clamp_temperature_k: float = 300.15


@dataclass(frozen=True)
class PadState:
    mode: str = 'input'
    output: str = 'released'
    drive_level: str = 'strong'
    pull: str = 'none'


_enums = (('input','push_pull','open_drain','open_source'),
          ('low','high','released'),('strong','weak'),('none','up','down'))


class _Config(C.Structure):
    _fields_ = [('struct_version',C.c_uint32),('struct_size',C.c_size_t)] + [
        (name, C.c_uint32 if name.startswith('enable_') else C.c_double)
        for name in PadProfile.__dataclass_fields__]


class _State(C.Structure):
    _fields_ = [(name,C.c_uint32) for name in PadState.__dataclass_fields__]


IO_PAD_SYMBOLS = (
    'spikes_circuit_add_io_pad', 'spikes_transient_session_set_io_pad',
    'spikes_io_pad_receive', 'spikes_transient_session_observe_io_pad',
    'spikes_transient_session_schedule_io_pad','spikes_transient_session_pending_io_pads',
)


def require_io_pad_api(library):
    """Verify the complete API before packaging or binding any pad operation."""
    lib=library._library
    missing=[name for name in IO_PAD_SYMBOLS if not hasattr(lib,name)]
    if missing:
        raise NativeABIError('This native library lacks owned electrical GPIO pads; incomplete API: '+', '.join(missing))
    lib.spikes_circuit_add_io_pad.argtypes=[C.c_void_p,*([C.c_char_p]*4),C.POINTER(_Config),C.POINTER(_State)]
    lib.spikes_circuit_add_io_pad.restype=C.c_int
    lib.spikes_transient_session_set_io_pad.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(_State)]
    lib.spikes_transient_session_set_io_pad.restype=C.c_int
    lib.spikes_io_pad_receive.argtypes=[*([C.c_double]*5),C.c_uint32,C.POINTER(C.c_uint32)]
    lib.spikes_io_pad_receive.restype=C.c_int
    lib.spikes_transient_session_observe_io_pad.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_double),C.c_size_t]
    lib.spikes_transient_session_observe_io_pad.restype=C.c_int
    lib.spikes_transient_session_schedule_io_pad.argtypes=[C.c_void_p,C.c_char_p,C.c_uint64,C.POINTER(_State)]
    lib.spikes_transient_session_schedule_io_pad.restype=C.c_int
    lib.spikes_transient_session_pending_io_pads.argtypes=[C.c_void_p,C.POINTER(C.c_size_t),C.POINTER(C.c_uint64)]
    lib.spikes_transient_session_pending_io_pads.restype=C.c_int
    return lib


def _api(owner):
    return require_io_pad_api(owner.library)


def _state(state):
    if not isinstance(state,PadState):raise TypeError('Expected PadState')
    try:return _State(*(allowed.index(value) for allowed,value in zip(_enums,asdict(state).values())))
    except ValueError as exc:raise ValueError('Unknown electrical GPIO state') from exc


def add_pad(circuit,prefix,pad,vdd,vss,profile=PadProfile(),initial=PadState()):
    """Compose before session creation; profiles are immutable during a run."""
    if not isinstance(profile,PadProfile):raise TypeError('Expected PadProfile')
    for name in ('enable_clamp_to_vdd','enable_clamp_to_vss'):
        if type(getattr(profile,name)) is not bool:raise ValueError(name+' must be boolean')
    config=_Config(1,C.sizeof(_Config),*asdict(profile).values())
    state=_state(initial)
    circuit.library._check(_api(circuit).spikes_circuit_add_io_pad(
        circuit._open_handle(),*(_text(n,'pad identifier') for n in (prefix,pad,vdd,vss)),
        C.byref(config),C.byref(state)),'adding owned GPIO pad')
    suffixes=['drive_high','drive_low','pull_up','pull_down']
    for field,suffix in [('package_inductance_h','package_l'),('package_resistance_ohm','package_r'),
                         ('capacitance_to_vss_f','cap_vss'),('capacitance_to_vdd_f','cap_vdd'),
                         ('enable_clamp_to_vdd','clamp_vdd'),('enable_clamp_to_vss','clamp_vss')]:
        if getattr(profile,field):suffixes.append(suffix)
    return tuple(prefix+'.io_pad.'+suffix for suffix in suffixes)


def set_pad(session,prefix,state):
    native=_state(state)
    session.library._check(_api(session).spikes_transient_session_set_io_pad(
        session._open_handle(),_text(prefix,'pad identifier'),C.byref(native)),'updating owned GPIO pad')


def observe_pad(session,prefix):
    """Accepted-point voltages and terminal currents, positive into the pad."""
    values=(C.c_double*7)()
    session.library._check(_api(session).spikes_transient_session_observe_io_pad(
        session._open_handle(),_text(prefix,'pad identifier'),values,7),'observing owned GPIO pad')
    return dict(zip(('pad_voltage_v','die_voltage_v','vdd_voltage_v','vss_voltage_v',
                     'pad_current_a','vdd_current_a','vss_current_a'),values))


def schedule_pad_edge(session,prefix,time_ns,state):
    """Queue an absolute integer-ns state change; no host wall-clock conversion."""
    if type(time_ns) is not int or not 0<=time_ns<=2**48:
        raise ValueError('GPIO edge time must be integer nanoseconds in 0..2^48')
    native=_state(state)
    session.library._check(_api(session).spikes_transient_session_schedule_io_pad(
        session._open_handle(),_text(prefix,'pad identifier'),time_ns,C.byref(native)),
        'scheduling owned GPIO edge')


def pending_pad_edges(session):
    count=C.c_size_t();time=C.c_uint64()
    session.library._check(_api(session).spikes_transient_session_pending_io_pads(
        session._open_handle(),C.byref(count),C.byref(time)),'querying GPIO edges')
    return count.value,(time.value if count.value else None)


def receive(session,pad_v,vdd_v,vss_v,*,vil_ratio=.3,vih_ratio=.7,previous='unknown'):
    """Generic Schmitt receiver; not metastability or vendor input-buffer physics."""
    states=('unknown','low','high')
    result=C.c_uint32()
    session.library._check(_api(session).spikes_io_pad_receive(
        pad_v,vdd_v,vss_v,vil_ratio,vih_ratio,states.index(previous),C.byref(result)),
        'sampling electrical GPIO input')
    return states[result.value]
