# SPDX-License-Identifier: Apache-2.0
"""Worker routing for bounded engineering reviews and calculators."""
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict
from .contracts import SpiDeR, ValidationIssue
from .engineering_review import review_engineering, quick_engineering_tool


def handle_engineering_review(method, params):
    try:
        if not isinstance(params, dict) or set(params) != {"request"}:
            raise ValueError("An explicit engineering request is required.")
        operation = review_engineering if method == "review_engineering" else quick_engineering_tool
        return {"ok": True, "result": operation(params["request"])}
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": str(exc), "type": type(exc).__name__}


def validate_design(design: SpiDeR) -> Dict[str, Any]:
    issues = [item if isinstance(item, ValidationIssue) else ValidationIssue(**item) for item in design.issues]
    if (not design.source_path or not Path(design.source_path).exists()) and not design.metadata.get("source_embedded"):
        issues.append(ValidationIssue(
            code="SOURCE_NOT_FOUND",
            severity="error",
            message="The source design file is not available.",
            suggestion="Re-import the board or restore the source path.",
        ))
    placeholders = [item.get("reference") for item in design.components if item.get("reference") in {"REF**", "U?", "?"}]
    if placeholders:
        issues.append(ValidationIssue(
            code="COMPONENT_REFERENCE_AMBIGUOUS",
            severity="warning",
            message=f"{len(placeholders)} component references are ambiguous.",
            suggestion="Resolve placeholder references before component-level PI attribution.",
        ))
    if not design.tracks and not design.zones:
        issues.append(ValidationIssue(
            code="NO_CONDUCTIVE_GEOMETRY",
            severity="error",
            message="No tracks or copper zones are available for PI analysis.",
            suggestion="Import a routed board or provide an interchange export.",
        ))
    if len(design.layers) < 2:
        issues.append(ValidationIssue(
            code="LAYER_MODEL_INCOMPLETE",
            severity="warning",
            message="The layer model is incomplete for return-path and HF analysis.",
            suggestion="Provide a complete board stackup.",
        ))
    return {
        "contract": design.contract,
        "valid": not any(i.severity == "error" for i in issues),
        "issues": [asdict(i) for i in issues],
        "counts": {
            "errors": sum(i.severity == "error" for i in issues),
            "warnings": sum(i.severity == "warning" for i in issues),
        },
    }
