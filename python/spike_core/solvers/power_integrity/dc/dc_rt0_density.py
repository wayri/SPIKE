# SPDX-License-Identifier: Apache-2.0
"""Unique-triangle-volume RT0 vector-density observable, not a branch histogram.

Signed outward integrated face currents reconstruct K=sum(q_i*(x-v_i))/(2A)
in A/mm. J=K/t is in A/mm2. Degree-two quadrature gives exact local Joule
loss. The percentile enclosure bounds every point of every physical triangle;
no low-current or undriven volume is discarded. See docs/DC_RT0_DENSITY.md.
"""
from __future__ import annotations

import numpy as np


def _geometry(triangles, flux, thickness):
    triangles = np.asarray(triangles,dtype=float)
    flux = np.asarray(flux,dtype=float)
    thickness = np.broadcast_to(np.asarray(thickness,dtype=float),(len(triangles),))
    if (triangles.ndim != 3 or triangles.shape[1:] != (3,2)
            or flux.shape != (len(triangles),3) or not len(triangles)
            or not np.isfinite(triangles).all() or not np.isfinite(flux).all()
            or not np.isfinite(thickness).all() or np.any(thickness <= 0)):
        raise ValueError("Density needs finite CCW triangles, three signed face fluxes and positive thickness")
    with np.errstate(over="ignore",invalid="ignore",under="ignore"):
        relative = triangles-triangles[:,:1]
        area2 = relative[:,1,0]*relative[:,2,1]-relative[:,1,1]*relative[:,2,0]
        edge_squared = np.sum(relative[:,1:]**2,axis=2).max(axis=1)
    if (not np.isfinite(relative).all() or not np.isfinite(area2).all()
            or not np.isfinite(edge_squared).all() or np.any(area2 <= 0)
            or np.any(edge_squared/area2 > 1e5)):
        raise ValueError("Density rejects reversed, degenerate, ill-shaped or overflowed triangles")
    return triangles,flux,thickness,relative,area2


def reconstruct_rt0_density(triangles_mm, outward_flux_a, thickness_mm):
    """Return vertex J values; they define the complete affine RT0 field."""
    _,flux,thickness,relative,area2 = _geometry(triangles_mm,outward_flux_a,thickness_mm)
    with np.errstate(over="ignore",invalid="ignore",divide="ignore",under="ignore"):
        denominator = area2*thickness
        vectors = (relative*flux.sum(axis=1)[:,None,None]
                -np.einsum("ti,tik->tk",flux,relative)[:,None,:])/denominator[:,None,None]
    if not np.isfinite(vectors).all() or not np.isfinite(denominator).all() or np.any(denominator <= 0):
        raise ValueError("RT0 density reconstruction overflowed or underflowed physical volume")
    return vectors


def rt0_dissipation_w(triangles_mm, outward_flux_a, thickness_mm, conductivity_s_m):
    triangles,flux,thickness,_,area2 = _geometry(triangles_mm,outward_flux_a,thickness_mm)
    sigma = np.broadcast_to(np.asarray(conductivity_s_m,dtype=float),(len(triangles),))
    if not np.isfinite(sigma).all() or np.any(sigma <= 0):
        raise ValueError("Density dissipation needs finite positive conductivity")
    vertices = reconstruct_rt0_density(triangles,flux,thickness)
    barycentric = np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
    with np.errstate(over="ignore",invalid="ignore",divide="ignore",under="ignore"):
        values = np.einsum("qi,tik->tqk",barycentric,vertices)
        # J[A/mm2]^2 * dV[mm3] / sigma[S/m] -> 1000 W.
        loss = (np.einsum("tqk,tqk->t",values,values)/6)*area2*thickness*(1000/sigma)
    if (not np.isfinite(loss).all()
            or np.any((loss == 0) & np.any(vertices != 0,axis=(1,2)))):
        raise ValueError("RT0 density dissipation overflowed or underflowed")
    return loss


def _percentile(values, weights, quantile):
    order = np.argsort(values,kind="stable")
    if values[order[0]] == values[order[-1]]:
        return float(values[order[0]])
    with np.errstate(over="ignore",invalid="ignore"):
        cumulative = np.cumsum(weights[order])
    if not np.isfinite(cumulative).all():
        raise ValueError("Density cumulative physical-volume sum overflowed")
    threshold = quantile*cumulative[-1]
    index = min(np.searchsorted(cumulative,threshold,side="left"),len(order)-1)
    # Positive summation: gamma_n bounds cumulative relative roundoff. Use
    # epsilon (twice unit roundoff) and a further factor two for the prefix,
    # total and threshold product, including subnormal absolute roundoff.
    count = len(weights)
    epsilon = np.finfo(float).eps
    gamma = (count+4)*epsilon/(1-(count+4)*epsilon)
    uncertainty = 2*gamma*cumulative[-1] + (2*count+8)*np.nextafter(0.,1.)
    upper_distance = cumulative[index]-threshold
    lower_distance = threshold-(cumulative[index-1] if index else 0.)
    if upper_distance > uncertainty and lower_distance > uncertainty:
        return float(values[order[index]])
    # A tiny weight uncertainty can move the quantile across a finite jump.
    # Resolve ambiguous ranks using exact integers for the supplied binary64
    # weights and quantile, not a tolerance, fsum, or extended-precision guess.
    numerator, shift = 0, 0
    for weight in weights:
        part, denominator = float(weight).as_integer_ratio()
        exponent = denominator.bit_length()-1
        if exponent > shift:
            numerator <<= exponent-shift
            shift = exponent
        numerator += part << (shift-exponent)
    q_num, q_den = float(quantile).as_integer_ratio()
    exact_threshold = numerator*q_num
    prefix = 0
    for index in order:
        part, denominator = float(weights[index]).as_integer_ratio()
        prefix += part << (shift-(denominator.bit_length()-1))
        if prefix*q_den >= exact_threshold:
            return float(values[index])
    raise ValueError("Density exact quantile rank was not resolved")


def _bounds(vectors):
    with np.errstate(over="ignore",invalid="ignore"):
        center = (vectors/3).sum(axis=1)
        magnitude = np.hypot(center[:,0],center[:,1])
        delta = vectors-center[:,None,:]
        radius = np.max(np.hypot(delta[:,:,0],delta[:,:,1]),axis=1)
        lower = np.maximum(0.,magnitude-radius)
        upper = np.max(np.hypot(vectors[:,:,0],vectors[:,:,1]),axis=1)
    if not np.isfinite(lower).all() or not np.isfinite(upper).all():
        raise ValueError("Density norm bounds overflowed")
    return lower,upper


def volume_percentile_enclosure(vertex_density_a_mm2, volumes_mm3, quantile=.95,
                                *, relative_tolerance=1e-6, absolute_tolerance=1e-10,
                                max_subcells=1000000):
    """Enclose the full-volume quantile of an affine vector norm.

    Triangle affine interpolation lies in the convex hull of its vertex
    vectors. The centroid-radius lower bound and vertex-norm upper bound
    therefore enclose every value. Weighted quantiles of these bounds enclose
    the true quantile. Refine only bound intervals touching that enclosure.
    Failure to meet the requested enclosure is explicit, never a silent pass.
    Disjoint physical support is a caller contract: vectors and volumes alone
    cannot certify it. The polygon compiler and RT0 assembler enforce ownership.
    """
    vectors = np.asarray(vertex_density_a_mm2,dtype=float)
    volumes = np.asarray(volumes_mm3,dtype=float)
    if (vectors.ndim != 3 or vectors.shape[1:] != (3,2) or not len(vectors)
            or volumes.shape != (len(vectors),) or not np.isfinite(vectors).all()
            or not np.isfinite(volumes).all() or np.any(volumes <= 0)
            or not np.isfinite(quantile) or not 0 < quantile < 1
            or not np.isfinite(relative_tolerance) or relative_tolerance <= 0
            or not np.isfinite(absolute_tolerance) or absolute_tolerance <= 0
            or isinstance(max_subcells,bool) or not isinstance(max_subcells,int)
            or not len(vectors) <= max_subcells <= 4000000):
        raise ValueError("Invalid full-volume density percentile input/budget")
    original_count = len(vectors)
    with np.errstate(over="ignore"):
        total_volume = float(volumes.sum())
    if not np.isfinite(total_volume):
        raise ValueError("Density physical-volume sum overflowed")
    for _ in range(32):
        low, high = _bounds(vectors)
        lower,upper = (_percentile(v,volumes,quantile) for v in (low,high))
        if upper-lower <= absolute_tolerance+relative_tolerance*upper:
            return {"quantile":quantile,"lower_a_mm2":lower,"upper_a_mm2":upper,
                "enclosure_width_a_mm2":upper-lower,"physical_volume_mm3":total_volume,
                "original_triangle_count":original_count,"quadrature_subcell_count":len(vectors),
                "converged":True}
        refine = (high >= lower) & (low <= upper) & (high-low > absolute_tolerance)
        if not np.any(refine) or len(vectors)+3*np.count_nonzero(refine) > max_subcells:
            raise ValueError(f"Density percentile enclosure budget exhausted: [{lower:g}, {upper:g}] A/mm2")
        selected = vectors[refine]
        a,b,c = selected[:,0],selected[:,1],selected[:,2]
        ab,bc,ca = a/2+b/2,b/2+c/2,c/2+a/2
        children = np.stack((np.stack((a,ab,ca),axis=1),np.stack((ab,b,bc),axis=1),
            np.stack((ca,bc,c),axis=1),np.stack((ab,bc,ca),axis=1)),axis=1).reshape(-1,3,2)
        vectors = np.concatenate((vectors[~refine],children))
        volumes = np.concatenate((volumes[~refine],np.repeat(volumes[refine]/4,4)))
        if np.any(volumes <= 0):
            raise ValueError("Density physical-volume subdivision underflowed")
    raise ValueError("Density percentile enclosure exceeds 32 refinement rounds")
