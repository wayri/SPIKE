# SPDX-License-Identifier: Apache-2.0
"""Analytic Fourier Dirichlet-to-Neumann energy for a rotating vacuum annulus.

Two independently meshed domains meet through one coherent positive energy;
angle changes only rotate Fourier coefficients, never remesh the field domain.
This operator is not by itself a complete motor or a convergence certificate.
"""
import math
import numpy as np

MU0=4*math.pi*1e-7


class AnnularGap:
    """Orthonormal real Fourier traces: constant, cos1,sin1,cos2,sin2,... ."""
    def __init__(self,inner_radius_m,outer_radius_m,stack_depth_m,maximum_mode):
        for value in (inner_radius_m,outer_radius_m,stack_depth_m):
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Positive finite annulus dimensions required')
        if outer_radius_m<=inner_radius_m:raise ValueError('Outer gap radius must exceed inner radius')
        if type(maximum_mode) is not int or not 0<=maximum_mode<=1024:
            raise ValueError('Fourier mode budget must be 0..1024')
        self.a=float(inner_radius_m);self.b=float(outer_radius_m)
        self.depth=float(stack_depth_m);self.maximum_mode=maximum_mode
        self.size=2*maximum_mode+1;self.log_ratio=math.log1p((self.b-self.a)/self.a)
        self.scale=self.depth/MU0
        if not math.isfinite(self.log_ratio) or self.log_ratio<=0 or not math.isfinite(self.scale/self.log_ratio):
            raise ValueError('Annulus dimensions exceed finite numerical range')

    def trace_basis(self,angles):
        angles=np.asarray(angles,float)
        if angles.ndim!=1 or not len(angles) or not np.isfinite(angles).all():
            raise ValueError('Finite boundary angles required')
        basis=np.empty((len(angles),self.size));basis[:,0]=1/math.sqrt(2*math.pi)
        for n in range(1,self.maximum_mode+1):
            basis[:,2*n-1]=np.cos(n*angles)/math.sqrt(math.pi)
            basis[:,2*n]=np.sin(n*angles)/math.sqrt(math.pi)
        return basis

    def matrices(self,angle_rad):
        """Return K and dK/dmechanical-angle for [.rotor-local,.stator] traces."""
        if type(angle_rad) not in (int,float) or not math.isfinite(angle_rad):
            raise ValueError('Finite mechanical angle required')
        m=self.size;K=np.zeros((2*m,2*m));derivative=np.zeros_like(K)
        k0=self.scale/self.log_ratio
        K[0,0]=K[m,m]=k0;K[0,m]=K[m,0]=-k0
        for n in range(1,self.maximum_mode+1):
            x=n*self.log_ratio;e=math.exp(-x)
            denominator=-math.expm1(-2*x)
            diagonal=self.scale*n*(1+e*e)/denominator
            cross=self.scale*n*2*e/denominator
            c=math.cos(n*angle_rad);s=math.sin(n*angle_rad)
            R=np.array([[c,-s],[s,c]]);dR=n*np.array([[-s,-c],[c,-s]])
            i=slice(2*n-1,2*n+1);j=slice(m+2*n-1,m+2*n+1)
            K[i,i]=diagonal*np.eye(2);K[j,j]=diagonal*np.eye(2)
            K[i,j]=-cross*R.T;K[j,i]=-cross*R
            derivative[i,j]=-cross*dR.T;derivative[j,i]=-cross*dR
        if not np.isfinite(K).all() or not np.isfinite(derivative).all():
            raise ValueError('Annular matrix exceeds finite numerical range')
        return K,derivative

    def energy_torque(self,rotor_coefficients,stator_coefficients,angle_rad):
        c=np.r_[rotor_coefficients,stator_coefficients].astype(float)
        if c.shape!=(2*self.size,) or not np.isfinite(c).all():raise ValueError('Finite aligned Fourier coefficients required')
        K,dK=self.matrices(angle_rad)
        r=c[:self.size];s=c[self.size:]
        # Positive sum/difference form avoids cancellation of nearly equal
        # traces, especially the exact common-constant gauge mode.
        with np.errstate(over='ignore',invalid='ignore'):
            energy=.5*self.scale/self.log_ratio*(r[0]-s[0])**2
            for n in range(1,self.maximum_mode+1):
                co=math.cos(n*angle_rad);si=math.sin(n*angle_rad)
                rotated=np.array([[co,-si],[si,co]])@r[2*n-1:2*n+1]
                plus=rotated+s[2*n-1:2*n+1];minus=rotated-s[2*n-1:2*n+1]
                t=math.tanh(n*self.log_ratio/2)
                energy+=self.scale*n/4*(t*(plus@plus)+(minus@minus)/t)
            torque=float(-.5*c@dK@c)
        if not np.isfinite([energy,torque]).all():raise ValueError('Annular energy exceeds finite numerical range')
        return {'vacuum_energy_j':float(energy),'rotor_torque_n_m':torque}

    def field(self,rotor_coefficients,stator_coefficients,angle_rad,radius_m,azimuth_rad):
        """Analytic Az, B_r and B_phi in the physical gap; all arrays in SI."""
        if type(angle_rad) not in (int,float) or not math.isfinite(angle_rad):
            raise ValueError('Finite mechanical angle required')
        a=np.asarray(rotor_coefficients,float);b=np.asarray(stator_coefficients,float)
        if a.shape!=(self.size,) or b.shape!=(self.size,) or not np.isfinite(np.r_[a,b]).all():
            raise ValueError('Aligned finite Fourier coefficients required')
        r,phi=np.broadcast_arrays(np.asarray(radius_m,float),np.asarray(azimuth_rad,float))
        if not np.isfinite(r).all() or not np.isfinite(phi).all() or np.any(r<self.a) or np.any(r>self.b):
            raise ValueError('Field samples must lie in the analytic gap')
        t=np.log(r/self.a);L=self.log_ratio
        A=((1-t/L)*a[0]+t/L*b[0])/math.sqrt(2*math.pi)
        dr=np.full_like(r,(b[0]-a[0])/(L*math.sqrt(2*math.pi))) / r
        dphi=np.zeros_like(r)
        for n in range(1,self.maximum_mode+1):
            c=math.cos(n*angle_rad);s=math.sin(n*angle_rad)
            ac=c*a[2*n-1]-s*a[2*n];ass=s*a[2*n-1]+c*a[2*n]
            bc,bs=b[2*n-1:2*n+1]
            # Stable sinh ratios for large mode counts and thin gaps.
            den=-math.expm1(-2*n*L)
            f=np.exp(-n*t)*(-np.expm1(-2*n*(L-t)))/den
            g=np.exp(-n*(L-t))*(-np.expm1(-2*n*t))/den
            df=-n*np.exp(-n*t)*(1+np.exp(-2*n*(L-t)))/den/r
            dg=n*np.exp(-n*(L-t))*(1+np.exp(-2*n*t))/den/r
            co=np.cos(n*phi)/math.sqrt(math.pi);si=np.sin(n*phi)/math.sqrt(math.pi)
            A+=(f*ac+g*bc)*co+(f*ass+g*bs)*si
            dr+=(df*ac+dg*bc)*co+(df*ass+dg*bs)*si
            dphi+=n*(-(f*ac+g*bc)*si+(f*ass+g*bs)*co)
        if not np.isfinite(A).all() or not np.isfinite(dphi/r).all() or not np.isfinite(dr).all():
            raise ValueError('Annular field exceeds finite numerical range')
        return {'potential_a_wb_per_m':A,'radial_b_t':dphi/r,'azimuthal_b_t':-dr}
