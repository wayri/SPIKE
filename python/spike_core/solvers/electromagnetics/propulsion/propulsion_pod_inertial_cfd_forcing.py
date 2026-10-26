# SPDX-License-Identifier: Apache-2.0
"""Explicit fixed-relative inexact Newton and fixed-vector merit safeguards."""
import numpy as np
from scipy.linalg import norm
from .propulsion_pod_inertial_cfd_linear import refined_gmres, RefinedLinearSolveError

METHOD='fixed_relative_forcing_v1'
ETA=.1


def applied_direction(matrix,delta,residual,n_velocity,gauge):
    """The gauge multiplier is a solve auxiliary, not an applied state update."""
    direction=matrix@delta
    direction[n_velocity:-1]-=gauge*delta[-1]
    defect=norm(direction+residual);scale=norm(residual)
    if not np.isfinite(direction).all() or not np.isfinite(defect) or not scale>0 or defect>ETA*scale:
        raise ValueError('Actual applied physical direction fails fixed-relative forcing')
    slope=float(residual@direction)/scale
    if not np.isfinite(slope) or slope>=0:raise ValueError('Applied physical Newton direction is not merit descent')
    return direction,slope,float(defect/scale)


def armijo_trial(residual,trial_residual,alpha,slope):
    """Norm merit uses the SAME scaled vector, never a state-dependent divisor."""
    if not 0<alpha<=1 or not np.isfinite(slope) or slope>=0:raise ValueError('Finite descent and bounded positive step required')
    return bool(np.isfinite(trial_residual).all() and norm(trial_residual)<=norm(residual)+1e-4*alpha*slope)


def solve_fixed_step(matrix,residual,preconditioner,n_velocity,gauge,*,cancel_check=None):
    delta,history=refined_gmres(matrix,-residual,preconditioner,relative_tolerance=ETA,initial_forcing=.05,cancel_check=cancel_check)
    try:direction,slope,defect=applied_direction(matrix,delta,residual,n_velocity,gauge)
    except ValueError as error:raise RefinedLinearSolveError(str(error),matrix,-residual,delta,history) from error
    for entry in history:entry.update(method=METHOD,forcing_eta=ETA,applied_physical_direction_relative_defect=defect,raw_scaled_merit_directional_derivative=slope)
    return delta,history,slope
