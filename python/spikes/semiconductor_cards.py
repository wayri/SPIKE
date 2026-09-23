"""Strict bindings for the existing static native NPN and NMOS kernels."""
import math

ALLOWED={'NPN':{'IS','BF','BR','NF','CBE','CBC','TF','TR'},'NMOS':{'LEVEL','VTO','KP','LAMBDA','GAMMA','PHI','CGS','CGD','CDS'}}
from .native_abi import _WbgFetElectrothermalModel
import ctypes
_WBG_FIELDS={name.upper():name for name,kind in _WbgFetElectrothermalModel._fields_ if kind is ctypes.c_double}
ALLOWED.update(SPK_GAN=set(_WBG_FIELDS),SPK_SIC=set(_WBG_FIELDS))


def parameters(kind,values):
    if kind in {'BSIMBULK','BSIMCMG'}:
        if not all(math.isfinite(v) for v in values.values()):raise ValueError('Finite BSIM parameters required')
        return dict(values)
    if set(values)-ALLOWED[kind]:raise ValueError('Unsupported compact-model parameters: '+', '.join(sorted(set(values)-ALLOWED[kind])))
    if not all(math.isfinite(v) for v in values.values()):raise ValueError('Finite compact-model parameters required')
    if kind in {'SPK_GAN','SPK_SIC'}:return {_WBG_FIELDS[k]:v for k,v in values.items()}
    charge_keys={'CBE':'c1','CBC':'c2','TF':'tf','TR':'tr'} if kind=='NPN' else {'CGS':'c1','CGD':'c2','CDS':'c3'}
    charge={f'charge_{target}':values[key] for key,target in charge_keys.items() if key in values}
    if any(v<0 for v in charge.values()):raise ValueError('Capacitances/transit times must be nonnegative')
    if kind=='NPN':
        saturation=values.get('IS',1e-15);bf=values.get('BF',99);br=values.get('BR',1);nf=values.get('NF',1)
        if min(saturation,bf,br,nf)<=0:raise ValueError('IS BF BR NF must be positive')
        return dict(saturation_current_a=saturation,forward_alpha=bf/(bf+1),reverse_alpha=br/(br+1),emission_coefficient=nf,temperature_k=300.15,**charge)
    if values.get('LEVEL',1)!=1:raise ValueError('Only static NMOS LEVEL=1 is bound; BSIM is unavailable')
    result=dict(threshold_voltage_v=values.get('VTO',1),transconductance_a_per_v2=values.get('KP',.001),
                channel_length_modulation_per_v=values.get('LAMBDA',0),body_effect_sqrt_v=values.get('GAMMA',0),surface_potential_v=values.get('PHI',.6))
    if result['transconductance_a_per_v2']<=0 or result['surface_potential_v']<=0 or min(result['channel_length_modulation_per_v'],result['body_effect_sqrt_v'])<0:
        raise ValueError('KP/PHI must be positive and LAMBDA/GAMMA nonnegative')
    return dict(result,**charge)
