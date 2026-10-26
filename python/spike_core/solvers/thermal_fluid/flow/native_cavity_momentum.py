# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Independent exact-arithmetic MAC momentum admission, not continuum validation.

The additional returned-field target is derived in
docs/validation/NATIVE_CAVITY_MOMENTUM_20261025.md. It does not reconstruct
rounding errors in the unavailable native predecessor/projection states.
"""
from fractions import Fraction
import math


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value):
    try:
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value))
    except OverflowError:
        return False


def _field(values, length):
    _require(isinstance(values, list) and len(values) == length
             and all(_finite(value) for value in values), "Invalid momentum field")
    return [Fraction(value) for value in values]


def _operators(n, reynolds, lid, face_u, face_v, pressure):
    """Exact dual-volume residuals over supplied rational fields.

    Caller owns field shape/finite admission. Scalar coefficients intentionally
    freeze the native binary h, nu and h*h conventions before exact evaluation.
    """
    h = 1. / n
    alpha = 1 / Fraction(h)
    beta = Fraction(1. / reynolds) / Fraction(h * h)

    def u(i, j):
        if j == -1:
            return -face_u[i]
        if j == n:
            return 2 * lid - face_u[(n - 1) * (n + 1) + i]
        return face_u[j * (n + 1) + i]

    def v(i, j):
        if i == -1:
            return -face_v[j * n]
        if i == n:
            return -face_v[j * n + n - 1]
        return face_v[j * n + i]

    amplitude = max(abs(value) for value in (*face_u, *face_v))
    for i in range(n + 1):
        amplitude = max(amplitude, abs(u(i, -1)), abs(u(i, n)))
    for j in range(n + 1):
        amplitude = max(amplitude, abs(v(-1, j)), abs(v(n, j)))
    horizontal, vertical = [], []
    for j in range(n):
        for i in range(1, n):
            center = u(i, j)
            neighbors = (u(i + 1, j), u(i - 1, j), u(i, j + 1), u(i, j - 1))
            east, west, north, south = ((center + value) / 2 for value in neighbors)
            flux = (east * east - west * west
                    + north * (v(i - 1, j + 1) + v(i, j + 1)) / 2
                    - south * (v(i - 1, j) + v(i, j)) / 2)
            diffusion = sum(value - center for value in neighbors)
            gradient = pressure[j * n + i] - pressure[j * n + i - 1]
            horizontal.append(beta * diffusion - alpha * (flux + gradient))
    for j in range(1, n):
        for i in range(n):
            center = v(i, j)
            neighbors = (v(i + 1, j), v(i - 1, j), v(i, j + 1), v(i, j - 1))
            east, west, north, south = ((center + value) / 2 for value in neighbors)
            flux = (north * north - south * south
                    + east * (u(i + 1, j - 1) + u(i + 1, j)) / 2
                    - west * (u(i, j - 1) + u(i, j)) / 2)
            diffusion = sum(value - center for value in neighbors)
            gradient = pressure[j * n + i] - pressure[(j - 1) * n + i]
            vertical.append(beta * diffusion - alpha * (flux + gradient))
    return horizontal, vertical, amplitude, alpha, beta


def validate_native_cavity_momentum(raw, s, scales):
    """Return independent diagnostics or reject inconsistent native momentum.

    Call after the existing schema, mass, pressure-gauge and cell/face checks.
    No returned claimed residual enlarges this independent acceptance target.
    """
    n, reynolds, lid = s["n"], scales["kernel_reynolds"], scales["lid"]
    tolerance, dt = s["steady_tolerance"], raw["flow_dt"]
    _require(type(n) is int and 8 <= n <= 64 and n % 4 == 0,
             "Unsupported momentum grid")
    _require(_finite(reynolds) and 1 <= reynolds <= 400
             and _finite(lid) and lid in (0, 1)
             and _finite(tolerance) and 1e-10 <= tolerance <= 1e-3,
             "Unsupported momentum controls")
    h, nu = 1. / n, 1. / reynolds
    ceiling = min(.15 * h * h / nu, .2 * h)
    _require(_finite(dt) and 0 < dt <= ceiling,
             "Native momentum timestep exceeds its universal ceiling")
    u = _field(raw["face_u"], n * (n + 1))
    v = _field(raw["face_v"], n * (n + 1))
    p = _field(raw["pressure"], n * n)
    _require(all(u[j * (n + 1)] == u[j * (n + 1) + n] == 0 for j in range(n))
             and all(v[i] == v[n * n + i] == 0 for i in range(n)),
             "Momentum wall normal is not zero")
    ru, rv, amplitude, alpha, beta = _operators(n, reynolds, Fraction(lid), u, v, p)
    residual = max(abs(value) for value in (*ru, *rv))
    step, tau = Fraction(dt), Fraction(tolerance)
    bound = tau * (1 + step * (8 * alpha * (amplitude + step * tau) + 8 * beta))
    # Compare exactly, without a guessed additive/multiplicative roundoff allowance.
    _require(residual <= bound, "Returned field fails independent momentum balance")
    try:
        residual_float, bound_float = float(residual), float(bound)
    except OverflowError as exc:
        raise ValueError("Unrepresentable independent momentum diagnostics") from exc
    _require(math.isfinite(residual_float) and math.isfinite(bound_float),
             "Nonfinite independent momentum diagnostics")
    return {"independent_momentum_residual_linf": residual_float,
            "independent_momentum_residual_limit": bound_float,
            "independent_momentum_verified": True,
            "independent_momentum_arithmetic": "exact_rational_binary_inputs"}
