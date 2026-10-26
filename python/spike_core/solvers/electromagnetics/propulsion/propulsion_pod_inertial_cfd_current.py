# SPDX-License-Identifier: Apache-2.0
"""Explicit restart-only current-Jacobian research preconditioner adapter."""
import numpy as np
from .propulsion_pod_jacobian_schur import JacobianSimpleSchur


class RestartCurrentSchur:
    """No unused reference factors; no seed solve or automatic fallback."""
    def __init__(self,matrix,n_velocity,n_pressure,gauge,*,diagonal_policy="positive_current_v1"):
        if diagonal_policy not in ("positive_current_v1","signed_current_nonzero_v1"):raise ValueError("Explicit supported diagonal policy required")
        self.diagonal_policy=diagonal_policy
        self.n=n_velocity;self.p=n_pressure;self.g=np.array(gauge,copy=True)
        if matrix.shape!=(self.n+self.p+1,self.n+self.p+1) or self.g.shape!=(self.p,) or not np.isfinite(self.g).all():
            raise ValueError('Actual bounded restart matrix/gauge dimensions required')
        self.factor_nonzeros=0
        self.last_factor_options=None
    def solve(self,rhs):
        raise ValueError('Current-Jacobian research adapter requires explicit field restart; no reference seed solve')
    def with_velocity(self,matrix):
        candidate=JacobianSimpleSchur(matrix,self.n,self.p,self.g,
            velocity_drop_tol=1e-6,velocity_fill_factor=20,
            maximum_factor_nonzeros=30_000_000,diagonal_policy=self.diagonal_policy)
        self.last_factor_options=dict(candidate.factor_options)
        self.last_factor_options_sha256=candidate.factor_options_sha256
        self.last_factor_nonzeros=candidate.factor_nonzeros
        return candidate.preconditioner
