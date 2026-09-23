"""Bounded geometry-derived signal-integrity channel analysis.

This module deliberately starts with a narrow, inspectable geometry envelope:
one straight, constant-width DesignIR v2 conductor path above one explicit
reference layer.  It produces a uniform quasi-TEM RLGC model, a reciprocal
two-port network, explicit TDR/TDT transforms, and a normalized NRZ eye.  The
formulation is independently implemented from the multiconductor telegrapher
equations; it is experimental until independent and measured validation closes
the release gate.
"""

from __future__ import annotations

from hashlib import sha256
from math import atan2, degrees, erfc, isfinite, pi, sqrt
import json
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .design_ir_v2 import DesignIRV2
from .hybrid_mesh import _segment_inside_polygon
from .quasistatic_capacitance import estimate_line_capacitance_per_m
from .sparameters import NetworkData, analyze_network
from .si_symbol_clock import sample_nrz_clock


REQUEST_CONTRACT = "spike/si-uniform-channel-request/v1"
EXTRACTION_CONTRACT = "spike/si-uniform-path-extraction/v1"
RESULT_CONTRACT = "spike/si-channel-result/v1"
MAX_FREQUENCY_POINTS = 32769
MAX_EYE_BITS = 8192
MAX_EYE_WAVEFORM_SAMPLES = 1_048_576
MAX_EYE_FFT_POINTS = 2_097_152
_C0_M_PER_S = 299_792_458.0


class SiChannelError(ValueError):
    """Raised when a channel would require guessing geometry or processing."""


_REQUEST_KEYS = {
    "contract", "channel_id", "signal_net", "victim_net", "reference_net",
    "reference_layer", "path_id", "victim_path_id", "path_mode",
    "cross_section_vertical_cells", "coupled_separation_tolerance_mm",
    "coupled_skew_tolerance_mm", "reference_impedance_ohm", "frequencies_hz",
    "bit_rate_hz", "bit_count", "statistical_eye_model", "trace_limit",
    "signaling", "pam4_model", "symbol_rate_hz", "symbol_count", "crosstalk_model",
}


def _validate_channel_request(request: Mapping[str, Any]) -> None:
    """Reject unsupported SI controls instead of silently ignoring them."""

    if not isinstance(request, Mapping):
        raise SiChannelError("SI channel request must be an object.")
    if request.get("contract") != REQUEST_CONTRACT:
        raise SiChannelError(f"Expected {REQUEST_CONTRACT}.")
    unknown = set(request) - _REQUEST_KEYS
    if unknown:
        raise SiChannelError(f"SI channel request has unknown fields: {sorted(unknown)}.")
    path_mode = request.get("path_mode", "strict_uniform")
    if path_mode not in {"strict_uniform", "piecewise_planar"}:
        raise SiChannelError("path_mode must be strict_uniform or piecewise_planar.")
    signaling = request.get("signaling", "single_ended")
    if signaling not in {"single_ended", "differential"}:
        raise SiChannelError("signaling must be single_ended or differential.")
    if signaling == "differential" and not str(request.get("victim_net", "")).strip():
        raise SiChannelError("Differential signaling requires an explicit victim_net partner.")
    if "crosstalk_model" in request:
        from .si_crosstalk import validate_model

        if not str(request.get("victim_net", "")).strip():
            raise SiChannelError("Loaded crosstalk requires an explicit victim_net.")
        validate_model(request["crosstalk_model"])
        if len(request.get("frequencies_hz", [])) > 8193:
            raise SiChannelError("Loaded crosstalk admits at most 8193 frequency points.")
    if path_mode == "piecewise_planar" and str(request.get("victim_net", "")).strip():
        for key in ("coupled_separation_tolerance_mm", "coupled_skew_tolerance_mm"):
            value = request.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)) or float(value) < 0:
                raise SiChannelError(f"{key} must be an explicit finite non-negative value for a coupled piecewise path.")


def _canonical_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _selector(value: str, records: Sequence[Any], kind: str) -> Any:
    matches = [record for record in records if value in {record.id, record.name, record.source_id}]
    if len(matches) != 1:
        raise SiChannelError(f"{kind} selector {value!r} resolved to {len(matches)} records; exactly one is required.")
    return matches[0]


def _point_key(point: Sequence[float]) -> tuple[float, float]:
    return (round(float(point[0]), 12), round(float(point[1]), 12))


def _ordered_open_path(tracks: Sequence[Any], *, require_straight: bool) -> list[Any]:
    adjacency: dict[tuple[float, float], list[int]] = {}
    for index, track in enumerate(tracks):
        start = _point_key(track.start_mm)
        end = _point_key(track.end_mm)
        if start == end:
            raise SiChannelError(f"Track {track.id} has zero length.")
        adjacency.setdefault(start, []).append(index)
        adjacency.setdefault(end, []).append(index)
    endpoints = [point for point, edges in adjacency.items() if len(edges) == 1]
    if len(endpoints) != 2 or any(len(edges) > 2 for edges in adjacency.values()):
        raise SiChannelError("The selected signal path must be one unbranched open chain.")
    ordered: list[Any] = []
    used: set[int] = set()
    cursor = endpoints[0]
    while len(used) < len(tracks):
        candidates = [index for index in adjacency[cursor] if index not in used]
        if len(candidates) != 1:
            raise SiChannelError("The selected signal path is disconnected or ambiguous.")
        index = candidates[0]
        used.add(index)
        track = tracks[index]
        ordered.append(track)
        start, end = _point_key(track.start_mm), _point_key(track.end_mm)
        cursor = end if cursor == start else start
    if cursor != endpoints[1]:
        raise SiChannelError("The selected signal path did not terminate at the second endpoint.")
    if require_straight:
        first = ordered[0]
        base = np.asarray(first.end_mm, dtype=float) - np.asarray(first.start_mm, dtype=float)
        base /= np.linalg.norm(base)
        origin = np.asarray(first.start_mm, dtype=float)
        for track in ordered:
            for point in (track.start_mm, track.end_mm):
                delta = np.asarray(point, dtype=float) - origin
                if abs(float(base[0] * delta[1] - base[1] * delta[0])) > 1e-9:
                    raise SiChannelError("The strict_uniform channel envelope admits only a straight path without bends.")
    return ordered


def _ordered_straight_path(tracks: Sequence[Any]) -> list[Any]:
    return _ordered_open_path(tracks, require_straight=True)


def _piecewise_bend_evidence(tracks: Sequence[Any]) -> list[dict[str, Any]]:
    """Describe, but do not hide, discontinuities omitted by the line model."""

    bends: list[dict[str, Any]] = []
    for prior, current in zip(tracks, tracks[1:]):
        prior_points = {_point_key(prior.start_mm): prior.start_mm, _point_key(prior.end_mm): prior.end_mm}
        current_points = {_point_key(current.start_mm): current.start_mm, _point_key(current.end_mm): current.end_mm}
        shared = set(prior_points) & set(current_points)
        if len(shared) != 1:
            raise SiChannelError("The piecewise path has an ambiguous bend vertex.")
        vertex_key = next(iter(shared))
        vertex = np.asarray(prior_points[vertex_key], dtype=float)
        prior_other = np.asarray(next(value for key, value in prior_points.items() if key != vertex_key), dtype=float)
        current_other = np.asarray(next(value for key, value in current_points.items() if key != vertex_key), dtype=float)
        prior_vector = vertex - prior_other
        current_vector = current_other - vertex
        prior_vector /= np.linalg.norm(prior_vector)
        current_vector /= np.linalg.norm(current_vector)
        angle = degrees(atan2(
            float(prior_vector[0] * current_vector[1] - prior_vector[1] * current_vector[0]),
            float(np.dot(prior_vector, current_vector)),
        ))
        if abs(angle) > 1e-7:
            bends.append({
                "vertex_mm": [float(value) for value in vertex],
                "turn_angle_deg": float(angle),
                "adjacent_track_ids": [prior.id, current.id],
                "treatment": "distributed-line length retained; bend discontinuity omitted",
            })
    return bends


def _frequency_grid(value: Any) -> np.ndarray:
    frequencies = np.asarray(value, dtype=float)
    if frequencies.ndim != 1 or not 3 <= len(frequencies) <= MAX_FREQUENCY_POINTS:
        raise SiChannelError(f"frequencies_hz must contain 3..{MAX_FREQUENCY_POINTS} values.")
    if not np.all(np.isfinite(frequencies)) or frequencies[0] != 0.0 or np.any(np.diff(frequencies) <= 0):
        raise SiChannelError("frequencies_hz must start at DC and be finite and strictly increasing.")
    spacing = np.diff(frequencies)
    if not np.allclose(spacing, spacing[0], rtol=1e-9, atol=max(float(spacing[0]) * 1e-12, 1e-9)):
        raise SiChannelError("TDR/TDT and eye analysis require an explicitly uniform frequency grid.")
    return frequencies


def _reference_zone_covers_path(zone: Any, tracks: Sequence[Any]) -> bool:
    """Prove the projected trace footprint stays inside one simple zone.

    The first envelope intentionally rejects zone unions, holes, and curved
    exact-boundary records.  Those cases need a union/clearance geometry
    kernel rather than optimistic endpoint sampling.
    """

    if zone.boundary_rings or zone.holes_mm or len(zone.outlines_mm) != 1:
        raise SiChannelError(
            "The bounded SI channel requires one simple polygonal reference zone without holes."
        )
    polygon = [tuple(map(float, point)) for point in zone.outlines_mm[0]]
    if len(polygon) < 3:
        raise SiChannelError("The reference-zone polygon requires at least three vertices.")
    tolerance_mm = 1e-9
    for track in tracks:
        start = np.asarray(track.start_mm, dtype=float)
        end = np.asarray(track.end_mm, dtype=float)
        direction = end - start
        length = float(np.linalg.norm(direction))
        if length <= 0:
            return False
        normal = np.asarray([-direction[1], direction[0]], dtype=float) / length
        half_width = float(track.width_mm) / 2.0
        for offset in (-half_width, 0.0, half_width):
            shifted_start = tuple(start + normal * offset)
            shifted_end = tuple(end + normal * offset)
            if not _segment_inside_polygon(shifted_start, shifted_end, polygon, tolerance_mm):
                return False
    return True


def extract_uniform_path_rlgc(design: DesignIRV2, request: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a bounded straight single-reference quasi-TEM channel."""

    _validate_channel_request(request)
    path_mode = str(request.get("path_mode", "strict_uniform"))
    net = _selector(str(request.get("signal_net", "")), design.nets, "Signal net")
    reference_layer = _selector(str(request.get("reference_layer", "")), design.layers, "Reference layer")
    reference_net = _selector(str(request.get("reference_net", "")), design.nets, "Reference net")
    path_id = str(request.get("path_id", "")).strip()
    tracks = [track for track in design.tracks if track.net_id == net.id]
    if path_id:
        tracks = [track for track in tracks if track.path is not None and track.path.path_id == path_id]
    if not tracks:
        raise SiChannelError("No canonical track geometry matched the selected signal path.")
    if any(arc.net_id == net.id for arc in design.arcs):
        raise SiChannelError("Arcs are outside the first straight uniform-channel envelope.")
    if any(via.net_id == net.id for via in design.vias):
        raise SiChannelError("Vias are outside the first straight uniform-channel envelope.")
    if len({track.layer_id for track in tracks}) != 1 or len({round(track.width_mm, 12) for track in tracks}) != 1:
        raise SiChannelError("The selected path must retain one signal layer and one constant width.")
    ordered = _ordered_open_path(tracks, require_straight=path_mode == "strict_uniform")
    signal_layer = _selector(ordered[0].layer_id, design.layers, "Signal layer")
    if signal_layer.id == reference_layer.id or reference_layer.layer_type != "copper":
        raise SiChannelError("The reference layer must be a distinct canonical copper layer.")

    reference_zones = [
        zone for zone in design.zones
        if zone.net_id == reference_net.id and reference_layer.id in zone.layer_ids
    ]
    if not reference_zones:
        raise SiChannelError("The explicit reference net has no retained zone on the selected reference layer.")
    if len(reference_zones) != 1:
        raise SiChannelError("The bounded SI channel requires exactly one unambiguous reference zone.")
    if not _reference_zone_covers_path(reference_zones[0], ordered):
        raise SiChannelError("The projected signal-trace footprint is not fully covered by the reference zone.")

    lower, upper = sorted((signal_layer.order, reference_layer.order))
    material_by_id = {material.id: material for material in design.materials}
    dielectric_layers = [
        layer for layer in design.layers
        if lower < layer.order < upper
        and (material_by_id.get(layer.material_id) is not None)
        and material_by_id[layer.material_id].relative_permittivity is not None
    ]
    if not dielectric_layers:
        raise SiChannelError("No dielectric material with relative permittivity exists between signal and reference layers.")
    permittivities = [float(material_by_id[layer.material_id].relative_permittivity) for layer in dielectric_layers]
    if any(value <= 1.0 or not isfinite(value) for value in permittivities):
        raise SiChannelError("Dielectric relative permittivity must be finite and greater than one.")
    if max(permittivities) - min(permittivities) > 1e-9:
        raise SiChannelError("Multiple dielectric permittivities require a field solve and are outside the uniform envelope.")
    epsilon_r = permittivities[0]
    loss_values = [material_by_id[layer.material_id].loss_tangent for layer in dielectric_layers]
    loss_known = all(value is not None for value in loss_values)
    loss_tangent = float(sum(float(value) for value in loss_values) / len(loss_values)) if loss_known else 0.0
    if loss_tangent < 0 or not isfinite(loss_tangent):
        raise SiChannelError("Dielectric loss tangent must be finite and non-negative.")

    height_m = abs(float(reference_layer.z_mm) - float(signal_layer.z_mm)) * 1e-3
    width_m = float(ordered[0].width_mm) * 1e-3
    thickness_m = float(signal_layer.thickness_mm or 0.0) * 1e-3
    signal_material = material_by_id.get(signal_layer.material_id)
    conductivity = float(signal_material.conductivity_s_per_m or 0.0) if signal_material else 0.0
    if height_m <= 0 or width_m <= 0 or thickness_m <= 0 or conductivity <= 0:
        raise SiChannelError("Signal/reference spacing, trace width/thickness, and conductor conductivity must be positive.")

    length_m = sum(
        float(np.linalg.norm(np.asarray(track.end_mm, dtype=float) - np.asarray(track.start_mm, dtype=float))) * 1e-3
        for track in ordered
    )
    capacitance_per_m = estimate_line_capacitance_per_m(width_m * 1e3, height_m * 1e3, epsilon_r)
    air_capacitance_per_m = estimate_line_capacitance_per_m(width_m * 1e3, height_m * 1e3, 1.0)
    effective_epsilon = capacitance_per_m / air_capacitance_per_m
    velocity_m_per_s = _C0_M_PER_S / sqrt(effective_epsilon)
    inductance_per_m = 1.0 / (velocity_m_per_s * velocity_m_per_s * capacitance_per_m)
    resistance_per_m = 1.0 / (conductivity * width_m * thickness_m)
    characteristic_impedance = sqrt(inductance_per_m / capacitance_per_m)
    bends = _piecewise_bend_evidence(ordered) if path_mode == "piecewise_planar" else []
    geometry = {
        "design_id": design.design_id,
        "signal_net_id": net.id,
        "reference_net_id": reference_net.id,
        "signal_layer_id": signal_layer.id,
        "reference_layer_id": reference_layer.id,
        "track_ids": [track.id for track in ordered],
        "reference_zone_ids": [zone.id for zone in reference_zones],
        "path_id": path_id,
        "length_m": length_m,
        "width_m": width_m,
        "thickness_m": thickness_m,
        "reference_spacing_m": height_m,
        "path_mode": path_mode,
        "uniform_cross_section_verified": True,
        "straight_path_verified": path_mode == "strict_uniform",
        "piecewise_planar_path_verified": path_mode == "piecewise_planar",
        "bend_evidence": bends,
        "reference_zone_declared": True,
        "reference_zone_full_path_coverage_verified": True,
    }
    return {
        "contract": EXTRACTION_CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "geometry": geometry,
        "geometry_digest": _canonical_digest(geometry),
        "rlgc_per_m": {
            "resistance_ohm_per_m": resistance_per_m,
            "inductance_h_per_m": inductance_per_m,
            "capacitance_f_per_m": capacitance_per_m,
            "loss_tangent": loss_tangent,
            "loss_tangent_known": loss_known,
        },
        "derived": {
            "effective_relative_permittivity": effective_epsilon,
            "lossless_characteristic_impedance_ohm": characteristic_impedance,
            "lossless_velocity_m_per_s": velocity_m_per_s,
            "lossless_delay_s": length_m / velocity_m_per_s,
        },
        "qualification": {
            "state": "bounded_uniform_single_reference_geometry_only" if path_mode == "strict_uniform" else "bounded_piecewise_planar_single_reference_geometry",
            "production_qualified": False,
            "execution_ready": True,
            "solver_ready": False,
            "compliance_ready": False,
        },
        "limitations": [
            "single straight constant-width planar path only" if path_mode == "strict_uniform" else "piecewise planar constant-width path; each segment uses one shared quasi-TEM cross-section",
            "single homogeneous dielectric and one simple polygonal reference zone without holes",
            "reference-zone coverage proves only the projected trace footprint, not return-current density",
            "quasi-static zero-thickness Hammerstad-Jensen capacitance approximation",
            "DC conductor resistance only; skin, proximity, roughness, dispersion, vias, launches, and connectors are excluded",
            *([] if path_mode == "strict_uniform" else ["bend discontinuities, corner radiation, and bend-local coupling are omitted; total centerline length is retained"]),
        ],
    }


def uniform_rlgc_network(
    extraction: Mapping[str, Any], frequencies_hz: Sequence[float], reference_impedance_ohm: float,
    *, cancel_check: Callable[[], bool] | None = None,
) -> NetworkData:
    frequencies = _frequency_grid(frequencies_hz)
    if not isfinite(reference_impedance_ohm) or reference_impedance_ohm <= 0:
        raise SiChannelError("reference_impedance_ohm must be positive and finite.")
    geometry = extraction.get("geometry") if isinstance(extraction.get("geometry"), Mapping) else {}
    values = extraction.get("rlgc_per_m") if isinstance(extraction.get("rlgc_per_m"), Mapping) else {}
    length_m = float(geometry.get("length_m", 0.0))
    resistance = float(values.get("resistance_ohm_per_m", -1.0))
    inductance = float(values.get("inductance_h_per_m", 0.0))
    capacitance = float(values.get("capacitance_f_per_m", 0.0))
    loss_tangent = float(values.get("loss_tangent", 0.0))
    if length_m <= 0 or resistance < 0 or inductance <= 0 or capacitance <= 0 or loss_tangent < 0:
        raise SiChannelError("Extracted length and RLGC values are outside the passive uniform-line domain.")
    matrices = np.empty((len(frequencies), 2, 2), dtype=complex)
    z0 = float(reference_impedance_ohm)
    for index, frequency in enumerate(frequencies):
        if cancel_check is not None and cancel_check():
            raise SiChannelError("SI channel analysis was cancelled.")
        omega = 2.0 * pi * float(frequency)
        z_total = complex(resistance, omega * inductance) * length_m
        y_total = complex(omega * capacitance * loss_tangent, omega * capacitance) * length_m
        gamma_length = np.sqrt(z_total * y_total)
        sinhc = 1.0 + 0j if abs(gamma_length) < 1e-14 else np.sinh(gamma_length) / gamma_length
        a = np.cosh(gamma_length)
        b = z_total * sinhc
        c = y_total * sinhc
        denominator = 2.0 * a + b / z0 + c * z0
        if abs(denominator) < 1e-18:
            raise SiChannelError(f"Uniform-line S conversion is singular at {frequency:g} Hz.")
        determinant = a * a - b * c
        matrices[index, 0, 0] = (b / z0 - c * z0) / denominator
        matrices[index, 1, 1] = matrices[index, 0, 0]
        matrices[index, 1, 0] = 2.0 / denominator
        matrices[index, 0, 1] = 2.0 * determinant / denominator
    return NetworkData(
        frequencies_hz=frequencies,
        parameters=matrices,
        reference_impedance_ohm=np.asarray([z0, z0]),
        parameter_kind="S",
        data_format="RI",
        source=f"DesignIR:{geometry.get('design_id', '')}:{extraction.get('geometry_digest', '')}",
        warnings=["Geometry-derived uniform-channel output is experimental and not protocol-compliance evidence."],
    )


def _real_impulse(values: np.ndarray) -> np.ndarray:
    positive = np.asarray(values, dtype=complex).copy()
    if abs(positive[0].imag) > 1e-9:
        raise SiChannelError("The DC network sample must be real for a real TDR/TDT transform.")
    positive[0] = positive[0].real
    spectrum = np.concatenate((positive, np.conjugate(positive[-1:0:-1])))
    impulse = np.fft.ifft(spectrum)
    imaginary_residue = float(np.max(np.abs(impulse.imag)))
    if imaginary_residue > 1e-9:
        raise SiChannelError("Hermitian time-domain construction retained excessive imaginary residue.")
    return impulse.real


def time_domain_report(
    network: NetworkData, *, incident_port: int = 0, observed_port: int = 1,
) -> dict[str, Any]:
    frequencies = _frequency_grid(network.frequencies_hz)
    s = network.s_parameters()
    if network.port_count < 2:
        raise SiChannelError("TDR/TDT channel analysis requires at least two ports.")
    if not (0 <= incident_port < network.port_count and 0 <= observed_port < network.port_count):
        raise SiChannelError("TDR/TDT port indices are outside the network.")
    sample_count = 2 * len(frequencies) - 1
    delta_f = float(frequencies[1] - frequencies[0])
    delta_t = 1.0 / (sample_count * delta_f)
    reflection_impulse = _real_impulse(s[:, incident_port, incident_port])
    transmission_impulse = _real_impulse(s[:, observed_port, incident_port])
    reflection_step = np.cumsum(reflection_impulse)
    transmission_step = np.cumsum(transmission_impulse)
    reference = float(network.reference_impedance_ohm[incident_port])
    denominator = 1.0 - reflection_step
    impedance = np.full_like(reflection_step, np.nan)
    valid = np.abs(denominator) > 1e-9
    impedance[valid] = reference * (1.0 + reflection_step[valid]) / denominator[valid]
    time_s = np.arange(sample_count, dtype=float) * delta_t
    return {
        "contract": "spike/si-time-domain/v1",
        "status": "completed",
        "model_status": "experimental",
        "processing": {
            "incident_port_index": incident_port,
            "observed_port_index": observed_port,
            "dc_policy": "explicit_required",
            "grid_policy": "uniform_required",
            "window": "none",
            "padding": "none",
            "spectrum": "explicit_hermitian",
            "sample_count": sample_count,
            "delta_t_s": delta_t,
            "bandwidth_hz": float(frequencies[-1]),
        },
        "tdr": [
            {"time_s": float(t), "reflection": float(rho), "impedance_ohm": None if not np.isfinite(z) else float(z)}
            for t, rho, z in zip(time_s, reflection_step, impedance)
        ],
        "tdt": [
            {"time_s": float(t), "normalized_step": float(value)}
            for t, value in zip(time_s, transmission_step)
        ],
        "limitations": [
            "finite-bandwidth unwindowed reconstruction",
            "no extrapolated DC, resampling, delay removal, gating, or de-embedding",
        ],
    }


def _prbs7(count: int) -> np.ndarray:
    state = 0x7F
    bits = np.empty(count, dtype=np.int8)
    for index in range(count):
        bits[index] = state & 1
        feedback = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) & 0x7E) | feedback
    return bits


def _fft_convolve_prefix(signal: np.ndarray, impulse: np.ndarray) -> np.ndarray:
    output_size = len(signal) + len(impulse) - 1
    fft_size = 1 << (output_size - 1).bit_length()
    if fft_size > MAX_EYE_FFT_POINTS:
        raise SiChannelError(
            f"The eye convolution needs {fft_size} FFT points; the hard limit is {MAX_EYE_FFT_POINTS}."
        )
    transformed = np.fft.rfft(signal, fft_size) * np.fft.rfft(impulse, fft_size)
    return np.fft.irfft(transformed, fft_size)[: len(signal)]


def normalized_nrz_eye(
    network: NetworkData, *, bit_rate_hz: float, bit_count: int = 1024,
    source_port: int = 0, sink_port: int = 1,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not isfinite(bit_rate_hz) or bit_rate_hz <= 0:
        raise SiChannelError("bit_rate_hz must be positive and finite.")
    if not 128 <= bit_count <= MAX_EYE_BITS:
        raise SiChannelError(f"bit_count must be 128..{MAX_EYE_BITS}.")
    frequencies = _frequency_grid(network.frequencies_hz)
    if not (0 <= source_port < network.port_count and 0 <= sink_port < network.port_count):
        raise SiChannelError("Eye source/sink port indices are outside the network.")
    impulse = _real_impulse(network.s_parameters()[:, sink_port, source_port])
    delta_t = 1.0 / ((2 * len(frequencies) - 1) * float(frequencies[1] - frequencies[0]))
    actual_samples_per_ui = 1.0 / (bit_rate_hz * delta_t)
    samples_per_ui = int(round(actual_samples_per_ui))
    if actual_samples_per_ui < 8 - 1e-9:
        raise SiChannelError("The frequency grid provides fewer than eight time samples per unit interval.")
    represented_rate = float(bit_rate_hz)
    bits = _prbs7(bit_count)
    waveform_samples = int(np.ceil(bit_count * actual_samples_per_ui))
    if waveform_samples > MAX_EYE_WAVEFORM_SAMPLES:
        raise SiChannelError(
            f"The eye waveform needs {waveform_samples} samples; the hard limit is {MAX_EYE_WAVEFORM_SAMPLES}."
        )
    if cancel_check is not None and cancel_check():
        raise SiChannelError("SI eye analysis was cancelled.")
    time_s = np.arange(waveform_samples) * delta_t
    waveform = sample_nrz_clock(bits, time_s, bit_rate_hz,
                               {"low_v": -.5, "high_v": .5, "delay_s": 0.,
                                "rise_time_s": 0., "fall_time_s": 0.})
    response = _fft_convolve_prefix(waveform, impulse)
    if cancel_check is not None and cancel_check():
        raise SiChannelError("SI eye analysis was cancelled.")
    delay_samples = int(np.argmax(np.abs(impulse)))
    high: list[float] = []
    low: list[float] = []
    # The Hermitian impulse buffer spans the complete periodic transform, not
    # the physical settling duration.  Align to its dominant cursor and retain
    # a fixed PRBS warm-up instead of discarding one full FFT record.
    start_bit = 16
    for index in range(start_bit, bit_count - 2):
        if cancel_check is not None and index % 64 == 0 and cancel_check():
            raise SiChannelError("SI eye analysis was cancelled.")
        sample_time = (index + .5) / bit_rate_hz + delay_samples * delta_t
        if sample_time > time_s[-1]:
            break
        (high if bits[index] else low).append(float(np.interp(sample_time, time_s, response)))
    if not high or not low:
        raise SiChannelError("The requested eye record is too short after channel settling.")
    eye_height = min(high) - max(low)
    midpoint = 0.5 * (float(np.mean(high)) + float(np.mean(low)))
    noise_sigma = 0.5 * (float(np.std(high)) + float(np.std(low)))
    q_factor = eye_height / (2.0 * noise_sigma) if noise_sigma > 0 else float("inf") if eye_height > 0 else 0.0
    ber_estimate = 0.5 * erfc(q_factor / sqrt(2.0)) if isfinite(q_factor) else 0.0
    phase_bins = min(samples_per_ui, 256)
    stride = max(1, samples_per_ui // phase_bins)
    traces: list[dict[str, Any]] = []
    for index in range(start_bit, min(bit_count - 2, start_bit + 256)):
        begin = index / bit_rate_hz + delay_samples * delta_t
        phases = np.arange(0, 2 * samples_per_ui, stride) / samples_per_ui
        if begin + phases[-1] / bit_rate_hz > time_s[-1]:
            break
        segment = np.interp(begin + phases / bit_rate_hz, time_s, response)
        if len(segment) > 1:
            traces.append({
                "source_bit_index": index,
                "values": [float(value) for value in segment],
            })
    return {
        "contract": "spike/si-nrz-eye/v1",
        "status": "completed",
        "model_status": "experimental",
        "normalization": "unit-difference ideal NRZ source and linear channel",
        "bit_rate_hz": float(bit_rate_hz),
        "represented_bit_rate_hz": represented_rate,
        "bit_count": bit_count,
        "samples_per_ui": samples_per_ui,
        "actual_samples_per_ui": actual_samples_per_ui,
        "clock_mode": "exact_symbol_boundaries",
        "waveform_samples": waveform_samples,
        "sampling_phase_ui": 0.5,
        "source_port_index": source_port,
        "sink_port_index": sink_port,
        "threshold": midpoint,
        "eye_height_normalized": eye_height,
        "deterministic_isi_q": q_factor if isfinite(q_factor) else None,
        "deterministic_isi_ber_estimate": ber_estimate,
        "traces": traces,
        "limitations": [
            "ideal normalized NRZ source; no IBIS, package, equalizer, CDR, jitter, or stochastic noise model",
            "BER is a deterministic-ISI Gaussian proxy and is not a protocol or rare-event qualification",
        ],
    }


def analyze_uniform_design_channel(
    design: DesignIRV2, request: Mapping[str, Any],
    *, cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    _validate_channel_request(request)
    if str(request.get("victim_net", "")).strip():
        from .si_coupled_channel import analyze_coupled_design_channel

        return analyze_coupled_design_channel(design, request, cancel_check=cancel_check)
    frequencies = _frequency_grid(request.get("frequencies_hz"))
    extraction = extract_uniform_path_rlgc(design, request)
    network = uniform_rlgc_network(
        extraction,
        frequencies,
        float(request.get("reference_impedance_ohm", 50.0)),
        cancel_check=cancel_check,
    )
    network_report = analyze_network(network, trace_limit=int(request.get("trace_limit", 2048)))
    time_report = time_domain_report(network)
    eye = None
    if request.get("bit_rate_hz") is not None:
        eye = normalized_nrz_eye(
            network,
            bit_rate_hz=float(request["bit_rate_hz"]),
            bit_count=int(request.get("bit_count", 1024)),
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
                cancel_check=cancel_check,
            )
    pam4_model = request.get("pam4_model")
    if pam4_model is not None:
        from .si_pam4_eye import pam4_eye

        if request.get("symbol_rate_hz") is None:
            raise SiChannelError("PAM4 analysis requires explicit symbol_rate_hz.")
        if eye is None:
            eye = {"contract": "spike/si-eye-collection/v1", "status": "completed"}
        eye["pam4"] = pam4_eye(
            network,
            symbol_rate_hz=float(request["symbol_rate_hz"]),
            symbol_count=int(request.get("symbol_count", 1024)),
            model=pam4_model,
            cancel_check=cancel_check,
        )
    time_samples = 2 * len(frequencies) - 1
    eye_samples = int(eye.get("waveform_samples", 0)) if eye else 0
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
        "crosstalk": None,
        "differential": None,
        "resource_admission": {
            "frequency_points": len(frequencies),
            "time_domain_samples": time_samples,
            "eye_waveform_samples": eye_samples,
            "estimated_numeric_bytes": int(len(frequencies) * 4 * 16 + time_samples * 5 * 8 + eye_samples * 24),
            "hard_limits": {
                "frequency_points": MAX_FREQUENCY_POINTS,
                "eye_bits": MAX_EYE_BITS,
                "eye_waveform_samples": MAX_EYE_WAVEFORM_SAMPLES,
                "eye_fft_points": MAX_EYE_FFT_POINTS,
            },
            "cooperative_cancellation_supported": True,
        },
        "provenance": {
            "implementation": "SPIKE independent uniform multiconductor-telegrapher-equation specialization",
            "design_contract": design.contract,
            "design_id": design.design_id,
            "request_digest": _canonical_digest(dict(request)),
            "reference_wave_definition": "pseudo-wave with real positive reference impedance",
        },
        "release_gate": {
            "state": "experimental_bounded_geometry",
            "required_before_promotion": [
                "frequency-dependent conductor and dielectric models",
                "mesh and frequency convergence",
                "independent solver correlation",
                "measured VNA and TDR coupon correlation with uncertainty",
            ],
        },
    }


__all__ = [
    "EXTRACTION_CONTRACT", "MAX_EYE_BITS", "MAX_EYE_FFT_POINTS", "MAX_EYE_WAVEFORM_SAMPLES",
    "MAX_FREQUENCY_POINTS", "REQUEST_CONTRACT",
    "RESULT_CONTRACT", "SiChannelError", "analyze_uniform_design_channel",
    "extract_uniform_path_rlgc", "normalized_nrz_eye", "time_domain_report",
    "uniform_rlgc_network",
]
