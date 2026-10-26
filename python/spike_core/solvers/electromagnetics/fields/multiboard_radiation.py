# SPDX-License-Identifier: Apache-2.0
"""Bounded diffuse-gray radiosity coupled to explicit board RC nodes.

Independently derived from surface emission/reflection and nodal heat balance.
View factors are supplied, never inferred from board placement or separation.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from ...thermal_fluid.heat.thermal_network import _network_links, _solve_linear
from ...thermal_fluid.heat.multiboard_thermal_scope import thermal_endpoint, thermal_node_id

SIGMA = 5.670374419e-8  # W/(m^2 K^4), SI Stefan-Boltzmann constant.
MAX_SURFACES = 64
MAX_NEWTON_ITERATIONS = 80
MAX_WORK = 50_000_000
RELATIVE_TOLERANCE = 1e-10


def _finite(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"{label} must be a finite {'positive ' if positive else ''}number.")
    return float(value)


class RadiationExchange:
    """Solve radiosity exactly for current uniform node temperatures."""
    def __init__(self, raw: Any, node_ids: list[str]):
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_SURFACES or any(not isinstance(s, Mapping) for s in raw):
            raise ValueError(f"radiation_surfaces requires 1..{MAX_SURFACES} objects.")
        self.surfaces = [dict(surface) for surface in raw]
        self.ids = [s.get("id") for s in raw]
        if any(not isinstance(i, str) or not i.strip() or len(i) > 256 or i == "ambient" for i in self.ids) or len(set(self.ids)) != len(raw):
            raise ValueError("Radiation surface IDs must be unique nonempty strings and cannot be ambient.")
        self.area, self.emissivity, self.nodes, self.factors, self.ambient = [], [], [], [], []
        for surface in raw:
            kind, owner, node = thermal_endpoint(surface)
            if set(surface) != {"id", kind, "node", "area_mm2", "emissivity", "view_factors"}:
                raise ValueError("Radiation surface fields must be id, board_id or part_id, node, area_mm2, emissivity, view_factors.")
            encoded = thermal_node_id(kind, owner, node)
            if encoded not in node_ids:
                raise ValueError("Radiation surface references an unknown board/part occurrence or node.")
            self.nodes.append(node_ids.index(encoded))
            self.area.append(_finite(surface["area_mm2"], "area_mm2", positive=True) * 1e-6)
            emissivity = _finite(surface["emissivity"], "emissivity", positive=True)
            if emissivity > 1:
                raise ValueError("emissivity must be >0 and <=1; ideal mirrors are unsupported.")
            self.emissivity.append(emissivity)
            factors = surface["view_factors"]
            if not isinstance(factors, Mapping) or set(factors) - {*self.ids, "ambient"}:
                raise ValueError("View factors must reference defined surfaces or ambient.")
            values = {key: _finite(value, "view factor") for key, value in factors.items()}
            if any(value < 0 or value > 1 for value in values.values()) or abs(sum(values.values()) - 1) > 1e-10:
                raise ValueError("Each nonnegative view-factor row must close to one within 1e-10; ambient fraction must be explicit.")
            self.factors.append([values.get(identifier, 0.) for identifier in self.ids])
            self.ambient.append(values.get("ambient", 0.))
        for i in range(len(raw)):
            for j in range(i):
                a, b = self.area[i] * self.factors[i][j], self.area[j] * self.factors[j][i]
                if abs(a - b) > 1e-10 * max(self.area[i], self.area[j]):
                    raise ValueError("Radiation view factors must obey area reciprocity Ai*Fij=Aj*Fji.")
        self.matrix = [[float(i == j) - (1 - self.emissivity[i]) * self.factors[i][j]
                        for j in range(len(raw))] for i in range(len(raw))]
        # Invert the bounded radiosity matrix once with the existing pivot kernel.
        columns = [_solve_linear(self.matrix, [float(i == j) for i in range(len(raw))]) for j in range(len(raw))]
        self.inverse = [[columns[j][i] for j in range(len(raw))] for i in range(len(raw))]

    def evaluate(self, temperatures_c: list[float], ambient_c: float):
        kelvin = [temperature + 273.15 for temperature in temperatures_c]
        ambient_kelvin = ambient_c + 273.15
        if any(not math.isfinite(t) or t < 0 for t in [*kelvin, ambient_kelvin]):
            raise ValueError("Radiation temperatures must be finite and >= absolute zero.")
        ambient_j = SIGMA * ambient_kelvin ** 4
        rhs = [e * SIGMA * kelvin[node] ** 4 + (1 - e) * f * ambient_j
               for e, node, f in zip(self.emissivity, self.nodes, self.ambient)]
        radiosity = [sum(coefficient * value for coefficient, value in zip(row, rhs)) for row in self.inverse]
        heat = [area * (radiosity[i] - sum(f * j for f, j in zip(self.factors[i], radiosity)) - self.ambient[i] * ambient_j)
                for i, area in enumerate(self.area)]
        n = len(temperatures_c)
        node_heat = [0.] * n
        jacobian = [[0.] * n for _ in range(n)]
        # dJ/dT = A^-1 diag(e sigma 4T^3), accumulated for surfaces on each node.
        derivatives = [[0.] * n for _ in self.ids]
        for i in range(len(self.ids)):
            for j, node in enumerate(self.nodes):
                derivatives[i][node] += self.inverse[i][j] * self.emissivity[j] * 4 * SIGMA * kelvin[node] ** 3
        for i, node in enumerate(self.nodes):
            node_heat[node] += heat[i]
            for column in range(n):
                jacobian[node][column] += self.area[i] * (derivatives[i][column] - sum(f * derivatives[j][column] for j, f in enumerate(self.factors[i])))
        ambient_heat = sum(area * f * (j - ambient_j) for area, f, j in zip(self.area, self.ambient, radiosity))
        if any(not math.isfinite(value) for value in [*radiosity, *heat, ambient_heat, *node_heat]):
            raise ValueError("Radiation exceeds finite numerical range.")
        exchange = [{"surface_a": self.ids[i], "surface_b": self.ids[j],
                     "heat_flow_w": self.area[i] * self.factors[i][j] * (radiosity[i] - radiosity[j])}
                    for i in range(len(self.ids)) for j in range(i + 1, len(self.ids)) if self.factors[i][j] > 0]
        return {"node_heat_w": node_heat, "jacobian": jacobian, "ambient_heat_flow_w": ambient_heat,
                "surface_heat_w": heat, "radiosity_w_per_m2": radiosity, "exchanges": exchange,
                "closure_residual_w": sum(heat) - ambient_heat}


def radiative_ambient_nodes(scenario, radiation):
    """Reachability using only supplied passive conduction and radiation paths."""
    ids = [element["id"] for element in scenario.thermal_elements]
    adjacency = {identifier: set() for identifier in ids}
    links, _ = _network_links(scenario, set(ids))
    reachable = {left for left, right, _, _ in links if right is None}
    for left, right, _, _ in links:
        if right is not None:
            adjacency[left].add(right)
            adjacency[right].add(left)
    for i, node in enumerate(radiation.nodes):
        if radiation.ambient[i] > 0:
            reachable.add(ids[node])
        for j, factor in enumerate(radiation.factors[i]):
            if factor > 0:
                adjacency[ids[node]].add(ids[radiation.nodes[j]])
    frontier = list(reachable)
    while frontier:
        for neighbor in adjacency[frontier.pop()] - reachable:
            reachable.add(neighbor)
            frontier.append(neighbor)
    return reachable


def estimate_radiative_board_network(scenario, surfaces):
    """Damped Newton heat balance and backward Euler with reciprocal radiosity."""
    ids = [e["id"] for e in scenario.thermal_elements]
    positions = {identifier: i for i, identifier in enumerate(ids)}
    radiation = RadiationExchange(surfaces, ids)
    links, issues = _network_links(scenario, set(ids))
    if issues:
        raise ValueError(issues[0]["message"])
    n = len(ids)
    powers = [e["power_w"] for e in scenario.thermal_elements]
    ambient = scenario.ambient_temperature_c
    matrix = [[0.] * n for _ in ids]
    for left, right, g, _ in links:
        i = positions[left]
        matrix[i][i] += g
        if right is not None:
            j = positions[right]
            matrix[j][j] += g
            matrix[i][j] -= g
            matrix[j][i] -= g
    work = len(surfaces) ** 4
    iterations = []

    def evaluate(temperature, inertia, prior):
        rad = radiation.evaluate(temperature, ambient)
        residual = [sum(matrix[i][j] * (temperature[j] - ambient) for j in range(n)) + rad["node_heat_w"][i]
                    + inertia[i] * (temperature[i] - prior[i]) - powers[i] for i in range(n)]
        scale = [max(1., abs(powers[i]), abs(rad["node_heat_w"][i]), abs(inertia[i] * (temperature[i] - prior[i]))) for i in range(n)]
        error = max(abs(r) / s for r, s in zip(residual, scale))
        if not math.isfinite(error):
            raise ValueError("Thermal residual exceeds finite numerical range.")
        return residual, error, rad

    def solve(start, inertia, prior):
        nonlocal work
        temperature = list(start)
        for iteration in range(MAX_NEWTON_ITERATIONS):
            residual, error, rad = evaluate(temperature, inertia, prior)
            if error <= RELATIVE_TOLERANCE:
                iterations.append(iteration)
                return temperature, residual, rad
            work += n ** 3 + len(surfaces) ** 2 * n
            if work > MAX_WORK:
                raise ValueError("Radiative board solve exceeds dense work limit; reduce nodes, surfaces, or transient steps.")
            jacobian = [[matrix[i][j] + rad["jacobian"][i][j] + (inertia[i] if i == j else 0.) for j in range(n)] for i in range(n)]
            direction = _solve_linear(jacobian, [-r for r in residual])
            fraction = 1.
            for _ in range(80):
                candidate = [t + fraction * delta for t, delta in zip(temperature, direction)]
                try:
                    _, next_error, _ = evaluate(candidate, inertia, prior)
                except (ValueError, OverflowError):
                    next_error = math.inf
                if next_error < error or next_error <= RELATIVE_TOLERANCE:
                    temperature = candidate
                    break
                fraction *= .5
            else:
                raise ValueError("Radiative thermal Newton line search failed to converge.")
        raise ValueError("Radiative thermal Newton iteration limit exceeded.")

    initial = [float(e.get("initial_temperature_c", ambient)) for e in scenario.thermal_elements]
    zeros = [0.] * n
    steady, residual, rad = solve(initial, zeros, zeros)
    frames, transient_residual = [], 0.
    if scenario.mode == "transient":
        duration = scenario.run["end_time_s"]
        steps = max(1, math.ceil(duration / scenario.run["write_interval_s"]))
        if (n ** 3 + len(surfaces) ** 2 * n) * steps > MAX_WORK:
            raise ValueError("Radiative transient minimum work exceeds its work limit.")
        dt = duration / steps
        inertia = [e["thermal_capacitance_j_per_c"] / dt for e in scenario.thermal_elements]
        prior = initial
        for step in range(steps + 1):
            if step:
                prior, r, _ = solve(prior, inertia, prior)
                transient_residual = max(transient_residual, max(abs(value) for value in r))
            frames.append({"time_s": min(duration, step * dt), "temperatures_c": dict(zip(ids, prior))})
    final_rad = radiation.evaluate(list(frames[-1]["temperatures_c"].values()), ambient) if frames else rad
    return {"contract": "spike/thermal-result/v1", "scenario_id": scenario.scenario_id, "status": "completed", "model_status": "approximate",
        "mode": scenario.mode, "ambient_temperature_c": ambient,
        "nodes": [{"id": identifier, "power_w": powers[i], "steady_temperature_c": steady[i], "temperature_rise_c": steady[i] - ambient} for i, identifier in enumerate(ids)],
        "links": [{"id": identifier, "from_id": left, "to_id": right or "ambient", "conductance_w_per_k": g} for left, right, g, identifier in links],
        "transient": frames, "radiation_surfaces": [dict(s, steady_net_heat_flow_w=rad["surface_heat_w"][i], net_heat_flow_w=final_rad["surface_heat_w"][i], radiosity_w_per_m2=final_rad["radiosity_w_per_m2"][i]) for i, s in enumerate(surfaces)],
        "radiation_exchange": [dict(pair, steady_heat_flow_w=pair["heat_flow_w"], heat_flow_w=final_rad["exchanges"][i]["heat_flow_w"]) for i, pair in enumerate(rad["exchanges"])],
        "radiation_node_heat_w": dict(zip(ids, rad["node_heat_w"])),
        "summary": {"node_count": n, "link_count": len(links), "total_power_w": sum(powers), "max_steady_temperature_c": max(steady),
            "radiation_ambient_heat_flow_w": rad["ambient_heat_flow_w"], "radiation_closure_residual_w": rad["closure_residual_w"],
            "max_transient_energy_balance_error_w": transient_residual, "max_newton_iterations": max(iterations), "dense_work_units": work},
        "issues": [{"code": "MULTIBOARD_RADIATION_APPROXIMATE", "severity": "warning", "message": "Uniform opaque diffuse-gray surfaces with explicit view factors; no geometry extraction, airflow or spatial board field."}],
        "provenance": {"engine": "spike-multiboard-radiosity-rc", "method": "damped Newton and backward Euler; exact bounded radiosity solve", "qualification": "engineering_precheck_only",
            "stefan_boltzmann_w_m2_k4": SIGMA, "relative_heat_balance_tolerance": RELATIVE_TOLERANCE,
            "radiation_model": "reciprocal diffuse-gray exchange; fixed black ambient closure", "dense_work_limit": MAX_WORK}}
