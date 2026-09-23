# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Admit rectangular zone field bases only inside their source copper.

The intersection area is the sum over a nonoverlapping triangulation of the
source polygon. All area calculations are in mm^2. No conductor widths,
current normalization, topology, or integration tolerances are modified.
"""

from __future__ import annotations

from math import fsum, isfinite
from typing import Any, Sequence

from .contracts import DesignIR
from .hybrid_mesh import (
    MeshBranch, _normalize_filled_zone_polygon, _point, _polygon_area,
    _polygon_is_simple, _signed_polygon_area, _triangulate_polygon,
)
from .peec_volume_resistance import _basis, _polygon_intersection_area


OUTSIDE_AREA_TOLERANCE_MM2 = 1e-8


class ZoneBasisSupportError(ValueError):
    """Admission failure with machine-readable source and basis ownership."""

    def __init__(self, code: str, message: str, report: dict[str, Any]) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.report = report


def _unresolved(branch: MeshBranch, reason: str) -> ZoneBasisSupportError:
    return ZoneBasisSupportError("PEEC_ZONE_SUPPORT_UNRESOLVED",
        f"{branch.id}: source {branch.source_id} on {branch.layer}: {reason}",
        {"branch_id": branch.id, "source_id": branch.source_id,
         "layer": branch.layer, "reason": reason})


def zone_basis_support_report(
    design: DesignIR, branches: Sequence[MeshBranch],
) -> dict[str, Any]:
    """Measure unsupported area without changing or repairing supplied bases."""
    zones: dict[str, list] = {}
    for index, zone in enumerate(design.zones):
        zones.setdefault(str(zone.get("id", f"zone-{index + 1}")), []).append(zone)
    triangulations: dict[str, tuple] = {}
    records: list[dict[str, Any]] = []
    total_area = 0.0
    total_outside = 0.0
    count = 0
    for branch in branches:
        if branch.kind != "zone":
            continue
        count += 1
        matches = zones.get(branch.source_id, [])
        if len(matches) != 1:
            raise _unresolved(branch, f"expected one source boundary; found {len(matches)}")
        zone = matches[0]
        if (str(zone.get("layer", "")) != branch.layer
                or str(zone.get("net_name") or zone.get("net") or "") != branch.net):
            raise _unresolved(branch, "source layer/net mismatch")
        if branch.source_id not in triangulations:
            # The current DesignIR zone represents one simple filled outline.
            # Never silently fill a separately supplied exclusion ring.
            if zone.get("holes") or zone.get("interiors"):
                raise _unresolved(branch, "separate hole rings are not supported")
            try:
                if any(isinstance(point, dict) and not {"x", "y"} <= point.keys()
                       for point in zone.get("points", [])):
                    raise ValueError("missing polygon coordinate")
                points = [_point(point) for point in zone.get("points", [])]
            except (TypeError, ValueError, IndexError, KeyError, OverflowError) as exc:
                raise _unresolved(branch, "invalid source boundary coordinates") from exc
            if len(points) < 3 or not all(isfinite(v) for point in points for v in point):
                raise _unresolved(branch, "source boundary needs finite polygon coordinates")
            # Work near the origin before shoelace tests and ear clipping.
            # Translation does not alter support, including concave boundaries.
            ox, oy = points[0]
            translated = [(x - ox, y - oy) for x, y in points]
            if not all(isfinite(v) for point in translated for v in point):
                raise _unresolved(branch, "source extent exceeded numerical range")
            polygon = _normalize_filled_zone_polygon(translated)
            if len(polygon) < 3 or not _polygon_is_simple(polygon, 1e-6):
                raise _unresolved(branch, "non-simple source boundary")
            if _signed_polygon_area(polygon) < 0.0:
                polygon.reverse()
            triangles = _triangulate_polygon(polygon)
            area = _polygon_area(polygon)
            if (not isfinite(area) or area <= 0.0 or not triangles
                    or abs(fsum(_polygon_area(t) for t in triangles) - area) > max(1e-8, area * 1e-9)):
                raise _unresolved(branch, "incomplete source triangulation")
            triangulations[branch.source_id] = (triangles, ox, oy)
        triangles, ox, oy = triangulations[branch.source_id]
        try:
            rectangle = tuple((x - ox, y - oy) for x, y in _basis(design, branch).polygon)
        except (TypeError, ValueError, OverflowError) as exc:
            raise _unresolved(branch, "invalid current-basis geometry") from exc
        if len(rectangle) != 4 or not all(isfinite(v) for point in rectangle for v in point):
            raise _unresolved(branch, "current basis needs a finite planar rectangle")
        area = branch.length_mm * branch.width_mm
        inside = fsum(_polygon_intersection_area(tuple(triangle), rectangle)
                      for triangle in triangles)
        if (not isfinite(area) or not isfinite(inside)
                or inside > area + OUTSIDE_AREA_TOLERANCE_MM2):
            raise _unresolved(branch, "nonfinite or inconsistent intersection area")
        outside = max(0.0, area - inside)
        total_area += area
        total_outside += outside
        if outside > OUTSIDE_AREA_TOLERANCE_MM2:
            records.append({"branch_id": branch.id, "source_id": branch.source_id,
                            "layer": branch.layer, "basis_area_mm2": area,
                            "violated_boundary": "source_zone_filled_outline",
                            "outside_area_mm2": outside})
    return {"zone_basis_count": count,
            "zone_basis_area_sum_mm2": total_area,
            "outside_area_sum_mm2": total_outside,
            "outside_area_tolerance_mm2": OUTSIDE_AREA_TOLERANCE_MM2,
            "violating_basis_count": len(records), "violations": records}


def admit_zone_basis_support(design: DesignIR, branches: Sequence[MeshBranch]) -> dict[str, Any]:
    """Fail before native quadrature when a zone basis extends outside copper."""
    report = zone_basis_support_report(design, branches)
    if report["violations"]:
        first = report["violations"][0]
        raise ZoneBasisSupportError("PEEC_ZONE_BASIS_OUTSIDE_COPPER",
            f"{report['violating_basis_count']} zone basis(es); "
            f"{first['branch_id']} extends {first['outside_area_mm2']:.12g} mm^2 outside "
            f"source {first['source_id']} on {first['layer']} "
            f"(tolerance {OUTSIDE_AREA_TOLERANCE_MM2:g} mm^2). "
            "A conforming current basis and shared-contact formulation are required.", report
        )
    return report
