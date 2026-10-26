# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original, bounded free-space radiation postprocessor for supplied RWG currents.

NOT a field/scattering solver, PEC-current model, mesh-convergence proof, or
compliance assessment. Full RWGs are dimensionless; coefficients and J_s are
A/m, coordinates m. With exp(+i*omega*t) and outgoing exp(-i*k*r), define
F(s) = integral J_s(x) exp(+i*k*s.x) dS [A*m]. The returned electric amplitude
E_inf = -i*omega*mu0/(4*pi) (F - s*(s.F)) [V] satisfies
E(r*s) ~ exp(-i*k*r)*E_inf/r [V/m]. No finite-range field is calculated.
For scattered currents caused by the stated plane-wave illumination ONLY,
total-polarization bistatic sigma = 4*pi*|E_inf|^2/|E_inc|^2 [m^2]. Incident
propagation direction is metadata, not an inferred excitation or current solve.

Derivation: expand |r*s-x|=r-s.x in the outgoing vector-potential Green
function and retain the transverse -i*omega*A radiation term. A Duffy map
to the unit square with Jacobian 2*area*(1-u) integrates the affine RWGs
using tensor Gauss-Legendre rules. Successive doubled orders estimate
quadrature change, NOT a certified error bound. Requiring final order >=
maximum triangle phase span reduces under-resolution, not aliasing proof.
Cancellation makes relative error unreliable at nulls; an explicit absolute
tolerance [A*m] therefore participates in admission. Current discretization,
charge continuity, material applicability and source accuracy remain untested.

Primary method sources (equations/invariants only; no external code inspected):
https://doi.org/10.1109/TAP.1982.1142818 (full triangular-surface current basis)
https://web.mit.edu/6.013_book/www/chapter12/Backup/12.4.html
https://physics.nist.gov/cuu/pdf/all.pdf (2022 CODATA constants)
Independent oracles: affine RWG integral l*(free_minus-free_plus)/3 and
normal observation of a planar patch (constant phase), plus rigid transforms,
scale covariance and Fourier conjugate symmetry. Implementation and fixtures
are independently authored SPIKE material. Human numerical review required.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import numbers

import numpy as np

from .mom_surface_basis import SurfaceBasis, SurfaceBasisError, build_surface_basis, evaluate

SPEED_OF_LIGHT_M_PER_S = 299_792_458.0
# 2022 CODATA recommended value. The uncertainty is immaterial at this
# experimental quadrature tolerance but 4*pi*1e-7 is no longer exact in SI.
VACUUM_PERMEABILITY_H_PER_M = 1.256_637_061_27e-6
MAX_FACES = 4096
MAX_EDGES = 2048
MAX_DIRECTIONS = 128
MAX_QUADRATURE_ORDER = 32
MAX_POINT_DIRECTION_EVALUATIONS = 2_000_000
MAX_ABSOLUTE_PHASE_RAD = 1e6


class FarFieldError(ValueError):
    """Invalid, numerically unsafe, or over-budget supplied-current request."""


@dataclass(frozen=True)
class FarFieldResult:
    frequency_hz: float
    observation_directions: tuple[tuple[float, float, float], ...]
    radiation_integral_am: tuple[tuple[complex, complex, complex], ...]
    electric_amplitude_v: tuple[tuple[complex, complex, complex], ...]
    quadrature_orders: tuple[int, ...]
    absolute_quadrature_change_am: tuple[float, ...]
    relative_quadrature_change: tuple[float, ...]
    point_direction_evaluations: int
    quadrature_converged: bool
    numerical_status: str
    model_status: str = "not_validated"
    executable_em_solver: bool = False
    scattering_solution_validated: bool = False


@dataclass(frozen=True)
class BistaticRcsResult:
    far_field: FarFieldResult
    incident_propagation_direction: tuple[float, float, float]
    incident_e_amplitude_v_per_m: float
    rcs_m2: tuple[float, ...] | None
    model_status: str = "not_validated"
    scattering_solution_validated: bool = False


def _positive_real(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real):
        raise FarFieldError(f"{name} must be a positive finite real number.")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise FarFieldError(f"{name} is not representable.") from exc
    if not math.isfinite(value) or value <= 0:
        raise FarFieldError(f"{name} must be a positive finite real number.")
    return value


def _order(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        raise FarFieldError(f"{name} must be an integer.")
    if not 2 <= value <= MAX_QUADRATURE_ORDER:
        raise FarFieldError(f"{name} exceeds the quadrature order budget.")
    return int(value)


def _directions(value):
    try:
        if not 1 <= len(value) <= MAX_DIRECTIONS:
            raise FarFieldError("Observation direction count exceeds budget.")
        arr = np.asarray(value)
        if arr.shape != (len(value), 3) or arr.dtype.kind not in "fiu":
            raise FarFieldError("Directions require real numeric triples.")
        # Mixed boolean lists would otherwise be silently coerced to integers.
        if any(isinstance(v, (bool, np.bool_)) for row in value for v in row):
            raise FarFieldError("Boolean directions are not admitted.")
        arr = arr.astype(float)
        if not np.isfinite(arr).all() or not np.allclose(np.linalg.norm(arr, axis=1), 1., atol=1e-12, rtol=0):
            raise FarFieldError("Directions must be finite unit vectors (tolerance 1e-12).")
        return arr
    except (TypeError, ValueError, OverflowError) as exc:
        raise FarFieldError(f"Invalid directions: {exc}") from exc


def _admit(surface, coefficients):
    if not isinstance(surface, SurfaceBasis):
        raise FarFieldError("surface must be a canonical SurfaceBasis.")
    try:
        if len(surface.triangles) > MAX_FACES or not 1 <= len(surface.edges) <= MAX_EDGES:
            raise FarFieldError("Surface face/edge count exceeds budget or has no RWGs.")
        if len(surface.vertices_m) > 3 * MAX_FACES:
            raise FarFieldError("Surface vertex count exceeds budget.")
        canonical = build_surface_basis(surface.vertices_m, surface.triangles)
        if canonical != surface:
            raise FarFieldError("SurfaceBasis geometry/topology metadata is inconsistent.")
        if len(coefficients) != len(surface.edges):
            raise FarFieldError("One current coefficient [A/m] is required per canonical RWG.")
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Complex) for v in coefficients):
            raise FarFieldError("Current coefficients must be real/complex numeric values.")
        result = np.asarray(coefficients, dtype=complex)
        if result.shape != (len(surface.edges),) or not np.isfinite(result).all():
            raise FarFieldError("Current coefficients must be a finite vector.")
        return result
    except (TypeError, ValueError, OverflowError, SurfaceBasisError) as exc:
        raise FarFieldError(f"Invalid supplied-current surface: {exc}") from exc


def _rule(order):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    nodes, weights = (nodes + 1) / 2, weights / 2
    u, v = np.meshgrid(nodes, nodes, indexing="ij")
    wu, wv = np.meshgrid(weights, weights, indexing="ij")
    return np.column_stack(((1-u).ravel()*(1-v).ravel(), u.ravel(), ((1-u)*v).ravel())), (2*wu*wv*(1-u)).ravel()


def _integrate(surface, coefficients, directions, k, order):
    bary, weights = _rule(order)
    origin = np.asarray(surface.vertices_m[0])
    xyz = np.asarray(surface.vertices_m) - origin
    total = np.zeros((len(directions), 3), dtype=complex)
    # O(edges*directions*order^2) work, O(directions*order^2 + vertices)
    # scratch storage. No edge-by-face or angle-by-surface dense allocation.
    for ei, edge in enumerate(surface.edges):
        for fi in (edge.plus_face, edge.minus_face):
            points = bary @ xyz[list(surface.triangles[fi])]
            current = evaluate(surface, ei, fi, bary) * coefficients[ei]
            phase = np.exp(1j * k * (directions @ points.T))
            total += (phase * weights) @ current * surface.areas_m2[fi]
    return total * np.exp(1j * k * (directions @ origin))[:, None]


def evaluate_far_field(surface: SurfaceBasis, coefficients_a_per_m, *, frequency_hz,
                       observation_directions, quadrature_order=4,
                       max_quadrature_order=16, relative_tolerance=1e-6,
                       absolute_tolerance_am=1e-12) -> FarFieldResult:
    """Evaluate supplied currents, recording doubled-order quadrature evidence.

    All directions must already be normalized. Orders are integers 2..32;
    max order must be a repeated doubling of the initial order, with at least
    two levels. The full worst-case work is preflighted before integration.
    Nonconvergence returns failed_to_converge, never a validated field.
    Absolute tolerance is on the full radiation integral, before projection.
    """
    coeff = _admit(surface, coefficients_a_per_m)
    directions = _directions(observation_directions)
    frequency = _positive_real(frequency_hz, "frequency_hz")
    rtol = _positive_real(relative_tolerance, "relative_tolerance")
    atol = _positive_real(absolute_tolerance_am, "absolute_tolerance_am")
    initial, maximum = _order(quadrature_order, "quadrature_order"), _order(max_quadrature_order, "max_quadrature_order")
    orders = [initial]
    while orders[-1] < maximum:
        orders.append(orders[-1] * 2)
    if len(orders) < 2 or orders[-1] != maximum:
        raise FarFieldError("max_quadrature_order must be a larger repeated doubling of quadrature_order.")
    work = 2 * len(surface.edges) * len(directions) * sum(n*n for n in orders)
    if work > MAX_POINT_DIRECTION_EVALUATIONS:
        raise FarFieldError("Worst-case point-direction evaluation budget exceeded.")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            k = 2 * math.pi * frequency / SPEED_OF_LIGHT_M_PER_S
            if not math.isfinite(k) or k <= 0:
                raise FarFieldError("Wavenumber is not representable.")
            xyz = np.asarray(surface.vertices_m)
            absolute_phase = k * (directions @ xyz.T)
            if np.max(np.abs(absolute_phase)) > MAX_ABSOLUTE_PHASE_RAD:
                raise FarFieldError("Absolute phase exceeds numerical-range budget; move the coordinate origin.")
            span = max(float(np.ptp(absolute_phase[:, list(face)], axis=1).max()) for face in surface.triangles)
            if span > maximum:
                raise FarFieldError("Triangle phase span exceeds final quadrature order; refine the surface.")
            previous = _integrate(surface, coeff, directions, k, initial)
            performed, used = [initial], 2*len(surface.edges)*len(directions)*initial**2
            converged = False
            for order in orders[1:]:
                current = _integrate(surface, coeff, directions, k, order)
                change = np.linalg.norm(current-previous, axis=1)
                magnitude = np.linalg.norm(current, axis=1)
                relative = change / np.maximum(magnitude, atol)
                performed.append(order)
                used += 2*len(surface.edges)*len(directions)*order**2
                converged = bool(order >= span and np.all(change <= atol + rtol*magnitude))
                previous = current
                if converged:
                    break
            transverse = current - directions * np.sum(directions*current, axis=1)[:, None]
            electric = -1j * frequency * VACUUM_PERMEABILITY_H_PER_M / 2 * transverse
            if not all(np.isfinite(v).all() for v in (current, change, relative, electric)):
                raise FarFieldError("Radiation output is not representable.")
    except (FloatingPointError, OverflowError, SurfaceBasisError) as exc:
        raise FarFieldError("Far-field evaluation exceeds numerical range.") from exc
    triples = lambda value: tuple(tuple(v.item() for v in row) for row in value)
    return FarFieldResult(frequency, triples(directions), triples(current), triples(electric),
                          tuple(performed), tuple(float(v) for v in change),
                          tuple(float(v) for v in relative), used, converged,
                          "approximate" if converged else "failed_to_converge")


def evaluate_bistatic_rcs(surface: SurfaceBasis, coefficients_a_per_m, *, frequency_hz,
                          observation_directions, incident_propagation_direction,
                          incident_e_amplitude_v_per_m, **quadrature_options) -> BistaticRcsResult:
    """Normalize supplied scattered-current radiation; no scattering is solved.

    Incident direction points along propagation (monostatic observation is its
    negative). Scalar incident amplitude is the positive electric-phasor norm
    [V/m]. No polarization-resolved RCS is inferred. Currents must belong to
    this excitation; the evaluator cannot establish that provenance. RCS is
    withheld (None) when quadrature is unresolved, including exact nulls.
    """
    incident = _directions([incident_propagation_direction])[0]
    amplitude = _positive_real(incident_e_amplitude_v_per_m, "incident_e_amplitude_v_per_m")
    field = evaluate_far_field(surface, coefficients_a_per_m, frequency_hz=frequency_hz,
                               observation_directions=observation_directions, **quadrature_options)
    rcs = None
    if field.quadrature_converged:
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                normalized = np.asarray(field.electric_amplitude_v) / amplitude
                values = 4 * math.pi * np.sum(np.abs(normalized)**2, axis=1)
                if not np.isfinite(values).all():
                    raise FarFieldError("RCS is not representable.")
                rcs = tuple(float(v) for v in values)
        except FloatingPointError as exc:
            raise FarFieldError("RCS exceeds numerical range.") from exc
    return BistaticRcsResult(field, tuple(float(v) for v in incident), amplitude, rcs)
