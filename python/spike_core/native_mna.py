"""Deterministic linear modified-nodal-analysis circuit engine.

This module is the first native circuit boundary for SPIKE.  It intentionally
supports only linear devices and explicit independent/dependent sources.  A
request containing a nonlinear or unknown device is blocked rather than being
silently simplified.  The result contract is JSON-compatible and independent
of the desktop UI and ngspice adapter.
"""

from __future__ import annotations

import cmath
import math
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
from scipy.sparse import lil_matrix, spmatrix

from .acceleration import AccelerationUnavailableError, solve_sparse_system


REQUEST_CONTRACT = "spike/native-mna-request/v1"
RESULT_CONTRACT = "spike/native-mna-result/v1"
VALIDATION_CONTRACT = "spike/native-mna-validation/v1"

SUPPORTED_ELEMENTS = {
    "resistor",
    "capacitor",
    "inductor",
    "voltage_source",
    "current_source",
    "vccs",
    "vcvs",
    "cccs",
    "ccvs",
}
BRANCH_ELEMENTS = {"inductor", "voltage_source", "vcvs", "ccvs"}
SOURCE_ELEMENTS = {"voltage_source", "current_source"}
SUPPORTED_WAVEFORMS = {"constant", "step", "pulse", "pwl"}
MAX_ELEMENTS = 100_000
MAX_POINTS = 1_000_000
MAX_DENSE_UNKNOWNS = 10_000
DEFAULT_SPARSE_THRESHOLD = 256


def _issue(code: str, message: str, path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": "error", "message": message, "path": path}


def _finite(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if positive and number <= 0:
        return None
    if nonnegative and number < 0:
        return None
    return number


def _node(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _linear_backend(request: Dict[str, Any], unknown_count: int) -> str:
    limits = request.get("resource_limits") if isinstance(request.get("resource_limits"), dict) else {}
    requested = str(limits.get("linear_backend", "auto") or "auto").strip().lower()
    aliases = {
        "superlu": "scipy-superlu",
        "scipy": "scipy-superlu",
        "mumps": "petsc-mumps",
        "petsc": "petsc-mumps",
    }
    requested = aliases.get(requested, requested)
    if requested not in {"auto", "dense", "scipy-superlu", "petsc-mumps"}:
        return "invalid"
    threshold = _finite(limits.get("sparse_threshold", DEFAULT_SPARSE_THRESHOLD), positive=True)
    threshold_count = int(threshold) if threshold is not None else DEFAULT_SPARSE_THRESHOLD
    if requested == "auto":
        return "scipy-superlu" if unknown_count >= threshold_count else "dense"
    return requested


def _element_nodes(element: Dict[str, Any]) -> Iterable[str]:
    for key in ("positive_node", "negative_node", "control_positive_node", "control_negative_node"):
        value = _node(element.get(key))
        if value:
            yield value


def _validate_waveform(element: Dict[str, Any], path: str, issues: List[Dict[str, str]]) -> None:
    waveform = element.get("waveform")
    if waveform is None:
        for key in ("dc_value", "value", "ac_magnitude", "ac_phase_deg"):
            if key in element and _finite(element.get(key), nonnegative=(key == "ac_magnitude")) is None:
                issues.append(_issue("MNA_SOURCE_VALUE_INVALID", f"{key} must be finite.", f"{path}.{key}"))
        return
    if not isinstance(waveform, dict):
        issues.append(_issue("MNA_WAVEFORM_INVALID", "A source waveform must be an object.", f"{path}.waveform"))
        return
    kind = str(waveform.get("type", "constant")).strip().lower()
    if kind not in SUPPORTED_WAVEFORMS:
        issues.append(_issue(
            "MNA_WAVEFORM_UNSUPPORTED",
            f"Waveform type {kind or 'missing'} is unsupported; expected constant, step, pulse, or pwl.",
            f"{path}.waveform.type",
        ))
        return
    scalar_fields = {
        "constant": (("value", False),),
        "step": (("initial", False), ("final", False), ("delay_s", True), ("rise_time_s", True)),
        "pulse": (
            ("low", False), ("high", False), ("delay_s", True), ("rise_time_s", True),
            ("fall_time_s", True), ("pulse_width_s", True), ("period_s", True),
        ),
    }
    for key, nonnegative in scalar_fields.get(kind, ()):
        if key in waveform and _finite(waveform.get(key), nonnegative=nonnegative) is None:
            issues.append(_issue("MNA_WAVEFORM_VALUE_INVALID", f"{key} must be finite and physically valid.", f"{path}.waveform.{key}"))
    if kind == "pulse":
        width = _finite(waveform.get("pulse_width_s", 0.0), positive=True)
        period = _finite(waveform.get("period_s", 0.0), nonnegative=True)
        if width is None:
            issues.append(_issue("MNA_PULSE_WIDTH_INVALID", "Pulse width must be finite and positive.", f"{path}.waveform.pulse_width_s"))
        if period is not None and period > 0.0:
            rise = float(waveform.get("rise_time_s", 0.0) or 0.0)
            fall = float(waveform.get("fall_time_s", 0.0) or 0.0)
            if width is not None and rise + width + fall > period:
                issues.append(_issue("MNA_PULSE_PERIOD_INVALID", "Pulse rise, width, and fall exceed its period.", f"{path}.waveform.period_s"))
    if kind == "pwl":
        points = waveform.get("points")
        if not isinstance(points, list) or not points:
            issues.append(_issue("MNA_PWL_POINTS_REQUIRED", "A PWL source requires at least one [time, value] point.", f"{path}.waveform.points"))
            return
        previous_time = -math.inf
        for point_index, point in enumerate(points):
            point_path = f"{path}.waveform.points[{point_index}]"
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                issues.append(_issue("MNA_PWL_POINT_INVALID", "Each PWL point must be [time_s, value].", point_path))
                continue
            time_value = _finite(point[0], nonnegative=True)
            signal_value = _finite(point[1])
            if time_value is None or signal_value is None or time_value <= previous_time:
                issues.append(_issue("MNA_PWL_POINT_INVALID", "PWL times must be finite, nonnegative, and strictly increasing; values must be finite.", point_path))
            if time_value is not None:
                previous_time = time_value


def validate_native_mna_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a native MNA request without executing numerical work."""

    issues: List[Dict[str, str]] = []
    if not isinstance(request, dict) or request.get("contract") != REQUEST_CONTRACT:
        return {
            "contract": VALIDATION_CONTRACT,
            "valid": False,
            "issues": [_issue("MNA_REQUEST_CONTRACT_INVALID", f"Expected {REQUEST_CONTRACT}.")],
        }
    ground = _node(request.get("ground_node", "0"))
    if not ground:
        issues.append(_issue("MNA_GROUND_REQUIRED", "An explicit circuit ground node is required.", "ground_node"))
    elements = request.get("elements")
    if not isinstance(elements, list) or not elements or len(elements) > MAX_ELEMENTS:
        issues.append(_issue("MNA_ELEMENT_COUNT_INVALID", f"Elements must contain 1 to {MAX_ELEMENTS} entries.", "elements"))
        elements = []

    identifiers: set[str] = set()
    branch_identifiers: set[str] = set()
    for index, element in enumerate(elements):
        path = f"elements[{index}]"
        if not isinstance(element, dict):
            issues.append(_issue("MNA_ELEMENT_INVALID", "Each circuit element must be an object.", path))
            continue
        identifier = str(element.get("id", "")).strip()
        if not identifier:
            issues.append(_issue("MNA_ELEMENT_ID_REQUIRED", "Each circuit element requires an ID.", f"{path}.id"))
        elif identifier in identifiers:
            issues.append(_issue("MNA_ELEMENT_ID_DUPLICATE", f"Duplicate element ID: {identifier}.", f"{path}.id"))
        identifiers.add(identifier)
        kind = str(element.get("type", "")).strip().lower()
        if kind not in SUPPORTED_ELEMENTS:
            issues.append(_issue(
                "MNA_ELEMENT_UNSUPPORTED",
                f"Element type {kind or 'missing'} is not supported by the linear native MNA engine.",
                f"{path}.type",
            ))
            continue
        if kind in BRANCH_ELEMENTS:
            branch_identifiers.add(identifier)
        positive = _node(element.get("positive_node"))
        negative = _node(element.get("negative_node"))
        if not positive or not negative or positive == negative:
            issues.append(_issue("MNA_ELEMENT_NODES_INVALID", "Elements require two distinct explicit terminal nodes.", path))
        if kind in {"resistor", "capacitor", "inductor"}:
            key = {"resistor": "resistance_ohm", "capacitor": "capacitance_f", "inductor": "inductance_h"}[kind]
            if _finite(element.get(key), positive=True) is None:
                issues.append(_issue("MNA_ELEMENT_VALUE_INVALID", f"{kind} requires finite positive {key}.", f"{path}.{key}"))
        if kind in SOURCE_ELEMENTS:
            _validate_waveform(element, path, issues)
        if kind in {"vccs", "vcvs"}:
            control_positive = _node(element.get("control_positive_node"))
            control_negative = _node(element.get("control_negative_node"))
            if not control_positive or not control_negative or control_positive == control_negative:
                issues.append(_issue("MNA_CONTROL_NODES_INVALID", f"{kind} requires two distinct control nodes.", path))
            key = "transconductance_s" if kind == "vccs" else "gain"
            if _finite(element.get(key)) is None:
                issues.append(_issue("MNA_DEPENDENT_VALUE_INVALID", f"{kind} requires finite {key}.", f"{path}.{key}"))
        if kind in {"cccs", "ccvs"}:
            key = "gain" if kind == "cccs" else "transresistance_ohm"
            if _finite(element.get(key)) is None:
                issues.append(_issue("MNA_DEPENDENT_VALUE_INVALID", f"{kind} requires finite {key}.", f"{path}.{key}"))

    for index, element in enumerate(elements):
        if not isinstance(element, dict) or str(element.get("type", "")).lower() not in {"cccs", "ccvs"}:
            continue
        control = str(element.get("control_source_id", "")).strip()
        if control not in branch_identifiers:
            issues.append(_issue(
                "MNA_CONTROL_SOURCE_INVALID",
                "Current-controlled sources must reference a voltage-defined branch element in the same request.",
                f"elements[{index}].control_source_id",
            ))

    analysis = request.get("analysis")
    if not isinstance(analysis, dict):
        issues.append(_issue("MNA_ANALYSIS_REQUIRED", "An analysis object is required.", "analysis"))
        analysis = {}
    mode = str(analysis.get("mode", "")).strip().lower()
    if mode not in {"operating_point", "ac", "transient"}:
        issues.append(_issue("MNA_ANALYSIS_MODE_INVALID", "Mode must be operating_point, ac, or transient.", "analysis.mode"))
    elif mode == "ac":
        start = _finite(analysis.get("start_hz"), positive=True)
        stop = _finite(analysis.get("stop_hz"), positive=True)
        points = _finite(analysis.get("points"), positive=True)
        if start is None or stop is None or stop < start:
            issues.append(_issue("MNA_AC_RANGE_INVALID", "AC analysis requires 0 < start_hz <= stop_hz.", "analysis"))
        if points is None or int(points) != points or points > MAX_POINTS:
            issues.append(_issue("MNA_POINT_BUDGET_INVALID", f"AC points must be an integer from 1 to {MAX_POINTS}.", "analysis.points"))
        if str(analysis.get("scale", "log")).strip().lower() not in {"linear", "log"}:
            issues.append(_issue("MNA_AC_SCALE_INVALID", "AC scale must be linear or log.", "analysis.scale"))
    elif mode == "transient":
        step = _finite(analysis.get("time_step_s"), positive=True)
        stop = _finite(analysis.get("stop_time_s"), positive=True)
        if step is None or stop is None or step > stop:
            issues.append(_issue("MNA_TRANSIENT_RANGE_INVALID", "Transient analysis requires 0 < time_step_s <= stop_time_s.", "analysis"))
        elif math.floor(stop / step + 1e-12) + 1 > MAX_POINTS:
            issues.append(_issue("MNA_POINT_BUDGET_INVALID", f"Transient analysis is limited to {MAX_POINTS} output points.", "analysis"))

    node_count = len({node for element in elements if isinstance(element, dict) for node in _element_nodes(element)} - {ground})
    branch_count = sum(
        1 for element in elements
        if isinstance(element, dict) and str(element.get("type", "")).lower() in BRANCH_ELEMENTS
    )
    unknown_count = node_count + branch_count
    memory_limit_gb = _finite((request.get("resource_limits") or {}).get("memory_limit_gb", 2.0), positive=True)
    bytes_per_scalar = 16 if mode == "ac" else 8
    estimated_dense_bytes = bytes_per_scalar * (unknown_count * unknown_count + 4 * unknown_count)
    estimated_nonzeros = max(unknown_count, min(unknown_count * unknown_count, len(elements) * 16 + unknown_count * 2))
    estimated_sparse_bytes = estimated_nonzeros * (bytes_per_scalar + 16) + unknown_count * 64
    selected_backend = _linear_backend(request, unknown_count)
    if selected_backend == "invalid":
        issues.append(_issue(
            "MNA_LINEAR_BACKEND_INVALID",
            "linear_backend must be auto, dense, scipy-superlu, or petsc-mumps.",
            "resource_limits.linear_backend",
        ))
    if selected_backend == "dense" and unknown_count > MAX_DENSE_UNKNOWNS:
        issues.append(_issue(
            "MNA_DENSE_UNKNOWN_LIMIT_EXCEEDED",
            f"The explicitly selected dense backend is limited to {MAX_DENSE_UNKNOWNS} unknowns; select an available sparse backend.",
            "elements",
        ))
    if memory_limit_gb is None or memory_limit_gb < 2.0:
        issues.append(_issue("MNA_MEMORY_LIMIT_INVALID", "Circuit memory_limit_gb must be at least 2 GB.", "resource_limits.memory_limit_gb"))
    estimated_bytes = estimated_dense_bytes if selected_backend == "dense" else estimated_sparse_bytes
    if memory_limit_gb is not None and estimated_bytes > memory_limit_gb * (1024 ** 3):
        issues.append(_issue(
            "MNA_MEMORY_BUDGET_EXCEEDED",
            f"Estimated {selected_backend} matrix storage is {estimated_bytes / (1024 ** 3):.3f} GB, above the {memory_limit_gb:g} GB limit.",
            "resource_limits.memory_limit_gb",
        ))
    return {
        "contract": VALIDATION_CONTRACT,
        "valid": not issues,
        "issues": issues,
        "counts": {
            "elements": len(elements),
            "nodes": node_count + 1,
            "branches": branch_count,
            "unknowns": unknown_count,
            "selected_linear_backend": selected_backend,
            "estimated_matrix_bytes": estimated_bytes,
            "estimated_dense_matrix_bytes": estimated_dense_bytes,
            "estimated_sparse_matrix_bytes": estimated_sparse_bytes,
            "estimated_nonzeros": estimated_nonzeros,
        },
    }


def _source_value(element: Dict[str, Any], time_s: float) -> float:
    waveform = element.get("waveform")
    if not isinstance(waveform, dict):
        return float(element.get("dc_value", element.get("value", 0.0)) or 0.0)
    kind = str(waveform.get("type", "constant")).lower()
    if kind == "constant":
        return float(waveform.get("value", element.get("dc_value", 0.0)) or 0.0)
    if kind == "step":
        initial = float(waveform.get("initial", 0.0))
        final = float(waveform.get("final", initial))
        delay = max(0.0, float(waveform.get("delay_s", 0.0)))
        rise = max(0.0, float(waveform.get("rise_time_s", 0.0)))
        if time_s < delay:
            return initial
        if rise and time_s < delay + rise:
            return initial + (final - initial) * (time_s - delay) / rise
        return final
    if kind == "pulse":
        low = float(waveform.get("low", 0.0))
        high = float(waveform.get("high", low))
        delay = max(0.0, float(waveform.get("delay_s", 0.0)))
        rise = max(0.0, float(waveform.get("rise_time_s", 0.0)))
        fall = max(0.0, float(waveform.get("fall_time_s", 0.0)))
        width = max(0.0, float(waveform.get("pulse_width_s", 0.0)))
        period = max(0.0, float(waveform.get("period_s", 0.0)))
        if time_s < delay:
            return low
        local = time_s - delay
        if period:
            local %= period
        if rise and local < rise:
            return low + (high - low) * local / rise
        if local < rise + width:
            return high
        if fall and local < rise + width + fall:
            return high + (low - high) * (local - rise - width) / fall
        return low
    if kind == "pwl":
        points = waveform.get("points", [])
        parsed = sorted((float(item[0]), float(item[1])) for item in points if isinstance(item, (list, tuple)) and len(item) == 2)
        if not parsed:
            return 0.0
        if time_s <= parsed[0][0]:
            return parsed[0][1]
        for (left_t, left_v), (right_t, right_v) in zip(parsed, parsed[1:]):
            if time_s <= right_t:
                ratio = (time_s - left_t) / max(right_t - left_t, np.finfo(float).eps)
                return left_v + ratio * (right_v - left_v)
        return parsed[-1][1]
    raise ValueError(f"Unsupported source waveform: {kind}")


def _indices(request: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int], List[str]]:
    ground = _node(request.get("ground_node", "0"))
    nodes = sorted({node for element in request["elements"] for node in _element_nodes(element) if node != ground})
    node_indices = {node: index for index, node in enumerate(nodes)}
    branch_ids = [str(element["id"]) for element in request["elements"] if element["type"] in BRANCH_ELEMENTS]
    branch_indices = {identifier: len(nodes) + index for index, identifier in enumerate(branch_ids)}
    return node_indices, branch_indices, nodes


def _add(matrix: Any, row: int | None, column: int | None, value: complex) -> None:
    if row is not None and column is not None:
        matrix[row, column] += value


def _rhs_add(rhs: np.ndarray, row: int | None, value: complex) -> None:
    if row is not None:
        rhs[row] += value


def _node_index(node_indices: Dict[str, int], node: str) -> int | None:
    return node_indices.get(node)


def _stamp_pair(matrix: Any, p: int | None, n: int | None, admittance: complex) -> None:
    _add(matrix, p, p, admittance)
    _add(matrix, n, n, admittance)
    _add(matrix, p, n, -admittance)
    _add(matrix, n, p, -admittance)


def _assemble(
    request: Dict[str, Any],
    *,
    mode: str,
    frequency_hz: float = 0.0,
    time_s: float = 0.0,
    time_step_s: float = 0.0,
    previous: np.ndarray | None = None,
) -> Tuple[Any, np.ndarray, Dict[str, int], Dict[str, int], List[str]]:
    node_indices, branch_indices, nodes = _indices(request)
    size = len(node_indices) + len(branch_indices)
    dtype = complex if mode == "ac" else float
    backend = _linear_backend(request, size)
    matrix = (
        lil_matrix((size, size), dtype=dtype)
        if backend in {"scipy-superlu", "petsc-mumps"}
        else np.zeros((size, size), dtype=dtype)
    )
    rhs = np.zeros(size, dtype=dtype)
    omega = 2.0 * math.pi * frequency_hz
    for element in request["elements"]:
        kind = str(element["type"])
        p = _node_index(node_indices, _node(element["positive_node"]))
        n = _node_index(node_indices, _node(element["negative_node"]))
        if kind == "resistor":
            _stamp_pair(matrix, p, n, 1.0 / float(element["resistance_ohm"]))
        elif kind == "capacitor":
            capacitance = float(element["capacitance_f"])
            if mode == "ac":
                _stamp_pair(matrix, p, n, 1j * omega * capacitance)
            elif mode == "transient":
                conductance = capacitance / time_step_s
                _stamp_pair(matrix, p, n, conductance)
                previous_voltage = 0.0 if previous is None else (0.0 if p is None else previous[p]) - (0.0 if n is None else previous[n])
                _rhs_add(rhs, p, conductance * previous_voltage)
                _rhs_add(rhs, n, -conductance * previous_voltage)
        elif kind in {"voltage_source", "inductor", "vcvs", "ccvs"}:
            branch = branch_indices[str(element["id"])]
            _add(matrix, p, branch, 1.0)
            _add(matrix, n, branch, -1.0)
            _add(matrix, branch, p, 1.0)
            _add(matrix, branch, n, -1.0)
            if kind == "voltage_source":
                if mode == "ac":
                    magnitude = float(element.get("ac_magnitude", 0.0) or 0.0)
                    phase = math.radians(float(element.get("ac_phase_deg", 0.0) or 0.0))
                    rhs[branch] += cmath.rect(magnitude, phase)
                else:
                    rhs[branch] += _source_value(element, time_s)
            elif kind == "inductor":
                inductance = float(element["inductance_h"])
                if mode == "ac":
                    matrix[branch, branch] -= 1j * omega * inductance
                elif mode == "transient":
                    coefficient = inductance / time_step_s
                    matrix[branch, branch] -= coefficient
                    previous_current = 0.0 if previous is None else previous[branch]
                    rhs[branch] -= coefficient * previous_current
            elif kind == "vcvs":
                cp = _node_index(node_indices, _node(element["control_positive_node"]))
                cn = _node_index(node_indices, _node(element["control_negative_node"]))
                gain = float(element["gain"])
                _add(matrix, branch, cp, -gain)
                _add(matrix, branch, cn, gain)
            else:
                matrix[branch, branch_indices[str(element["control_source_id"])]] -= float(element["transresistance_ohm"])
        elif kind == "current_source":
            if mode == "ac":
                magnitude = float(element.get("ac_magnitude", 0.0) or 0.0)
                phase = math.radians(float(element.get("ac_phase_deg", 0.0) or 0.0))
                value: complex = cmath.rect(magnitude, phase)
            else:
                value = _source_value(element, time_s)
            _rhs_add(rhs, p, -value)
            _rhs_add(rhs, n, value)
        elif kind == "vccs":
            cp = _node_index(node_indices, _node(element["control_positive_node"]))
            cn = _node_index(node_indices, _node(element["control_negative_node"]))
            gain = float(element["transconductance_s"])
            _add(matrix, p, cp, gain)
            _add(matrix, p, cn, -gain)
            _add(matrix, n, cp, -gain)
            _add(matrix, n, cn, gain)
        elif kind == "cccs":
            control = branch_indices[str(element["control_source_id"])]
            gain = float(element["gain"])
            _add(matrix, p, control, gain)
            _add(matrix, n, control, -gain)
    return matrix, rhs, node_indices, branch_indices, nodes


def _solve(matrix: Any, rhs: np.ndarray, *, requested_backend: str) -> Tuple[np.ndarray, float | None, float, Dict[str, Any]]:
    if isinstance(matrix, spmatrix):
        try:
            solution, backend = solve_sparse_system(matrix.tocsr(), rhs, requested=requested_backend)
        except (AccelerationUnavailableError, RuntimeError, ValueError) as exc:
            raise ValueError(f"Sparse circuit solve failed: {exc}.") from exc
        condition: float | None = None
    else:
        try:
            solution = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as exc:
            raise ValueError(f"Circuit matrix is singular or ill-conditioned: {exc}.") from exc
        condition = float(np.linalg.cond(matrix))
        backend = {"requested": "dense", "selected": "numpy-dense", "fallback": "", "fallback_used": False}
    residual = float(np.linalg.norm(matrix @ solution - rhs) / max(np.linalg.norm(rhs), np.finfo(float).eps))
    if not np.all(np.isfinite(solution)) or not math.isfinite(residual) or residual > 1e-8:
        raise ValueError(f"Circuit matrix residual is not acceptable ({residual:.6g}).")
    if condition is not None and (not math.isfinite(condition) or condition > 1e16):
        raise ValueError(f"Circuit matrix condition number is not acceptable ({condition:.6g}).")
    return solution, condition, residual, backend


def _complex_series(values: List[complex]) -> Dict[str, List[float]]:
    return {
        "real": [float(value.real) for value in values],
        "imaginary": [float(value.imag) for value in values],
        "magnitude": [float(abs(value)) for value in values],
        "phase_deg": [float(math.degrees(cmath.phase(value))) for value in values],
    }


def _element_currents(
    request: Dict[str, Any],
    solution: np.ndarray,
    node_indices: Dict[str, int],
    branch_indices: Dict[str, int],
    *,
    mode: str,
    frequency_hz: float = 0.0,
    time_s: float = 0.0,
    time_step_s: float = 0.0,
    previous: np.ndarray | None = None,
) -> Dict[str, complex]:
    """Return positive-to-negative terminal current for every supported element."""

    def voltage(node: Any, vector: np.ndarray | None = solution) -> complex:
        index = _node_index(node_indices, _node(node))
        return 0.0 if index is None or vector is None else complex(vector[index])

    currents: Dict[str, complex] = {}
    omega = 2.0 * math.pi * frequency_hz
    for element in request["elements"]:
        identifier = str(element["id"])
        kind = str(element["type"])
        terminal_voltage = voltage(element["positive_node"]) - voltage(element["negative_node"])
        if kind == "resistor":
            current = terminal_voltage / float(element["resistance_ohm"])
        elif kind == "capacitor":
            capacitance = float(element["capacitance_f"])
            if mode == "ac":
                current = terminal_voltage * 1j * omega * capacitance
            elif mode == "transient":
                previous_voltage = voltage(element["positive_node"], previous) - voltage(element["negative_node"], previous)
                current = capacitance * (terminal_voltage - previous_voltage) / time_step_s
            else:
                current = 0.0
        elif kind in BRANCH_ELEMENTS:
            current = complex(solution[branch_indices[identifier]])
        elif kind == "current_source":
            if mode == "ac":
                magnitude = float(element.get("ac_magnitude", 0.0) or 0.0)
                phase = math.radians(float(element.get("ac_phase_deg", 0.0) or 0.0))
                current = cmath.rect(magnitude, phase)
            else:
                current = _source_value(element, time_s)
        elif kind == "vccs":
            control_voltage = voltage(element["control_positive_node"]) - voltage(element["control_negative_node"])
            current = float(element["transconductance_s"]) * control_voltage
        else:
            current = float(element["gain"]) * complex(solution[branch_indices[str(element["control_source_id"])]])
        currents[identifier] = complex(current)
    return currents


def _element_powers(
    request: Dict[str, Any],
    solution: np.ndarray,
    node_indices: Dict[str, int],
    currents: Dict[str, complex],
    *,
    ac: bool = False,
) -> Dict[str, complex]:
    def voltage(node: Any) -> complex:
        index = _node_index(node_indices, _node(node))
        return 0.0 if index is None else complex(solution[index])

    powers: Dict[str, complex] = {}
    for element in request["elements"]:
        voltage_drop = voltage(element["positive_node"]) - voltage(element["negative_node"])
        current = currents[str(element["id"])]
        powers[str(element["id"])] = voltage_drop * (current.conjugate() if ac else current)
    return powers


def run_native_mna(request: Dict[str, Any]) -> Dict[str, Any]:
    """Run a validated linear MNA request and return a JSON-compatible result."""

    validation = validate_native_mna_request(request)
    if not validation["valid"]:
        return {"contract": RESULT_CONTRACT, "status": "blocked", "model_status": "unsupported", "validation": validation}
    mode = str(request["analysis"]["mode"])
    selected_backend = str(validation["counts"]["selected_linear_backend"])
    backend_runs: List[Dict[str, Any]] = []

    def solve_system(matrix: Any, rhs: np.ndarray) -> Tuple[np.ndarray, float | None, float]:
        solution, condition, residual, backend = _solve(matrix, rhs, requested_backend=selected_backend)
        backend_runs.append(dict(backend))
        return solution, condition, residual

    try:
        if mode == "operating_point":
            matrix, rhs, node_indices, branch_indices, nodes = _assemble(request, mode=mode)
            solution, condition, residual = solve_system(matrix, rhs)
            element_currents = _element_currents(request, solution, node_indices, branch_indices, mode=mode)
            element_powers = _element_powers(request, solution, node_indices, element_currents)
            data: Dict[str, Any] = {
                "node_voltage_v": {node: float(solution[index]) for node, index in node_indices.items()},
                "branch_current_a": {identifier: float(solution[index]) for identifier, index in branch_indices.items()},
                "element_current_a": {identifier: float(value.real) for identifier, value in element_currents.items()},
                "element_power_w": {identifier: float(value.real) for identifier, value in element_powers.items()},
            }
            diagnostics = {"condition_number_max": condition, "relative_residual_max": residual, "points": 1}
        elif mode == "ac":
            analysis = request["analysis"]
            points = int(analysis["points"])
            scale = str(analysis.get("scale", "log")).lower()
            if scale == "linear" or float(analysis["start_hz"]) == float(analysis["stop_hz"]):
                frequencies = np.linspace(float(analysis["start_hz"]), float(analysis["stop_hz"]), points)
            else:
                frequencies = np.geomspace(float(analysis["start_hz"]), float(analysis["stop_hz"]), points)
            node_values: Dict[str, List[complex]] = {}
            branch_values: Dict[str, List[complex]] = {}
            element_current_values: Dict[str, List[complex]] = {}
            element_power_values: Dict[str, List[complex]] = {}
            conditions: List[float] = []
            residuals: List[float] = []
            for frequency in frequencies:
                matrix, rhs, node_indices, branch_indices, nodes = _assemble(request, mode=mode, frequency_hz=float(frequency))
                solution, condition, residual = solve_system(matrix, rhs)
                element_currents = _element_currents(
                    request, solution, node_indices, branch_indices, mode=mode, frequency_hz=float(frequency),
                )
                element_powers = _element_powers(request, solution, node_indices, element_currents, ac=True)
                if condition is not None:
                    conditions.append(condition)
                residuals.append(residual)
                for node, index in node_indices.items():
                    node_values.setdefault(node, []).append(complex(solution[index]))
                for identifier, index in branch_indices.items():
                    branch_values.setdefault(identifier, []).append(complex(solution[index]))
                for identifier, value in element_currents.items():
                    element_current_values.setdefault(identifier, []).append(value)
                for identifier, value in element_powers.items():
                    element_power_values.setdefault(identifier, []).append(value)
            data = {
                "frequency_hz": [float(value) for value in frequencies],
                "node_voltage_v": {node: _complex_series(values) for node, values in node_values.items()},
                "branch_current_a": {identifier: _complex_series(values) for identifier, values in branch_values.items()},
                "element_current_a": {identifier: _complex_series(values) for identifier, values in element_current_values.items()},
                "element_complex_power_va": {identifier: _complex_series(values) for identifier, values in element_power_values.items()},
            }
            diagnostics = {
                "condition_number_max": max(conditions) if conditions else None,
                "relative_residual_max": max(residuals),
                "points": points,
            }
        else:
            analysis = request["analysis"]
            step = float(analysis["time_step_s"])
            stop = float(analysis["stop_time_s"])
            times = np.arange(0.0, stop + step * 0.5, step)
            node_values: Dict[str, List[float]] = {}
            branch_values: Dict[str, List[float]] = {}
            element_current_values: Dict[str, List[float]] = {}
            element_power_values: Dict[str, List[float]] = {}
            previous: np.ndarray | None = None
            conditions = []
            residuals = []
            for time_s in times:
                matrix, rhs, node_indices, branch_indices, nodes = _assemble(
                    request, mode=mode, time_s=float(time_s), time_step_s=step, previous=previous,
                )
                solution, condition, residual = solve_system(matrix, rhs)
                element_currents = _element_currents(
                    request,
                    solution,
                    node_indices,
                    branch_indices,
                    mode=mode,
                    time_s=float(time_s),
                    time_step_s=step,
                    previous=previous,
                )
                element_powers = _element_powers(request, solution, node_indices, element_currents)
                if condition is not None:
                    conditions.append(condition)
                residuals.append(residual)
                for node, index in node_indices.items():
                    node_values.setdefault(node, []).append(float(solution[index]))
                for identifier, index in branch_indices.items():
                    branch_values.setdefault(identifier, []).append(float(solution[index]))
                for identifier, value in element_currents.items():
                    element_current_values.setdefault(identifier, []).append(float(value.real))
                for identifier, value in element_powers.items():
                    element_power_values.setdefault(identifier, []).append(float(value.real))
                previous = solution
            data = {
                "time_s": [float(value) for value in times],
                "node_voltage_v": node_values,
                "branch_current_a": branch_values,
                "element_current_a": element_current_values,
                "element_power_w": element_power_values,
                "integration": "backward_euler",
            }
            diagnostics = {
                "condition_number_max": max(conditions) if conditions else None,
                "relative_residual_max": max(residuals),
                "points": len(times),
            }
    except (ValueError, OverflowError, ZeroDivisionError) as exc:
        return {
            "contract": RESULT_CONTRACT,
            "status": "failed",
            "model_status": "experimental",
            "validation": validation,
            "issues": [_issue("MNA_NUMERICAL_FAILURE", str(exc))],
        }
    backend_summary = backend_runs[-1] if backend_runs else {
        "requested": selected_backend,
        "selected": "not-run",
        "fallback": "",
        "fallback_used": False,
    }
    diagnostics["linear_backend"] = backend_summary
    diagnostics["linear_backend_runs"] = len(backend_runs)
    return {
        "contract": RESULT_CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "mode": mode,
        "data": data,
        "diagnostics": diagnostics,
        "validation": validation,
        "issues": [],
        "provenance": {
            "solver": "spike.native.linear_mna",
            "solver_version": "0.2.0",
            "formulation": "modified_nodal_analysis",
            "acceleration": backend_summary,
            "limitations": [
                "Only linear R, L, C and explicit independent/dependent sources are supported.",
                "Transient integration uses fixed-step backward Euler; nonlinear semiconductor and behavioral models are unsupported.",
                "This experimental engine is not yet release-validated for closed-loop PCB field/circuit co-simulation.",
            ],
        },
    }


__all__ = [
    "REQUEST_CONTRACT",
    "RESULT_CONTRACT",
    "VALIDATION_CONTRACT",
    "run_native_mna",
    "validate_native_mna_request",
]
