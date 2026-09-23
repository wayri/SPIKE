"""Bounded multi-board execution adapters.

The multi-board planner owns retained assembly identity.  This module is the
next boundary: it can execute *independent* SI jobs sequentially, and it can
compile an explicitly parameterised harness into a circuit fragment.  It does
not guess a harness impedance from a material name or wire gauge, and it does
not represent that a field-coupled PI/SI solve has happened.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Dict, Mapping

from .design_ir_v2 import DesignIRV2
from .assembly_scale import MAX_BOARDS
from .multiboard_analysis import PLAN_CONTRACT, REQUEST_CONTRACT, plan_multiboard_analysis
from .si_protocol_test_runner import SiProtocolTestRunnerError, run_si_protocol_test_suite, preflight_si_suite_resources


SI_BATCH_REQUEST_CONTRACT = "spike/multiboard-si-independent-batch-request/v1"
SI_BATCH_RESULT_CONTRACT = "spike/multiboard-si-independent-batch-result/v1"
HARNESS_COMPILE_REQUEST_CONTRACT = "spike/multiboard-harness-compile-request/v1"
HARNESS_COMPILE_RESULT_CONTRACT = "spike/multiboard-harness-compile-result/v1"
COUPLED_BIND_REQUEST_CONTRACT = "spike/multiboard-coupled-reduced-network-bind-request/v1"
COUPLED_BIND_RESULT_CONTRACT = "spike/multiboard-coupled-reduced-network-bind-result/v1"

MAX_BATCH_BOARD_JOBS = MAX_BOARDS
MAX_BATCH_LANES = 256
MAX_BATCH_FREQUENCY_POINTS = 1_000_000
MAX_BATCH_NUMERIC_BYTES = 1_073_741_824


class MultiboardExecutionError(ValueError):
    """Raised when a bounded multi-board execution request is incomplete."""


def _digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _finite(value: Any, name: str, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool):
        raise MultiboardExecutionError(f"{name} must be a finite numeric value.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise MultiboardExecutionError(f"{name} must be a finite numeric value.") from exc
    if not math.isfinite(result) or (positive and result <= 0.0) or (nonnegative and result < 0.0):
        qualifier = "positive" if positive else "non-negative" if nonnegative else "finite"
        raise MultiboardExecutionError(f"{name} must be {qualifier}.")
    return result


def _plan_from_request(raw: Any, *, domain: str, mode: str) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise MultiboardExecutionError("multiboard_request must be an object.")
    plan = plan_multiboard_analysis(raw)
    if plan["domain"] != domain or plan["mode"] != mode:
        raise MultiboardExecutionError(f"multiboard_request must plan {domain} {mode}.")
    return plan


def _limit(value: Any, name: str, maximum: int) -> int:
    if value is None:
        return maximum
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise MultiboardExecutionError(f"{name} must be an integer from 1 through {maximum}.")
    return value


def run_independent_si_batch(
    raw: Mapping[str, Any],
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
    """Run independently-scoped SI suites without cross-board coupling.

    Jobs are intentionally sequential.  Parallelising up to 30 large board jobs in
    the worker would over-admit CPU/RAM and recreates the UI starvation issue
    this boundary is meant to avoid.  Each child runner still enforces its own
    hard numeric limits; this adapter additionally enforces aggregate limits.
    """

    if not isinstance(raw, Mapping) or raw.get("contract") != SI_BATCH_REQUEST_CONTRACT:
        raise MultiboardExecutionError(f"Batch contract must be {SI_BATCH_REQUEST_CONTRACT}.")
    expected = {"contract", "multiboard_request", "jobs", "resource_limits"}
    unknown = set(raw) - expected
    if unknown:
        raise MultiboardExecutionError(f"Batch request has unknown fields: {sorted(unknown)}.")
    plan = _plan_from_request(raw.get("multiboard_request"), domain="si", mode="independent_board_batch")
    if not plan["independent_jobs_admissible"]:
        raise MultiboardExecutionError("The independent multi-board SI plan is not admitted.")
    jobs = raw.get("jobs")
    if not isinstance(jobs, list) or not jobs or len(jobs) > MAX_BATCH_BOARD_JOBS:
        raise MultiboardExecutionError(f"jobs must contain 1 through {MAX_BATCH_BOARD_JOBS} entries.")
    limits_raw = raw.get("resource_limits") or {}
    if not isinstance(limits_raw, Mapping) or set(limits_raw) - {
        "maximum_board_jobs", "maximum_total_lanes", "maximum_total_frequency_points", "maximum_total_estimated_numeric_bytes",
    }:
        raise MultiboardExecutionError("resource_limits is not an object or contains unknown fields.")
    limits = {
        "maximum_board_jobs": _limit(limits_raw.get("maximum_board_jobs"), "maximum_board_jobs", MAX_BATCH_BOARD_JOBS),
        "maximum_total_lanes": _limit(limits_raw.get("maximum_total_lanes"), "maximum_total_lanes", MAX_BATCH_LANES),
        "maximum_total_frequency_points": _limit(limits_raw.get("maximum_total_frequency_points"), "maximum_total_frequency_points", MAX_BATCH_FREQUENCY_POINTS),
        "maximum_total_estimated_numeric_bytes": _limit(limits_raw.get("maximum_total_estimated_numeric_bytes"), "maximum_total_estimated_numeric_bytes", MAX_BATCH_NUMERIC_BYTES),
    }
    if len(jobs) > limits["maximum_board_jobs"]:
        raise MultiboardExecutionError("Job count exceeds maximum_board_jobs.")

    board_by_id = {item["board_id"]: item for item in plan["graph"]["boards"]}
    designs = raw["multiboard_request"]["designs"]
    # Admit the entire batch before the first solve: a malformed fourth board
    # must not consume three expensive solves before reporting its error.
    preflight_ids: set[str] = set()
    planned_lanes = planned_points = 0
    for index, job in enumerate(jobs):
        if cancel_check is not None and cancel_check():
            raise MultiboardExecutionError("Multi-board independent SI execution was cancelled.")
        if not isinstance(job, Mapping) or set(job) != {"board_id", "suite_request"}:
            raise MultiboardExecutionError(f"jobs[{index}] must contain only board_id and suite_request.")
        board_id = job["board_id"]
        if not isinstance(board_id, str) or board_id not in board_by_id or board_id in preflight_ids:
            raise MultiboardExecutionError(f"jobs[{index}].board_id is unknown or duplicated.")
        try:
            admission = preflight_si_suite_resources(job["suite_request"])
        except (SiProtocolTestRunnerError, ValueError, TypeError) as exc:
            raise MultiboardExecutionError(f"SI job for board {board_id} failed preflight: {exc}") from exc
        planned_lanes += admission["lanes"]
        planned_points += admission["frequency_points"]
        preflight_ids.add(board_id)
    if planned_lanes > limits["maximum_total_lanes"] or planned_points > limits["maximum_total_frequency_points"]:
        raise MultiboardExecutionError("Planned SI jobs exceed aggregate multi-board resource limits before execution.")
    seen: set[str] = set()
    completed: list[Dict[str, Any]] = []
    totals = {"board_jobs": 0, "lanes": 0, "frequency_points": 0, "estimated_numeric_bytes": 0}
    for index, job in enumerate(jobs):
        if cancel_check is not None and cancel_check():
            raise MultiboardExecutionError("Multi-board independent SI execution was cancelled.")
        if not isinstance(job, Mapping) or set(job) != {"board_id", "suite_request"}:
            raise MultiboardExecutionError(f"jobs[{index}] must contain only board_id and suite_request.")
        board_id = job.get("board_id")
        suite_request = job.get("suite_request")
        if not isinstance(board_id, str) or board_id not in board_by_id or board_id in seen:
            raise MultiboardExecutionError(f"jobs[{index}].board_id is unknown or duplicated.")
        if not isinstance(suite_request, Mapping):
            raise MultiboardExecutionError(f"jobs[{index}].suite_request must be an object.")
        board = board_by_id[board_id]
        design = designs.get(board["design_id"])
        if not isinstance(design, Mapping):
            raise MultiboardExecutionError(f"Board {board_id} has no retained DesignIR v2 payload.")
        try:
            result = run_si_protocol_test_suite(DesignIRV2.from_dict(design), suite_request, cancel_check=cancel_check)
        except (SiProtocolTestRunnerError, ValueError, TypeError) as exc:
            raise MultiboardExecutionError(f"SI job for board {board_id} could not run: {exc}") from exc
        admission = result["resource_admission"]
        totals["board_jobs"] += 1
        totals["lanes"] += int(admission["actual_lanes"])
        totals["frequency_points"] += int(admission["actual_frequency_points"])
        totals["estimated_numeric_bytes"] += int(admission["estimated_numeric_bytes"])
        if (
            totals["lanes"] > limits["maximum_total_lanes"]
            or totals["frequency_points"] > limits["maximum_total_frequency_points"]
            or totals["estimated_numeric_bytes"] > limits["maximum_total_estimated_numeric_bytes"]
        ):
            raise MultiboardExecutionError("A completed SI job exceeded aggregate multi-board resource limits.")
        completed.append({
            "board_id": board_id,
            "namespace": board["namespace"],
            "design_id": board["design_id"],
            "result": result,
        })
        seen.add(board_id)
    result = {
        "contract": SI_BATCH_RESULT_CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "plan_contract": PLAN_CONTRACT,
        "plan_digest": plan["plan_digest"],
        "execution_strategy": "sequential_independent_board_jobs",
        "coupling": {"included": False, "reason": "Harnesses, connector mappings, and cross-board field coupling are excluded from independent board jobs."},
        "jobs": completed,
        "resource_admission": {"actual": totals, "hard_limits": limits, "cooperative_cancellation_supported": True},
        "release_gate": {
            "state": "experimental_screening_only",
            "required_before_promotion": [
                "cross-board connector, harness, and return-path models",
                "field/circuit coupling validation against independent and measured evidence",
                "protocol-specific compliance fixtures and uncertainty treatment",
            ],
        },
    }
    result["result_digest"] = _digest(result)
    return result


def _terminal(endpoint: Mapping[str, Any], pin: str) -> str:
    return f"{endpoint['board_id']}:{endpoint['connector_id']}:{pin}"


def compile_harness_electrical_network(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Compile explicitly supplied harness conductor values into R/L/C/G fragments.

    Values must be provided per conductor.  ``conductor_material_id`` and AWG
    are provenance only: neither is sufficient to infer resistance, inductance,
    capacitance, a return path, shielding, or mutual coupling.
    """

    if not isinstance(raw, Mapping) or raw.get("contract") != HARNESS_COMPILE_REQUEST_CONTRACT:
        raise MultiboardExecutionError(f"Harness compile contract must be {HARNESS_COMPILE_REQUEST_CONTRACT}.")
    if set(raw) != {"contract", "multiboard_request", "conductor_models"}:
        raise MultiboardExecutionError("Harness compile request must contain only contract, multiboard_request, and conductor_models.")
    source = raw.get("multiboard_request")
    if not isinstance(source, Mapping):
        raise MultiboardExecutionError("multiboard_request must be an object.")
    domain = str(source.get("domain") or "").strip().lower()
    if domain not in {"pi", "si"}:
        raise MultiboardExecutionError("Harness compilation only supports PI or SI requests.")
    plan = _plan_from_request(source, domain=domain, mode="coupled_harness_network")
    models = raw.get("conductor_models")
    if not isinstance(models, list):
        raise MultiboardExecutionError("conductor_models must be an array.")
    graph_harnesses = {item["harness_id"]: item for item in plan["graph"]["harnesses"]}
    models_by_harness: Dict[str, Mapping[str, Any]] = {}
    for index, model in enumerate(models):
        if not isinstance(model, Mapping) or set(model) != {"harness_id", "conductors"}:
            raise MultiboardExecutionError(f"conductor_models[{index}] must contain only harness_id and conductors.")
        identifier = model.get("harness_id")
        if not isinstance(identifier, str) or identifier not in graph_harnesses or identifier in models_by_harness:
            raise MultiboardExecutionError(f"conductor_models[{index}].harness_id is unknown or duplicated.")
        models_by_harness[identifier] = model
    if set(models_by_harness) != set(graph_harnesses):
        missing = sorted(set(graph_harnesses) - set(models_by_harness))
        extra = sorted(set(models_by_harness) - set(graph_harnesses))
        raise MultiboardExecutionError(f"Conductor models must cover every selected harness; missing={missing}, extra={extra}.")

    elements: list[Dict[str, Any]] = []
    conductors: list[Dict[str, Any]] = []
    for harness_id in sorted(graph_harnesses):
        harness = graph_harnesses[harness_id]
        expected = {str(key): str(value) for key, value in harness["pin_map"].items()}
        raw_conductors = models_by_harness[harness_id].get("conductors")
        if not isinstance(raw_conductors, list) or len(raw_conductors) != len(expected):
            raise MultiboardExecutionError(f"Harness {harness_id} needs exactly one explicit conductor model per pin mapping.")
        seen_pins: set[str] = set()
        for index, conductor in enumerate(raw_conductors):
            allowed = {"source_pin", "target_pin", "resistance_ohm", "inductance_h", "capacitance_to_reference_f", "conductance_to_reference_s", "reference_node"}
            if not isinstance(conductor, Mapping) or set(conductor) - allowed or not {"source_pin", "target_pin", "resistance_ohm", "inductance_h"}.issubset(conductor):
                raise MultiboardExecutionError(f"Harness {harness_id} conductor {index} has incomplete or unknown fields.")
            source_pin, target_pin = str(conductor["source_pin"]), str(conductor["target_pin"])
            if expected.get(source_pin) != target_pin or source_pin in seen_pins:
                raise MultiboardExecutionError(f"Harness {harness_id} conductor {index} does not match a unique retained pin mapping.")
            seen_pins.add(source_pin)
            resistance = _finite(conductor["resistance_ohm"], "resistance_ohm", positive=True)
            inductance = _finite(conductor["inductance_h"], "inductance_h", positive=True)
            source_node = _terminal(harness["endpoint_a"], source_pin)
            target_node = _terminal(harness["endpoint_b"], target_pin)
            series_node = f"harness:{harness_id}:{source_pin}:series"
            provenance = {"harness_id": harness_id, "source_pin": source_pin, "target_pin": target_pin, "length_mm": harness["length_mm"]}
            elements.extend([
                {"id": f"harness:{harness_id}:{source_pin}:R", "type": "resistor", "positive_node": source_node, "negative_node": series_node, "resistance_ohm": resistance, **provenance},
                {"id": f"harness:{harness_id}:{source_pin}:L", "type": "inductor", "positive_node": series_node, "negative_node": target_node, "inductance_h": inductance, **provenance},
            ])
            capacitance = conductor.get("capacitance_to_reference_f")
            conductance = conductor.get("conductance_to_reference_s")
            reference = conductor.get("reference_node")
            if capacitance is not None or conductance is not None:
                if not isinstance(reference, str) or not reference.strip():
                    raise MultiboardExecutionError(f"Harness {harness_id} conductor {index} shunt values require an explicit reference_node.")
                reference = reference.strip()
                if capacitance is not None:
                    elements.append({"id": f"harness:{harness_id}:{source_pin}:C", "type": "capacitor", "positive_node": series_node, "negative_node": reference, "capacitance_f": _finite(capacitance, "capacitance_to_reference_f", positive=True), **provenance})
                if conductance is not None:
                    conductance_value = _finite(conductance, "conductance_to_reference_s", positive=True)
                    elements.append({"id": f"harness:{harness_id}:{source_pin}:G", "type": "resistor", "positive_node": series_node, "negative_node": reference, "resistance_ohm": 1.0 / conductance_value, **provenance})
            conductors.append({"harness_id": harness_id, "source_node": source_node, "target_node": target_node, "source_pin": source_pin, "target_pin": target_pin})
        if seen_pins != set(expected):
            raise MultiboardExecutionError(f"Harness {harness_id} conductor models do not cover every retained pin mapping.")
    result = {
        "contract": HARNESS_COMPILE_RESULT_CONTRACT,
        "status": "compiled",
        "domain": domain,
        "plan_contract": PLAN_CONTRACT,
        "plan_digest": plan["plan_digest"],
        "model_status": "explicit_circuit_fragment_only",
        "production_qualified": False,
        "circuit_fragment": {"ground_node": "not_bound", "elements": elements, "conductors": conductors},
        "coupling": {
            "cross_board_harness_elements_compiled": True,
            "board_networks_bound": False,
            "field_coupling_executed": False,
            "return_path_inferred": False,
        },
        "release_gate": {
            "state": "blocked_pending_board_port_models",
            "required_before_execution": [
                "explicit board reduced-port networks and shared reference definitions",
                "explicit source/load boundary conditions and analysis mode",
                "validated connector, harness return-path, shielding, and mutual-coupling models",
            ],
        },
    }
    result["result_digest"] = _digest(result)
    return result


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise MultiboardExecutionError(f"{name} must be a lower- or upper-case SHA-256 hexadecimal string.")
    return value.lower()


def _require_record(value: Any, fields: set[str], name: str, *, optional: set[str] | None = None) -> Mapping[str, Any]:
    optional = optional or set()
    if not isinstance(value, Mapping) or set(value) - fields - optional or not fields.issubset(value):
        raise MultiboardExecutionError(f"{name} has missing or unknown fields.")
    return value


def bind_coupled_reduced_network(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Bind explicit board-port models to connector/harness circuit fragments.

    This is a reproducible orchestration handoff.  Board models are represented
    by their kind, immutable digest, and typed terminals rather than being
    silently re-extracted.  The adapter retains supplied mutual terms but does
    not execute them because the present linear-MNA fragment engine has no
    mutual-inductor or distributed multi-conductor primitive.
    """

    if not isinstance(raw, Mapping) or raw.get("contract") != COUPLED_BIND_REQUEST_CONTRACT:
        raise MultiboardExecutionError(f"Coupled bind contract must be {COUPLED_BIND_REQUEST_CONTRACT}.")
    expected = {
        "contract", "multiboard_request", "board_port_networks", "connector_bindings", "reference_nodes",
        "conductor_models", "return_paths", "shield_paths", "mutual_terms",
    }
    if set(raw) - expected or not {"contract", "multiboard_request", "board_port_networks", "connector_bindings", "reference_nodes", "conductor_models", "return_paths"}.issubset(raw):
        raise MultiboardExecutionError("Coupled bind request has missing or unknown fields.")
    source = raw.get("multiboard_request")
    if not isinstance(source, Mapping):
        raise MultiboardExecutionError("multiboard_request must be an object.")
    domain = str(source.get("domain") or "").strip().lower()
    if domain not in {"pi", "si"}:
        raise MultiboardExecutionError("Coupled reduced-network binding only supports PI or SI.")
    plan = _plan_from_request(source, domain=domain, mode="coupled_harness_network")
    harness_compile = compile_harness_electrical_network({
        "contract": HARNESS_COMPILE_REQUEST_CONTRACT,
        "multiboard_request": source,
        "conductor_models": raw.get("conductor_models"),
    })
    boards = {item["board_id"]: item for item in plan["graph"]["boards"]}
    harnesses = {item["harness_id"]: item for item in plan["graph"]["harnesses"]}

    reference_nodes = raw.get("reference_nodes")
    if not isinstance(reference_nodes, list) or not reference_nodes:
        raise MultiboardExecutionError("reference_nodes must contain explicit return reference definitions.")
    references: Dict[str, Dict[str, Any]] = {}
    reference_circuit_nodes: set[str] = set()
    for index, item in enumerate(reference_nodes):
        record = _require_record(item, {"reference_id", "circuit_node", "role"}, f"reference_nodes[{index}]")
        reference_id, circuit_node, role = record["reference_id"], record["circuit_node"], record["role"]
        if not isinstance(reference_id, str) or not reference_id.strip() or reference_id in references:
            raise MultiboardExecutionError(f"reference_nodes[{index}].reference_id is empty or duplicated.")
        if not isinstance(circuit_node, str) or not circuit_node.strip() or circuit_node in reference_circuit_nodes:
            raise MultiboardExecutionError(f"reference_nodes[{index}].circuit_node is empty or duplicated.")
        if role not in {"return", "shield"}:
            raise MultiboardExecutionError(f"reference_nodes[{index}].role must be return or shield.")
        references[reference_id] = {"reference_id": reference_id, "circuit_node": circuit_node, "role": role}
        reference_circuit_nodes.add(circuit_node)
    if not any(item["role"] == "return" for item in references.values()):
        raise MultiboardExecutionError("At least one explicit return reference node is required.")

    raw_networks = raw.get("board_port_networks")
    if not isinstance(raw_networks, list) or len(raw_networks) != len(boards):
        raise MultiboardExecutionError("board_port_networks must provide exactly one reduced network for every selected board.")
    networks: list[Dict[str, Any]] = []
    ports: Dict[tuple[str, str], Dict[str, Any]] = {}
    ports_by_connector_pin: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    seen_network_boards: set[str] = set()
    for index, item in enumerate(raw_networks):
        record = _require_record(item, {"board_id", "network_id", "network_kind", "model_sha256", "ports"}, f"board_port_networks[{index}]")
        board_id = record["board_id"]
        if not isinstance(board_id, str) or board_id not in boards or board_id in seen_network_boards:
            raise MultiboardExecutionError(f"board_port_networks[{index}].board_id is unknown or duplicated.")
        if record["network_kind"] not in {"native_linear_fragment", "nport_s_parameters"}:
            raise MultiboardExecutionError(f"board_port_networks[{index}].network_kind is unsupported.")
        if not isinstance(record["network_id"], str) or not record["network_id"].strip():
            raise MultiboardExecutionError(f"board_port_networks[{index}].network_id must be non-empty.")
        model_sha256 = _sha256(record["model_sha256"], f"board_port_networks[{index}].model_sha256")
        raw_ports = record["ports"]
        if not isinstance(raw_ports, list) or not raw_ports:
            raise MultiboardExecutionError(f"board_port_networks[{index}].ports must not be empty.")
        normalized_ports: list[Dict[str, Any]] = []
        for port_index, port in enumerate(raw_ports):
            port_record = _require_record(
                port,
                {"port_id", "connector_id", "pin", "signal_node", "return_node", "return_reference_id"},
                f"board_port_networks[{index}].ports[{port_index}]", optional={"shield_node", "shield_reference_id"},
            )
            port_id = port_record["port_id"]
            key = (board_id, port_id) if isinstance(port_id, str) else (board_id, "")
            connector_key = (board_id, str(port_record["connector_id"]), str(port_record["pin"]))
            string_fields = ("port_id", "connector_id", "pin", "signal_node", "return_node", "return_reference_id")
            if any(not isinstance(port_record[field], str) or not port_record[field].strip() for field in string_fields):
                raise MultiboardExecutionError(f"board_port_networks[{index}].ports[{port_index}] has an empty terminal field.")
            if key in ports or connector_key in ports_by_connector_pin:
                raise MultiboardExecutionError(f"board_port_networks[{index}].ports[{port_index}] duplicates a board port or connector pin.")
            return_reference_id = port_record["return_reference_id"]
            if return_reference_id not in references or references[return_reference_id]["role"] != "return":
                raise MultiboardExecutionError(f"board port {board_id}:{port_id} requires a declared return reference.")
            shield_reference_id = port_record.get("shield_reference_id")
            shield_node = port_record.get("shield_node")
            if (shield_reference_id is None) != (shield_node is None):
                raise MultiboardExecutionError(f"board port {board_id}:{port_id} must provide shield node and reference together.")
            if shield_reference_id is not None:
                if not isinstance(shield_reference_id, str) or shield_reference_id not in references or references[shield_reference_id]["role"] != "shield":
                    raise MultiboardExecutionError(f"board port {board_id}:{port_id} has an unknown shield reference.")
                if not isinstance(shield_node, str) or not shield_node.strip():
                    raise MultiboardExecutionError(f"board port {board_id}:{port_id} shield_node must be non-empty.")
            normalized = {"board_id": board_id, **dict(port_record)}
            ports[key] = normalized
            ports_by_connector_pin[connector_key] = normalized
            normalized_ports.append(normalized)
        networks.append({"board_id": board_id, "network_id": record["network_id"], "network_kind": record["network_kind"], "model_sha256": model_sha256, "ports": normalized_ports})
        seen_network_boards.add(board_id)

    conductor_nodes = {
        (item["harness_id"], item["source_pin"]): item
        for item in harness_compile["circuit_fragment"]["conductors"]
    }
    raw_bindings = raw.get("connector_bindings")
    if not isinstance(raw_bindings, list):
        raise MultiboardExecutionError("connector_bindings must be an array.")
    bindings: list[Dict[str, Any]] = []
    expected_bindings: set[tuple[str, str, str]] = set()
    for harness in harnesses.values():
        for source_pin, target_pin in harness["pin_map"].items():
            expected_bindings.add((harness["harness_id"], "a", str(source_pin)))
            expected_bindings.add((harness["harness_id"], "b", str(target_pin)))
    seen_bindings: set[tuple[str, str, str]] = set()
    binding_ids: set[str] = set()
    connector_elements: list[Dict[str, Any]] = []
    for index, item in enumerate(raw_bindings):
        record = _require_record(
            item,
            {"binding_id", "board_id", "connector_id", "pin", "port_id", "harness_id", "harness_side", "harness_pin", "resistance_ohm", "inductance_h"},
            f"connector_bindings[{index}]",
        )
        binding_id = record["binding_id"]
        board_id, harness_id, side, pin = record["board_id"], record["harness_id"], record["harness_side"], str(record["harness_pin"])
        if not isinstance(binding_id, str) or not binding_id.strip() or binding_id in binding_ids:
            raise MultiboardExecutionError(f"connector_bindings[{index}].binding_id is empty or duplicated.")
        if board_id not in boards or harness_id not in harnesses or side not in {"a", "b"}:
            raise MultiboardExecutionError(f"connector_bindings[{index}] has an unknown board, harness, or side.")
        key = (harness_id, side, pin)
        if key not in expected_bindings or key in seen_bindings:
            raise MultiboardExecutionError(f"connector_bindings[{index}] does not bind a unique retained harness endpoint pin.")
        harness = harnesses[harness_id]
        expected_board = harness["endpoint_a"]["board_id"] if side == "a" else harness["endpoint_b"]["board_id"]
        expected_connector = harness["endpoint_a"]["connector_id"] if side == "a" else harness["endpoint_b"]["connector_id"]
        if board_id != expected_board or record["connector_id"] != expected_connector:
            raise MultiboardExecutionError(f"connector_bindings[{index}] does not match the retained harness endpoint.")
        port = ports.get((board_id, record["port_id"]))
        if port is None or port["connector_id"] != record["connector_id"] or port["pin"] != record["pin"] or str(record["pin"]) != pin:
            raise MultiboardExecutionError(f"connector_bindings[{index}] does not resolve to the declared board port and connector pin.")
        source_pin = pin if side == "a" else next((source for source, target in harness["pin_map"].items() if str(target) == pin), None)
        conductor = conductor_nodes.get((harness_id, str(source_pin)))
        if conductor is None:
            raise MultiboardExecutionError(f"connector_bindings[{index}] has no compiled harness conductor.")
        harness_node = conductor["source_node"] if side == "a" else conductor["target_node"]
        series_node = f"connector:{binding_id}:series"
        resistance = _finite(record["resistance_ohm"], "connector resistance_ohm", positive=True)
        inductance = _finite(record["inductance_h"], "connector inductance_h", positive=True)
        provenance = {"binding_id": binding_id, "board_id": board_id, "harness_id": harness_id, "harness_side": side, "port_id": record["port_id"]}
        connector_elements.extend([
            {"id": f"connector:{binding_id}:R", "type": "resistor", "positive_node": port["signal_node"], "negative_node": series_node, "resistance_ohm": resistance, **provenance},
            {"id": f"connector:{binding_id}:L", "type": "inductor", "positive_node": series_node, "negative_node": harness_node, "inductance_h": inductance, **provenance},
        ])
        bindings.append({**dict(record), "harness_terminal_node": harness_node, "return_reference_id": port["return_reference_id"], "shield_reference_id": port.get("shield_reference_id")})
        seen_bindings.add(key)
        binding_ids.add(binding_id)
    if seen_bindings != expected_bindings:
        raise MultiboardExecutionError("connector_bindings must cover every selected harness endpoint pin exactly once.")

    def compile_reference_paths(value: Any, label: str, role: str) -> list[Dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise MultiboardExecutionError(f"{label} must be an array.")
        paths: list[Dict[str, Any]] = []
        seen_harnesses: set[str] = set()
        for index, item in enumerate(value):
            record = _require_record(item, {"harness_id", "source_port_id", "target_port_id", "resistance_ohm", "inductance_h"}, f"{label}[{index}]")
            harness_id = record["harness_id"]
            if not isinstance(harness_id, str) or harness_id not in harnesses or harness_id in seen_harnesses:
                raise MultiboardExecutionError(f"{label}[{index}].harness_id is unknown or duplicated.")
            harness = harnesses[harness_id]
            source = ports.get((harness["endpoint_a"]["board_id"], record["source_port_id"]))
            target = ports.get((harness["endpoint_b"]["board_id"], record["target_port_id"]))
            if source is None or target is None:
                raise MultiboardExecutionError(f"{label}[{index}] does not resolve to retained board ports.")
            source_node = source["return_node"] if role == "return" else source.get("shield_node")
            target_node = target["return_node"] if role == "return" else target.get("shield_node")
            source_reference = source["return_reference_id"] if role == "return" else source.get("shield_reference_id")
            target_reference = target["return_reference_id"] if role == "return" else target.get("shield_reference_id")
            if not isinstance(source_node, str) or not isinstance(target_node, str) or not source_reference or not target_reference:
                raise MultiboardExecutionError(f"{label}[{index}] requires explicit {role} nodes and references at both ports.")
            resistance = _finite(record["resistance_ohm"], f"{label} resistance_ohm", positive=True)
            inductance = _finite(record["inductance_h"], f"{label} inductance_h", positive=True)
            series_node = f"{label}:{harness_id}:series"
            provenance = {"harness_id": harness_id, "source_port_id": record["source_port_id"], "target_port_id": record["target_port_id"], "path_role": role, "source_reference_id": source_reference, "target_reference_id": target_reference}
            paths.extend([
                {"id": f"{label}:{harness_id}:R", "type": "resistor", "positive_node": source_node, "negative_node": series_node, "resistance_ohm": resistance, **provenance},
                {"id": f"{label}:{harness_id}:L", "type": "inductor", "positive_node": series_node, "negative_node": target_node, "inductance_h": inductance, **provenance},
            ])
            seen_harnesses.add(harness_id)
        if role == "return" and seen_harnesses != set(harnesses):
            raise MultiboardExecutionError("return_paths must provide one explicit return path for every selected harness.")
        return paths

    return_elements = compile_reference_paths(raw.get("return_paths"), "return", "return")
    shield_elements = compile_reference_paths(raw.get("shield_paths"), "shield", "shield")
    raw_mutual = raw.get("mutual_terms") or []
    if not isinstance(raw_mutual, list):
        raise MultiboardExecutionError("mutual_terms must be an array when supplied.")
    valid_conductor_ids = {f"harness:{item['harness_id']}:{item['source_pin']}" for item in harness_compile["circuit_fragment"]["conductors"]}
    mutual_terms: list[Dict[str, Any]] = []
    mutual_ids: set[str] = set()
    mutual_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_mutual):
        record = _require_record(item, {"term_id", "conductor_a_id", "conductor_b_id", "mutual_inductance_h"}, f"mutual_terms[{index}]")
        term_id, first, second = record["term_id"], record["conductor_a_id"], record["conductor_b_id"]
        if not isinstance(term_id, str) or not term_id.strip() or term_id in mutual_ids or first not in valid_conductor_ids or second not in valid_conductor_ids or first == second:
            raise MultiboardExecutionError(f"mutual_terms[{index}] is invalid or has duplicate/self conductor references.")
        pair = tuple(sorted((first, second)))
        if pair in mutual_pairs:
            raise MultiboardExecutionError(f"mutual_terms[{index}] duplicates a conductor pair.")
        mutual_terms.append({**dict(record), "mutual_inductance_h": _finite(record["mutual_inductance_h"], "mutual_inductance_h")})
        mutual_ids.add(term_id)
        mutual_pairs.add(pair)

    circuit_elements = [
        *harness_compile["circuit_fragment"]["elements"], *connector_elements, *return_elements, *shield_elements,
    ]
    result = {
        "contract": COUPLED_BIND_RESULT_CONTRACT,
        "status": "bound",
        "domain": domain,
        "plan_contract": PLAN_CONTRACT,
        "plan_digest": plan["plan_digest"],
        "model_status": "explicit_reduced_network_orchestration_only",
        "production_qualified": False,
        "board_port_networks": sorted(networks, key=lambda item: item["board_id"]),
        "connector_bindings": sorted(bindings, key=lambda item: item["binding_id"]),
        "reference_nodes": sorted(references.values(), key=lambda item: item["reference_id"]),
        "circuit_fragment": {"elements": circuit_elements, "mutual_terms": sorted(mutual_terms, key=lambda item: item["term_id"])},
        "coupling": {
            "board_port_models_bound": True,
            "connector_models_bound": True,
            "harness_signal_models_bound": True,
            "return_paths_bound": True,
            "shield_paths_bound": bool(shield_elements),
            "mutual_terms_provided": bool(mutual_terms),
            "mutual_terms_executed": False,
            "field_coupling_executed": False,
            "solver_executed": False,
        },
        "release_gate": {
            "state": "blocked_pending_domain_solver_and_validation",
            "required_before_execution": [
                "a versioned PI reduced-circuit adapter or SI N-port cascade adapter that consumes this exact binding digest",
                "mutual/distributed multi-conductor support when mutual_terms are supplied",
                "explicit source/load, analysis, reference-plane, and de-embedding definitions",
                "analytical, independent-solver, and measured two-board harness validation fixtures",
            ],
        },
    }
    result["result_digest"] = _digest(result)
    return result


__all__ = [
    "HARNESS_COMPILE_REQUEST_CONTRACT", "HARNESS_COMPILE_RESULT_CONTRACT", "MAX_BATCH_BOARD_JOBS",
    "MAX_BATCH_FREQUENCY_POINTS", "MAX_BATCH_LANES", "MAX_BATCH_NUMERIC_BYTES", "MultiboardExecutionError",
    "SI_BATCH_REQUEST_CONTRACT", "SI_BATCH_RESULT_CONTRACT", "COUPLED_BIND_REQUEST_CONTRACT",
    "COUPLED_BIND_RESULT_CONTRACT", "bind_coupled_reduced_network", "compile_harness_electrical_network",
    "run_independent_si_batch",
]
