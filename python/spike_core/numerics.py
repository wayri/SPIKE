"""Numerical quality helpers shared by quasi-static solver adapters."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np


def project_symmetric_positive(
    matrix: np.ndarray,
    *,
    absolute_floor: float = 1e-18,
    relative_floor: float = 1e-12,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Project a finite symmetric matrix onto the positive-definite cone.

    PEEC partial-element matrices should be passive. Imported overlapping
    primitives and line-filament quadrature can violate that property. The
    correction is returned as explicit quality metadata and must not be hidden
    as solver accuracy.
    """

    value = np.asarray(matrix, dtype=float)
    if value.ndim != 2 or value.shape[0] != value.shape[1] or value.size == 0:
        raise ValueError("the matrix must be non-empty and square")
    if not np.all(np.isfinite(value)):
        raise ValueError("the matrix contains non-finite values")
    symmetric = (value + value.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    spectral_scale = max(float(np.max(np.abs(eigenvalues), initial=0.0)), 1e-30)
    floor = max(spectral_scale * relative_floor, absolute_floor)
    negative = eigenvalues < -floor
    clipped = np.maximum(eigenvalues, floor)
    correction = clipped - eigenvalues
    projected = (eigenvectors * clipped) @ eigenvectors.T
    projected = (projected + projected.T) / 2.0
    return projected, {
        "negative_eigenmode_count": int(np.count_nonzero(negative)),
        "eigenmode_count": int(len(eigenvalues)),
        "minimum_eigenvalue": float(eigenvalues[0]),
        "maximum_eigenvalue": float(eigenvalues[-1]),
        "eigenvalue_floor": float(floor),
        "frobenius_correction_ratio": float(
            np.linalg.norm(correction) / max(np.linalg.norm(eigenvalues), 1e-30)
        ),
    }


def assess_symmetric_positive_semidefinite(
    matrix: np.ndarray,
    *,
    absolute_tolerance: float = 1e-18,
    relative_tolerance: float = 1e-12,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Validate a finite symmetric positive-semidefinite matrix without editing it.

    Ideal topology constraints can contribute exactly zero field energy, so a
    PEEC branch inductance matrix may be passive semidefinite rather than
    positive definite.  Unlike ``project_symmetric_positive``, this routine
    never supplies a numerical regularizer; callers must fail closed when a
    negative mode exceeds the stated scale-aware tolerance.
    """

    value = np.asarray(matrix, dtype=float)
    if value.ndim != 2 or value.shape[0] != value.shape[1] or value.size == 0:
        raise ValueError("the matrix must be non-empty and square")
    if not np.all(np.isfinite(value)):
        raise ValueError("the matrix contains non-finite values")
    symmetric = (value + value.T) / 2.0
    eigenvalues = np.linalg.eigvalsh(symmetric)
    spectral_scale = max(float(np.max(np.abs(eigenvalues), initial=0.0)), 1e-30)
    tolerance = max(spectral_scale * relative_tolerance, absolute_tolerance)
    return symmetric, {
        "negative_eigenmode_count": int(np.count_nonzero(eigenvalues < -tolerance)),
        "eigenmode_count": int(len(eigenvalues)),
        "minimum_eigenvalue": float(eigenvalues[0]),
        "maximum_eigenvalue": float(eigenvalues[-1]),
        "passivity_tolerance": float(tolerance),
        "frobenius_correction_ratio": 0.0,
        "projection_applied": False,
    }
