"""Bounded, fail-closed normalization for PI batch analysis reports.

This module deliberately consumes the CLI/service batch envelope rather than a
UI-specific shape.  It converts mixed DC, AC, and transient results into a
small stable data contract that HTML, PDF, and future cloud report renderers can
consume without interpreting arbitrary solver payloads.

The implementation is stdlib-only and does not invoke solvers or write files.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Mapping, Sequence


BATCH_RESULT_CONTRACT = "spike/analysis-batch-result/v1"
REPORT_DATA_CONTRACT = "spike/pi-batch-report-data/v1"
_MAX_JOBS = 1_000
_MAX_ISSUES_PER_JOB = 100
_MAX_TOTAL_ISSUES = 10_000
_VALID_MODES = frozenset(("dc", "ac", "transient"))
_VALID_STATUSES = frozenset(("completed", "blocked", "failed", "cancelled", "not_run"))


class BatchReportError(ValueError):
    """Raised when a batch result cannot be safely converted to report data."""


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BatchReportError(f"{path} must be an object.")
    return value


def _require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatchReportError(f"{path} must be a non-empty string.")
    return value


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise BatchReportError(f"{path} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BatchReportError(f"{path} must be a finite number.") from exc
    if not math.isfinite(number):
        raise BatchReportError(f"{path} must be a finite number.")
    return number


def _optional_number(value: Any, path: str) -> float | None:
    return None if value is None else _finite_number(value, path)


def _as_strings(value: Any, path: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BatchReportError(f"{path} must be an array of strings.")
    result: List[str] = []
    for index, item in enumerate(value):
        result.append(_require_string(item, f"{path}[{index}]"))
    return result


def _issues(value: Any, path: str, job_id: str) -> List[Dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise BatchReportError(f"{path} must be an array.")
    if len(value) > _MAX_ISSUES_PER_JOB:
        raise BatchReportError(f"{path} exceeds the {_MAX_ISSUES_PER_JOB} issue limit.")
    result: List[Dict[str, str]] = []
    for index, raw_issue in enumerate(value):
        issue = _require_mapping(raw_issue, f"{path}[{index}]")
        result.append({
            "job_id": job_id,
            "severity": str(issue.get("severity", "info")),
            "code": str(issue.get("code", "SPIKE-REPORT-UNKNOWN")),
            "message": str(issue.get("message", "No message supplied.")),
            "path": str(issue.get("path", "")),
        })
    return result


def _summary_metrics(summary: Mapping[str, Any], mode: str, path: str) -> Dict[str, float]:
    """Copy only reportable scalar metrics from a solver summary."""

    common = (
        "max_voltage_drop_v",
        "max_current_density_a_mm2",
        "max_current_a",
        "total_power_loss_w",
        "total_copper_loss_w",
        "minimum_voltage_v",
        "maximum_voltage_v",
    )
    mode_keys = {
        "dc": (),
        "ac": ("impedance_min_ohm", "impedance_max_ohm", "impedance_at_target_ohm"),
        "transient": ("peak_voltage_v", "minimum_voltage_v", "peak_current_a", "time_steps", "saved_frames"),
    }
    metrics: Dict[str, float] = {}
    for key in (*common, *mode_keys[mode]):
        if key in summary and summary[key] is not None:
            metrics[key] = _finite_number(summary[key], f"{path}.{key}")
    return metrics


def _impedance_metrics(networks: Mapping[str, Any], path: str) -> Dict[str, float]:
    """Derive AC impedance extrema from normalized parasitic response points."""

    parasitics = networks.get("parasitics", [])
    if not isinstance(parasitics, list):
        raise BatchReportError(f"{path}.parasitics must be an array.")
    magnitudes: List[float] = []
    for network_index, raw_network in enumerate(parasitics):
        network = _require_mapping(raw_network, f"{path}.parasitics[{network_index}]")
        points = network.get("impedance", [])
        if not isinstance(points, list):
            raise BatchReportError(f"{path}.parasitics[{network_index}].impedance must be an array.")
        for point_index, raw_point in enumerate(points):
            point = _require_mapping(raw_point, f"{path}.parasitics[{network_index}].impedance[{point_index}]")
            if "magnitude_ohm" in point:
                magnitudes.append(_finite_number(
                    point["magnitude_ohm"],
                    f"{path}.parasitics[{network_index}].impedance[{point_index}].magnitude_ohm",
                ))
    if not magnitudes:
        return {}
    return {"impedance_min_ohm": min(magnitudes), "impedance_max_ohm": max(magnitudes)}


def _job_report(raw_job: Any, position: int) -> Dict[str, Any]:
    job = _require_mapping(raw_job, f"results[{position}]")
    job_id = _require_string(job.get("id"), f"results[{position}].id")
    index = job.get("index", position)
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise BatchReportError(f"results[{position}].index must be a non-negative integer.")

    has_result = "result" in job
    has_error = "error" in job
    if has_result == has_error:
        raise BatchReportError(f"results[{position}] must contain exactly one of result or error.")
    if has_error:
        return {
            "id": job_id,
            "index": index,
            "status": "failed",
            "mode": "unknown",
            "nets": [],
            "solver": "",
            "model_status": "failed",
            "metrics": {},
            "issues": [{
                "job_id": job_id,
                "severity": "error",
                "code": "SPIKE-REPORT-BATCH-JOB-FAILED",
                "message": str(job["error"]),
                "path": "",
            }],
            "provenance": {},
        }

    result = _require_mapping(job["result"], f"results[{position}].result")
    status = _require_string(result.get("status"), f"results[{position}].result.status")
    if status not in _VALID_STATUSES:
        raise BatchReportError(f"results[{position}].result.status is unsupported: {status}.")
    mode = _require_string(result.get("mode"), f"results[{position}].result.mode")
    if mode not in _VALID_MODES:
        raise BatchReportError(f"results[{position}].result.mode is unsupported: {mode}.")
    model_status = _require_string(result.get("model_status"), f"results[{position}].result.model_status")
    summary = _require_mapping(result.get("summary", {}), f"results[{position}].result.summary")
    provenance = _require_mapping(result.get("provenance", {}), f"results[{position}].result.provenance")
    nets = _as_strings(summary.get("net_names", result.get("net_names", [])), f"results[{position}].result.net_names")
    solver = str(provenance.get("solver", provenance.get("solver_plugin", result.get("solver_id", ""))))
    metrics = _summary_metrics(summary, mode, f"results[{position}].result.summary")
    if mode == "ac":
        derived = _impedance_metrics(_require_mapping(result.get("networks", {}), f"results[{position}].result.networks"), f"results[{position}].result.networks")
        metrics = {**derived, **metrics}
    return {
        "id": job_id,
        "index": index,
        "status": status,
        "mode": mode,
        "nets": nets,
        "solver": solver,
        "model_status": model_status,
        "metrics": metrics,
        "issues": _issues(result.get("issues", []), f"results[{position}].result.issues", job_id),
        "provenance": {
            key: provenance[key]
            for key in ("solver", "solver_plugin", "solver_version", "formulation", "validation", "runtime")
            if key in provenance
        },
    }


def normalize_pi_batch_report(batch_result: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a bounded batch result into ``spike/pi-batch-report-data/v1``.

    Raises ``BatchReportError`` for any malformed envelope or non-finite scalar.
    The output is deliberately constrained to report metadata and numeric metrics;
    it does not carry raw meshes, fields, board geometry, or arbitrary extensions.
    """

    batch = _require_mapping(batch_result, "batch_result")
    if batch.get("contract") != BATCH_RESULT_CONTRACT:
        raise BatchReportError(f"Expected {BATCH_RESULT_CONTRACT}.")
    results = batch.get("results")
    if not isinstance(results, list) or not results:
        raise BatchReportError("batch_result.results must be a non-empty array.")
    if len(results) > _MAX_JOBS:
        raise BatchReportError(f"batch_result.results exceeds the {_MAX_JOBS} job limit.")

    jobs = [_job_report(raw_job, position) for position, raw_job in enumerate(results)]
    all_issues = [issue for job in jobs for issue in job["issues"]]
    if len(all_issues) > _MAX_TOTAL_ISSUES:
        raise BatchReportError(f"batch_result produces more than {_MAX_TOTAL_ISSUES} report issues.")
    if len({job["id"] for job in jobs}) != len(jobs):
        raise BatchReportError("batch_result.results contains duplicate job ids.")

    counts = {status: sum(job["status"] == status for job in jobs) for status in _VALID_STATUSES}
    modes = {mode: sum(job["mode"] == mode for job in jobs) for mode in _VALID_MODES}
    total_power_loss_w = sum(
        job["metrics"].get("total_power_loss_w", job["metrics"].get("total_copper_loss_w", 0.0))
        for job in jobs if job["status"] == "completed"
    )
    return {
        "contract": REPORT_DATA_CONTRACT,
        "status": "completed" if counts["failed"] == 0 and counts["blocked"] == 0 and counts["cancelled"] == 0 else "incomplete",
        "jobs": jobs,
        "totals": {
            "requested": len(jobs),
            "completed": counts["completed"],
            "blocked": counts["blocked"],
            "failed": counts["failed"],
            "cancelled": counts["cancelled"],
            "not_run": counts["not_run"],
            "dc_jobs": modes["dc"],
            "ac_jobs": modes["ac"],
            "transient_jobs": modes["transient"],
            "total_power_loss_w": total_power_loss_w,
            "issue_count": len(all_issues),
        },
        "issues": all_issues,
        "provenance": {
            "source_contract": BATCH_RESULT_CONTRACT,
            "source_status": str(batch.get("status", "unknown")),
            "aggregation": "spike.pi_batch_report",
            "aggregation_version": 1,
        },
    }
