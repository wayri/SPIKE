"""Bounded, inspectable lumped thermal-network calculation.

This module deliberately models only an explicitly supplied thermal resistance/
capacitance network.  It is useful for early solid-conduction and interface
trade-offs, but it is not a substitute for geometry-derived spreading, CFD, or
thermal sign-off.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


MAX_NETWORK_NODES = 256
MAX_TRANSIENT_STEPS = 10_000


def _issue(code: str, message: str, *, severity: str = "error") -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _finite_positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _conductance(link: Mapping[str, Any], label: str) -> Tuple[float | None, Dict[str, str] | None]:
    """Return conductance from one of the explicit supported link definitions."""
    resistance = _finite_positive(link.get("resistance_c_per_w"))
    if resistance is not None:
        return 1.0 / resistance, None
    conductance = _finite_positive(link.get("conductance_w_per_k"))
    if conductance is not None:
        return conductance, None

    # The geometry form is intentionally restricted to a one-dimensional
    # through-interface resistance.  It must not be mistaken for board spreading.
    conductivity = _finite_positive(link.get("conductivity_w_mk", link.get("thermal_conductivity_w_mk")))
    area_mm2 = _finite_positive(link.get("contact_area_mm2"))
    thickness_mm = _finite_positive(link.get("thickness_mm"))
    if conductivity is not None and area_mm2 is not None and thickness_mm is not None:
        return conductivity * area_mm2 * 1e-3 / thickness_mm, None
    return None, _issue(
        "THERMAL_NETWORK_LINK_PROPERTIES_REQUIRED",
        f"{label} needs positive resistance_c_per_w, conductance_w_per_k, or conductivity_w_mk/contact_area_mm2/thickness_mm.",
    )


def _solve_linear(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> List[float]:
    """Solve a small dense system using deterministic partial-pivot elimination."""
    n = len(rhs)
    work = [list(row) + [float(rhs[index])] for index, row in enumerate(matrix)]
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(work[row][column]))
        if abs(work[pivot][column]) <= 1e-15:
            raise ValueError("thermal network is singular")
        if pivot != column:
            work[column], work[pivot] = work[pivot], work[column]
        scale = work[column][column]
        for index in range(column, n + 1):
            work[column][index] /= scale
        for row in range(column + 1, n):
            factor = work[row][column]
            if factor == 0:
                continue
            for index in range(column, n + 1):
                work[row][index] -= factor * work[column][index]
    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        solution[row] = work[row][n] - sum(work[row][column] * solution[column] for column in range(row + 1, n))
    return solution


def _network_links(scenario: Any, node_ids: set[str]) -> Tuple[List[Tuple[str, str | None, float, str]], List[Dict[str, str]]]:
    links: List[Tuple[str, str | None, float, str]] = []
    issues: List[Dict[str, str]] = []
    for index, raw in enumerate(scenario.thermal_links):
        if not bool(raw.get("enabled", True)):
            continue
        link_id = str(raw.get("id") or f"thermal_links[{index}]")
        left = str(raw.get("from_id") or "")
        right = str(raw.get("to_id") or "")
        endpoints = (left, right)
        if endpoints.count("ambient") == 1:
            node = right if left == "ambient" else left
            other = None
        elif left in node_ids and right in node_ids and left != right:
            node, other = left, right
        else:
            issues.append(_issue("THERMAL_NETWORK_LINK_ENDPOINT_INVALID", f"{link_id} must connect two elements or one element to ambient."))
            continue
        conductance, error = _conductance(raw, link_id)
        if error:
            issues.append(error)
            continue
        links.append((node, other, conductance, link_id))

    for element in scenario.thermal_elements:
        node_id = str(element.get("id") or "")
        resistance = _finite_positive(element.get("ambient_resistance_c_per_w"))
        if resistance is not None:
            links.append((node_id, None, 1.0 / resistance, f"ambient:{node_id}"))
    return links, issues


def estimate_lumped_thermal_network(scenario: Any, *, inherited_issues: Iterable[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    """Solve an explicit resistive/RC thermal network.

    ``thermal_elements`` are nodes. ``thermal_links`` connect two nodes or an
    element to the literal ``ambient`` endpoint.  A node-level
    ``ambient_resistance_c_per_w`` is shorthand for an ambient link.  Transient
    runs require positive ``thermal_capacitance_j_per_c`` on every node.
    """
    issues = [dict(item) for item in inherited_issues]
    if scenario.mode not in {"steady_state", "transient"}:
        issues.append(_issue("THERMAL_NETWORK_MODE_UNSUPPORTED", "The lumped thermal network supports steady_state or transient mode only."))
    elements = list(scenario.thermal_elements)
    if not elements:
        issues.append(_issue("THERMAL_NETWORK_ELEMENTS_REQUIRED", "A lumped thermal-network estimate needs at least one thermal element."))
    if len(elements) > MAX_NETWORK_NODES:
        issues.append(_issue("THERMAL_NETWORK_NODE_LIMIT_EXCEEDED", f"The compact network supports at most {MAX_NETWORK_NODES} thermal elements."))

    ids = [str(element.get("id") or "") for element in elements]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        issues.append(_issue("THERMAL_NETWORK_ELEMENT_ID_INVALID", "Thermal-network elements need unique non-empty IDs."))
    node_ids = set(ids)
    links, link_issues = _network_links(scenario, node_ids)
    issues.extend(link_issues)

    powers: Dict[str, float] = {}
    capacitance: Dict[str, float] = {}
    for element in elements:
        node_id = str(element.get("id") or "")
        try:
            power = float(element.get("power_w", 0) or 0)
        except (TypeError, ValueError):
            power = float("nan")
        if not math.isfinite(power) or power < 0:
            issues.append(_issue("THERMAL_NETWORK_POWER_INVALID", f"{node_id or '<unnamed>'} power_w must be finite and non-negative."))
        powers[node_id] = power
        if scenario.mode == "transient":
            value = _finite_positive(element.get("thermal_capacitance_j_per_c"))
            if value is None:
                issues.append(_issue("THERMAL_NETWORK_CAPACITANCE_REQUIRED", f"{node_id or '<unnamed>'} needs positive thermal_capacitance_j_per_c for transient analysis."))
            else:
                capacitance[node_id] = value

    # Power tables may contribute to an explicitly named element.  No component
    # reference is inferred: that would create a silent electro-thermal mapping.
    for source in scenario.heat_sources:
        element_id = str(source.get("element_id") or "")
        if not element_id:
            continue
        if element_id not in node_ids:
            issues.append(_issue("THERMAL_NETWORK_HEAT_SOURCE_ELEMENT_UNKNOWN", f"Heat source {source.get('id') or '<unnamed>'} targets unknown element {element_id}."))
            continue
        power = _finite_nonnegative(source.get("power_w"))
        if power is None:
            issues.append(_issue("THERMAL_NETWORK_HEAT_SOURCE_POWER_INVALID", f"Heat source {source.get('id') or '<unnamed>'} needs finite non-negative power_w."))
            continue
        powers[element_id] += power

    if not any(item.get("severity") == "error" for item in issues):
        connected = {node for node, other, _, _ in links if other is None}
        # A component attached to an ambient-connected node is constrained.  A
        # straightforward graph traversal catches isolated floating subgraphs.
        adjacency = {node: set() for node in node_ids}
        for left, right, _, _ in links:
            if right is not None:
                adjacency[left].add(right)
                adjacency[right].add(left)
        reachable = set(connected)
        frontier = list(connected)
        while frontier:
            node = frontier.pop()
            for neighbor in adjacency[node]:
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    frontier.append(neighbor)
        for node in sorted(node_ids - reachable):
            issues.append(_issue("THERMAL_NETWORK_AMBIENT_PATH_REQUIRED", f"{node} has no explicit thermal path to ambient."))

    if any(item.get("severity") == "error" for item in issues):
        return {
            "contract": "spike/thermal-result/v1", "scenario_id": scenario.scenario_id,
            "status": "blocked", "model_status": "failed", "mode": scenario.mode,
            "ambient_temperature_c": scenario.ambient_temperature_c, "summary": {"node_count": len(elements)},
            "nodes": [], "links": [], "issues": issues,
            "provenance": {"engine": "spike-lumped-thermal-network", "qualification": "not_executed"},
        }

    index = {node_id: offset for offset, node_id in enumerate(ids)}
    matrix = [[0.0 for _ in ids] for _ in ids]
    for left, right, conductance, _ in links:
        row = index[left]
        matrix[row][row] += conductance
        if right is not None:
            column = index[right]
            matrix[column][column] += conductance
            matrix[row][column] -= conductance
            matrix[column][row] -= conductance
    rises = _solve_linear(matrix, [powers[node_id] for node_id in ids])
    temperatures = [float(scenario.ambient_temperature_c) + rise for rise in rises]
    frames: List[Dict[str, Any]] = []
    if scenario.mode == "transient":
        end_time = float(scenario.run["end_time_s"])
        requested_interval = float(scenario.run["write_interval_s"])
        steps = max(1, math.ceil(end_time / requested_interval))
        if steps > MAX_TRANSIENT_STEPS:
            return {
                "contract": "spike/thermal-result/v1", "scenario_id": scenario.scenario_id, "status": "blocked", "model_status": "failed",
                "mode": scenario.mode, "ambient_temperature_c": scenario.ambient_temperature_c, "summary": {"node_count": len(elements)}, "nodes": [], "links": [],
                "issues": issues + [_issue("THERMAL_NETWORK_TRANSIENT_STEP_LIMIT_EXCEEDED", f"Transient output requires {steps} steps; the compact network limit is {MAX_TRANSIENT_STEPS}.")],
                "provenance": {"engine": "spike-lumped-thermal-network", "qualification": "not_executed"},
            }
        delta_t = end_time / steps
        prior = [0.0] * len(ids)
        for step in range(steps + 1):
            if step:
                transient_matrix = [row[:] for row in matrix]
                rhs = [powers[node_id] for node_id in ids]
                for node_id, row in index.items():
                    inertia = capacitance[node_id] / delta_t
                    transient_matrix[row][row] += inertia
                    rhs[row] += inertia * prior[row]
                prior = _solve_linear(transient_matrix, rhs)
            frames.append({
                "time_s": min(end_time, step * delta_t),
                "temperatures_c": {node_id: float(scenario.ambient_temperature_c) + prior[index[node_id]] for node_id in ids},
            })

    nodes = [
        {"id": node_id, "power_w": powers[node_id], "temperature_rise_c": rises[index[node_id]], "steady_temperature_c": temperatures[index[node_id]],
         **({"thermal_capacitance_j_per_c": capacitance[node_id]} if node_id in capacitance else {})}
        for node_id in ids
    ]
    return {
        "contract": "spike/thermal-result/v1", "scenario_id": scenario.scenario_id,
        "status": "completed", "model_status": "approximate", "mode": scenario.mode,
        "ambient_temperature_c": scenario.ambient_temperature_c,
        "summary": {"node_count": len(nodes), "link_count": len(links), "total_power_w": sum(powers.values()), "max_steady_temperature_c": max(temperatures)},
        "nodes": nodes,
        "links": [{"id": link_id, "from_id": left, "to_id": right or "ambient", "conductance_w_per_k": conductance} for left, right, conductance, link_id in links],
        "transient": frames,
        "issues": issues + [_issue("LUMPED_THERMAL_NETWORK_MODEL", "Explicit resistance/capacitance network only; geometry-derived spreading, radiation, airflow, and conjugate heat transfer are not solved.", severity="warning")],
        "provenance": {
            "engine": "spike-lumped-thermal-network", "method": "dense conductance solve; backward-Euler transient integration",
            "qualification": "engineering_precheck_only", "ambient_path": "explicit thermal-links or node ambient_resistance_c_per_w",
        },
    }


__all__ = ["MAX_NETWORK_NODES", "MAX_TRANSIENT_STEPS", "estimate_lumped_thermal_network"]
