# SPDX-License-Identifier: Apache-2.0
"""Explicit experimental inexact Newton linear accuracy budget.

This changes the inner algorithm, never the final nonlinear/physical gates.
It is deliberately separate from the retained strict-relative method.
"""
import math
from .propulsion_pod_inertial_cfd_linear import refined_gmres

METHOD='inexact_absolute_budget_v1'


def forcing_budget(nonlinear_error,nonlinear_target):
    if type(nonlinear_error) not in (int,float) or type(nonlinear_target) not in (int,float) or not math.isfinite(nonlinear_error) or not math.isfinite(nonlinear_target) or not 0<nonlinear_target<nonlinear_error:raise ValueError('Positive unconverged nonlinear error/target required')
    eta=min(.1,.1*(nonlinear_target/nonlinear_error))
    if not 0<eta<1:raise ValueError('Unrepresentable inexact Newton forcing budget')
    return eta


def solve_inexact_step(matrix,rhs,preconditioner,nonlinear_error,nonlinear_target,*,cancel_check=None):
    eta=forcing_budget(float(nonlinear_error),float(nonlinear_target))
    solution,history=refined_gmres(matrix,rhs,preconditioner,relative_tolerance=eta,initial_forcing=.5*eta,cancel_check=cancel_check)
    for entry in history:
        entry.update(method=METHOD,forcing_eta=eta,nonlinear_error=nonlinear_error,nonlinear_target=nonlinear_target,linear_residual_bound_relative_to_PDE_scale=eta*nonlinear_error)
    return solution,history
