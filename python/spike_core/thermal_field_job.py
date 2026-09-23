"""Fail-closed orchestration for field-thermal solver plugins.

The planner records requested physics and resource limits before a case adapter
is invoked.  It deliberately never fabricates field samples: a plan becomes
executable only when a selected, explicit plugin advertises every requested
capability and a qualified geometry handoff is present.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Callable, Dict, Iterable, Mapping


REQUEST_CONTRACT = "spike/thermal-field-job-request/v1"
PLAN_CONTRACT = "spike/thermal-field-job-plan/v1"
RESULT_CONTRACT = "spike/thermal-field-result/v1"
ADAPTER_RUN_CONTRACT = "spike/thermal-field-adapter-run/v1"
MAX_FIELD_CELLS = 50_000_000
MAX_OUTPUT_SAMPLES = 5_000_000
MAX_TOTAL_FIELD_SAMPLES = 50_000_000
MAX_MEMORY_MB = 1_048_576
MAX_CPU_SECONDS = 604_800


class ThermalFieldJobError(ValueError):
    """Raised for structurally malformed field-job requests."""


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _issue(code: str, message: str, *, severity: str = "error") -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ThermalFieldJobError("thermal field-job planning cancelled")


def _number(value: Any, label: str, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ThermalFieldJobError(f"{label} must be numeric.") from exc
    if not math.isfinite(result) or result < minimum or (maximum is not None and result > maximum):
        range_text = f"[{minimum}, {maximum}]" if maximum is not None else f">= {minimum}"
        raise ThermalFieldJobError(f"{label} must be finite and within {range_text}.")
    return result


def _requested_physics(scenario: Mapping[str, Any], requested: Iterable[str]) -> list[str]:
    explicit = {str(value) for value in requested}
    mode = str(scenario.get("mode", "steady_state"))
    options = scenario.get("options", {}) if isinstance(scenario.get("options", {}), Mapping) else {}
    present = {
        "solid_conduction",
        "transient_conduction" if mode == "transient" else "",
        "thermal_contacts" if scenario.get("thermal_links") or scenario.get("component_bonds") else "",
        "material_properties" if scenario.get("material_library") else "",
        "coatings" if scenario.get("surface_finish_library") else "",
        "component_heat_source_table" if scenario.get("heat_sources") else "",
        "enclosure" if str(scenario.get("enclosure", "open")) != "open" else "",
        "heatsinks" if scenario.get("virtual_heatsinks") else "",
        "fans" if scenario.get("fans") else "",
        "potting" if str(scenario.get("medium", "air")) == "potting" else "",
        "vacuum_radiation" if str(scenario.get("medium", "air")) == "vacuum" else "",
        "radiation" if bool(options.get("radiation", False)) else "",
        "airflow" if str(scenario.get("convection", "natural")) == "forced" or scenario.get("fans") or scenario.get("flow_channels") else "",
        "conjugate_heat_transfer" if mode == "conjugate_heat_transfer" else "",
        "electrothermal_iteration" if bool((scenario.get("electrothermal") or {}).get("enabled", False)) else "",
    }
    # Requested values are accepted only from the published vocabulary so a typo
    # cannot silently turn off a required physics gate.
    allowed = {
        "solid_conduction", "transient_conduction", "thermal_contacts", "material_properties", "coatings",
        "component_heat_source_table", "package_shapes", "mcad_parts", "enclosure", "heatsinks", "fans",
        "potting", "vacuum_radiation", "radiation", "airflow", "conjugate_heat_transfer", "electrothermal_iteration",
    }
    unknown = explicit - allowed
    if unknown:
        raise ThermalFieldJobError(f"Unknown requested thermal physics: {', '.join(sorted(unknown))}.")
    return sorted((present | explicit) - {""})


def _default_solver_catalog() -> Dict[str, Dict[str, Any]]:
    """Return only real, locally known descriptors; discovery is not readiness."""
    from .external_engines import external_engine_catalog
    from .openfoam import openfoam_capabilities
    from .solver_plugins import default_solver_registry

    entries = {item["id"]: dict(item) for item in default_solver_registry().catalog()}
    entries.update({item["id"]: dict(item) for item in external_engine_catalog().get("engines", [])})
    runtime = openfoam_capabilities()
    entries["external.openfoam"] = {
        **entries.get("external.openfoam", {}), "id": "external.openfoam", "name": "OpenFOAM",
        "state": "experimental" if runtime.get("execution_ready") else "unavailable",
        "model_status": "experimental" if runtime.get("execution_ready") else "unsupported",
        "execution": "fixed_argv_process", "actions": ["prepare", "run"] if runtime.get("execution_ready") else ["prepare"],
        # Existing adapter is intentionally single-region air only.
        "capabilities": ["airflow", "component_heat_source_table"],
        "reason": "The current OpenFOAM adapter has no multi-region solid/contact, radiation, or CHT qualification.",
    }
    entries["spike.lumped_thermal_network"] = {
        "id": "spike.lumped_thermal_network", "name": "SPIKE Lumped Thermal Network", "state": "available",
        "model_status": "approximate", "execution": "builtin", "actions": ["run"],
        "capabilities": ["solid_conduction", "transient_conduction", "thermal_contacts", "material_properties", "component_heat_source_table"],
        "reason": "Explicit resistance/capacitance engineering precheck only; it produces no geometry field.",
    }
    return entries


def _resource_plan(scenario: Mapping[str, Any], budget: Mapping[str, Any]) -> Dict[str, int]:
    volume = scenario.get("bounding_volume_mm", {})
    mesh = scenario.get("mesh", {})
    if not isinstance(volume, Mapping) or not isinstance(mesh, Mapping):
        raise ThermalFieldJobError("scenario bounding_volume_mm and mesh must be objects.")
    dimensions = [_number(volume.get(axis), f"bounding_volume_mm.{axis}", minimum=1e-12) for axis in ("x", "y", "z")]
    cell_size = _number(mesh.get("cell_size_mm"), "mesh.cell_size_mm", minimum=1e-12)
    requested_cells = math.prod(max(1, math.ceil(value / cell_size)) for value in dimensions)
    configured_max_cells = int(_number(budget.get("max_cells", mesh.get("max_cells", MAX_FIELD_CELLS)), "resource_budget.max_cells", minimum=1, maximum=MAX_FIELD_CELLS))
    max_samples = int(_number(budget.get("max_output_samples", 250_000), "resource_budget.max_output_samples", minimum=1, maximum=MAX_OUTPUT_SAMPLES))
    max_total_samples = int(_number(budget.get("max_total_field_samples", requested_cells), "resource_budget.max_total_field_samples", minimum=1, maximum=MAX_TOTAL_FIELD_SAMPLES))
    memory = int(_number(budget.get("memory_limit_mb", 4096), "resource_budget.memory_limit_mb", minimum=512, maximum=MAX_MEMORY_MB))
    cpu = int(_number(budget.get("cpu_time_limit_s", 3600), "resource_budget.cpu_time_limit_s", minimum=1, maximum=MAX_CPU_SECONDS))
    return {"requested_cells": requested_cells, "max_cells": configured_max_cells, "max_output_samples": max_samples, "max_total_field_samples": max_total_samples, "memory_limit_mb": memory, "cpu_time_limit_s": cpu}


def plan_thermal_field_job(
    request: Mapping[str, Any],
    *,
    solver_catalog: Mapping[str, Mapping[str, Any]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
    """Validate and plan one explicit thermal field-solver invocation.

    This is orchestration only. A `ready_for_execution` plan authorizes a later
    adapter to launch; it is never a field result or a qualification claim.
    """
    if not isinstance(request, Mapping) or request.get("contract") != REQUEST_CONTRACT:
        raise ThermalFieldJobError(f"Expected {REQUEST_CONTRACT}.")
    scenario = request.get("scenario")
    if not isinstance(scenario, Mapping):
        raise ThermalFieldJobError("A thermal field job requires a scenario object.")
    selection = request.get("solver_selection")
    if not isinstance(selection, Mapping) or not isinstance(selection.get("solver_id"), str) or not selection["solver_id"].strip() or selection["solver_id"] == "auto":
        raise ThermalFieldJobError("solver_selection.solver_id must be a concrete plugin ID; automatic fallback is forbidden.")
    geometry = request.get("geometry", {})
    if not isinstance(geometry, Mapping):
        raise ThermalFieldJobError("geometry must be an object.")
    budget = request.get("resource_budget", {})
    if not isinstance(budget, Mapping):
        raise ThermalFieldJobError("resource_budget must be an object.")
    _cancel(cancel_check)
    requested = _requested_physics(scenario, request.get("requested_physics", []))
    resources = _resource_plan(scenario, budget)
    _cancel(cancel_check)
    catalog = dict(solver_catalog) if solver_catalog is not None else _default_solver_catalog()
    solver_id = str(selection["solver_id"])
    solver = catalog.get(solver_id)
    issues: list[Dict[str, str]] = []
    if resources["requested_cells"] > resources["max_cells"]:
        issues.append(_issue("THERMAL_FIELD_CELL_BUDGET_EXCEEDED", f"The requested mesh has {resources['requested_cells']} cells, exceeding the approved {resources['max_cells']}-cell budget."))
    if not bool(request.get("cancellation_enabled", True)):
        issues.append(_issue("THERMAL_FIELD_CANCELLATION_REQUIRED", "Field jobs must enable cooperative cancellation before execution."))
    if not bool(geometry.get("qualified_geometry", False)):
        issues.append(_issue("THERMAL_FIELD_GEOMETRY_EVIDENCE_REQUIRED", "A field-thermal run requires a qualified geometry/mesh handoff; retained MCAD files alone are insufficient."))
    if "package_shapes" in requested and not geometry.get("assembly_shape_evidence_id"):
        issues.append(_issue("THERMAL_FIELD_PACKAGE_SHAPE_EVIDENCE_REQUIRED", "Package-shape thermal physics requires a resolved assembly-shape evidence ID."))
    if "mcad_parts" in requested and not geometry.get("mcad_geometry_evidence_id"):
        issues.append(_issue("THERMAL_FIELD_MCAD_EVIDENCE_REQUIRED", "MCAD thermal physics requires a tessellated/qualified MCAD geometry evidence ID."))
    if "thermal_contacts" in requested and not geometry.get("contact_evidence_id"):
        issues.append(_issue("THERMAL_FIELD_CONTACT_EVIDENCE_REQUIRED", "Field thermal contacts/bonds require resolved contact geometry evidence."))
    _cancel(cancel_check)
    qualification_summary: Dict[str, Any] = {
        "valid": False,
        "evidence_id": "",
        "covered_gates": [],
        "required_gates": [],
        "platforms": [],
        "issues": ["No solver qualification evidence was evaluated."],
    }
    if solver is None:
        issues.append(_issue("THERMAL_FIELD_SOLVER_UNKNOWN", f"Selected solver plugin {solver_id} is not catalogued."))
        selected = {"id": solver_id}
    else:
        selected = {key: solver.get(key) for key in ("id", "name", "version", "state", "model_status", "execution", "actions", "reason")}
        state = str(solver.get("state", "unavailable"))
        if state not in {"available", "experimental", "reference_validated", "validated"} or "run" not in solver.get("actions", []):
            issues.append(_issue("THERMAL_FIELD_SOLVER_NOT_EXECUTABLE", str(solver.get("reason") or f"Selected solver {solver_id} has state {state} and cannot run this job.")))
        missing = sorted(set(requested) - {str(item) for item in solver.get("capabilities", [])})
        if missing:
            issues.append(_issue("THERMAL_FIELD_SOLVER_CAPABILITY_MISSING", f"Selected solver {solver_id} does not declare: {', '.join(missing)}."))
        from .thermal_qualification import validate_thermal_qualification

        qualification_summary = validate_thermal_qualification(
            solver.get("qualification_evidence"),
            solver_id=solver_id,
            solver_version=str(solver.get("version") or ""),
            requested_physics=requested,
        )
        if str(solver.get("model_status", "unsupported")) not in {"validated", "reference_validated"} or not qualification_summary["valid"]:
            detail = "; ".join(qualification_summary["issues"])
            issues.append(_issue("THERMAL_FIELD_SOLVER_NOT_QUALIFIED", f"The selected solver has no complete field-thermal release qualification for this job. {detail}".strip()))
    status = "ready_for_execution" if not any(item["severity"] == "error" for item in issues) else "blocked"
    plan = {
        "contract": PLAN_CONTRACT, "job_id": str(request.get("job_id") or ""), "status": status,
        "result_contract": RESULT_CONTRACT, "requested_physics": requested, "solver_selection": selected,
        "scenario_digest": _canonical_digest(scenario),
        "geometry": {"qualified_geometry": bool(geometry.get("qualified_geometry", False)), "mesh_evidence_id": str(geometry.get("mesh_evidence_id") or ""), "contact_evidence_id": str(geometry.get("contact_evidence_id") or ""), "assembly_shape_evidence_id": str(geometry.get("assembly_shape_evidence_id") or ""), "mcad_geometry_evidence_id": str(geometry.get("mcad_geometry_evidence_id") or "")},
        "resource_budget": resources,
        "cancellation": {"required": True, "enabled": bool(request.get("cancellation_enabled", True)), "poll_points": ["before_geometry", "after_mesh_admission", "between_solver_iterations", "before_result_import"]},
        "execution": {"permitted": status == "ready_for_execution", "result_generation": "adapter_owned_no_synthetic_fields", "scope": "single admitted board/assembly scope supplied by caller"},
        "qualification": {
            "field_result_produced": False,
            "production_qualified": False,
            "solver_release_qualified": bool(qualification_summary["valid"]),
            "evidence_id": qualification_summary.get("evidence_id", ""),
            "required_gates": qualification_summary.get("required_gates", []),
            "covered_gates": qualification_summary.get("covered_gates", []),
            "platforms": qualification_summary.get("platforms", []),
            "reason": "Qualification evidence passed; field results still require runtime execution." if qualification_summary["valid"] else "The selected adapter has not passed the complete release qualification gate.",
        },
        "issues": issues,
    }
    plan["plan_digest"] = _canonical_digest({key: value for key, value in plan.items() if key != "plan_digest"})
    return plan


def _execution_result(plan: Mapping[str, Any], code: str, message: str, *, status: str = "blocked", probe: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """Return a normalized terminal response without accepting partial fields."""
    return {
        "contract": RESULT_CONTRACT, "job_id": str(plan.get("job_id") or ""), "plan_digest": str(plan.get("plan_digest") or ""),
        "status": status, "model_status": "unsupported" if status == "blocked" else "failed",
        "summary": {}, "fields": {}, "component_temperatures_k": {}, "resource_usage": {},
        "issues": [_issue(code, message)],
        "qualification": {"production_qualified": False, "field_result_produced": False, "reason": "No accepted field result was produced."},
        "provenance": {"solver_id": str(plan.get("solver_selection", {}).get("id") or ""), "plan_digest": str(plan.get("plan_digest") or ""), "runtime_probe": dict(probe or {})},
    }


def _adapter_method(adapter: Any, name: str) -> Callable[..., Any] | None:
    value = adapter.get(name) if isinstance(adapter, Mapping) else getattr(adapter, name, None)
    return value if callable(value) else None


def _field_artifact(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ThermalFieldJobError(f"Thermal plugin field {name} requires digest-bound artifact metadata when not all samples are previewed.")
    artifact_id = str(value.get("id") or "")
    digest = str(value.get("sha256") or "")
    contract = str(value.get("contract") or "")
    try:
        byte_count = int(value.get("bytes"))
    except (TypeError, ValueError) as exc:
        raise ThermalFieldJobError(f"Thermal plugin field {name} artifact bytes must be an integer.") from exc
    if not artifact_id or not contract or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest) or not 0 <= byte_count <= 1_073_741_824:
        raise ThermalFieldJobError(f"Thermal plugin field {name} artifact metadata is invalid.")
    return {"id": artifact_id, "sha256": digest, "bytes": byte_count, "contract": contract}


def _finite_field_samples(value: Any, name: str, *, vector: bool, maximum: int, max_total: int) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("samples"), list):
        raise ThermalFieldJobError(f"Thermal plugin result field {name} needs a samples array.")
    raw_samples = value["samples"]
    if not raw_samples or len(raw_samples) > maximum:
        raise ThermalFieldJobError(f"Thermal plugin result field {name} sample count exceeds the plan budget.")
    try:
        total_samples = int(value.get("total_samples", len(raw_samples)))
    except (TypeError, ValueError) as exc:
        raise ThermalFieldJobError(f"Thermal plugin result field {name} total_samples must be an integer.") from exc
    if total_samples < len(raw_samples) or total_samples > max_total:
        raise ThermalFieldJobError(f"Thermal plugin result field {name} total_samples is outside the plan budget.")
    normalized = []
    for index, sample in enumerate(raw_samples):
        if not isinstance(sample, Mapping):
            raise ThermalFieldJobError(f"Thermal plugin result field {name} sample {index} must be an object.")
        point = sample.get("point_mm")
        if not isinstance(point, list) or len(point) != 3:
            raise ThermalFieldJobError(f"Thermal plugin result field {name} sample {index} needs point_mm XYZ coordinates.")
        point_values = [_number(item, f"{name}.point_mm", minimum=-1e300, maximum=1e300) for item in point]
        raw_value = sample.get("value")
        if vector:
            if not isinstance(raw_value, list) or len(raw_value) != 3:
                raise ThermalFieldJobError(f"Thermal plugin result field {name} sample {index} needs a three-value vector.")
            result_value: Any = [_number(item, f"{name}.value", minimum=-1e300, maximum=1e300) for item in raw_value]
        else:
            result_value = _number(raw_value, f"{name}.value", minimum=-1e300, maximum=1e300)
        normalized.append({"point_mm": point_values, "value": result_value, "region": str(sample.get("region") or "unknown")})
    result: Dict[str, Any] = {"unit": str(value.get("unit") or ""), "samples": normalized, "preview_samples": len(normalized), "total_samples": total_samples}
    if total_samples > len(normalized):
        result["artifact"] = _field_artifact(value.get("artifact"), name)
    return result


def _normalize_adapter_result(plan: Mapping[str, Any], raw: Any, *, elapsed_s: float) -> Dict[str, Any]:
    if not isinstance(raw, Mapping) or raw.get("contract") != RESULT_CONTRACT:
        raise ThermalFieldJobError(f"Thermal plugin result must use {RESULT_CONTRACT}.")
    if raw.get("plan_digest") != plan.get("plan_digest"):
        raise ThermalFieldJobError("Thermal plugin result plan digest does not match the admitted job.")
    selected = plan["solver_selection"]
    provenance = raw.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("solver_id") != selected.get("id"):
        raise ThermalFieldJobError("Thermal plugin result solver identity does not match the selected plugin.")
    status = str(raw.get("status") or "")
    if status != "completed":
        raise ThermalFieldJobError(f"Thermal plugin returned terminal status {status or '<missing>'} without an accepted field result.")
    fields = raw.get("fields")
    if not isinstance(fields, Mapping):
        raise ThermalFieldJobError("Thermal plugin result needs a fields object.")
    maximum = int(plan["resource_budget"]["max_output_samples"])
    max_total = int(plan["resource_budget"]["max_total_field_samples"])
    temperature = _finite_field_samples(fields.get("temperature_k"), "temperature_k", vector=False, maximum=maximum, max_total=max_total)
    if temperature["unit"] != "K":
        raise ThermalFieldJobError("Thermal plugin temperature_k field must use kelvin (K).")
    normalized_fields: Dict[str, Any] = {"temperature_k": temperature}
    sample_count = int(temperature["preview_samples"])
    total_sample_count = int(temperature["total_samples"])
    for name, unit, vector in (("velocity_m_s", "m/s", True), ("heat_flux_w_m2", "W/m2", True), ("pressure_pa", "Pa", False)):
        if name not in fields:
            continue
        values = _finite_field_samples(fields[name], name, vector=vector, maximum=maximum - sample_count, max_total=max_total - total_sample_count)
        if values["unit"] != unit:
            raise ThermalFieldJobError(f"Thermal plugin {name} field must use {unit}.")
        normalized_fields[name] = values
        sample_count += int(values["preview_samples"])
        total_sample_count += int(values["total_samples"])
    if sample_count > maximum or total_sample_count > max_total:
        raise ThermalFieldJobError("Thermal plugin result exceeds the admitted output-sample budget.")
    temperatures = raw.get("component_temperatures_k", {})
    if not isinstance(temperatures, Mapping) or any(not str(key) or not math.isfinite(float(value)) or float(value) < 0 for key, value in temperatures.items()):
        raise ThermalFieldJobError("Thermal plugin component_temperatures_k must map non-empty IDs to finite Kelvin values.")
    reported_status = str(raw.get("model_status") or "unvalidated")
    if reported_status not in {"validated", "reference_validated", "experimental", "approximate", "solver_dependent"}:
        raise ThermalFieldJobError("Thermal plugin result has an unsupported model_status.")
    summary = raw.get("summary", {})
    if not isinstance(summary, Mapping):
        raise ThermalFieldJobError("Thermal plugin result summary must be an object.")
    raw_issues = raw.get("issues", [])
    if not isinstance(raw_issues, list) or not all(isinstance(item, Mapping) and item.get("code") and item.get("severity") and item.get("message") for item in raw_issues):
        raise ThermalFieldJobError("Thermal plugin result issues must be structured records.")
    return {
        "contract": RESULT_CONTRACT, "job_id": str(plan.get("job_id") or ""), "plan_digest": str(plan["plan_digest"]),
        "status": "completed", "model_status": reported_status, "summary": dict(summary), "fields": normalized_fields,
        "component_temperatures_k": {str(key): float(value) for key, value in temperatures.items()},
        "resource_usage": {"rendered_preview_samples": sample_count, "total_field_samples": total_sample_count, "max_output_samples": maximum, "max_total_field_samples": max_total, "wall_time_s": elapsed_s, "cpu_time_limit_s": int(plan["resource_budget"]["cpu_time_limit_s"]), "memory_limit_mb": int(plan["resource_budget"]["memory_limit_mb"]), "requested_cells": int(plan["resource_budget"]["requested_cells"])},
        "issues": [dict(item) for item in raw_issues],
        "qualification": {
            "production_qualified": bool(plan.get("qualification", {}).get("solver_release_qualified")) and reported_status in {"validated", "reference_validated"},
            "field_result_produced": True,
            "evidence_id": str(plan.get("qualification", {}).get("evidence_id") or ""),
            "reason": "The runtime result is bound to a plan whose solver evidence passed every requested release gate." if bool(plan.get("qualification", {}).get("solver_release_qualified")) and reported_status in {"validated", "reference_validated"} else "The result is accepted for inspection but is not production qualified.",
        },
        "provenance": {**dict(provenance), "solver_id": str(selected["id"]), "plan_digest": str(plan["plan_digest"]), "scenario_digest": str(plan["scenario_digest"]), "qualification_evidence_id": str(plan.get("qualification", {}).get("evidence_id") or "")},
    }


def _power_table(scenario: Mapping[str, Any]) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for index, source in enumerate(scenario.get("heat_sources", [])):
        if not isinstance(source, Mapping):
            raise ThermalFieldJobError("Heat-source tables must contain objects.")
        source_id = str(source.get("id") or f"source-{index + 1}")
        values[source_id] = _number(source.get("power_w", 0), f"heat_sources[{source_id}].power_w", minimum=0.0)
    return values


def _apply_power_table(scenario: Mapping[str, Any], values: Mapping[str, Any]) -> Dict[str, Any]:
    copied = json.loads(json.dumps(scenario, ensure_ascii=True, allow_nan=False))
    sources = copied.get("heat_sources", [])
    known = {str(item.get("id") or f"source-{index + 1}"): item for index, item in enumerate(sources) if isinstance(item, dict)}
    if set(values) != set(known):
        raise ThermalFieldJobError("Electro-thermal electrical step must return exactly the admitted heat-source IDs.")
    for source_id, value in values.items():
        known[source_id]["power_w"] = _number(value, f"electrothermal power {source_id}", minimum=0.0)
    return copied


def _electrothermal_settings(scenario: Mapping[str, Any]) -> Dict[str, float | int]:
    settings = scenario.get("electrothermal")
    if not isinstance(settings, Mapping) or not bool(settings.get("enabled", False)):
        return {"enabled": False}
    return {
        "enabled": True,
        "max_iterations": int(_number(settings.get("max_iterations", 12), "electrothermal.max_iterations", minimum=1, maximum=50)),
        "temperature_tolerance_k": _number(settings.get("temperature_tolerance_k", 0.1), "electrothermal.temperature_tolerance_k", minimum=1e-9, maximum=1e6),
        "power_tolerance_w": _number(settings.get("power_tolerance_w", 0.01), "electrothermal.power_tolerance_w", minimum=1e-12, maximum=1e12),
    }


def execute_thermal_field_job(
    request: Mapping[str, Any],
    *,
    adapter_registry: Mapping[str, Any],
    solver_catalog: Mapping[str, Mapping[str, Any]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    electrical_step: Callable[[Mapping[str, float], int], Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Execute one already-admitted thermal field job through an explicit adapter.

    An adapter exposes ``probe()`` and ``run(invocation)``. Both are host-owned
    code paths; request data cannot nominate an executable or inject capability
    claims. Every rejected, failed, timed-out, or cancelled execution returns no
    fields, preventing a partial field from being rendered as a result.
    """
    plan = plan_thermal_field_job(request, solver_catalog=solver_catalog, cancel_check=cancel_check)
    if plan["status"] != "ready_for_execution":
        return _execution_result(plan, "THERMAL_FIELD_PLAN_BLOCKED", "The thermal field plan did not pass solver, geometry, resource, and qualification gates.")
    solver_id = str(plan["solver_selection"]["id"])
    adapter = adapter_registry.get(solver_id)
    if adapter is None:
        return _execution_result(plan, "THERMAL_FIELD_ADAPTER_NOT_REGISTERED", f"No host-owned execution adapter is registered for {solver_id}.")
    probe_method = _adapter_method(adapter, "probe")
    run_method = _adapter_method(adapter, "run")
    if probe_method is None or run_method is None:
        return _execution_result(plan, "THERMAL_FIELD_ADAPTER_INTERFACE_INVALID", "Thermal field adapters must expose probe() and run(invocation).")
    try:
        _cancel(cancel_check)
        probe = probe_method()
        if not isinstance(probe, Mapping) or probe.get("contract") != "spike/solver-plugin-probe-result/v1" or probe.get("status") != "passed":
            return _execution_result(plan, "THERMAL_FIELD_RUNTIME_PROBE_FAILED", "The selected solver plugin did not pass its declared runtime probe.", probe=probe if isinstance(probe, Mapping) else None)
        settings = _electrothermal_settings(request["scenario"])
        scenario = dict(request["scenario"])
        prior_temperatures: Mapping[str, float] | None = None
        prior_powers: Mapping[str, float] | None = None
        started = time.monotonic()
        for iteration in range(int(settings.get("max_iterations", 1))):
            _cancel(cancel_check)
            invocation = {
                "contract": ADAPTER_RUN_CONTRACT, "job_id": plan["job_id"], "plan_digest": plan["plan_digest"],
                "scenario": scenario, "geometry": plan["geometry"], "requested_physics": plan["requested_physics"],
                "resource_budget": plan["resource_budget"], "runtime_probe": dict(probe), "electrothermal_iteration": iteration if settings["enabled"] else None,
            }
            raw = run_method(invocation)
            elapsed = time.monotonic() - started
            if elapsed > int(plan["resource_budget"]["cpu_time_limit_s"]):
                return _execution_result(plan, "THERMAL_FIELD_CPU_BUDGET_EXCEEDED", "The solver adapter exceeded the admitted wall-time budget.", status="failed", probe=probe)
            _cancel(cancel_check)
            result = _normalize_adapter_result(plan, raw, elapsed_s=elapsed)
            if not settings["enabled"]:
                result["provenance"]["runtime_probe"] = dict(probe)
                return result
            if electrical_step is None:
                return _execution_result(plan, "ELECTROTHERMAL_ELECTRICAL_ADAPTER_REQUIRED", "Electro-thermal iteration requires a host-owned electrical-step adapter; no implicit power update is permitted.", probe=probe)
            powers = _power_table(scenario)
            temperatures = result["component_temperatures_k"]
            if not temperatures:
                return _execution_result(plan, "ELECTROTHERMAL_TEMPERATURE_TABLE_REQUIRED", "Electro-thermal iteration requires component_temperatures_k from the thermal adapter.", status="failed", probe=probe)
            if prior_temperatures is not None and prior_powers is not None:
                max_temperature_change = max(abs(temperatures.get(key, float("inf")) - prior_temperatures[key]) for key in prior_temperatures)
                max_power_change = max(abs(powers[key] - prior_powers[key]) for key in powers)
                if max_temperature_change <= float(settings["temperature_tolerance_k"]) and max_power_change <= float(settings["power_tolerance_w"]):
                    result["electrothermal"] = {"status": "converged", "iterations": iteration + 1, "temperature_tolerance_k": settings["temperature_tolerance_k"], "power_tolerance_w": settings["power_tolerance_w"]}
                    result["provenance"]["runtime_probe"] = dict(probe)
                    return result
            next_powers = electrical_step(dict(temperatures), iteration)
            if not isinstance(next_powers, Mapping):
                return _execution_result(plan, "ELECTROTHERMAL_ELECTRICAL_RESULT_INVALID", "The electrical-step adapter must return a heat-source power mapping.", status="failed", probe=probe)
            prior_temperatures, prior_powers = dict(temperatures), powers
            scenario = _apply_power_table(scenario, next_powers)
        return _execution_result(plan, "ELECTROTHERMAL_ITERATION_LIMIT", "Electro-thermal iteration reached its admitted limit without satisfying temperature and power tolerances.", status="failed", probe=probe)
    except ThermalFieldJobError as exc:
        message = str(exc)
        code = "THERMAL_FIELD_CANCELLED" if "cancelled" in message else "THERMAL_FIELD_RESULT_REJECTED"
        return _execution_result(plan, code, message, status="cancelled" if code == "THERMAL_FIELD_CANCELLED" else "failed")
    except Exception as exc:  # Adapter failures are terminal and cannot leak partial fields.
        return _execution_result(plan, "THERMAL_FIELD_ADAPTER_FAILED", f"Thermal field adapter failed: {exc}", status="failed")


__all__ = ["ADAPTER_RUN_CONTRACT", "PLAN_CONTRACT", "REQUEST_CONTRACT", "RESULT_CONTRACT", "ThermalFieldJobError", "execute_thermal_field_job", "plan_thermal_field_job"]
