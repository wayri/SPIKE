# SPDX-License-Identifier: Apache-2.0
"""Bounded public sampled-C/three-phase FEM/electrothermal/BEM orchestration."""
from __future__ import annotations
from ....solver_source_paths import solver_source_path
import copy
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from .propulsion_pod import DEFAULT_REQUEST as OLD_DEFAULT, _keys, _number, _ratio
from .propulsion_pod_three_phase_field import ThreePhaseFieldMotor, validate_field_spec
from .propulsion_pod_thermal import ThermalNetwork, validate_thermal_spec, NODE_NAMES
from .propulsion_pod_three_phase import coupled_electrothermal_step
from .propulsion_pod_three_phase_controller import create_three_phase_controller, SOURCE_SHA256
from .propulsion_pod_propeller import evaluate_propeller

REQUEST='spike/propulsion-pod-three-phase-request/v1'
RESULT='spike/propulsion-pod-three-phase-result/v1'
DEFAULT_REQUEST={'contract':REQUEST,'field_motor':{},'thermal':{},
    'fluid':{'kind':'hover_bem','request':copy.deepcopy(OLD_DEFAULT['propeller'])},
    'drive':{'dc_bus_v':12.,'current_limit_a':4.,'speed_kp':.06,'speed_ki':.5,
             'current_gain':.25,'end_turn_inductance_h':[.0002]*3},
    'shaft':copy.deepcopy(OLD_DEFAULT['shaft']),
    'transient':{**OLD_DEFAULT['transient'],'duration_s':.05}}

def validate_three_phase_request(request):
    _keys(request,DEFAULT_REQUEST,'request')
    if request['contract']!=REQUEST:raise ValueError('Unsupported three-phase request contract')
    r=copy.deepcopy(request)
    r['field_motor']=validate_field_spec(r['field_motor']);r['thermal']=validate_thermal_spec(r['thermal'])
    for name in ('drive','shaft','transient'): _keys(r[name],DEFAULT_REQUEST[name],name)
    _keys(r['fluid'],('kind','request'),'fluid')
    if r['fluid']['kind']!='hover_bem':raise ValueError('Only explicit hover_bem is currently admitted; not CFD')
    d,s,t=r['drive'],r['shaft'],r['transient']
    for key,lo,hi in (('dc_bus_v',.001,100.),('current_limit_a',.001,100.),('speed_kp',0.,10.),('speed_ki',0.,100.),('current_gain',0.,100.)):
        d[key]=_number(d[key],key,lo,hi)
    if not isinstance(d['end_turn_inductance_h'],list) or len(d['end_turn_inductance_h'])!=3:raise ValueError('Three end-turn inductances required')
    d['end_turn_inductance_h']=[_number(v,'end turn inductance',0.,1.) for v in d['end_turn_inductance_h']]
    for key,lo,hi in (('inertia_kg_m2',1e-9,100.),('damping_n_m_s',0.,100.),('initial_speed_rad_s',0.,500.),('initial_angle_rad',-1e6,1e6)):
        s[key]=_number(s[key],key,lo,hi)
    for key,lo,hi in (('duration_s',1e-5,10.),('time_step_s',1e-6,.01),('controller_period_s',1e-6,.1),('field_output_interval_s',1e-6,10.),('target_speed_rad_s',0.,500.),('maximum_speed_rad_s',.01,500.),('wall_budget_s',1.,600.)):
        t[key]=_number(t[key],key,lo,hi)
    n=_ratio(t['duration_s'],t['time_step_s'],'duration_s');stride=_ratio(t['controller_period_s'],t['time_step_s'],'controller_period_s');frames=_ratio(t['field_output_interval_s'],t['time_step_s'],'field_output_interval_s')
    if n>20000 or (n+frames-1)//frames+1>101:raise ValueError('Step/frame capture budget exceeded')
    if t['maximum_speed_rad_s']*t['time_step_s']>.1:raise ValueError('Rotor angle step exceeds .1 rad')
    if s['initial_speed_rad_s']>=t['maximum_speed_rad_s']:raise ValueError('Initial speed outside shaft bracket')
    if t['target_speed_rad_s']>=t['maximum_speed_rad_s']:raise ValueError('Target speed must be below maximum')
    evaluate_propeller(r['fluid']['request'],0.);evaluate_propeller(r['fluid']['request'],t['maximum_speed_rad_s'])
    return r,n,stride,frames

def run_three_phase_pod(request):
    r,n,stride,frame_stride=validate_three_phase_request(request)
    started=time.monotonic();motor=ThreePhaseFieldMotor(r['field_motor']);thermal=ThermalNetwork(r['thermal'])
    d,s,t=r['drive'],r['shaft'],r['transient'];dt=t['time_step_s']
    def fluid(w):
        out=evaluate_propeller(r['fluid']['request'],w)
        return {**out,'provider_kind':'hover_bem','is_blade_resolved_cfd':False}
    currents=[0.]*3;angle=s['initial_angle_rad'];speed=s['initial_speed_rad_s'];temperature=list(r['thermal']['initial_temperature_k'])
    duty=[.5]*3;neutral=0.;history=[];frames=[];events=[];mesh=None
    keys=('dc_source_work_j','fluid_shaft_work_j','magnetic_and_kinetic_storage_change_j','thermal_storage_change_j','ambient_heat_j','defect_j')
    totals={key:0. for key in keys};max_kvl=max_kcl=max_shaft=max_defect=0.
    controller=create_three_phase_controller(t['controller_period_s'])
    executable=controller.manifest.executable_sha256
    try:
        for index in range(n+1):
            if time.monotonic()-started>t['wall_budget_s']:raise ValueError('Wall budget exceeded; incomplete result refused')
            now=index*dt;state=motor.evaluate(currents,angle);load=fluid(speed)
            if index<n and index%stride==0:
                derivative=state['angular_derivatives']['dflux_dangle_wb_turn_per_rad']
                rr=thermal.resistances(temperature,duty);R=np.array(rr['winding_resistance_ohm'])+rr['leg_resistance_ohm']
                sensor={'target_rad_s':t['target_speed_rad_s'],'speed_rad_s':speed,'bus_v':d['dc_bus_v'],
                    'current_limit_a':d['current_limit_a'],'kp':d['speed_kp'],'ki':d['speed_ki'],'current_gain':d['current_gain']}
                for j,phase in enumerate('abc'):
                    sensor['current_'+phase]=currents[j];sensor['dpsi_'+phase]=derivative[j];sensor['resistance_'+phase]=float(R[j])
                output=controller.step(sensor,now,t['controller_period_s'])
                duty=[output['VdutyA'],output['VdutyB'],output['VdutyC']]
                events.append({'time_s':now,'sensors':sensor,'duty':list(duty),'controller_state':dict(controller.state)})
            history.append({'time_s':now,'currents_a':list(currents),'current_sum_a':float(sum(currents)),
                'angle_rad':angle,'speed_rad_s':speed,'temperature_k':list(temperature),'duty':list(duty),
                'neutral_voltage_v':neutral,'flux_linkage_wb_turn':state['flux_linkage_wb_turn'],
                'torque_n_m':state['torque_n_m'],'fluid_torque_n_m':load['torque_nm'],'fluid_power_w':load['power_w'],
                'thrust_n':load.get('thrust_n'),'cumulative_energy_j':dict(totals)})
            if index%frame_stride==0 or index==n:
                field=motor.evaluate(currents,angle,True)['field']
                if mesh is None:mesh={k:field[k] for k in ('nodes_m','triangles','region_ids')}
                frames.append({'time_s':now,'angle_rad':angle,'speed_rad_s':speed,'currents_a':list(currents),
                    'temperature_k':list(temperature),'element_b_t':field['element_b_t'],
                    'potential_a_wb_per_m':field['potential_a_wb_per_m'],'current_density_a_per_m2':field['current_density_a_per_m2'],
                    'radial_airflow':load.get('radial_airflow',[])})
            if index==n:break
            accepted=coupled_electrothermal_step(motor,fluid,thermal,currents,angle,speed,temperature,duty,d['dc_bus_v'],dt,
                d['end_turn_inductance_h'],s['inertia_kg_m2'],s['damping_n_m_s'],t['maximum_speed_rad_s'])
            currents=accepted['currents_a'];angle=accepted['angle_rad'];speed=accepted['speed_rad_s'];temperature=accepted['temperature_k'];neutral=accepted['neutral_voltage_v']
            for key in keys:totals[key]+=accepted['energy'][key]
            max_kvl=max(max_kvl,*map(abs,accepted['phase_kvl_residual_v']));max_kcl=max(max_kcl,abs(sum(currents)))
            max_shaft=max(max_shaft,abs(accepted['shaft_residual_n_m']));max_defect=max(max_defect,abs(accepted['energy']['defect_j']))
    finally:controller.close()
    source_names=('propulsion_pod_three_phase_run.py','propulsion_pod_three_phase.py','propulsion_pod_three_phase_field.py','propulsion_pod_thermal.py','propulsion_pod_three_phase_controller.py','propulsion_pod_propeller.py','magnetic_fem.py')
    hashes={name:hashlib.sha256(solver_source_path(name).read_bytes()).hexdigest() for name in source_names}
    result={'contract':RESULT,'status':'completed','model_status':'experimental','production_qualified':False,
        'request':r,'request_sha256':hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'accepted_steps':n,'controller_ticks':len(events),'history':history,'controller_events':events,
        'field_mesh':mesh,'frames':frames,'thermal_node_names':list(NODE_NAMES),
        'energy':{**totals,'maximum_step_defect_j':max_defect,'maximum_phase_kvl_residual_v':max_kvl,
                  'maximum_current_sum_a':max_kcl,'maximum_shaft_residual_n_m':max_shaft,
                  'method':'common midpoint electrothermal fixed point and harmonic discrete-gradient shaft work'},
        'provenance':{'controller':'actual persistent compiled C, three AO duties','controller_source_sha256':SOURCE_SHA256,
            'controller_executable_sha256':executable,'source_sha256':hashes,'field_basis':motor.diagnostics,
            'field_spec_sha256':motor.spec_sha256,'fluid_provider_kind':r['fluid']['kind'],'duration_wall_s':time.monotonic()-started},
        'limitations':['Synthetic three-phase fixed circular linear PM reference; no physical motor calibration or VESC firmware qualification.',
            'Averaged bridge conduction only; no switching/diode/deadtime loss. current_limit_a caps requested current, not actual current or safety protection.',
            'Illustrative supplied lumped thermal network and linear resistance feedback; not measured PCB/package/motor temperatures or CFD cooling.',
            'Hover BEM reaction and annular inflow are not blade-resolved CFD. No whole-drone flight or actual device qualification.',
            'Electrical/bearing losses transfer internally into thermal storage and ambient heat; no duplicated external heat term.',
            'Requires optional Studio source runtime/local C compiler and knowledgeable human numerical review before release.']}
    if len(json.dumps(result,allow_nan=False).encode())>14*1024*1024:raise ValueError('Result exceeds14MiB; reduce field frames/duration')
    return result

__all__=['REQUEST','RESULT','DEFAULT_REQUEST','validate_three_phase_request','run_three_phase_pod']
