# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Fail-closed checks for the mesh that CSXCAD actually produced."""

from __future__ import annotations

import math


VACUUM_LIGHT_SPEED_M_S = 299_792_458.0
ESTIMATED_BYTES_PER_CELL = 256


ACTUAL_GRID_POLICY_SOURCE = r'''
def actual_grid_report(lines_by_axis, cell_limit, memory_limit_bytes,
                       bytes_per_cell=256, vacuum_light_speed_m_s=299792458.0):
    """Validate final CSXCAD lines and return bounded, unit-labelled metrics."""
    try:
        cell_limit = int(cell_limit)
        memory_limit_bytes = int(memory_limit_bytes)
        bytes_per_cell = int(bytes_per_cell)
    except (TypeError, ValueError, OverflowError):
        raise RuntimeError("OPENEMS_ACTUAL_GRID_BUDGET_INVALID")
    if cell_limit <= 0 or memory_limit_bytes <= 0 or bytes_per_cell <= 0:
        raise RuntimeError("OPENEMS_ACTUAL_GRID_BUDGET_INVALID")
    counts, minimums, maximums = [], [], []
    for axis in ("x", "y", "z"):
        try:
            lines = [float(value) for value in lines_by_axis[axis]]
        except (KeyError, TypeError, ValueError, OverflowError):
            raise RuntimeError("OPENEMS_ACTUAL_GRID_INVALID_" + axis.upper())
        if len(lines) < 2 or any(not math.isfinite(value) for value in lines):
            raise RuntimeError("OPENEMS_ACTUAL_GRID_INVALID_" + axis.upper())
        spacings = [lines[index + 1] - lines[index] for index in range(len(lines) - 1)]
        if any(not math.isfinite(value) or value <= 0 for value in spacings):
            raise RuntimeError("OPENEMS_ACTUAL_GRID_NOT_INCREASING_" + axis.upper())
        if min(spacings) < 1e-12:
            raise RuntimeError("OPENEMS_ACTUAL_GRID_SPACING_UNREPRESENTABLE_" + axis.upper())
        counts.append(len(spacings))
        minimums.append(min(spacings))
        maximums.append(max(spacings))
    cells = math.prod(counts)
    memory_bytes = cells * bytes_per_cell
    if cells > cell_limit:
        raise RuntimeError("OPENEMS_ACTUAL_GRID_CELL_BUDGET_EXCEEDED: %d > %d" % (cells, cell_limit))
    if memory_bytes > memory_limit_bytes:
        raise RuntimeError("OPENEMS_ACTUAL_GRID_MEMORY_BUDGET_EXCEEDED: %d > %d" % (memory_bytes, memory_limit_bytes))
    # Conservative vacuum Yee CFL reference from global axis minima. The
    # production engine may use a different local timestep criterion.
    minimum_m = [value * 1e-3 for value in minimums]
    cfl_seconds = 1.0 / (vacuum_light_speed_m_s * math.sqrt(
        sum(1.0 / (value * value) for value in minimum_m)))
    if not math.isfinite(cfl_seconds) or cfl_seconds <= 0:
        raise RuntimeError("OPENEMS_ACTUAL_GRID_CFL_INVALID")
    return {
        "axis_cell_counts": dict(zip(("x", "y", "z"), counts)),
        "cell_count": cells,
        "estimated_memory_bytes": memory_bytes,
        "bytes_per_cell_assumption": bytes_per_cell,
        "minimum_spacing_mm": dict(zip(("x", "y", "z"), minimums)),
        "maximum_spacing_mm": dict(zip(("x", "y", "z"), maximums)),
        "vacuum_cfl_reference_timestep_s": cfl_seconds,
    }

def require_time_window(actual_grid, max_timesteps, frequency_start_hz,
                        frequency_stop_hz):
    """Enforce a conservative one-cycle resource-screening policy.

    Global-minimum-axis CFL is a reference estimate, not the timestep
    selected by openEMS on a nonuniform grid. This intentionally may reject
    otherwise runnable cases; passing does not establish temporal accuracy.
    """
    try:
        steps = int(max_timesteps)
        start = float(frequency_start_hz)
        stop = float(frequency_stop_hz)
        cfl = float(actual_grid["vacuum_cfl_reference_timestep_s"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise RuntimeError("OPENEMS_ACTUAL_GRID_TIME_WINDOW_INVALID")
    if (steps <= 0 or not math.isfinite(start) or not math.isfinite(stop)
            or not 0 <= start < stop or not math.isfinite(cfl) or cfl <= 0):
        raise RuntimeError("OPENEMS_ACTUAL_GRID_TIME_WINDOW_INVALID")
    required_s = 1.0 / (start if start > 0 else stop)
    reference_s = steps * cfl
    if not math.isfinite(reference_s) or reference_s < required_s:
        raise RuntimeError(
            "OPENEMS_ACTUAL_GRID_TIME_WINDOW_POLICY_INSUFFICIENT: %.6g s < %.6g s"
            % (reference_s, required_s))
    return {
        "cfl_reference_time_window_s": reference_s,
        "minimum_one_cycle_window_s": required_s,
    }
'''


namespace = {"math": math}
exec(compile(ACTUAL_GRID_POLICY_SOURCE, "<spike-openems-mesh-policy>", "exec"), namespace)
actual_grid_report = namespace["actual_grid_report"]
require_time_window = namespace["require_time_window"]


__all__ = ["ACTUAL_GRID_POLICY_SOURCE", "actual_grid_report", "require_time_window"]
