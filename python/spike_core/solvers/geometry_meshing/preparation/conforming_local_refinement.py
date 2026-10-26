# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Strict, bounded area controls for the experimental conforming copper mesh.

Coordinates and edge lengths are millimetres. Controls only partition retained
interior rectangles; they do not move copper, terminal contacts, or via lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite


@dataclass(frozen=True)
class LocalCopperRegion:
    layer: str
    net: str
    bounds_mm: tuple[float, float, float, float]
    maximum_edge_mm: float


def parse_local_copper_regions(raw: object, base_target_mm: float) -> tuple[LocalCopperRegion, ...]:
    """Reject malformed, ambiguous, or coarsening requests before allocation."""
    if raw is None:
        return ()
    if not isinstance(raw, dict) or set(raw) != {"contract", "regions"}:
        raise ValueError("Conforming local refinement requires contract and regions")
    if raw["contract"] != "spike/conforming-local-refinement/v1":
        raise ValueError("Unsupported conforming local refinement contract")
    rows = raw["regions"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError("Conforming local refinement requires 1..64 regions")
    parsed = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"layer", "net", "bounds_mm", "maximum_edge_mm"}:
            raise ValueError("Conforming local region requires layer, net, bounds_mm, maximum_edge_mm")
        if not isinstance(row["layer"], str) or not row["layer"] or not isinstance(row["net"], str) or not row["net"]:
            raise ValueError("Conforming local region requires nonempty layer and net")
        bounds = row["bounds_mm"]
        edge = row["maximum_edge_mm"]
        if (not isinstance(bounds, list) or len(bounds) != 4
                or any(type(value) not in (int, float) for value in bounds)
                or type(edge) not in (int, float)):
            raise ValueError("Conforming local bounds and maximum edge must be JSON numbers")
        try:
            bounds = tuple(float(value) for value in bounds)
            edge = float(edge)
        except OverflowError as error:
            raise ValueError("Conforming local bounds and maximum edge must be finite") from error
        if (not all(isfinite(value) for value in bounds) or not isfinite(edge)
                or not bounds[0] < bounds[2] or not bounds[1] < bounds[3]
                or not 0 < edge <= base_target_mm):
            raise ValueError("Conforming local region requires finite positive bounds and refinement edge")
        parsed.append(LocalCopperRegion(row["layer"], row["net"], bounds, edge))
    return tuple(parsed)


def refine_local_rectangles(
    rectangles: list[tuple[float, float, float, float]],
    regions: tuple[LocalCopperRegion, ...],
    layer: str,
    net: str,
    remaining_cells: int,
) -> tuple[list[tuple[float, float, float, float]], dict[int, int]]:
    """Split exactly at region boundaries; never enlarge the rectangle union.

    Returns per-rule positive-area hit counts. A missing hit is rejected by
    the caller after all layer/net groups have been processed.
    """
    selected = [(index, region) for index, region in enumerate(regions)
                if region.layer == layer and region.net == net]
    result: list[tuple[float, float, float, float]] = []
    hits: dict[int, int] = {}
    for x0, y0, x1, y1 in rectangles:
        touching = [(index, region) for index, region in selected
                    if min(x1, region.bounds_mm[2]) > max(x0, region.bounds_mm[0])
                    and min(y1, region.bounds_mm[3]) > max(y0, region.bounds_mm[1])]
        for index, _ in touching:
            hits[index] = hits.get(index, 0) + 1
        xs = sorted({x0, x1, *(min(x1, max(x0, coordinate))
            for _, region in touching for coordinate in (region.bounds_mm[0], region.bounds_mm[2]))})
        ys = sorted({y0, y1, *(min(y1, max(y0, coordinate))
            for _, region in touching for coordinate in (region.bounds_mm[1], region.bounds_mm[3]))})
        # The downstream RT0 triangle admission rejects dimensions below
        # 1e-9 mm. Reject a near-coincident manual cut at this boundary too,
        # before the preview could report an apparently valid control cell.
        if (any(b-a < 1e-9 for a,b in zip(xs,xs[1:]))
                or any(b-a < 1e-9 for a,b in zip(ys,ys[1:]))):
            raise ValueError("Conforming local region creates a sub-1e-9 mm control sliver")
        if len(result) + (len(xs)-1)*(len(ys)-1) > remaining_cells:
            raise ValueError("Conforming local subdivision exceeds the control-cell budget")
        for xa, xb in zip(xs, xs[1:]):
            for ya, yb in zip(ys, ys[1:]):
                cx, cy = (xa+xb)/2, (ya+yb)/2
                limits = [region.maximum_edge_mm for _, region in touching
                    if region.bounds_mm[0] <= cx <= region.bounds_mm[2]
                    and region.bounds_mm[1] <= cy <= region.bounds_mm[3]]
                if not limits:
                    if len(result)+1 > remaining_cells:
                        raise ValueError("Conforming local subdivision exceeds the control-cell budget")
                    result.append((xa, ya, xb, yb))
                    continue
                edge = min(limits)
                width, height = xb-xa, yb-ya
                if width > remaining_cells*edge or height > remaining_cells*edge:
                    raise ValueError("Conforming local subdivision exceeds the control-cell budget")
                nx, ny = max(1, ceil(width/edge)), max(1, ceil(height/edge))
                if len(result) + nx*ny > remaining_cells:
                    raise ValueError("Conforming local subdivision exceeds the control-cell budget")
                for i in range(nx):
                    low_x = xa+width*i/nx
                    high_x = xb if i == nx-1 else xa+width*(i+1)/nx
                    for j in range(ny):
                        low_y = ya+height*j/ny
                        high_y = yb if j == ny-1 else ya+height*(j+1)/ny
                        result.append((low_x, low_y, high_x, high_y))
    return result, hits
