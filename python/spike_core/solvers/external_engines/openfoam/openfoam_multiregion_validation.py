"""Evidence-only validator for runnable OpenFOAM v2606 multi-region cases.

It accepts outputs which a real OpenFOAM/postProcess run wrote and which bind
back to a verified runnable manifest.  It deliberately produces *candidate*
evidence; it does not establish solver correlation or production readiness.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .openfoam_multiregion_execution import MultiRegionExecutionError, load_verified_runnable_case


EVIDENCE_CONTRACT = "spike/openfoam-multiregion-validation-evidence/v1"
RECORD_CONTRACT = "spike/openfoam-multiregion-validation-record/v1"
MAX_ARTIFACT_BYTES = 32 * 1024**2


def _finite(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise MultiRegionExecutionError(f"{label} must be finite.")
    return float(value)


def _load_record(root: Path, value: Mapping[str, Any] | None) -> tuple[dict[str, Any], str]:
    if value is not None:
        record = dict(value)
        return record, "explicit_result_record"
    path = root / "postProcessing" / "spike" / "validation-record.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise MultiRegionExecutionError("No bounded postProcessing validation artifact is available.")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MultiRegionExecutionError("Validation artifact is not valid UTF-8 JSON.") from exc
    if not isinstance(record, dict):
        raise MultiRegionExecutionError("Validation artifact must be an object.")
    return record, hashlib.sha256(path.read_bytes()).hexdigest()


def _conservation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {"status": "incomplete", "passed": False, "reason": "Missing explicit input and boundary heat balance."}
    try:
        tolerance = _finite(raw.get("relative_tolerance"), "conservation relative_tolerance")
        if all(key in raw for key in ("input_energy_j", "boundary_energy_j", "stored_energy_change_j")):
            input_value = _finite(raw.get("input_energy_j"), "conservation input_energy_j")
            boundary_value = _finite(raw.get("boundary_energy_j"), "conservation boundary_energy_j")
            stored_value = _finite(raw.get("stored_energy_change_j"), "conservation stored_energy_change_j")
            mode = "transient_energy"
            values = {"input_energy_j": input_value, "boundary_energy_j": boundary_value, "stored_energy_change_j": stored_value}
        else:
            input_value = _finite(raw.get("input_power_w"), "conservation input_power_w")
            boundary_value = _finite(raw.get("boundary_power_w"), "conservation boundary_power_w")
            stored_value = 0.0
            mode = "steady_power"
            values = {"input_power_w": input_value, "boundary_power_w": boundary_value}
    except MultiRegionExecutionError as exc:
        return {"status": "incomplete", "passed": False, "reason": str(exc)}
    if input_value <= 0 or boundary_value < 0 or stored_value < 0 or tolerance <= 0:
        return {"status": "incomplete", "passed": False, "reason": "Conservation input/tolerance must be positive and output/storage terms non-negative."}
    residual = abs(input_value - boundary_value - stored_value) / abs(input_value)
    return {"status": "evaluated", "mode": mode, **values, "relative_residual": residual,
            "relative_tolerance": tolerance, "passed": residual <= tolerance}


def _convergence(raw: Any, *, kind: str, independent_key: str) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or not isinstance(raw.get("levels"), list):
        return {"status": "incomplete", "passed": False, "reason": f"Missing explicit {kind} refinement levels."}
    try:
        tolerance = _finite(raw.get("relative_tolerance"), f"{kind} relative_tolerance")
    except MultiRegionExecutionError as exc:
        return {"status": "incomplete", "passed": False, "reason": str(exc)}
    levels = raw["levels"]
    if len(levels) < 3 or tolerance <= 0:
        return {"status": "incomplete", "passed": False, "reason": f"{kind} requires at least three levels and a positive tolerance."}
    try:
        independent = [_finite(item.get(independent_key), f"{kind} {independent_key}") if isinstance(item, Mapping) else float("nan") for item in levels]
        metric = [_finite(item.get("maximum_temperature_k"), f"{kind} maximum_temperature_k") if isinstance(item, Mapping) else float("nan") for item in levels]
    except MultiRegionExecutionError as exc:
        return {"status": "incomplete", "passed": False, "reason": str(exc)}
    monotonic = (all(right > left for left, right in zip(independent, independent[1:])) if kind == "mesh" else all(right < left for left, right in zip(independent, independent[1:])))
    if not monotonic or any(value <= 0 for value in independent):
        return {"status": "incomplete", "passed": False, "reason": f"{kind} level ordering is not a strict refinement sequence."}
    deltas = [abs(right - left) / max(abs(right), 1e-30) for left, right in zip(metric, metric[1:])]
    return {"status": "evaluated", "levels": [dict(item) for item in levels], "successive_relative_changes": deltas,
            "finest_relative_change": deltas[-1], "relative_tolerance": tolerance, "passed": deltas[-1] <= tolerance}


def import_v2606_validation_evidence(case_dir: str | Path, *, result_record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return candidate evidence only when it binds to a verified manifest."""
    root, manifest = load_verified_runnable_case(case_dir)
    record, origin = _load_record(root, result_record)
    if record.get("contract") != RECORD_CONTRACT or record.get("manifest_digest") != manifest.get("manifest_digest"):
        raise MultiRegionExecutionError("Validation record is not bound to the verified runnable case manifest.")
    conservation = _conservation(record.get("conservation"))
    mesh = _convergence(record.get("mesh_convergence"), kind="mesh", independent_key="cells")
    time = _convergence(record.get("time_convergence"), kind="time", independent_key="delta_t_s")
    passed = conservation["passed"] and mesh["passed"] and time["passed"]
    return {
        "contract": EVIDENCE_CONTRACT,
        "status": "candidate_evidence_complete" if passed else "candidate_evidence_incomplete_or_failed",
        "candidate_passed": passed,
        "conservation": conservation,
        "mesh_convergence": mesh,
        "time_convergence": time,
        "provenance": {"solver": "chtMultiRegionFoam", "required_runtime_version": "2606", "manifest_digest": manifest["manifest_digest"], "record_origin": origin},
        "qualification": {"production_qualified": False, "reason": "Conservation and refinement records are candidate evidence only; reference/measurement correlation and release review remain required."},
    }


__all__ = ["EVIDENCE_CONTRACT", "RECORD_CONTRACT", "import_v2606_validation_evidence"]
