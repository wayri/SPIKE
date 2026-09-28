# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Ohmic PEEC matrix for the same uniform conductor bases as volume inductance.

Rectangles are planar copper prisms; circular barrels are coaxial annuli.  The
bilinear form is integral(b_i dot b_j / sigma) over shared copper volume.  It
keeps duplicated, overlapping current bases coupled instead of treating them
as independent resistors.  Unsupported intersecting shapes fail explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isclose, isfinite, pi
from typing import Sequence

import numpy as np

from .contracts import DesignIR
from .hybrid_mesh import MeshBranch
from .peec_magnetic_geometry import describe_magnetic_cross_section


@dataclass(frozen=True)
class _Basis:
    branch: MeshBranch
    area_mm2: float
    direction: tuple[float, float, float]
    z_low: float
    z_high: float
    polygon: tuple[tuple[float, float], ...] = ()
    annulus: tuple[float, float, float, float] | None = None


def _basis(design: DesignIR, branch: MeshBranch) -> _Basis:
    section = describe_magnetic_cross_section(design, branch)
    x0, y0, z0 = branch.start_mm
    x1, y1, z1 = branch.end_mm
    if section.shape == "circular_annulus":
        assert section.inner_radius_mm is not None
        assert section.outer_radius_mm is not None
        return _Basis(branch, section.area_mm2, (0.0, 0.0, 1.0 if z1 > z0 else -1.0),
                      min(z0, z1), max(z0, z1),
                      annulus=(x0, y0, section.inner_radius_mm, section.outer_radius_mm))
    if not isclose(z0, z1, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("volume resistance supports only planar rectangular copper")
    length = hypot(x1 - x0, y1 - y0)
    if not isfinite(length) or length <= 0.0:
        raise ValueError("invalid planar current-basis length")
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    half = branch.width_mm / 2.0
    nx, ny = -uy * half, ux * half
    polygon = ((x0 - nx, y0 - ny), (x1 - nx, y1 - ny),
               (x1 + nx, y1 + ny), (x0 + nx, y0 + ny))
    return _Basis(branch, section.area_mm2, (ux, uy, 0.0),
                  z0 - branch.thickness_mm / 2.0,
                  z0 + branch.thickness_mm / 2.0, polygon=polygon)


def _polygon_intersection_area(first: tuple[tuple[float, float], ...],
                               second: tuple[tuple[float, float], ...]) -> float:
    # Translate before clipping/area to avoid cancellation at large PCB origins.
    ox, oy = first[0]
    output = [(x - ox, y - oy) for x, y in first]
    boundary = [(x - ox, y - oy) for x, y in second]
    for index, edge_start in enumerate(boundary):
        edge_end = boundary[(index + 1) % len(boundary)]
        ex, ey = edge_end[0] - edge_start[0], edge_end[1] - edge_start[1]

        def side(point: tuple[float, float]) -> float:
            return ex * (point[1] - edge_start[1]) - ey * (point[0] - edge_start[0])

        previous = output[-1] if output else (0.0, 0.0)
        previous_side = side(previous)
        clipped: list[tuple[float, float]] = []
        for current in output:
            current_side = side(current)
            if (current_side >= 0.0) != (previous_side >= 0.0):
                fraction = previous_side / (previous_side - current_side)
                clipped.append((previous[0] + fraction * (current[0] - previous[0]),
                                previous[1] + fraction * (current[1] - previous[1])))
            if current_side >= 0.0:
                clipped.append(current)
            previous, previous_side = current, current_side
        output = clipped
        if len(output) < 3:
            return 0.0
    twice_area = sum(output[i][0] * output[(i + 1) % len(output)][1]
                     - output[i][1] * output[(i + 1) % len(output)][0]
                     for i in range(len(output)))
    return max(0.0, twice_area / 2.0)


def _shared_volume_mm3(first: _Basis, second: _Basis) -> float:
    height = max(0.0, min(first.z_high, second.z_high) - max(first.z_low, second.z_low))
    if height == 0.0:
        return 0.0
    if first.annulus is None and second.annulus is None:
        return height * _polygon_intersection_area(first.polygon, second.polygon)
    if first.annulus is None or second.annulus is None:
        # The admitted rectangular basis is planar and the annular basis axial.
        return 0.0
    ax, ay, ai, ao = first.annulus
    bx, by, bi, bo = second.annulus
    distance = hypot(ax - bx, ay - by)
    if distance >= ao + bo:
        return 0.0
    if distance > 1e-12:
        raise ValueError("intersecting noncoaxial annuli need a separate resistance integral")
    inner, outer = max(ai, bi), min(ao, bo)
    return height * pi * max(0.0, outer * outer - inner * inner)


def assemble_overlap_resistance(
    design: DesignIR, branches: Sequence[MeshBranch]
) -> tuple[np.ndarray, dict[str, float | int]]:
    """Return symmetric ohmic matrix in ohms, with no energy repair or clamps."""
    bases = [_basis(design, branch) for branch in branches]
    matrix = np.zeros((len(bases), len(bases)), dtype=float)
    overlap_pairs = 0
    for i, first in enumerate(bases):
        for j in range(i + 1):
            second = bases[j]
            direction_dot = sum(a * b for a, b in zip(first.direction, second.direction))
            shared = _shared_volume_mm3(first, second)
            if shared <= 0.0:
                continue
            if first.branch.net != second.branch.net or not isclose(
                first.branch.conductivity_s_m, second.branch.conductivity_s_m,
                rel_tol=1e-12, abs_tol=0.0
            ):
                raise ValueError("overlapping copper bases have incompatible net or conductivity")
            if abs(direction_dot) < 1e-15 and i != j:
                continue
            value = (1000.0 * shared * direction_dot /
                     (first.branch.conductivity_s_m * first.area_mm2 * second.area_mm2))
            if not isfinite(value):
                raise ValueError("volume resistance entry exceeded numerical range")
            matrix[i, j] = matrix[j, i] = value
            if i != j:
                overlap_pairs += 1
    if len(bases):
        eigenvalues = np.linalg.eigvalsh(matrix)
        scale = max(float(np.max(np.abs(eigenvalues))), 1e-30)
        if eigenvalues[0] < -max(1e-18, 1e-12 * scale):
            raise ValueError("volume resistance matrix has negative ohmic energy")
        if any(matrix[i, i] <= 0.0 for i in range(len(bases))):
            raise ValueError("volume resistance basis has no positive self loss")
        minimum = float(eigenvalues[0])
    else:
        minimum = 0.0
    return matrix, {"overlap_pair_count": overlap_pairs,
                    "minimum_resistance_eigenvalue_ohm": minimum}
