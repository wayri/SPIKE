"""Coupled power-loop parasitic extraction for explicit copper paths.

The extractor treats every routed net segment as an independent conductor with
an explicit current-entry and current-exit terminal.  All selected branches are
then solved together against the full PEEC resistance/partial-inductance
matrix.  This preserves mutual coupling between forward and return conductors;
adding independently extracted net inductances would not.
"""

from __future__ import annotations

from math import isfinite, pi
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from .contracts import AnalysisSpec, ValidationIssue
from .hybrid_mesh import HybridMesh, nearest_mesh_node
from .peec_network import dense, impedance_point, solve_linear_system


def solve_coupled_path_currents(
    mesh: HybridMesh,
    paths: Sequence[Dict[str, Any]],
    branch_indices: Sequence[int],
    branch_impedance: np.ndarray,
    *,
    diagnostics: bool = False,
) -> Tuple[complex, np.ndarray, Dict[str, Any]]:
    """Solve one ampere through each serial conductor path.

    Each path supplies ``node_ids``, ``start_node`` and ``end_node``.  One
    voltage reference is removed per disconnected conductor while the full
    branch impedance matrix, including cross-conductor mutual L, is retained.
    The returned impedance is the sum of the voltage drops along the ordered
    loop path.
    """

    if not paths:
        raise ValueError("at least one conductor path is required")
    if branch_impedance.shape != (len(branch_indices), len(branch_indices)):
        raise ValueError("branch impedance does not match the selected loop branches")

    branch_column = {branch_index: column for column, branch_index in enumerate(branch_indices)}
    retained_rows: List[Tuple[int, int]] = []
    path_nodes: List[Dict[int, int]] = []
    for path in paths:
        node_ids = [int(value) for value in path["node_ids"]]
        start_node = int(path["start_node"])
        end_node = int(path["end_node"])
        if start_node == end_node:
            raise ValueError("a conductor path start and end resolve to the same mesh node")
        local = {node_id: index for index, node_id in enumerate(node_ids)}
        if start_node not in local or end_node not in local:
            raise ValueError("a conductor endpoint is outside its connected copper component")
        path_nodes.append(local)
        retained_rows.extend((len(path_nodes) - 1, node_id) for node_id in node_ids if node_id != end_node)

    incidence = np.zeros((len(retained_rows), len(branch_indices)), dtype=float)
    voltage_row = {key: row for row, key in enumerate(retained_rows)}
    for path_index, path in enumerate(paths):
        local = path_nodes[path_index]
        end_node = int(path["end_node"])
        for branch_index in path["branch_indices"]:
            branch = mesh.branches[int(branch_index)]
            column = branch_column[int(branch_index)]
            for node_id, sign in ((branch.node_p, 1.0), (branch.node_n, -1.0)):
                if node_id in local and node_id != end_node:
                    incidence[voltage_row[(path_index, node_id)], column] = sign

    branch_count = len(branch_indices)
    voltage_count = len(retained_rows)
    matrix = np.zeros((branch_count + voltage_count, branch_count + voltage_count), dtype=complex)
    matrix[:branch_count, :branch_count] = branch_impedance
    matrix[:branch_count, branch_count:] = -incidence.T
    matrix[branch_count:, :branch_count] = incidence
    rhs = np.zeros(matrix.shape[0], dtype=complex)
    for path_index, path in enumerate(paths):
        start_node = int(path["start_node"])
        rhs[branch_count + voltage_row[(path_index, start_node)]] += 1.0

    solution, quality = solve_linear_system(matrix, rhs, diagnostics)
    currents = solution[:branch_count]
    impedance = sum(
        solution[branch_count + voltage_row[(path_index, int(path["start_node"]))]]
        for path_index, path in enumerate(paths)
    )
    return complex(impedance), currents, quality


def _connected_path(
    mesh: HybridMesh,
    net: str,
    start_node: int,
) -> Tuple[List[int], List[int]]:
    candidate_indices = [index for index, branch in enumerate(mesh.branches) if branch.net == net]
    adjacency: Dict[int, List[Tuple[int, int]]] = {}
    for branch_index in candidate_indices:
        branch = mesh.branches[branch_index]
        adjacency.setdefault(branch.node_p, []).append((branch.node_n, branch_index))
        adjacency.setdefault(branch.node_n, []).append((branch.node_p, branch_index))
    nodes = {start_node}
    branches: set[int] = set()
    pending = [start_node]
    while pending:
        current = pending.pop()
        for neighbor, branch_index in adjacency.get(current, []):
            branches.add(branch_index)
            if neighbor not in nodes:
                nodes.add(neighbor)
                pending.append(neighbor)
    return sorted(nodes), sorted(branches)


def _terminal(raw: Any, label: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an explicit pad or coordinate terminal")
    if raw.get("position_mm") is None and raw.get("at") is None:
        raise ValueError(f"{label} requires position_mm or at")
    return raw


def _normalize_conductors(request: Dict[str, Any]) -> List[Dict[str, Any]]:
    configured = request.get("conductors")
    if isinstance(configured, list) and configured:
        return [dict(item) for item in configured if isinstance(item, dict)]
    forward = request.get("forward")
    return_path = request.get("return")
    if not isinstance(forward, dict) or not isinstance(return_path, dict):
        raise ValueError("forward and return conductor definitions are required")
    return [
        {
            "id": str(forward.get("id") or "forward"),
            "role": "forward",
            "net": forward.get("net"),
            "start": forward.get("start") or forward.get("source"),
            "end": forward.get("end") or forward.get("load"),
        },
        {
            "id": str(return_path.get("id") or "return"),
            "role": "return",
            "net": return_path.get("net"),
            # Return current enters at the load side and exits at the source side.
            "start": return_path.get("start") or return_path.get("load"),
            "end": return_path.get("end") or return_path.get("source"),
        },
    ]


def _series_component_impedance(
    raw_models: Any,
    frequencies: Sequence[float],
) -> Tuple[np.ndarray, List[Dict[str, Any]], List[ValidationIssue]]:
    impedance = np.zeros(len(frequencies), dtype=complex)
    accepted: List[Dict[str, Any]] = []
    issues: List[ValidationIssue] = []
    if raw_models is None:
        return impedance, accepted, issues
    if not isinstance(raw_models, list):
        raise ValueError("component_models must be an array")
    for index, raw in enumerate(raw_models):
        if not isinstance(raw, dict):
            raise ValueError(f"component_models[{index}] must be an object")
        identifier = str(raw.get("id") or raw.get("reference") or f"component-{index + 1}")
        if raw.get("reviewed") is not True:
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-E-0204", "error",
                f"Series model {identifier} has not been reviewed.",
                path=f"options.loop_extractions.component_models[{index}]",
                suggestion="Review the pin mapping and operating-point model in the Power Tree model assistant.",
            ))
            continue
        topology = str(raw.get("topology", "series")).lower()
        if topology != "series":
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-W-0205", "warning",
                f"Shunt model {identifier} is preserved for the circuit solve but is not added to scalar loop impedance.",
                path=f"options.loop_extractions.component_models[{index}]",
                status="unsupported",
            ))
            continue
        def nonnegative(key: str, value: Any) -> float:
            if isinstance(value, bool):
                raise ValueError(f"component_models[{index}].{key} must be finite and non-negative")
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"component_models[{index}].{key} must be finite and non-negative") from exc
            if not isfinite(number) or number < 0.0:
                raise ValueError(f"component_models[{index}].{key} must be finite and non-negative")
            return number

        resistance = nonnegative("resistance_ohm", raw.get("resistance_ohm", raw.get("linearized_resistance_ohm", 0.0)))
        inductance = nonnegative("inductance_h", raw.get("inductance_h", 0.0))
        capacitance = nonnegative("capacitance_f", raw.get("capacitance_f", 0.0))
        if str(raw.get("model_kind", "linear_rlc")).lower() not in {"linear_rlc", "passive", "linearized_operating_point"}:
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-W-0206", "warning",
                f"Nonlinear model {identifier} contributes only its reviewed operating-point linearization to this extraction.",
                path=f"options.loop_extractions.component_models[{index}]",
                suggestion="Run the linked ngspice transient or operating-point study for nonlinear device behavior.",
                status="approximate",
            ))
        for frequency_index, frequency in enumerate(frequencies):
            omega = 2.0 * pi * float(frequency)
            impedance[frequency_index] += resistance + 1j * omega * inductance
            if capacitance > 0:
                impedance[frequency_index] += 1.0 / (1j * omega * capacitance)
        accepted.append({
            "id": identifier,
            "reference": raw.get("reference"),
            "model_kind": raw.get("model_kind", "linear_rlc"),
            "resistance_ohm": resistance,
            "inductance_h": inductance,
            "capacitance_f": capacitance or None,
            "input_pins": list(raw.get("input_pins", [])),
            "output_pins": list(raw.get("output_pins", [])),
            "geometry_center_mm": raw.get("geometry_center_mm"),
            "model_link": raw.get("model_link"),
            "operating_point": raw.get("operating_point"),
            "reviewed": True,
        })
    return impedance, accepted, issues


def extract_loop_parasitics(
    mesh: HybridMesh,
    spec: AnalysisSpec,
    solver: Any,
    inductance: np.ndarray,
    branch_capacitance: np.ndarray,
    frequencies: Sequence[float],
) -> Tuple[List[Dict[str, Any]], List[ValidationIssue], Dict[int, float]]:
    """Extract requested pad-to-pad power-loop impedance and loop inductance."""

    raw_requests = spec.options.get("loop_extractions", [])
    if not raw_requests:
        return [], [], {}
    if not isinstance(raw_requests, list):
        return [], [ValidationIssue(
            "SPIKE-BE-PI-E-0200", "error", "options.loop_extractions must be an array.",
            path="options.loop_extractions",
        )], {}

    results: List[Dict[str, Any]] = []
    issues: List[ValidationIssue] = []
    last_currents: Dict[int, float] = {}
    reference_net = str((spec.return_path or {}).get("net") or "")
    for request_index, raw_request in enumerate(raw_requests):
        path = f"options.loop_extractions[{request_index}]"
        if not isinstance(raw_request, dict):
            issues.append(ValidationIssue("SPIKE-BE-PI-E-0200", "error", "Loop extraction request must be an object.", path=path))
            continue
        identifier = str(raw_request.get("id") or f"loop-{request_index + 1}")
        try:
            configured = _normalize_conductors(raw_request)
            if len(configured) < 2:
                raise ValueError("at least one forward and one return conductor are required")
            roles = {str(item.get("role", "")).lower() for item in configured}
            if "forward" not in roles or "return" not in roles:
                raise ValueError("conductor definitions must include forward and return roles")
            resolved: List[Dict[str, Any]] = []
            selected_branches: List[int] = []
            selected_nets: List[str] = []
            for conductor_index, conductor in enumerate(configured):
                net = str(conductor.get("net") or "")
                if not net:
                    raise ValueError(f"conductor {conductor_index + 1} requires a net")
                start = _terminal(conductor.get("start"), f"conductor {conductor_index + 1} start")
                end = _terminal(conductor.get("end"), f"conductor {conductor_index + 1} end")
                start_node = nearest_mesh_node(mesh, start, net)
                end_node = nearest_mesh_node(mesh, end, net)
                if start_node is None or end_node is None:
                    raise ValueError(f"{net} endpoints did not snap to selected copper")
                node_ids, branch_indices = _connected_path(mesh, net, start_node)
                if end_node not in node_ids:
                    raise ValueError(f"{net} endpoints are not connected through the extracted copper graph")
                overlap = set(selected_branches).intersection(branch_indices)
                if overlap:
                    raise ValueError(f"{net} reuses {len(overlap)} branch(es) already assigned to this loop")
                selected_branches.extend(branch_indices)
                selected_nets.append(net)
                resolved.append({
                    "id": str(conductor.get("id") or f"conductor-{conductor_index + 1}"),
                    "role": str(conductor.get("role") or "segment"),
                    "net": net,
                    "start_node": int(start_node),
                    "end_node": int(end_node),
                    "node_ids": node_ids,
                    "branch_indices": branch_indices,
                    "connected_layers": sorted({mesh.branches[index].layer for index in branch_indices}),
                    "geometry_counts": {
                        kind: sum(1 for index in branch_indices if mesh.branches[index].kind == kind)
                        for kind in sorted({mesh.branches[index].kind for index in branch_indices})
                    },
                    "start_terminal": start,
                    "end_terminal": end,
                })
            if len(set(selected_nets)) < 2:
                raise ValueError("forward and return paths must include at least two distinct nets")
            selected_branches = sorted(selected_branches)
            component_impedance, component_models, component_issues = _series_component_impedance(
                raw_request.get("component_models"), frequencies
            )
            issues.extend(component_issues)
            sweep: List[Dict[str, Any]] = []
            quality_points: List[Dict[str, Any]] = []
            geometry_impedance: List[complex] = []
            for frequency_index, frequency in enumerate(frequencies):
                resistance = dense(solver.compute_resistance(float(frequency)))
                branch_impedance = resistance[np.ix_(selected_branches, selected_branches)] + (
                    1j * 2.0 * pi * float(frequency) * inductance[np.ix_(selected_branches, selected_branches)]
                )
                value, currents, quality = solve_coupled_path_currents(
                    mesh, resolved, selected_branches, branch_impedance,
                    diagnostics=frequency_index in {0, len(frequencies) - 1},
                )
                geometry_impedance.append(value)
                total = value + component_impedance[frequency_index]
                point = impedance_point(float(frequency), total)
                point["geometry_resistance_ohm"] = float(value.real)
                point["geometry_reactance_ohm"] = float(value.imag)
                point["component_resistance_ohm"] = float(component_impedance[frequency_index].real)
                point["component_reactance_ohm"] = float(component_impedance[frequency_index].imag)
                sweep.append(point)
                quality_points.append(quality)
                if frequency_index == len(frequencies) - 1:
                    last_currents.update({
                        branch_index: float(abs(currents[column]))
                        for column, branch_index in enumerate(selected_branches)
                    })
            first_frequency = float(frequencies[0])
            geometry_loop_inductance = float(geometry_impedance[0].imag / (2.0 * pi * first_frequency))
            component_l = sum(float(item.get("inductance_h") or 0.0) for item in component_models)
            component_capacitances = [
                float(item["capacitance_f"])
                for item in component_models
                if item.get("capacitance_f") is not None and float(item["capacitance_f"]) > 0.0
            ]
            component_series_capacitance = (
                1.0 / sum(1.0 / value for value in component_capacitances)
                if component_capacitances else None
            )
            forward_branch_indices = [
                index
                for conductor in resolved if str(conductor["role"]).lower() == "forward"
                for index in conductor["branch_indices"]
            ]
            request_return_nets = {
                str(item["net"])
                for item in resolved
                if str(item["role"]).lower() == "return"
            }
            capacitance_reference_valid = bool(
                reference_net
                and len(request_return_nets) == 1
                and reference_net in request_return_nets
            )
            estimated_capacitance = (
                float(np.sum(branch_capacitance[forward_branch_indices]))
                if capacitance_reference_valid else 0.0
            )
            if not capacitance_reference_valid:
                issues.append(ValidationIssue(
                    "SPIKE-BE-PI-W-0203", "warning",
                    f"Loop extraction {identifier} has no capacitance result because its return conductor "
                    "does not match the explicit dielectric-reference net used by this solve.",
                    path=path,
                    suggestion="Run loops with different return nets as separate extraction jobs, or use a multiconductor electrostatic solver.",
                    status="unsupported",
                ))
            results.append({
                "contract": "spike/loop-parasitics/v1",
                "id": identifier,
                "name": str(raw_request.get("name") or identifier),
                "model_status": "approximate",
                "conductors": resolved,
                "forward_nets": [item["net"] for item in resolved if str(item["role"]).lower() == "forward"],
                "return_nets": [item["net"] for item in resolved if str(item["role"]).lower() == "return"],
                "geometry_resistance_ohm": float(geometry_impedance[0].real),
                "geometry_loop_inductance_h": geometry_loop_inductance,
                "component_resistance_ohm": sum(float(item.get("resistance_ohm") or 0.0) for item in component_models),
                "component_inductance_h": component_l,
                "component_series_capacitance_f": component_series_capacitance,
                "total_loop_inductance_h": geometry_loop_inductance + component_l,
                "estimated_net_capacitance_f": estimated_capacitance or None,
                "capacitance_model_status": "approximate" if estimated_capacitance > 0 else "unsupported",
                "component_models": component_models,
                "impedance": sweep,
                "quality": {
                    "maximum_relative_residual": max(float(item["relative_residual"]) for item in quality_points),
                    "maximum_sampled_condition_number": max(
                        (float(item["condition_number"]) for item in quality_points if item.get("condition_number") is not None),
                        default=None,
                    ),
                    "explicit_pad_to_pad_endpoints": True,
                    "mutual_partial_inductance_included": True,
                    "dielectric_stackup_used_for_capacitance": estimated_capacitance > 0,
                    "capacitance_reference_net": reference_net or None,
                },
                "validity": {
                    "scope": "Quasi-static pad-to-pad loop R/L and bounded forward-to-explicit-return capacitance estimate.",
                    "limits": [
                        "loop R/L uses the full selected PEEC partial-inductance matrix",
                        "capacitance is a single-reference stackup estimate, not a multiconductor electrostatic solve",
                        "reviewed series component models are linearized at their declared operating point",
                        "nonlinear switching behavior requires the linked SPICE study",
                    ],
                },
            })
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(ValidationIssue(
                "SPIKE-BE-PI-E-0201", "error", f"Loop extraction {identifier} is invalid: {exc}.",
                path=path,
                suggestion="Select explicit pad endpoints on connected forward and return conductors, then review all intervening component models.",
            ))

    if results:
        issues.append(ValidationIssue(
            "SPIKE-BE-PI-W-0202", "warning",
            "Loop inductance includes forward/return mutual PEEC coupling. Net capacitance remains a bounded single-reference dielectric estimate.",
            path="networks.loop_parasitics",
            suggestion="Correlate sign-off capacitance against a validated electrostatic FEM/BEM solver or measurement.",
            status="approximate",
        ))
    return results, issues, last_currents
