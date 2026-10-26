# SPDX-License-Identifier: Apache-2.0
"""Experimental eleven-node teaching thermal network; no device characterization."""
from __future__ import annotations
import copy
import math
from numbers import Real
import numpy as np

NODE_NAMES = ('winding_a','winding_b','winding_c','mos_a_high','mos_a_low',
              'mos_b_high','mos_b_low','mos_c_high','mos_c_low','motor_case','board_case')
_links=np.zeros((11,11))
for _j in range(3): _links[_j,9]=_links[9,_j]=.5
for _j in range(3,9): _links[_j,10]=_links[10,_j]=2.5
DEFAULT_SPEC = dict(capacities_j_per_k=[8.]*3+[.4]*6+[80.,30.],
    ambient_conductance_w_per_k=[0.]*9+[.8,.5],links_w_per_k=_links.tolist(),
    ambient_temperature_k=298.15,initial_temperature_k=[298.15]*11,
    winding_resistance_ref_ohm=[.08]*3,copper_alpha_per_k=.00393,
    mosfet_resistance_ref_ohm=[.002]*6,mosfet_alpha_per_k=.004,
    reference_temperature_k=298.15,minimum_temperature_k=200.,maximum_temperature_k=450.)
del _links, _j

def _scalar(x,name,low,high):
    if isinstance(x,(bool,np.bool_)) or not isinstance(x,Real) or not math.isfinite(x) or not low<=x<=high:
        raise ValueError(f'{name} must be finite in [{low},{high}]')
    return float(x)

def _vector(x,n,name,low,high):
    if not isinstance(x,(list,tuple,np.ndarray)) or np.asarray(x).shape!=(n,):
        raise ValueError(f'{name} must contain {n} values')
    return np.array([_scalar(v,name,low,high) for v in x])

def validate_thermal_spec(spec=None):
    if spec is None: spec={}
    if not isinstance(spec,dict) or set(spec)-set(DEFAULT_SPEC): raise ValueError('Unknown thermal specification')
    s=copy.deepcopy(DEFAULT_SPEC);s.update(copy.deepcopy(spec))
    for key,n,low,high in (('capacities_j_per_k',11,1e-6,1e8),('ambient_conductance_w_per_k',11,0.,1e6),
        ('winding_resistance_ref_ohm',3,1e-9,1e3),('mosfet_resistance_ref_ohm',6,1e-9,1e3)):
        s[key]=_vector(s[key],n,key,low,high).tolist()
    for key,lo,hi in (('ambient_temperature_k',1.,2000.),('reference_temperature_k',1.,2000.),
        ('minimum_temperature_k',1.,2000.),('maximum_temperature_k',1.,2000.),
        ('copper_alpha_per_k',0.,.1),('mosfet_alpha_per_k',0.,.1)):
        s[key]=_scalar(s[key],key,lo,hi)
    if s['minimum_temperature_k']>=s['maximum_temperature_k']: raise ValueError('Temperature bounds must be ordered')
    s['initial_temperature_k']=_vector(s['initial_temperature_k'],11,'initial_temperature_k',s['minimum_temperature_k'],s['maximum_temperature_k']).tolist()
    links=s['links_w_per_k']
    if not isinstance(links,(list,tuple,np.ndarray)) or np.asarray(links).shape!=(11,11): raise ValueError('links must be 11x11')
    links=np.array([_vector(row,11,'link conductance',0.,1e6) for row in links])
    if not np.array_equal(links,links.T) or np.any(np.diag(links)!=0): raise ValueError('links must be exactly symmetric with zero diagonal')
    s['links_w_per_k']=links.tolist()
    for alpha in (s['copper_alpha_per_k'],s['mosfet_alpha_per_k']):
        if 1+alpha*(s['minimum_temperature_k']-s['reference_temperature_k'])<=0:
            raise ValueError('Resistance must remain positive throughout admitted temperature range')
    return s

class ThermalNetwork:
    """Node order NODE_NAMES; six switches are phase-major high then low.

    All capacities/conductances and temperature coefficients are supplied or
    illustrative teaching inputs. No convection correlation is inferred.
    """
    def __init__(self,spec=None):
        self._spec=validate_thermal_spec(spec)
        s=self._spec
        self._capacity=np.array(s['capacities_j_per_k'])
        self._ambient=np.array(s['ambient_conductance_w_per_k'])
        links=np.array(s['links_w_per_k'])
        self._G=np.diag(links.sum(axis=1)+self._ambient)-links
        self._rref=np.r_[s['winding_resistance_ref_ohm'],s['mosfet_resistance_ref_ohm']]
        self._alpha=np.r_[[s['copper_alpha_per_k']]*3,[s['mosfet_alpha_per_k']]*6]

    @property
    def spec(self): return copy.deepcopy(self._spec)

    def resistances(self,Tbar,duty3):
        s=self._spec
        t=_vector(Tbar,11,'temperature',s['minimum_temperature_k'],s['maximum_temperature_k'])
        duty=_vector(duty3,3,'duty',0.,1.)
        r=self._rref*(1+self._alpha*(t[:9]-s['reference_temperature_k']))
        if np.any(r<=0): raise ValueError('Nonpositive resistance')
        leg=duty*r[3::2]+(1-duty)*r[4::2]
        return dict(winding_resistance_ohm=r[:3].tolist(),mosfet_resistance_ohm=r[3:].tolist(),leg_resistance_ohm=leg.tolist())

    def midpoint_step(self,T0,phaseibar3,duty3,dt,bearing_heat_w=0.):
        s=self._spec
        t0=_vector(T0,11,'initial temperature',s['minimum_temperature_k'],s['maximum_temperature_k'])
        current=_vector(phaseibar3,3,'phase current',-1e5,1e5)
        duty=_vector(duty3,3,'duty',0.,1.)
        h=_scalar(dt,'dt',1e-12,1e6);bearing=_scalar(bearing_heat_w,'bearing heat',0.,1e9)
        weights=np.r_[current**2,np.column_stack((duty,1-duty)).ravel()*np.repeat(current**2,2)]
        p0=np.zeros(11);beta=np.zeros(11)
        p0[:9]=weights*self._rref*(1-self._alpha*s['reference_temperature_k'])
        beta[:9]=weights*self._rref*self._alpha
        p0[9]=bearing
        diagonal=2*self._capacity/h
        if np.any(diagonal-np.diag(self._G)+beta < 0):
            raise ValueError('Thermal midpoint monotonicity gate failed; reduce dt')
        A=np.diag(diagonal)+self._G-np.diag(beta)
        eigen=np.linalg.eigvalsh(A)
        if eigen[0]<=1e-12*max(1.,float(eigen[-1])) or eigen[-1]/eigen[0]>1e12:
            raise ValueError('Thermal midpoint positive-feedback/runaway conditioning gate failed; reduce dt/current')
        rhs=diagonal*t0+p0+self._ambient*s['ambient_temperature_k']
        midpoint=np.linalg.solve(A,rhs);t1=2*midpoint-t0
        _vector(t1,11,'final temperature',s['minimum_temperature_k'],s['maximum_temperature_k'])
        resistance=self.resistances(midpoint,duty)
        heat=p0+beta*midpoint
        ambient=self._ambient*(midpoint-s['ambient_temperature_k'])
        residual=self._capacity*(t1-t0)/h+self._G@midpoint-heat-self._ambient*s['ambient_temperature_k']
        storage=float(self._capacity@(t1-t0));ambient_j=float(h*ambient.sum());heat_j=float(h*heat.sum())
        return dict(temperature_k=t1.tolist(),midpoint_temperature_k=midpoint.tolist(),
            thermal_residual_w=residual.tolist(),heat_distribution_w=heat.tolist(),
            winding_heat_w=heat[:3].tolist(),mosfet_heat_w=heat[3:9].tolist(),bearing_heat_w=bearing,
            ambient_heat_j=ambient_j,storage_j=storage,generated_heat_j=heat_j,
            electrical_loss_j=float(h*heat[:9].sum()),energy_residual_j=storage+ambient_j-heat_j,
            minimum_system_eigenvalue_w_per_k=float(eigen[0]),system_condition_number=float(eigen[-1]/eigen[0]),
            resistances=resistance,model_status='experimental illustrative lumped thermal network')

__all__=['NODE_NAMES','DEFAULT_SPEC','validate_thermal_spec','ThermalNetwork']
