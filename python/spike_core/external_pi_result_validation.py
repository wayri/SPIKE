"""Validation and normalization for external PI multiport solver results.

External engines may use different formulations, meshes, and linear solvers.
SPIKE accepts their output only through this bounded numerical contract so PDN
loading and comparison code never depends on an engine-specific file format.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np


PI_MULTIPORT_RESULT_CONTRACT = "spike/pi-multiport-result/v1"
PDN_MULTIPORT_CONTRACT = "spike/pdn-multiport/v1"
MODEL_STATUSES = {
    "validated", "reference_validated", "approximate", "experimental",
    "unvalidated", "unsupported", "failed",
}
MAX_PORTS = 64
MAX_FREQUENCY_POINTS = 100_000


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        requirement = "finite and positive" if positive else "finite"
        raise ValueError(f"{label} must be {requirement}.")
    return number


def _frequency_grid(values: Iterable[Any]) -> List[float]:
    frequencies = [_finite(value, "frequency_hz", positive=True) for value in values]
    if not 2 <= len(frequencies) <= MAX_FREQUENCY_POINTS:
        raise ValueError(
            f"External PI results require 2 through {MAX_FREQUENCY_POINTS} frequency points."
        )
    if any(current <= previous for previous, current in zip(frequencies, frequencies[1:])):
        raise ValueError("External PI result frequencies must be strictly increasing.")
    return frequencies


def _same_frequency(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=max(1e-12, expected * 1e-12))


def _terminal(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an explicit terminal object.")
    object_id = str(value.get("object_id", "")).strip()
    net = str(value.get("net", "")).strip()
    if not object_id or not net:
        raise ValueError(f"{label} requires object_id and net.")
    return dict(value)


def validate_external_pi_multiport(
    payload: Dict[str, Any],
    *,
    expected_engine_id: str = "",
    expected_frequencies_hz: Sequence[float] | None = None,
) -> Dict[str, Any]:
    """Validate an engine result and return ``spike/pdn-multiport/v1`` data."""

    if not isinstance(payload, dict) or payload.get("contract") != PI_MULTIPORT_RESULT_CONTRACT:
        raise ValueError(f"Expected {PI_MULTIPORT_RESULT_CONTRACT}.")
    engine_id = str(payload.get("engine_id", "")).strip()
    if not engine_id:
        raise ValueError("External PI results require engine_id provenance.")
    if expected_engine_id and engine_id != expected_engine_id:
        raise ValueError(f"External PI result engine {engine_id!r} does not match {expected_engine_id!r}.")
    if payload.get("status") != "completed":
        raise ValueError("Only completed external PI results can be imported.")
    model_status = str(payload.get("model_status", "")).strip().lower()
    if model_status not in MODEL_STATUSES or model_status in {"unvalidated", "unsupported", "failed"}:
        raise ValueError(f"External PI result model_status {model_status!r} is not usable.")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("External PI results require provenance.")
    if not str(provenance.get("solver_version", "")).strip():
        raise ValueError("External PI provenance requires solver_version.")
    if not str(provenance.get("adapter_version", "")).strip():
        raise ValueError("External PI provenance requires adapter_version.")
    if model_status in {"validated", "reference_validated"} and not provenance.get("validation_evidence"):
        raise ValueError("Validated external PI status requires explicit validation_evidence.")

    raw_ports = payload.get("ports")
    if not isinstance(raw_ports, list) or not 2 <= len(raw_ports) <= MAX_PORTS:
        raise ValueError(f"External PI results require 2 through {MAX_PORTS} ordered ports.")
    ports: List[Dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(raw_ports):
        if not isinstance(raw, dict):
            raise ValueError("Every external PI port must be an object.")
        identifier = str(raw.get("id", "")).strip()
        role = str(raw.get("role", "")).strip()
        if not identifier or identifier in identifiers:
            raise ValueError("External PI port IDs must be non-empty and unique.")
        if role not in {"observation", "candidate"}:
            raise ValueError(f"Port {identifier} has an unsupported role.")
        if index == 0 and role != "observation":
            raise ValueError("The first external PI port must be the observation port.")
        if index > 0 and role != "candidate":
            raise ValueError("Only the first external PI port may be an observation port.")
        positive = _terminal(raw.get("positive_terminal"), f"port {identifier} positive_terminal")
        negative = _terminal(raw.get("negative_terminal"), f"port {identifier} negative_terminal")
        if positive["object_id"] == negative["object_id"]:
            raise ValueError(f"Port {identifier} terminals must identify distinct objects.")
        endpoint_reviewed = raw.get("endpoint_reviewed") is True
        if not endpoint_reviewed:
            raise ValueError(f"Port {identifier} endpoints must be explicitly reviewed.")
        identifiers.add(identifier)
        ports.append({
            "id": identifier,
            "role": role,
            "endpoint_reviewed": True,
            "positive_terminal": positive,
            "negative_terminal": negative,
            "location": raw.get("location", {}),
        })

    raw_points = payload.get("z_parameters")
    if not isinstance(raw_points, list):
        raise ValueError("External PI results require z_parameters.")
    ordered = sorted(raw_points, key=lambda item: float(item.get("frequency_hz", 0)))
    frequencies = _frequency_grid(point.get("frequency_hz") for point in ordered)
    if expected_frequencies_hz is not None:
        expected = _frequency_grid(expected_frequencies_hz)
        if len(expected) != len(frequencies) or any(
            not _same_frequency(actual, wanted) for actual, wanted in zip(frequencies, expected)
        ):
            raise ValueError("External PI result frequency grid does not exactly match the request.")

    size = len(ports)
    matrices: List[np.ndarray] = []
    normalized_points: List[Dict[str, Any]] = []
    for point in ordered:
        resistance = np.asarray(point.get("resistance_ohm"), dtype=float)
        reactance = np.asarray(point.get("reactance_ohm"), dtype=float)
        if resistance.shape != (size, size) or reactance.shape != (size, size):
            raise ValueError(f"External PI Z matrices must be {size} by {size}.")
        if not np.all(np.isfinite(resistance)) or not np.all(np.isfinite(reactance)):
            raise ValueError("External PI Z matrices contain non-finite values.")
        matrix = resistance.astype(complex) + 1j * reactance
        matrices.append(matrix)
        normalized_points.append({
            "frequency_hz": float(point["frequency_hz"]),
            "resistance_ohm": resistance.tolist(),
            "reactance_ohm": reactance.tolist(),
        })

    reciprocity = [
        float(np.linalg.norm(matrix - matrix.T) / max(np.linalg.norm(matrix), np.finfo(float).eps))
        for matrix in matrices
    ]
    passivity = [
        float(np.min(np.linalg.eigvalsh((matrix + matrix.conjugate().T) / 2)))
        for matrix in matrices
    ]
    maximum_reciprocity_error = max(reciprocity)
    minimum_passivity_eigenvalue = min(passivity)
    declared_quality = payload.get("quality", {})
    if not isinstance(declared_quality, dict):
        raise ValueError("External PI result quality must be an object.")
    passivity_tolerance = _finite(declared_quality.get("passivity_tolerance_ohm", 1e-9), "passivity_tolerance_ohm", positive=True)
    reciprocity_tolerance = _finite(declared_quality.get("reciprocity_tolerance", 1e-7), "reciprocity_tolerance", positive=True)
    if minimum_passivity_eigenvalue < -passivity_tolerance:
        raise ValueError("External PI Z matrix fails the declared passivity tolerance.")
    if maximum_reciprocity_error > reciprocity_tolerance and payload.get("reciprocal") is not False:
        raise ValueError("External PI Z matrix fails the declared reciprocity tolerance.")
    convergence = payload.get("convergence")
    if not isinstance(convergence, dict) or convergence.get("passed") is not True:
        raise ValueError("External PI results require a passed mesh-convergence record.")

    source_result_id = str(payload.get("source_result_id") or payload.get("analysis_id") or "external-pi")
    candidates: List[Dict[str, Any]] = []
    for candidate_index, port in enumerate(ports[1:], start=1):
        candidates.append({
            "id": port["id"],
            "location": port.get("location", {}),
            "source_result_id": source_result_id,
            "endpoint_reviewed": True,
            "reciprocal": maximum_reciprocity_error <= reciprocity_tolerance,
            "model_status": model_status,
            "local_impedance": _impedance_trace(frequencies, matrices, candidate_index, candidate_index),
            "transfer_impedance": _impedance_trace(frequencies, matrices, 0, candidate_index),
            "reverse_transfer_impedance": _impedance_trace(frequencies, matrices, candidate_index, 0),
        })
    return {
        "contract": PDN_MULTIPORT_CONTRACT,
        "model_status": model_status,
        "net": str(payload.get("net", "")),
        "source_result_id": source_result_id,
        "engine_id": engine_id,
        "reference": payload.get("reference", {}),
        "ports": ports,
        "observation_impedance": _impedance_trace(frequencies, matrices, 0, 0),
        "candidates": candidates,
        "z_parameters": normalized_points,
        "quality": {
            **declared_quality,
            "maximum_reciprocity_error": maximum_reciprocity_error,
            "minimum_passivity_eigenvalue_ohm": minimum_passivity_eigenvalue,
        },
        "convergence": convergence,
        "provenance": provenance,
        "validity": payload.get("validity", {}),
    }


def _impedance_trace(
    frequencies: Sequence[float],
    matrices: Sequence[np.ndarray],
    row: int,
    column: int,
) -> List[Dict[str, float]]:
    result: List[Dict[str, float]] = []
    for frequency, matrix in zip(frequencies, matrices):
        value = complex(matrix[row, column])
        result.append({
            "frequency_hz": float(frequency),
            "resistance_ohm": value.real,
            "reactance_ohm": value.imag,
            "magnitude_ohm": abs(value),
            "phase_deg": math.degrees(np.angle(value)),
        })
    return result
