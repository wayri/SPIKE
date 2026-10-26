"""User-level thermal scenario contract.

This is intentionally simpler than an OpenFOAM dictionary. SPIKE owns the
translation from engineering intent to solver-specific boundary conditions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math

from typing import Any, Dict, List

from .thermal_network import estimate_lumped_thermal_network


@dataclass
class ThermalScenario:
    contract: str = "spike/thermal/v1"
    scenario_id: str = ""
    name: str = "Natural convection board enclosure"
    mode: str = "steady_state"
    application_environment: str = "domestic"
    medium: str = "air"
    enclosure: str = "open"
    convection: str = "natural"
    bounding_volume_mm: Dict[str, float] = field(default_factory=lambda: {"x": 220.0, "y": 140.0, "z": 40.0})
    ambient_temperature_c: float = 25.0
    gravity: str = "-Z"
    heat_sources: List[Dict[str, Any]] = field(default_factory=list)
    thermal_elements: List[Dict[str, Any]] = field(default_factory=list)
    thermal_links: List[Dict[str, Any]] = field(default_factory=list)
    material_library: List[Dict[str, Any]] = field(default_factory=list)
    surface_finish_library: List[Dict[str, Any]] = field(default_factory=list)
    thermal_screening: List[Dict[str, Any]] = field(default_factory=list)
    assembly_issues: List[str] = field(default_factory=list)
    component_bonds: List[Dict[str, Any]] = field(default_factory=list)
    flow_channels: List[Dict[str, Any]] = field(default_factory=list)
    fans: List[Dict[str, Any]] = field(default_factory=list)
    openings: List[Dict[str, Any]] = field(default_factory=list)
    virtual_heatsinks: List[Dict[str, Any]] = field(default_factory=list)
    cabinet: Dict[str, Any] = field(default_factory=dict)
    potting: Dict[str, Any] = field(default_factory=dict)
    materials: Dict[str, Any] = field(default_factory=lambda: {"air": "standard-air", "board": "FR4-copper"})
    mesh: Dict[str, Any] = field(default_factory=lambda: {"cell_size_mm": 2.0, "max_cells": 1000000})
    run: Dict[str, Any] = field(default_factory=lambda: {"end_time_s": 60.0, "write_interval_s": 1.0, "max_iterations": 2000, "residual_target": 1e-6})
    solver: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=lambda: {"radiation": False, "turbulence": "auto"})
    # Bounded presentation data may be persisted beside the scenario by the
    # desktop. It is never solver input and is excluded from case digests.
    field_result: Dict[str, Any] | None = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value.pop("field_result", None)
        return value


def validate_scenario(scenario: ThermalScenario) -> Dict[str, Any]:
    issues = []
    # Compact thermal estimates do not need spatial source locations.  CFD case
    # generation does, so retain those diagnostics separately from validity.
    case_issues = []
    volume = scenario.bounding_volume_mm
    if any(float(volume.get(axis, 0)) <= 0 for axis in ("x", "y", "z")):
        issues.append({"code": "THERMAL_VOLUME_INVALID", "severity": "error", "message": "Bounding volume dimensions must be positive."})
    if scenario.mode not in {"steady_state", "transient", "conjugate_heat_transfer"}:
        issues.append({"code": "THERMAL_MODE_UNSUPPORTED", "severity": "error", "message": f"Unsupported thermal mode: {scenario.mode}."})
    if scenario.ambient_temperature_c < -273.15:
        issues.append({"code": "AMBIENT_TEMPERATURE_INVALID", "severity": "error", "message": "Ambient temperature is below absolute zero."})
    if scenario.application_environment not in {"domestic", "industrial", "marine", "aerospace", "custom"}:
        issues.append({"code": "APPLICATION_ENVIRONMENT_INVALID", "severity": "error", "message": f"Unsupported application environment: {scenario.application_environment}."})
    if scenario.medium not in {"air", "vacuum", "potting"}:
        issues.append({"code": "THERMAL_MEDIUM_INVALID", "severity": "error", "message": f"Unsupported thermal medium: {scenario.medium}."})
    if scenario.enclosure not in {"open", "sealed", "vented_cabinet"}:
        issues.append({"code": "ENCLOSURE_INVALID", "severity": "error", "message": f"Unsupported enclosure: {scenario.enclosure}."})
    if scenario.convection not in {"none", "natural", "forced"}:
        issues.append({"code": "CONVECTION_INVALID", "severity": "error", "message": f"Unsupported convection mode: {scenario.convection}."})
    if scenario.gravity not in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}:
        issues.append({"code": "THERMAL_GRAVITY_INVALID", "severity": "error", "message": "Gravity must be one of +X, -X, +Y, or -Y, +Z, -Z."})
    enabled_fans = [fan for fan in scenario.fans if bool(fan.get("enabled", True))]
    enabled_heatsinks = [heatsink for heatsink in scenario.virtual_heatsinks if bool(heatsink.get("enabled", True))]
    if scenario.medium == "vacuum" and (enabled_fans or scenario.flow_channels or scenario.convection != "none"):
        issues.append({"code": "VACUUM_CONVECTION_INVALID", "severity": "error", "message": "Vacuum scenarios cannot contain fans, airflow channels, or convection."})
    if scenario.medium == "potting" and float(scenario.potting.get("conductivity_w_mk", 0)) <= 0:
        issues.append({"code": "POTTING_MATERIAL_INCOMPLETE", "severity": "error", "message": "Potted scenarios require positive potting thermal conductivity."})
    if scenario.enclosure == "vented_cabinet" and not scenario.cabinet.get("airflow_direction"):
        issues.append({"code": "CABINET_AIRFLOW_INCOMPLETE", "severity": "error", "message": "A vented cabinet needs an airflow direction."})
    for fan in enabled_fans:
        if not fan.get("position") or not fan.get("direction"):
            issues.append({"code": "FAN_GEOMETRY_INCOMPLETE", "severity": "error", "message": "Each fan needs a position and direction."})
        elif len(fan.get("position", [])) != 3 or len(fan.get("direction", [])) != 3 or not all(math.isfinite(float(value)) for value in [*fan.get("position", []), *fan.get("direction", [])]):
            issues.append({"code": "FAN_GEOMETRY_INVALID", "severity": "error", "message": "Each fan position and direction must contain three finite coordinates."})
        elif math.sqrt(sum(float(value) ** 2 for value in fan.get("direction", []))) <= 1e-12:
            issues.append({"code": "FAN_DIRECTION_INVALID", "severity": "error", "message": "Each enabled fan needs a non-zero airflow direction."})
        # v1 scenarios predate explicit fan envelopes. Preserve their historical
        # defaults while rejecting zero or negative dimensions supplied by v2 UIs.
        if float(fan.get("diameter_mm", 80) or 0) <= 0 or float(fan.get("depth_mm", 25) or 0) <= 0:
            issues.append({"code": "FAN_DIMENSIONS_INVALID", "severity": "error", "message": "Each enabled fan needs positive diameter_mm and depth_mm."})
        if scenario.convection == "forced" and float(fan.get("flow_rate_m3_s", 0) or 0) <= 0:
            issues.append({"code": "FAN_FLOW_RATE_INVALID", "severity": "error", "message": "Forced convection fans need a positive flow_rate_m3_s."})
        if float(fan.get("static_pressure_pa", 0) or 0) < 0 or float(fan.get("rpm", 0) or 0) < 0:
            issues.append({"code": "FAN_OPERATING_POINT_INVALID", "severity": "error", "message": "Fan static pressure and RPM must be non-negative."})
    for channel in scenario.flow_channels:
        if len(channel.get("path", [])) < 2:
            issues.append({"code": "FLOW_CHANNEL_PATH_INCOMPLETE", "severity": "error", "message": "Each flow channel needs at least two path points."})
        if float(channel.get("width_mm", 0) or 0) <= 0 or float(channel.get("height_mm", 0) or 0) <= 0:
            issues.append({"code": "FLOW_CHANNEL_DIMENSIONS_INVALID", "severity": "error", "message": "Each flow channel needs positive width_mm and height_mm."})
    for heatsink in enabled_heatsinks:
        dimensions = heatsink.get("dimensions_mm", {})
        if any(float(dimensions.get(axis, 0)) <= 0 for axis in ("x", "y", "z")):
            issues.append({"code": "HEATSINK_GEOMETRY_INCOMPLETE", "severity": "error", "message": "Each virtual heatsink needs positive X/Y/Z dimensions."})
        target = str(heatsink.get("target") or "")
        if target != "board-total" and target not in {str(element.get("id") or "") for element in scenario.thermal_elements}:
            issues.append({"code": "HEATSINK_TARGET_INVALID", "severity": "error", "message": f"Heatsink target {target or '<blank>'} does not resolve to the board or a thermal element."})
        if float(heatsink.get("interface_resistance_c_per_w", 0) or 0) < 0:
            issues.append({"code": "HEATSINK_INTERFACE_INVALID", "severity": "error", "message": "Heatsink interface resistance must be non-negative."})
        if int(heatsink.get("fin_count", 0) or 0) < 0 or float(heatsink.get("fin_thickness_mm", 0) or 0) <= 0 or float(heatsink.get("fin_height_mm", 0) or 0) < 0:
            issues.append({"code": "HEATSINK_FIN_GEOMETRY_INVALID", "severity": "error", "message": "Heatsink fin count and height must be non-negative and fin thickness must be positive."})
    if not scenario.heat_sources:
        issues.append({"code": "HEAT_SOURCE_MISSING", "severity": "warning", "message": "No heat sources are defined; the thermal field will remain ambient."})
    for index, source in enumerate(scenario.heat_sources):
        source_id = str(source.get("id") or f"heat-source-{index + 1}")
        position = source.get("position")
        if not isinstance(position, list) or len(position) != 3:
            case_issues.append({"code": "HEAT_SOURCE_POSITION_INVALID", "severity": "error", "message": f"{source_id} needs a three-coordinate position in mm before CFD case preparation."})
        elif not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in position):
            case_issues.append({"code": "HEAT_SOURCE_POSITION_INVALID", "severity": "error", "message": f"{source_id} position must contain finite numeric values before CFD case preparation."})
        elif all(isinstance(volume.get(axis), (int, float)) and math.isfinite(float(volume[axis])) and float(volume[axis]) > 0 for axis in ("x", "y", "z")):
            outside_axes = [
                axis
                for axis, coordinate in zip(("x", "y", "z"), position)
                if float(coordinate) < 0 or float(coordinate) > float(volume[axis])
            ]
            if outside_axes:
                case_issues.append({
                    "code": "HEAT_SOURCE_OUTSIDE_VOLUME",
                    "severity": "error",
                    "message": f"{source_id} lies outside the CFD bounding volume on: {', '.join(outside_axes)}.",
                })
        if float(source.get("power_w", 0) or 0) < 0:
            issues.append({"code": "HEAT_SOURCE_POWER_INVALID", "severity": "error", "message": f"{source_id} power_w must be non-negative."})
    for index, bond in enumerate(scenario.component_bonds):
        if not bool(bond.get("enabled", True)):
            continue
        path = f"component_bonds[{index}]"
        if not bond.get("component_ref") or not bond.get("pad_id") or not bond.get("connected_layers"):
            issues.append({"code": "THERMAL_COMPONENT_BOND_INCOMPLETE", "severity": "error", "message": f"{path} must resolve a component, pad, and connected copper layer."})
        thermal = bond.get("thermal", {})
        if float(thermal.get("conductivity_w_mk", 0) or 0) <= 0 or float(thermal.get("contact_area_mm2", 0) or 0) <= 0:
            issues.append({"code": "THERMAL_COMPONENT_BOND_PROPERTIES_INVALID", "severity": "error", "message": f"{path} needs positive conductivity and contact area."})
    element_ids = set()
    material_ids = {str(material.get("id", "")) for material in scenario.material_library}
    for index, element in enumerate(scenario.thermal_elements):
        element_id = str(element.get("id") or "")
        reference = str(element.get("reference") or element_id or f"thermal_elements[{index}]")
        if not element_id or element_id in element_ids:
            issues.append({"code": "THERMAL_ELEMENT_ID_INVALID", "severity": "error", "message": f"{reference} needs a unique thermal element ID."})
        element_ids.add(element_id)
        if float(element.get("power_w", 0) or 0) < 0:
            issues.append({"code": "THERMAL_ELEMENT_POWER_INVALID", "severity": "error", "message": f"{reference} dissipation must be non-negative."})
        emissivity = float(element.get("emissivity", 0) or 0)
        if emissivity < 0 or emissivity > 1:
            issues.append({"code": "THERMAL_ELEMENT_EMISSIVITY_INVALID", "severity": "error", "message": f"{reference} emissivity must be between 0 and 1."})
        dimensions = element.get("dimensions_mm", {})
        if any(float(dimensions.get(axis, 0) or 0) <= 0 for axis in ("x", "y", "z")):
            issues.append({"code": "THERMAL_ELEMENT_GEOMETRY_INVALID", "severity": "error", "message": f"{reference} needs positive X/Y/Z dimensions."})
        material_id = str(element.get("material_id") or "")
        if material_id and material_ids and material_id not in material_ids:
            issues.append({"code": "THERMAL_ELEMENT_MATERIAL_UNKNOWN", "severity": "error", "message": f"{reference} references unknown material {material_id}."})
    for index, link in enumerate(scenario.thermal_links):
        if not bool(link.get("enabled", True)):
            continue
        link_id = str(link.get("id") or f"thermal_links[{index}]")
        source_id = str(link.get("from_id") or "")
        target_id = str(link.get("to_id") or "")
        ambient_endpoints = (source_id == "ambient") + (target_id == "ambient")
        if ambient_endpoints == 1:
            non_ambient = target_id if source_id == "ambient" else source_id
            valid_endpoints = non_ambient in element_ids
        else:
            valid_endpoints = source_id in element_ids and target_id in element_ids and source_id != target_id
        if not valid_endpoints:
            issues.append({"code": "THERMAL_LINK_ENDPOINT_INVALID", "severity": "error", "message": f"{link_id} must connect two different existing thermal elements or one element to ambient."})
        resistance = float(link.get("resistance_c_per_w", 0) or 0)
        conductance = float(link.get("conductance_w_per_k", 0) or 0)
        conductivity = float(link.get("conductivity_w_mk", link.get("thermal_conductivity_w_mk", 0)) or 0)
        contact_area = float(link.get("contact_area_mm2", 0) or 0)
        thickness = float(link.get("thickness_mm", 0) or 0)
        has_geometry = conductivity > 0 and contact_area > 0 and thickness > 0
        if resistance <= 0 and conductance <= 0 and not has_geometry:
            issues.append({"code": "THERMAL_LINK_PROPERTIES_INVALID", "severity": "error", "message": f"{link_id} needs positive resistance, conductance, or conductivity/contact-area/thickness."})
    try:
        mesh_cell_size = float(scenario.mesh.get("cell_size_mm", 0) or 0)
        mesh_max_cells = int(scenario.mesh.get("max_cells", 0) or 0)
    except (TypeError, ValueError):
        mesh_cell_size = 0.0
        mesh_max_cells = 0
    if not math.isfinite(mesh_cell_size) or mesh_cell_size <= 0 or mesh_max_cells <= 0:
        issues.append({"code": "THERMAL_MESH_INVALID", "severity": "error", "message": "mesh.cell_size_mm and mesh.max_cells must be positive."})
    elif all(isinstance(volume.get(axis), (int, float)) and math.isfinite(float(volume[axis])) and float(volume[axis]) > 0 for axis in ("x", "y", "z")):
        cells = math.prod(max(1, math.ceil(float(volume[axis]) / mesh_cell_size)) for axis in ("x", "y", "z"))
        if cells > mesh_max_cells:
            issues.append({"code": "THERMAL_MESH_CELL_LIMIT_EXCEEDED", "severity": "error", "message": f"Requested bounding volume and cell size require {cells} cells, exceeding mesh.max_cells ({mesh_max_cells})."})
    try:
        end_time_s = float(scenario.run.get("end_time_s", 0) or 0)
        write_interval_s = float(scenario.run.get("write_interval_s", 0) or 0)
        max_iterations = int(scenario.run.get("max_iterations", 0) or 0)
        residual_target = float(scenario.run.get("residual_target", 0) or 0)
    except (TypeError, ValueError):
        end_time_s = write_interval_s = residual_target = 0.0
        max_iterations = 0
    if not all(math.isfinite(value) and value > 0 for value in (end_time_s, write_interval_s, residual_target)) or max_iterations <= 0:
        issues.append({"code": "THERMAL_RUN_CONTROL_INVALID", "severity": "error", "message": "Run time, write interval, iteration ceiling, and residual target must be positive."})
    if scenario.convection == "forced" and not enabled_fans and not scenario.flow_channels:
        issues.append({"code": "FORCED_CONVECTION_DRIVER_MISSING", "severity": "error", "message": "Forced convection requires at least one fan or flow channel."})
    requested_models = [name for name, requested in {
        "vacuum_radiation": scenario.medium == "vacuum",
        "potting_conjugate_conduction": scenario.medium == "potting",
        "cabinet_boundary_model": scenario.enclosure != "open",
        "virtual_heatsink_geometry": bool(enabled_heatsinks),
        "surface_to_surface_radiation": bool(scenario.options.get("radiation", False)),
        "solid_thermal_elements_and_contacts": bool(scenario.thermal_elements or scenario.thermal_links),
    }.items() if requested]
    # This is deliberately narrower than a PCB conjugate heat-transfer model.
    # A generated OpenFOAM case has not established numerical validation.
    case_generation_ready = (
        not any(issue["severity"] == "error" for issue in issues)
        and not any(issue["severity"] == "error" for issue in case_issues)
        and scenario.mode == "steady_state"
        and scenario.medium == "air"
        and scenario.enclosure == "open"
        and scenario.convection in {"natural", "forced"}
        and not bool(scenario.options.get("radiation", False))
        and not enabled_heatsinks
        and not scenario.component_bonds
        and not scenario.thermal_elements
        and not scenario.thermal_links
    )
    capability = {
        "status": "experimental_case_ready" if case_generation_ready else "unsupported",
        "implemented_physics": ["scenario_validation", "single_region_air_case_generation"],
        "requested_but_unimplemented": requested_models or ([] if case_generation_ready else ["open_air_conjugate_heat_transfer"]),
        "reason": (
            "A deterministic single-region air-convection OpenFOAM case can be generated, but it is not externally validated and does not model PCB solids or component bonds."
            if case_generation_ready else
            "The requested physics needs a validated multi-region mesh and OpenFOAM dictionary generator."
        ),
        "case_generation_ready": case_generation_ready,
        "execution_requires": ["native Linux or fixed-argv WSL OpenFOAM runtime", "reviewed generated case", "explicit experimental execution enablement"],
    }
    return {
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "solver_ready": False,
        "issues": issues,
        "case_issues": case_issues,
        "capability": capability,
    }


def estimate_compact_thermal(scenario: ThermalScenario) -> Dict[str, Any]:
    """Estimate source temperatures from explicit lumped thermal parameters.

    This is an inspectable first-order RC network, not a CFD or board-spreading
    solver. Environment choices are recorded but do not silently alter a
    user-supplied theta value.
    """
    validation = validate_scenario(scenario)
    if scenario.thermal_elements:
        # Explicit elements and links are a different model from independent
        # theta-JA sources.  Dispatch only when the user supplied that topology.
        return estimate_lumped_thermal_network(scenario, inherited_issues=validation["issues"])
    issues = list(validation["issues"])
    sources = []
    for index, source in enumerate(scenario.heat_sources):
        source_id = str(source.get("id") or f"heat-source-{index + 1}")
        power_w = float(source.get("power_w", 0))
        theta_c_per_w = float(source.get("theta_ja_c_per_w", 0))
        capacitance_j_per_c = float(source.get("thermal_capacitance_j_per_c", 0))
        if power_w < 0:
            issues.append({"code": "HEAT_SOURCE_POWER_INVALID", "severity": "error", "message": f"{source_id} power must be non-negative."})
        if theta_c_per_w <= 0:
            issues.append({"code": "THERMAL_RESISTANCE_REQUIRED", "severity": "error", "message": f"{source_id} needs a positive theta_ja_c_per_w for compact estimation."})
        if scenario.mode == "transient" and capacitance_j_per_c <= 0:
            issues.append({"code": "THERMAL_CAPACITANCE_REQUIRED", "severity": "error", "message": f"{source_id} needs positive thermal_capacitance_j_per_c for transient estimation."})
        if power_w < 0 or theta_c_per_w <= 0 or (scenario.mode == "transient" and capacitance_j_per_c <= 0):
            continue

        temperature_rise_c = power_w * theta_c_per_w
        steady_temperature_c = scenario.ambient_temperature_c + temperature_rise_c
        source_result: Dict[str, Any] = {
            "id": source_id,
            "power_w": power_w,
            "theta_ja_c_per_w": theta_c_per_w,
            "temperature_rise_c": temperature_rise_c,
            "steady_temperature_c": steady_temperature_c,
        }
        if capacitance_j_per_c > 0:
            tau_s = theta_c_per_w * capacitance_j_per_c
            source_result["thermal_capacitance_j_per_c"] = capacitance_j_per_c
            source_result["time_constant_s"] = tau_s
            source_result["transient"] = [
                {
                    "time_s": tau_s * multiplier,
                    "temperature_c": scenario.ambient_temperature_c
                    + temperature_rise_c * (1.0 - math.exp(-multiplier)),
                }
                for multiplier in (0.0, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0)
            ]
        sources.append(source_result)

    blocked = any(issue["severity"] == "error" for issue in issues)
    total_power_w = sum(float(source.get("power_w", 0)) for source in sources)
    max_temperature_c = max((float(source["steady_temperature_c"]) for source in sources), default=scenario.ambient_temperature_c)
    return {
        "contract": "spike/thermal-result/v1",
        "scenario_id": scenario.scenario_id,
        "status": "blocked" if blocked else "completed",
        "model_status": "approximate" if not blocked else "failed",
        "mode": scenario.mode,
        "ambient_temperature_c": scenario.ambient_temperature_c,
        "summary": {
            "source_count": len(sources),
            "total_power_w": total_power_w,
            "max_steady_temperature_c": max_temperature_c,
        },
        "sources": sources,
        "issues": issues + ([{
            "code": "COMPACT_THERMAL_MODEL",
            "severity": "warning",
            "message": "First-order independent source RC estimates use supplied theta values; PCB spreading, source coupling, airflow, radiation, and enclosure fields are not solved.",
        }] if not blocked else []),
        "provenance": {
            "engine": "spike-compact-thermal-rc",
            "method": "T = Tambient + P * theta; transient uses a first-order RC step response",
            "environment_recorded": scenario.application_environment,
            "medium_recorded": scenario.medium,
            "convection_recorded": scenario.convection,
        },
    }
