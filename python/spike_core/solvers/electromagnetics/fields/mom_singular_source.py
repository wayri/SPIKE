# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded Green-function moments for one planar triangular source.

This is an integration kernel, not an EFIE assembly or an EM solver. Coordinates
are metres and the time convention is exp(+i omega t), so the outgoing kernel
is exp(-i k R)/(4 pi R). The triangle fan cancels an on-surface 1/R singularity
analytically; it never substitutes a fictitious radius or drops a quadrature
point. A failed quadrature budget raises instead of returning a field result.

The coordinate transformation is independently derived from the triangle
Jacobian. The general singularity-removing principle is described by
https://doi.org/10.1137/0719090; no external implementation was inspected.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


class MomSourceIntegrationError(ValueError):
    """Invalid geometry, unresolved quadrature, or exceeded integration budget."""


@dataclass(frozen=True)
class TriangleGreenMoments:
    scalar_m: complex
    relative_first_m2: tuple[complex, complex, complex]
    scalar_error_m: float
    first_error_m2: float
    quadrature_order: int
    interaction: str
    converged: bool = True


def _vector3(value: object, name: str) -> np.ndarray:
    if isinstance(value, (list, tuple, np.ndarray)) and any(
        isinstance(component, (bool, np.bool_)) for component in value
    ):
        raise MomSourceIntegrationError(f"{name} requires real, non-boolean coordinates.")
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise MomSourceIntegrationError(f"{name} must contain three finite real coordinates.") from exc
    if array.shape != (3,) or array.dtype.kind not in "fiu":
        raise MomSourceIntegrationError(f"{name} must contain three finite real coordinates.")
    array = array.astype(float)
    if not np.isfinite(array).all() or np.max(np.abs(array)) > 1e12:
        raise MomSourceIntegrationError(f"{name} is non-finite or exceeds the coordinate budget.")
    return array


def _anchor_on_triangle(vertices: np.ndarray, observation: np.ndarray, normal: np.ndarray) -> np.ndarray:
    """Closest source-local point to the observation on a closed triangle."""
    a, b, c = vertices
    projection = observation - float(np.dot(normal, observation - a)) * normal
    ab, ac, ap = b - a, c - a, projection - a
    aa, bb, cc = float(ab @ ab), float(ab @ ac), float(ac @ ac)
    rhs = np.array([float(ap @ ab), float(ap @ ac)])
    try:
        u, v = np.linalg.solve(np.array([[aa, bb], [bb, cc]]), rhs)
    except np.linalg.LinAlgError as exc:
        raise MomSourceIntegrationError("Triangle barycentric projection is ill-conditioned.") from exc
    if u >= 0. and v >= 0. and u + v <= 1.:
        return projection
    candidates = []
    for start, end in ((a, b), (b, c), (c, a)):
        direction = end - start
        fraction = max(0., min(1., float((observation - start) @ direction) / float(direction @ direction)))
        candidates.append(start + fraction * direction)
    return min(candidates, key=lambda point: float((point - observation) @ (point - observation)))


def _integrate_order(vertices: np.ndarray, observation: np.ndarray, anchor: np.ndarray, wave_number: float, order: int) -> tuple[complex, np.ndarray]:
    nodes, weights = np.polynomial.legendre.leggauss(order)
    nodes, weights = (nodes + 1.) * .5, weights * .5
    u, v = np.meshgrid(nodes, nodes, indexing="ij")
    w = (weights[:, None] * weights[None, :]).ravel()
    u, v = u.ravel(), v.ravel()
    scalar = 0j
    moment = np.zeros(3, dtype=complex)
    for index in range(3):
        a = vertices[index] - anchor
        b = vertices[(index + 1) % 3] - anchor
        double_area = float(np.linalg.norm(np.cross(a, b)))
        if double_area == 0.:
            continue
        # When the anchor is the perpendicular projection onto the source
        # plane, integrate the 1/R radial factor exactly. This also resolves
        # a source observation arbitrarily close to that plane without a
        # distance floor or an impractically dense radial quadrature.
        projected_inside = (
            float(np.linalg.norm(anchor - observation)) < max(float(np.linalg.norm(a)), float(np.linalg.norm(b)))
            and abs(float((anchor - observation) @ a)) <= 1e-12 * float(a @ a)
            and abs(float((anchor - observation) @ b)) <= 1e-12 * float(b @ b)
        )
        if projected_inside:
            directions = (1. - nodes[:, None]) * a + nodes[:, None] * b
            radii = np.linalg.norm(directions, axis=1)
            if (radii <= 0.).any():
                raise MomSourceIntegrationError("Triangle fan has an unresolved zero-length ray.")
            height = float(np.linalg.norm(anchor - observation))
            radial_scalar = 1. / (np.hypot(height, radii) + height)
            radial_first = (radii * np.hypot(height, radii) - height * height * np.arcsinh(radii / height)) / (2. * radii**3) if height > 0. else 1. / (2. * radii)
            factor = weights * double_area / (4. * math.pi)
            scalar += complex(np.sum(factor * radial_scalar))
            moment += np.sum(factor[:, None] * ((anchor - observation)[None, :] * radial_scalar[:, None] + directions * radial_first[:, None]), axis=0)
            if wave_number == 0.:
                continue
        positions = anchor - observation + u[:, None] * ((1. - v[:, None]) * a + v[:, None] * b)
        distances = np.linalg.norm(positions, axis=1)
        if (distances <= 0.).any() or not np.isfinite(distances).all():
            raise MomSourceIntegrationError("Source distance is numerically unrepresentable.")
        oscillation = np.expm1(-1j * wave_number * distances) if projected_inside else np.exp(-1j * wave_number * distances)
        samples = w * (double_area / (4. * math.pi)) * (u / distances) * oscillation
        scalar += complex(np.sum(samples))
        moment += np.sum(samples[:, None] * positions, axis=0)
    if not math.isfinite(abs(scalar)) or not np.isfinite(moment).all():
        raise MomSourceIntegrationError("Green moments are numerically unrepresentable.")
    return scalar, moment


def integrate_triangle_green(
    vertices_m: object,
    observation_m: object,
    *,
    wave_number_rad_m: float = 0.,
    max_order: int = 32,
    relative_tolerance: float = 1e-8,
) -> TriangleGreenMoments:
    """Integrate G and (r'-observation)G over an explicit triangle.

    The returned scalar and first moment have units m and m^2. Three or more
    increasing tensor-Gauss orders must agree within a geometry-scaled budget.
    Near/singular interactions that exhaust the order budget are rejected.
    This kernel alone does not establish double-integral or MoM accuracy.
    """
    try:
        if any(isinstance(component, (bool, np.bool_)) for row in vertices_m for component in row):
            raise MomSourceIntegrationError("vertices_m requires real, non-boolean coordinates.")
    except (TypeError, ValueError) as exc:
        raise MomSourceIntegrationError("vertices_m must contain three finite 3D points.") from exc
    try:
        raw = np.asarray(vertices_m)
    except (TypeError, ValueError) as exc:
        raise MomSourceIntegrationError("vertices_m must contain three finite 3D points.") from exc
    if raw.shape != (3, 3):
        raise MomSourceIntegrationError("vertices_m must contain three finite 3D points.")
    vertices = np.stack([_vector3(row, "vertex") for row in raw])
    observation = _vector3(observation_m, "observation_m")
    if isinstance(wave_number_rad_m, bool) or not isinstance(wave_number_rad_m, (int, float)) or not math.isfinite(wave_number_rad_m) or wave_number_rad_m < 0:
        raise MomSourceIntegrationError("wave_number_rad_m must be finite and non-negative.")
    if isinstance(max_order, bool) or not isinstance(max_order, int) or max_order not in (12, 16, 24, 32):
        raise MomSourceIntegrationError("max_order must be 12, 16, 24 or 32.")
    if isinstance(relative_tolerance, bool) or not isinstance(relative_tolerance, (int, float)) or not math.isfinite(relative_tolerance) or not 1e-13 <= relative_tolerance <= 1e-3:
        raise MomSourceIntegrationError("relative_tolerance must be between 1e-13 and 1e-3.")
    # Form edge vectors before subtracting a distant observation. Subtracting
    # the observation first can erase small source edges and falsely converge.
    local = vertices - vertices[0]
    observation_local = observation - vertices[0]
    edges = np.array([local[1] - local[0], local[2] - local[1], local[0] - local[2]])
    scale = float(np.max(np.linalg.norm(edges, axis=1)))
    cross = np.cross(edges[0], -edges[2])
    double_area = float(np.linalg.norm(cross))
    if not math.isfinite(scale) or not math.isfinite(double_area) or scale <= 0 or double_area <= 1e-13 * scale * scale:
        raise MomSourceIntegrationError("Triangle is degenerate or too ill-conditioned.")
    if wave_number_rad_m * scale > 24.:
        raise MomSourceIntegrationError("Electrical size exceeds the source-quadrature budget; refine the triangle.")
    if wave_number_rad_m * float(np.max(np.linalg.norm(local - observation_local, axis=1))) > 1e6:
        raise MomSourceIntegrationError("Absolute Green phase exceeds the numerical-range budget.")
    anchor = _anchor_on_triangle(local, observation_local, cross / double_area)
    distance = float(np.linalg.norm(anchor - observation_local))
    interaction = "on_surface" if distance <= 1e-13 * scale else "near" if distance < scale else "separated"
    orders = [order for order in (4, 8, 12, 16, 24, 32) if order <= max_order]
    previous = None
    previous_error = None
    for order in orders:
        value = _integrate_order(local, observation_local, anchor, float(wave_number_rad_m), order)
        if previous is not None:
            scalar_error = abs(value[0] - previous[0])
            first_error = float(np.linalg.norm(value[1] - previous[1]))
            scaled_scalar_budget = relative_tolerance * max(abs(value[0]), scale * 1e-12)
            scaled_first_budget = relative_tolerance * max(float(np.linalg.norm(value[1])), scale * scale * 1e-12)
            error = max(scalar_error / scaled_scalar_budget, first_error / scaled_first_budget)
            if previous_error is not None and error <= 1. and previous_error <= 10. and error <= max(previous_error * 1.1, 1e-4):
                return TriangleGreenMoments(value[0], tuple(complex(v) for v in value[1]), scalar_error, first_error, order, interaction)
            previous_error = error
        previous = value
    raise MomSourceIntegrationError("Green moments did not converge within the bounded quadrature order.")
