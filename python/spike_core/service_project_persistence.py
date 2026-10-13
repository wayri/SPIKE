"""Portable result and visual state at the desktop/package boundary."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .spider_v2 import SpiDeRV2
from .project_package import ProjectPackageError, _sha256, read_project
from .multiboard_identity import migrate_legacy_result_assembly_digest
from .project_state_artifacts import externalize_result_state, hydrate_result_state, read_verified_artifacts
from .project_visual_artifacts import prepare_visual_artifacts, read_saved_visual_stage
from .project_parallel_state import admit_payload_parallel


def project_for_desktop(payload: dict, projected: dict, *, copy_project: bool = True) -> dict:
    """A binary manufacturing source reopens through its canonical geometry."""
    projected = copy.deepcopy(projected) if copy_project else dict(projected)
    projected["analysis"] = dict(projected.get("analysis") or {})
    if "parallel_execution" in payload.get("analyses", {}):
        projected["analysis"]["parallel_execution"] = copy.deepcopy(payload["analyses"]["parallel_execution"])
    canonical = payload.get("design_ir") or {}
    design = dict(projected.get("design") or {})
    projected["design"] = design
    design["canonical_design"] = canonical
    if not design.get("source_board") and canonical.get("contract") == "spike/design-ir/v2":
        source_format = str((canonical.get("source") or {}).get("source_format", ""))
        if source_format not in {"kicad", "kicad_pcb"}:
            snapshot = {"contract": "spike/design-snapshot/v1",
                        "design": SpiDeRV2.from_dict(canonical).to_v1(allow_unprojected_arcs=True).to_dict(),
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
        studies = ((snapshot.get("assembly_ir") or {}).get("extensions") or {}).get("spike.multiboard-studies", {})
        if isinstance(studies, dict):
            for study in studies.values():
                if isinstance(study, dict):
                    study.pop("result", None)
        analysis = snapshot.get("analysis")
        if isinstance(analysis, dict):
            parallel = analysis.get("parallel_execution")
            if isinstance(parallel, dict):
                parallel["runs"] = []
            for key in ("latest_result", "active_result", "pdn_review"):
                analysis.pop(key, None)
            analysis["result_history"] = []
            retained_em = analysis.get("retained_assembly_em")
            if isinstance(retained_em, dict):
                retained_em["result"] = None
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
        volume_study = analyses.get("assembly_volume_electrothermal")
        if isinstance(volume_study, dict):
            volume_study["result"] = None
        field_study = analyses.get("assembly_field_study")
        if field_study is not None:
            from .assembly_field_study import import_assembly_field_study, export_assembly_field_study
            admitted = import_assembly_field_study(field_study)
            analyses["assembly_field_study"] = export_assembly_field_study(
                admitted["request"], admitted["problem"], admitted["result"], include_results=False,
            )
    clean["results"] = {}
    studies = ((clean.get("assembly_ir") or {}).get("extensions") or {}).get("spike.multiboard-studies", {})
    if isinstance(studies, dict):
        for study in studies.values():
            if isinstance(study, dict):
                study.pop("result", None)
    extensions = clean.get("extensions")
    if isinstance(extensions, dict) and isinstance(extensions.get("legacy"), dict):
        clear_desktop(extensions["legacy"])
    return clean


def prepare_persistent_state(payload: dict, visuals: Any, members: dict[str, bytes]) -> tuple[dict, dict[str, bytes]]:
    """Move full results out of metadata, retaining exact future result fields."""
    admit_payload_parallel(payload, resolve=lambda name: members[name])
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
        value = json.loads(data[reference["path"]])
        if isinstance(value, dict) and value.get("contract") in {
            "spike/multiboard-circuit-result/v1", "spike/multiboard-thermal-result/v1", "spike/multiboard-em-result/v1"
        }:
            opened = read_project(path)
            if opened.manifest.get("manifest_payload_sha256") != digest:
                raise ProjectPackageError("The package changed during the saved result read; reopen it.")
            value = migrate_saved_assembly_results(value, opened.payload.get("assembly_ir"))
        return {"value": value}
    index = params.get("index")
    if not isinstance(index, dict):
        raise ProjectPackageError("A saved visual index is required.")
    return read_saved_visual_stage(path, index, str(params.get("stage", "")), digest)


def migrate_saved_assembly_results(value: Any, original_assembly: Any) -> Any:
    """Upgrade old result identities only from verified, pre-transport metadata."""
    if not isinstance(original_assembly, dict):
        return value
    if isinstance(value, list):
        return [migrate_saved_assembly_results(item, original_assembly) for item in value]
    if not isinstance(value, dict):
        return value
    if value.get("contract") in {"spike/parallel-workspace/v1", "spike/parallel-batch-result/v1", "spike/cluster-batch-result/v1"}:
        return value  # Execution digests bind the original immutable results.
    if value.get("contract") in {
        "spike/multiboard-circuit-result/v1", "spike/multiboard-thermal-result/v1", "spike/multiboard-em-result/v1"
    }:
        return migrate_legacy_result_assembly_digest(value, original_assembly)
    updated = {key: migrate_saved_assembly_results(item, original_assembly) for key, item in value.items()}
    result = updated.get("result")
    if isinstance(result, dict) and result.get("assembly_identity_migration") and "assembly_digest" in updated:
        migration = result["assembly_identity_migration"]
        if updated["assembly_digest"] == migration["from"]:
            updated["assembly_digest"] = migration["to"]
    return updated


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
