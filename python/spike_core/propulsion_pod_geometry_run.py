# SPDX-License-Identifier: Apache-2.0
"""Bounded inline-port application boundary for the geometry propulsion loop.

Representation/source checks do not certify the imported numerical evidence.
Only the fixed built-in demonstration controller may be compiled by this route.
"""
import copy
import hashlib
import json
from .propulsion_pod import _keys,_number,_ratio
from .propulsion_pod_energy_table import PeriodicLinearMagneticPort
from .propulsion_pod_load_table import CfdLoadTable
from .propulsion_pod_geometry_loop import run_geometry_loop
from .propulsion_pod_thermal import validate_thermal_spec

REQUEST_KEYS={'initial_currents_a','initial_angle_rad','initial_speed_rad_s','thermal','drive','shaft','transient'}


def prepare_geometry_run(params):
    _keys(params,{'request','magnetic_table','cfd_table','expected_field_sha256','expected_fluid_sha256'},'geometry run')
    encoded=json.dumps(params,allow_nan=False,sort_keys=True).encode()
    if len(encoded)>8*1024*1024:raise ValueError('Inline geometry inputs exceed8MiB')
    r=copy.deepcopy(params['request']);_keys(r,REQUEST_KEYS,'geometry request')
    d,s,t=r['drive'],r['shaft'],r['transient']
    _keys(d,{'dc_bus_v','current_limit_a','speed_kp','speed_ki','current_gain','end_turn_inductance_h'},'drive')
    _keys(s,{'inertia_kg_m2','damping_n_m_s'},'shaft')
    _keys(t,{'duration_s','time_step_s','controller_period_s','target_speed_rad_s','maximum_speed_rad_s','wall_budget_s'},'transient')
    for key,lo,hi in (('dc_bus_v',.001,100.),('current_limit_a',.001,100.),('speed_kp',0.,10.),('speed_ki',0.,100.),('current_gain',0.,100.)):
        d[key]=_number(d[key],key,lo,hi)
    if not isinstance(d['end_turn_inductance_h'],list) or len(d['end_turn_inductance_h'])!=3:
        raise ValueError('Three explicit end-turn inductances required')
    d['end_turn_inductance_h']=[_number(v,'end-turn inductance',0.,1.) for v in d['end_turn_inductance_h']]
    for key,lo,hi in (('inertia_kg_m2',1e-9,100.),('damping_n_m_s',0.,100.)):
        s[key]=_number(s[key],key,lo,hi)
    for key,lo,hi in (('duration_s',1e-5,10.),('time_step_s',1e-6,.01),('controller_period_s',1e-6,.1),('target_speed_rad_s',0.,500.),('maximum_speed_rad_s',.01,500.),('wall_budget_s',1.,600.)):
        t[key]=_number(t[key],key,lo,hi)
    count=_ratio(t['duration_s'],t['time_step_s'],'duration_s')
    stride=_ratio(t['controller_period_s'],t['time_step_s'],'controller_period_s')
    if count>20000 or stride<1 or t['maximum_speed_rad_s']*t['time_step_s']>.1:
        raise ValueError('Geometry integration step/angle budget exceeded')
    r['initial_angle_rad']=_number(r['initial_angle_rad'],'initial angle',-1e6,1e6)
    r['initial_speed_rad_s']=_number(r['initial_speed_rad_s'],'initial speed',0.,500.)
    if r['initial_speed_rad_s']>=t['maximum_speed_rad_s'] or t['target_speed_rad_s']>=t['maximum_speed_rad_s']:
        raise ValueError('Initial/target speed must be below the maximum')
    r['thermal']=validate_thermal_spec(r['thermal'])
    port=PeriodicLinearMagneticPort(params['magnetic_table'],d['end_turn_inductance_h'])
    fluid=CfdLoadTable(params['cfd_table'])
    if port.source_sha256!=params['expected_field_sha256'] or fluid.source_sha256!=params['expected_fluid_sha256']:
        raise ValueError('Retained constitutive source hash mismatch')
    if not isinstance(r['initial_currents_a'],list) or len(r['initial_currents_a'])!=3:
        raise ValueError('Three initial phase currents required')
    r['initial_currents_a']=[_number(v,'initial current',-port.max_current_a,port.max_current_a) for v in r['initial_currents_a']]
    port.flux_coordinates(r['initial_currents_a'],r['initial_angle_rad'])
    if d['current_limit_a']>port.max_current_a:raise ValueError('Controller demand exceeds magnetic-table current envelope')
    if not fluid.minimum_speed_rad_s<=min(r['initial_speed_rad_s'],t['target_speed_rad_s']) or t['maximum_speed_rad_s']>fluid.maximum_speed_rad_s:
        raise ValueError('Requested speed envelope exceeds retained CFD anchors')
    diagnostics={'accepted_steps_if_successful':count,'controller_stride':stride,
        'field_table_sha256':port.source_sha256,'fluid_port_sha256':fluid.source_sha256,
        'inline_parameter_sha256':hashlib.sha256(encoded).hexdigest(),
        'physical_load_qualified':False,'representation_only':True}
    return r,port,fluid,diagnostics


def execute_geometry_run(params):
    r,port,fluid,diagnostics=prepare_geometry_run(params)
    out=run_geometry_loop(port,fluid,initial_currents_a=r['initial_currents_a'],
        initial_angle_rad=r['initial_angle_rad'],initial_speed_rad_s=r['initial_speed_rad_s'],
        thermal_spec=r['thermal'],drive=r['drive'],shaft=r['shaft'],transient=r['transient'])
    out['inline_input_evidence']=diagnostics
    out['source_qualifications']={'magnetic':copy.deepcopy(params['magnetic_table'].get('qualification',{})),
        'fluid':copy.deepcopy(params['cfd_table']['evidence'])}
    return out
