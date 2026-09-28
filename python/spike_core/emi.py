"""Versioned EMI workflow setup, preflight, and screening.

This module deliberately separates risk screening from field solving. Screening
only ranks supplied electrical/geometry metrics; it never manufactures field,
radiation, or compliance results when a validated solver is unavailable.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Tuple

from .contracts import DesignIR
from .solver_manager import recommend_emi_nets, recommend_solver


EMI_SETUP_CONTRACT = "spike/emi-setup/v1"
EMI_PREFLIGHT_CONTRACT = "spike/emi-preflight/v1"
EMI_WORKFLOW_CONTRACT = "spike/emi-workflow/v1"

_ANALYSES = {"conducted_screening", "near_field", "far_field"}
_ENVIRONMENTS = {"free_space", "bench_ground_plane", "shielded_enclosure"}
_EXCITATIONS = {"prepass_results", "explicit_ports", "spice"}
_RE_STANDARDS = {
    "cispr-25-2021": {
        "title": "CISPR 25:2021",
        "method": "automotive on-board receiver protection",
        "source": "https://webstore.iec.ch/en/publication/64645",
        "classifications": {"1", "2", "3", "4", "5"},
    },
    "cispr-32-2015-amd1-2019": {
        "title": "CISPR 32:2015+AMD1:2019",
        "method": "multimedia-equipment radiated emissions",
        "source": "https://webstore.iec.ch/en/publication/65836",
        "classifications": {"A", "B"},
    },
    "mil-std-461h-2026-re102": {
        "title": "MIL-STD-461H:2026 RE102",
        "method": "electric-field radiated emissions",
        "source": "https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=35789",
        "platform_required": True,
    },
    "mil-std-461g-2015-re102": {
        "title": "MIL-STD-461G:2015 RE102 (historical)",
        "method": "electric-field radiated emissions",
        "source": "https://quicksearch.dla.mil/qsDocDetails.aspx?ident_number=35789",
        "platform_required": True,
    },
}
_RE_PLATFORMS = {"ground", "surface_ship", "submarine", "aircraft", "space"}
_METRIC_FIELDS = (
    "dv_dt_v_per_s",
    "di_dt_a_per_s",
    "peak_current_a",
    "loop_area_mm2",
    "return_discontinuities",
)


def _issue(
    code: str,
    severity: str,
    message: str,
    path: str = "",
    suggestion: str = "",
) -> Dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "path": path,
        "suggestion": suggestion,
        "status": "open",
    }


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _validate_chamber(raw: Any) -> Tuple[Dict[str, Any] | None, List[Dict[str, str]]]:
    """Chamber controls describe a visual fixture, never an implicit solver mesh."""
    if raw is None:
        return None, []  # Existing v1 projects remain compatible.
    if not isinstance(raw, dict):
        return None, [_issue("EMI_CHAMBER_INVALID", "error", "Chamber setup must be an object.", "chamber")]
    defaults = {"distance_m": 3, "table_height_m": 0.8, "antenna_height_m": 1.5, "azimuth_deg": 0,
                "orientation": "flat", "polarization": "horizontal", "floor": "absorber", "cutaway": True}
    chamber = {**defaults, **raw}
    issues = []
    for key, low, high in [("distance_m", 1, 10), ("table_height_m", .5, 1.5), ("antenna_height_m", 1, 4), ("azimuth_deg", 0, 360)]:
        number = _finite_number(chamber[key])
        if isinstance(chamber[key], bool) or number is None or not low <= number <= high:
            issues.append(_issue("EMI_CHAMBER_RANGE", "error", f"{key} must be between {low} and {high}.", f"chamber.{key}"))
    for key, choices in [("orientation", ("flat", "upright", "side")), ("polarization", ("horizontal", "vertical")), ("floor", ("absorber", "ground_plane"))]:
        if chamber[key] not in choices:
            issues.append(_issue("EMI_CHAMBER_OPTION", "error", f"Unsupported chamber {key}.", f"chamber.{key}"))
    if not isinstance(chamber["cutaway"], bool):
        issues.append(_issue("EMI_CHAMBER_OPTION", "error", "Cutaway must be a boolean.", "chamber.cutaway"))
    issues.append(_issue("EMI_CHAMBER_PREVIEW", "info", "The chamber, antenna polarization, table and DUT pose are a visual setup. The current field adapter solves its prepared domain; no chamber reflection, receive antenna or EMC detector response is inferred.", "chamber"))
    return chamber, issues


def _validate_radiated_emissions_standard(raw: Any) -> Tuple[Dict[str, Any] | None, List[Dict[str, str]]]:
    """Bind a reference edition only; no limit or compliance result is inferred."""
    if raw is None:
        return None, []
    if not isinstance(raw, dict):
        return None, [_issue("EMI_STANDARD_INVALID", "error", "Radiated-emissions standard must be an object.", "radiated_emissions_standard")]
    identifier = raw.get("id")
    if isinstance(identifier, str) and identifier in {"mil-431", "mil-std-431"}:
        return None, [_issue("EMI_STANDARD_NOT_RE", "error", "MIL-431 is not a verified radiated-emissions method. Select an exact published standard and revision.", "radiated_emissions_standard.id")]
    if not isinstance(identifier, str) or identifier not in _RE_STANDARDS:
        return None, [_issue("EMI_STANDARD_UNKNOWN", "error", "Unknown or unsupported radiated-emissions standard edition.", "radiated_emissions_standard.id")]
    profile = _RE_STANDARDS[identifier]
    allowed = {"id", "classification"} if "classifications" in profile else {"id", "platform"}
    if set(raw) - allowed:
        return None, [_issue("EMI_STANDARD_INVALID", "error", "Unsupported field or classification/platform for this standard.", "radiated_emissions_standard")]
    if "classifications" in profile:
        classification = raw.get("classification")
        if not isinstance(classification, str) or classification not in profile["classifications"]:
            return None, [_issue("EMI_STANDARD_CLASS", "error", "Select a valid class for this exact standard edition.", "radiated_emissions_standard.classification")]
        selection = {"id": identifier, "classification": classification}
    else:
        platform = raw.get("platform")
        if not isinstance(platform, str) or platform not in _RE_PLATFORMS:
            return None, [_issue("EMI_STANDARD_PLATFORM", "error", "Select a supported platform category; limit applicability still requires expert review.", "radiated_emissions_standard.platform")]
        selection = {"id": identifier, "platform": platform}
    reference = {
        **selection,
        "title": profile["title"],
        "method": profile["method"],
        "source": profile["source"],
        "limit_data_status": "not_bundled",
        "comparison_status": "unavailable",
        "compliance_available": False,
        "required_evidence_status": {
            "detector": "not_qualified",
            "measurement_bandwidth": "not_qualified",
            "frequency_applicability": "not_qualified",
            "antenna_and_polarization": "not_qualified",
            "distance_and_fixture": "not_qualified",
            "measured_correlation": "not_qualified",
        },
    }
    return reference, [_issue("EMI_STANDARD_REFERENCE_ONLY", "warning", "The selected edition is reference metadata only. Licensed limits, detector, bandwidth, antenna, polarization, setup and measured correlation are not available; no pass/fail comparison is possible.", "radiated_emissions_standard")]


def _names(values: Any, *, limit: int = 128) -> List[str]:
    if not isinstance(values, list):
        return []
    result: List[str] = []
    for value in values[:limit]:
        name = str(value).strip()
        if name and name not in result:
            result.append(name)
    return result


def _design_net_names(design: DesignIR) -> set[str]:
    return {
        str(item.get("name", item.get("net_name", ""))).strip()
        for item in design.nets
        if str(item.get("name", item.get("net_name", ""))).strip()
    }


def _geometry_net(item: Dict[str, Any]) -> str:
    return str(item.get("net_name", item.get("net", ""))).strip()


def _geometry_coverage(design: DesignIR, net_names: Iterable[str]) -> List[Dict[str, Any]]:
    coverage: List[Dict[str, Any]] = []
    for net in net_names:
        tracks = [item for item in design.tracks if _geometry_net(item) == net]
        vias = [item for item in design.vias if _geometry_net(item) == net]
        pads = [item for item in design.pads if _geometry_net(item) == net]
        zones = [item for item in design.zones if _geometry_net(item) == net]
        layers = sorted({
            str(item.get("layer", ""))
            for item in [*tracks, *pads, *zones]
            if str(item.get("layer", "")).strip()
        } | {
            str(layer)
            for via in vias
            for layer in (via.get("layers") or [via.get("start_layer"), via.get("end_layer")])
            if str(layer or "").strip()
        })
        length_mm = 0.0
        for track in tracks:
            start, end = track.get("start"), track.get("end")
            if isinstance(start, list) and isinstance(end, list) and len(start) >= 2 and len(end) >= 2:
                x0, y0, x1, y1 = map(_finite_number, (start[0], start[1], end[0], end[1]))
                if None not in (x0, y0, x1, y1):
                    length_mm += math.hypot(float(x1) - float(x0), float(y1) - float(y0))
        coverage.append({
            "net": net,
            "tracks": len(tracks),
            "vias": len(vias),
            "pads": len(pads),
            "zones": len(zones),
            "layers": layers,
            "routed_length_mm": round(length_mm, 6),
            "has_geometry": bool(tracks or vias or pads or zones),
        })
    return coverage


def _validate_ports(ports: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    issues: List[Dict[str, str]] = []
    if not isinstance(ports, list):
        return [], [_issue("EMI_PORTS_INVALID", "error", "Excitation ports must be a list.", "excitation.ports")]
    if len(ports) > 32:
        return [], [_issue("EMI_PORT_LIMIT", "error", "At most 32 explicit ports are allowed per EMI setup.", "excitation.ports")]
    normalized: List[Dict[str, Any]] = []
    excited = 0
    for index, raw in enumerate(ports):
        path = f"excitation.ports[{index}]"
        if not isinstance(raw, dict):
            issues.append(_issue("EMI_PORT_INVALID", "error", "Each port must be an object.", path))
            continue
        start = raw.get("start")
        stop = raw.get("stop")
        if not isinstance(start, list) or not isinstance(stop, list) or len(start) != 3 or len(stop) != 3:
            issues.append(_issue("EMI_PORT_ENDPOINTS", "error", "Port start and stop must each contain X, Y, and Z coordinates.", path))
            continue
        start_values = [_finite_number(value) for value in start]
        stop_values = [_finite_number(value) for value in stop]
        impedance = _finite_number(raw.get("impedance_ohm", 50))
        direction = str(raw.get("direction", "")).lower()
        if any(value is None for value in [*start_values, *stop_values]):
            issues.append(_issue("EMI_PORT_COORDINATE", "error", "Port coordinates must be finite numbers.", path))
            continue
        if start_values == stop_values:
            issues.append(_issue("EMI_PORT_ZERO_LENGTH", "error", "Port start and stop cannot be identical.", path))
        if direction not in {"x", "y", "z"}:
            issues.append(_issue("EMI_PORT_DIRECTION", "error", "Port direction must be x, y, or z.", path))
        if impedance is None or impedance <= 0:
            issues.append(_issue("EMI_PORT_IMPEDANCE", "error", "Port impedance must be a positive finite value.", path))
        excite = bool(raw.get("excite", False))
        excited += int(excite)
        normalized.append({
            "id": str(raw.get("id", f"port-{index + 1}")),
            "name": str(raw.get("name", f"Port {index + 1}")),
            "start": [float(value) for value in start_values if value is not None],
            "stop": [float(value) for value in stop_values if value is not None],
            "direction": direction,
            "impedance_ohm": float(impedance or 0),
            "excite": excite,
        })
    if ports and excited != 1:
        issues.append(_issue(
            "EMI_EXCITED_PORT_COUNT",
            "error",
            "Exactly one port must be excited for the current openEMS single-excitation adapter.",
            "excitation.ports",
        ))
    return normalized, issues


def _validate_metrics(
    metrics: Any,
    selected_nets: List[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], bool]:
    issues: List[Dict[str, str]] = []
    normalized: List[Dict[str, Any]] = []
    if not isinstance(metrics, list):
        return [], [_issue("EMI_METRICS_INVALID", "error", "Net metrics must be a list.", "net_metrics")], False
    seen: set[str] = set()
    for index, raw in enumerate(metrics):
        path = f"net_metrics[{index}]"
        if not isinstance(raw, dict):
            issues.append(_issue("EMI_METRIC_INVALID", "error", "Each net metric must be an object.", path))
            continue
        net = str(raw.get("net", "")).strip()
        if net not in selected_nets:
            issues.append(_issue("EMI_METRIC_NET", "error", f"Metric net '{net}' is not selected for EMI review.", path))
            continue
        if net in seen:
            issues.append(_issue("EMI_METRIC_DUPLICATE", "error", f"Metric net '{net}' is duplicated.", path))
            continue
        seen.add(net)
        row: Dict[str, Any] = {"net": net, "source": str(raw.get("source", "user"))}
        for field in _METRIC_FIELDS:
            value = _finite_number(raw.get(field, 0))
            if value is None or value < 0:
                issues.append(_issue("EMI_METRIC_VALUE", "error", f"{field} must be a non-negative finite magnitude.", f"{path}.{field}"))
                value = 0.0
            row[field] = float(value)
        normalized.append(row)
    missing = [net for net in selected_nets if net not in seen]
    if missing:
        issues.append(_issue(
            "EMI_METRICS_MISSING",
            "warning",
            f"Pre-pass electrical metrics are missing for {len(missing)} selected net(s): {', '.join(missing[:6])}.",
            "net_metrics",
            "Run PI/transient/SPICE pre-pass analyses or enter measured metric magnitudes before screening.",
        ))
    dynamic = any(row["dv_dt_v_per_s"] > 0 or row["di_dt_a_per_s"] > 0 or row["peak_current_a"] > 0 for row in normalized)
    if selected_nets and not dynamic:
        issues.append(_issue(
            "EMI_DYNAMIC_METRICS_EMPTY",
            "warning",
            "No non-zero dV/dt, dI/dt, or peak-current data is available; risk ranking would not be electrically meaningful.",
            "net_metrics",
            "Import solved transient/SPICE metrics or enter defensible measured values.",
        ))
    complete = len(normalized) == len(selected_nets) and dynamic and not any(item["severity"] == "error" for item in issues)
    return normalized, issues, complete


def validate_emi_setup(
    design: DesignIR,
    setup: Dict[str, Any],
    solver_catalog: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate the staged EMI workflow without running or inferring physics."""

    issues: List[Dict[str, str]] = []
    if not isinstance(setup, dict):
        setup = {}
        issues.append(_issue("EMI_SETUP_INVALID", "error", "EMI setup must be a JSON object."))
    if setup.get("contract") != EMI_SETUP_CONTRACT:
        issues.append(_issue(
            "EMI_SETUP_CONTRACT",
            "error",
            f"Expected setup contract {EMI_SETUP_CONTRACT}.",
            "contract",
        ))

    chamber, chamber_issues = _validate_chamber(setup.get("chamber"))
    issues.extend(chamber_issues)
    reference_standard, standard_issues = _validate_radiated_emissions_standard(setup.get("radiated_emissions_standard"))
    issues.extend(standard_issues)
    if "radiated_emissions_standard" in setup and setup["radiated_emissions_standard"] is None:
        issues.append(_issue("EMI_STANDARD_INVALID", "error", "Omit an unselected standard instead of using null.", "radiated_emissions_standard"))
    available_nets = _design_net_names(design)
    selected_nets = _names(setup.get("selected_nets"))
    return_nets = _names(setup.get("return_nets"))
    if not selected_nets:
        issues.append(_issue("EMI_NET_REQUIRED", "error", "Select at least one aggressor or candidate net.", "selected_nets"))
    for net in [*selected_nets, *return_nets]:
        if net not in available_nets:
            issues.append(_issue("EMI_NET_UNKNOWN", "error", f"Net '{net}' does not exist in DesignIR.", "selected_nets"))
    overlap = sorted(set(selected_nets) & set(return_nets))
    if overlap:
        issues.append(_issue("EMI_RETURN_OVERLAP", "error", f"Candidate and return selections overlap: {', '.join(overlap)}.", "return_nets"))

    analyses = _names(setup.get("requested_analyses"), limit=3)
    invalid_analyses = [value for value in analyses if value not in _ANALYSES]
    if not analyses or invalid_analyses:
        issues.append(_issue("EMI_ANALYSIS_INVALID", "error", "Select one or more supported EMI workflow stages.", "requested_analyses"))

    frequency = setup.get("frequency") if isinstance(setup.get("frequency"), dict) else {}
    start_hz = _finite_number(frequency.get("start_hz"))
    stop_hz = _finite_number(frequency.get("stop_hz"))
    points = _finite_number(frequency.get("points"))
    if start_hz is None or stop_hz is None or points is None or start_hz <= 0 or stop_hz <= start_hz or not 2 <= points <= 100000:
        issues.append(_issue("EMI_FREQUENCY_INVALID", "error", "Frequency sweep requires 0 < start < stop and 2 to 100000 points.", "frequency"))

    environment = setup.get("environment") if isinstance(setup.get("environment"), dict) else {}
    environment_kind = str(environment.get("kind", "free_space"))
    if environment_kind not in _ENVIRONMENTS:
        issues.append(_issue("EMI_ENVIRONMENT_INVALID", "error", "Select a supported test environment.", "environment.kind"))
    if environment_kind != "free_space":
        issues.append(_issue(
            "EMI_ENVIRONMENT_ADAPTER_LIMIT",
            "warning",
            "The current openEMS adapter exports free-space cases only; bench planes and enclosures remain setup metadata.",
            "environment.kind",
        ))

    mesh = setup.get("mesh") if isinstance(setup.get("mesh"), dict) else {}
    resolution = _finite_number(mesh.get("resolution_mm"))
    padding = _finite_number(mesh.get("padding_cells"))
    if resolution is None or not 0.0001 <= resolution <= 100:
        issues.append(_issue("EMI_MESH_RESOLUTION", "error", "Mesh resolution must be between 0.0001 and 100 mm.", "mesh.resolution_mm"))
    if padding is None or not 2 <= padding <= 40:
        issues.append(_issue("EMI_BOUNDARY_PADDING", "error", "Boundary padding must be between 2 and 40 cells.", "mesh.padding_cells"))
    max_solver_time = _finite_number(setup.get("max_solver_time_s"))
    if max_solver_time is None or not 1 <= max_solver_time <= 604800:
        issues.append(_issue("EMI_SOLVER_TIME", "error", "Maximum solver time must be between 1 second and 7 days.", "max_solver_time_s"))

    excitation = setup.get("excitation") if isinstance(setup.get("excitation"), dict) else {}
    excitation_mode = str(excitation.get("mode", "prepass_results"))
    if excitation_mode not in _EXCITATIONS:
        issues.append(_issue("EMI_EXCITATION_INVALID", "error", "Select a supported excitation source.", "excitation.mode"))
    ports, port_issues = _validate_ports(excitation.get("ports", []))
    issues.extend(port_issues)
    if excitation_mode == "explicit_ports" and not ports:
        issues.append(_issue("EMI_PORT_REQUIRED", "error", "Explicit-port excitation requires at least one port.", "excitation.ports"))
    if excitation_mode in {"prepass_results", "spice"}:
        issues.append(_issue(
            "EMI_CLOSED_LOOP_UNAVAILABLE",
            "warning",
            "Closed-loop PI/SPICE-to-full-wave excitation is not implemented; results are retained as screening inputs only.",
            "excitation.mode",
        ))

    metrics, metric_issues, metrics_complete = _validate_metrics(setup.get("net_metrics", []), selected_nets)
    issues.extend(metric_issues)
    coverage = _geometry_coverage(design, selected_nets)
    missing_geometry = [row["net"] for row in coverage if not row["has_geometry"]]
    if missing_geometry:
        issues.append(_issue(
            "EMI_GEOMETRY_MISSING",
            "error",
            f"No exported conductor geometry exists for: {', '.join(missing_geometry)}.",
            "selected_nets",
        ))
    if not design.stackup:
        issues.append(_issue("EMI_STACKUP_MISSING", "error", "A material stackup is required for field setup.", "design.stackup"))
    if design.technology != "rigid":
        issues.append(_issue(
            "EMI_TECHNOLOGY_UNSUPPORTED",
            "error",
            f"The current full-wave adapter does not support {design.technology} deformation.",
            "design.technology",
            "Export and validate each rigid region separately until flex geometry is supported.",
        ))

    recommendation = recommend_solver("emi_radiation", solver_catalog)["workload"]
    solver_ready = recommendation.get("recommended") is not None
    if not solver_ready:
        issues.append(_issue(
            "EMI_SOLVER_UNAVAILABLE",
            "warning",
            "No installed solver currently passes SPIKE's far-field, port, and lossy-dielectric capability gates.",
            "solver",
            "Use Solver Manager to register a compatible engine; preparation remains available for inspection.",
        ))

    errors = [item for item in issues if item["severity"] == "error"]
    can_screen = not errors and metrics_complete
    can_prepare = not errors
    can_run = can_prepare and solver_ready and excitation_mode == "explicit_ports" and bool(ports)
    status = "blocked" if errors else "ready_to_run" if can_run else "ready_to_screen" if can_screen else "ready_to_prepare"

    stages = [
        {"id": "setup", "name": "Design and domain", "state": "blocked" if errors else "complete", "detail": f"{len(selected_nets)} candidate net(s), {len(return_nets)} return net(s)."},
        {"id": "screen", "name": "Electrical pre-pass", "state": "ready" if can_screen else "needs_input", "detail": "Requires defensible dV/dt, dI/dt, peak-current, loop-area, and return-path metrics."},
        {"id": "excitation", "name": "Excitation and ports", "state": "complete" if excitation_mode == "explicit_ports" and ports and not port_issues else "screening_only", "detail": "Explicit conductor-to-conductor ports are required for the current full-wave adapter."},
        {"id": "fields", "name": "Full-wave fields", "state": "ready" if can_run else "capability_gated", "detail": "Runs only when an eligible local solver and valid explicit ports are present."},
        {
            "id": "far_field",
            "name": "Far field and compliance",
            "state": "reference_fixture_validated" if can_run else "capability_gated",
            "detail": (
                "NF2FF execution is available; this setup is not a regulatory-compliance prediction."
                if can_run else "No eligible version-matched far-field engine is installed."
            ),
        },
    ]
    return {
        "contract": EMI_PREFLIGHT_CONTRACT,
        "setup_contract": EMI_SETUP_CONTRACT,
        "status": status,
        "can_screen": can_screen,
        "can_prepare": can_prepare,
        "can_run": can_run,
        "issues": issues,
        "counts": {"errors": len(errors), "warnings": sum(item["severity"] == "warning" for item in issues)},
        "stages": stages,
        "geometry_coverage": coverage,
        "normalized": {
            **({"chamber": chamber} if chamber is not None else {}),
            **({"radiated_emissions_standard": {key: reference_standard[key] for key in ("id", "classification", "platform") if key in reference_standard}} if reference_standard is not None else {}),
            "selected_nets": selected_nets,
            "return_nets": return_nets,
            "requested_analyses": analyses,
            "frequency": {"start_hz": start_hz, "stop_hz": stop_hz, "points": int(points or 0)},
            "environment": {"kind": environment_kind},
            "mesh": {"resolution_mm": resolution, "padding_cells": int(padding or 0)},
            "max_solver_time_s": max_solver_time,
            "excitation": {"mode": excitation_mode, "ports": ports},
            "net_metrics": metrics,
        },
        "solver_recommendation": recommendation,
        "reference_standard": reference_standard,
        "validity": {
            "model_status": "screening_only",
            "statement": "Preflight validates setup completeness; it does not validate radiated-emission accuracy.",
        },
    }


def screen_emi_setup(
    design: DesignIR,
    setup: Dict[str, Any],
    solver_catalog: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Rank selected nets using supplied pre-pass metrics and attach provenance."""

    preflight = validate_emi_setup(design, setup, solver_catalog)
    if not preflight["can_screen"]:
        return {
            "contract": EMI_WORKFLOW_CONTRACT,
            "status": "blocked",
            "model_status": "unsupported",
            "preflight": preflight,
            "screening": None,
            "message": "EMI screening requires a valid setup and complete non-zero electrical pre-pass metrics.",
        }
    screening = recommend_emi_nets(preflight["normalized"]["net_metrics"])
    geometry_by_net = {row["net"]: row for row in preflight["geometry_coverage"]}
    ranked = [
        {**item, "geometry": geometry_by_net.get(item["net"], {})}
        for item in screening["recommended_nets"]
    ]
    return {
        "contract": EMI_WORKFLOW_CONTRACT,
        "status": "completed_screening_only",
        "model_status": "approximate",
        "preflight": preflight,
        "screening": {**screening, "recommended_nets": ranked},
        "provenance": {
            "inputs": "user, measured, or prior-solver metric magnitudes supplied in the EMI setup",
            "algorithm": "weighted normalized log-feature ranking",
            "field_solver_executed": False,
            "compliance_prediction": False,
        },
    }
