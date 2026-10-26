# SPDX-License-Identifier: Apache-2.0
"""Bounded algebraic reassociation of existing P2 volume transport tensors.

Same inputs, quadrature and c,i,a,j,b Jacobian layout as RotatingNavierStokes.
Boundary flux, Coriolis block formation and sparse assembly stay with caller.
See validation/PROPULSION_POD_TRANSPORT_CONTRACTIONS_20261024.md.
"""
import math

import numpy as np


def volume_transport_contractions(N, grad, weights, uq, gu, w, rho, *, jacobian=True,
                                  chunk_cells=128, maximum_cells=40000,
                                  maximum_output_bytes=224*1024**2):
    """Return (skew[c,i,j], mass[c,i,j], extra[c,i,a,j,b] or None).

    Inputs are existing float64 arrays: N[q,10], grad[c,q,10,3],
    weights[c,q], uq/w[c,q,3], gu[c,q,3,3]. Density is kg/m^3.
    Positive existing volume weights are retained exactly. Working tensors
    contain at most chunk_cells cells; no global c,q,i,j array is formed.
    """
    if type(jacobian) is not bool:
        raise ValueError('Jacobian flag must be boolean')
    if type(rho) not in (int, float) or not math.isfinite(rho) or rho <= 0:
        raise ValueError('Positive finite density required')
    if type(chunk_cells) is not int or not 1 <= chunk_cells <= 256:
        raise ValueError('Cell chunk budget must be 1..256')
    if type(maximum_cells) is not int or not 1 <= maximum_cells <= 40000:
        raise ValueError('Cell count budget must be 1..40000')
    if type(maximum_output_bytes) is not int or not 1 <= maximum_output_bytes <= 224*1024**2:
        raise ValueError('Output byte budget must be at most 224 MiB')
    arrays = (N, grad, weights, uq, gu, w)
    if any(not isinstance(a, np.ndarray) or a.dtype != np.dtype('float64') for a in arrays):
        raise ValueError('Existing float64 NumPy arrays required; implicit full-array copies are forbidden')
    if N.ndim != 2 or N.shape[1] != 10 or not 1 <= len(N) <= 216:
        raise ValueError('Bounded quadrature by ten P2 basis values required')
    if weights.ndim != 2 or weights.shape[1] != len(N) or not 1 <= len(weights) <= maximum_cells:
        raise ValueError('Bounded aligned cell/quadrature weights required')
    cells, points = weights.shape
    if (grad.shape != (cells, points, 10, 3) or uq.shape != (cells, points, 3)
            or w.shape != uq.shape or gu.shape != (cells, points, 3, 3)):
        raise ValueError('Aligned P2 volume field and gradient shapes required')
    output_bytes = cells*(200+900*jacobian)*8
    if output_bytes > maximum_output_bytes:
        raise ValueError('Volume contraction output byte budget exceeded')
    if not np.isfinite(N).all():
        raise ValueError('Finite basis values required')
    # Validate in bounded slices before allocating outputs; no full grad mask.
    for lo in range(0, cells, chunk_cells):
        hi = min(lo+chunk_cells, cells)
        if any(not np.isfinite(a[lo:hi]).all() for a in arrays[1:]) or np.any(weights[lo:hi] <= 0):
            raise ValueError('Finite volume fields and positive quadrature weights required')
    skew = np.empty((cells, 10, 10))
    mass = np.empty_like(skew)
    extra = np.empty((cells, 10, 3, 10, 3)) if jacobian else None
    pairs = (N[:, :, None]*N[:, None, :]).reshape(points, 100).T if jacobian else None
    for lo in range(0, cells, chunk_cells):
        hi = min(lo+chunk_cells, cells)
        count = hi-lo
        g, weight = grad[lo:hi], weights[lo:hi]
        adv = np.einsum('cqb,cqjb->cqj', w[lo:hi], g)
        transport = N.T@(adv*weight[:, :, None])
        skew[lo:hi] = .5*rho*(transport-transport.swapaxes(1, 2))
        mass[lo:hi] = N.T@(weight[:, :, None]*N)
        if jacobian:
            # (i,j),q times q,(a,b), then restore c,i,a,j,b.
            weighted_gradient = (gu[lo:hi]*weight[:, :, None, None]).reshape(count, points, 9)
            first = (pairs@weighted_gradient).reshape(count, 10, 10, 3, 3).transpose(0, 1, 3, 2, 4)
            extra[lo:hi] = first
            del weighted_gradient, first
            # (i,b),q times q,(j,a), then exchange the component axes.
            weighted_velocity_basis = ((uq[lo:hi]*weight[:, :, None])[:, :, None, :]
                                       *N[None, :, :, None]).reshape(count, points, 30)
            second = (g.transpose(0, 2, 3, 1).reshape(count, 30, points)
                      @weighted_velocity_basis).reshape(count, 10, 3, 10, 3).transpose(0, 1, 4, 3, 2)
            extra[lo:hi] -= second
            extra[lo:hi] *= .5*rho
            del weighted_velocity_basis, second
        if (not np.isfinite(skew[lo:hi]).all() or not np.isfinite(mass[lo:hi]).all()
                or (jacobian and not np.isfinite(extra[lo:hi]).all())):
            raise ValueError('Volume contractions exceed finite numerical range')
    return skew, mass, extra
