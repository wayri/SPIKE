# SPDX-License-Identifier: Apache-2.0
"""Fixed SIMPLE pressure-graph preconditioner; does not change the PDE.

The complete gauge-bordered negative Schur approximation is factored. The
gauge functional is deliberately not assumed to equal the pressure null mode.
"""
import numpy as np
from scipy.sparse import bmat,diags,csc_matrix
from scipy.sparse.linalg import LinearOperator,spilu,splu,gmres


class SimpleSchurStokes:
    def __init__(self,A,n,npres,gauge,*,reference_velocity=True):
        if type(reference_velocity) is not bool:raise ValueError('Explicit reference velocity retention bool required')
        self.A=A;self.n=n;self.npres=npres;self.gauge=np.asarray(gauge)
        self.C=A[n:n+npres,:n].tocsc()
        diagonal=A[:n,:n].diagonal()
        if np.any(diagonal<=0) or not np.isfinite(diagonal).all():
            raise ValueError('Positive finite Stokes velocity diagonal required')
        S=self.C@diags(1/diagonal)@self.C.T
        g=csc_matrix(self.gauge[:,None])
        self.schur=splu(bmat([[-S,g],[g.T,csc_matrix((1,1))]],format='csc'))
        self.ilu=spilu(A[:n,:n].tocsc(),drop_tol=1e-3,fill_factor=8) if reference_velocity else None
        # Legacy attribute name: native stored-entry counter, not exposed CSC nnz.
        self.factor_nonzeros=self.schur.nnz+(self.ilu.nnz if self.ilu is not None else 0)
        self.preconditioner=self._operator(A,self.ilu) if self.ilu is not None else None
        self.last_iterations=0

    def _operator(self,matrix,ilu):
        n=self.n;C=self.C;npres=self.npres;schur=self.schur
        def apply(r):
            yu=ilu.solve(r[:n])
            p_lambda=schur.solve(np.r_[r[n:n+npres]-C@yu,r[-1]])
            return np.r_[yu-ilu.solve(C.T@p_lambda[:-1]),p_lambda]
        return LinearOperator(matrix.shape,matvec=apply)

    def with_velocity(self,matrix):
        ilu=spilu(matrix[:self.n,:self.n].tocsc(),drop_tol=1e-4,fill_factor=10)
        count=self.schur.nnz+ilu.nnz
        if not 0<=count<=30_000_000:raise ValueError('Explicit combined preconditioner factor budget exceeded')
        return self._operator(matrix,ilu)

    def solve(self,rhs):
        if self.ilu is None:raise ValueError('Reference velocity seed factor explicitly omitted for field restart')
        history=[]
        if not np.any(rhs):return np.zeros_like(rhs)
        result,info=gmres(self.A,rhs,M=self.preconditioner,rtol=1e-12,atol=0.,restart=100,maxiter=40,callback=lambda r:history.append(float(r)),callback_type='pr_norm')
        self.last_iterations=len(history)
        relative=float(np.linalg.norm(self.A@result-rhs)/np.linalg.norm(rhs))
        if info or relative>1e-10:
            raise ValueError('SIMPLE-Schur Stokes solve failed unchanged residual gate: info='+str(info)+' iterations='+str(len(history))+' true_relative='+str(relative))
        return result
