"""Exact closed zone-boundary primitives used by DesignIR v2."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import List, Optional


def _point(value):
    values = list(value or (0.0, 0.0))
    return (float(values[0]), float(values[1]))


@dataclass
class ZoneBoundarySegment:
    kind: str
    end_mm: tuple[float, float]
    center_mm: Optional[tuple[float, float]] = None
    clockwise: Optional[bool] = None

    def __post_init__(self) -> None:
        self.end_mm = _point(self.end_mm)
        self.center_mm = _point(self.center_mm) if self.center_mm is not None else None
        if not all(math.isfinite(value) for value in self.end_mm):
            raise ValueError("Zone boundary endpoints must be finite.")
        if self.kind == "line":
            if self.center_mm is not None or self.clockwise is not None:
                raise ValueError("Line boundary segments cannot carry arc metadata.")
        elif self.kind == "arc":
            if self.center_mm is None or not all(math.isfinite(value) for value in self.center_mm):
                raise ValueError("Arc boundary segments require a finite center.")
            if not isinstance(self.clockwise, bool):
                raise ValueError("Arc boundary segments require an explicit direction.")
        else:
            raise ValueError("Zone boundary segment kind is unsupported.")


@dataclass
class ZoneBoundaryRing:
    role: str
    start_mm: tuple[float, float]
    segments: List[ZoneBoundarySegment] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.start_mm = _point(self.start_mm)
        self.segments = [item if isinstance(item, ZoneBoundarySegment) else ZoneBoundarySegment(**dict(item)) for item in self.segments]
        if self.role not in {"outer", "cutout"}:
            raise ValueError("Zone boundary ring role is unsupported.")
        if len(self.segments) < 2 or not all(math.isfinite(value) for value in self.start_mm):
            raise ValueError("Zone boundary rings require a finite start and at least two segments.")
        current = self.start_mm
        for segment in self.segments:
            if segment.end_mm == current:
                raise ValueError("Zone boundary segments must have non-zero extent.")
            if segment.kind == "arc":
                assert segment.center_mm is not None
                start_radius = math.hypot(current[0] - segment.center_mm[0], current[1] - segment.center_mm[1])
                end_radius = math.hypot(segment.end_mm[0] - segment.center_mm[0], segment.end_mm[1] - segment.center_mm[1])
                if start_radius <= 0 or not math.isclose(start_radius, end_radius, rel_tol=1e-9, abs_tol=1e-9):
                    raise ValueError("Zone boundary arcs require equal positive start/end radii.")
            current = segment.end_mm
        if not all(math.isclose(current[index], self.start_mm[index], rel_tol=0.0, abs_tol=1e-9) for index in (0, 1)):
            raise ValueError("Zone boundary rings must close exactly.")
