# SPDX-License-Identifier: Apache-2.0
"""Conservative periodic interpolation of geometry-resolved linear field ports.

Only a common scalar coenergy is interpolated. Flux, torque and Hamiltonian
derivatives follow from it; this does not qualify field/mesh/material accuracy.
"""
import copy
import hashlib
import json
import math
import numpy as np
from scipy.interpolate import CubicSpline
from .propulsion_pod_three_phase import STAR

CONTRACT = 'spike/periodic-linear-motor-ports/v1'


class PeriodicLinearMagneticPort:
    """Geometry-derived linear anhysteretic port, including declared end turns.

    Periodic cubic interpolation is checked for positive balanced inductance at
    sample points and interior extrema. This is a constitutive surrogate of the
    supplied field samples; approximation/validation evidence remains attached.
    """
    kind = 'periodic-linear-field-table/v1'
    def __init__(self, table, end_turn_inductance_h=(0.,0.,0.)):
        if not isinstance(table,dict) or table.get('contract')!=CONTRACT:
            raise ValueError('Expected periodic linear field-port table')
        self.table=copy.deepcopy(table)
        table=self.table
        angles=np.asarray(table['angles_rad'],float)
        L=np.asarray(table['inductance_h'],float);psi=np.asarray(table['pm_flux_wb_turn'],float)
        co=np.asarray(table['zero_current_coenergy_j'],float)
        n=len(angles);end=np.asarray(end_turn_inductance_h,float)
        if n<5 or n>2049 or angles.shape!=(n,) or L.shape!=(n,3,3) or psi.shape!=(n,3) or co.shape!=(n,):
            raise ValueError('Invalid angular field-port table dimensions')
        if end.shape!=(3,) or not np.isfinite(end).all() or np.any(end<0):
            raise ValueError('Three nonnegative end-turn inductances required')
        if not np.isfinite(np.r_[angles,L.ravel(),psi.ravel(),co]).all() or angles[0]!=0 or np.any(np.diff(angles)<=0):
            raise ValueError('Finite strictly ordered angular samples starting at zero required')
        self.period=float(angles[-1])
        if not .001<=self.period<=2*math.pi+1e-10:
            raise ValueError('Invalid mechanical periodic angle')
        for label,values in (('inductance',L),('PM flux',psi),('coenergy',co)):
            scale=max(float(np.max(np.abs(values))),1e-12)
            if np.max(np.abs(values[-1]-values[0]))>1e-10+1e-6*scale:
                raise ValueError('Field-port periodic closure failed: '+label)
        scale=max(float(np.max(np.abs(L))),1e-12)
        if np.max(np.abs(L-L.transpose(0,2,1)))>1e-10+1e-7*scale:
            raise ValueError('Field winding reciprocity failed')
        # Symmetrization removes only admitted roundoff, not a physical mismatch.
        L=.5*(L+L.transpose(0,2,1));L[-1]=L[0];psi[-1]=psi[0];co[-1]=co[0]
        self.L=CubicSpline(angles,L,axis=0,bc_type='periodic',extrapolate='periodic')
        self.psi=CubicSpline(angles,psi,axis=0,bc_type='periodic',extrapolate='periodic')
        self.reference_coenergy_j=float(co[0])
        self.C=CubicSpline(angles,co-co[0],bc_type='periodic',extrapolate='periodic')
        self.end=np.diag(end)
        if type(table['maximum_phase_current_a']) not in (float,int):
            raise ValueError('Numeric phase-current envelope required')
        self.max_current_a=float(table['maximum_phase_current_a'])
        if not math.isfinite(self.max_current_a) or not 0<self.max_current_a<=1000:
            raise ValueError('Explicit phase-current envelope required')
        # Cubic coefficients give a rigorous sufficient SPD certificate: every
        # Bernstein control matrix is positive on each interval. Sampling alone
        # could miss a negative inductance between angular knots.
        minimum=math.inf
        for k,h in enumerate(np.diff(angles)):
            a,b,c,d=self.L.c[:,k]
            controls=(d,d+h*c/3,d+2*h*c/3+h*h*b/3,d+h*c+h*h*b+h**3*a)
            for matrix in controls:
                eigen=np.linalg.eigvalsh(STAR.T@(matrix+self.end)@STAR)
                minimum=min(minimum,float(eigen[0]))
                if eigen[0]<=1e-12 or eigen[-1]/eigen[0]>1e8:
                    raise ValueError('Periodic balanced differential inductance is not certified positive')
        self.diagnostics={'minimum_bernstein_balanced_inductance_h':minimum,
                          'material_qualified':False,'field_load_qualified':False,
                          'interpolation':'periodic cubic common scalar quadratic coenergy',
                          'sample_count':n,'period_rad':self.period}
        self.source_sha256=hashlib.sha256(json.dumps(table,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def _terms(self,theta):
        if not math.isfinite(theta):raise ValueError('Finite unwrapped mechanical angle required')
        L=self.L(theta)+self.end;psi=self.psi(theta)
        return L,psi,STAR.T@L@STAR,STAR.T@psi

    def flux_coordinates(self,currents,theta):
        i=np.asarray(currents,float)
        if i.shape!=(3,) or not np.isfinite(i).all() or abs(i.sum())>1e-10 or max(abs(i))>self.max_current_a:
            raise ValueError('Balanced phase current outside magnetic table envelope')
        L,psi,_,_=self._terms(theta)
        return (STAR.T@(L@i+psi)).tolist()

    def phase_flux_angle_derivative(self,currents,theta):
        """Fixed-current phase linkage derivative for the controller sensors."""
        self.flux_coordinates(currents,theta)  # Same range and balance admission.
        derivative=self.L(theta,1)@np.asarray(currents,float)+self.psi(theta,1)
        if derivative.shape!=(3,) or not np.isfinite(derivative).all():
            raise ValueError('Finite phase flux angle derivative required')
        return derivative.tolist()

    def energy_gradient(self,q,theta):
        q=np.asarray(q,float)
        if q.shape!=(2,) or not np.isfinite(q).all():raise ValueError('Two finite flux coordinates required')
        L,psi,A,p=self._terms(theta);x=np.linalg.solve(A,q-p);i=STAR@x
        if max(abs(i))>self.max_current_a:raise ValueError('Magnetic table phase-current envelope exceeded')
        torque=float(.5*i@self.L(theta,1)@i+i@self.psi(theta,1)+self.C(theta,1))
        energy=float(.5*(q-p)@x-self.C(theta)-self.reference_coenergy_j)
        return {'energy_j':energy,'current_coordinates_a':x.tolist(),'torque_n_m':torque,
                'flux_linkage_wb_turn':(L@i+psi).tolist()}

    def energy_difference(self,start,end):
        a,b=np.asarray(start,float),np.asarray(end,float)
        if a.shape!=(3,) or b.shape!=(3,) or not np.isfinite(np.r_[a,b]).all():
            raise ValueError('Finite flux/angle endpoints required')
        self.energy_gradient(a[:2],a[2]); self.energy_gradient(b[:2],b[2])
        _,_,A0,p0=self._terms(a[2]);_,_,A1,p1=self._terms(b[2])
        M0=np.linalg.inv(A0);M1=np.linalg.inv(A1)
        # Integrating the derivative cancels the large constant before floating
        # subtraction, including near a period boundary and on multiple turns.
        deltaL=self.L.derivative().integrate(a[2],b[2],extrapolate='periodic')
        deltaP=STAR.T@self.psi.derivative().integrate(a[2],b[2],extrapolate='periodic')
        deltaC=float(self.C.derivative().integrate(a[2],b[2],extrapolate='periodic'))
        s0=a[:2]-p0;deltaS=(b[:2]-a[:2])-deltaP;s1=s0+deltaS
        deltaM=-M1@(STAR.T@deltaL@STAR)@M0
        return float(.5*deltaS@M1@(s1+s0)+.5*s0@deltaM@s0-deltaC)


def sample_linear_field_ports(model, intervals, period_rad, maximum_phase_current_a=100., on_sample=None):
    """Execute real field samples; no fitted motor constants or BEM substitute.

    `model.linear_ports(theta)` or callable `model(theta)` must execute/retain the geometry-resolved PDE
    basis and return full three-terminal L, PM flux and zero-current coenergy.
    No field mesh or angle convergence is established by interpolation itself.
    """
    if type(intervals) is not int or not 4<=intervals<=2048:
        raise ValueError('Angular interval count outside 4..2048')
    if type(period_rad) not in (float,int) or not math.isfinite(period_rad) or not .001<=period_rad<=2*math.pi+1e-10:
        raise ValueError('Finite declared mechanical period required')
    angles=np.linspace(0.,period_rad,intervals+1)
    provider=model if callable(model) else model.linear_ports
    samples=[]
    for index,theta in enumerate(angles):
        sample=provider(float(theta));samples.append(sample)
        if on_sample is not None:on_sample(index,len(angles),sample)
    table={'contract':CONTRACT,'angles_rad':angles.tolist(),
           'inductance_h':[s['inductance_h'] for s in samples],
           'pm_flux_wb_turn':[s['pm_flux_linkage_wb_turn'] for s in samples],
           'zero_current_coenergy_j':[s['coenergy_zero_current_j'] for s in samples],
           'maximum_phase_current_a':maximum_phase_current_a,
           'source_field_evidence':[{k:s[k] for k in ('source_sha256','geometry_sha256','spec_sha256','solver_errors','mesh_diagnostics') if k in s} for s in samples],
           'qualification':{'production_qualified':False,'mesh_converged':False,
                            'angular_converged':False,'source_material_qualified':False}}
    PeriodicLinearMagneticPort(table)
    return table
