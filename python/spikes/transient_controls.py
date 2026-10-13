# SPDX-License-Identifier: Apache-2.0
"""Bounded output and integration grids for internal transient analyses."""

from __future__ import annotations

import bisect
import math
from typing import Any, Mapping


MAX_TRANSIENT_POINTS = 1_000_000


def _ratio_count(span_s: float, step_s: float, *, include_partial: bool) -> int:
    ratio = span_s / step_s
    if not math.isfinite(ratio):
        raise ValueError("Transient time grid is not finite.")
    nearest = round(ratio)
    tolerance = 16.0 * math.ulp(max(abs(ratio), 1.0))
    intervals = nearest if abs(ratio - nearest) <= tolerance else (
        math.ceil(ratio) if include_partial else math.floor(ratio)
    )
    return int(intervals)


def effective_integration_step_s(
    output_step_s: float,
    stop_time_s: float,
    maximum_time_step_s: float | None,
) -> tuple[float, int]:
    """Return a fixed integration step that reaches TSTOP and does not exceed TMAX."""

    limit = min(output_step_s, maximum_time_step_s or output_step_s)
    intervals = transient_integration_point_count(
        output_step_s, stop_time_s, maximum_time_step_s
    ) - 1
    if intervals + 1 > MAX_TRANSIENT_POINTS:
        raise ValueError(
            f"Transient integration exceeds {MAX_TRANSIENT_POINTS} points."
        )
    endpoint_tolerance = 16.0 * math.ulp(max(abs(stop_time_s), 1.0e-300))
    step = (
        limit
        if abs(intervals * limit - stop_time_s) <= endpoint_tolerance
        else stop_time_s / intervals
    )
    if step > limit and not math.isclose(step, limit, rel_tol=2.0e-15, abs_tol=0.0):
        intervals += 1
        if intervals + 1 > MAX_TRANSIENT_POINTS:
            raise ValueError(
                f"Transient integration exceeds {MAX_TRANSIENT_POINTS} points."
            )
        step = stop_time_s / intervals
    return step, intervals + 1


def transient_integration_point_count(
    output_step_s: float,
    stop_time_s: float,
    maximum_time_step_s: float | None,
) -> int:
    """Count an integration grid without allocating or applying a history cap."""

    limit = min(output_step_s, maximum_time_step_s or output_step_s)
    return max(1, _ratio_count(stop_time_s, limit, include_partial=True)) + 1


def output_times_s(
    output_step_s: float,
    start_time_s: float,
    stop_time_s: float,
) -> tuple[float, ...]:
    """Build the retained TSTART-based output grid and include TSTOP exactly."""

    intervals = _ratio_count(
        stop_time_s - start_time_s, output_step_s, include_partial=False
    )
    count_without_partial = intervals + 1
    last = start_time_s + intervals * output_step_s
    tolerance = 16.0 * math.ulp(max(abs(stop_time_s), abs(last), 1.0e-300))
    append_stop = abs(last - stop_time_s) > tolerance
    count = count_without_partial + int(append_stop)
    if count > MAX_TRANSIENT_POINTS:
        raise ValueError(f"Transient output exceeds {MAX_TRANSIENT_POINTS} points.")
    result = tuple(start_time_s + index * output_step_s for index in range(count_without_partial))
    if append_stop:
        result += (stop_time_s,)
    elif result:
        result = result[:-1] + (stop_time_s,)
    return result


def _interpolate_series(
    source_times: tuple[float, ...], values: Any, target_times: tuple[float, ...]
) -> list[float]:
    if len(values) != len(source_times):
        raise ValueError("Transient result series does not match its time grid.")
    result: list[float] = []
    for target in target_times:
        upper = bisect.bisect_left(source_times, target)
        if upper == 0:
            result.append(float(values[0]))
            continue
        if upper == len(source_times):
            tolerance = 16.0 * math.ulp(max(abs(target), abs(source_times[-1]), 1.0e-300))
            if target > source_times[-1] + tolerance:
                raise ValueError("Transient integration did not reach the requested output time.")
            result.append(float(values[-1]))
            continue
        right_time = source_times[upper]
        tolerance = 16.0 * math.ulp(max(abs(target), abs(right_time), 1.0e-300))
        if abs(right_time - target) <= tolerance:
            result.append(float(values[upper]))
            continue
        lower = upper - 1
        left_time = source_times[lower]
        fraction = (target - left_time) / (right_time - left_time)
        result.append(float(values[lower]) + fraction * (float(values[upper]) - float(values[lower])))
    return result


def retain_transient_outputs(
    data: Mapping[str, Any], target_times: tuple[float, ...]
) -> dict[str, Any]:
    """Return transient data linearly sampled on the explicit output grid."""

    source_times = tuple(float(value) for value in data.get("time_s", ()))
    if not source_times or any(
        right <= left for left, right in zip(source_times, source_times[1:])
    ):
        raise ValueError("Transient integration returned an invalid time grid.")
    sampled_times: list[float] = []
    for target in target_times:
        upper = bisect.bisect_left(source_times, target)
        candidates = source_times[max(0, upper - 1):min(len(source_times), upper + 1)]
        snapped = target
        for candidate in candidates:
            tolerance = 16.0 * math.ulp(max(abs(target), abs(candidate), 1.0e-300))
            if abs(candidate - target) <= tolerance:
                snapped = candidate
                break
        sampled_times.append(snapped)
    result = dict(data)
    result["time_s"] = sampled_times
    for key in (
        "node_voltage_v",
        "branch_current_a",
        "element_current_a",
        "element_power_w",
    ):
        table = data.get(key)
        if isinstance(table, Mapping):
            result[key] = {
                str(name): _interpolate_series(source_times, values, target_times)
                for name, values in table.items()
            }
    return result


__all__ = [
    "MAX_TRANSIENT_POINTS",
    "effective_integration_step_s",
    "output_times_s",
    "retain_transient_outputs",
    "transient_integration_point_count",
]
