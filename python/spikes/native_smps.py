# SPDX-License-Identifier: Apache-2.0
"""Typed bulk-array transport to the C++ SMPS kernel; no Python numerical solve."""
import ctypes as ct
from functools import lru_cache
from pathlib import Path
from .smps_stability import validate,LIMITATIONS,TOPOLOGIES,CONTROLLERS
from .native_abi import load_native_library,NativeABIError

NUMBERS=('input_voltage_v','duty_cycle','inductance_h','capacitance_f','load_resistance_ohm',
         'switching_frequency_hz','turns_ratio','start_hz','stop_hz','controller_gain',
         'zero1_hz','zero2_hz','pole1_hz','pole2_hz','feedback_gain','pwm_gain')


class Config(ct.Structure):
    _fields_=[(name,ct.c_uint32) for name in ('api_version','struct_size','topology','controller_type','points')]+[(name,ct.c_double) for name in NUMBERS]


@lru_cache(maxsize=8)
def _library(path,mtime,size):
    native=load_native_library(path);lib=native._library
    if not hasattr(lib,'spikes_smps_analyze'):raise NativeABIError('Selected library lacks C++ SMPS API; rebuild or explicitly choose reference mode')
    lib.spikes_smps_analyze.argtypes=[ct.POINTER(Config),ct.POINTER(ct.c_void_p)];lib.spikes_smps_analyze.restype=ct.c_int
    lib.spikes_smps_result_size.argtypes=[ct.c_void_p,ct.c_uint32];lib.spikes_smps_result_size.restype=ct.c_size_t
    lib.spikes_smps_result_data.argtypes=[ct.c_void_p,ct.c_uint32];lib.spikes_smps_result_data.restype=ct.POINTER(ct.c_double)
    lib.spikes_smps_result_stability.argtypes=[ct.c_void_p];lib.spikes_smps_result_stability.restype=ct.c_char_p
    lib.spikes_smps_result_warning_count.argtypes=[ct.c_void_p];lib.spikes_smps_result_warning_count.restype=ct.c_size_t
    lib.spikes_smps_result_warning.argtypes=[ct.c_void_p,ct.c_size_t];lib.spikes_smps_result_warning.restype=ct.c_char_p
    lib.spikes_smps_result_destroy.argtypes=[ct.c_void_p];lib.spikes_smps_result_destroy.restype=None
    return native


def analyze(config,library):
    c=validate(config);path=Path(library).resolve(strict=True);stat=path.stat()
    native=_library(str(path),stat.st_mtime_ns,stat.st_size);lib=native._library
    value=Config(1,ct.sizeof(Config),TOPOLOGIES.index(c['topology']),CONTROLLERS.index(c['controller_type']),c['points'],*[c[name] for name in NUMBERS])
    result=ct.c_void_p();code=lib.spikes_smps_analyze(ct.byref(value),ct.byref(result))
    if code==1:raise ValueError(native._error())
    native._check(code,'native SMPS analysis')
    if not result.value:raise NativeABIError('Native SMPS analysis returned a null result')
    try:
        def data(field):
            count=lib.spikes_smps_result_size(result,field)
            if count>70000:raise NativeABIError('Native SMPS result exceeds array bound')
            pointer=lib.spikes_smps_result_data(result,field)
            if count and not pointer:raise NativeABIError('Missing native SMPS result array')
            return list(pointer[:count]) if count else []
        def pairs(field):
            values=data(field)
            if len(values)%2:raise NativeABIError('Invalid native complex array length')
            return [values[i:i+2] for i in range(0,len(values),2)]
        def crossings(field,gain):
            values=data(field);output=[]
            if len(values)%7:raise NativeABIError('Invalid native crossing array')
            for i in range(0,len(values),7):
                f,inside,averaged,phase,pm,db,gm=values[i:i+7]
                item=dict(frequency_hz=f,in_sweep=bool(inside),below_averaging_limit=bool(averaged))
                item.update(dict(phase_deg=phase,phase_margin_deg=pm) if gain else dict(gain_db=db,gain_margin_db=gm));output.append(item)
            return output
        s=data(12)
        if len(s)!=18:raise NativeABIError('Invalid native summary length')
        report=dict(contract='spikes/smps-stability/v1',status='completed',model_status='approximate',
          backend='SPIKES C++ ideal CCM averaged kernel',config=c,frequency_hz=data(0),plant=pairs(1),loop=pairs(2),
          plant_gain_db=data(3),plant_phase_deg=data(4),loop_gain_db=data(5),loop_phase_deg=data(6),
          plant_poles_rad_s=pairs(7),plant_zeros_rad_s=pairs(8),closed_loop_poles_rad_s=pairs(9),
          stability=lib.spikes_smps_result_stability(result).decode('ascii'),
          operating_point=dict(zip(('output_voltage_v','output_current_a','output_power_w','output_polarity','inductor_current_a','reference_voltage_v'),s[:6])),
          ccm=dict(admissible=True,inductor_ripple_pp_a=s[6],valley_current_a=s[7],peak_current_a=s[8],output_ripple_pp_v_estimate=s[9],method='Ideal constant-output triangular ripple; not a switched-periodic solution'),
          plant_dc_gain_v_per_duty=s[10],state_space=dict(a_per_s=[s[12:14],s[14:16]],b_duty_per_s=s[16:18],output=[0.,1.]),
          rational_model=dict(variable='x=s/omega_scale_rad_s',omega_scale_rad_s=s[11],plant_numerator=data(13),plant_denominator=data(14),loop_numerator=data(15),loop_denominator=data(16),closed_loop_denominator=data(17)),
          margins=dict(gain_crossings=crossings(10,True),phase_crossings=crossings(11,False),method='C++ rational crossing polynomial roots',scope='All finite positive-frequency model crossings, including outside display sweep',missing_crossing='Empty list does not certify infinite margin'),
          stability_scope='Internal poles of the uncancelled rational negative-feedback averaged model only',
          warnings=[lib.spikes_smps_result_warning(result,i).decode('ascii') for i in range(lib.spikes_smps_result_warning_count(result))],
          limitations=list(LIMITATIONS),native_library=str(path))
        return report
    finally:lib.spikes_smps_result_destroy(result)
