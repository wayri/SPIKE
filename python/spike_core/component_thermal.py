# SPDX-License-Identifier: MIT
"""Component-table adapter for SPIKE's explicit thermal RC network kernel."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .thermal import ThermalScenario
from .thermal_network import MAX_NETWORK_NODES, MAX_TRANSIENT_STEPS, estimate_lumped_thermal_network, estimate_surface_thermal_network

MAX_COMPONENT_SAMPLES = 100_000
MAX_SURFACE_BOUNDARIES = 2048


def _number(value: Any, label: str, *, minimum: float = 0, strict: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number) or number < minimum or (strict and number == minimum):
        raise ValueError(f"{label} must be finite and {'greater than' if strict else 'at least'} {minimum}.")
    return number


def _admit_surfaces(request: Mapping[str, Any], refs: set[str], ambient: float) -> list[dict[str, Any]]:
    rows = request.get("surfaces", [])
    if not isinstance(rows, list) or len(rows) > MAX_SURFACE_BOUNDARIES:
        raise ValueError(f"surfaces must be a list of at most {MAX_SURFACE_BOUNDARIES} boundaries.")
    surfaces, ids = [], set()
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError("Each surface boundary must be an object.")
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("Surface enabled must be a boolean.")
        if not enabled:
            continue
        identifier = str(raw.get("id", "")).strip()
        ref = str(raw.get("object_ref", "")).strip()
        surface = str(raw.get("surface", "whole")).strip()
        kind = raw.get("kind")
        if not identifier or len(identifier) > 128 or identifier in ids:
            raise ValueError("Surface boundaries need unique IDs of 1 to 128 characters.")
        ids.add(identifier)
        if ref not in refs or not surface or len(surface) > 128:
            raise ValueError(f"{identifier} needs an included object_ref and a surface name of 1 to 128 characters.")
        if kind not in {"conduction", "convection", "radiation"}:
            raise ValueError(f"{identifier} has an unsupported heat transfer kind.")
        item = {"id": identifier, "object_ref": ref, "surface": surface, "kind": kind, "enabled": True}
        if kind == "conduction":
            target = str(raw.get("target_ref", "ambient"))
            if target != "ambient" and (target not in refs or target == ref):
                raise ValueError(f"{identifier} conduction target must be ambient or another included object.")
            item.update(target_ref=target, resistance_c_per_w=_number(raw.get("resistance_c_per_w"), f"{identifier} resistance (K/W)", strict=True))
            if not math.isfinite(1 / item["resistance_c_per_w"]):
                raise ValueError(f"{identifier} resistance is too small.")
        else:
            item["area_mm2"] = _number(raw.get("area_mm2"), f"{identifier} area (mm2)", strict=True)
            if kind == "convection":
                item["heat_transfer_coefficient_w_m2_k"] = _number(raw.get("heat_transfer_coefficient_w_m2_k"), f"{identifier} heat transfer coefficient (W/m2/K)", strict=True)
            else:
                item["emissivity"] = _number(raw.get("emissivity"), f"{identifier} emissivity", strict=True)
                if item["emissivity"] > 1:
                    raise ValueError(f"{identifier} emissivity must not exceed 1.")
        if kind == "radiation":
            key = "surroundings_temperature_c"
        else:
            key = "ambient_temperature_c"
        if kind != "conduction" or item["target_ref"] == "ambient":
            item[key] = _number(raw.get(key, ambient), f"{identifier} sink temperature (C)", minimum=-273.15)
        surfaces.append(item)
    return surfaces


def _admit(request: Mapping[str, Any]) -> tuple[ThermalScenario, list[dict[str, Any]], list[dict[str, Any]]]:
    raw_scenario = request.get("scenario", {})
    if not isinstance(raw_scenario, Mapping):
        raise ValueError("scenario must be an object.")
    mode = raw_scenario.get("mode", "steady_state")
    if mode not in {"steady_state", "transient"}:
        raise ValueError("Component thermal mode must be steady_state or transient.")
    ambient = _number(raw_scenario.get("ambient_temperature_c", 25), "Ambient temperature (C)", minimum=-273.15)
    rows = request.get("components")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_NETWORK_NODES:
        raise ValueError(f"Provide 1 to {MAX_NETWORK_NODES} component rows.")
    run = raw_scenario.get("run", {})
    if not isinstance(run, Mapping):
        raise ValueError("scenario.run must be an object.")
    end = _number(run.get("end_time_s", 60), "Duration (s)", strict=True)
    interval = _number(run.get("write_interval_s", 1), "Time step (s)", strict=True)
    if mode == "transient":
        ratio = end / interval
        if not math.isfinite(ratio) or ratio > MAX_TRANSIENT_STEPS:
            raise ValueError(f"Transient duration/time step must not exceed {MAX_TRANSIENT_STEPS} steps.")
        steps = max(1, math.ceil(ratio))
        if (steps + 1) * len(rows) > MAX_COMPONENT_SAMPLES:
            raise ValueError(f"Transient output exceeds {MAX_COMPONENT_SAMPLES} component samples; increase the time step or reduce duration.")
    scenario = ThermalScenario(mode=mode, ambient_temperature_c=ambient, scenario_id=str(raw_scenario.get("scenario_id", "")))
    scenario.run.update(end_time_s=end, write_interval_s=interval)
    components = []
    seen = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Component row {index + 1} must be an object.")
        ref = str(raw.get("component_ref", "")).strip()
        if not ref or ref.casefold() == "ambient" or len(ref) > 128 or ref.casefold() in seen:
            raise ValueError(f"Component row {index + 1} needs a unique reference of 1 to 128 characters.")
        seen.add(ref.casefold())
        power = _number(raw.get("power_w"), f"{ref} dissipation (W)")
        node = {"id": ref, "power_w": power}
        component = {"component_ref": ref, "power_w": power}
        for side in ("top", "bottom"):
            key = f"resistance_{side}_c_per_w"
            if raw.get(key) in (None, ""):
                continue
            resistance = _number(raw[key], f"{ref} {side} resistance (K/W)", strict=True)
            if not math.isfinite(1.0 / resistance):
                raise ValueError(f"{ref} {side} resistance is too small for finite conductance.")
            component[key] = resistance
            scenario.thermal_links.append({"id": f"{ref}:{side}", "from_id": ref, "to_id": "ambient", "resistance_c_per_w": resistance})
        conductance = sum(1.0 / component[f"resistance_{side}_c_per_w"] for side in ("top", "bottom") if f"resistance_{side}_c_per_w" in component)
        if not math.isfinite(conductance):
            raise ValueError(f"{ref} combined conductance exceeds the finite numerical range.")
        capacitance = raw.get("thermal_capacitance_j_per_c")
        if capacitance not in (None, "") or mode == "transient":
            node["thermal_capacitance_j_per_c"] = _number(capacitance, f"{ref} heat capacity (J/K)", strict=True)
            component["thermal_capacitance_j_per_c"] = node["thermal_capacitance_j_per_c"]
        node["initial_temperature_c"] = _number(raw.get("initial_temperature_c", ambient), f"{ref} initial temperature (C)", minimum=-273.15)
        scenario.thermal_elements.append(node)
        components.append(component)
    surfaces = _admit_surfaces(request, {component["component_ref"] for component in components}, ambient)
    return scenario, components, surfaces


def run_component_thermal(request: Mapping[str, Any]) -> dict[str, Any]:
    """Run bounded steady/transient component paths without an external engine.

    Top and bottom values are *complete effective paths to ambient*, in K/W.
    They cannot be substituted by junction-to-case package data without the
    remainder of the case-to-ambient path. Missing sides are open circuits.
    """
    try:
        scenario, components, surfaces = _admit(request)
        result = estimate_surface_thermal_network(scenario, surfaces) if surfaces else estimate_lumped_thermal_network(scenario)
        if result["status"] != "completed":
            return result
        nodes = {node["id"]: node for node in result["nodes"]}
        for component in components:
            node = nodes[component["component_ref"]]
            node.update(component)
            rise = node["temperature_rise_c"]
            node["heat_flow_top_w"] = rise / component["resistance_top_c_per_w"] if "resistance_top_c_per_w" in component else 0.0
            node["heat_flow_bottom_w"] = rise / component["resistance_bottom_c_per_w"] if "resistance_bottom_c_per_w" in component else 0.0
            node["temperature_c"] = result["transient"][-1]["temperatures_c"][node["id"]] if result["transient"] else node["steady_temperature_c"]
            if not all(math.isfinite(node[key]) for key in ("temperature_rise_c", "steady_temperature_c", "temperature_c", "heat_flow_top_w", "heat_flow_bottom_w")):
                raise ValueError(f"{node['id']} parameters exceed the finite numerical range.")
        if any(not math.isfinite(value) for frame in result["transient"] for value in frame["temperatures_c"].values()):
            raise ValueError("Transient parameters exceed the finite numerical range.")
        result["summary"]["max_temperature_c"] = max(node["temperature_c"] for node in result["nodes"])
        if not surfaces:
            result["summary"]["steady_energy_balance_error_w"] = sum(node["heat_flow_top_w"] + node["heat_flow_bottom_w"] - node["power_w"] for node in result["nodes"])
        if any(not math.isfinite(value) for value in result["summary"].values()):
            raise ValueError("Component totals exceed the finite numerical range.")
        result["provenance"].update(
            adapter="spike-component-thermal/v1", solver_id="spike.lumped_thermal_network",
            resistance_interpretation="Complete independent top/bottom paths to the specified ambient; missing sides are adiabatic.",
            field_result_produced=False, production_qualified=False,
            inputs={"scenario": {"mode": scenario.mode, "ambient_temperature_c": scenario.ambient_temperature_c, "run": scenario.run},
                    "components": [dict(component, initial_temperature_c=element["initial_temperature_c"]) for component, element in zip(components, scenario.thermal_elements)], "surfaces": surfaces},
        )
        result["issues"].append({"code": "COMPONENT_THERMAL_PATH_ASSUMPTIONS", "severity": "warning", "message": "Top/bottom resistances are complete paths to ambient and add to explicit surface boundaries. Avoid overlapping paths. Each object has one temperature; surface labels do not create a spatial field. Constant power/properties, prescribed convection and radiation to fixed surroundings; no PCB spreading, airflow, or radiation view factors are computed."})
        return result
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
        return {"contract": "spike/thermal-result/v1", "status": "blocked", "model_status": "failed", "nodes": [], "transient": [], "summary": {},
                "issues": [{"code": "COMPONENT_THERMAL_INPUT_INVALID", "severity": "error", "message": str(exc)}],
                "provenance": {"engine": "spike-lumped-thermal-network", "qualification": "not_executed"}}
