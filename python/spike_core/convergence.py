"""Deterministic mesh-convergence studies for solver result sign-off."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite
from typing import Any, Callable, Dict, Iterable, List

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue


SolverRunner = Callable[[DesignIR, AnalysisSpec], AnalysisResult]

DC_METRICS = {
    "max_load_voltage_drop_v": 0.03,
    "total_copper_loss_w": 0.05,
    "effective_path_resistance_ohm": 0.05,
    "p95_current_density_a_mm2": 0.10,
}
DC_ADVISORY_METRICS = {
    "max_voltage_drop_v": 0.25,
    "max_current_density_a_mm2": 0.25,
}
AC_METRICS = {
    "resistance_start_ohm": 0.05,
    "resistance_stop_ohm": 0.05,
    "partial_inductance_h": 0.05,
}


def _relative_delta(before: float, after: float) -> float:
    return abs(after - before) / max(abs(before), abs(after), 1e-30)


def _metrics(result: AnalysisResult) -> Dict[str, float]:
    summary = result.summary
    values: Dict[str, float] = {}
    for key in set(DC_METRICS) | set(DC_ADVISORY_METRICS) | set(AC_METRICS):
        value = summary.get(key)
        if isinstance(value, (int, float)) and isfinite(value):
            values[key] = float(value)
    load_current = float(summary.get("total_load_current_a", 0) or 0)
    copper_loss = float(summary.get("total_copper_loss_w", 0) or 0)
    if isfinite(load_current) and isfinite(copper_loss) and load_current > 0 and copper_loss >= 0:
        values["effective_path_resistance_ohm"] = copper_loss / (load_current * load_current)
    return values


def _comparison(
    metric: str,
    threshold: float,
    previous: Dict[str, Any],
    current: Dict[str, Any],
    required: bool,
    absolute_tolerance: float | None = None,
) -> Dict[str, Any]:
    before = previous["metrics"].get(metric)
    after = current["metrics"].get(metric)
    available = before is not None and after is not None
    delta = _relative_delta(float(before), float(after)) if available else None
    absolute_delta = abs(float(after) - float(before)) if available else None
    relative_passed = bool(available and delta is not None and delta <= threshold)
    absolute_passed = bool(
        available
        and absolute_tolerance is not None
        and absolute_delta is not None
        and absolute_delta <= absolute_tolerance
    )
    passed = relative_passed or absolute_passed
    return {
        "metric": metric,
        "coarse_value": before,
        "fine_value": after,
        "relative_delta": delta,
        "absolute_delta": absolute_delta,
        "tolerance": threshold,
        "absolute_tolerance": absolute_tolerance,
        "pass_basis": "relative" if relative_passed else "absolute" if absolute_passed else "none",
        "required": required,
        "status": "passed" if passed else "failed" if available else "unavailable",
        "meaning": (
            "required numerical stability metric"
            if required
            else "mesh-sensitive hotspot monitor; reported but not used alone to block sign-off"
        ),
    }


def _level_spec(spec: AnalysisSpec, factor: float, index: int) -> AnalysisSpec:
    mesh = dict(spec.mesh)
    target = float(mesh.get("target_size_mm", 1.0))
    zone = float(mesh.get("zone_cell_mm", target))
    mesh["target_size_mm"] = target * factor
    mesh["zone_cell_mm"] = zone * factor
    # Refinement must not silently stop at the coarse-run conductor limit.
    growth = max(1.0, 1.0 / (factor * factor))
    for key in ("max_conductors", "max_zone_cells", "max_preview_cells"):
        if key in mesh and mesh[key] is not None:
            mesh[key] = min(int(max(1, float(mesh[key])) * growth), 2_000_000)
    return replace(
        spec,
        analysis_id=f"{spec.analysis_id or 'analysis'}-convergence-{index + 1}",
        mesh=mesh,
    )


def _refinement_comparison(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    """Check that changing the requested cell size refined the solved network."""
    counts = ("node_count", "edge_count")
    before = {key: previous.get(key) for key in counts}
    after = {key: current.get(key) for key in counts}
    available = all(
        isinstance(before[key], int) and isinstance(after[key], int)
        and before[key] > 0 and after[key] > 0
        for key in counts
    )
    passed = available and all(after[key] >= before[key] for key in counts) and any(
        after[key] > before[key] for key in counts
    )
    return {
        "metric": "resolved_mesh_growth",
        "coarse_value": before,
        "fine_value": after,
        "required": True,
        "status": "passed" if passed else "failed" if available else "unavailable",
        "meaning": "the finer solve must contain more resolved nodes or branches without losing either count",
    }


def run_mesh_convergence(
    design: DesignIR,
    spec: AnalysisSpec,
    runner: SolverRunner,
    levels: Iterable[float] = (2.0, 1.0, 0.5),
    metric_tolerance: float | None = None,
    density_tolerance: float | None = None,
    minimum_levels: int = 3,
    stop_when_converged: bool = True,
) -> Dict[str, Any]:
    """Run ordered mesh refinements and return the fine result plus deltas."""

    factors = [float(value) for value in levels]
    if len(factors) < 2 or any(value <= 0 for value in factors):
        raise ValueError("Mesh convergence requires at least two positive refinement factors.")
    if any(next_value >= value for value, next_value in zip(factors, factors[1:])):
        raise ValueError("Mesh convergence factors must be strictly decreasing from coarse to fine.")
    if spec.mode not in {"dc", "ac", "broadband_hf"}:
        raise ValueError("Mesh convergence is currently defined for DC and quasi-static AC PI analyses.")

    minimum_levels = int(minimum_levels)
    if minimum_levels < 2 or minimum_levels > len(factors):
        raise ValueError("minimum_levels must be between two and the number of refinement factors.")

    defaults = DC_METRICS if spec.mode == "dc" else AC_METRICS
    thresholds = dict(defaults)
    advisory_thresholds = dict(DC_ADVISORY_METRICS) if spec.mode == "dc" else {}
    voltage_limit = float(
        spec.limits.get(
            "max_voltage_drop_v",
            float(spec.limits.get("max_voltage_drop_mv", 50.0)) / 1000.0,
        )
    )
    absolute_thresholds = (
        {"max_load_voltage_drop_v": max(1e-6, voltage_limit * 0.001)}
        if spec.mode == "dc"
        else {}
    )
    advisory_absolute_thresholds = (
        {"max_voltage_drop_v": absolute_thresholds["max_load_voltage_drop_v"]}
        if spec.mode == "dc"
        else {}
    )
    if metric_tolerance is not None:
        if metric_tolerance <= 0:
            raise ValueError("The convergence metric tolerance must be positive.")
        thresholds = {key: float(metric_tolerance) for key in thresholds}
    if density_tolerance is not None and "p95_current_density_a_mm2" in thresholds:
        if density_tolerance <= 0:
            raise ValueError("The current-density convergence tolerance must be positive.")
        thresholds["p95_current_density_a_mm2"] = float(density_tolerance)
        advisory_thresholds["max_current_density_a_mm2"] = max(float(density_tolerance), 0.25)

    level_records: List[Dict[str, Any]] = []
    final_result: AnalysisResult | None = None
    comparisons: List[Dict[str, Any]] = []
    comparison_history: List[Dict[str, Any]] = []
    converged = False
    for index, factor in enumerate(factors):
        level_spec = _level_spec(spec, factor, index)
        result = runner(design, level_spec)
        metrics = _metrics(result)
        final_result = result
        level_records.append({
            "index": index,
            "factor": factor,
            "target_size_mm": level_spec.mesh.get("target_size_mm"),
            "zone_cell_mm": level_spec.mesh.get("zone_cell_mm"),
            "status": result.status,
            "model_status": result.model_status,
            "metrics": metrics,
            "node_count": result.summary.get("node_count"),
            "edge_count": result.summary.get("edge_count", result.summary.get("filament_count")),
            "issues": [issue.__dict__ for issue in result.issues if issue.severity == "error"],
        })
        if result.status != "completed" or result.model_status not in {
            "approximate", "validated", "reference_validated"
        } or any(issue.severity == "error" for issue in result.issues):
            converged = False
            comparisons = []
            break
        if len(level_records) >= 2:
            previous, current = level_records[-2], level_records[-1]
            required = [
                _comparison(
                    metric,
                    threshold,
                    previous,
                    current,
                    True,
                    absolute_thresholds.get(metric),
                )
                for metric, threshold in thresholds.items()
            ]
            required.append(_refinement_comparison(previous, current))
            advisory = [
                _comparison(
                    metric,
                    threshold,
                    previous,
                    current,
                    False,
                    advisory_absolute_thresholds.get(metric),
                )
                for metric, threshold in advisory_thresholds.items()
            ]
            comparisons = required + advisory
            comparison_history.append({
                "coarse_level_index": previous["index"],
                "fine_level_index": current["index"],
                "signoff_eligible": len(level_records) >= minimum_levels,
                "comparisons": comparisons,
            })
            converged = len(level_records) >= minimum_levels and all(
                item["status"] == "passed" for item in required
            )
            if converged and stop_when_converged:
                break

    if final_result is None:
        raise RuntimeError("Mesh convergence did not execute a solver level.")

    peak_comparison = next(
        (item for item in comparisons if item["metric"] == "max_current_density_a_mm2"),
        None,
    )
    if converged and peak_comparison and peak_comparison["status"] != "passed":
        final_result.issues.append(ValidationIssue(
            code="CURRENT_DENSITY_PEAK_MESH_SENSITIVE",
            severity="warning",
            message="Global PI metrics converged, but the single-cell peak current density remains mesh-sensitive.",
            suggestion="Inspect the reported hotspot, copper corner, via transition, and local mesh quality before applying a current-density limit.",
            status="approximate",
        ))

    convergence_issue = ValidationIssue(
        code="MESH_CONVERGENCE_PASSED" if converged else "MESH_CONVERGENCE_FAILED",
        severity="info" if converged else "warning",
        message=(
            f"Mesh convergence passed after {len(level_records)} levels; required PI metrics are within configured tolerances."
            if converged else
            "Mesh convergence did not pass. Refine the mesh, repair failed geometry, or review singular current-density locations before sign-off."
        ),
        suggestion="" if converged else "Inspect the per-metric deltas and the fine-grid solver issues.",
        status="validated" if converged else "failed_to_converge",
    )
    final_result.issues.append(convergence_issue)
    final_result.summary = {
        **final_result.summary,
        "mesh_convergence_status": "passed" if converged else "failed_to_converge",
        "mesh_convergence_levels": len(level_records),
        "mesh_convergence_max_relative_delta": max(
            (float(item["relative_delta"]) for item in comparisons if item["required"] and item.get("relative_delta") is not None),
            default=None,
        ),
        "mesh_convergence_peak_density_advisory": peak_comparison["status"] if peak_comparison else "unavailable",
    }
    final_result.provenance = {
        **final_result.provenance,
        "mesh_convergence": {
            "contract": "spike/mesh-convergence/v1",
            "status": "passed" if converged else "failed_to_converge",
            "factors": factors,
            "thresholds": thresholds,
            "advisory_thresholds": advisory_thresholds,
            "absolute_thresholds": absolute_thresholds,
            "comparison_basis": "last_two_completed_refinement_levels",
            "minimum_levels": minimum_levels,
            "adaptive_stop": bool(stop_when_converged),
            "comparisons": comparisons,
            "comparison_history": comparison_history,
        },
    }
    return {
        "contract": "spike/mesh-convergence/v1",
        "status": "passed" if converged else "failed_to_converge",
        "can_sign_off": converged,
        "mode": spec.mode,
        "levels": level_records,
        "comparisons": comparisons,
        "comparison_history": comparison_history,
        "thresholds": thresholds,
        "advisory_thresholds": advisory_thresholds,
        "absolute_thresholds": absolute_thresholds,
        "result": final_result.to_dict(),
        "limitations": [
            "A passing mesh study establishes numerical stability for the selected geometry, terminals, loads, and solver settings only.",
            "It does not validate material inputs, package models, manufacturing tolerances, or omitted physics.",
        ],
    }
