# SPDX-License-Identifier: Apache-2.0
"""O(N) evaluation of the existing exact annular Fourier energy.

No material model or cutoff convergence claim is added. See the independent
PROPULSION_POD_MODAL_GAP_REVIEW_20261024.md and implementation method record.
"""
import math
import numpy as np

from .propulsion_pod_annular_gap import AnnularGap
from .propulsion_pod_magnetic_p2 import _require


METHOD = 'exact-positive-modal-annular-gap/v1'


class ModalGap:
    """One immutable-angle modal snapshot, ordered [rotor trace, stator trace]."""
    def __init__(self, gap, angle_rad):
        _require(isinstance(gap, AnnularGap), 'Prepared analytic annular gap required')
        checked = AnnularGap(gap.a, gap.b, gap.depth, gap.maximum_mode)
        _require(gap.size == checked.size and gap.log_ratio == checked.log_ratio
                 and gap.scale == checked.scale, 'Prepared annular gap changed')
        _require(type(angle_rad) in (int, float) and math.isfinite(angle_rad),
                 'Finite mechanical angle required')
        self.size = gap.size
        self.k0 = gap.scale/gap.log_ratio
        self.n = np.arange(1, gap.maximum_mode+1, dtype=float)
        x = self.n*gap.log_ratio
        e = np.exp(-x)
        denominator = -np.expm1(-2*x)
        self.diagonal = gap.scale*self.n*(1+e*e)/denominator
        self.cross = gap.scale*self.n*2*e/denominator
        self.half_scale_n = gap.scale*self.n/2
        self.t = np.tanh(x/2)
        self.cos = np.cos(self.n*angle_rad)
        self.sin = np.sin(self.n*angle_rad)
        for value in vars(self).values():
            if isinstance(value, np.ndarray):
                _require(np.isfinite(value).all(), 'Modal gap exceeds finite numerical range')
                value.setflags(write=False)

    def _pairs(self, coefficients):
        raw = np.asarray(coefficients)
        _require(raw.dtype.kind in 'iuf' and raw.shape == (2*self.size,),
                 'Real aligned Fourier coefficients required')
        c = np.asarray(raw, dtype=float)
        _require(np.isfinite(c).all(), 'Finite aligned Fourier coefficients required')
        return c, c[1:self.size].reshape(-1, 2), c[self.size+1:].reshape(-1, 2)

    def _rotate(self, r):
        return np.column_stack((self.cos*r[:, 0]-self.sin*r[:, 1],
                                self.sin*r[:, 0]+self.cos*r[:, 1]))

    def _unrotate(self, u):
        return np.column_stack((self.cos*u[:, 0]+self.sin*u[:, 1],
                                -self.sin*u[:, 0]+self.cos*u[:, 1]))

    def apply(self, coefficients):
        """Exact gap Hessian action, using the stable positive energy gradient."""
        c, r, s = self._pairs(coefficients)
        u = self._rotate(r)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            plus = self.t[:, None]*(u+s)
            minus = (u-s)/self.t[:, None]
            gr = self._unrotate(self.half_scale_n[:, None]*(plus+minus))
            gs = self.half_scale_n[:, None]*(plus-minus)
            zero = self.k0*(c[0]-c[self.size])
            result = np.r_[zero, gr.ravel(), -zero, gs.ravel()]
        _require(np.isfinite(result).all(), 'Modal gap action exceeds finite numerical range')
        return result

    def angle_derivative_action(self, coefficients):
        c, r, s = self._pairs(coefficients)
        u = self._rotate(r)
        # R'=n J R; (R')^T=-n R^T J.
        js = np.column_stack((-s[:, 1], s[:, 0]))
        ju = np.column_stack((-u[:, 1], u[:, 0]))
        with np.errstate(over='ignore', invalid='ignore'):
            gr = self.cross[:, None]*self.n[:, None]*self._unrotate(js)
            gs = -self.cross[:, None]*self.n[:, None]*ju
            result = np.r_[0., gr.ravel(), 0., gs.ravel()]
        _require(np.isfinite(result).all(), 'Modal angle action exceeds finite numerical range')
        return result

    def energy_torque(self, coefficients):
        c, r, s = self._pairs(coefficients)
        u = self._rotate(r)
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            plus, minus = u+s, u-s
            energy = .5*self.k0*(c[0]-c[self.size])**2
            energy += np.sum(.5*self.half_scale_n*(self.t*np.sum(plus*plus, axis=1)
                                                   + np.sum(minus*minus, axis=1)/self.t))
            torque = np.sum(self.cross*self.n*(s[:, 1]*u[:, 0]-s[:, 0]*u[:, 1]))
        _require(np.isfinite([energy, torque]).all(), 'Modal energy exceeds finite numerical range')
        return {'vacuum_energy_j': float(energy), 'rotor_torque_n_m': float(torque)}

    def energy_difference(self, initial, final, angle_increment_rad):
        """Same gap energy difference, cancelling constants before arithmetic."""
        _require(type(angle_increment_rad) in (int, float) and math.isfinite(angle_increment_rad),
                 'Finite unwrapped angle increment required')
        a, r0, s0 = self._pairs(initial)
        b, r1, s1 = self._pairs(final)
        delta = self.n*angle_increment_rad
        cm1, sn = -2*np.sin(delta/2)**2, np.sin(delta)
        dr = r1-r0
        dr += np.column_stack((cm1*r1[:, 0]-sn*r1[:, 1],
                               sn*r1[:, 0]+cm1*r1[:, 1]))
        du, ds = self._rotate(dr), s1-s0
        u0 = self._rotate(r0)
        plus, minus = u0+s0, u0-s0
        dp, dm = du+ds, du-ds
        dz = (b[0]-a[0])-(b[self.size]-a[self.size])
        value = .5*self.k0*dz*(2*(a[0]-a[self.size])+dz)
        value += np.sum(.5*self.half_scale_n*(self.t*np.sum(dp*(2*plus+dp), axis=1)
                                              + np.sum(dm*(2*minus+dm), axis=1)/self.t))
        _require(math.isfinite(value), 'Modal energy difference exceeds finite range')
        return float(value)

    def add_to_dense(self, matrix):
        """Add exact modal entries to a caller-owned reference Schur allocation."""
        _require(isinstance(matrix, np.ndarray) and matrix.dtype == np.dtype('float64')
                 and matrix.shape == (2*self.size, 2*self.size) and matrix.flags.writeable,
                 'Owned writable float64 reference matrix required')
        m = self.size
        matrix[0, 0] += self.k0
        matrix[m, m] += self.k0
        matrix[0, m] -= self.k0
        matrix[m, 0] -= self.k0
        i = np.arange(1, m, 2);j = i+m
        for index in (i, i+1, j, j+1):matrix[index, index] += self.diagonal
        bc, bs = self.cross*self.cos, self.cross*self.sin
        for row, col, value in ((i,j,-bc),(i+1,j+1,-bc),(i,j+1,-bs),(i+1,j,bs)):
            matrix[row, col] += value
            matrix[col, row] += value
        _require(np.isfinite(matrix).all(), 'Reference Schur exceeds finite numerical range')
        return matrix
