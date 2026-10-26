# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded rectilinear thermal grids and conservative area transfer.

All coordinates are millimetres. An overlap matrix contains destination-area
fractions, so transferring a piecewise constant source raster conserves its
integrated area. Refinement cannot recover geometry missing from that raster.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix


def grid_edges(board: Mapping[str, Any], bounds: tuple[float, float, float, float],
               layers: int) -> tuple[np.ndarray, np.ndarray, bool]:
    """Admit full-board edge lists or preserve the legacy uniform-step grid."""
    explicit = "x_edges_mm" in board or "y_edges_mm" in board
    axes = []
    for key, low, high in (("x_edges_mm", bounds[0], bounds[2]),
                           ("y_edges_mm", bounds[1], bounds[3])):
        if explicit:
            raw = board.get(key)
            if not isinstance(raw, (list, tuple)) or not 2 <= len(raw) <= 8193:
                raise ValueError(f"{key} needs 2..8193 full-board edges.")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw):
                raise ValueError(f"{key} needs finite numeric edges.")
            axis = np.asarray(raw, dtype=float)
            if (not np.all(np.isfinite(axis)) or axis[0] != low or axis[-1] != high
                    or np.any(np.diff(axis) < 1e-6)):
                raise ValueError(f"{key} must increase by at least 1e-6 mm and exactly cover board bounds.")
        else:
            raw = board.get("grid_step_mm")
            if isinstance(raw, bool):
                raise ValueError("board grid_step_mm must be positive and finite.")
            step = float(raw)
            if not math.isfinite(step) or step <= 0:
                raise ValueError("board grid_step_mm must be positive and finite.")
            count = math.ceil((high - low) / step)
            if count > 8192:
                raise ValueError("Layered grid exceeds the bounded cell limit.")
            axis = np.linspace(low, high, count + 1)
        axes.append(axis)
    cells = (len(axes[0]) - 1) * (len(axes[1]) - 1)
    if cells > 8192 or cells * layers > 131072:
        raise ValueError("Layered grid exceeds 8192 planar or 131072 volume cells.")
    return axes[0], axes[1], explicit


def cell_index(edges: np.ndarray, point: float) -> int:
    """Assign an admitted point to its containing cell; high boundary is closed."""
    return max(0, min(len(edges) - 2, int(np.searchsorted(edges, point, side="right")) - 1))


def rectangle_weights(x: np.ndarray, y: np.ndarray,
                      box: tuple[float, float, float, float]) -> list[tuple[int, float]]:
    """Exact overlap fractions of an axis-aligned rectangle inside the grid."""
    x0, y0, x1, y1 = box
    area = (x1 - x0) * (y1 - y0)
    if area <= 0 or x0 < x[0] or x1 > x[-1] or y0 < y[0] or y1 > y[-1]:
        raise ValueError("Thermal contact rectangle must be nonempty and inside board bounds.")
    ox = np.maximum(0, np.minimum(x[1:], x1) - np.maximum(x[:-1], x0))
    oy = np.maximum(0, np.minimum(y[1:], y1) - np.maximum(y[:-1], y0))
    indices = np.flatnonzero(np.outer(oy, ox).ravel())
    fractions = np.outer(oy, ox).ravel() / area
    result = [(int(index), float(fractions[index])) for index in indices]
    if abs(sum(weight for _, weight in result) - 1) > 1e-10:
        raise ValueError("Thermal contact area was not conserved on the grid.")
    return result


def overlap_matrix(destination: np.ndarray, source: np.ndarray) -> csr_matrix:
    """Sparse 1-D destination-normalized overlaps in linear traversal time."""
    rows, columns, values = [], [], []
    i = j = 0
    while i < len(destination) - 1 and j < len(source) - 1:
        width = min(destination[i + 1], source[j + 1]) - max(destination[i], source[j])
        if width > 0:
            rows.append(i)
            columns.append(j)
            values.append(width / (destination[i + 1] - destination[i]))
        if destination[i + 1] < source[j + 1]:
            i += 1
        elif destination[i + 1] > source[j + 1]:
            j += 1
        else:
            i += 1
            j += 1
    return csr_matrix((values, (rows, columns)), shape=(len(destination) - 1, len(source) - 1))


def transfer_coverage(coverage: Mapping[str, np.ndarray], source_x: np.ndarray, source_y: np.ndarray,
                      target_x: np.ndarray, target_y: np.ndarray) -> dict[str, np.ndarray]:
    """Integrate fixed physical raster occupancy onto each thermal control volume."""
    wx, wy = overlap_matrix(target_x, source_x), overlap_matrix(target_y, source_y)
    # Source and target each fit the planar budget, but a cross-axis
    # intermediate need not. Choose the smaller cross product (<=8192
    # entries for admitted grids), not an unconditional y-first multiply.
    y_first = (len(target_y) - 1) * (len(source_x) - 1)
    x_first = (len(target_x) - 1) * (len(source_y) - 1)
    if y_first <= x_first:
        return {name: np.asarray((wx @ (wy @ values).T).T) for name, values in coverage.items()}
    return {name: np.asarray(wy @ (wx @ values.T).T) for name, values in coverage.items()}
