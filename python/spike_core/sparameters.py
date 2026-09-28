"""License-clean Touchstone and S-parameter utilities for SPIKE.

This module is deliberately independent of geometry solvers. PEEC, MoM,
full-wave, measured, and third-party engines can all exchange network data
through the same representation.
"""

from __future__ import annotations

import cmath
import re
from dataclasses import dataclass, field
from math import log10
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np


TOUCHSTONE_CONTRACT = "spike/touchstone-analysis/v1"
_PORTS_FROM_SUFFIX = re.compile(r"\.s(\d+)p$", re.IGNORECASE)
_FREQUENCY_SCALE = {
    "hz": 1.0,
    "khz": 1e3,
    "mhz": 1e6,
    "ghz": 1e9,
}


class TouchstoneError(ValueError):
    """Raised when a network file cannot be interpreted without guessing."""


@dataclass
class NetworkData:
    frequencies_hz: np.ndarray
    parameters: np.ndarray
    reference_impedance_ohm: np.ndarray
    parameter_kind: str = "S"
    data_format: str = "RI"
    source: str = ""
    comments: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def port_count(self) -> int:
        return int(self.parameters.shape[1])

    def s_parameters(self) -> np.ndarray:
        kind = self.parameter_kind.upper()
        if kind == "S":
            return np.asarray(self.parameters, dtype=complex)
        if kind == "Z":
            return z_to_s(self.parameters, self.reference_impedance_ohm)
        if kind == "Y":
            impedance = np.asarray(
                [np.linalg.inv(matrix) for matrix in self.parameters],
                dtype=complex,
            )
            return z_to_s(impedance, self.reference_impedance_ohm)
        raise TouchstoneError(
            f"Touchstone parameter kind {self.parameter_kind!r} is not supported."
        )


def _port_count(path: Path, declared: int | None) -> int:
    match = _PORTS_FROM_SUFFIX.search(path.name)
    suffix_ports = int(match.group(1)) if match else None
    if declared is not None and suffix_ports is not None and declared != suffix_ports:
        raise TouchstoneError(
            f"Touchstone port count {declared} conflicts with the {path.suffix} suffix."
        )
    ports = declared or suffix_ports
    if ports is None or ports < 1:
        raise TouchstoneError(
            "Touchstone port count is missing; use an .sNp suffix or [Number of Ports]."
        )
    if ports > 128:
        raise TouchstoneError("Touchstone files with more than 128 ports are rejected.")
    return ports


def _complex_pair(first: float, second: float, data_format: str) -> complex:
    if data_format == "RI":
        return complex(first, second)
    if data_format == "MA":
        return cmath.rect(first, np.deg2rad(second))
    if data_format == "DB":
        return cmath.rect(10.0 ** (first / 20.0), np.deg2rad(second))
    raise TouchstoneError(f"Unsupported Touchstone data format: {data_format}")


def _parse_numbers(tokens: Iterable[str], line_number: int) -> List[float]:
    result = []
    for token in tokens:
        try:
            value = float(token.replace("D", "E").replace("d", "e"))
        except ValueError as exc:
            raise TouchstoneError(
                f"Invalid numeric token {token!r} on line {line_number}."
            ) from exc
        if not np.isfinite(value):
            raise TouchstoneError(
                f"Non-finite numeric token {token!r} on line {line_number}."
            )
        result.append(value)
    return result


def read_touchstone(path: str | Path) -> NetworkData:
    source_path = Path(path)
    if not source_path.is_file():
        raise TouchstoneError(f"Touchstone input does not exist: {source_path}")
    try:
        lines = source_path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError:
        lines = source_path.read_text(encoding="latin-1").splitlines()
    return parse_touchstone_text("\n".join(lines), str(source_path.resolve()))


def parse_touchstone_text(text: str, name: str = "network.s2p") -> NetworkData:
    """Parse uploaded text without granting filesystem access to a UI payload."""
    if not isinstance(text, str) or len(text) > 32_000_000:
        raise TouchstoneError("Touchstone text must be at most 32 MB.")
    source_path = Path(name)
    lines = text.lstrip("\ufeff").splitlines()

    frequency_unit = "ghz"
    parameter_kind = "S"
    data_format = "MA"
    reference_values = [50.0]
    declared_ports: int | None = None
    matrix_format = "full"
    comments: List[str] = []
    warnings: List[str] = []
    numeric_tokens: List[tuple[str, int]] = []
    in_network_data = True
    two_port_order = "21_12"

    for line_number, raw_line in enumerate(lines, 1):
        content, separator, comment = raw_line.partition("!")
        if separator and comment.strip():
            comments.append(comment.strip())
        stripped = content.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            option = stripped[1:].split()
            lowered = [item.lower() for item in option]
            if lowered and lowered[0] in _FREQUENCY_SCALE:
                frequency_unit = lowered[0]
            if len(lowered) >= 2:
                parameter_kind = lowered[1].upper()
            if len(lowered) >= 3:
                data_format = lowered[2].upper()
            if "r" in lowered:
                index = lowered.index("r")
                if index + 1 >= len(option):
                    raise TouchstoneError(
                        f"Reference impedance is missing on line {line_number}."
                    )
                reference_values = _parse_numbers([option[index + 1]], line_number)
            continue
        if stripped.startswith("["):
            closing = stripped.find("]")
            if closing < 0:
                raise TouchstoneError(f"Malformed Touchstone keyword on line {line_number}.")
            keyword = stripped[1:closing].strip().lower()
            value = stripped[closing + 1 :].strip()
            if keyword == "number of ports":
                declared_ports = int(value)
            elif keyword == "reference":
                reference_values = _parse_numbers(value.split(), line_number)
            elif keyword == "matrix format":
                matrix_format = value.lower()
            elif keyword == "two-port data order":
                if value not in {"21_12", "12_21"}:
                    raise TouchstoneError("Unsupported [Two-Port Data Order].")
                two_port_order = value
            elif keyword == "mixed-mode order":
                raise TouchstoneError("Mixed-mode Touchstone input must first be converted to single-ended ports.")
            elif keyword == "network data":
                in_network_data = True
            elif keyword in {"noise data", "end"}:
                in_network_data = False
            continue
        if in_network_data:
            numeric_tokens.extend((token, line_number) for token in stripped.split())

    ports = _port_count(source_path, declared_ports)
    if matrix_format != "full":
        raise TouchstoneError(
            f"Touchstone matrix format {matrix_format!r} is not supported yet; export a full matrix."
        )
    if parameter_kind not in {"S", "Z", "Y"}:
        raise TouchstoneError(
            f"Touchstone parameter kind {parameter_kind!r} is unsupported; use S, Z, or Y."
        )
    if data_format not in {"RI", "MA", "DB"}:
        raise TouchstoneError(
            f"Touchstone data format {data_format!r} is unsupported; use RI, MA, or DB."
        )
    if len(reference_values) not in {1, ports}:
        raise TouchstoneError(
            f"Expected one or {ports} reference impedances, got {len(reference_values)}."
        )
    reference = np.asarray(
        reference_values if len(reference_values) == ports else reference_values * ports,
        dtype=float,
    )
    if np.any(reference <= 0):
        raise TouchstoneError("Reference impedances must be positive.")

    values_per_frequency = 1 + 2 * ports * ports
    if not numeric_tokens:
        raise TouchstoneError("Touchstone file contains no network data.")
    if len(numeric_tokens) % values_per_frequency:
        line_number = numeric_tokens[-1][1]
        raise TouchstoneError(
            f"Incomplete {ports}-port network record near line {line_number}; "
            f"expected {values_per_frequency} numeric values per frequency."
        )

    records = len(numeric_tokens) // values_per_frequency
    frequencies = np.empty(records, dtype=float)
    matrices = np.empty((records, ports, ports), dtype=complex)
    scale = _FREQUENCY_SCALE[frequency_unit]
    for record_index in range(records):
        offset = record_index * values_per_frequency
        group = numeric_tokens[offset : offset + values_per_frequency]
        values = _parse_numbers(
            [token for token, _ in group],
            group[0][1],
        )
        frequencies[record_index] = values[0] * scale
        pairs = values[1:]
        # Two-port legacy order is special; 3+ ports use matrix rows.
        for pair_index in range(ports * ports):
            column_major = ports == 2 and two_port_order == "21_12"
            row = pair_index % ports if column_major else pair_index // ports
            column = pair_index // ports if column_major else pair_index % ports
            matrices[record_index, row, column] = _complex_pair(
                pairs[2 * pair_index],
                pairs[2 * pair_index + 1],
                data_format,
            )

    if np.any(frequencies < 0):
        raise TouchstoneError("Frequency values cannot be negative.")
    if np.any(np.diff(frequencies) <= 0):
        raise TouchstoneError("Frequency values must be strictly increasing.")
    if frequencies[0] > 0:
        warnings.append(
            "The file has no DC point; time-domain and causality workflows require extrapolation."
        )
    ratios = np.diff(frequencies)
    if ratios.size > 1 and not np.allclose(ratios, ratios[0], rtol=1e-5, atol=0):
        warnings.append(
            "The frequency grid is nonuniform; time-domain conversion requires resampling."
        )

    return NetworkData(
        frequencies_hz=frequencies,
        parameters=matrices,
        reference_impedance_ohm=reference,
        parameter_kind=parameter_kind,
        data_format=data_format,
        source=str(source_path),
        comments=comments,
        warnings=warnings,
    )


def _reference_vector(reference: float | Sequence[float] | np.ndarray, ports: int) -> np.ndarray:
    values = np.asarray(reference, dtype=float)
    if values.ndim == 0:
        values = np.repeat(values, ports)
    if values.shape != (ports,) or np.any(values <= 0) or not np.all(np.isfinite(values)):
        raise ValueError(f"Reference impedance must contain {ports} positive finite values.")
    return values


def s_to_z(
    s_parameters: np.ndarray,
    reference_impedance_ohm: float | Sequence[float] | np.ndarray = 50.0,
) -> np.ndarray:
    s = np.asarray(s_parameters, dtype=complex)
    single = s.ndim == 2
    if single:
        s = s[np.newaxis, ...]
    if s.ndim != 3 or s.shape[1] != s.shape[2]:
        raise ValueError("S-parameters must be an N x N matrix or frequency stack.")
    ports = s.shape[1]
    reference = _reference_vector(reference_impedance_ohm, ports)
    root = np.diag(np.sqrt(reference))
    identity = np.eye(ports, dtype=complex)
    result = np.empty_like(s)
    for index, matrix in enumerate(s):
        try:
            normalized = np.linalg.solve((identity - matrix).T, (identity + matrix).T).T
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                f"S-to-Z conversion is singular at sample {index}."
            ) from exc
        result[index] = root @ normalized @ root
    return result[0] if single else result


def z_to_s(
    impedance: np.ndarray,
    reference_impedance_ohm: float | Sequence[float] | np.ndarray = 50.0,
) -> np.ndarray:
    z = np.asarray(impedance, dtype=complex)
    single = z.ndim == 2
    if single:
        z = z[np.newaxis, ...]
    if z.ndim != 3 or z.shape[1] != z.shape[2]:
        raise ValueError("Impedance must be an N x N matrix or frequency stack.")
    ports = z.shape[1]
    reference = _reference_vector(reference_impedance_ohm, ports)
    inverse_root = np.diag(1.0 / np.sqrt(reference))
    identity = np.eye(ports, dtype=complex)
    result = np.empty_like(z)
    for index, matrix in enumerate(z):
        normalized = inverse_root @ matrix @ inverse_root
        try:
            result[index] = np.linalg.solve(
                (normalized + identity).T,
                (normalized - identity).T,
            ).T
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                f"Z-to-S conversion is singular at sample {index}."
            ) from exc
    return result[0] if single else result


def s_to_y(
    s_parameters: np.ndarray,
    reference_impedance_ohm: float | Sequence[float] | np.ndarray = 50.0,
) -> np.ndarray:
    impedance = s_to_z(s_parameters, reference_impedance_ohm)
    single = impedance.ndim == 2
    matrices = impedance[np.newaxis, ...] if single else impedance
    try:
        result = np.asarray([np.linalg.inv(matrix) for matrix in matrices])
    except np.linalg.LinAlgError as exc:
        raise ValueError("S-to-Y conversion encountered a singular impedance matrix.") from exc
    return result[0] if single else result


def renormalize_s(
    s_parameters: np.ndarray,
    old_reference_ohm: float | Sequence[float] | np.ndarray,
    new_reference_ohm: float | Sequence[float] | np.ndarray,
) -> np.ndarray:
    return z_to_s(s_to_z(s_parameters, old_reference_ohm), new_reference_ohm)


def single_ended_to_mixed_mode(s_parameters: np.ndarray) -> np.ndarray:
    """Transform adjacent +/- port pairs to differential/common-mode waves.

    Input ports are paired (1,2), (3,4), ... and output ordering is
    D1..Dn,C1..Cn. The transform assumes equal real single-ended reference
    impedances. Differential/common impedance conventions remain metadata and
    must be stated explicitly by exporters.
    """

    s = np.asarray(s_parameters, dtype=complex)
    single = s.ndim == 2
    if single:
        s = s[np.newaxis, ...]
    if s.ndim != 3 or s.shape[1] != s.shape[2] or s.shape[1] % 2:
        raise ValueError("Mixed-mode conversion requires an even-port square matrix.")
    ports = s.shape[1]
    pairs = ports // 2
    transform = np.zeros((ports, ports), dtype=float)
    scale = 1.0 / np.sqrt(2.0)
    for pair in range(pairs):
        positive = pair * 2
        negative = positive + 1
        transform[pair, positive] = scale
        transform[pair, negative] = -scale
        transform[pairs + pair, positive] = scale
        transform[pairs + pair, negative] = scale
    result = np.asarray([transform @ matrix @ transform.T for matrix in s])
    return result[0] if single else result


def _trace_points(
    frequencies: np.ndarray,
    values: np.ndarray,
    limit: int | None,
) -> List[Dict[str, float]]:
    indices = np.arange(len(frequencies))
    if limit and limit > 1 and len(indices) > limit:
        indices = np.unique(np.linspace(0, len(indices) - 1, limit).astype(int))
    phase = np.unwrap(np.angle(values))
    result = []
    for index in indices:
        magnitude = abs(values[index])
        result.append(
            {
                "frequency_hz": float(frequencies[index]),
                "magnitude": float(magnitude),
                "magnitude_db": float(20.0 * log10(max(magnitude, 1e-300))),
                "phase_deg": float(np.rad2deg(phase[index])),
            }
        )
    return result


def analyze_network(
    network: NetworkData,
    *,
    trace_limit: int | None = None,
    passivity_tolerance: float = 1e-9,
    reciprocity_tolerance: float = 1e-6,
) -> Dict[str, Any]:
    s = network.s_parameters()
    frequencies = network.frequencies_hz
    ports = network.port_count
    singular_values = np.asarray(
        [np.linalg.svd(matrix, compute_uv=False)[0] for matrix in s],
        dtype=float,
    )
    reciprocity_error = np.asarray(
        [np.max(np.abs(matrix - matrix.T)) for matrix in s],
        dtype=float,
    )
    passivity_mask = singular_values > 1.0 + passivity_tolerance
    reciprocity_mask = reciprocity_error > reciprocity_tolerance
    issues: List[Dict[str, Any]] = []
    for warning in network.warnings:
        issues.append(
            {
                "code": "TOUCHSTONE_TIME_DOMAIN_LIMIT",
                "severity": "warning",
                "message": warning,
            }
        )
    if np.any(passivity_mask):
        worst = int(np.argmax(singular_values))
        issues.append(
            {
                "code": "SPARAM_PASSIVITY_VIOLATION",
                "severity": "warning",
                "message": (
                    f"Maximum singular value is {singular_values[worst]:.6g} "
                    f"at {frequencies[worst]:.6g} Hz."
                ),
            }
        )
    if np.any(reciprocity_mask):
        worst = int(np.argmax(reciprocity_error))
        issues.append(
            {
                "code": "SPARAM_NONRECIPROCAL",
                "severity": "info",
                "message": (
                    f"Maximum |S-S^T| is {reciprocity_error[worst]:.6g} "
                    f"at {frequencies[worst]:.6g} Hz. Active or ferrite devices may be intentionally nonreciprocal."
                ),
            }
        )

    traces: Dict[str, List[Dict[str, float]]] = {}
    for destination in range(ports):
        for source in range(ports):
            key = f"S{destination + 1}{source + 1}"
            traces[key] = _trace_points(
                frequencies,
                s[:, destination, source],
                trace_limit,
            )

    # Sii is the port reflection when every OTHER port is matched to its
    # reference resistance. A standing-wave ratio is meaningful only for a
    # reflection magnitude strictly below one; an ideal open is infinite.
    reflection_vswr = []
    indices = np.arange(len(frequencies)) if trace_limit is None else np.unique(
        np.linspace(0, len(frequencies) - 1, min(len(frequencies), trace_limit)).astype(int)
    )
    for port in range(ports):
        samples = []
        for index in indices:
            gamma = s[index, port, port]
            magnitude = float(abs(gamma))
            if magnitude > 1.0 + 1e-12:
                status, vswr = "non_passive_reflection", None
            elif magnitude >= 1.0 - 1e-12:
                status, vswr = "infinite", None
            else:
                status, vswr = "finite", float((1.0 + magnitude) / (1.0 - magnitude))
            samples.append({"frequency_hz": float(frequencies[index]),
                            "reflection_real": float(gamma.real), "reflection_imag": float(gamma.imag),
                            "reflection_magnitude": magnitude, "vswr": vswr,
                            "vswr_status": status})
        reflection_vswr.append({"port": port, "trace": samples})

    mixed_mode: Dict[str, Any] | None = None
    if ports % 2 == 0:
        mixed = single_ended_to_mixed_mode(s)
        pairs = ports // 2
        mixed_traces: Dict[str, List[Dict[str, float]]] = {}
        for destination in range(ports):
            destination_mode = "D" if destination < pairs else "C"
            destination_pair = destination % pairs + 1
            for source in range(ports):
                source_mode = "D" if source < pairs else "C"
                source_pair = source % pairs + 1
                key = (
                    f"S{destination_mode}{source_mode}"
                    f"{destination_pair}{source_pair}"
                )
                mixed_traces[key] = _trace_points(
                    frequencies,
                    mixed[:, destination, source],
                    trace_limit,
                )
        mixed_mode = {
            "port_pairs": [
                {"positive": pair * 2 + 1, "negative": pair * 2 + 2}
                for pair in range(pairs)
            ],
            "ordering": [
                *[f"D{pair + 1}" for pair in range(pairs)],
                *[f"C{pair + 1}" for pair in range(pairs)],
            ],
            "traces": mixed_traces,
            "reference_note": (
                "Equal-reference orthonormal wave transform. Differential and "
                "common-mode impedance conventions must be preserved by exporters."
            ),
        }

    group_delay: List[Dict[str, float]] = []
    if ports >= 2 and len(frequencies) >= 2:
        phase = np.unwrap(np.angle(s[:, 1, 0]))
        delay = -np.gradient(phase, 2.0 * np.pi * frequencies)
        group_delay = [
            {
                "frequency_hz": float(frequency),
                "group_delay_s": float(value),
            }
            for frequency, value in zip(frequencies, delay)
        ]

    input_impedance: List[Dict[str, float]] = []
    try:
        impedance = s_to_z(s, network.reference_impedance_ohm)
        input_impedance = [
            {
                "frequency_hz": float(frequency),
                "resistance_ohm": float(matrix[0, 0].real),
                "reactance_ohm": float(matrix[0, 0].imag),
                "magnitude_ohm": float(abs(matrix[0, 0])),
                "phase_deg": float(np.rad2deg(np.angle(matrix[0, 0]))),
            }
            for frequency, matrix in zip(frequencies, impedance)
        ]
    except ValueError as exc:
        issues.append(
            {
                "code": "SPARAM_IMPEDANCE_CONVERSION_FAILED",
                "severity": "warning",
                "message": str(exc),
            }
        )

    from .si_impedance import network_impedance_report

    return {
        "contract": TOUCHSTONE_CONTRACT,
        "status": "completed",
        "model_status": "source_dependent",
        "network_quality_status": "warning" if issues else "pass",
        "source": network.source,
        "parameter_kind": network.parameter_kind,
        "data_format": network.data_format,
        "port_count": ports,
        "frequency": {
            "count": int(len(frequencies)),
            "start_hz": float(frequencies[0]),
            "stop_hz": float(frequencies[-1]),
            "uniform_spacing": bool(
                len(frequencies) < 3
                or np.allclose(np.diff(frequencies), np.diff(frequencies)[0], rtol=1e-5, atol=0)
            ),
            "has_dc": bool(frequencies[0] == 0),
        },
        "reference_impedance_ohm": network.reference_impedance_ohm.tolist(),
        "checks": {
            "passivity": {
                "status": "fail" if np.any(passivity_mask) else "pass",
                "worst_singular_value": float(np.max(singular_values)),
                "violation_count": int(np.count_nonzero(passivity_mask)),
            },
            "reciprocity": {
                "status": "fail" if np.any(reciprocity_mask) else "pass",
                "worst_error": float(np.max(reciprocity_error)),
                "violation_count": int(np.count_nonzero(reciprocity_mask)),
            },
            "causality": {
                "status": "not_evaluated",
                "reason": (
                    "A defensible causality check requires DC handling, uniform resampling, "
                    "window policy, and delay removal; SPIKE does not silently infer these choices."
                ),
            },
        },
        "traces": traces,
        "reflection_vswr": {"ports": reflection_vswr,
                            "definition": "Sii with all other ports matched to their real reference impedances; VSWR=(1+|Sii|)/(1-|Sii|) for |Sii|<1",
                            "vswr_unavailable_as_null": True},
        "mixed_mode": mixed_mode,
        "group_delay_s21": group_delay,
        "input_impedance_port1": input_impedance,
        "input_impedance_port1_definition": "Open-circuit Z11; all OTHER ports open. Not matched input impedance.",
        "impedance_response": network_impedance_report(network, trace_limit=max(16, min(trace_limit if trace_limit is not None else 2048, 16384))),
        "issues": issues,
        "provenance": {
            "implementation": "SPIKE independent network analysis",
            "touchstone_parser": "spike/touchstone/v1",
            "complex_wave_definition": "pseudo-wave with real positive reference impedance",
        },
    }


def write_touchstone(
    path: str | Path,
    frequencies_hz: Sequence[float] | np.ndarray,
    s_parameters: np.ndarray,
    reference_impedance_ohm: float | Sequence[float] | np.ndarray = 50.0,
    *,
    data_format: str = "RI",
    comments: Sequence[str] = (),
) -> None:
    destination = Path(path)
    text = touchstone_text(frequencies_hz, s_parameters, reference_impedance_ohm,
                          data_format=data_format, comments=comments)
    _port_count(destination, np.asarray(s_parameters).shape[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="ascii")


def touchstone_text(
    frequencies_hz: Sequence[float] | np.ndarray,
    s_parameters: np.ndarray,
    reference_impedance_ohm: float | Sequence[float] | np.ndarray = 50.0,
    *, data_format: str = "RI", comments: Sequence[str] = (),
) -> str:
    s = np.asarray(s_parameters, dtype=complex)
    frequencies = np.asarray(frequencies_hz, dtype=float)
    if s.ndim != 3 or s.shape[1] != s.shape[2] or s.shape[0] != len(frequencies):
        raise ValueError("S-parameter output must have shape (frequency, port, port).")
    ports = s.shape[1]
    if not 1 <= ports <= 128 or frequencies.ndim != 1 or not len(frequencies):
        raise ValueError("Touchstone requires 1..128 ports and a nonempty frequency vector.")
    if not np.all(np.isfinite(s)) or not np.all(np.isfinite(frequencies)) or np.any(frequencies < 0) or np.any(np.diff(frequencies) <= 0):
        raise ValueError("Touchstone output must be finite with increasing non-negative frequencies.")
    reference = _reference_vector(reference_impedance_ohm, ports)
    if not np.allclose(reference, reference[0]):
        raise ValueError("Touchstone 1.0 output requires one shared reference impedance.")
    format_name = data_format.upper()
    if format_name not in {"RI", "MA", "DB"}:
        raise ValueError("Touchstone output format must be RI, MA, or DB.")

    lines = [f"! {line.encode('ascii', 'replace').decode('ascii')}" for comment in comments for line in str(comment).splitlines()]
    lines.append(f"# Hz S {format_name} R {reference[0]:.17g}")
    for frequency, matrix in zip(frequencies, s):
        # Preserve binary64 precision. Rounding dense high-frequency grids to
        # 12 digits can make adjacent spacings fail the uniform-grid contract.
        values = [f"{frequency:.17g}"]
        for outer in range(ports):
            for inner in range(ports):
                row, column = (inner, outer) if ports == 2 else (outer, inner)
                value = matrix[row, column]
                if format_name == "RI":
                    first, second = value.real, value.imag
                elif format_name == "MA":
                    first, second = abs(value), np.rad2deg(np.angle(value))
                else:
                    first = 20.0 * log10(max(abs(value), 1e-300))
                    second = np.rad2deg(np.angle(value))
                values.extend((f"{first:.17g}", f"{second:.17g}"))
                if ports >= 3 and ((inner + 1) % 4 == 0 or inner == ports - 1):
                    lines.append(" ".join(values))
                    values = []
        if values:
            lines.append(" ".join(values))
    return "\n".join(lines) + "\n"
