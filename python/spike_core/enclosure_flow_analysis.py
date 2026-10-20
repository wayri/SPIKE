# SPDX-License-Identifier: Apache-2.0
"""Bounded probes and cell-exact traces of a supplied closed MAC field.

This is experimental reconstruction, not a momentum solve or physical
validation. See docs/validation/ENCLOSURE_FLOW_ANALYSIS_20261021.md.
"""
from collections.abc import Mapping
import hashlib
import json
import math
import numbers
import time

import numpy as np

from .enclosure_refinement import (
    EnclosureRefinementError, _as_numeric_array, _divergence,
    _validate_built_grid,
)


CONTRACT = "spike/enclosure-flow-analysis/v1"
RESULT_CONTRACT = "spike/enclosure-flow-analysis-result/v1"
_KEYS = {
    "contract", "grid", "fluid_mask", "face_velocity_m_s",
    "velocity_reference_frame", "probes_m", "seed_points_m", "controls",
}
_DEFAULTS = {
    "max_time_s": 1., "max_step_s": .05, "max_points_per_streamline": 512,
    "max_cell_events": 256, "max_total_points": 4096,
    "max_output_bytes": 2_000_000, "max_runtime_s": 10.,
}
_INTEGER_LIMITS = {
    "max_points_per_streamline": (2, 1024), "max_cell_events": (1, 1024),
    "max_total_points": (1, 8192), "max_output_bytes": (1024, 2_000_000),
}
_QUADRATURE = tuple(np.polynomial.legendre.leggauss(n) for n in (8, 16))
_EPS = np.finfo(float).eps


class EnclosureFlowAnalysisError(ValueError):
    """A malformed, unresolved, or unrepresentable reconstruction request."""


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise EnclosureFlowAnalysisError(f"{name} must be a finite real number")
    value = float(value)
    if not math.isfinite(value):
        raise EnclosureFlowAnalysisError(f"{name} must be finite")
    return value


def _controls(raw):
    if not isinstance(raw, Mapping) or set(raw) - set(_DEFAULTS):
        raise EnclosureFlowAnalysisError("controls contains unknown options")
    result = dict(_DEFAULTS, **raw)
    for key, (lower, upper) in _INTEGER_LIMITS.items():
        value = result[key]
        if type(value) is not int or not lower <= value <= upper:
            raise EnclosureFlowAnalysisError(f"{key} must be an integer in [{lower}, {upper}]")
    for key, upper in (("max_time_s", 1e6), ("max_step_s", 1e3), ("max_runtime_s", 30.)):
        result[key] = _number(result[key], key)
        if not 0. < result[key] <= upper:
            raise EnclosureFlowAnalysisError(f"{key} must be positive and at most {upper}")
    return result


class _Budget:
    def __init__(self, controls, cancel_check):
        self.controls = controls
        self.cancel_check = cancel_check
        self.deadline = time.monotonic() + controls["max_runtime_s"]
        self.points = 0
        self.point_bytes = 0

    def check(self):
        if self.cancel_check and self.cancel_check():
            raise InterruptedError("flow analysis cancelled")
        if time.monotonic() >= self.deadline:
            raise EnclosureFlowAnalysisError("wall-clock runtime budget exceeded")

    def add_point(self, point):
        self.check()
        self.points += 1
        self.point_bytes += len(json.dumps(point, separators=(",", ":"), allow_nan=False))
        if self.points > self.controls["max_total_points"]:
            raise EnclosureFlowAnalysisError("aggregate output point budget exceeded")
        if self.point_bytes > self.controls["max_output_bytes"]:
            raise EnclosureFlowAnalysisError("output byte budget exceeded")


def _locations(raw, name, maximum):
    if not isinstance(raw, (list, tuple)) or len(raw) > maximum:
        raise EnclosureFlowAnalysisError(f"{name} must contain at most {maximum} points")
    points = []
    for index, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise EnclosureFlowAnalysisError(f"{name}[{index}] must contain three coordinates")
        points.append(np.array([_number(x, name) for x in item]))
    return points


def _locate(axes, mask, point, *, seed):
    cell = []
    for axis, value in zip(axes, point):
        # Boundary values lack a unique three-component trace; neither probes
        # nor seeds are admitted on the exterior surface.
        if not axis[0] < value < axis[-1]:
            raise EnclosureFlowAnalysisError("point must lie strictly inside the domain")
        if seed and np.any(axis == value):
            raise EnclosureFlowAnalysisError("seed must not lie on a grid plane")
        cell.append(int(np.searchsorted(axis, value, side="right") - 1))
    cell = tuple(cell)
    if not mask[cell]:
        raise EnclosureFlowAnalysisError("point is not in a fluid cell")
    return cell


def _admit(request, budget):
    shape, _, axes, coarse_axes, _, widths, _ = _validate_built_grid(request["grid"])
    # The helper checks metrics, but a purported built object must also retain
    # every coarse cut and share its endpoints.
    for fine, coarse in zip(axes, coarse_axes):
        if (fine[0] != coarse[0] or fine[-1] != coarse[-1]
                or not np.isin(coarse, fine).all()):
            raise EnclosureFlowAnalysisError("grid does not preserve its coarse domain and cuts")
        centers = fine[:-1] + .5 * np.diff(fine)
        if np.any(centers <= fine[:-1]) or np.any(centers >= fine[1:]):
            raise EnclosureFlowAnalysisError("grid cell interiors are not safely representable")
    mask = np.asarray(request["fluid_mask"])
    if mask.dtype.kind != "b" or mask.shape != shape or not mask.any():
        raise EnclosureFlowAnalysisError("fluid_mask must be a nonempty Boolean grid array")
    raw = request["face_velocity_m_s"]
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise EnclosureFlowAnalysisError("face_velocity_m_s must contain three arrays")
    fields = []
    for axis in range(3):
        budget.check()
        face_shape = list(shape)
        face_shape[axis] += 1
        field = _as_numeric_array(raw[axis], f"face_velocity_m_s[{axis}]", tuple(face_shape))
        allowed = np.zeros(face_shape, dtype=bool)
        middle, lower, upper = [slice(None)] * 3, [slice(None)] * 3, [slice(None)] * 3
        middle[axis], lower[axis], upper[axis] = slice(1, -1), slice(None, -1), slice(1, None)
        allowed[tuple(middle)] = mask[tuple(lower)] & mask[tuple(upper)]
        if np.any(field[~allowed] != 0.):
            raise EnclosureFlowAnalysisError("closed exterior and solid face velocities must be exactly zero")
        fields.append(field.copy())
    divergence, _, _ = _divergence(fields, widths)
    velocity_scale = max(float(np.max(np.abs(f))) for f in fields)
    hmin = min(float(np.min(w)) for w in widths)
    scale = np.divide(velocity_scale, hmin)
    limit = np.multiply(1e-9, scale)
    maximum = float(np.max(np.abs(divergence[mask])))
    if not math.isfinite(float(limit)) or maximum > limit:
        raise EnclosureFlowAnalysisError("field divergence exceeds 1e-9 * max_face_speed / minimum_width")
    # Do not keep caller-owned arrays in a long-running postprocessor.
    return tuple(a.copy() for a in axes), mask.copy(), tuple(fields), divergence, maximum, float(limit)


def _cell_data(axes, fields, cell):
    low = np.array([axes[d][cell[d]] for d in range(3)])
    high = np.array([axes[d][cell[d] + 1] for d in range(3)])
    minus, plus = [], []
    for axis in range(3):
        upper = list(cell)
        upper[axis] += 1
        minus.append(fields[axis][cell])
        plus.append(fields[axis][tuple(upper)])
    minus, plus = np.array(minus), np.array(plus)
    return low, high, minus, plus, (plus - minus) / (high - low)


def _velocity(data, position):
    low, high, minus, plus, _ = data
    fraction = (position - low) / (high - low)
    if np.any(fraction < 0.) or np.any(fraction > 1.):
        raise EnclosureFlowAnalysisError("reconstruction point left its owning cell")
    return (1. - fraction) * minus + fraction * plus


def _speed(velocity):
    # hypot is scale-safe; sum(v*v) needlessly under/overflows.
    return math.hypot(*(float(v) for v in velocity))


def _exit_times(data, position, velocity):
    low, high, minus, plus, slope = data
    times = np.full(3, np.inf)
    for d in range(3):
        v = float(velocity[d])
        if v == 0.:
            continue
        target = high[d] if v > 0. else low[d]
        face_v = float(plus[d] if v > 0. else minus[d])
        # Equilibria and exactly zero wall-normal flux are reached only at
        # infinite time. There is no positional epsilon through a wall.
        if face_v == 0. or math.copysign(1., face_v) != math.copysign(1., v):
            continue
        distance = float(target - position[d])
        if slope[d] == 0.:
            value = distance / v
        else:
            difference = face_v - v
            if abs(difference) <= .5 * abs(v):
                ratio = difference / v
                # Express log1p(r)/b as (distance/v)*log1p(r)/r
                # to retain the constant-velocity limit when rounded r is zero.
                value = (distance / v) * (math.log1p(ratio) / ratio if ratio else 1.)
            else:
                value = (math.log(abs(face_v)) - math.log(abs(v))) / float(slope[d])
        if not math.isfinite(value) or value <= 0.:
            raise EnclosureFlowAnalysisError("cell-exit time is not safely representable")
        times[d] = value
    return times


def _advance(position, velocity, slope, dt):
    z = slope * dt
    factor = np.ones(3)
    nonzero = z != 0.
    factor[nonzero] = np.expm1(z[nonzero]) / z[nonzero]
    return position + (velocity * dt) * factor


def _arc_length(velocity, slope, dt):
    values = []
    for nodes, weights in _QUADRATURE:
        speeds = [_speed(velocity * np.exp(slope * (dt * (.5 + .5 * x)))) for x in nodes]
        values.append(float(np.multiply(dt, .5 * math.fsum(w * s for w, s in zip(weights, speeds)))))
    error = abs(values[1] - values[0])
    if not math.isfinite(values[1]) or error > 1e-10 * values[1]:
        raise EnclosureFlowAnalysisError("arclength quadrature criterion failed")
    return values[1], error


def _point(position, velocity, cell, elapsed, length):
    return {"position_m": position.tolist(), "velocity_m_s": velocity.tolist(),
            "speed_m_s": _speed(velocity), "cell_index": list(cell),
            "time_s": float(elapsed), "arclength_m": float(length)}


def _trace(axes, mask, fields, seed, controls, budget):
    cell = _locate(axes, mask, seed, seed=True)
    position = seed.copy()
    elapsed, length, error_sum, events = 0., 0., 0., 0
    data = _cell_data(axes, fields, cell)
    points = [_point(position, _velocity(data, position), cell, elapsed, length)]
    budget.add_point(points[0])
    reason = "time_limit"
    while elapsed < controls["max_time_s"]:
        budget.check()
        if len(points) >= controls["max_points_per_streamline"]:
            reason = "point_limit"
            break
        data = _cell_data(axes, fields, cell)
        velocity = _velocity(data, position)
        if np.all(velocity == 0.):
            reason = "stagnation"
            break
        exits = _exit_times(data, position, velocity)
        first_exit = float(np.min(exits))
        remaining = controls["max_time_s"] - elapsed
        slope = data[4]
        largest_slope = float(np.max(np.abs(slope)))
        # This cap controls exponential/quadrature dynamic range and output
        # sampling. It is not a CFD time step or an ODE truncation tolerance.
        dt = min(controls["max_step_s"], remaining, first_exit)
        if largest_slope and largest_slope > .5 / dt:
            dt = .5 / largest_slope
        next_time = elapsed + dt
        if dt <= 0. or next_time == elapsed:
            reason = "precision_limit"
            break
        next_position = _advance(position, velocity, slope, dt)
        is_exit = dt == first_exit
        crossing = []
        if is_exit:
            crossing = [d for d in range(3) if abs(float(exits[d]) - first_exit) <= 64 * _EPS * first_exit]
            for d in crossing:
                next_position[d] = data[1][d] if velocity[d] > 0. else data[0][d]
        if np.array_equal(next_position, position):
            reason = "precision_limit"
            break
        # Each coordinate is monotone until an event. A valid endpoint and
        # its display chord therefore stay in this same convex fluid cell.
        if np.any(next_position < data[0]) or np.any(next_position > data[1]):
            raise EnclosureFlowAnalysisError("rounded path endpoint left its cell before an event")
        # Reaching a non-exit boundary by rounding is not a license to cross it.
        touched = ((next_position == data[0]) | (next_position == data[1]))
        if any(touched[d] and position[d] != next_position[d] and d not in crossing for d in range(3)):
            reason = "precision_limit"
            break
        increment, estimate = _arc_length(velocity, slope, dt)
        next_length = float(np.add(length, increment))
        if increment <= 0. or next_length == length:
            reason = "precision_limit"
            break
        elapsed, length = next_time, next_length
        error_sum += estimate
        position = next_position
        point = _point(position, _velocity(data, position), cell, elapsed, length)
        budget.add_point(point)
        points.append(point)
        if is_exit:
            events += 1
            if len(crossing) != 1:
                reason = "ambiguous_cell_edge"
                break
            d = crossing[0]
            neighbor = list(cell)
            neighbor[d] += 1 if velocity[d] > 0. else -1
            if not 0 <= neighbor[d] < mask.shape[d]:
                reason = "domain_boundary"
                break
            if not mask[tuple(neighbor)]:
                reason = "solid_boundary"
                break
            if events >= controls["max_cell_events"]:
                reason = "event_limit"
                break
            cell = tuple(neighbor)
    return {"seed_m": seed.tolist(), "termination_reason": reason, "cell_events": events,
            "points": points, "arclength_m": length,
            "arclength_quadrature_error_estimate_m": error_sum}


def _digest(axes, mask, fields, probes, seeds, controls):
    digest = hashlib.sha256()
    digest.update(b"spike/flow-analysis-source/v1\0")
    for array in (*axes, mask, *fields):
        numeric = np.asarray(array, dtype="u1" if array.dtype.kind == "b" else "<f8")
        digest.update(json.dumps(list(numeric.shape)).encode("ascii"))
        digest.update(numeric.tobytes(order="C"))
    digest.update(json.dumps({
        "probes_m": [p.tolist() for p in probes], "seed_points_m": [p.tolist() for p in seeds],
        "controls": controls, "velocity_reference_frame": "stationary",
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii"))
    return digest.hexdigest()


def analyze_enclosure_flow(request, *, cancel_check=None):
    """Analyze an explicitly supplied stationary closed field, or fail closed.

    Completed means reconstruction completed to each stated stopping condition,
    not that a solver or a physical experiment verified the source field.
    """
    base = {"contract": RESULT_CONTRACT, "model_status": "experimental",
            "production_qualified": False, "source_data_kind": "supplied_shared_face_field",
            "velocity_reference_frame": "stationary",
            "reconstruction": "cellwise_rectangular_rt0",
            "limitations": [
                "Supplied-field admission is not momentum or physical verification.",
                "Only shared normal velocity is continuous; tangential traces can jump.",
                "Impermeability is preserved, but tangential no-slip is not reconstructed.",
                "No transverse gradients, vorticity, Q criterion, pressure, or thermal analysis.",
                "Curved paths are sampled at cell-contained endpoints; arclength is quadrature-estimated.",
            ]}
    try:
        if not isinstance(request, Mapping) or set(request) != _KEYS:
            raise EnclosureFlowAnalysisError("request has missing or unknown options")
        if request["contract"] != CONTRACT or request["velocity_reference_frame"] != "stationary":
            raise EnclosureFlowAnalysisError("only the stationary closed-field contract is supported")
        controls = _controls(request["controls"])
        budget = _Budget(controls, cancel_check)
        budget.check()
        probe_points = _locations(request["probes_m"], "probes_m", 64)
        seeds = _locations(request["seed_points_m"], "seed_points_m", 16)
        with np.errstate(over="raise", under="raise", invalid="raise", divide="raise"):
            axes, mask, fields, divergence, maximum, limit = _admit(request, budget)
            # Validate all seeds before allocating trace outputs.
            for seed in seeds:
                _locate(axes, mask, seed, seed=True)
            probes = []
            for position in probe_points:
                budget.check()
                cell = _locate(axes, mask, position, seed=False)
                point = _point(position, _velocity(_cell_data(axes, fields, cell), position), cell, 0., 0.)
                point["divergence_s_inv"] = float(divergence[cell])
                budget.add_point(point)
                probes.append(point)
            traces = [_trace(axes, mask, fields, seed, controls, budget) for seed in seeds]
            result = dict(base, status="completed", probes=probes, streamlines=traces,
                          source_digest_sha256=_digest(axes, mask, fields, probe_points, seeds, controls),
                          diagnostics={"max_divergence_s_inv": maximum,
                                       "divergence_admission_limit_s_inv": limit,
                                       "output_points": budget.points,
                                       "arclength_quadrature_relative_criterion": 1e-10,
                                       "arclength_error_kind": "8_vs_16_point_gauss_estimate_not_bound"})
            budget.check()
            if len(json.dumps(result, separators=(",", ":"), allow_nan=False).encode("ascii")) > controls["max_output_bytes"]:
                raise EnclosureFlowAnalysisError("output byte budget exceeded")
            return result
    except InterruptedError:
        return dict(base, status="cancelled", reason="flow analysis cancelled")
    except (EnclosureFlowAnalysisError, EnclosureRefinementError, FloatingPointError,
            OverflowError, TypeError, ValueError) as exc:
        return dict(base, status="blocked", reason=str(exc))
