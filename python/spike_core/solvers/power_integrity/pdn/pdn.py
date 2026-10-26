"""Deterministic PDN target review and auditable decoupling screening.

The module deliberately separates three electrical placement models:

* ``direct_port_shunt`` is the legacy port-level approximation.
* ``series_connection_path`` adds explicit mounting/spreading impedance.
* ``multiport_impedance_loading`` loads an extracted candidate port through a
  two-port Z-parameter reduction.  This is the only geometry-aware mode.

No spatial impedance is inferred from board coordinates.  Candidate-port
frequency grids must match the reviewed driving-point sweep exactly so a
ranking cannot be produced from hidden interpolation.
"""

from __future__ import annotations

import cmath
import itertools
import math
from math import inf, pi, radians
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np


_MODEL_STATUS_ORDER = {
    "validated": 0,
    "approximate": 1,
    "experimental": 1,
    "solver_dependent": 1,
    "unvalidated": 1,
    "unsupported": 2,
    "failed": 3,
}


def _finite(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Expected a finite numeric value.") from exc
    if not math.isfinite(number):
        raise ValueError("Expected a finite numeric value.")
    if positive and number <= 0:
        raise ValueError("Expected a positive numeric value.")
    if nonnegative and number < 0:
        raise ValueError("Expected a non-negative numeric value.")
    return number


def _complex_impedance(point: Dict[str, Any]) -> complex:
    if point.get("resistance_ohm") is not None or point.get("reactance_ohm") is not None:
        value = complex(
            _finite(point.get("resistance_ohm", 0)),
            _finite(point.get("reactance_ohm", 0)),
        )
    else:
        magnitude = _finite(point.get("magnitude_ohm", 0), nonnegative=True)
        value = cmath.rect(magnitude, radians(_finite(point.get("phase_deg", 0))))
    if not math.isfinite(value.real) or not math.isfinite(value.imag):
        raise ValueError("Impedance points must contain finite values.")
    return value


def _sweep(result: Dict[str, Any], net: str = "") -> tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    networks = result.get("networks", {})
    parasitics = networks.get("parasitics", []) if isinstance(networks, dict) else []
    if not parasitics and isinstance(result.get("parasitics"), list):
        parasitics = result["parasitics"]
    selected = next((item for item in parasitics if not net or item.get("net") == net), None)
    if not selected:
        raise ValueError("The result contains no compatible impedance sweep.")
    points = sorted(selected.get("impedance", []), key=lambda item: float(item.get("frequency_hz", 0)))
    if len(points) < 2:
        raise ValueError("PDN review requires at least two impedance points.")
    frequencies = [_finite(point.get("frequency_hz"), positive=True) for point in points]
    if any(current <= previous for previous, current in zip(frequencies, frequencies[1:])):
        raise ValueError("PDN impedance frequencies must be finite, positive, and strictly increasing.")
    for point in points:
        _complex_impedance(point)
    return str(selected.get("net", net or "active-port")), points, selected


def _extrema(points: Sequence[Dict[str, Any]], kind: str) -> List[Dict[str, float]]:
    values = [abs(_complex_impedance(point)) for point in points]
    result: List[Dict[str, float]] = []
    for index in range(1, len(points) - 1):
        is_peak = values[index] > values[index - 1] and values[index] >= values[index + 1]
        is_valley = values[index] < values[index - 1] and values[index] <= values[index + 1]
        if (kind == "peak" and is_peak) or (kind == "valley" and is_valley):
            result.append({
                "frequency_hz": float(points[index]["frequency_hz"]),
                "magnitude_ohm": values[index],
            })
    return result


def _candidate_impedance(candidate: Dict[str, Any], frequency_hz: float) -> complex:
    capacitance = _finite(candidate.get("capacitance_f", 0), positive=True)
    count_value = _finite(candidate.get("count", 1), positive=True)
    count = int(count_value)
    if count_value != count:
        raise ValueError("Candidate count must be a positive integer.")
    esr = _finite(candidate.get("esr_ohm", 0), nonnegative=True)
    esl = _finite(candidate.get("esl_h", 0), nonnegative=True)
    omega = 2 * pi * frequency_hz
    impedance = complex(esr, omega * esl - 1 / (omega * capacitance))
    return impedance / count


def _candidate_id(candidate: Dict[str, Any], index: int) -> str:
    return str(candidate.get("id", candidate.get("name", f"candidate-{index + 1}")))


def _aligned_impedance_sweep(
    raw_points: Any,
    frequencies: Sequence[float],
    label: str,
) -> List[complex]:
    if not isinstance(raw_points, list) or len(raw_points) != len(frequencies):
        raise ValueError(f"{label} must contain exactly one point for every reviewed frequency.")
    ordered = sorted(raw_points, key=lambda item: float(item.get("frequency_hz", 0)) if isinstance(item, dict) else 0)
    values: List[complex] = []
    for expected, point in zip(frequencies, ordered):
        if not isinstance(point, dict):
            raise ValueError(f"{label} points must be objects.")
        actual = _finite(point.get("frequency_hz"), positive=True)
        if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=max(1e-12, expected * 1e-12)):
            raise ValueError(f"{label} frequency grid must exactly match the reviewed sweep.")
        values.append(_complex_impedance(point))
    return values


def _path_impedance(candidate: Dict[str, Any], frequency_hz: float) -> complex:
    resistance = _finite(
        candidate.get("mounting_resistance_ohm", candidate.get("connection_resistance_ohm", 0)),
        nonnegative=True,
    )
    inductance = _finite(
        candidate.get("mounting_inductance_h", candidate.get("connection_inductance_h", 0)),
        nonnegative=True,
    )
    return complex(resistance, 2 * pi * frequency_hz * inductance)


def _parallel(left: complex, right: complex) -> complex:
    if left == 0j or right == 0j:
        return 0j
    denominator = left + right
    if abs(denominator) <= 1e-30:
        raise ValueError("Candidate creates a singular parallel impedance.")
    return left * right / denominator


def _target_excess_integral(frequencies: Sequence[float], magnitudes: Sequence[float], target_ohm: float) -> float:
    if len(frequencies) < 2:
        return 0.0
    excess = [max(value / target_ohm - 1, 0.0) for value in magnitudes]
    total = 0.0
    for index in range(len(frequencies) - 1):
        span = math.log10(frequencies[index + 1]) - math.log10(frequencies[index])
        total += 0.5 * (excess[index] + excess[index + 1]) * span
    return total


def _normalized_status(value: Any, default: str = "approximate") -> str:
    status = str(value or default).strip().lower()
    return status if status in _MODEL_STATUS_ORDER else default


def _weakest_status(*statuses: str) -> str:
    normalized = [_normalized_status(status) for status in statuses]
    weakest = max(normalized, key=lambda status: _MODEL_STATUS_ORDER[status])
    return "approximate" if weakest in {"experimental", "solver_dependent", "unvalidated"} else weakest


def _candidate_response(
    candidate: Dict[str, Any],
    index: int,
    frequencies: Sequence[float],
    base: Sequence[complex],
    target_ohm: float,
    source_model_status: str,
) -> Dict[str, Any]:
    identifier = _candidate_id(candidate, index)
    common: Dict[str, Any] = {
        "id": identifier,
        "status": "evaluated",
        "capacitance_f": candidate.get("capacitance_f"),
        "esr_ohm": candidate.get("esr_ohm", 0),
        "esl_h": candidate.get("esl_h", 0),
        "count": candidate.get("count", 1),
        "location": candidate.get("location"),
        "source_result_id": candidate.get("source_result_id"),
        "issues": [],
    }
    try:
        # Validate the bank once before selecting a placement model.
        _candidate_impedance(candidate, frequencies[0])
        has_multiport = any(
            key in candidate
            for key in ("local_impedance", "transfer_impedance", "reverse_transfer_impedance")
        )
        spreading_raw = candidate.get("spreading_impedance")
        has_series_path = spreading_raw is not None or any(
            key in candidate
            for key in (
                "mounting_resistance_ohm", "mounting_inductance_h",
                "connection_resistance_ohm", "connection_inductance_h",
            )
        )
        assumptions: List[str] = []
        if has_multiport:
            if candidate.get("endpoint_reviewed") is not True:
                raise ValueError("Geometry-aware candidate endpoints must be explicitly reviewed.")
            if not str(candidate.get("source_result_id", "")).strip():
                raise ValueError("Geometry-aware candidates require source_result_id provenance.")
            local = _aligned_impedance_sweep(candidate.get("local_impedance"), frequencies, "local_impedance")
            forward = _aligned_impedance_sweep(candidate.get("transfer_impedance"), frequencies, "transfer_impedance")
            reverse_raw = candidate.get("reverse_transfer_impedance")
            if reverse_raw is None:
                reverse = forward
                if candidate.get("reciprocal") is not True:
                    assumptions.append("Reverse transfer impedance was assumed equal to forward transfer impedance.")
            else:
                reverse = _aligned_impedance_sweep(reverse_raw, frequencies, "reverse_transfer_impedance")
            method = "multiport_impedance_loading"
            loaded: List[complex] = []
            for frequency, z00, zcc, z0c, zc0 in zip(frequencies, base, local, forward, reverse):
                load = _candidate_impedance(candidate, frequency) + _path_impedance(candidate, frequency)
                denominator = zcc + load
                if abs(denominator) <= 1e-30:
                    raise ValueError("Candidate-port load produces a singular two-port reduction.")
                value = z00 - z0c * zc0 / denominator
                tolerance = max(1e-12, abs(value) * 1e-9)
                if value.real < -tolerance:
                    raise ValueError("Candidate-port data produces a non-passive loaded driving-point impedance.")
                loaded.append(value)
            candidate_status = _weakest_status(
                source_model_status,
                _normalized_status(candidate.get("model_status")),
                "approximate" if assumptions else "validated",
            )
        else:
            spreading = (
                _aligned_impedance_sweep(spreading_raw, frequencies, "spreading_impedance")
                if spreading_raw is not None else [0j] * len(frequencies)
            )
            method = "series_connection_path" if has_series_path else "direct_port_shunt"
            if method == "direct_port_shunt":
                assumptions.append("The capacitor bank is connected directly at the reviewed driving-point port.")
            else:
                assumptions.append("The supplied series path is treated as a lumped branch at the reviewed port.")
            loaded = [
                _parallel(
                    board,
                    _candidate_impedance(candidate, frequency)
                    + _path_impedance(candidate, frequency)
                    + spreading_impedance,
                )
                for frequency, board, spreading_impedance in zip(frequencies, base, spreading)
            ]
            candidate_status = _weakest_status(source_model_status, "approximate")

        magnitudes = [abs(value) for value in loaded]
        if any(not math.isfinite(value) for value in magnitudes):
            raise ValueError("Candidate response contains a non-finite impedance.")
        base_magnitudes = [abs(value) for value in base]
        worst_index = max(range(len(magnitudes)), key=magnitudes.__getitem__)
        maximum_degradation = max(
            ((candidate_value - base_value) / base_value * 100 if base_value else 0.0)
            for candidate_value, base_value in zip(magnitudes, base_magnitudes)
        )
        common.update({
            "placement_method": method,
            "model_status": candidate_status,
            "assumptions": assumptions,
            "mounting_resistance_ohm": _finite(
                candidate.get("mounting_resistance_ohm", candidate.get("connection_resistance_ohm", 0)),
                nonnegative=True,
            ),
            "mounting_inductance_h": _finite(
                candidate.get("mounting_inductance_h", candidate.get("connection_inductance_h", 0)),
                nonnegative=True,
            ),
            "worst_impedance_ohm": magnitudes[worst_index],
            "worst_frequency_hz": frequencies[worst_index],
            "worst_target_ratio": magnitudes[worst_index] / target_ohm,
            "worst_impedance_improvement_percent": (
                100 * (max(base_magnitudes) - magnitudes[worst_index]) / max(base_magnitudes)
                if max(base_magnitudes) else 0.0
            ),
            "maximum_local_degradation_percent": maximum_degradation,
            "target_excess_integral_log_decades": _target_excess_integral(frequencies, magnitudes, target_ohm),
            "violation_count": sum(value > target_ohm for value in magnitudes),
            "passes_target": max(magnitudes) <= target_ohm,
            "response": [
                {
                    "frequency_hz": frequency,
                    "resistance_ohm": value.real,
                    "reactance_ohm": value.imag,
                    "magnitude_ohm": abs(value),
                    "phase_deg": math.degrees(cmath.phase(value)),
                }
                for frequency, value in zip(frequencies, loaded)
            ],
        })
    except ValueError as exc:
        common.update({
            "status": "rejected",
            "placement_method": "invalid",
            "model_status": "unsupported",
            "passes_target": False,
            "issues": [{
                "code": "SPIKE-BE-PI-E-0100",
                "severity": "error",
                "message": str(exc),
            }],
        })
    return common


def review_pdn(
    result: Dict[str, Any],
    target_ohm: float,
    net: str = "",
    candidates: Iterable[Dict[str, Any]] = (),
) -> Dict[str, Any]:
    """Review one extracted driving-point impedance against a fixed target."""

    target_ohm = _finite(target_ohm, positive=True)
    selected_net, points, selected_network = _sweep(result, net)
    frequencies = [float(point["frequency_hz"]) for point in points]
    base = [_complex_impedance(point) for point in points]
    magnitudes = [abs(value) for value in base]
    source_model_status = _normalized_status(
        selected_network.get("model_status", result.get("model_status", "approximate"))
    )
    violations = [
        {
            "frequency_hz": float(point["frequency_hz"]),
            "magnitude_ohm": magnitude,
            "target_ohm": target_ohm,
            "excess_ratio": magnitude / target_ohm,
        }
        for point, magnitude in zip(points, magnitudes)
        if magnitude > target_ohm
    ]
    recommendations = [
        _candidate_response(candidate, index, frequencies, base, target_ohm, source_model_status)
        for index, candidate in enumerate(candidates)
    ]
    recommendations.sort(key=lambda item: (
        2 if item["status"] != "evaluated" else 0 if item["passes_target"] else 1,
        float(item.get("worst_target_ratio", inf)),
        float(item.get("target_excess_integral_log_decades", inf)),
        item["id"],
    ))
    evaluated = [item for item in recommendations if item["status"] == "evaluated"]
    method_counts = {
        method: sum(item.get("placement_method") == method for item in evaluated)
        for method in ("multiport_impedance_loading", "series_connection_path", "direct_port_shunt")
    }
    overall_statuses = [source_model_status]
    overall_statuses.extend(str(item.get("model_status", "approximate")) for item in evaluated)
    if recommendations and not evaluated:
        overall_statuses.append("unsupported")
    worst_index = max(range(len(magnitudes)), key=magnitudes.__getitem__)
    return {
        "contract": "spike/pdn-review/v1",
        "status": "pass" if not violations else "violated",
        "model_status": _weakest_status(*overall_statuses),
        "source_model_status": _weakest_status(source_model_status),
        "net": selected_net,
        "target_ohm": target_ohm,
        "frequency_start_hz": frequencies[0],
        "frequency_stop_hz": frequencies[-1],
        "point_count": len(points),
        "maximum_impedance_ohm": magnitudes[worst_index],
        "maximum_impedance_frequency_hz": frequencies[worst_index],
        "target_excess_integral_log_decades": _target_excess_integral(frequencies, magnitudes, target_ohm),
        "violation_count": len(violations),
        "violations": violations,
        "resonances": _extrema(points, "peak"),
        "anti_resonances": _extrema(points, "valley"),
        "candidate_screening": recommendations,
        "candidate_method_counts": method_counts,
        "best_candidate_id": evaluated[0]["id"] if evaluated else None,
        "validity": {
            "scope": "Driving-point impedance target review and explicit shunt-load screening.",
            "source_model_status": source_model_status,
            "limits": [
                "Only multiport_impedance_loading uses location-specific extracted transfer and local driving-point impedance.",
                "Candidate-port sweeps must use the source frequency grid; SPIKE does not silently interpolate spatial extraction data.",
                "Direct-port and lumped series-path candidates remain approximate placement screens.",
                "Capacitor bias, temperature, tolerance, aging, nonlinear behavior, and regulator control-loop dynamics require explicit component models.",
                "The review inherits every validity limit and warning from the source solver result.",
            ],
        },
    }


def _pdn_multiport(result: Dict[str, Any], net: str) -> Dict[str, Any]:
    networks = result.get("networks", {})
    multiports = networks.get("pdn_multiports", []) if isinstance(networks, dict) else []
    if not multiports and isinstance(result.get("pdn_multiports"), list):
        multiports = result["pdn_multiports"]
    selected = next((item for item in multiports if not net or item.get("net") == net), None)
    if not isinstance(selected, dict):
        raise ValueError("PDN optimization requires an explicit frequency-dependent multiport result.")
    if selected.get("contract") != "spike/pdn-multiport/v1":
        raise ValueError("PDN optimization requires the spike/pdn-multiport/v1 contract.")
    return selected


def _multiport_matrices(multiport: Dict[str, Any]) -> tuple[List[float], List[np.ndarray]]:
    raw_points = multiport.get("z_parameters")
    ports = multiport.get("ports")
    if not isinstance(raw_points, list) or len(raw_points) < 2:
        raise ValueError("PDN optimization requires at least two multiport impedance matrices.")
    if not isinstance(ports, list) or len(ports) < 2:
        raise ValueError("PDN optimization requires one observation port and at least one candidate port.")
    size = len(ports)
    ordered = sorted(raw_points, key=lambda item: float(item.get("frequency_hz", 0)))
    frequencies: List[float] = []
    matrices: List[np.ndarray] = []
    for point in ordered:
        if not isinstance(point, dict):
            raise ValueError("Multiport impedance points must be objects.")
        frequency = _finite(point.get("frequency_hz"), positive=True)
        resistance = np.asarray(point.get("resistance_ohm"), dtype=float)
        reactance = np.asarray(point.get("reactance_ohm"), dtype=float)
        if resistance.shape != (size, size) or reactance.shape != (size, size):
            raise ValueError(f"Every multiport impedance matrix must be {size} by {size}.")
        matrix = resistance.astype(complex) + 1j * reactance
        if not np.all(np.isfinite(matrix.real)) or not np.all(np.isfinite(matrix.imag)):
            raise ValueError("Multiport impedance matrices must contain finite values.")
        frequencies.append(frequency)
        matrices.append(matrix)
    if any(current <= previous for previous, current in zip(frequencies, frequencies[1:])):
        raise ValueError("Multiport frequencies must be finite, positive, and strictly increasing.")
    return frequencies, matrices


def _positive_integer(value: Any, label: str, *, minimum: int = 1, maximum: int = 1_000_000) -> int:
    number = _finite(value, positive=True)
    integer = int(number)
    if number != integer or not minimum <= integer <= maximum:
        raise ValueError(f"{label} must be an integer from {minimum} through {maximum}.")
    return integer


def _library_entry(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Every capacitor-library entry must be an object.")
    entry = {
        "id": str(raw.get("id") or raw.get("name") or f"capacitor-{index + 1}"),
        "capacitance_f": _finite(raw.get("capacitance_f"), positive=True),
        "esr_ohm": _finite(raw.get("esr_ohm", 0), nonnegative=True),
        "esl_h": _finite(raw.get("esl_h", 0), nonnegative=True),
        "mounting_resistance_ohm": _finite(raw.get("mounting_resistance_ohm", 0), nonnegative=True),
        "mounting_inductance_h": _finite(raw.get("mounting_inductance_h", 0), nonnegative=True),
        "min_count": _positive_integer(raw.get("min_count", 1), "min_count"),
        "max_count": _positive_integer(raw.get("max_count", raw.get("min_count", 1)), "max_count"),
        "unit_cost": _finite(raw.get("unit_cost", 0), nonnegative=True),
        "voltage_rating_v": None if raw.get("voltage_rating_v") is None else _finite(raw["voltage_rating_v"], positive=True),
        "ripple_current_rating_a": None if raw.get("ripple_current_rating_a") is None else _finite(raw["ripple_current_rating_a"], positive=True),
        "allowed_port_ids": tuple(str(value) for value in raw.get("allowed_port_ids", [])),
        "model_status": _normalized_status(raw.get("model_status", "approximate")),
    }
    if entry["max_count"] < entry["min_count"]:
        raise ValueError(f"Capacitor {entry['id']} has max_count below min_count.")
    return entry


def _bank_impedance(entry: Dict[str, Any], count: int, frequency_hz: float) -> complex:
    omega = 2 * pi * frequency_hz
    device = complex(
        entry["esr_ohm"],
        omega * entry["esl_h"] - 1 / (omega * entry["capacitance_f"]),
    ) / count
    mounting = complex(
        entry["mounting_resistance_ohm"],
        omega * entry["mounting_inductance_h"],
    )
    return device + mounting


def _rating_issue(entry: Dict[str, Any], constraints: Dict[str, Any]) -> str:
    operating_voltage = constraints.get("operating_voltage_v")
    voltage_derating = _finite(constraints.get("voltage_derating", 1.0), positive=True)
    if voltage_derating > 1:
        raise ValueError("voltage_derating must not exceed 1.0.")
    if operating_voltage is not None:
        required = _finite(operating_voltage, nonnegative=True)
        rating = entry["voltage_rating_v"]
        if rating is None:
            return "Voltage rating is required by the optimization constraints."
        if required > rating * voltage_derating:
            return "Voltage rating fails the configured derating requirement."
    required_ripple = constraints.get("required_ripple_current_a")
    ripple_derating = _finite(constraints.get("ripple_current_derating", 1.0), positive=True)
    if ripple_derating > 1:
        raise ValueError("ripple_current_derating must not exceed 1.0.")
    if required_ripple is not None:
        required = _finite(required_ripple, nonnegative=True)
        rating = entry["ripple_current_rating_a"]
        if rating is None:
            return "Ripple-current rating is required by the optimization constraints."
        if required > rating * ripple_derating:
            return "Ripple-current rating fails the configured derating requirement."
    return ""


def optimize_pdn(
    result: Dict[str, Any],
    target_ohm: float,
    net: str = "",
    capacitor_library: Iterable[Dict[str, Any]] = (),
    constraints: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Search a finite capacitor/port domain using an extracted Z matrix.

    The search changes only explicit shunt loads.  It never edits or infers the
    copper RLC model, and it inherits the weakest validity state of the field
    extraction and component models.
    """

    target_ohm = _finite(target_ohm, positive=True)
    constraints = dict(constraints or {})
    multiport = _pdn_multiport(result, net)
    frequencies, matrices = _multiport_matrices(multiport)
    raw_ports = multiport["ports"]
    candidate_metadata = {
        str(item.get("id")): item
        for item in multiport.get("candidates", [])
        if isinstance(item, dict) and item.get("id") is not None
    }
    candidate_ports: List[Dict[str, Any]] = []
    requested_port_ids = {str(value) for value in constraints.get("candidate_port_ids", [])}
    for matrix_index, port in enumerate(raw_ports[1:], start=1):
        if not isinstance(port, dict):
            raise ValueError("Every PDN multiport endpoint must be an object.")
        identifier = str(port.get("id") or f"port-{matrix_index}")
        if requested_port_ids and identifier not in requested_port_ids:
            continue
        metadata = candidate_metadata.get(identifier, {})
        if port.get("endpoint_reviewed") is not True or metadata.get("endpoint_reviewed") is not True:
            raise ValueError(f"Candidate port {identifier} must be explicitly reviewed before optimization.")
        candidate_ports.append({
            "id": identifier,
            "matrix_index": matrix_index,
            "location": metadata.get("location", port.get("source_terminal", {})),
        })
    if requested_port_ids - {item["id"] for item in candidate_ports}:
        missing = ", ".join(sorted(requested_port_ids - {item["id"] for item in candidate_ports}))
        raise ValueError(f"Requested candidate ports are unavailable or unreviewed: {missing}.")
    max_ports = _positive_integer(constraints.get("max_candidate_ports", 12), "max_candidate_ports", maximum=64)
    if not candidate_ports:
        raise ValueError("No reviewed candidate ports are available for PDN optimization.")
    if len(candidate_ports) > max_ports:
        raise ValueError(
            f"{len(candidate_ports)} candidate ports exceed the configured optimization limit of {max_ports}."
        )

    library = [_library_entry(item, index) for index, item in enumerate(capacitor_library)]
    if not library:
        raise ValueError("PDN optimization requires a finite capacitor library.")
    rejected_library: List[Dict[str, Any]] = []
    eligible_library: List[Dict[str, Any]] = []
    for entry in library:
        issue = _rating_issue(entry, constraints)
        if issue:
            rejected_library.append({"id": entry["id"], "reason": issue})
        else:
            eligible_library.append(entry)
    if not eligible_library:
        raise ValueError("No capacitor-library entry satisfies the configured electrical ratings.")

    max_total_count = _positive_integer(constraints.get("max_total_count", 32), "max_total_count")
    max_total_cost = (
        float("inf")
        if constraints.get("max_total_cost") is None
        else _finite(constraints["max_total_cost"], nonnegative=True)
    )
    max_evaluations = _positive_integer(constraints.get("max_evaluations", 100_000), "max_evaluations")
    top_n = _positive_integer(constraints.get("top_n", 10), "top_n", maximum=1000)
    choices: List[List[tuple[Dict[str, Any], int] | None]] = []
    for port in candidate_ports:
        port_choices: List[tuple[Dict[str, Any], int] | None] = [None]
        for entry in eligible_library:
            if entry["allowed_port_ids"] and port["id"] not in entry["allowed_port_ids"]:
                continue
            port_choices.extend((entry, count) for count in range(entry["min_count"], entry["max_count"] + 1))
        choices.append(port_choices)
    theoretical_combinations = math.prod(len(items) for items in choices) - 1
    if theoretical_combinations < 1:
        raise ValueError("The capacitor library has no eligible assignment for the selected ports.")

    base_values = [matrix[0, 0] for matrix in matrices]
    base_magnitudes = [abs(value) for value in base_values]
    recommendations: List[Dict[str, Any]] = []
    evaluated = 0
    feasible = 0
    singular = 0
    truncated = theoretical_combinations > max_evaluations
    for combination in itertools.islice(itertools.product(*choices), max_evaluations + 1):
        if all(choice is None for choice in combination):
            continue
        if evaluated >= max_evaluations:
            truncated = True
            break
        evaluated += 1
        assignments = [
            (port, choice[0], choice[1])
            for port, choice in zip(candidate_ports, combination)
            if choice is not None
        ]
        total_count = sum(count for _, _, count in assignments)
        total_cost = sum(entry["unit_cost"] * count for _, entry, count in assignments)
        if total_count > max_total_count or total_cost > max_total_cost:
            continue
        loaded_values: List[complex] = []
        active_indices = [port["matrix_index"] for port, _, _ in assignments]
        try:
            for frequency, matrix in zip(frequencies, matrices):
                zcc = matrix[np.ix_(active_indices, active_indices)]
                loads = np.diag([
                    _bank_impedance(entry, count, frequency)
                    for _, entry, count in assignments
                ])
                z0c = matrix[0, active_indices]
                zc0 = matrix[active_indices, 0]
                loaded = matrix[0, 0] - z0c @ np.linalg.solve(zcc + loads, zc0)
                tolerance = max(1e-12, abs(loaded) * 1e-9)
                if not np.isfinite(loaded.real) or not np.isfinite(loaded.imag) or loaded.real < -tolerance:
                    raise np.linalg.LinAlgError("non-passive or non-finite loaded impedance")
                loaded_values.append(complex(loaded))
        except np.linalg.LinAlgError:
            singular += 1
            continue
        feasible += 1
        magnitudes = [abs(value) for value in loaded_values]
        worst_index = max(range(len(magnitudes)), key=magnitudes.__getitem__)
        excess_integral = _target_excess_integral(frequencies, magnitudes, target_ohm)
        model_status = _weakest_status(
            _normalized_status(multiport.get("model_status", result.get("model_status", "approximate"))),
            *(entry["model_status"] for _, entry, _ in assignments),
        )
        recommendation = {
            "id": "+".join(f"{port['id']}:{entry['id']}x{count}" for port, entry, count in assignments),
            "model_status": model_status,
            "passes_target": max(magnitudes) <= target_ohm,
            "worst_impedance_ohm": magnitudes[worst_index],
            "worst_frequency_hz": frequencies[worst_index],
            "worst_target_ratio": magnitudes[worst_index] / target_ohm,
            "target_excess_integral_log_decades": excess_integral,
            "violation_count": sum(value > target_ohm for value in magnitudes),
            "total_count": total_count,
            "total_cost": total_cost,
            "assignments": [{
                "port_id": port["id"],
                "location": port["location"],
                "capacitor_id": entry["id"],
                "count": count,
                "capacitance_f": entry["capacitance_f"],
                "esr_ohm": entry["esr_ohm"],
                "esl_h": entry["esl_h"],
                "mounting_resistance_ohm": entry["mounting_resistance_ohm"],
                "mounting_inductance_h": entry["mounting_inductance_h"],
            } for port, entry, count in assignments],
            "response": [{
                "frequency_hz": frequency,
                "resistance_ohm": value.real,
                "reactance_ohm": value.imag,
                "magnitude_ohm": abs(value),
                "phase_deg": math.degrees(cmath.phase(value)),
            } for frequency, value in zip(frequencies, loaded_values)],
        }
        recommendations.append(recommendation)
    recommendations.sort(key=lambda item: (
        0 if item["passes_target"] else 1,
        float(item["worst_target_ratio"]),
        float(item["target_excess_integral_log_decades"]),
        int(item["total_count"]),
        float(item["total_cost"]),
        item["id"],
    ))
    recommendations = recommendations[:top_n]
    for rank, recommendation in enumerate(recommendations, start=1):
        recommendation["rank"] = rank
        recommendation["target_violation_score"] = float(
            recommendation["target_excess_integral_log_decades"]
        )
        for assignment in recommendation["assignments"]:
            assignment["candidate_port_id"] = assignment["port_id"]
    source_status = _normalized_status(multiport.get("model_status", result.get("model_status", "approximate")))
    worst_base_index = max(range(len(base_magnitudes)), key=base_magnitudes.__getitem__)
    exhaustive = not truncated and evaluated >= theoretical_combinations
    optimization_id = str(
        constraints.get("optimization_id")
        or f"{multiport.get('source_result_id', 'pdn')}:{multiport.get('net', net or 'active-port')}"
    )
    source_network = {
        "result_id": str(multiport.get("source_result_id") or "unidentified-source-result"),
        "result_contract": str(multiport.get("contract")),
        "model_status": source_status,
        "observation_port_id": str(raw_ports[0].get("id") or "observation"),
        "frequency_hz": frequencies,
    }
    return {
        "contract": "spike/pdn-optimization/v1",
        "record_type": "result",
        "optimization_id": optimization_id,
        "source_network": source_network,
        "status": "completed" if recommendations else "no_feasible_configuration",
        "search_status": "exhaustive" if exhaustive else "bounded",
        "search_scope": "exhaustive" if exhaustive else "bounded",
        "claim": "global_optimum" if exhaustive and recommendations else "recommendation",
        "optimality": "optimal_within_explicit_search_domain" if exhaustive and recommendations else "recommendation_only",
        "model_status": _weakest_status(
            source_status,
            *(str(item["model_status"]) for item in recommendations),
        ),
        "source_model_status": source_status,
        "source_result_id": multiport.get("source_result_id"),
        "net": str(multiport.get("net", net)),
        "target_ohm": target_ohm,
        "frequency_start_hz": frequencies[0],
        "frequency_stop_hz": frequencies[-1],
        "point_count": len(frequencies),
        "baseline": {
            "worst_impedance_ohm": base_magnitudes[worst_base_index],
            "worst_frequency_hz": frequencies[worst_base_index],
            "target_excess_integral_log_decades": _target_excess_integral(
                frequencies, base_magnitudes, target_ohm
            ),
            "violation_count": sum(value > target_ohm for value in base_magnitudes),
        },
        "search": {
            "candidate_port_count": len(candidate_ports),
            "eligible_library_count": len(eligible_library),
            "rejected_library": rejected_library,
            "theoretical_combinations": theoretical_combinations,
            "evaluated_combinations": evaluated,
            "feasible_combinations": feasible,
            "singular_or_nonpassive_combinations": singular,
            "max_evaluations": max_evaluations,
            "truncated": truncated,
        },
        "constraints": constraints,
        "recommendations": recommendations,
        "best_recommendation_id": recommendations[0]["id"] if recommendations else None,
        "evaluated_configurations": evaluated,
        "search_limit": max_evaluations,
        "issues": [],
        "validity": {
            "scope": "Finite capacitor-bank search over reviewed ports of an extracted frequency-dependent Z matrix.",
            "limits": [
                "The optimizer loads the supplied copper/network model; it does not tune or alter extracted copper RLC values.",
                "Optimal means optimal only within the explicit ports, component library, count bounds, constraints, frequency samples, and objective ordering.",
                "A bounded search is a recommendation and carries no global-optimum claim.",
                "Voltage and ripple-current limits are enforced only when configured and supplied by the component library.",
                "Bias, temperature, aging, tolerance, control-loop stability, and nonlinear components require explicit models or sweeps.",
                "High-voltage and kiloampere use requires separately validated contact, busbar, current-sharing, electrothermal, insulation, clearance, creepage, and arc/corona models.",
                "Every recommendation inherits the weakest validity status and warnings of the source solver and component models.",
            ],
        },
    }
