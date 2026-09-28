# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original closed-box Huygens postprocessor, not a Maxwell field solver.

Peak complex phasors use exp(+i omega t). Returned amplitude F is defined by
E(r) = F(r_hat) exp(-ikr)/r. Inputs must be collocated midpoint samples on all
six faces, entirely in one homogeneous isotropic lossless exterior, outside
all sources/scatterers and PML. This physical precondition is caller-owned;
finite arrays alone cannot establish Maxwell consistency or containment.

Equivalent currents J=n cross H, M=-n cross E are midpoint integrated.
No external implementation is incorporated. Scope reference:
https://meep.readthedocs.io/en/master/Python_User_Interface/#near-to-far-field-spectra
"""
from __future__ import annotations

import math
from typing import Callable, Mapping

import numpy as np

MAX_SAMPLES = 100_000
MAX_DIRECTIONS = 4096
MAX_SAMPLE_DIRECTIONS = 20_000_000
FACE_NAMES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")


class FarFieldError(ValueError):
    """Invalid data, unsupported scope or exceeded bounded workload."""


def _array(value, shape, complex_ok=False):
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise FarFieldError("E_INPUT: rectangular numeric array required") from exc
    if raw.dtype.kind not in ("i", "u", "f", "c") or (not complex_ok and raw.dtype.kind == "c"):
        raise FarFieldError("E_INPUT: numeric arrays required")
    if raw.shape != shape or not np.all(np.isfinite(raw)):
        raise FarFieldError("E_INPUT: array shape or finite value invalid")
    return raw.astype(complex if complex_ok else float, copy=False)


def box_samples(bounds_m, divisions):
    """Return face midpoint positions, internally derived normals and areas.

Each face shape follows ascending tangential axis order, then xyz components.
"""
    bounds = _array(bounds_m, (3, 2))
    if not isinstance(divisions, (list, tuple)) or len(divisions) != 3 or any(type(n) is not int or n < 1 for n in divisions):
        raise FarFieldError("E_INPUT: three positive integer divisions required")
    nx, ny, nz = divisions
    if 2 * (nx * ny + nx * nz + ny * nz) > MAX_SAMPLES:
        raise FarFieldError("E_RESOURCE: surface sample limit")
    with np.errstate(over="ignore", invalid="ignore"):
        widths = bounds[:, 1] - bounds[:, 0]
    if not np.all(np.isfinite(widths)) or np.any(widths <= 0):
        raise FarFieldError("E_INPUT: finite positive box widths required")
    steps = widths / divisions
    axes = [bounds[a, 0] + (np.arange(divisions[a]) + .5) * steps[a] for a in range(3)]
    if any(not np.all(np.isfinite(axis)) or np.any(np.diff(axis) <= 0)
           or axis[0] <= bounds[a, 0] or axis[-1] >= bounds[a, 1]
           for a, axis in enumerate(axes)):
        raise FarFieldError("E_INPUT: box midpoints not representable distinctly")
    result = {}
    for index, name in enumerate(FACE_NAMES):
        axis, side = divmod(index, 2)
        tangents = [a for a in range(3) if a != axis]
        grids = np.meshgrid(*(axes[a] for a in tangents), indexing="ij")
        points = np.empty((*grids[0].shape, 3))
        points[..., axis] = bounds[axis, side]
        for a, grid in zip(tangents, grids):
            points[..., a] = grid
        normal = np.zeros(3)
        normal[axis] = 2 * side - 1
        area = float(steps[tangents[0]] * steps[tangents[1]])
        if not math.isfinite(area) or area <= 0:
            raise FarFieldError("E_INPUT: surface area not representable")
        result[name] = (points, normal, area)
    return result


def huygens_far_field(*, bounds_m, divisions, electric_fields: Mapping,
                      magnetic_fields: Mapping, directions, frequency_hz: float,
                      permittivity_f_per_m: float, permeability_h_per_m: float,
                      homogeneous_lossless_exterior: bool,
                      cancelled: Callable[[], bool] | None = None):
    """Compute bounded far amplitudes/intensity; raises rather than partial output.

Directions must be unit Cartesian vectors. Returned intensity is W/sr for
peak phasors. No total power/directivity is inferred from arbitrary directions.
"""
    def poll():
        if cancelled is not None and cancelled():
            raise FarFieldError("E_CANCELLED: far-field postprocessing cancelled")
    poll()
    if homogeneous_lossless_exterior is not True:
        raise FarFieldError("E_UNSUPPORTED: homogeneous lossless exterior required")
    numbers = (frequency_hz, permittivity_f_per_m, permeability_h_per_m)
    try:
        valid_numbers = all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in numbers)
    except OverflowError:
        valid_numbers = False
    if not valid_numbers:
        raise FarFieldError("E_INPUT: finite positive frequency and material required")
    surfaces = box_samples(bounds_m, divisions)
    if (not isinstance(electric_fields, Mapping) or not isinstance(magnetic_fields, Mapping)
            or set(electric_fields) != set(FACE_NAMES) or set(magnetic_fields) != set(FACE_NAMES)):
        raise FarFieldError("E_INPUT: all six faces required without extras")
    try:
        raw_dirs = np.asarray(directions)
    except (TypeError, ValueError) as exc:
        raise FarFieldError("E_INPUT: rectangular directions required") from exc
    if raw_dirs.ndim != 2 or raw_dirs.shape[1] != 3 or not 1 <= len(raw_dirs) <= MAX_DIRECTIONS:
        raise FarFieldError("E_RESOURCE: bounded nonempty direction array required")
    dirs = _array(raw_dirs, raw_dirs.shape)
    if not np.allclose(np.linalg.norm(dirs, axis=1), 1., rtol=0, atol=1e-12):
        raise FarFieldError("E_INPUT: unit directions required")
    count = sum(p.size // 3 for p, _, _ in surfaces.values())
    if count * len(dirs) > MAX_SAMPLE_DIRECTIONS:
        raise FarFieldError("E_RESOURCE: quadrature work limit")
    k = 2 * math.pi * frequency_hz * math.sqrt(permittivity_f_per_m) * math.sqrt(permeability_h_per_m)
    eta = math.sqrt(permeability_h_per_m) / math.sqrt(permittivity_f_per_m)
    if not math.isfinite(k) or not math.isfinite(eta) or k <= 0 or eta <= 0:
        raise FarFieldError("E_INPUT: derived medium constants not representable")
    electric_current, magnetic_current, positions = [], [], []
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            for name, (points, normal, area) in surfaces.items():
                poll()
                e = _array(electric_fields[name], points.shape, True).reshape(-1, 3)
                h = _array(magnetic_fields[name], points.shape, True).reshape(-1, 3)
                electric_current.append(np.cross(normal, h) * area)
                magnetic_current.append(-np.cross(normal, e) * area)
                positions.append(points.reshape(-1, 3))
            j, m, xyz = map(np.concatenate, (electric_current, magnetic_current, positions))
            amplitude = np.empty((len(dirs), 3), complex)
            for start in range(0, len(dirs), 16):
                poll()
                rays = dirs[start:start + 16]
                phase = np.exp(1j * k * (rays @ xyz.T))
                nj, nm = phase @ j, phase @ m
                amplitude[start:start + len(rays)] = 1j * k / (4 * math.pi) * (
                    eta * np.cross(rays, np.cross(rays, nj)) + np.cross(rays, nm))
            intensity = np.sum(np.abs(amplitude)**2, axis=1) / (2 * eta)
        except FloatingPointError as exc:
            raise FarFieldError("E_NUMERIC: unrepresentable quadrature") from exc
    poll()
    if not np.all(np.isfinite(amplitude)) or not np.all(np.isfinite(intensity)):
        raise FarFieldError("E_NUMERIC: nonfinite far field")
    return {"electric_amplitude_v": amplitude, "radiation_intensity_w_per_sr": intensity,
            "surface_samples": count, "production_qualified": False,
            "scope": "closed_box_huygens_postprocessor", "phasor_convention": "exp(+iwt)"}
