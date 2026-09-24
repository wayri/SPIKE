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
MAX_SURFACE_DENSE_WORK = 50_000_000


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
    # Component top/bottom networks are diagonal. Preserve their O(n) solve
    # rather than running elimination over zeros on every transient sample.
    if all(value == 0 for row, values in enumerate(matrix) for column, value in enumerate(values) if row != column):
        if any(matrix[row][row] <= 0 for row in range(n)):
            raise ValueError("thermal network is singular")
        return [rhs[row] / matrix[row][row] for row in range(n)]
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
    initial_rises: Dict[str, float] = {}
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
            try:
                initial = float(element.get("initial_temperature_c", scenario.ambient_temperature_c))
            except (TypeError, ValueError):
                initial = float("nan")
            if not math.isfinite(initial) or initial < -273.15:
                issues.append(_issue("THERMAL_NETWORK_INITIAL_TEMPERATURE_INVALID", f"{node_id} initial_temperature_c must be finite and at least -273.15 C."))
            initial_rises[node_id] = initial - float(scenario.ambient_temperature_c)

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
        prior = [initial_rises[node_id] for node_id in ids]
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


def estimate_surface_thermal_network(scenario: Any, surfaces: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Solve admitted object boundaries, retaining a single temperature per object.

    The component adapter owns admission and SI-unit conversion is explicit here.
    Radiation is diffuse gray exchange with fixed, large isothermal surroundings
    (view factor one). It is not interobject radiation or a spatial field solver.
    """
    sigma = 5.670374419e-8  # W/(m² K⁴), SI Stefan-Boltzmann constant.
    ids = [str(element["id"]) for element in scenario.thermal_elements]
    index = {identifier: offset for offset, identifier in enumerate(ids)}
    ambient = float(scenario.ambient_temperature_c)
    powers = [float(element["power_w"]) for element in scenario.thermal_elements]
    legacy, issues = _network_links(scenario, set(ids))
    if issues:
        raise ValueError(issues[0]["message"])
    # Each branch is (source, destination or fixed sink, coefficient, sink C,
    # radiation flag). Linear coefficients are W/K; radiation is W/K^4.
    branches = [(index[left], index[right] if right else None, conductance, ambient, False)
                for left, right, conductance, _ in legacy]
    for item in surfaces:
        kind = item["kind"]
        other = index[item["target_ref"]] if kind == "conduction" and item["target_ref"] != "ambient" else None
        if kind == "conduction":
            coefficient = 1 / item["resistance_c_per_w"]
        elif kind == "convection":
            coefficient = item["heat_transfer_coefficient_w_m2_k"] * item["area_mm2"] * 1e-6
        else:
            coefficient = sigma * item["emissivity"] * item["area_mm2"] * 1e-6
        if not math.isfinite(coefficient) or coefficient <= 0:
            raise ValueError(f"{item['id']} coefficient exceeds the positive finite numerical range.")
        sink = item.get("surroundings_temperature_c", item.get("ambient_temperature_c", ambient))
        branches.append((index[item["object_ref"]], other, coefficient, sink, kind == "radiation"))

    reachable = {left for left, right, _, _, _ in branches if right is None}
    adjacency = {i: set() for i in range(len(ids))}
    for left, right, _, _, _ in branches:
        if right is not None:
            adjacency[left].add(right)
            adjacency[right].add(left)
    frontier = list(reachable)
    while frontier:
        for neighbor in adjacency[frontier.pop()]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                frontier.append(neighbor)
    if len(reachable) != len(ids):
        missing = ", ".join(ids[i] for i in range(len(ids)) if i not in reachable)
        raise ValueError(f"Objects without an explicit path to a fixed thermal sink: {missing}.")

    steps = 0
    if scenario.mode == "transient":
        end = float(scenario.run["end_time_s"])
        steps = max(1, math.ceil(end / float(scenario.run["write_interval_s"])))
        if steps > MAX_TRANSIENT_STEPS:
            raise ValueError(f"Transient output exceeds {MAX_TRANSIENT_STEPS} steps.")
    # A single interobject branch selects dense elimination for this matrix.
    # Bound both the minimum expected work and actual Newton factorizations;
    # the latter prevents nonlinear iterations multiplying the admitted budget.
    dense_solve_work = len(ids) ** 3 if any(right is not None for _, right, _, _, _ in branches) else 0
    dense_work_used = 0
    work_limit_message = (
        f"Coupled surface solve exceeds the {MAX_SURFACE_DENSE_WORK:,} dense work-unit limit. "
        "Reduce the number of objects, increase the time step, or shorten the duration."
    )
    if dense_solve_work * (steps + 1) > MAX_SURFACE_DENSE_WORK:
        raise ValueError(work_limit_message)

    matrix = [[0.0] * len(ids) for _ in ids]
    for left, right, coefficient, _, radiation in branches:
        if radiation:
            continue
        matrix[left][left] += coefficient
        if right is not None:
            matrix[right][right] += coefficient
            matrix[left][right] -= coefficient
            matrix[right][left] -= coefficient
    if any(not math.isfinite(value) for row in matrix for value in row):
        raise ValueError("Combined thermal conductance exceeds the finite numerical range.")

    def evaluate(rises: Sequence[float], inertia: Sequence[float], prior: Sequence[float]):
        residual = [-power + inertia[i] * (rises[i] - prior[i]) for i, power in enumerate(powers)]
        scales = [max(1.0, abs(power), abs(inertia[i] * (rises[i] - prior[i]))) for i, power in enumerate(powers)]
        flows = []
        for left, right, coefficient, sink, radiation in branches:
            delta = rises[left] - (rises[right] if right is not None else sink - ambient)
            if radiation:
                kelvin = rises[left] + ambient + 273.15
                sink_kelvin = sink + 273.15
                flow = coefficient * delta * (kelvin + sink_kelvin) * (kelvin * kelvin + sink_kelvin * sink_kelvin)
            else:
                flow = coefficient * delta
            residual[left] += flow
            scales[left] += abs(flow)
            if right is not None:
                residual[right] -= flow
                scales[right] += abs(flow)
            flows.append(flow)
        if any(not math.isfinite(value) for value in [*residual, *scales, *flows]):
            raise ValueError("Thermal heat balance exceeds the finite numerical range.")
        error = max(abs(value) / scale for value, scale in zip(residual, scales))
        return residual, error, flows

    def solve(start: Sequence[float], inertia: Sequence[float], prior: Sequence[float]):
        nonlocal dense_work_used
        rises = list(start)
        for _ in range(120):
            residual, error, flows = evaluate(rises, inertia, prior)
            if error <= 1e-10:
                return rises, residual, flows
            jacobian = [row[:] for row in matrix]
            for i, value in enumerate(inertia):
                jacobian[i][i] += value
            for left, _, coefficient, _, radiation in branches:
                if radiation:
                    # A 1 K seed avoids a zero derivative at absolute zero.
                    kelvin = max(1.0, rises[left] + ambient + 273.15)
                    jacobian[left][left] += 4 * coefficient * kelvin ** 3
            if dense_work_used + dense_solve_work > MAX_SURFACE_DENSE_WORK:
                raise ValueError(work_limit_message)
            dense_work_used += dense_solve_work
            direction = _solve_linear(jacobian, [-value for value in residual])
            if any(not math.isfinite(value) for value in direction):
                raise ValueError("Thermal Newton update exceeds the finite numerical range.")
            fraction = 1.0
            for _ in range(80):
                candidate = [value + fraction * delta for value, delta in zip(rises, direction)]
                if all(math.isfinite(value) and value + ambient >= -273.15 for value in candidate):
                    try:
                        _, next_error, _ = evaluate(candidate, inertia, prior)
                    except (ValueError, OverflowError):
                        next_error = math.inf
                    if next_error <= 1e-10 or next_error < error:
                        rises = candidate
                        break
                fraction *= 0.5
            else:
                raise ValueError("Thermal heat balance failed to converge; review path scales and boundary temperatures.")
        raise ValueError("Thermal heat balance exceeded its 120-iteration convergence limit.")

    initial = [float(element.get("initial_temperature_c", ambient)) - ambient for element in scenario.thermal_elements]
    zeros = [0.0] * len(ids)
    steady, steady_residual, flows = solve(initial, zeros, zeros)
    frames = []
    transient_residual = 0.0
    if scenario.mode == "transient":
        dt = end / steps
        inertia = [float(element["thermal_capacitance_j_per_c"]) / dt for element in scenario.thermal_elements]
        prior = initial
        for step in range(steps + 1):
            if step:
                prior, residual, _ = solve(prior, inertia, prior)
                transient_residual = max(transient_residual, max(abs(value) for value in residual))
            frames.append({"time_s": min(end, step * dt), "temperatures_c": {identifier: ambient + prior[i] for i, identifier in enumerate(ids)}})
    temperatures = [ambient + value for value in steady]
    return {
        "contract": "spike/thermal-result/v1", "scenario_id": scenario.scenario_id,
        "status": "completed", "model_status": "approximate", "mode": scenario.mode,
        "ambient_temperature_c": ambient,
        "nodes": [{"id": identifier, "power_w": powers[i], "temperature_rise_c": steady[i], "steady_temperature_c": temperatures[i]} for i, identifier in enumerate(ids)],
        "links": [{"id": link_id, "from_id": left, "to_id": right or "ambient", "conductance_w_per_k": conductance, "heat_flow_w": flows[i]}
                  for i, (left, right, conductance, link_id) in enumerate(legacy)],
        "surfaces": [dict(item, heat_flow_w=flows[len(legacy) + i]) for i, item in enumerate(surfaces)],
        "transient": frames,
        "summary": {"node_count": len(ids), "link_count": len(branches), "total_power_w": sum(powers),
                    "max_steady_temperature_c": max(temperatures), "steady_energy_balance_error_w": sum(steady_residual),
                    "max_node_energy_balance_error_w": max(abs(value) for value in steady_residual),
                    "max_transient_energy_balance_error_w": transient_residual},
        "issues": [],
        "provenance": {"engine": "spike-lumped-thermal-network", "method": "damped Newton heat balance; backward-Euler transient integration",
                       "qualification": "engineering_precheck_only", "radiation_model": "gray body to fixed large surroundings, view factor one",
                       "dense_work_units": dense_work_used, "dense_work_limit": MAX_SURFACE_DENSE_WORK,
                       "stefan_boltzmann_w_m2_k4": sigma, "relative_heat_balance_tolerance": 1e-10},
    }


__all__ = ["MAX_NETWORK_NODES", "MAX_TRANSIENT_STEPS", "estimate_lumped_thermal_network", "estimate_surface_thermal_network"]
