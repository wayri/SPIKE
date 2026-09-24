# SPDX-License-Identifier: MIT
"""Admission boundary for process-extension analysis results."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .contracts import AnalysisResult, DesignIR


MAX_VISUAL_SAMPLES = 250_000
MAX_PROBES = 100_000
MAX_DEPTH = 32
MODEL_STATUSES = {"experimental", "approximate", "unvalidated", "validated", "reference_validated"}


def _finite_tree(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("Extension result nesting exceeds the supported limit.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("Extension result contains a non-finite number.")
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Extension result object keys must be strings.")
        for item in value.values():
            _finite_tree(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _finite_tree(item, depth=depth + 1)
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise ValueError("Extension result contains a non-JSON value.")


def _number(value: Any, label: str) -> None:
    try:
        finite = math.isfinite(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else False
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"Extension visualization {label} must be a finite number.")


def design_binding(design: Any) -> dict[str, str]:
    if isinstance(design, DesignIR):
        design = design.to_dict()
    if not isinstance(design, dict) or design.get("contract") != "spike/v1":
        raise ValueError("Analysis extensions require a spike/v1 DesignIR in context.design.")
    identifier = design.get("design_id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("Analysis extension DesignIR requires a nonempty design_id.")
    _finite_tree(design)
    canonical = json.dumps(design, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return {"design_id": identifier, "digest_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}


def admit_analysis_result(raw: Any, binding: dict[str, str], *, extension_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - set(AnalysisResult.__dataclass_fields__):
        raise ValueError("Extension analysis_result has unsupported fields.")
    if raw.get("contract") != "spike/v1" or raw.get("status") not in {"completed", "completed_with_warnings"}:
        raise ValueError("Extension analysis_result must be a completed spike/v1 AnalysisResult.")
    if not isinstance(raw.get("analysis_id"), str) or not raw["analysis_id"].strip():
        raise ValueError("Extension analysis_result requires analysis_id.")
    if not isinstance(raw.get("mode"), str) or not raw["mode"].strip():
        raise ValueError("Extension analysis_result requires mode.")
    if raw.get("model_status") not in MODEL_STATUSES:
        raise ValueError("Extension analysis_result requires an explicit supported model_status.")
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("design_id") != binding["design_id"] or provenance.get("design_digest_sha256") != binding["digest_sha256"]:
        raise ValueError("Extension analysis_result provenance does not match the input DesignIR binding.")
    if not isinstance(provenance.get("solver"), str) or not provenance["solver"].strip():
        raise ValueError("Extension analysis_result requires provenance.solver.")
    if raw["model_status"] in {"validated", "reference_validated"} and not provenance.get("validation_evidence"):
        raise ValueError("Validated external results require provenance.validation_evidence.")
    for key in ("summary", "fields", "networks"):
        if not isinstance(raw.get(key), dict):
            raise ValueError(f"Extension analysis_result.{key} must be an object.")
    for key, limit in (("probes", MAX_PROBES), ("issues", MAX_PROBES)):
        value = raw.get(key)
        if not isinstance(value, list) or len(value) > limit or any(not isinstance(item, dict) for item in value):
            raise ValueError(f"Extension analysis_result.{key} must be a bounded array of objects.")
    for issue in raw["issues"]:
        if (not isinstance(issue.get("code"), str) or not issue["code"]
                or issue.get("severity") not in {"info", "warning", "error"}
                or not isinstance(issue.get("message"), str) or not issue["message"]):
            raise ValueError("Extension analysis_result issues require code, severity, and message.")
    visual = raw["fields"].get("visualization")
    if visual is not None:
        if not isinstance(visual, dict) or visual.get("schema") != "spike/result-visualization/v1":
            raise ValueError("Extension visualization requires spike/result-visualization/v1.")
        count = 0
        for field_type in ("scalar_fields", "vector_fields"):
            fields = visual.get(field_type, {})
            if not isinstance(fields, dict):
                raise ValueError(f"Extension visualization.{field_type} must be an object.")
            for name, samples in fields.items():
                if not isinstance(name, str) or not name:
                    raise ValueError("Extension visualization field names must be nonempty strings.")
                if not isinstance(samples, list) or any(not isinstance(sample, dict) for sample in samples):
                    raise ValueError("Extension visualization fields require arrays of sample objects.")
                count += len(samples)
                if count > MAX_VISUAL_SAMPLES:
                    raise ValueError("Extension visualization exceeds the sample limit.")
                for sample in samples:
                    for coordinate in ("x_mm", "y_mm"):
                        _number(sample.get(coordinate), coordinate)
                    if "z_mm" in sample:
                        _number(sample["z_mm"], "z_mm")
                    if field_type == "vector_fields":
                        vector = sample.get("vector")
                        if not isinstance(vector, list) or len(vector) != 3:
                            raise ValueError("Extension visualization vector must have three components.")
                        for component in vector:
                            _number(component, "vector component")
                        _number(sample.get("magnitude"), "magnitude")
                    else:
                        _number(sample.get("value"), "value")
        if "mesh" in visual and not isinstance(visual["mesh"], (dict, list)):
            raise ValueError("Extension visualization.mesh must be an object or array.")
    _finite_tree(raw)
    # Preserve reported data and add only the origin attribution established by the host.
    return {**raw, "provenance": {**provenance, "extension_id": extension_id}}
