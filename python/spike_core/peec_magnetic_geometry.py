# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Explicit PEEC cross-sections, separate from mesh resistance equivalents.

All coordinates and dimensions here are in millimetres. This module describes
geometry only; it does not make the existing PEEC inductance kernel passive or
resolve overlapping planar current bases.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import dist, isclose, isfinite, pi
from numbers import Real
from typing import Any, Mapping

from .contracts import DesignIR
from .hybrid_mesh import TOPOLOGY_ONLY_BRANCH_KINDS, MeshBranch


class MagneticGeometryError(ValueError):
    """The branch has no unambiguous supported magnetic cross-section."""


@dataclass(frozen=True)
class MagneticCrossSection:
    shape: str  # "rectangle" or "circular_annulus"
    area_mm2: float
    width_mm: float | None = None
    thickness_mm: float | None = None
    inner_radius_mm: float | None = None
    outer_radius_mm: float | None = None


def _positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MagneticGeometryError(f"{label} must be a finite positive mm value")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MagneticGeometryError(f"{label} must be a finite positive mm value") from exc
    if not isfinite(number) or number <= 0.0:
        raise MagneticGeometryError(f"{label} must be a finite positive mm value")
    return number


def _coordinate(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise MagneticGeometryError("branch endpoints must be finite mm coordinates")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MagneticGeometryError("branch endpoints must be finite mm coordinates") from exc
    if not isfinite(number):
        raise MagneticGeometryError("branch endpoints must be finite mm coordinates")
    return number


def _source(design: DesignIR, branch: MeshBranch) -> Mapping[str, Any]:
    if branch.kind == "via":
        items = design.vias
        fallback = "via"
    else:
        items = design.pads
        fallback = "pad"
    matches = [
        item for index, item in enumerate(items, start=1)
        if str(item.get("id") or (item.get("component_pad") if fallback == "pad" else None)
               or f"{fallback}-{index}") == branch.source_id
    ]
    if len(matches) != 1:
        raise MagneticGeometryError(
            f"{branch.kind} branch {branch.id} needs one source {branch.source_id!r}; found {len(matches)}"
        )
    return matches[0]


def _pad_drill_diameter(pad: Mapping[str, Any]) -> float:
    raw = pad.get("drill_size", pad.get("drill_size_mm"))
    if isinstance(raw, Mapping):
        raw = (raw.get("x", raw.get("width")), raw.get("y", raw.get("height")))
    if raw is None:
        diameter = _positive(pad.get("drill"), "pad drill diameter")
        dimensions = (diameter, diameter)
    elif isinstance(raw, (list, tuple)) and len(raw) == 2:
        dimensions = (
            _positive(raw[0], "pad drill width"),
            _positive(raw[1], "pad drill height"),
        )
    else:
        raise MagneticGeometryError("pad drill_size must contain two mm dimensions")
    if str(pad.get("drill_shape", "circle")).strip().lower() not in {"", "circle"}:
        raise MagneticGeometryError("noncircular plated pad barrels need a separate magnetic model")
    if not isclose(dimensions[0], dimensions[1], rel_tol=0.0, abs_tol=1e-12):
        raise MagneticGeometryError("noncircular plated pad barrels need a separate magnetic model")
    if pad.get("plated") is False or str(pad.get("type", "")).lower() == "np_thru_hole":
        raise MagneticGeometryError("unplated pad cannot have a magnetic barrel")
    return dimensions[0]


def describe_magnetic_cross_section(
    design: DesignIR, branch: MeshBranch
) -> MagneticCrossSection:
    """Describe a branch cross-section without reusing barrel circumference as width.

    The current mesh's ``width_mm * thickness_mm`` remains its DC area. For a
    circular barrel, ``thickness_mm`` is plating thickness; the magnetic
    cross-section is the actual annulus around the drill. Unsupported slots
    and ambiguous source identifiers fail closed.
    """
    if design.units != "mm":
        raise MagneticGeometryError("magnetic geometry requires DesignIR units=mm")
    if branch.kind in TOPOLOGY_ONLY_BRANCH_KINDS:
        raise MagneticGeometryError(
            f"{branch.kind} is a graph-only link, not a magnetic current basis"
        )
    if len(branch.start_mm) != 3 or len(branch.end_mm) != 3:
        raise MagneticGeometryError("branch endpoints must have three mm coordinates")
    start = tuple(_coordinate(value) for value in branch.start_mm)
    end = tuple(_coordinate(value) for value in branch.end_mm)
    _positive(dist(start, end), "branch length")
    width = _positive(branch.width_mm, "branch resistance width")
    thickness = _positive(branch.thickness_mm, "branch resistance thickness")
    resistance_area = width * thickness
    if not isfinite(resistance_area):
        raise MagneticGeometryError("branch resistance area must be finite mm2")
    if branch.kind not in {"via", "pad_barrel"}:
        return MagneticCrossSection("rectangle", resistance_area, width, thickness)
    if (not isclose(start[0], end[0], rel_tol=0.0, abs_tol=1e-12)
            or not isclose(start[1], end[1], rel_tol=0.0, abs_tol=1e-12)):
        raise MagneticGeometryError("circular barrel axis must be vertical")
    source = _source(design, branch)
    diameter = (
        _positive(source.get("drill"), "via drill diameter")
        if branch.kind == "via" else _pad_drill_diameter(source)
    )
    inner_radius = diameter / 2.0
    outer_radius = inner_radius + thickness
    magnetic_area = pi * thickness * (diameter + thickness)
    if not isfinite(outer_radius) or not isfinite(magnetic_area):
        raise MagneticGeometryError("barrel magnetic geometry must have finite mm dimensions and area")
    # The mesher's equivalent DC width is pi*(drill+plating). Check provenance
    # instead of accepting a different magnetic shape to conceal an input error.
    if not isclose(resistance_area, magnetic_area, rel_tol=1e-10, abs_tol=1e-12):
        raise MagneticGeometryError(
            "barrel resistance area does not match the source drill and plating annulus"
        )
    return MagneticCrossSection(
        "circular_annulus", magnetic_area,
        inner_radius_mm=inner_radius, outer_radius_mm=outer_radius,
    )
