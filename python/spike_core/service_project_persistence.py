"""Portable result and visual state at the desktop/package boundary."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .design_ir_v2 import DesignIRV2
from .project_package import ProjectPackageError, _sha256
from .project_state_artifacts import externalize_result_state, hydrate_result_state, read_verified_artifacts
from .project_visual_artifacts import prepare_visual_artifacts, read_saved_visual_stage


def project_for_desktop(payload: dict, projected: dict) -> dict:
    """A binary manufacturing source reopens through its canonical geometry."""
    projected = copy.deepcopy(projected)
    canonical = payload.get("design_ir") or {}
    design = projected.setdefault("design", {})
    design["canonical_design"] = canonical
    if not design.get("source_board") and canonical.get("contract") == "spike/design-ir/v2":
        source_format = str((canonical.get("source") or {}).get("source_format", ""))
        if source_format not in {"kicad", "kicad_pcb"}:
            snapshot = {"contract": "spike/design-snapshot/v1",
                        "design": DesignIRV2.from_dict(canonical).to_v1().to_dict(),
                        "canonical_design": canonical, "report": canonical.get("metadata", {}).get("import_report", {})}
            design.update(source_board=json.dumps(snapshot), source_format="spike-normalized",
                          source_file="saved-design.spike-design.json")
    visuals = (payload.get("extensions") or {}).get("board_visuals")
    if visuals:
        projected["board_visuals"] = visuals
    return projected


def without_saved_results(payload: dict) -> dict:
    """Keep project setup while omitting persisted simulation outputs."""
    clean = copy.deepcopy(payload)

    def clear_desktop(snapshot: dict) -> None:
        snapshot.pop("results", None)
        analysis = snapshot.get("analysis")
        if isinstance(analysis, dict):
            for key in ("latest_result", "active_result", "pdn_review"):
                analysis.pop(key, None)
            analysis["result_history"] = []
            si = analysis.get("si")
            if isinstance(si, dict):
                si.pop("latest_channel_result", None)
        emi = snapshot.get("emi")
        if isinstance(emi, dict):
            for key in ("preflight", "screening", "field_result"):
                emi.pop(key, None)
        thermal = snapshot.get("thermal")
        if isinstance(thermal, dict) and isinstance(thermal.get("scenario"), dict):
            thermal["scenario"].pop("result", None)
            thermal["scenario"].pop("field_result", None)

    analyses = clean.get("analyses")
    if isinstance(analyses, dict):
        clear_desktop({"analysis": analyses})
    clean["results"] = {}
    extensions = clean.get("extensions")
    if isinstance(extensions, dict) and isinstance(extensions.get("legacy"), dict):
        clear_desktop(extensions["legacy"])
    return clean


def prepare_persistent_state(payload: dict, visuals: Any, members: dict[str, bytes]) -> tuple[dict, dict[str, bytes]]:
    """Move full results out of metadata, retaining exact future result fields."""
    payload, result_members = externalize_result_state(payload)
    members = {**members, **result_members}
    if visuals is not None:
        source_digest = str((payload.get("design_ir", {}).get("source") or {}).get("source_digest", ""))
        index, visual_members = prepare_visual_artifacts(visuals, source_digest)
        payload.setdefault("extensions", {})["board_visuals"] = index
        members.update(visual_members)
    # Encoded desktop visuals belong in artifact members, never legacy metadata.
    legacy = payload.get("extensions", {}).get("legacy")
    if isinstance(legacy, dict):
        legacy.pop("board_visuals", None)
    referenced_artifacts: set[str] = set()
    def validate_reference(value):
        if isinstance(value, list):
            for child in value:
                validate_reference(child)
        elif isinstance(value, dict):
            if value.get("contract") == "spike/state-artifact-reference/v1":
                data = members.get(value.get("path"))
                if data is None or len(data) != value.get("bytes") or _sha256(data) != value.get("sha256"):
                    raise ProjectPackageError("A saved result reference has no matching verified artifact; reopen its original project.")
                referenced_artifacts.add(value["path"])
            else:
                for child in value.values():
                    validate_reference(child)
    validate_reference(payload)
    members = {name: data for name, data in members.items()
               if not name.startswith("state/artifacts/") or name in referenced_artifacts}
    return payload, members


def read_persistent_artifact(method: str, params: dict) -> dict:
    path = Path(str(params.get("path", "")))
    digest = str(params.get("expected_manifest_payload_sha256", ""))
    if method == "read_project_state_artifact":
        reference = params.get("reference")
        if not isinstance(reference, dict):
            raise ProjectPackageError("A saved result reference is required.")
        data = read_verified_artifacts(path, [reference], expected_manifest_payload_sha256=digest,
                                       allowed_prefix="state/artifacts/")
        return {"value": json.loads(data[reference["path"]])}
    index = params.get("index")
    if not isinstance(index, dict):
        raise ProjectPackageError("A saved visual index is required.")
    return read_saved_visual_stage(path, index, str(params.get("stage", "")), digest)


def merge_future_fields(base: Any, updated: Any) -> Any:
    """Maps retain unknown fields; explicit values and list membership are edits."""
    if isinstance(base, dict) and base.get("contract") == "spike/state-artifact-reference/v1":
        return updated
    if isinstance(base, dict) and isinstance(updated, dict):
        return {**base, **{key: merge_future_fields(base.get(key), value) for key, value in updated.items()}}
    if isinstance(base, list) and isinstance(updated, list):
        def identity(item):
            return next((item[key] for key in ("id", "design_id", "analysis_id", "ref") if key in item), None) if isinstance(item, dict) else None
        indexed = {identity(item): item for item in base if isinstance(identity(item), (str, int))}
        return [merge_future_fields(indexed.get(identity(item)), item) if isinstance(identity(item), (str, int)) else item for item in updated]
    return updated
