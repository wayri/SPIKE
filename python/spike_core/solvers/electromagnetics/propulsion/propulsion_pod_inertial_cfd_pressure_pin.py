# SPDX-License-Identifier: Apache-2.0
"""Algebraic pressure-gauge reduction; original full residual still required."""
import numpy as np
from scipy.linalg import norm


def pressure_pin_reduction(matrix,rhs,n_velocity,pressure_constant_mode):
    """Eliminate one gauge-equivalent pressure dof and redundant continuity row.

    For [A,G,0;C,0,g;0,gT,0], require Gz=0 and C.T z=0.
    This helper does not factor, solve, admit a result, or relax the original
    full-system residual requirement. The caller must check every restored row.
    """
    N=matrix.shape[0];n=n_velocity;rhs=np.asarray(rhs,dtype=float);z=np.asarray(pressure_constant_mode,dtype=float)
    if matrix.shape!=(N,N) or type(n) is not int or not 0<n<N-2 or rhs.shape!=(N,) or z.shape!=(N-n-1,):raise ValueError('Gauge reduction dimensions invalid')
    if not np.isfinite(matrix.data).all() or not np.isfinite(rhs).all() or not np.isfinite(z).all() or not np.any(z):raise ValueError('Finite nonzero gauge data required')
    if matrix[n:-1,n:-1].nnz or matrix[:n,-1].nnz or matrix[-1,:n].nnz or matrix[-1,-1]!=0:raise ValueError('Unsupported nonzero pressure/gauge blocks')
    g=np.asarray(matrix[n:-1,-1].toarray()).ravel();row=np.asarray(matrix[-1,n:-1].toarray()).ravel()
    if not np.array_equal(g,row):raise ValueError('Gauge row and column must agree')
    denominator=float(z@g)
    if not np.isfinite(denominator) or abs(denominator)<=1e-12*norm(z)*norm(g):raise ValueError('Gauge does not constrain constant pressure mode')
    G=matrix[:n,n:-1];C=matrix[n:-1,:n]
    upper=float(norm(G@z)/(max(norm(G.data),np.finfo(float).tiny)*norm(z)))
    lower=float(norm(C.T@z)/(max(norm(C.data),np.finfo(float).tiny)*norm(z)))
    if not np.isfinite(upper+lower) or max(upper,lower)>1e-12:raise ValueError('Actual upper/right and continuity/left pressure null checks failed')
    multiplier=float(z@rhs[n:-1]/denominator);projected=rhs[n:-1]-g*multiplier;pin=int(np.argmax(abs(z)));pressure_keep=np.flatnonzero(np.arange(len(z))!=pin);keep=np.r_[np.arange(n),n+pressure_keep]
    reduced=matrix[keep][:,keep].tocsc();reduced_rhs=np.r_[rhs[:n],projected[pressure_keep]]
    context={'n':n,'N':N,'z':z.copy(),'g':g,'denominator':denominator,'multiplier':multiplier,'gauge_rhs':float(rhs[-1]),'pressure_keep':pressure_keep,'pin':pin}
    evidence={'pinned_pressure_index':pin,'upper_constant_mode_relative_residual':upper,'lower_constant_mode_relative_residual':lower,'gauge_dot_constant_mode':denominator,'reduced_size':len(keep),'original_size':N,'original_full_residual_check_required':True}
    return reduced,reduced_rhs,context,evidence


def restore_pressure_gauge(reduced_solution,context):
    n=context['n'];solution=np.asarray(reduced_solution,dtype=float)
    if solution.shape!=(context['N']-2,) or not np.isfinite(solution).all():raise ValueError('Finite reduced solution required')
    pressure=np.zeros(len(context['z']));pressure[context['pressure_keep']]=solution[n:]
    pressure+=context['z']*((context['gauge_rhs']-context['g']@pressure)/context['denominator'])
    return np.r_[solution[:n],pressure,context['multiplier']]
