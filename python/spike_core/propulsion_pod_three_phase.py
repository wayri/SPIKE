# SPDX-License-Identifier: Apache-2.0
"""Constrained-star circuit/field/shaft with two-way Joule thermal feedback.

This numerical owner takes an explicit fluid provider. A BEM provider remains
a BEM result; a blade-CFD result must come from an admitted CFD owner. Neither
an uncharacterized motor nor a prescribed load is relabelled real hardware.
"""
import math
import numpy as np
from scipy.optimize import brentq
from .propulsion_pod import angular_secants

STAR = np.array([[1.,0.],[0.,1.],[-1.,-1.]])

def coupled_electrothermal_step(motor, fluid_provider, thermal, currents, angle, speed,
        temperature_k, duty, bus_v, dt, end_turn_l, inertia, damping, maximum_speed,
        maximum_thermal_iterations=40, temperature_tolerance_k=1e-8):
    """Accept one common step or raise, leaving every caller state unchanged.

    `fluid_provider(w)` must return resisting torque_nm, power_w and resolved
    provenance. Temperatures use the same midpoint resistance in circuit and
    heat deposition. Only R depends on T: no hidden thermomagnetic energy.
    """
    i0=np.asarray(currents,float);T0=np.asarray(temperature_k,float);d=np.asarray(duty,float)
    if i0.shape!=(3,) or d.shape!=(3,) or T0.shape!=(11,) or not np.isfinite(np.r_[i0,d,T0]).all():
        raise ValueError('Expected finite 3-phase current/duty and 11 temperatures')
    if abs(i0.sum())>1e-10 or np.any(d<0) or np.any(d>1):
        raise ValueError('Floating-star current or averaged bridge duty is invalid')
    if not all(math.isfinite(x) for x in (angle,speed,bus_v,dt,inertia,damping,maximum_speed)):
        raise ValueError('Nonfinite coupled step input')
    if dt<=0 or inertia<=0 or damping<0 or bus_v<=0 or not 0<=speed<maximum_speed:
        raise ValueError('Invalid timestep, passive drive or shaft range')
    L=np.asarray(motor.inductance_h)+np.diag(end_turn_l)
    q0=i0[:2]
    v=d*bus_v
    T1=T0.copy()
    accepted=None
    for iteration in range(maximum_thermal_iterations):
        Tbar=.5*(T0+T1)
        resistance=thermal.resistances(Tbar.tolist(),d.tolist())
        R=np.asarray(resistance['winding_resistance_ohm'])+np.asarray(resistance['leg_resistance_ohm'])
        matrix=STAR.T@(L/dt+np.diag(R/2))@STAR
        rhs=STAR.T@((L/dt-np.diag(R/2))@i0+v)
        def trial(w1):
            wbar=.5*(speed+w1);theta1=angle+dt*wbar
            dpsi,dC=angular_secants(motor,angle,theta1)
            q1=np.linalg.solve(matrix,rhs-STAR.T@(wbar*dpsi))
            i1=STAR@q1;ibar=.5*(i0+i1)
            torque=float(ibar@dpsi+dC)
            fluid=fluid_provider(wbar)
            if not isinstance(fluid,dict) or not all(k in fluid for k in ('torque_nm','power_w')):
                raise ValueError('Fluid provider did not return reaction and shaft work')
            if not all(math.isfinite(fluid[k]) for k in ('torque_nm','power_w')) or fluid['torque_nm']<0:
                raise ValueError('Fluid provider returned invalid reaction')
            if abs(fluid['power_w']-fluid['torque_nm']*wbar)>1e-10+1e-9*abs(fluid['power_w']):
                raise ValueError('Fluid shaft torque/work identity failed')
            residual=inertia*(w1-speed)/dt-torque+damping*wbar+fluid['torque_nm']
            return residual,i1,theta1,torque,dpsi,fluid
        low,high=trial(0.)[0],trial(maximum_speed)[0]
        if abs(low)<1e-13:
            w1=0.
        elif low>=0 or high<=0:
            raise ValueError('Electrothermal shaft root is not bracketed; step rejected')
        else:
            w1=brentq(lambda w:trial(w)[0],0.,maximum_speed,xtol=1e-12,rtol=1e-12,maxiter=60)
        mechanical,i1,theta1,torque,dpsi,fluid=trial(w1)
        ibar=.5*(i0+i1);wbar=.5*(speed+w1)
        heat=thermal.midpoint_step(T0.tolist(),ibar.tolist(),d.tolist(),dt,bearing_heat_w=damping*wbar*wbar)
        updated=np.asarray(heat['temperature_k'])
        difference=float(np.max(np.abs(updated-T1)))
        if difference<=temperature_tolerance_k:
            accepted=(w1,i1,theta1,torque,dpsi,fluid,mechanical,heat,Tbar,R)
            break
        T1=updated
    if accepted is None:
        raise ValueError('Temperature/current fixed point failed; step rejected')
    w1,i1,theta1,torque,dpsi,fluid,mechanical,heat,Tbar,R=accepted
    actual_resistance=thermal.resistances(heat['midpoint_temperature_k'],d.tolist())
    R=np.asarray(actual_resistance['winding_resistance_ohm'])+np.asarray(actual_resistance['leg_resistance_ohm'])
    if np.max(np.abs(i1))>motor.spec['max_current_a']:
        raise ValueError('Field current envelope exceeded; step rejected')
    # Neutral voltage is an unknown reaction; projected KVL and KCL must BOTH close.
    raw=L@(i1-i0)/dt+wbar*dpsi+R*ibar-v
    neutral=-float(raw.mean())
    residual=raw+neutral
    if max(abs(residual))>1e-8 or abs(i1.sum())>1e-10 or abs(mechanical)>1e-10:
        raise ValueError('Phase KVL/KCL or shaft residual failed')
    U0=motor.evaluate(i0.tolist(),angle)['magnetic_energy_j']+.5*i0@np.diag(end_turn_l)@i0
    U1=motor.evaluate(i1.tolist(),theta1)['magnetic_energy_j']+.5*i1@np.diag(end_turn_l)@i1
    storage=float(U1-U0)+.5*inertia*(w1*w1-speed*speed)
    source=dt*float(v@ibar);shaft=dt*fluid['power_w']
    thermal_storage=heat['storage_j']
    ambient=heat['ambient_heat_j']
    defect=source-shaft-storage-thermal_storage-ambient
    if abs(defect)>1e-9+1e-7*max(abs(source),abs(storage),abs(thermal_storage)):
        raise ValueError('Whole electrothermal/shaft/fluid energy failed')
    return {'currents_a':i1.tolist(),'angle_rad':theta1,'speed_rad_s':w1,'temperature_k':heat['temperature_k'],
        'neutral_voltage_v':neutral,'duty':d.tolist(),'field_torque_dg_n_m':torque,'fluid':fluid,
        'thermal':heat,'temperature_iterations':iteration+1,'phase_kvl_residual_v':residual.tolist(),
        'shaft_residual_n_m':mechanical,'energy':{'dc_source_work_j':source,'fluid_shaft_work_j':shaft,
            'magnetic_and_kinetic_storage_change_j':storage,'thermal_storage_change_j':thermal_storage,
            'ambient_heat_j':ambient,'defect_j':float(defect)},
        'resistance_midpoint_ohm':R.tolist(),'back_emf_midpoint_v':(wbar*dpsi).tolist()}
