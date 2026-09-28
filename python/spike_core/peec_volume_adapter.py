# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Typed DesignIR copper bases for the bounded native finite-volume PEEC path."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Any, Sequence

import numpy as np

from .contracts import DesignIR
from .hybrid_mesh import MeshBranch
from .peec_magnetic_geometry import describe_magnetic_cross_section
from .peec_volume_resistance import assemble_overlap_resistance
from .peec_volume_support import admit_zone_basis_support
from .peec_matrices import embed_physical_inductance
from .numerics import assess_symmetric_positive_semidefinite


@dataclass(frozen=True)
class VolumeMatrices:
    inductance_h: np.ndarray
    dc_resistance_ohm: np.ndarray
    quality: dict[str, float | int | str]


def retry_nonpassive_legacy(
    native: Any, design: DesignIR, branches: Sequence[MeshBranch],
    total_branches: int, physical_indices: Sequence[int],
) -> tuple[VolumeMatrices | None, np.ndarray | None, dict | None, str | None]:
    """Try one bounded volume matrix after legacy energy rejection, without repair."""
    try:
        volume = extract_volume_matrices(native, design, branches)
        embedded = embed_physical_inductance(
            np.asarray(volume.inductance_h, dtype=float), total_branches, physical_indices,
        )
        matrix, quality = assess_symmetric_positive_semidefinite(embedded)
        return volume, matrix, quality, None
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as error:
        return None, None, None, str(error)


def _add_basis(assembler: Any, native: Any, design: DesignIR, branch: MeshBranch) -> None:
    section = describe_magnetic_cross_section(design, branch)
    start = tuple(float(value) for value in branch.start_mm)
    end = tuple(float(value) for value in branch.end_mm)
    center = tuple((a + b) * 5e-4 for a, b in zip(start, end))
    if section.shape == "rectangle":
        if abs(start[2] - end[2]) > 1e-12:
            raise ValueError("finite-volume rectangle must be planar")
        length_mm = hypot(end[0] - start[0], end[1] - start[1])
        ux, uy = (end[0] - start[0]) / length_mm, (end[1] - start[1]) / length_mm
        basis = native.VolumeRectangularBasis()
        basis.center_m = center
        basis.direction = (ux, uy, 0.0)
        basis.width_axis = (-uy, ux, 0.0)
        basis.length_m = length_mm * 1e-3
        basis.width_m = float(section.width_mm) * 1e-3
        basis.thickness_m = float(section.thickness_mm) * 1e-3
        assembler.add_rectangular(basis)
    elif section.shape == "circular_annulus":
        basis = native.VolumeCoaxialAnnulusBasis()
        basis.center_m = center
        basis.direction = (0.0, 0.0, 1.0 if end[2] > start[2] else -1.0)
        basis.length_m = abs(end[2] - start[2]) * 1e-3
        basis.inner_radius_m = float(section.inner_radius_mm) * 1e-3
        basis.outer_radius_m = float(section.outer_radius_mm) * 1e-3
        assembler.add_coaxial_annulus(basis)
    else:
        raise ValueError(f"unsupported finite-volume magnetic section: {section.shape}")


def extract_volume_matrices(
    native: Any, design: DesignIR, branches: Sequence[MeshBranch],
    options: Any | None = None,
) -> VolumeMatrices:
    """Assemble L and R from identical ordered volume bases, failing closed."""
    required = ("VolumeMatrixAssembler", "VolumeMatrixIntegrationOptions",
                "VolumeRectangularBasis", "VolumeCoaxialAnnulusBasis")
    if any(not hasattr(native, name) for name in required):
        raise ValueError("native finite-volume PEEC backend is unavailable")
    if not branches:
        raise ValueError("finite-volume PEEC requires physical copper branches")
    support = admit_zone_basis_support(design, branches)
    if options is None:
        options = native.VolumeMatrixIntegrationOptions()
        # Directed rectangular integrals split the pair budget evenly. Marble
        # has an asymmetric overlap whose two directions use unequal work;
        # a 2M cap admits the converged reference without changing tolerance.
        rectangular = options.pair
        rectangular.max_potential_evaluations = 2_000_000
        options.pair = rectangular
        # A 0.5 mm Marble rail mesh has 120 bases/7,260 symmetric pairs;
        # retain a finite matrix cap while admitting that verified workload.
        # The independent global evaluation budget remains 100 million.
        options.maximum_matrix_pairs = 8_192
    assembler = native.VolumeMatrixAssembler(options)
    for branch in branches:
        _add_basis(assembler, native, design, branch)
    extraction = assembler.compute_inductance()
    if not extraction.converged:
        raise ValueError(
            f"{extraction.failure_code}: volume pair "
            f"({extraction.failure_pair_i}, {extraction.failure_pair_j}) did not qualify"
        )
    inductance = np.array(extraction.inductance_h, dtype=float, copy=True)
    errors = np.asarray(extraction.estimated_error_h, dtype=float)
    n = len(branches)
    if (inductance.shape != (n, n) or errors.shape != (n, n)
            or not np.all(np.isfinite(inductance)) or not np.all(np.isfinite(errors))
            or np.any(errors < 0.0)):
        raise ValueError("native finite-volume result has invalid shape or nonfinite entries")
    resistance, resistance_quality = assemble_overlap_resistance(design, branches)
    quality: dict[str, float | int | str] = {
        "method": "uniform_volume_current",
        "basis_count": n,
        "pair_count": int(extraction.pair_count),
        "potential_evaluations": int(extraction.potential_evaluations),
        "maximum_matrix_pairs": int(options.maximum_matrix_pairs),
        "maximum_total_potential_evaluations": int(options.maximum_total_potential_evaluations),
        "maximum_pair_potential_evaluations": int(options.pair.max_potential_evaluations),
        "rectangular_absolute_tolerance_h": float(options.pair.absolute_tolerance_h),
        "rectangular_relative_tolerance": float(options.pair.relative_tolerance),
        "maximum_estimated_pair_error_h": float(np.max(errors)),
        "zone_basis_outside_area_sum_mm2": float(support["outside_area_sum_mm2"]),
        "zone_basis_outside_area_tolerance_mm2": float(support["outside_area_tolerance_mm2"]),
        **resistance_quality,
    }
    if not all(isfinite(float(value)) for value in quality.values()
               if isinstance(value, (float, int))):
        raise ValueError("nonfinite finite-volume quality metric")
    return VolumeMatrices(inductance, resistance, quality)


class VolumeResistanceOverlay:
    """Preserve native isolated-skin increments over the exact DC overlap form.

    Frequency dependent proximity redistribution is not represented, so callers
    must retain the approximate model status for broadband results.
    """

    def __init__(self, base_solver: Any, branch_indices: Sequence[int],
                 volume_dc_resistance_ohm: np.ndarray) -> None:
        self._base_solver = base_solver
        self._indices = list(branch_indices)
        self._volume_dc = np.asarray(volume_dc_resistance_ohm, dtype=float).copy()
        self._base_dc = np.asarray(base_solver.compute_resistance(0.0), dtype=float)
        if (self._volume_dc.shape != (len(self._indices), len(self._indices))
                or self._base_dc.ndim != 2 or self._base_dc.shape[0] != self._base_dc.shape[1]
                or any(index < 0 or index >= self._base_dc.shape[0] for index in self._indices)
                or not np.all(np.isfinite(self._volume_dc))
                or not np.all(np.isfinite(self._base_dc))):
            raise ValueError("volume resistance overlay has incompatible matrices")

    def compute_resistance(self, frequency: float) -> np.ndarray:
        current = np.asarray(self._base_solver.compute_resistance(frequency), dtype=float).copy()
        if current.shape != self._base_dc.shape or not np.all(np.isfinite(current)):
            raise ValueError("native frequency resistance has invalid shape or entries")
        positions = np.ix_(self._indices, self._indices)
        current[positions] += self._volume_dc - self._base_dc[positions]
        return current
