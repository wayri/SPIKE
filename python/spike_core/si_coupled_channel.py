"""Bounded two-conductor geometry-derived SI channel reference solver.

The solver admits only two straight, parallel, coextensive traces above one
simple reference plane in one homogeneous dielectric.  A sparse finite-
difference cross-section solve produces a Maxwell capacitance matrix.  The
vacuum matrix gives the quasi-TEM inductance matrix, and the multiconductor
telegrapher state transition produces a four-port network.  This is an
independently written reference path pending the packaged SPIKES process
implementation and measured qualification.
"""

from __future__ import annotations

from math import ceil, isfinite, log10, pi
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.linalg import expm
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from .design_ir_v2 import DesignIRV2
from .sparameters import NetworkData, analyze_network, single_ended_to_mixed_mode
from .si_channel import (
    MAX_EYE_BITS,
    MAX_FREQUENCY_POINTS,
    RESULT_CONTRACT,
    SiChannelError,
    _canonical_digest,
    _frequency_grid,
    _ordered_open_path,
    _validate_channel_request,
    _reference_zone_covers_path,
    _selector,
    normalized_nrz_eye,
    time_domain_report,
)


COUPLED_EXTRACTION_CONTRACT = "spike/si-coupled-path-extraction/v1"
_EPSILON_0 = 8.854_187_812_8e-12
_C0_M_PER_S = 299_792_458.0
MIN_VERTICAL_CELLS = 12
MAX_VERTICAL_CELLS = 96
MAX_HORIZONTAL_CELLS = 1024


def _path_for_net(design: DesignIRV2, net: Any, path_id: str, *, path_mode: str) -> list[Any]:
    tracks = [track for track in design.tracks if track.net_id == net.id]
    if path_id:
        tracks = [track for track in tracks if track.path is not None and track.path.path_id == path_id]
    if not tracks:
        raise SiChannelError(f"No canonical track geometry matched net {net.name!r}.")
    if any(arc.net_id == net.id for arc in design.arcs):
        raise SiChannelError("Arcs are outside the bounded coupled-channel envelope.")
    if any(via.net_id == net.id for via in design.vias):
        raise SiChannelError("Vias are outside the bounded coupled-channel envelope.")
    if len({track.layer_id for track in tracks}) != 1 or len({round(track.width_mm, 12) for track in tracks}) != 1:
        raise SiChannelError("Each coupled path must retain one layer and one constant width.")
    return _ordered_open_path(tracks, require_straight=path_mode == "strict_uniform")


def _endpoints(tracks: Sequence[Any]) -> tuple[np.ndarray, np.ndarray]:
    counts: dict[tuple[float, float], int] = {}
    for track in tracks:
        for point in (track.start_mm, track.end_mm):
            key = (round(float(point[0]), 12), round(float(point[1]), 12))
            counts[key] = counts.get(key, 0) + 1
    values = [np.asarray(point, dtype=float) for point, count in sorted(counts.items()) if count == 1]
    if len(values) != 2:
        raise SiChannelError("Each coupled path must have exactly two endpoints.")
    return values[0], values[1]


def _coupled_geometry(signal_tracks: Sequence[Any], victim_tracks: Sequence[Any]) -> dict[str, float]:
    a0, a1 = _endpoints(signal_tracks)
    b0, b1 = _endpoints(victim_tracks)
    axis = a1 - a0
    length_mm = float(np.linalg.norm(axis))
    if length_mm <= 0:
        raise SiChannelError("The coupled path length must be positive.")
    axis /= length_mm
    normal = np.asarray([-axis[1], axis[0]])
    victim_axis = b1 - b0
    victim_length = float(np.linalg.norm(victim_axis))
    if victim_length <= 0 or abs(float(axis[0] * victim_axis[1] - axis[1] * victim_axis[0])) > 1e-9:
        raise SiChannelError("The bounded coupled paths must be parallel.")
    a_projection = sorted((float(np.dot(a0, axis)), float(np.dot(a1, axis))))
    b_projection = sorted((float(np.dot(b0, axis)), float(np.dot(b1, axis))))
    if max(abs(a_projection[index] - b_projection[index]) for index in (0, 1)) > 1e-6:
        raise SiChannelError("The bounded coupled paths must be coextensive without longitudinal skew.")
    signal_center = 0.5 * float(np.dot(a0 + a1, normal))
    victim_center = 0.5 * float(np.dot(b0 + b1, normal))
    separation_mm = abs(victim_center - signal_center)
    signal_width_mm = float(signal_tracks[0].width_mm)
    victim_width_mm = float(victim_tracks[0].width_mm)
    edge_gap_mm = separation_mm - 0.5 * (signal_width_mm + victim_width_mm)
    if edge_gap_mm <= 0:
        raise SiChannelError("Coupled trace copper footprints overlap or touch.")
    return {
        "length_mm": length_mm,
        "signal_center_mm": signal_center,
        "victim_center_mm": victim_center,
        "signal_width_mm": signal_width_mm,
        "victim_width_mm": victim_width_mm,
        "center_separation_mm": separation_mm,
        "edge_gap_mm": edge_gap_mm,
    }


def _ordered_points(tracks: Sequence[Any]) -> list[np.ndarray]:
    """Return the path in traversal order, independent of source segment orientation."""

    endpoints, counts = [], {}
    for track in tracks:
        for point in (track.start_mm, track.end_mm):
            key = (round(float(point[0]), 12), round(float(point[1]), 12))
            counts[key] = counts.get(key, 0) + 1
    ends = sorted(key for key, count in counts.items() if count == 1)
    if len(ends) != 2:
        raise SiChannelError("Each coupled piecewise path must have exactly two endpoints.")
    cursor = ends[0]
    points = [np.asarray(cursor, dtype=float)]
    unused = list(tracks)
    while unused:
        matched = [track for track in unused if cursor in {
            (round(float(track.start_mm[0]), 12), round(float(track.start_mm[1]), 12)),
            (round(float(track.end_mm[0]), 12), round(float(track.end_mm[1]), 12)),
        }]
        if len(matched) != 1:
            raise SiChannelError("The coupled piecewise path is disconnected or ambiguous.")
        track = matched[0]
        unused.remove(track)
        start = (round(float(track.start_mm[0]), 12), round(float(track.start_mm[1]), 12))
        end = (round(float(track.end_mm[0]), 12), round(float(track.end_mm[1]), 12))
        cursor = end if cursor == start else start
        points.append(np.asarray(cursor, dtype=float))
    return points


def _piecewise_coupled_geometry(
    signal_tracks: Sequence[Any], victim_tracks: Sequence[Any], *,
    separation_tolerance_mm: float, skew_tolerance_mm: float,
) -> dict[str, Any]:
    """Build a one-cross-section approximation for matched bent pairs.

    This is intentionally not a general coupled-line field solve.  Each paired
    segment must remain parallel and nearly equal length.  The smallest
    observed center separation is then used over the longer total path, making
    the retained cross-section coupling no weaker than any admitted segment.
    """

    signal_points = _ordered_points(signal_tracks)
    victim_points = _ordered_points(victim_tracks)
    if np.linalg.norm(signal_points[0] - victim_points[0]) > np.linalg.norm(signal_points[0] - victim_points[-1]):
        victim_points.reverse()
    if len(signal_points) != len(victim_points):
        raise SiChannelError("Coupled piecewise paths must have the same segment count.")
    signal_width_mm = float(signal_tracks[0].width_mm)
    victim_width_mm = float(victim_tracks[0].width_mm)
    separations: list[float] = []
    separation_weights: list[float] = []
    signal_length_mm = 0.0
    victim_length_mm = 0.0
    segment_evidence: list[dict[str, Any]] = []
    for index, (a0, a1, b0, b1) in enumerate(zip(signal_points, signal_points[1:], victim_points, victim_points[1:])):
        a_vector, b_vector = a1 - a0, b1 - b0
        a_length, b_length = float(np.linalg.norm(a_vector)), float(np.linalg.norm(b_vector))
        if a_length <= 0 or b_length <= 0:
            raise SiChannelError("Coupled piecewise paths contain a zero-length segment.")
        a_axis, b_axis = a_vector / a_length, b_vector / b_length
        if abs(float(a_axis[0] * b_axis[1] - a_axis[1] * b_axis[0])) > 1e-6 or float(np.dot(a_axis, b_axis)) <= 0:
            raise SiChannelError("Corresponding coupled piecewise segments must be co-directed and parallel.")
        if abs(a_length - b_length) > skew_tolerance_mm:
            raise SiChannelError("Corresponding coupled piecewise segment lengths exceed coupled_skew_tolerance_mm.")
        normal = np.asarray([-a_axis[1], a_axis[0]])
        separation = abs(float(np.dot(0.5 * (b0 + b1 - a0 - a1), normal)))
        edge_gap = separation - 0.5 * (signal_width_mm + victim_width_mm)
        if edge_gap <= 0:
            raise SiChannelError("Coupled piecewise trace copper footprints overlap or touch.")
        separations.append(separation)
        separation_weights.append(max(a_length, b_length))
        signal_length_mm += a_length
        victim_length_mm += b_length
        segment_evidence.append({
            "segment_index": index,
            "signal_length_mm": a_length,
            "victim_length_mm": b_length,
            "center_separation_mm": separation,
            "edge_gap_mm": edge_gap,
        })
    if max(separations) - min(separations) > separation_tolerance_mm:
        raise SiChannelError("Coupled piecewise center-separation variation exceeds coupled_separation_tolerance_mm.")
    if abs(signal_length_mm - victim_length_mm) > skew_tolerance_mm:
        raise SiChannelError("Coupled piecewise total skew exceeds coupled_skew_tolerance_mm.")
    separation_mm = min(separations)
    weighted_average_separation_mm = float(np.average(np.asarray(separations), weights=np.asarray(separation_weights)))
    return {
        "length_mm": max(signal_length_mm, victim_length_mm),
        "signal_center_mm": -0.5 * separation_mm,
        "victim_center_mm": 0.5 * separation_mm,
        "signal_width_mm": signal_width_mm,
        "victim_width_mm": victim_width_mm,
        "center_separation_mm": separation_mm,
        "edge_gap_mm": separation_mm - 0.5 * (signal_width_mm + victim_width_mm),
        "piecewise_segment_evidence": segment_evidence,
        "maximum_center_separation_mm": max(separations),
        "length_weighted_average_center_separation_mm": weighted_average_separation_mm,
        "conservative_extraction_center_separation_mm": separation_mm,
        "signal_length_mm": signal_length_mm,
        "victim_length_mm": victim_length_mm,
        "coupled_separation_tolerance_mm": separation_tolerance_mm,
        "coupled_skew_tolerance_mm": skew_tolerance_mm,
    }


def _cross_section_capacitance(
    *, centers_m: Sequence[float], widths_m: Sequence[float], height_m: float,
    vertical_cells: int, cancel_check: Callable[[], bool] | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    margin = max(5.0 * height_m, 2.0 * max(widths_m))
    left = min(center - width / 2.0 for center, width in zip(centers_m, widths_m)) - margin
    right = max(center + width / 2.0 for center, width in zip(centers_m, widths_m)) + margin
    dy = height_m / vertical_cells
    horizontal_cells = int(ceil((right - left) / dy))
    if horizontal_cells > MAX_HORIZONTAL_CELLS:
        raise SiChannelError(
            f"Cross-section needs {horizontal_cells} horizontal cells; the hard limit is {MAX_HORIZONTAL_CELLS}."
        )
    horizontal_cells = max(horizontal_cells, 16)
    dx = (right - left) / horizontal_cells
    nx, ny = horizontal_cells, vertical_cells
    node_count = (nx + 1) * (ny + 1)
    matrix = lil_matrix((node_count, node_count), dtype=float)
    top_owner = np.full(nx + 1, -1, dtype=int)
    x_values = left + np.arange(nx + 1, dtype=float) * dx
    for conductor, (center, width) in enumerate(zip(centers_m, widths_m)):
        owned = np.abs(x_values - center) <= width / 2.0 + dx * 0.25
        if int(np.count_nonzero(owned)) < 2:
            raise SiChannelError("Cross-section mesh resolves a trace with fewer than two boundary nodes.")
        if np.any(top_owner[owned] >= 0):
            raise SiChannelError("Cross-section mesh aliases the two conductors.")
        top_owner[owned] = conductor

    def node(i: int, j: int) -> int:
        return j * (nx + 1) + i

    dirichlet = np.zeros(node_count, dtype=bool)
    dirichlet[: nx + 1] = True
    for i, owner in enumerate(top_owner):
        if owner >= 0:
            dirichlet[node(i, ny)] = True
    for j in range(ny + 1):
        for i in range(nx + 1):
            row = node(i, j)
            if dirichlet[row]:
                matrix[row, row] = 1.0
            elif i == 0:
                matrix[row, row] = 1.0
                matrix[row, node(1, j)] = -1.0
            elif i == nx:
                matrix[row, row] = 1.0
                matrix[row, node(nx - 1, j)] = -1.0
            elif j == ny:
                matrix[row, row] = 1.0
                matrix[row, node(i, ny - 1)] = -1.0
            else:
                matrix[row, row] = 2.0 / (dx * dx) + 2.0 / (dy * dy)
                matrix[row, node(i - 1, j)] = -1.0 / (dx * dx)
                matrix[row, node(i + 1, j)] = -1.0 / (dx * dx)
                matrix[row, node(i, j - 1)] = -1.0 / (dy * dy)
                matrix[row, node(i, j + 1)] = -1.0 / (dy * dy)
    operator = matrix.tocsr()
    capacitance = np.zeros((2, 2), dtype=float)
    for excitation in range(2):
        if cancel_check is not None and cancel_check():
            raise SiChannelError("Coupled cross-section extraction was cancelled.")
        rhs = np.zeros(node_count, dtype=float)
        for i, owner in enumerate(top_owner):
            if owner >= 0:
                rhs[node(i, ny)] = 1.0 if owner == excitation else 0.0
        voltage = np.asarray(spsolve(operator, rhs), dtype=float)
        if not np.all(np.isfinite(voltage)):
            raise SiChannelError("Coupled cross-section solve produced non-finite potentials.")
        for conductor in range(2):
            indices = np.flatnonzero(top_owner == conductor)
            charge = 0.0
            for i in indices:
                boundary_weight = 0.5 if i in {indices[0], indices[-1]} else 1.0
                charge += boundary_weight * (voltage[node(i, ny)] - voltage[node(i, ny - 1)]) * dx / dy
            capacitance[conductor, excitation] = _EPSILON_0 * charge
    capacitance = 0.5 * (capacitance + capacitance.T)
    eigenvalues = np.linalg.eigvalsh(capacitance)
    if np.min(eigenvalues) <= 0 or capacitance[0, 1] >= 0:
        raise SiChannelError("Extracted Maxwell capacitance matrix failed passive coupled-line checks.")
    return capacitance, {
        "vertical_cells": ny,
        "horizontal_cells": nx,
        "node_count": node_count,
        "dx_m": dx,
        "dy_m": dy,
        "side_margin_m": margin,
    }


def extract_coupled_path_rlgc(
    design: DesignIRV2, request: Mapping[str, Any],
    *, cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    _validate_channel_request(request)
    path_mode = str(request.get("path_mode", "strict_uniform"))
    signal = _selector(str(request.get("signal_net", "")), design.nets, "Signal net")
    victim = _selector(str(request.get("victim_net", "")), design.nets, "Victim net")
    if signal.id == victim.id:
        raise SiChannelError("signal_net and victim_net must be distinct.")
    reference = _selector(str(request.get("reference_net", "")), design.nets, "Reference net")
    reference_layer = _selector(str(request.get("reference_layer", "")), design.layers, "Reference layer")
    signal_tracks = _path_for_net(
        design, signal, str(request.get("path_id", "")).strip(), path_mode=path_mode,
    )
    victim_tracks = _path_for_net(
        design, victim, str(request.get("victim_path_id", "")).strip(), path_mode=path_mode,
    )
    if signal_tracks[0].layer_id != victim_tracks[0].layer_id:
        raise SiChannelError("The bounded coupled paths must be on the same signal layer.")
    if path_mode == "strict_uniform":
        line_geometry = _coupled_geometry(signal_tracks, victim_tracks)
    else:
        line_geometry = _piecewise_coupled_geometry(
            signal_tracks,
            victim_tracks,
            separation_tolerance_mm=float(request["coupled_separation_tolerance_mm"]),
            skew_tolerance_mm=float(request["coupled_skew_tolerance_mm"]),
        )
    signal_layer = _selector(signal_tracks[0].layer_id, design.layers, "Signal layer")
    if signal_layer.id == reference_layer.id or reference_layer.layer_type != "copper":
        raise SiChannelError("The reference layer must be a distinct copper layer.")
    reference_zones = [
        zone for zone in design.zones
        if zone.net_id == reference.id and reference_layer.id in zone.layer_ids
    ]
    if len(reference_zones) != 1:
        raise SiChannelError("The bounded coupled channel requires exactly one reference zone.")
    for tracks in (signal_tracks, victim_tracks):
        if not _reference_zone_covers_path(reference_zones[0], tracks):
            raise SiChannelError("Both projected trace footprints must be fully covered by the reference zone.")

    material_by_id = {material.id: material for material in design.materials}
    lower, upper = sorted((signal_layer.order, reference_layer.order))
    dielectric_layers = [
        layer for layer in design.layers
        if lower < layer.order < upper and material_by_id.get(layer.material_id) is not None
    ]
    if not dielectric_layers:
        raise SiChannelError("No dielectric exists between the signal and reference layers.")
    permittivities = [material_by_id[layer.material_id].relative_permittivity for layer in dielectric_layers]
    if any(value is None or not isfinite(float(value)) or float(value) <= 1.0 for value in permittivities):
        raise SiChannelError("Every admitted dielectric requires finite relative permittivity above one.")
    epsilon_r = float(permittivities[0])
    if any(abs(float(value) - epsilon_r) > 1e-9 for value in permittivities[1:]):
        raise SiChannelError("Multiple dielectric permittivities require a more general field solve.")
    loss_values = [material_by_id[layer.material_id].loss_tangent for layer in dielectric_layers]
    loss_known = all(value is not None for value in loss_values)
    loss_tangent = float(np.mean([float(value) for value in loss_values])) if loss_known else 0.0
    if loss_tangent < 0 or not isfinite(loss_tangent):
        raise SiChannelError("Dielectric loss tangent must be finite and non-negative.")
    conductor = material_by_id.get(signal_layer.material_id)
    conductivity = float(conductor.conductivity_s_per_m or 0.0) if conductor else 0.0
    thickness_m = float(signal_layer.thickness_mm or 0.0) * 1e-3
    height_m = abs(float(reference_layer.z_mm) - float(signal_layer.z_mm)) * 1e-3
    if conductivity <= 0 or thickness_m <= 0 or height_m <= 0:
        raise SiChannelError("Conductor conductivity/thickness and reference spacing must be positive.")

    requested_cells = int(request.get("cross_section_vertical_cells", 24))
    if not MIN_VERTICAL_CELLS <= requested_cells <= MAX_VERTICAL_CELLS:
        raise SiChannelError(
            f"cross_section_vertical_cells must be {MIN_VERTICAL_CELLS}..{MAX_VERTICAL_CELLS}."
        )
    levels = sorted(set((requested_cells, int(round(requested_cells * 1.5)), requested_cells * 2)))
    levels = [min(level, MAX_VERTICAL_CELLS) for level in levels]
    vacuum_matrices: list[np.ndarray] = []
    mesh_levels: list[dict[str, Any]] = []
    centers_m = [line_geometry["signal_center_mm"] * 1e-3, line_geometry["victim_center_mm"] * 1e-3]
    widths_m = [line_geometry["signal_width_mm"] * 1e-3, line_geometry["victim_width_mm"] * 1e-3]
    for level in levels:
        matrix, mesh = _cross_section_capacitance(
            centers_m=centers_m, widths_m=widths_m, height_m=height_m,
            vertical_cells=level, cancel_check=cancel_check,
        )
        vacuum_matrices.append(matrix)
        mesh_levels.append(mesh)
    convergence = []
    for index in range(1, len(vacuum_matrices)):
        prior, current = vacuum_matrices[index - 1], vacuum_matrices[index]
        relative = float(np.linalg.norm(current - prior) / np.linalg.norm(current))
        convergence.append({
            "coarse_vertical_cells": mesh_levels[index - 1]["vertical_cells"],
            "fine_vertical_cells": mesh_levels[index]["vertical_cells"],
            "relative_matrix_change": relative,
        })
    vacuum_capacitance = vacuum_matrices[-1]
    capacitance = epsilon_r * vacuum_capacitance
    inductance = np.linalg.inv(vacuum_capacitance) / (_C0_M_PER_S * _C0_M_PER_S)
    resistance = np.diag([
        1.0 / (conductivity * width * thickness_m) for width in widths_m
    ])
    geometry = {
        "design_id": design.design_id,
        "signal_net_id": signal.id,
        "victim_net_id": victim.id,
        "reference_net_id": reference.id,
        "signal_layer_id": signal_layer.id,
        "reference_layer_id": reference_layer.id,
        "signal_track_ids": [track.id for track in signal_tracks],
        "victim_track_ids": [track.id for track in victim_tracks],
        "reference_zone_id": reference_zones[0].id,
        "length_m": line_geometry["length_mm"] * 1e-3,
        "signal_width_m": widths_m[0],
        "victim_width_m": widths_m[1],
        "center_separation_m": line_geometry["center_separation_mm"] * 1e-3,
        "edge_gap_m": line_geometry["edge_gap_mm"] * 1e-3,
        "reference_spacing_m": height_m,
        "path_mode": path_mode,
        "parallel_coextensive_verified": path_mode == "strict_uniform",
        "piecewise_parallel_pair_verified": path_mode == "piecewise_planar",
        "piecewise_approximation": (
            "length-weighted segment separation is reported; minimum observed center separation is applied over the longer retained path"
            if path_mode == "piecewise_planar" else None
        ),
        "piecewise_segment_evidence": line_geometry.get("piecewise_segment_evidence", []),
        "length_weighted_average_center_separation_mm": line_geometry.get("length_weighted_average_center_separation_mm"),
        "conservative_extraction_center_separation_mm": line_geometry.get("conservative_extraction_center_separation_mm"),
        "coupled_separation_tolerance_mm": line_geometry.get("coupled_separation_tolerance_mm"),
        "coupled_skew_tolerance_mm": line_geometry.get("coupled_skew_tolerance_mm"),
        "reference_zone_full_path_coverage_verified": True,
    }
    return {
        "contract": COUPLED_EXTRACTION_CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "geometry": geometry,
        "geometry_digest": _canonical_digest(geometry),
        "rlgc_per_m": {
            "resistance_ohm_per_m": resistance.tolist(),
            "inductance_h_per_m": inductance.tolist(),
            "capacitance_f_per_m": capacitance.tolist(),
            "vacuum_capacitance_f_per_m": vacuum_capacitance.tolist(),
            "loss_tangent": loss_tangent,
            "loss_tangent_known": loss_known,
        },
        "cross_section": {
            "formulation": "sparse_finite_difference_maxwell_capacitance",
            "boundary_policy": "ground_bottom; conductor_dirichlet_top; natural_outer",
            "levels": mesh_levels,
            "convergence": convergence,
            "latest_relative_matrix_change": convergence[-1]["relative_matrix_change"],
        },
        "qualification": {
            "state": "bounded_coupled_homogeneous_reference_solver" if path_mode == "strict_uniform" else "bounded_piecewise_planar_coupled_reference_solver",
            "execution_ready": True,
            "solver_ready": False,
            "production_qualified": False,
            "compliance_ready": False,
        },
        "limitations": [
            "two straight parallel coextensive planar traces only" if path_mode == "strict_uniform" else "piecewise planar paired traces with bounded separation/skew variation only",
            "single homogeneous dielectric and simple continuous reference polygon",
            "finite cross-section truncation with natural outer boundaries",
            "DC conductor resistance; no skin, proximity, roughness, dispersion, via, launch, connector, package, or radiation model",
            *([] if path_mode == "strict_uniform" else ["bend discontinuities and bend-local coupling are omitted; minimum observed separation is used over the longer path as an approximation, not a guaranteed NEXT/FEXT upper bound"]),
        ],
    }


def multiconductor_rlgc_network(
    extraction: Mapping[str, Any], frequencies_hz: Sequence[float], reference_impedance_ohm: float,
    *, cancel_check: Callable[[], bool] | None = None,
) -> NetworkData:
    frequencies = _frequency_grid(frequencies_hz)
    if not isfinite(reference_impedance_ohm) or reference_impedance_ohm <= 0:
        raise SiChannelError("reference_impedance_ohm must be positive and finite.")
    rlgc = extraction["rlgc_per_m"]
    resistance = np.asarray(rlgc["resistance_ohm_per_m"], dtype=float)
    inductance = np.asarray(rlgc["inductance_h_per_m"], dtype=float)
    capacitance = np.asarray(rlgc["capacitance_f_per_m"], dtype=float)
    if any(matrix.shape != (2, 2) for matrix in (resistance, inductance, capacitance)):
        raise SiChannelError("Coupled RLGC matrices must be 2 x 2.")
    loss_tangent = float(rlgc.get("loss_tangent", 0.0))
    length_m = float(extraction["geometry"]["length_m"])
    matrices = np.empty((len(frequencies), 4, 4), dtype=complex)
    identity2 = np.eye(2, dtype=complex)
    identity4 = np.eye(4, dtype=complex)
    root_reference = np.eye(4, dtype=complex) * np.sqrt(reference_impedance_ohm)
    for index, frequency in enumerate(frequencies):
        if cancel_check is not None and cancel_check():
            raise SiChannelError("Coupled SI network analysis was cancelled.")
        omega = 2.0 * pi * float(frequency)
        z_per_m = resistance.astype(complex) + 1j * omega * inductance
        y_per_m = (omega * loss_tangent + 1j * omega) * capacitance
        state = np.block([
            [np.zeros((2, 2), dtype=complex), -z_per_m],
            [-y_per_m, np.zeros((2, 2), dtype=complex)],
        ])
        transition = expm(state * length_m)
        t11, t12 = transition[:2, :2], transition[:2, 2:]
        t21, t22 = transition[2:, :2], transition[2:, 2:]
        try:
            inverse_t12 = np.linalg.solve(t12, identity2)
        except np.linalg.LinAlgError as exc:
            raise SiChannelError(f"Coupled line transition is singular at {frequency:g} Hz.") from exc
        terminal_y = np.block([
            [-inverse_t12 @ t11, inverse_t12],
            [-t21 + t22 @ inverse_t12 @ t11, -t22 @ inverse_t12],
        ])
        normalized_y = root_reference @ terminal_y @ root_reference
        try:
            matrices[index] = np.linalg.solve(
                (identity4 + normalized_y).T, (identity4 - normalized_y).T,
            ).T
        except np.linalg.LinAlgError as exc:
            raise SiChannelError(f"Coupled line S conversion is singular at {frequency:g} Hz.") from exc
    return NetworkData(
        frequencies_hz=frequencies,
        parameters=matrices,
        reference_impedance_ohm=np.repeat(float(reference_impedance_ohm), 4),
        parameter_kind="S",
        data_format="RI",
        source=f"DesignIR:{extraction['geometry']['design_id']}:{extraction['geometry_digest']}",
        warnings=["Bounded coupled geometry output is experimental and not protocol-compliance evidence."],
    )


def crosstalk_report(network: NetworkData, *, trace_limit: int = 2048) -> dict[str, Any]:
    if network.port_count != 4:
        raise SiChannelError("NEXT/FEXT topology requires the bounded four-port coupled network.")
    frequencies = np.asarray(network.frequencies_hz, dtype=float)
    s = network.s_parameters()
    indices = np.arange(len(frequencies))
    if len(indices) > trace_limit:
        indices = np.unique(np.linspace(0, len(indices) - 1, trace_limit).astype(int))

    def points(values: np.ndarray) -> list[dict[str, float]]:
        return [
            {
                "frequency_hz": float(frequencies[index]),
                "magnitude": float(abs(values[index])),
                "transfer_db": float(20.0 * log10(max(abs(values[index]), 1e-300))),
            }
            for index in indices
        ]

    next_values = s[:, 1, 0]
    fext_values = s[:, 3, 0]
    next_worst = int(np.argmax(np.abs(next_values)))
    fext_worst = int(np.argmax(np.abs(fext_values)))
    return {
        "contract": "spike/si-crosstalk-result/v1",
        "status": "completed",
        "model_status": "experimental",
        "port_order": ["aggressor.near", "victim.near", "aggressor.far", "victim.far"],
        "mapping": {
            "next": "S(victim.near, aggressor.near)",
            "fext": "S(victim.far, aggressor.near)",
        },
        "next": {
            "trace": points(next_values),
            "worst_transfer_db": float(20.0 * log10(max(abs(next_values[next_worst]), 1e-300))),
            "worst_frequency_hz": float(frequencies[next_worst]),
        },
        "fext": {
            "trace": points(fext_values),
            "worst_transfer_db": float(20.0 * log10(max(abs(fext_values[fext_worst]), 1e-300))),
            "worst_frequency_hz": float(frequencies[fext_worst]),
        },
        "geometry_or_field_coupling_claimed": True,
        "production_qualified": False,
    }


def _differential_subnetwork(network: NetworkData) -> tuple[NetworkData, dict[str, Any]]:
    """Extract the differential near/far two-port from the bounded 4-port pair."""

    if network.port_count != 4:
        raise SiChannelError("Differential signaling requires the bounded four-port coupled network.")
    if not np.allclose(network.reference_impedance_ohm, network.reference_impedance_ohm[0]):
        raise SiChannelError("Differential mixed-mode extraction requires equal real single-ended reference impedances.")
    mixed = single_ended_to_mixed_mode(network.s_parameters())
    single_ended_reference = float(network.reference_impedance_ohm[0])
    differential_reference = 2.0 * single_ended_reference
    differential = NetworkData(
        frequencies_hz=np.asarray(network.frequencies_hz, dtype=float),
        parameters=mixed[:, :2, :2],
        reference_impedance_ohm=np.asarray([differential_reference, differential_reference]),
        parameter_kind="S",
        data_format="RI",
        source=f"{network.source}:mixed-mode-differential",
        warnings=[
            "Differential subnetwork is an equal-reference orthonormal mixed-mode transform of the bounded four-port channel.",
        ],
    )
    return differential, {
        "port_order": ["differential.near", "differential.far", "common.near", "common.far"],
        "differential_subnetwork_ports": ["differential.near", "differential.far"],
        "single_ended_reference_impedance_ohm": single_ended_reference,
        "differential_reference_impedance_ohm": differential_reference,
        "wave_definition": "equal-reference orthonormal transform; differential reference is twice each equal single-ended reference",
    }


def _differential_report(
    network: NetworkData, request: Mapping[str, Any], *, trace_limit: int,
    cancel_check: Callable[[], bool] | None,
) -> dict[str, Any]:
    differential, transform = _differential_subnetwork(network)
    network_report = analyze_network(differential, trace_limit=trace_limit)
    time_report = time_domain_report(differential, incident_port=0, observed_port=1)
    eye = None
    if request.get("bit_rate_hz") is not None:
        eye = normalized_nrz_eye(
            differential, bit_rate_hz=float(request["bit_rate_hz"]),
            bit_count=int(request.get("bit_count", 1024)), source_port=0, sink_port=1,
            cancel_check=cancel_check,
        )
        statistical_model = request.get("statistical_eye_model")
        if statistical_model is not None:
            from .si_statistical_eye import statistical_nrz_eye

            eye["statistical"] = statistical_nrz_eye(
                differential,
                bit_rate_hz=float(request["bit_rate_hz"]),
                bit_count=int(request.get("bit_count", 1024)), model=statistical_model,
                source_port=0, sink_port=1, cancel_check=cancel_check,
            )
    return {
        "contract": "spike/si-differential-channel/v1",
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "transform": transform,
        "network": network_report,
        "time_domain": time_report,
        "eye": eye,
        "limitations": [
            "mixed-mode extraction retains only the differential-to-differential two-port; mode conversion remains in the parent four-port report",
            "the bounded piecewise/straight coupled-line model remains experimental and is not protocol-compliance evidence",
        ],
    }


def analyze_coupled_design_channel(
    design: DesignIRV2, request: Mapping[str, Any],
    *, cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    _validate_channel_request(request)
    frequencies = _frequency_grid(request.get("frequencies_hz"))
    extraction = extract_coupled_path_rlgc(design, request, cancel_check=cancel_check)
    network = multiconductor_rlgc_network(
        extraction, frequencies, float(request.get("reference_impedance_ohm", 50.0)),
        cancel_check=cancel_check,
    )
    trace_limit = int(request.get("trace_limit", 2048))
    network_report = analyze_network(network, trace_limit=trace_limit)
    network_report["port_order"] = ["aggressor.near", "victim.near", "aggressor.far", "victim.far"]
    time_report = time_domain_report(network, incident_port=0, observed_port=2)
    eye = None
    if request.get("bit_rate_hz") is not None:
        eye = normalized_nrz_eye(
            network, bit_rate_hz=float(request["bit_rate_hz"]),
            bit_count=int(request.get("bit_count", 1024)), source_port=0, sink_port=2,
            cancel_check=cancel_check,
        )
        statistical_model = request.get("statistical_eye_model")
        if statistical_model is not None:
            from .si_statistical_eye import statistical_nrz_eye

            eye["statistical"] = statistical_nrz_eye(
                network,
                bit_rate_hz=float(request["bit_rate_hz"]),
                bit_count=int(request.get("bit_count", 1024)),
                model=statistical_model,
                source_port=0,
                sink_port=2,
                cancel_check=cancel_check,
            )
    crosstalk = crosstalk_report(network, trace_limit=trace_limit)
    if "crosstalk_model" in request:
        from .si_crosstalk import analyze_crosstalk

        crosstalk["loaded"] = analyze_crosstalk(network, cancel_check=cancel_check, **request["crosstalk_model"])
    differential = None
    if request.get("signaling", "single_ended") == "differential":
        differential = _differential_report(
            network, request, trace_limit=trace_limit, cancel_check=cancel_check,
        )
        time_report = differential["time_domain"]
        eye = differential["eye"]
    time_samples = 2 * len(frequencies) - 1
    eye_samples = int(eye.get("waveform_samples", 0)) if eye else 0
    loaded_samples = len((request.get("crosstalk_model") or {}).get("waveform_v") or [])
    return {
        "contract": RESULT_CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "extraction": extraction,
        "network": network_report,
        "time_domain": time_report,
        "eye": eye,
        "crosstalk": crosstalk,
        "differential": differential,
        "resource_admission": {
            "frequency_points": len(frequencies),
            "time_domain_samples": time_samples,
            "eye_waveform_samples": eye_samples,
            "loaded_crosstalk_waveform_samples": loaded_samples,
            "estimated_numeric_bytes": int(len(frequencies) * 16 * 16 + time_samples * 5 * 8 + eye_samples * 24 + loaded_samples * 128),
            "hard_limits": {
                "frequency_points": MAX_FREQUENCY_POINTS,
                "eye_bits": MAX_EYE_BITS,
                "loaded_crosstalk_frequency_points": 8193,
                "loaded_crosstalk_waveform_samples": 65536,
                "cross_section_vertical_cells": MAX_VERTICAL_CELLS,
                "cross_section_horizontal_cells": MAX_HORIZONTAL_CELLS,
            },
            "cooperative_cancellation_supported": True,
        },
        "provenance": {
            "implementation": "SPIKE independent sparse cross-section and multiconductor telegrapher reference solver",
            "design_contract": design.contract,
            "design_id": design.design_id,
            "request_digest": _canonical_digest(dict(request)),
            "reference_wave_definition": "pseudo-wave with equal real positive reference impedances",
            "production_solver_target": "SPIKES isolated process boundary",
        },
        "release_gate": {
            "state": "experimental_bounded_geometry",
            "required_before_promotion": [
                "packaged SPIKES process implementation and source/package parity",
                "three-level cross-section and frequency convergence acceptance",
                "independent 2-D/3-D field-solver comparison",
                "measured four-port VNA and TDR coupled-line coupon correlation with uncertainty",
                "source/package/connector and statistical receiver models for BER or protocol decisions",
            ],
        },
    }


__all__ = [
    "COUPLED_EXTRACTION_CONTRACT", "analyze_coupled_design_channel",
    "crosstalk_report", "extract_coupled_path_rlgc", "multiconductor_rlgc_network",
]
