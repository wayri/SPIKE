"""Truthful solver selection, management policy, and EMI pre-pass screening."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List

from .acceleration import acceleration_catalog
from .external_engines import external_engine_catalog
from .spikes_runtime import engine_status
from .solver_state import (
    forget_solver_registration,
    load_solver_state,
    register_solver_path,
    tuning_catalog,
    update_solver_tuning,
)


SOLVER_MANAGER_CONTRACT = "spike/solver-manager/v1"
SOLVER_SELECTION_CONTRACT = "spike/solver-selection/v1"
EMI_SCREENING_CONTRACT = "spike/emi-prepass-screening/v1"

WORKLOADS: List[Dict[str, Any]] = [
    {
        "id": "dc_pi", "name": "DC power integrity", "domain": "pi",
        "required": ["voltage_drop", "current_density", "copper_zones", "through_vias"],
        "candidates": ["spike.routed_dc", "external.elmer", "external.sparselizard"],
    },
    {
        "id": "quasistatic_ac_pi", "name": "Quasi-static AC power integrity", "domain": "pi",
        "required": ["frequency_dependent_impedance", "partial_inductance", "capacitance_extraction"],
        "candidates": ["spike.peec_2_5d", "external.fasthenry", "external.fastcap", "external.elmer", "external.sparselizard"],
    },
    {
        "id": "geometry_transient", "name": "Geometry-derived PI transient", "domain": "pi",
        "required": ["transient_waveforms", "geometry_transient", "partial_inductance"],
        "candidates": ["spike.peec_rl_transient"],
    },
    {
        "id": "circuit_cosimulation", "name": "Circuit co-simulation", "domain": "pi",
        "required": ["transient", "explicit_netlist"],
        "candidates": ["external.ngspice", "spike.ngspice"],
    },
    {
        "id": "linear_circuit_workspace", "name": "Native linear circuit workspace", "domain": "circuit",
        "required": ["linear_mna", "explicit_circuit_workspace", "operating_point", "ac_sweep", "transient_waveforms"],
        "candidates": ["spike.native_mna"],
    },
    {
        "id": "owned_circuit_workspace", "name": "Owned structured circuit workspace", "domain": "circuit",
        "required": ["explicit_circuit_workspace", "operating_point", "transient_waveforms", "release_owned_engine"],
        "candidates": ["spike.owned_spice_workspace"],
    },
    {
        "id": "fullwave_comparison", "name": "Full-wave field comparison", "domain": "si",
        "required": ["fdtd_3d_experimental", "explicit_lumped_ports"],
        "candidates": ["external.openems", "external.elmer", "external.sparselizard", "spike.fullwave_3d"],
    },
    {
        "id": "thermal_airflow", "name": "Conjugate thermal and airflow", "domain": "thermal",
        "required": ["conjugate_heat_transfer", "airflow"],
        "candidates": ["external.openfoam", "external.elmer", "external.flotherm", "external.sparselizard"],
    },
    {
        "id": "emi_radiation", "name": "PCB EMI radiation and far field", "domain": "emi",
        "required": ["far_field", "ports", "lossy_dielectrics"],
        "candidates": ["external.openems", "external.elmer", "external.sparselizard", "spike.fullwave_3d"],
    },
]


NATIVE_WORKSPACE_SOLVER: Dict[str, Any] = {
    "id": "spike.native_mna",
    "name": "SPIKE Native Linear MNA Workspace",
    "version": "1",
    "provider": "SPIKE",
    "source": "native",
    "state": "available",
    "model_status": "approximate",
    "execution": "workspace_contract",
    "request_contract": "spike/native-mna-request/v1",
    "capabilities": [
        "linear_mna", "explicit_circuit_workspace", "operating_point",
        "ac_sweep", "transient_waveforms", "passive_rlc",
        "independent_sources", "linear_dependent_sources",
    ],
    "actions": ["validate", "run"],
    "validation": "Closed-form DC divider, AC RC corner, and backward-Euler RC transient reference fixtures pass.",
    "scope": "Explicit reviewed linear circuit workspace only; no PCB geometry extraction and no nonlinear-device model.",
    "reason": "Accepts an explicit reviewed linear circuit workspace only; it does not extract PCB geometry or model nonlinear devices.",
}


def _owned_spice_workspace_solver() -> Dict[str, Any]:
    """Describe the release-owned circuit bridge after probing its exact runtime.

    This deliberately remains a separate circuit workload.  The bridge accepts
    an explicit reviewed workspace, not board geometry, so it must never be
    selected as a substitute for geometry-derived or closed-loop co-simulation.
    """

    status = engine_status()
    available = bool(status.get("available"))
    features = status.get("features")
    transient = isinstance(features, dict) and bool(features.get("transient"))
    runnable = available and transient
    return {
        "id": "spike.owned_spice_workspace",
        "name": "SPIKES Owned Structured Circuit Workspace",
        "version": str(status.get("abi_version") or "unavailable"),
        "provider": "SPIKE",
        "source": "native",
        "state": "experimental" if runnable else "unavailable",
        "model_status": "experimental" if runnable else "unsupported",
        "execution": "owned_workspace_contract",
        "request_contract": "spike/owned-spice-workspace-request/v1",
        "capabilities": (
            [
                "explicit_circuit_workspace", "operating_point",
                "transient_waveforms", "release_owned_engine",
            ] if runnable else []
        ),
        "actions": ["validate", "run"] if runnable else ["detect"],
        "validation": (
            "The release-owned engine passed its in-process availability probe; "
            "structured-workspace execution remains experimental."
        ) if runnable else "The release-owned SPIKES circuit runtime probe is unavailable or lacks transient support.",
        "scope": (
            "Explicit reviewed circuit workspace only (operating point and transient). "
            "No raw netlist input, caller-selected library, AC/phasor solve, PCB geometry extraction, "
            "or closed-loop field/circuit co-simulation is advertised by this workload."
        ),
        "reason": (
            "Runtime-probed release-owned engine for bounded, structured circuit execution; "
            "experimental and not product-qualified."
        ) if runnable else (
            "The release-owned circuit runtime must pass its availability and transient-feature probe before this workload can run."
        ),
    }


def _state_ready(state: str) -> bool:
    return state in {"available", "experimental", "reference_validated", "validated"}


def _candidate_record(identifier: str, entries: Dict[str, Dict[str, Any]], required: Iterable[str]) -> Dict[str, Any]:
    entry = entries.get(identifier)
    if entry is None:
        return {"id": identifier, "name": identifier, "state": "not_catalogued", "eligible": False, "missing": list(required), "reason": "Not catalogued."}
    capabilities = set(entry.get("capabilities", []))
    missing = [capability for capability in required if capability not in capabilities]
    state = str(entry.get("state", "unavailable"))
    eligible = _state_ready(state) and not missing
    if eligible:
        reason = str(entry.get("validation") or entry.get("reason") or "Capability and runtime gates pass.")
    elif not _state_ready(state):
        reason = str(entry.get("reason") or entry.get("validation") or f"Runtime state is {state}.")
    else:
        reason = f"Missing required capabilities: {', '.join(missing)}"
    return {
        "id": identifier,
        "name": str(entry.get("name", identifier)),
        "source": str(entry.get("source", "unknown")),
        "state": state,
        "model_status": str(entry.get("model_status", "unsupported")),
        "execution": str(entry.get("execution", entry.get("interface", "builtin"))),
        "adapter_version": str(entry.get("adapter_version", "")),
        "request_contract": str(entry.get("request_contract", "")),
        "scope": str(entry.get("scope", "")),
        "actions": list(entry.get("actions", [])),
        "eligible": eligible,
        "missing": missing,
        "reason": reason,
    }


def solver_manager_catalog(internal_solvers: List[Dict[str, Any]], *, refresh: bool = False) -> Dict[str, Any]:
    external = external_engine_catalog(refresh=refresh)
    state = load_solver_state()
    entries = {str(item["id"]): {**item, "source": "native"} for item in internal_solvers}
    entries[NATIVE_WORKSPACE_SOLVER["id"]] = dict(NATIVE_WORKSPACE_SOLVER)
    entries["spike.owned_spice_workspace"] = _owned_spice_workspace_solver()
    entries.update({str(item["id"]): {**item, "source": "external"} for item in external["engines"]})
    workloads = []
    for definition in WORKLOADS:
        candidates = [_candidate_record(identifier, entries, definition["required"]) for identifier in definition["candidates"]]
        best = next((candidate for candidate in candidates if candidate["eligible"]), None)
        model_status = str(best.get("model_status", "unsupported")) if best else "unsupported"
        workload_status = (
            "validated" if model_status == "validated"
            else "reference_validated" if model_status == "reference_validated"
            else "solver_dependent" if model_status == "solver_dependent"
            else "experimental" if model_status == "experimental"
            else "approximate" if best else "unavailable"
        )
        workloads.append({
            **definition,
            "status": workload_status,
            "recommended": best,
            "candidates": candidates,
        })
    workload_membership: Dict[str, List[Dict[str, Any]]] = {}
    for workload in workloads:
        for candidate in workload["candidates"]:
            workload_membership.setdefault(candidate["id"], []).append({
                "id": workload["id"],
                "name": workload["name"],
                "eligible": candidate["eligible"],
                "missing": candidate["missing"],
            })
    tuning_profiles = tuning_catalog()
    tunable_ids = {profile["target_id"] for profile in tuning_profiles}
    readiness = []
    for identifier, entry in sorted(entries.items()):
        state_name = str(entry.get("state", "unavailable"))
        runtime_verified = state_name in {
            "available", "experimental", "reference_validated", "validated",
            "runtime_verified_adapter_pending", "adapter_ready_unvalidated",
        }
        is_native = entry.get("source") == "native"
        adapter_ready = "run" in entry.get("actions", []) and _state_ready(state_name)
        model_status = str(entry.get("model_status", "unsupported"))
        readiness.append({
            "id": identifier,
            "name": str(entry.get("name", identifier)),
            "source": str(entry.get("source", "unknown")),
            "runtime": "verified" if runtime_verified else "missing_or_unverified",
            "adapter": "not_required" if is_native else "ready" if adapter_ready else "missing_or_gated",
            "validation": model_status,
            "tunable": identifier in tunable_ids,
            "workflows": workload_membership.get(identifier, []),
            "reason": str(entry.get("reason", "")),
        })
    return {
        "contract": SOLVER_MANAGER_CONTRACT,
        "selection_policy": "capability_then_validity_then_declared_priority",
        "installation": {
            "managed_downloads": False,
            "reason": "Signed package manifests, hashes, SBOMs, license notices, and rollback are required before managed installation is enabled.",
            "register_local_paths": True,
            "remove_behavior": "forget_registration_only",
        },
        "registrations": state["registrations"],
        "tuning_profiles": tuning_profiles,
        "readiness_matrix": readiness,
        "accelerators": acceleration_catalog()["policy"],
        "workloads": workloads,
        "emi_pipeline": {
            "state": "capability_gated",
            "stages": [
                {"id": "pi_si_prepass", "state": "available_approximate", "detail": "Native DC, quasi-static AC, and transient metrics may be used."},
                {"id": "net_screening", "state": "available_screening_only", "detail": "Ranks supplied pre-pass metrics; it does not predict compliance."},
                {"id": "closed_loop_spice", "state": "unavailable", "detail": "Geometry RLC/device coupling and validation are incomplete."},
                {"id": "fullwave_fields", "state": "reference_validated_if_openems_ready", "detail": "Explicit ports and a version-matched reference-validation record are required."},
                {"id": "far_field_dashboard", "state": "reference_fixture_validated", "detail": "NF2FF execution is enabled for version-matched openEMS; arbitrary-PCB and compliance accuracy remain unvalidated."},
            ],
        },
    }


def register_external_solver(engine_id: str, path: str, internal_solvers: List[Dict[str, Any]]) -> Dict[str, Any]:
    registration = register_solver_path(engine_id, path)
    return {"registration": registration, "catalog": solver_manager_catalog(internal_solvers, refresh=True)}


def unregister_external_solver(engine_id: str, internal_solvers: List[Dict[str, Any]]) -> Dict[str, Any]:
    removed = forget_solver_registration(engine_id)
    return {"removed": removed, "files_deleted": False, "catalog": solver_manager_catalog(internal_solvers, refresh=True)}


def tune_solver(target_id: str, values: Dict[str, Any], internal_solvers: List[Dict[str, Any]]) -> Dict[str, Any]:
    configured = update_solver_tuning(target_id, values)
    return {"target_id": target_id, "configured": configured, "catalog": solver_manager_catalog(internal_solvers)}


def recommend_solver(workload_id: str, internal_solvers: List[Dict[str, Any]]) -> Dict[str, Any]:
    catalog = solver_manager_catalog(internal_solvers)
    workload = next((item for item in catalog["workloads"] if item["id"] == workload_id), None)
    if workload is None:
        raise ValueError(f"Unknown solver workload: {workload_id}")
    return {"contract": "spike/solver-recommendation/v1", "workload": workload}


def select_solver(
    workload_id: str,
    solver_id: str,
    internal_solvers: List[Dict[str, Any]],
    *,
    refresh: bool = False,
) -> Dict[str, Any]:
    """Resolve one user-selected solver without silently substituting another.

    This selection contract deliberately does not launch a solver.  Workbench
    routes must carry the selected id into their own request contract and apply
    their geometry, port, and validation gates before execution.
    """
    requested = str(solver_id or "").strip()
    if not requested or requested == "auto":
        raise ValueError("A concrete solver_id is required; automatic substitution is not permitted.")
    catalog = solver_manager_catalog(internal_solvers, refresh=refresh)
    workload = next((item for item in catalog["workloads"] if item["id"] == workload_id), None)
    if workload is None:
        raise ValueError(f"Unknown solver workload: {workload_id}")
    candidate = next((item for item in workload["candidates"] if item["id"] == requested), None)
    if candidate is None:
        return {
            "contract": SOLVER_SELECTION_CONTRACT,
            "workload_id": workload_id,
            "requested_solver_id": requested,
            "status": "blocked",
            "selected": None,
            "reason": f"{requested} is not declared for the {workload['name']} workload.",
            "selection_policy": "explicit_solver_only_no_fallback",
        }
    if not candidate["eligible"]:
        return {
            "contract": SOLVER_SELECTION_CONTRACT,
            "workload_id": workload_id,
            "requested_solver_id": requested,
            "status": "blocked",
            "selected": None,
            "candidate": candidate,
            "reason": candidate["reason"],
            "selection_policy": "explicit_solver_only_no_fallback",
        }
    return {
        "contract": SOLVER_SELECTION_CONTRACT,
        "workload_id": workload_id,
        "requested_solver_id": requested,
        "status": "selected",
        "selected": candidate,
        "reason": "The requested solver satisfies the declared workload capability and runtime gates. Execution remains route-specific.",
        "selection_policy": "explicit_solver_only_no_fallback",
    }


def _metric(value: Any) -> float:
    try:
        result = abs(float(value))
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def recommend_emi_nets(net_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(net_metrics, list) or not net_metrics:
        raise ValueError("EMI pre-pass screening requires at least one net metric record.")
    if len(net_metrics) > 4096:
        raise ValueError("EMI pre-pass screening is limited to 4096 nets per request.")
    feature_weights = {
        "dv_dt_v_per_s": 0.30,
        "di_dt_a_per_s": 0.30,
        "peak_current_a": 0.15,
        "loop_area_mm2": 0.15,
        "return_discontinuities": 0.10,
    }
    rows = []
    for index, raw in enumerate(net_metrics):
        if not isinstance(raw, dict) or not str(raw.get("net", "")).strip():
            raise ValueError(f"EMI metric record {index} requires a net name.")
        rows.append({"net": str(raw["net"]), **{key: math.log1p(_metric(raw.get(key))) for key in feature_weights}})
    extrema = {
        key: (min(row[key] for row in rows), max(row[key] for row in rows))
        for key in feature_weights
    }
    ranked = []
    for row in rows:
        contributions = {}
        for key, weight in feature_weights.items():
            low, high = extrema[key]
            normalized = (row[key] - low) / (high - low) if high > low else 0.0
            contributions[key] = normalized * weight
        score = 100.0 * sum(contributions.values())
        reasons = sorted(contributions, key=contributions.get, reverse=True)[:2]
        ranked.append({
            "net": row["net"],
            "score": round(score, 3),
            "reasons": [key.replace("_", " ") for key in reasons if contributions[key] > 0],
        })
    ranked.sort(key=lambda item: (-item["score"], item["net"]))
    return {
        "contract": EMI_SCREENING_CONTRACT,
        "status": "screening_only",
        "recommended_nets": ranked,
        "warning": "This normalized heuristic prioritizes full-wave review; it is not a radiation prediction or EMI compliance result.",
    }
