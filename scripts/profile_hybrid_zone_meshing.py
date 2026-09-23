# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded profiler for repeated hybrid-zone containment work.

The default fixture is one unchanged filled polygon from the checked-in
MODULAR-BUS-NIB DesignIR.  It compares the production rasterization path with
a per-polygon containment cache prototype and fails unless every emitted
fragment remains exactly equal and in the same order.
"""
from __future__ import annotations

import argparse
import cProfile
from dataclasses import asdict
import hashlib
import io
import json
from math import ceil, hypot, sqrt
from pathlib import Path
import pstats
import sys
from time import perf_counter
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.hybrid_mesh import (  # noqa: E402
    _clean_polygon,
    _clip_polygon_to_rect,
    _clip_polygon_to_rect_fragments,
    _normalize_filled_zone_polygon,
    _point_in_polygon,
    _polygon_area,
    _segments,
    _triangulate_polygon,
)
from python.spike_core.contracts import AnalysisSpec, DesignIR  # noqa: E402
import python.spike_core.hybrid_mesh as hybrid_mesh_module  # noqa: E402


Point2D = tuple[float, float]
Polygon = list[Point2D]


class ContainmentCache:
    """Exact per-polygon predicates with bounded point and segment caches."""

    def __init__(self, polygon: Polygon, tolerance: float, maximum_entries: int):
        self.polygon = polygon
        self.tolerance = tolerance
        self.edges = tuple(_segments(polygon))
        self.maximum_entries = maximum_entries
        self.points: dict[Point2D, bool] = {}
        self.segments: dict[tuple[Point2D, Point2D], bool] = {}

    def point_inside(self, point: Point2D) -> bool:
        cached = self.points.get(point)
        if cached is not None:
            return cached
        result = _point_in_polygon(point, self.polygon, self.tolerance)
        if len(self.points) < self.maximum_entries:
            self.points[point] = result
        return result

    def segment_inside(self, start: Point2D, end: Point2D) -> bool:
        key = (start, end) if start <= end else (end, start)
        cached = self.segments.get(key)
        if cached is not None:
            return cached
        result = self._segment_inside_uncached(start, end)
        if len(self.segments) < self.maximum_entries:
            self.segments[key] = result
        return result

    def _segment_inside_uncached(self, start: Point2D, end: Point2D) -> bool:
        if not (self.point_inside(start) and self.point_inside(end)):
            return False
        dx, dy = end[0] - start[0], end[1] - start[1]
        denominator_scale = max(hypot(dx, dy), 1.0)
        parameters = [0.0, 1.0]
        tolerance = self.tolerance
        for a, b in self.edges:
            sx, sy = b[0] - a[0], b[1] - a[1]
            denominator = dx * sy - dy * sx
            ax, ay = a[0] - start[0], a[1] - start[1]
            if abs(denominator) <= tolerance * denominator_scale:
                cross = ax * dy - ay * dx
                if abs(cross) > tolerance * denominator_scale:
                    continue
                length_squared = dx * dx + dy * dy
                if length_squared <= tolerance * tolerance:
                    continue
                for point in (a, b):
                    projection = (
                        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
                    ) / length_squared
                    if -tolerance <= projection <= 1 + tolerance:
                        parameters.append(max(0.0, min(1.0, projection)))
                continue
            t = (ax * sy - ay * sx) / denominator
            u = (ax * dy - ay * dx) / denominator
            if -tolerance <= t <= 1 + tolerance and -tolerance <= u <= 1 + tolerance:
                parameters.append(max(0.0, min(1.0, t)))
        ordered = sorted(set(round(value, 12) for value in parameters))
        return all(
            self.point_inside((
                start[0] + dx * ((left + right) / 2),
                start[1] + dy * ((left + right) / 2),
            ))
            for left, right in zip(ordered, ordered[1:])
            if right - left > 1e-12
        )


def _contained(candidate: Polygon, cache: ContainmentCache) -> bool:
    face = _clean_polygon(candidate)
    if len(face) < 3 or _polygon_area(face) <= 1e-12:
        return False
    triangles = _triangulate_polygon(face)
    if not triangles:
        return False
    for triangle in triangles:
        if not all(cache.segment_inside(start, end) for start, end in _segments(triangle)):
            return False
        center = (
            sum(point[0] for point in triangle) / 3,
            sum(point[1] for point in triangle) / 3,
        )
        if not cache.point_inside(center):
            return False
    return True


def _cached_fragments(
    polygon: Polygon,
    triangles: list[Polygon],
    triangle_bounds: list[tuple[float, float, float, float]],
    bounds: tuple[float, float, float, float],
    tolerance: float,
    cache: ContainmentCache,
) -> list[Polygon]:
    x0, y0, x1, y1 = bounds
    clipped = _clip_polygon_to_rect(polygon, x0, y0, x1, y1, tolerance)
    if len(clipped) < 3:
        return []
    if _contained(clipped, cache):
        return [clipped]
    fragments = []
    for triangle, (triangle_min_x, triangle_min_y, triangle_max_x, triangle_max_y) in zip(
        triangles, triangle_bounds
    ):
        if (
            triangle_max_x < x0 - tolerance
            or x1 + tolerance < triangle_min_x
            or triangle_max_y < y0 - tolerance
            or y1 + tolerance < triangle_min_y
        ):
            continue
        fragment = _clip_polygon_to_rect(triangle, x0, y0, x1, y1, tolerance)
        if (
            len(fragment) >= 3
            and _polygon_area(fragment) > 1e-12
            and _contained(fragment, cache)
        ):
            fragments.append(fragment)
    return fragments


def _fixture(path: Path, net: str) -> tuple[Polygon, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    design = payload.get("design", payload)
    candidates = [
        (index, zone)
        for index, zone in enumerate(design.get("zones", []))
        if str(zone.get("net_name") or zone.get("net") or "") == net
        and str(zone.get("layer", "")).endswith(".Cu")
    ]
    if not candidates:
        raise ValueError(f"No copper zone for net {net!r} in {path}")
    index, zone = max(candidates, key=lambda item: len(item[1].get("points", [])))
    polygon = _normalize_filled_zone_polygon(
        [(float(point[0]), float(point[1])) for point in zone.get("points", [])]
    )
    if len(polygon) < 3:
        raise ValueError("Selected zone has no usable polygon")
    return polygon, {
        "path": str(path.relative_to(ROOT)),
        "zone_index": index,
        "net": net,
        "layer": str(zone.get("layer", "")),
        "polygon_vertices": len(polygon),
        "polygon_sha256": hashlib.sha256(
            json.dumps(polygon, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest(),
    }


def _grid(
    polygon: Polygon,
    zone_cell_mm: float,
    max_zone_cells: int,
    max_grid_cells: int,
) -> tuple[float, list[tuple[float, float, float, float]]]:
    min_x, max_x = min(x for x, _ in polygon), max(x for x, _ in polygon)
    min_y, max_y = min(y for _, y in polygon), max(y for _, y in polygon)
    estimated = max(1.0, (max_x - min_x) * (max_y - min_y) / zone_cell_mm**2)
    cell = zone_cell_mm * sqrt(max(1.0, estimated / max_zone_cells))
    columns = max(1, int(ceil((max_x - min_x) / cell)))
    rows = max(1, int(ceil((max_y - min_y) / cell)))
    count = columns * rows
    if count > max_grid_cells:
        raise ValueError(
            f"Fixture needs {count} grid cells, above --max-grid-cells={max_grid_cells}"
        )
    bounds = [
        (
            min_x + column * cell,
            min_y + row * cell,
            min(min_x + (column + 1) * cell, max_x),
            min(min_y + (row + 1) * cell, max_y),
        )
        for row in range(rows)
        for column in range(columns)
    ]
    return cell, bounds


def _profile(call: Callable[[], list[list[Polygon]]]) -> tuple[list[list[Polygon]], dict[str, object]]:
    profiler = cProfile.Profile()
    started = perf_counter()
    profiler.enable()
    result = call()
    profiler.disable()
    elapsed = perf_counter() - started
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumtime").print_stats(12)
    return result, {"elapsed_s": elapsed, "top_cumulative": stream.getvalue().splitlines()}


def _shallow_cache_bytes(values: dict[object, object]) -> int:
    return sys.getsizeof(values) + sum(
        sys.getsizeof(key) + sys.getsizeof(value) for key, value in values.items()
    )


def benchmark(args: argparse.Namespace) -> dict[str, object]:
    polygon, fixture = _fixture(args.input, args.net)
    triangles = _triangulate_polygon(polygon)
    if not triangles:
        raise ValueError("Selected zone could not be triangulated")
    cell, bounds = _grid(
        polygon, args.zone_cell_mm, args.max_zone_cells, args.max_grid_cells
    )
    triangle_bounds = [
        (
            min(x for x, _ in triangle),
            min(y for _, y in triangle),
            max(x for x, _ in triangle),
            max(y for _, y in triangle),
        )
        for triangle in triangles
    ]
    baseline, baseline_profile = _profile(lambda: [
        _clip_polygon_to_rect_fragments(
            polygon, triangles, x0, y0, x1, y1, args.tolerance_mm
        )
        for x0, y0, x1, y1 in bounds
    ])
    cache = ContainmentCache(polygon, args.tolerance_mm, args.maximum_cache_entries)
    optimized, optimized_profile = _profile(lambda: [
        _cached_fragments(
            polygon, triangles, triangle_bounds, item, args.tolerance_mm, cache
        )
        for item in bounds
    ])
    if baseline != optimized:
        mismatch = next(
            index for index, (left, right) in enumerate(zip(baseline, optimized))
            if left != right
        )
        raise AssertionError(f"Cached prototype changed fragments at grid cell {mismatch}")
    canonical = json.dumps(baseline, separators=(",", ":"), allow_nan=False).encode("utf-8")
    baseline_s = float(baseline_profile["elapsed_s"])
    optimized_s = float(optimized_profile["elapsed_s"])
    report = {
        "contract": "spike/hybrid-zone-meshing-profile/v1",
        "fixture": fixture,
        "settings": {
            "zone_cell_mm": args.zone_cell_mm,
            "effective_cell_mm": cell,
            "max_zone_cells": args.max_zone_cells,
            "max_grid_cells": args.max_grid_cells,
            "actual_grid_cells": len(bounds),
            "maximum_cache_entries_per_kind": args.maximum_cache_entries,
            "containment_tolerance_mm": args.tolerance_mm,
        },
        "equivalence": {
            "exact_fragment_lists": True,
            "nonempty_cells": sum(bool(item) for item in baseline),
            "fragment_count": sum(len(item) for item in baseline),
            "fragments_sha256": hashlib.sha256(canonical).hexdigest(),
        },
        "baseline": baseline_profile,
        "cached_prototype": {
            **optimized_profile,
            "point_cache_entries": len(cache.points),
            "segment_cache_entries": len(cache.segments),
            "point_cache_shallow_bytes": _shallow_cache_bytes(cache.points),
            "segment_cache_shallow_bytes": _shallow_cache_bytes(cache.segments),
        },
        "speedup": baseline_s / optimized_s if optimized_s else None,
    }
    if args.full_mesh:
        report["full_mesh"] = _full_mesh_comparison(args)
    return report


def _full_mesh_comparison(args: argparse.Namespace) -> dict[str, object]:
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    raw = payload.get("design", payload)
    design_values = {
        key: value for key, value in raw.items() if key in DesignIR.__dataclass_fields__
    }
    design_values["issues"] = []
    design = DesignIR(**design_values)
    spec = AnalysisSpec(mode="dc", net_names=[args.net], mesh={
        "target_size_mm": args.full_target_size_mm,
        "zone_cell_mm": args.full_zone_cell_mm,
        "max_zone_cells": args.max_zone_cells,
        "max_conductors": 500_000,
        "memory_budget_mb": 2048,
    })

    production_cache = hybrid_mesh_module._PolygonContainmentCache
    production_fragments = hybrid_mesh_module._clip_polygon_to_rect_fragments

    class NoCache:
        def __init__(self, polygon, tolerance, maximum_entries=None):
            self.polygon = polygon
            self.tolerance = tolerance

        def point_inside(self, point):
            return _point_in_polygon(point, self.polygon, self.tolerance)

        def segment_inside(self, start, end):
            return hybrid_mesh_module._segment_inside_polygon(
                start, end, self.polygon, self.tolerance
            )

    def baseline_fragments(
        polygon, triangles, x0, y0, x1, y1, tolerance,
        containment_cache=None, triangle_bounds=None,
    ):
        return production_fragments(
            polygon, triangles, x0, y0, x1, y1, tolerance, None, None
        )

    try:
        hybrid_mesh_module._PolygonContainmentCache = NoCache
        hybrid_mesh_module._clip_polygon_to_rect_fragments = baseline_fragments
        started = perf_counter()
        baseline = hybrid_mesh_module.build_hybrid_mesh(design, spec)
        baseline_elapsed = perf_counter() - started
    finally:
        hybrid_mesh_module._PolygonContainmentCache = production_cache
        hybrid_mesh_module._clip_polygon_to_rect_fragments = production_fragments

    started = perf_counter()
    optimized = hybrid_mesh_module.build_hybrid_mesh(design, spec)
    optimized_elapsed = perf_counter() - started
    baseline_bytes = json.dumps(
        asdict(baseline), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    optimized_bytes = json.dumps(
        asdict(optimized), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if baseline_bytes != optimized_bytes:
        raise AssertionError("Cached full-net mesh changed the serialized HybridMesh")
    return {
        "settings": {
            "target_size_mm": args.full_target_size_mm,
            "zone_cell_mm": args.full_zone_cell_mm,
        },
        "exact_serialized_mesh": True,
        "mesh_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "nodes": len(baseline.nodes),
        "branches": len(baseline.branches),
        "cells": len(baseline.cells),
        "truncated": baseline.truncated,
        "baseline_elapsed_s": baseline_elapsed,
        "optimized_elapsed_s": optimized_elapsed,
        "speedup": baseline_elapsed / optimized_elapsed if optimized_elapsed else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "docs/validation/modular-bus-nib-design.json",
    )
    parser.add_argument("--net", default="/12Vout")
    parser.add_argument("--zone-cell-mm", type=float, default=0.25)
    parser.add_argument("--max-zone-cells", type=int, default=20_000)
    parser.add_argument("--max-grid-cells", type=int, default=20_000)
    parser.add_argument("--maximum-cache-entries", type=int, default=131_072)
    parser.add_argument("--tolerance-mm", type=float, default=0.0001)
    parser.add_argument("--full-mesh", action="store_true")
    parser.add_argument("--full-target-size-mm", type=float, default=0.5)
    parser.add_argument("--full-zone-cell-mm", type=float, default=0.25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.zone_cell_mm <= 0 or args.max_zone_cells < 1 or args.max_grid_cells < 1:
        parser.error("Cell size and cell limits must be positive")
    if args.maximum_cache_entries < 1 or args.tolerance_mm <= 0:
        parser.error("Cache limit and containment tolerance must be positive")
    report = benchmark(args)
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
