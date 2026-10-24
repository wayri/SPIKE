# SPDX-License-Identifier: Apache-2.0
"""Compiled-controller orchestration over conservative geometry-derived ports.

Internal integration seam: no imported field/load table is silently admitted
as converged. Public study admission and exact source bindings belong upstream.
"""
import hashlib
import copy
from contextlib import ExitStack
from pathlib import Path
import time
import numpy as np
from .propulsion_pod_energy_step import energy_port_step
from .propulsion_pod_three_phase_controller import create_three_phase_controller,SOURCE_SHA256
from .propulsion_pod_thermal import ThermalNetwork


def run_geometry_loop(port, fluid_trial, *, initial_currents_a, initial_angle_rad,
                      initial_speed_rad_s, thermal_spec, drive, shaft, transient):
    """Run actual C ticks and common implicit electrothermal/shaft steps.

    The port contains end-turn storage. Load trials must be immutable and
    numerically admitted by the caller. Results retain unqualified status unless
    a separate revision-bound study establishes the required physical evidence.
    Controller sensors use the port's fixed-current phase linkage derivative.
    A direct nonlinear port must supply a coherent Hamiltonian and stable energy
    differences under the same stepper gates. Its internal result is distinct
    from the public linear-table study; this runner does not admit materials,
    field/load convergence or a new public worker/GUI route.
    """
    budget=transient.get('wall_budget_s')
    if type(budget) not in (int,float) or not np.isfinite(budget) or budget<=0:
        raise ValueError('Positive finite geometry-loop wall budget required')
    deadline=time.monotonic()+budget
    bounded=getattr(port,'bounded_run',None)
    if getattr(port,'kind',None)=='direct-nonlinear-field-port/v1' and not callable(bounded):
        raise ValueError('Direct magnetic port must inherit the whole-loop deadline')
    with ExitStack() as scope:
        if callable(bounded):scope.enter_context(bounded(deadline))
        return _run_geometry_loop(port,fluid_trial,initial_currents_a=initial_currents_a,
            initial_angle_rad=initial_angle_rad,initial_speed_rad_s=initial_speed_rad_s,
            thermal_spec=thermal_spec,drive=drive,shaft=shaft,transient=transient,
            deadline_monotonic=deadline)


def _run_geometry_loop(port, fluid_trial, *, initial_currents_a, initial_angle_rad,
                       initial_speed_rad_s, thermal_spec, drive, shaft, transient,
                       deadline_monotonic):
    """Run inside the caller's cooperative whole-loop wall-budget scope."""
    kind=getattr(port,'kind',None)
    if kind not in ('periodic-linear-field-table/v1','direct-nonlinear-field-port/v1'):
        raise ValueError('Explicit supported magnetic port kind required')
    if not callable(getattr(port,'phase_flux_angle_derivative',None)):
        raise ValueError('Magnetic port fixed-current phase derivative required')
    dt=float(transient['time_step_s']);duration=float(transient['duration_s'])
    period=float(transient['controller_period_s'])
    if not np.isfinite([dt,duration,period]).all() or min(dt,duration,period)<=0:
        raise ValueError('Positive finite time controls required')
    count=round(duration/dt);stride=round(period/dt)
    if not 1<=count<=20000 or stride<1 or abs(count*dt-duration)>1e-12 or abs(stride*dt-period)>1e-12:
        raise ValueError('Bounded integral timestep/controller grid required')
    thermal=ThermalNetwork(thermal_spec)
    q=port.flux_coordinates(initial_currents_a,initial_angle_rad)
    theta=float(initial_angle_rad);speed=float(initial_speed_rad_s)
    temperature=list(thermal.spec['initial_temperature_k']);duty=[.5]*3
    controller=create_three_phase_controller(period)
    history=[];ticks=[];totals={};previous_interval=None
    try:
        for index in range(count+1):
            if time.monotonic()>deadline_monotonic:
                raise ValueError('Geometry-loop wall budget exceeded; incomplete result refused')
            now=index*dt;state=port.energy_gradient(q,theta)
            x=np.asarray(state['current_coordinates_a']);currents=np.r_[x,-x.sum()]
            if index<count and index%stride==0:
                resistance=thermal.resistances(temperature,duty)
                R=np.asarray(resistance['winding_resistance_ohm'])+resistance['leg_resistance_ohm']
                derivative=np.asarray(port.phase_flux_angle_derivative(currents.tolist(),theta),float)
                if derivative.shape!=(3,) or not np.isfinite(derivative).all():
                    raise ValueError('Finite three-phase flux angle derivative required')
                sensors={'target_rad_s':transient['target_speed_rad_s'],'speed_rad_s':speed,
                         'bus_v':drive['dc_bus_v'],'current_limit_a':drive['current_limit_a'],
                         'kp':drive['speed_kp'],'ki':drive['speed_ki'],'current_gain':drive['current_gain']}
                for j,name in enumerate('abc'):
                    sensors['current_'+name]=float(currents[j]);sensors['dpsi_'+name]=float(derivative[j]);sensors['resistance_'+name]=float(R[j])
                output=controller.step(sensors,now,period)
                duty=[output['VdutyA'],output['VdutyB'],output['VdutyC']]
                ticks.append({'time_s':now,'sensors':sensors,'duty':list(duty)})
            history.append({'time_s':now,'currents_a':currents.tolist(),'flux_coordinates_wb_turn':list(q),
                            'speed_rad_s':speed,'angle_rad':theta,'temperature_k':list(temperature),
                            'duty':list(duty),'cumulative_energy_j':dict(totals),
                            'field_torque_n_m':state['torque_n_m'],
                            'preceding_interval':previous_interval})
            if index==count:break
            step=energy_port_step(port,fluid_trial,thermal,q,theta,speed,temperature,duty,drive['dc_bus_v'],dt,
                                 shaft['inertia_kg_m2'],shaft['damping_n_m_s'],transient['maximum_speed_rad_s'])
            q=step['flux_coordinates_wb_turn'];theta=step['angle_rad'];speed=step['speed_rad_s'];temperature=step['temperature_k']
            previous_interval={'start_time_s':now,'end_time_s':(index+1)*dt,
                'field_torque_dg_n_m':step['field_torque_dg_n_m'],
                'work_currents_a':list(step['work_currents_a']),
                'fluid_midpoint':{key:step['fluid'][key] for key in ('torque_nm','thrust_n','power_w',
                    'provider_kind','load_table_sha256') if key in step['fluid']},
                'projected_kvl_residual_v':list(step['projected_kvl_residual_v']),
                'shaft_residual_n_m':step['shaft_residual_n_m'],'energy_j':dict(step['energy'])}
            for key,value in step['energy'].items():totals[key]=totals.get(key,0.)+value
    finally:
        controller.close()
    if time.monotonic()>deadline_monotonic:
        raise ValueError('Geometry-loop wall budget exceeded; incomplete result refused')
    result={'contract':('spike/geometry-propulsion-loop-result/v1' if kind=='periodic-linear-field-table/v1'
                        else 'spike/geometry-propulsion-direct-loop-result/v1'),'status':'completed',
            'production_qualified':False,'physical_load_qualified':False,
            'accepted_steps':count,'controller_ticks':len(ticks),'history':history,'controller_events':ticks,
            'energy':totals,'controller_executable_sha256':controller.manifest.executable_sha256,
            'controller_source_sha256':SOURCE_SHA256,
            'magnetic_port_sha256':port.source_sha256,'magnetic_port_kind':kind,
            'fluid_port_sha256':getattr(fluid_trial,'source_sha256',None),
            'request':{'initial_currents_a':list(initial_currents_a),'initial_angle_rad':float(initial_angle_rad),
                'initial_speed_rad_s':float(initial_speed_rad_s),'thermal':copy.deepcopy(thermal.spec),
                'drive':copy.deepcopy(drive),'shaft':copy.deepcopy(shaft),'transient':copy.deepcopy(transient)},
            'field_port_diagnostics':copy.deepcopy(port.diagnostics),
            'orchestrator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope':'Actual compiled C and conservative supplied magnetic/load ports; source-specific numerical and physical admission remains separate.'}
    if kind=='periodic-linear-field-table/v1':result['field_table_sha256']=port.source_sha256
    return result
