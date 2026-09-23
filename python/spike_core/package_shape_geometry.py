"""Canonical analytic geometry carried by exact package-shape selectors."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping


PACKAGE_SHAPE_GEOMETRY_V1 = "spike/package-shape-selector-geometry/v1"
REPRESENTATIONS = {"unsupported", "point", "line", "circle", "plane", "axis"}


class PackageShapeGeometryError(ValueError):
    """Raised when an exact-selector analytic descriptor is malformed."""


def _vector(raw: Any, label: str, *, unit: bool = False) -> list[float] | None:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise PackageShapeGeometryError(f"{label} must be a three-value vector or null.")
    values: list[float] = []
    for item in raw:
        if isinstance(item, bool):
            raise PackageShapeGeometryError(f"{label} must contain finite numeric values.")
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise PackageShapeGeometryError(f"{label} must contain finite numeric values.") from exc
        if not math.isfinite(value):
            raise PackageShapeGeometryError(f"{label} must contain finite numeric values.")
        values.append(0.0 if value == 0.0 else value)
    if unit and abs(math.sqrt(sum(value * value for value in values)) - 1.0) > 1e-10:
        raise PackageShapeGeometryError(f"{label} must be a unit vector.")
    return values


def canonicalize_selector_geometry(raw: Any, kind: str, label: str) -> Dict[str, Any]:
    """Validate one BREP-derived, shape-local analytic descriptor."""

    fields = {"contract", "coordinate_space", "representation", "origin_mm", "direction", "radius_mm"}
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise PackageShapeGeometryError(f"{label} must contain exactly: {', '.join(sorted(fields))}.")
    if raw.get("contract") != PACKAGE_SHAPE_GEOMETRY_V1 or raw.get("coordinate_space") != "shape_local_mm":
        raise PackageShapeGeometryError(f"{label} contract or coordinate space is unsupported.")
    representation = raw.get("representation")
    if representation not in REPRESENTATIONS:
        raise PackageShapeGeometryError(f"{label} representation is unsupported.")
    origin = _vector(raw.get("origin_mm"), f"{label} origin_mm")
    direction = _vector(raw.get("direction"), f"{label} direction", unit=True)
    radius_raw = raw.get("radius_mm")
    radius = None
    if radius_raw is not None:
        if isinstance(radius_raw, bool):
            raise PackageShapeGeometryError(f"{label} radius_mm must be positive and finite or null.")
        try:
            radius = float(radius_raw)
        except (TypeError, ValueError) as exc:
            raise PackageShapeGeometryError(f"{label} radius_mm must be positive and finite or null.") from exc
        if not math.isfinite(radius) or radius <= 0:
            raise PackageShapeGeometryError(f"{label} radius_mm must be positive and finite or null.")
    expected = {
        "unsupported": (False, False, False),
        "point": (True, False, False),
        "line": (True, True, False),
        "circle": (True, True, True),
        "plane": (True, True, False),
        "axis": (True, True, False),
    }[representation]
    actual = (origin is not None, direction is not None, radius is not None)
    if actual != expected:
        raise PackageShapeGeometryError(f"{label} fields do not match its {representation} representation.")
    allowed = {
        "solid": {"unsupported"}, "shell": {"unsupported"},
        "face": {"plane", "unsupported"},
        "edge": {"line", "circle", "unsupported"},
        "vertex": {"point"}, "axis": {"axis"},
    }.get(kind, set())
    if representation not in allowed:
        raise PackageShapeGeometryError(f"{label} representation is not valid for topology kind {kind}.")
    return {
        "contract": PACKAGE_SHAPE_GEOMETRY_V1,
        "coordinate_space": "shape_local_mm",
        "representation": representation,
        "origin_mm": origin,
        "direction": direction,
        "radius_mm": radius,
    }
