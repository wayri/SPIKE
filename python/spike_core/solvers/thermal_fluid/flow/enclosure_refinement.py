# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded rectilinear enclosure refinement and conservative MAC transfer.

Refinement inserts tensor-product planes through the whole domain.  The face
transfer is the rectangular lowest-order Raviart--Thomas reconstruction: each
normal component is affine only in its own coordinate and constant over the
coarse face's tangential directions.
"""
from collections.abc import Mapping
import math
import numbers
from fractions import Fraction

import numpy as np


MAX_COARSE_CELLS = 4096
MAX_FINE_CELLS = 8192
MAX_INTERVALS_PER_AXIS = 64
MAX_REFINEMENT_REGIONS = 64
MAX_RELATIVE_METRIC_ERROR = 1e-10
_GRID_KEYS = {
    "shape", "spacing_m", "origin_m", "local_refinement",
}
_REGION_KEYS = {"bounds_m", "split_factor"}
_BUILT_GRID_KEYS = {
    "axes_m", "coarse_axes_m", "shape", "coarse_shape", "parent_indices",
    "cell_widths_m", "cell_centers_m", "cell_volumes_m3", "face_areas_m2",
}


class EnclosureRefinementError(ValueError):
    """Raised when a refinement or transfer request is unsafe or malformed."""


def _finite_number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise EnclosureRefinementError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        raise EnclosureRefinementError(f"{name} must be a finite real number") from None
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise EnclosureRefinementError(f"{name} must be {qualifier}")
    return result


def _triple(value, name, converter):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise EnclosureRefinementError(f"{name} must contain exactly three values")
    return tuple(converter(item, f"{name}[{axis}]") for axis, item in enumerate(value))


def _validate_shape(value):
    def convert(item, name):
        if type(item) is not int or not 1 <= item <= 32:
            raise EnclosureRefinementError(f"{name} must be an integer from 1 through 32")
        return item

    shape = _triple(value, "shape", convert)
    if math.prod(shape) > MAX_COARSE_CELLS:
        raise EnclosureRefinementError("shape exceeds 4096 coarse cells")
    return shape


def _coarse_axis(origin, spacing, count, axis):
    end = origin + count * spacing
    if not math.isfinite(end) or end <= origin:
        raise EnclosureRefinementError(f"axis {axis} extent is not safely representable")
    with np.errstate(over="ignore", invalid="ignore"):
        values = origin + np.arange(count + 1, dtype=float) * spacing
    widths = np.diff(values)
    if not np.isfinite(values).all() or np.any(widths <= 0.0):
        raise EnclosureRefinementError(f"axis {axis} cuts are not safely representable")
    relative_error = np.max(np.abs(widths - spacing)) / spacing
    if not math.isfinite(float(relative_error)) or relative_error > MAX_RELATIVE_METRIC_ERROR:
        raise EnclosureRefinementError(
            f"axis {axis} physical cuts do not reproduce declared spacing within 1e-10 relative error")
    return values


def _validate_region(region, coarse_axes, index):
    if not isinstance(region, Mapping) or set(region) != _REGION_KEYS:
        raise EnclosureRefinementError(
            f"local_refinement[{index}] requires exactly bounds_m and split_factor")
    split = region["split_factor"]
    if type(split) is not int or not 2 <= split <= 4:
        raise EnclosureRefinementError(
            f"local_refinement[{index}].split_factor must be an integer from 2 through 4")
    bounds = region["bounds_m"]
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 3:
        raise EnclosureRefinementError(
            f"local_refinement[{index}].bounds_m must contain three intervals")
    parsed = []
    for axis, raw in enumerate(bounds):
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            raise EnclosureRefinementError(
                f"local_refinement[{index}].bounds_m[{axis}] must contain [low, high]")
        low = _finite_number(raw[0], f"local_refinement[{index}].bounds_m[{axis}][0]")
        high = _finite_number(raw[1], f"local_refinement[{index}].bounds_m[{axis}][1]")
        if high <= low:
            raise EnclosureRefinementError(
                f"local_refinement[{index}].bounds_m[{axis}] must be nonempty")
        if low < coarse_axes[axis][0] or high > coarse_axes[axis][-1]:
            raise EnclosureRefinementError(
                f"local_refinement[{index}].bounds_m[{axis}] lies outside the domain")
        parsed.append((low, high))
    return tuple(parsed), split


def _derived_geometry_is_safe(widths):
    minimums = [float(np.min(axis)) for axis in widths]
    maximums = [float(np.max(axis)) for axis in widths]
    values = [math.prod(minimums), math.prod(maximums)]
    for axis in range(3):
        tangential = [item for item in range(3) if item != axis]
        values.extend((
            minimums[tangential[0]] * minimums[tangential[1]],
            maximums[tangential[0]] * maximums[tangential[1]],
        ))
    return all(math.isfinite(item) and item > 0.0 for item in values)


def build_enclosure_grid(grid, *, cancel_check=None):
    """Build a bounded nested rectilinear grid from an exact request mapping.

    Every selected coarse interval receives the requested equal subdivision.
    Generated cuts are tensor planes, so an axis refinement propagates across
    the complete domain.  Overlapping region factors contribute the union of
    their rational subdivision cuts and never move a coarse cut.
    """
    if cancel_check and cancel_check():
        raise InterruptedError()
    if not isinstance(grid, Mapping) or set(grid) != _GRID_KEYS:
        raise EnclosureRefinementError(
            "grid requires exactly shape, spacing_m, origin_m, and local_refinement")
    shape = _validate_shape(grid["shape"])
    spacing = _triple(
        grid["spacing_m"], "spacing_m",
        lambda item, name: _finite_number(item, name, positive=True),
    )
    origin = _triple(grid["origin_m"], "origin_m", _finite_number)
    coarse_axes = tuple(
        _coarse_axis(origin[axis], spacing[axis], shape[axis], axis)
        for axis in range(3)
    )
    regions = grid["local_refinement"]
    if not isinstance(regions, (list, tuple)):
        raise EnclosureRefinementError("local_refinement must be a list")
    if len(regions) > MAX_REFINEMENT_REGIONS:
        raise EnclosureRefinementError("local_refinement exceeds 64 regions")

    # Fractions are retained exactly until coordinates are emitted, so factors
    # such as two and four share their midpoint rather than creating near-cuts.
    subdivisions = [[set() for _ in range(shape[axis])] for axis in range(3)]
    for index, region in enumerate(regions):
        if cancel_check and cancel_check():
            raise InterruptedError()
        bounds, split = _validate_region(region, coarse_axes, index)
        fractions = tuple(Fraction(part, split) for part in range(1, split))
        for axis in range(3):
            low, high = bounds[axis]
            selected = np.flatnonzero(
                (coarse_axes[axis][:-1] < high) & (coarse_axes[axis][1:] > low))
            if selected.size == 0:
                raise EnclosureRefinementError(
                    f"local_refinement[{index}] does not intersect axis {axis} cells")
            for coarse_index in selected:
                subdivisions[axis][int(coarse_index)].update(fractions)

    fine_shape = tuple(
        sum(1 + len(cuts) for cuts in subdivisions[axis]) for axis in range(3))
    if any(count > MAX_INTERVALS_PER_AXIS for count in fine_shape):
        raise EnclosureRefinementError("refined grid exceeds 64 intervals on an axis")
    if math.prod(fine_shape) > MAX_FINE_CELLS:
        raise EnclosureRefinementError("refined grid exceeds 8192 cells")
    if cancel_check and cancel_check():
        raise InterruptedError()

    axes = []
    parents = []
    for axis in range(3):
        cuts = [float(coarse_axes[axis][0])]
        parent = []
        for coarse_index, fractions in enumerate(subdivisions[axis]):
            left = float(coarse_axes[axis][coarse_index])
            width = float(coarse_axes[axis][coarse_index + 1] - left)
            ordered_fractions = [Fraction(0), *sorted(fractions), Fraction(1)]
            local = [left + width * float(fraction) for fraction in ordered_fractions[1:-1]]
            represented = np.diff(np.asarray([left, *local,
                                              float(coarse_axes[axis][coarse_index + 1])]))
            intended = np.asarray([
                spacing[axis] * float(ordered_fractions[item + 1] - ordered_fractions[item])
                for item in range(len(ordered_fractions) - 1)
            ])
            if not np.isfinite(intended).all() or np.any(intended <= 0.0):
                raise EnclosureRefinementError(
                    f"refined axis {axis} requested split widths are not safely representable")
            with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
                relative_error = np.max(np.abs(represented - intended) / intended)
            if (not math.isfinite(float(relative_error))
                    or relative_error > MAX_RELATIVE_METRIC_ERROR):
                raise EnclosureRefinementError(
                    f"refined axis {axis} cuts do not reproduce requested split widths "
                    "within 1e-10 relative error")
            cuts.extend(local)
            cuts.append(float(coarse_axes[axis][coarse_index + 1]))
            parent.extend([coarse_index] * (1 + len(fractions)))
        axis_values = np.asarray(cuts, dtype=float)
        if not np.isfinite(axis_values).all() or np.any(np.diff(axis_values) <= 0.0):
            raise EnclosureRefinementError(
                f"refined axis {axis} cuts are not safely representable")
        axes.append(axis_values)
        parents.append(np.asarray(parent, dtype=np.intp))

    widths = tuple(np.diff(axis) for axis in axes)
    coarse_widths = tuple(np.diff(axis) for axis in coarse_axes)
    if (not _derived_geometry_is_safe(widths)
            or not _derived_geometry_is_safe(coarse_widths)):
        raise EnclosureRefinementError("refined cell volumes or face areas are not safely representable")
    centers = tuple(axis[:-1] + 0.5 * width for axis, width in zip(axes, widths))
    if any(np.any((center <= axis[:-1]) | (center >= axis[1:]))
           for axis, center in zip(axes, centers)):
        raise EnclosureRefinementError("refined cell centers are not safely representable")
    if cancel_check and cancel_check():
        raise InterruptedError()

    with np.errstate(over="raise", under="ignore", invalid="raise"):
        try:
            volumes = (widths[0][:, None, None] * widths[1][None, :, None]
                       * widths[2][None, None, :])
            face_areas = (
                np.broadcast_to(widths[1][None, :, None] * widths[2][None, None, :],
                                (fine_shape[0] + 1, fine_shape[1], fine_shape[2])).copy(),
                np.broadcast_to(widths[0][:, None, None] * widths[2][None, None, :],
                                (fine_shape[0], fine_shape[1] + 1, fine_shape[2])).copy(),
                np.broadcast_to(widths[0][:, None, None] * widths[1][None, :, None],
                                (fine_shape[0], fine_shape[1], fine_shape[2] + 1)).copy(),
            )
        except FloatingPointError as exc:
            raise EnclosureRefinementError("refined geometry arithmetic is not finite") from exc
    if not np.isfinite(volumes).all() or np.any(volumes <= 0.0):
        raise EnclosureRefinementError("refined cell volumes are not finite and positive")

    return {
        "axes_m": tuple(axes),
        "coarse_axes_m": coarse_axes,
        "shape": fine_shape,
        "coarse_shape": shape,
        "parent_indices": tuple(parents),
        "cell_widths_m": widths,
        "cell_centers_m": centers,
        "cell_volumes_m3": volumes,
        "face_areas_m2": face_areas,
    }


def _as_numeric_array(value, name, shape):
    try:
        array = np.asarray(value)
    except (OverflowError, TypeError, ValueError):
        raise EnclosureRefinementError(f"{name} must be a real array with shape {shape}") from None
    if array.shape != shape or array.dtype.kind not in "iuf":
        raise EnclosureRefinementError(f"{name} must be a real array with shape {shape}")
    result = array.astype(float, copy=False)
    if not np.isfinite(result).all():
        raise EnclosureRefinementError(f"{name} must contain only finite values")
    return result


def _validate_built_grid(grid):
    if not isinstance(grid, Mapping) or set(grid) != _BUILT_GRID_KEYS:
        raise EnclosureRefinementError("grid must be the unmodified result of build_enclosure_grid")
    fine_shape = _validate_shape_like(grid["shape"], "shape", MAX_FINE_CELLS, 64)
    coarse_shape = _validate_shape_like(
        grid["coarse_shape"], "coarse_shape", MAX_COARSE_CELLS, 32)
    axes = _axis_arrays(grid["axes_m"], fine_shape, "axes_m")
    coarse_axes = _axis_arrays(grid["coarse_axes_m"], coarse_shape, "coarse_axes_m")
    parents_raw = grid["parent_indices"]
    if not isinstance(parents_raw, (list, tuple)) or len(parents_raw) != 3:
        raise EnclosureRefinementError("parent_indices must contain three arrays")
    parents = []
    for axis in range(3):
        try:
            parent = np.asarray(parents_raw[axis])
        except (OverflowError, TypeError, ValueError):
            raise EnclosureRefinementError(
                f"parent_indices[{axis}] has invalid shape or type") from None
        if parent.shape != (fine_shape[axis],) or parent.dtype.kind not in "iu":
            raise EnclosureRefinementError(f"parent_indices[{axis}] has invalid shape or type")
        parent = parent.astype(np.intp, copy=False)
        expected = np.searchsorted(coarse_axes[axis], axes[axis][:-1], side="right") - 1
        expected[axes[axis][:-1] == coarse_axes[axis][-1]] = coarse_shape[axis] - 1
        if (np.any(parent < 0) or np.any(parent >= coarse_shape[axis])
                or not np.array_equal(parent, expected)
                or np.any(axes[axis][:-1] < coarse_axes[axis][parent])
                or np.any(axes[axis][1:] > coarse_axes[axis][parent + 1])):
            raise EnclosureRefinementError(f"parent_indices[{axis}] is inconsistent with the axes")
        parents.append(parent)
    widths = _tuple_arrays(grid["cell_widths_m"], "cell_widths_m", 3)
    centers = _tuple_arrays(grid["cell_centers_m"], "cell_centers_m", 3)
    for axis in range(3):
        if (widths[axis].shape != (fine_shape[axis],)
                or not np.array_equal(widths[axis], np.diff(axes[axis]))):
            raise EnclosureRefinementError(f"cell_widths_m[{axis}] is inconsistent")
        expected_centers = axes[axis][:-1] + 0.5 * widths[axis]
        if centers[axis].shape != (fine_shape[axis],) or not np.array_equal(
                centers[axis], expected_centers):
            raise EnclosureRefinementError(f"cell_centers_m[{axis}] is inconsistent")
    if (not _derived_geometry_is_safe(widths)
            or not _derived_geometry_is_safe(tuple(np.diff(axis) for axis in coarse_axes))):
        raise EnclosureRefinementError("grid geometry is not safely representable")
    volumes = _as_numeric_array(grid["cell_volumes_m3"], "cell_volumes_m3", fine_shape)
    expected_volumes = (widths[0][:, None, None] * widths[1][None, :, None]
                        * widths[2][None, None, :])
    if not np.array_equal(volumes, expected_volumes):
        raise EnclosureRefinementError("cell_volumes_m3 is inconsistent")
    face_areas_raw = grid["face_areas_m2"]
    if not isinstance(face_areas_raw, (list, tuple)) or len(face_areas_raw) != 3:
        raise EnclosureRefinementError("face_areas_m2 must contain three arrays")
    face_areas = []
    for axis in range(3):
        face_shape = list(fine_shape)
        face_shape[axis] += 1
        actual = _as_numeric_array(
            face_areas_raw[axis], f"face_areas_m2[{axis}]", tuple(face_shape))
        tangential = [item for item in range(3) if item != axis]
        base = (widths[tangential[0]][:, None]
                * widths[tangential[1]][None, :])
        base_shape = [1, 1, 1]
        base_shape[tangential[0]] = fine_shape[tangential[0]]
        base_shape[tangential[1]] = fine_shape[tangential[1]]
        expected = np.broadcast_to(base.reshape(base_shape), face_shape)
        if not np.array_equal(actual, expected):
            raise EnclosureRefinementError(f"face_areas_m2[{axis}] is inconsistent")
        face_areas.append(actual)
    return fine_shape, coarse_shape, axes, coarse_axes, tuple(parents), widths, tuple(face_areas)


def _validate_shape_like(value, name, maximum_cells, maximum_axis):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(item) is not int or not 1 <= item <= maximum_axis for item in value)):
        raise EnclosureRefinementError(f"{name} is invalid")
    result = tuple(value)
    if math.prod(result) > maximum_cells:
        raise EnclosureRefinementError(f"{name} exceeds its cell budget")
    return result


def _axis_arrays(value, shape, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise EnclosureRefinementError(f"{name} must contain 3 arrays")
    arrays = []
    for axis, raw in enumerate(value):
        array = _as_numeric_array(raw, f"{name}[{axis}]", (shape[axis] + 1,))
        if np.any(np.diff(array) <= 0.0):
            raise EnclosureRefinementError(f"{name}[{axis}] is invalid")
        arrays.append(array)
    return tuple(arrays)


def _tuple_arrays(value, name, count):
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise EnclosureRefinementError(f"{name} must contain {count} arrays")
    try:
        return tuple(np.asarray(item) for item in value)
    except (OverflowError, TypeError, ValueError):
        raise EnclosureRefinementError(f"{name} contains an invalid array") from None


def _coarse_plane_indices(fine_axis, coarse_axis):
    locations = np.searchsorted(fine_axis, coarse_axis)
    if (np.any(locations >= len(fine_axis))
            or not np.array_equal(fine_axis[locations], coarse_axis)):
        raise EnclosureRefinementError("coarse cuts are not preserved in the refined axes")
    return locations


def _prolong_component(coarse, axis, axes, coarse_axes, parents):
    fine_shape = [len(item) - 1 for item in axes]
    fine_shape[axis] += 1
    output = np.empty(fine_shape, dtype=float)
    tangential = [item for item in range(3) if item != axis]
    tangential_index = np.ix_(*(parents[item] for item in tangential))
    planes = _coarse_plane_indices(axes[axis], coarse_axes[axis])
    plane_map = {int(fine): coarse_index for coarse_index, fine in enumerate(planes)}
    for fine_index, coordinate in enumerate(axes[axis]):
        if fine_index in plane_map:
            slab = np.take(coarse, plane_map[fine_index], axis=axis)
        else:
            coarse_index = int(np.searchsorted(coarse_axes[axis], coordinate) - 1)
            fraction = ((coordinate - coarse_axes[axis][coarse_index])
                        / (coarse_axes[axis][coarse_index + 1]
                           - coarse_axes[axis][coarse_index]))
            lower = np.take(coarse, coarse_index, axis=axis)
            upper = np.take(coarse, coarse_index + 1, axis=axis)
            slab = (1.0 - fraction) * lower + fraction * upper
        target = [slice(None)] * 3
        target[axis] = fine_index
        output[tuple(target)] = slab[tangential_index]
    if not np.isfinite(output).all():
        raise EnclosureRefinementError("prolonged face velocities are not finite")
    return output


def _stable_divergence(terms):
    scale = np.maximum.reduce(tuple(np.abs(term) for term in terms))
    normalized = np.zeros_like(scale)
    nonzero = scale > 0.0
    for term in terms:
        normalized[nonzero] += term[nonzero] / scale[nonzero]
    with np.errstate(over="raise", invalid="raise"):
        try:
            divergence = normalized * scale
        except FloatingPointError as exc:
            raise EnclosureRefinementError("velocity divergence is not representable") from exc
    if not np.isfinite(divergence).all():
        raise EnclosureRefinementError("velocity divergence is not finite")
    return divergence, scale


def _divergence(face_fields, widths):
    terms = []
    for axis in range(3):
        denominator_shape = [1, 1, 1]
        denominator_shape[axis] = len(widths[axis])
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            try:
                terms.append(np.diff(face_fields[axis], axis=axis)
                             / widths[axis].reshape(denominator_shape))
            except FloatingPointError as exc:
                raise EnclosureRefinementError("velocity gradients are not representable") from exc
    divergence, scale = _stable_divergence(terms)
    return divergence, scale, terms


def _flux_diagnostics(coarse_fields, fine_fields, coarse_axes, axes, parents, face_areas):
    total_error = 0.0
    total_expected_magnitude = 0.0
    total_actual_magnitude = 0.0
    maximum_error = 0.0
    zero_error = 0.0
    zero_patches = 0
    for axis in range(3):
        tangential = [item for item in range(3) if item != axis]
        coarse_widths = [np.diff(coarse_axes[item]) for item in range(3)]
        planes = _coarse_plane_indices(axes[axis], coarse_axes[axis])
        for coarse_face, fine_face in enumerate(planes):
            for first in range(len(coarse_axes[tangential[0]]) - 1):
                fine_first = np.flatnonzero(parents[tangential[0]] == first)
                for second in range(len(coarse_axes[tangential[1]]) - 1):
                    fine_second = np.flatnonzero(parents[tangential[1]] == second)
                    coarse_index = [0, 0, 0]
                    coarse_index[axis] = coarse_face
                    coarse_index[tangential[0]] = first
                    coarse_index[tangential[1]] = second
                    value = float(coarse_fields[axis][tuple(coarse_index)])
                    area = (float(coarse_widths[tangential[0]][first])
                            * float(coarse_widths[tangential[1]][second]))
                    expected = value * area
                    patch_index = [None, None, None]
                    patch_index[axis] = np.asarray([fine_face])
                    patch_index[tangential[0]] = fine_first
                    patch_index[tangential[1]] = fine_second
                    selector = np.ix_(*patch_index)
                    with np.errstate(over="raise", invalid="raise"):
                        try:
                            products = (fine_fields[axis][selector]
                                        * face_areas[axis][selector])
                        except FloatingPointError as exc:
                            raise EnclosureRefinementError(
                                "integrated face flux is not representable") from exc
                    try:
                        actual = math.fsum(float(item) for item in products.flat)
                    except OverflowError as exc:
                        raise EnclosureRefinementError(
                            "integrated face flux is not representable") from exc
                    error = abs(actual - expected)
                    total_error += error
                    total_expected_magnitude += abs(expected)
                    total_actual_magnitude += abs(actual)
                    maximum_error = max(maximum_error, error)
                    if value == 0.0:
                        zero_patches += 1
                        zero_error = max(zero_error, float(
                            np.max(np.abs(fine_fields[axis][selector]), initial=0.0)))
    values = (total_error, total_expected_magnitude, total_actual_magnitude,
              maximum_error, zero_error)
    if not all(math.isfinite(item) for item in values):
        raise EnclosureRefinementError("face flux diagnostics are not finite")
    scale = max(total_expected_magnitude, total_actual_magnitude)
    relative = total_error / scale if scale else 0.0
    return {
        "coarse_face_flux_integral_absolute_error_m3_s": total_error,
        "maximum_coarse_face_flux_integral_error_m3_s": maximum_error,
        "coarse_face_flux_integral_scale_m3_s": scale,
        "coarse_face_flux_integral_relative_error": relative,
        "zero_coarse_face_patches": zero_patches,
        "zero_coarse_face_preservation_error_m_s": zero_error,
    }


def prolong_mac_fluxes(grid, face_velocity_m_s, *, cancel_check=None):
    """Prolong coarse MAC normal velocities without changing cell divergence.

    ``grid`` must be the direct result of :func:`build_enclosure_grid`.
    Coarse face arrays use shapes ``(nx+1,ny,nz)``, ``(nx,ny+1,nz)`` and
    ``(nx,ny,nz+1)``.  No cell-centered velocity averaging is performed.
    """
    if cancel_check and cancel_check():
        raise InterruptedError()
    (fine_shape, coarse_shape, axes, coarse_axes, parents, widths,
     face_areas) = _validate_built_grid(grid)
    if not isinstance(face_velocity_m_s, (list, tuple)) or len(face_velocity_m_s) != 3:
        raise EnclosureRefinementError("face_velocity_m_s must contain three MAC arrays")
    coarse_fields = []
    for axis in range(3):
        expected_shape = list(coarse_shape)
        expected_shape[axis] += 1
        coarse_fields.append(_as_numeric_array(
            face_velocity_m_s[axis], f"face_velocity_m_s[{axis}]", tuple(expected_shape)))
    if cancel_check and cancel_check():
        raise InterruptedError()
    with np.errstate(over="raise", invalid="raise"):
        try:
            fine_fields = tuple(
                _prolong_component(coarse_fields[axis], axis, axes, coarse_axes, parents)
                for axis in range(3)
            )
        except FloatingPointError as exc:
            raise EnclosureRefinementError("face velocity interpolation is not finite") from exc
    if cancel_check and cancel_check():
        raise InterruptedError()

    coarse_widths = tuple(np.diff(axis) for axis in coarse_axes)
    coarse_divergence, coarse_scale, _ = _divergence(coarse_fields, coarse_widths)
    fine_divergence, fine_scale, _ = _divergence(fine_fields, widths)
    expected_divergence = coarse_divergence[np.ix_(*parents)]
    with np.errstate(over="ignore", invalid="ignore"):
        difference = np.abs(fine_divergence - expected_divergence)
    if not np.isfinite(difference).all():
        raise EnclosureRefinementError("divergence comparison is not finite")
    maximum_difference = float(np.max(difference, initial=0.0))
    divergence_scale = float(max(
        np.max(coarse_scale, initial=0.0), np.max(fine_scale, initial=0.0),
        np.max(np.abs(coarse_divergence), initial=0.0),
        np.max(np.abs(fine_divergence), initial=0.0),
    ))
    diagnostics = {
        "maximum_coarse_divergence_s_inv": float(
            np.max(np.abs(coarse_divergence), initial=0.0)),
        "maximum_fine_divergence_s_inv": float(
            np.max(np.abs(fine_divergence), initial=0.0)),
        "maximum_divergence_difference_s_inv": maximum_difference,
        "divergence_scale_s_inv": divergence_scale,
        "maximum_divergence_difference_relative": (
            maximum_difference / divergence_scale if divergence_scale else 0.0),
    }
    diagnostics.update(_flux_diagnostics(
        coarse_fields, fine_fields, coarse_axes, axes, parents, face_areas))
    if cancel_check and cancel_check():
        raise InterruptedError()
    return {"face_velocity_m_s": fine_fields, "diagnostics": diagnostics}


__all__ = [
    "EnclosureRefinementError", "build_enclosure_grid", "prolong_mac_fluxes",
]
