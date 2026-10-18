# SPDX-License-Identifier: Apache-2.0
"""Recorded-sample measurements shared by owned and reference runners.

This module has no solver imports. Numerical reduction policies remain explicit
at each caller; importing the owned-engine path does not initialize SciPy or
unrelated multiphysics providers.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from typing import Any, Mapping
from .contracts import CircuitProject, MeasureDirective, ProbeDescriptor


def _probe_value(probe: ProbeDescriptor, data: Mapping[str, Any]) -> float:
    if probe.quantity == "node_voltage":
        values = data.get("node_voltage_v", {})

        def voltage(node: str) -> float:
            return 0.0 if node == "0" else float(values[node])

        result = voltage(probe.targets[0])
        if len(probe.targets) == 2:
            result -= voltage(probe.targets[1])
        return result
    key = "element_current_a" if probe.quantity == "element_current" else "element_power_w"
    return float(data[key][probe.targets[0]])


def _measure_probe_values(probe: ProbeDescriptor, data: Mapping[str, Any]) -> float | list[float]:
    if "time_s" in data:
        count = len(data["time_s"])
    elif "sweep" in data:
        count = len(data["sweep"]["values"])
    else:
        return _probe_value(probe, data)
    return [
        _probe_value(probe, {
            "node_voltage_v": {name: values[index] for name, values in data["node_voltage_v"].items()},
            "element_current_a": {name: values[index] for name, values in data["element_current_a"].items()},
            "element_power_w": {name: values[index] for name, values in data["element_power_w"].items()},
        })
        for index in range(count)
    ]


def _one_measurement(
    measure: MeasureDirective,
    data: Mapping[str, Any],
    *,
    transient_weighting: str = "time",
) -> dict[str, Any]:
    values = _measure_probe_values(measure.probe, data)
    base: dict[str, Any] = {
        "status": "completed", "operation": measure.operation,
        "probe": measure.probe.to_dict(), "unit": measure.probe.unit,
    }
    if isinstance(values, float):
        return base | {"value": values}
    axis = list(data["time_s"] if measure.analysis == "tran" else data["sweep"]["values"])
    if measure.operation == "find":
        assert measure.at_value is not None
        at = measure.at_value
        if axis[0] > axis[-1]:
            axis.reverse()
            values.reverse()
        tolerance = max(abs(axis[0]), abs(axis[-1]), abs(at), 1.0) * 1.0e-12
        if at < axis[0] - tolerance or at > axis[-1] + tolerance:
            raise ValueError(f"AT={at:g} is outside the simulated axis.")
        if at <= axis[0] + tolerance:
            value = values[0]
        elif at >= axis[-1] - tolerance:
            value = values[-1]
        else:
            upper = next(index for index, coordinate in enumerate(axis) if coordinate >= at)
            if abs(axis[upper] - at) <= tolerance:
                value = values[upper]
            else:
                lower = upper - 1
                fraction = (at - axis[lower]) / (axis[upper] - axis[lower])
                value = values[lower] + fraction * (values[upper] - values[lower])
        return base | {"value": value, "at": at, "interpolation": "linear"}

    selected = list(range(len(axis)))
    if measure.from_value is not None:
        assert measure.to_value is not None
        selected = [
            index for index, coordinate in enumerate(axis)
            if measure.from_value <= coordinate <= measure.to_value
        ]
        base["window"] = {"from": measure.from_value, "to": measure.to_value}
    if measure.analysis == "tran" and transient_weighting == "time":
        if len(axis) < 2 or any(right <= left for left, right in zip(axis, axis[1:])):
            raise ValueError("Transient measurement requires a strictly increasing time axis.")
        start = axis[0] if measure.from_value is None else measure.from_value
        stop = axis[-1] if measure.to_value is None else measure.to_value
        if start < axis[0] or stop > axis[-1] or start >= stop:
            raise ValueError("Measurement window must have positive duration within the simulated axis.")
        def interpolate(time: float) -> float:
            upper = bisect_left(axis, time)
            if upper < len(axis) and axis[upper] == time:
                return values[upper]
            lower = upper - 1
            fraction = (time-axis[lower]) / (axis[upper]-axis[lower])
            return values[lower] + fraction * (values[upper]-values[lower])
        times = [start] + [time for time in axis if start < time < stop] + [stop]
        samples = [interpolate(time) for time in times]
        if measure.operation == "max":
            value = max(samples)
        elif measure.operation == "min":
            value = min(samples)
        else:
            # Exact moments of the piecewise-linear sample interpolant. A
            # sample-count average biases adaptive/event-dense time grids.
            moments = []
            for t0, t1, a, b in zip(times, times[1:], samples, samples[1:]):
                moment = (a+b)/2 if measure.operation == "avg" else (a*a+a*b+b*b)/3
                moments.append((t1-t0)*moment)
            value = math.fsum(moments)/(stop-start)
            if measure.operation == "rms":
                value = math.sqrt(value)
        return base | {"value": value, "sample_count": len(selected),
                       "interpolation": "piecewise_linear", "weighting": "time",
                       "integration_points": len(times)}
    if not selected:
        raise ValueError("Measurement window contains no simulated samples.")
    samples = [values[index] for index in selected]
    if measure.operation == "max":
        value = max(samples)
    elif measure.operation == "min":
        value = min(samples)
    elif measure.operation == "avg":
        value = sum(samples) / len(samples)
    else:
        value = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return base | {"value": value, "sample_count": len(samples)}


def _measurements(
    project: CircuitProject,
    data: Mapping[str, Any],
    *,
    transient_weighting: str | None = None,
) -> dict[str, Any]:
    if transient_weighting is None:
        # Studio historically reduces native recorded samples by sample count.
        # Native result data identifies that route with its integration field;
        # owned core runners pass the newer time-domain policy explicitly.
        transient_weighting = "sample" if "integration" in data else "time"
    if transient_weighting not in {"sample", "time"}:
        raise ValueError("transient_weighting must be sample or time")
    result: dict[str, Any] = {}
    for measure in project.measurements:
        try:
            result[measure.name] = _one_measurement(
                measure, data, transient_weighting=transient_weighting
            )
        except (KeyError, ValueError, ArithmeticError) as exc:
            result[measure.name] = {
                "status": "failed", "operation": measure.operation,
                "probe": measure.probe.to_dict(),
                "issue": {"code": "SPIKES_MEASURE_FAILED", "message": str(exc)},
            }
    return result
