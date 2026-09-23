"""Deterministic fixed-point orchestration for field/circuit co-simulation.

The coupler owns iteration, relaxation, convergence, cancellation, and result
provenance.  It does not pretend that a field solver exists: callers must pass
an explicit process-isolated or native field-reduction provider.  Provider
responses may update R/L/C/G values, but may not change reviewed circuit
topology or endpoint mappings during an iteration.
"""

from __future__ import annotations

from copy import deepcopy
import math
import time
from typing import Any, Callable, Dict, Iterable, List

from .contracts import DesignIR
from .native_circuit_compiler import run_spice_workspace_native_mna
from .owned_spice_workspace import (
    REQUEST_CONTRACT as OWNED_SPICE_REQUEST_CONTRACT,
    run_owned_spice_workspace,
)


REQUEST_CONTRACT = "spike/field-circuit-cosimulation-request/v1"
RESULT_CONTRACT = "spike/field-circuit-cosimulation-result/v1"
FIELD_REQUEST_CONTRACT = "spike/field-reduction-request/v1"
FIELD_RESULT_CONTRACT = "spike/field-reduction-result/v1"
VALIDATION_CONTRACT = "spike/field-circuit-cosimulation-validation/v1"

FieldReductionProvider = Callable[[Dict[str, Any]], Dict[str, Any]]

_PARAMETERS = (
    "resistance_ohm",
    "inductance_h",
    "capacitance_f",
    "conductance_s",
)
_MAX_ITERATIONS = 100
_CIRCUIT_ENGINES = {"linear_native_mna", "owned_spice"}


def _issue(code: str, message: str, path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": "error", "message": message, "path": path}


def _finite(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if positive and number <= 0.0:
        return None
    if nonnegative and number < 0.0:
        return None
    return number


def validate_field_circuit_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Validate only the bounded coupling controls, without running a solver."""

    issues: List[Dict[str, str]] = []
    if not isinstance(request, dict) or request.get("contract") != REQUEST_CONTRACT:
        return {
            "contract": VALIDATION_CONTRACT,
            "valid": False,
            "issues": [_issue(
                "SPIKE-BE-SPICE-E-0041",
                f"Expected coupling contract {REQUEST_CONTRACT}.",
                "contract",
            )],
        }

    circuit_engine = str(request.get("circuit_engine", "linear_native_mna"))
    if circuit_engine not in _CIRCUIT_ENGINES:
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0041",
            "circuit_engine must be linear_native_mna or owned_spice.",
            "circuit_engine",
        ))
    if circuit_engine == "owned_spice" and not isinstance(
        request.get("owned_spice_limits", {}), dict
    ):
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0041",
            "owned_spice_limits must be an object when the owned SPICE engine is selected.",
            "owned_spice_limits",
        ))
    circuit_probes = request.get("circuit_probes", [])
    if (
        not isinstance(circuit_probes, list)
        or len(circuit_probes) > 256
        or any(not isinstance(item, str) or not item for item in circuit_probes)
    ):
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0041",
            "circuit_probes must contain at most 256 non-empty descriptors.",
            "circuit_probes",
        ))

    integers = {
        "maximum_iterations": (2, _MAX_ITERATIONS),
        "minimum_iterations": (2, _MAX_ITERATIONS),
    }
    parsed_integers: Dict[str, int] = {}
    for key, (minimum, maximum) in integers.items():
        raw_value = request.get(key, minimum)
        value = raw_value if isinstance(raw_value, int) and not isinstance(raw_value, bool) else -1
        parsed_integers[key] = value
        if value < minimum or value > maximum:
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0041",
                f"{key} must be between {minimum} and {maximum}.",
                key,
            ))
    if parsed_integers.get("minimum_iterations", 0) > parsed_integers.get("maximum_iterations", 0):
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0041",
            "minimum_iterations cannot exceed maximum_iterations.",
            "minimum_iterations",
        ))

    numeric_fields = {
        "relaxation": (True, False),
        "parameter_relative_tolerance": (True, False),
        "circuit_relative_tolerance": (True, False),
        "absolute_floor": (True, False),
        "time_limit_s": (True, False),
    }
    for key, (positive, nonnegative) in numeric_fields.items():
        value = _finite(request.get(key), positive=positive, nonnegative=nonnegative)
        if value is None:
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0041",
                f"{key} must be finite and positive.",
                key,
            ))
        elif key == "relaxation" and value > 1.0:
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0041",
                "relaxation must be greater than zero and no greater than one.",
                key,
            ))
    return {"contract": VALIDATION_CONTRACT, "valid": not issues, "issues": issues}


def _run_circuit_stage(
    workspace: Dict[str, Any], design: DesignIR, request: Dict[str, Any],
) -> Dict[str, Any]:
    circuit_engine = str(request.get("circuit_engine", "linear_native_mna"))
    if circuit_engine == "linear_native_mna":
        return run_spice_workspace_native_mna(
            workspace, design, resource_limits=request.get("resource_limits"),
        )
    owned_request = {
        "contract": OWNED_SPICE_REQUEST_CONTRACT,
        "request_id": f"{str(request.get('request_id', 'field-circuit'))[:96]}-circuit",
        "workspace": workspace,
        "probes": list(request.get("circuit_probes", [])),
        "resource_limits": dict(request.get("owned_spice_limits", {})),
    }
    owned = run_owned_spice_workspace(owned_request, design)
    return {
        "contract": "spike/field-circuit-owned-spice-stage/v1",
        "status": owned.get("status", "failed"),
        "result": owned.get("circuit_result"),
        "owned_bridge": owned,
    }


def _enabled_parasitics(workspace: Dict[str, Any]) -> List[Dict[str, Any]]:
    values = workspace.get("parasitics", [])
    if not isinstance(values, list) or not values:
        raise ValueError("A field/circuit iteration requires reviewed workspace parasitics.")
    enabled = [item for item in values if isinstance(item, dict) and item.get("enabled", True)]
    if not enabled:
        raise ValueError("A field/circuit iteration requires at least one enabled parasitic section.")
    identifiers: set[str] = set()
    for index, item in enumerate(enabled):
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in identifiers:
            raise ValueError(f"workspace.parasitics[{index}] requires a unique ID.")
        identifiers.add(identifier)
        if item.get("endpoint_reviewed") is not True:
            raise ValueError(f"Parasitic {identifier} must have reviewed endpoints before coupling.")
        if not str(item.get("from_node", "")).strip() or not str(item.get("to_node", "")).strip():
            raise ValueError(f"Parasitic {identifier} requires explicit circuit endpoints.")
        for parameter in _PARAMETERS:
            if _finite(item.get(parameter, 0.0), nonnegative=True) is None:
                raise ValueError(f"Parasitic {identifier} has an invalid {parameter} value.")
    return enabled


def _field_updates(response: Dict[str, Any], expected: Iterable[str]) -> Dict[str, Dict[str, float]]:
    if not isinstance(response, dict) or response.get("contract") != FIELD_RESULT_CONTRACT:
        raise ValueError(f"The field provider must return {FIELD_RESULT_CONTRACT}.")
    if response.get("status") != "completed":
        raise ValueError(f"The field provider returned status {response.get('status', 'missing')}.")
    values = response.get("parasitics")
    if not isinstance(values, list):
        raise ValueError("The field provider response requires a parasitics array.")
    updates: Dict[str, Dict[str, float]] = {}
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"Field parasitics[{index}] must be an object.")
        identifier = str(item.get("id", "")).strip()
        if not identifier or identifier in updates:
            raise ValueError("Field parasitic IDs must be non-empty and unique.")
        updates[identifier] = {}
        for parameter in _PARAMETERS:
            value = _finite(item.get(parameter, 0.0), nonnegative=True)
            if value is None:
                raise ValueError(f"Field parasitic {identifier} has invalid {parameter}.")
            updates[identifier][parameter] = value
    expected_ids = set(expected)
    if set(updates) != expected_ids:
        missing = sorted(expected_ids - set(updates))
        unexpected = sorted(set(updates) - expected_ids)
        raise ValueError(f"Field provider changed coupling topology (missing={missing}, unexpected={unexpected}).")
    return updates


def _relative_delta(left: float, right: float, floor: float) -> float:
    return abs(right - left) / max(abs(left), abs(right), floor)


def _apply_updates(
    workspace: Dict[str, Any],
    updates: Dict[str, Dict[str, float]],
    relaxation: float,
    floor: float,
) -> tuple[Dict[str, Any], float]:
    updated = deepcopy(workspace)
    maximum_delta = 0.0
    for item in updated.get("parasitics", []):
        identifier = str(item.get("id", ""))
        if identifier not in updates or not item.get("enabled", True):
            continue
        for parameter in _PARAMETERS:
            previous = float(item.get(parameter, 0.0) or 0.0)
            candidate = updates[identifier][parameter]
            relaxed = previous + relaxation * (candidate - previous)
            item[parameter] = relaxed
            maximum_delta = max(maximum_delta, _relative_delta(previous, relaxed, floor))
    return updated, maximum_delta


def _series_values(value: Any) -> List[float]:
    if isinstance(value, dict):
        value = value.get("magnitude", [])
    if isinstance(value, list):
        return [float(item) for item in value if _finite(item) is not None]
    if _finite(value) is not None:
        return [float(value)]
    return []


def _circuit_signature(result: Dict[str, Any]) -> Dict[str, List[float]]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    signature: Dict[str, List[float]] = {}
    for group in ("node_voltage_v", "element_current_a"):
        for identifier, value in sorted((data.get(group) or {}).items()):
            signature[f"{group}:{identifier}"] = _series_values(value)
    return signature


def _signature_delta(
    previous: Dict[str, List[float]] | None,
    current: Dict[str, List[float]],
    floor: float,
) -> float:
    if previous is None:
        return math.inf
    if set(previous) != set(current):
        return math.inf
    maximum = 0.0
    for key in current:
        if len(previous[key]) != len(current[key]):
            return math.inf
        for left, right in zip(previous[key], current[key]):
            maximum = max(maximum, _relative_delta(left, right, floor))
    return maximum


def _blocked(request: Dict[str, Any], issues: List[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "contract": RESULT_CONTRACT,
        "request_id": str(request.get("request_id", "field-circuit")),
        "status": "blocked",
        "model_status": "unsupported",
        "converged": False,
        "iterations": [],
        "issues": issues,
    }


def run_iterative_field_circuit_cosimulation(
    design: DesignIR,
    workspace: Dict[str, Any],
    request: Dict[str, Any],
    field_provider: FieldReductionProvider | None,
    *,
    cancellation_event: Any = None,
) -> Dict[str, Any]:
    """Iterate a reviewed circuit workspace against an explicit field provider."""

    validation = validate_field_circuit_request(request)
    if not validation["valid"]:
        return _blocked(request, validation["issues"])
    if field_provider is None or not callable(field_provider):
        return _blocked(request, [_issue(
            "SPIKE-BE-SOLVER-E-0001",
            "No native or process-isolated field-reduction provider was supplied.",
            "field_provider",
        )])
    try:
        initial = _enabled_parasitics(workspace)
    except ValueError as exc:
        return _blocked(request, [_issue("SPIKE-BE-SPICE-E-0030", str(exc), "workspace.parasitics")])

    maximum_iterations = int(request["maximum_iterations"])
    minimum_iterations = int(request["minimum_iterations"])
    relaxation = float(request["relaxation"])
    parameter_tolerance = float(request["parameter_relative_tolerance"])
    circuit_tolerance = float(request["circuit_relative_tolerance"])
    floor = float(request["absolute_floor"])
    deadline = time.monotonic() + float(request["time_limit_s"])
    current_workspace = deepcopy(workspace)
    expected_ids = [str(item["id"]) for item in initial]
    previous_signature: Dict[str, List[float]] | None = None
    iteration_history: List[Dict[str, Any]] = []
    final_circuit: Dict[str, Any] | None = None
    final_field: Dict[str, Any] | None = None

    for iteration in range(1, maximum_iterations + 1):
        if cancellation_event is not None and cancellation_event.is_set():
            return {
                **_blocked(request, [_issue("SPIKE-BE-SOLVER-E-0003", "Field/circuit execution was cancelled.")]),
                "status": "cancelled",
                "model_status": "experimental",
                "iterations": iteration_history,
            }
        if time.monotonic() >= deadline:
            return {
                **_blocked(request, [_issue("SPIKE-BE-SOLVER-P-0004", "Field/circuit execution exceeded its time budget.")]),
                "status": "failed",
                "model_status": "experimental",
                "iterations": iteration_history,
            }

        try:
            circuit = _run_circuit_stage(current_workspace, design, request)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return {
                **_blocked(request, [_issue("SPIKE-BE-SPICE-E-0041", str(exc), "circuit")]),
                "status": "failed",
                "model_status": "experimental",
                "iterations": iteration_history,
            }
        native_result = circuit.get("result") or {}
        if native_result.get("status") != "completed":
            stage_status = circuit.get("status", native_result.get("status", "failed"))
            if stage_status not in {"blocked", "cancelled", "failed"}:
                stage_status = "failed"
            owned_bridge = circuit.get("owned_bridge")
            stage_model_status = (
                owned_bridge.get("model_status", "experimental")
                if isinstance(owned_bridge, dict)
                else native_result.get("model_status", "experimental")
            )
            return {
                **_blocked(request, [_issue(
                    "SPIKE-BE-SPICE-E-0041",
                    "The configured circuit stage did not complete; field iteration was not started.",
                    "circuit",
                )]),
                "status": stage_status,
                "model_status": stage_model_status,
                "iterations": iteration_history,
                "circuit": circuit,
            }
        signature = _circuit_signature(native_result)
        circuit_delta = _signature_delta(previous_signature, signature, floor)
        field_request = {
            "contract": FIELD_REQUEST_CONTRACT,
            "request_id": str(request.get("request_id", "field-circuit")),
            "iteration": iteration,
            "analysis": deepcopy(current_workspace.get("analysis", {})),
            "parasitics": deepcopy(_enabled_parasitics(current_workspace)),
            "circuit_result": deepcopy(native_result),
            "remaining_time_s": max(0.0, deadline - time.monotonic()),
        }
        try:
            field = field_provider(field_request)
            updates = _field_updates(field, expected_ids)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return {
                **_blocked(request, [_issue("SPIKE-BE-SPICE-E-0042", str(exc), "field_provider")]),
                "status": "failed",
                "model_status": "experimental",
                "iterations": iteration_history,
                "circuit": circuit,
            }
        next_workspace, parameter_delta = _apply_updates(current_workspace, updates, relaxation, floor)
        converged = (
            iteration >= minimum_iterations
            and parameter_delta <= parameter_tolerance
            and circuit_delta <= circuit_tolerance
        )
        iteration_history.append({
            "iteration": iteration,
            "parameter_relative_delta_max": parameter_delta,
            "circuit_relative_delta_max": circuit_delta if math.isfinite(circuit_delta) else None,
            "converged": converged,
            "circuit_diagnostics": deepcopy(native_result.get("diagnostics", {})),
            "field_diagnostics": deepcopy(field.get("diagnostics", {})),
            "elapsed_s": float(request["time_limit_s"]) - max(0.0, deadline - time.monotonic()),
        })
        final_circuit = circuit
        final_field = field
        current_workspace = next_workspace
        previous_signature = signature
        if converged:
            return {
                "contract": RESULT_CONTRACT,
                "request_id": str(request.get("request_id", "field-circuit")),
                "status": "completed",
                "model_status": "experimental",
                "converged": True,
                "iteration_count": iteration,
                "iterations": iteration_history,
                "workspace": current_workspace,
                "circuit": final_circuit,
                "field": final_field,
                "issues": [],
                "provenance": {
                    "coupler": "spike.native.fixed_point_field_circuit",
                    "coupler_version": "0.1.0",
                    "field_provider": str(field.get("provider", "explicit_provider")),
                    "circuit_engine": str(request.get("circuit_engine", "linear_native_mna")),
                    "topology_changes_allowed": False,
                    "relaxation": relaxation,
                },
            }

    return {
        "contract": RESULT_CONTRACT,
        "request_id": str(request.get("request_id", "field-circuit")),
        "status": "failed",
        "model_status": "experimental",
        "converged": False,
        "iteration_count": maximum_iterations,
        "iterations": iteration_history,
        "workspace": current_workspace,
        "circuit": final_circuit,
        "field": final_field,
        "issues": [_issue(
            "SPIKE-BE-SOLVER-E-0002",
            "Field/circuit fixed-point iteration did not converge within the configured iteration limit.",
        )],
    }


__all__ = [
    "FIELD_REQUEST_CONTRACT",
    "FIELD_RESULT_CONTRACT",
    "REQUEST_CONTRACT",
    "RESULT_CONTRACT",
    "VALIDATION_CONTRACT",
    "run_iterative_field_circuit_cosimulation",
    "validate_field_circuit_request",
]
