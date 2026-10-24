# SPDX-License-Identifier: Apache-2.0
"""Unique-volume quantile enclosure for retained conservative tetra fields."""
import math
import numpy as np
from python.spike_core.dc_rt0_density import _percentile


def tetra_density_enclosure(vertex_density_a_m2, volumes_m3, quantile=.95):
    vectors = np.asarray(vertex_density_a_m2, dtype=float); volumes = np.asarray(volumes_m3, dtype=float)
    if (vectors.ndim != 3 or vectors.shape[1:] != (4, 3) or not len(vectors)
            or volumes.shape != (len(vectors),) or not np.isfinite(vectors).all()
            or not np.isfinite(volumes).all() or np.any(volumes <= 0)
            or type(quantile) not in (int, float) or not 0 < quantile < 1):
        raise ValueError("Invalid tetrahedral field/physical volume/quantile")
    centroid = (vectors/4).sum(axis=1)
    norms = np.hypot.reduce(vectors, axis=2)
    radius = np.hypot.reduce(vectors-centroid[:, None, :], axis=2).max(axis=1)
    lower = np.maximum(0., np.hypot.reduce(centroid, axis=1)-radius); upper = norms.max(axis=1)
    if not np.isfinite(lower).all() or not np.isfinite(upper).all(): raise ValueError("Tetra density bounds overflowed")
    lo, hi = (_percentile(value, volumes, quantile) for value in (lower, upper))
    if hi-lo > 1e-12+1e-6*hi: raise ValueError("Tetra density enclosure needs refinement; not accepted")
    total = math.fsum(volumes)
    if not math.isfinite(total): raise ValueError("Tetra density physical volume overflowed")
    return {"quantile": quantile, "lower_a_m2": lo, "upper_a_m2": hi,
            "enclosure_width_a_m2": hi-lo, "physical_volume_m3": total,
            "tetrahedron_count": len(vectors), "converged": True,
            "scope": "reconstructed affine RT0 field; spatial/model error remains separate"}
