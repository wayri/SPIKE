# SPDX-License-Identifier: Apache-2.0
"""Bounded same-equation GMRES residual refinement for Newton corrections."""
import numpy as np
from scipy.linalg import norm as safe_norm
from scipy.sparse.linalg import gmres


class RefinedLinearSolveError(ValueError):
    def __init__(self,message,matrix,rhs,iterate,history):
        super().__init__(message);self.matrix=matrix;self.rhs=rhs;self.iterate=iterate;self.linear_history=history


def refined_gmres(matrix,rhs,preconditioner,*,max_refinements=2,cancel_check=None,initial_iterate=None,relative_tolerance=1e-8,initial_forcing=5e-9):
    """Return only after independent selected full-system convergence.

    Default1e-8 retains the strict method. A separately named inexact Newton
    owner supplies its explicitly derived accuracy budget; no implicit waiver.

    A failed initial Krylov status supplies an iterate only. Recompute the
    full residual and solve a fresh correction equation if necessary. Inner
    status is retained verbatim; the outer driver independently checks the
    original system, including an already converged nonzero initial iterate.
    No matrix/forcing/physical penalty changes.
    """
    if type(max_refinements) is not int or not 0<=max_refinements<=3:raise ValueError('Refinement budget0..3 required')
    if type(relative_tolerance) not in (int,float) or not np.isfinite(relative_tolerance) or not 0<relative_tolerance<=.1 or type(initial_forcing) not in (int,float) or not np.isfinite(initial_forcing) or not 0<initial_forcing<=relative_tolerance:raise ValueError('Explicit finite linear accuracy/forcing budget required')
    rhs=np.asarray(rhs,dtype=float);norm=float(safe_norm(rhs));x=np.zeros_like(rhs) if initial_iterate is None else np.array(initial_iterate,dtype=float,copy=True);history=[]
    if not np.isfinite(rhs).all():raise ValueError('Nonfinite linear rhs')
    if x.shape!=rhs.shape or not np.isfinite(x).all():raise ValueError('Finite matching initial linear iterate required')
    if not np.any(rhs):return np.zeros_like(rhs),history
    if not np.isfinite(norm) or norm<=0:raise ValueError('Finite positive robust rhs norm required')
    for refinement in range(max_refinements+1):
        if cancel_check and cancel_check():raise InterruptedError('Newton linear refinement cancelled')
        residual=rhs-matrix@x;trace=[]
        rnorm=float(safe_norm(residual));before=rnorm/norm
        if np.isfinite(before) and before<=relative_tolerance:
            history.append({'refinement':refinement,'GMRES_info':None,'iterations':0,'true_full_relative_residual':before,'overall_refinement_status':'converged_original_system','no_correction_required':True})
            return x,history
        def report(value):
            if cancel_check and cancel_check():raise InterruptedError('Newton Krylov budget cancelled')
            trace.append(float(value))
        forcing=initial_forcing if refinement==0 and initial_iterate is None else .01
        # SciPy GMRES computes a non-scaled np.linalg.norm internally. Only
        # extreme rhs magnitudes are scalar-normalized to prevent under/overflow;
        # ordinary case/replay arithmetic remains unchanged.
        rhs_scale=rnorm if rnorm and (rnorm<1e-140 or rnorm>1e140) else 1.
        correction,info=gmres(matrix,residual/rhs_scale,M=preconditioner,rtol=forcing,atol=0.,restart=100,maxiter=40,callback=report,callback_type='pr_norm')
        x+=correction*rhs_scale;true=float(safe_norm(matrix@x-rhs)/norm)
        history.append({'refinement':refinement,'GMRES_info':int(info),'iterations':len(trace),'requested_correction_forcing':forcing,'true_full_relative_residual':true,'full_relative_residual_target':relative_tolerance,'correction_rhs_relative':rnorm/norm,'scalar_rhs_normalization':rhs_scale,'overall_refinement_status':'converged_original_system' if np.isfinite(true) and true<=relative_tolerance and info>=0 else 'not_converged'})
        if not np.isfinite(x).all() or not np.isfinite(true):break
        if info<0:break
        if true<=relative_tolerance:return x,history
    raise RefinedLinearSolveError('Bounded refined Newton linear solve failed selected full-system true-residual gate: '+str(history),matrix,rhs,x,history)
