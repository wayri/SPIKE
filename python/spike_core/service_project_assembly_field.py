# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound persistence for admitted assembly field-study records."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, Mapping

from .multiboard_identity import canonical_json_digest
from .project_package import ProjectPackageError, read_project, write_spike_package
from .service_helpers import error_response, operation_id


STUDY_KEY = "assembly_field_study"


class AssemblyFieldStudyStale(ProjectPackageError):
    """The saved study is sound but no longer belongs to the current assembly."""


def _open_current_project(params: Mapping[str, Any], operation: str, *, include_members: bool):
    path = Path(str(params.get("project_path", "")))
    if not path.is_file():
        raise ProjectPackageError(f"Open a saved SPIKE project before {operation}.")
    opened = read_project(path, include_members=include_members)
    if opened.migrated:
        raise ProjectPackageError(f"Migrate and save the legacy project before {operation}.")
    expected = str(params.get("expected_manifest_payload_sha256", "")).strip().lower()
    actual = str(opened.manifest.get("manifest_payload_sha256", "")).strip().lower()
    if not expected or expected != actual:
        raise ProjectPackageError(f"The project changed since it was verified; reopen it before {operation}.")
    return path, opened


def _assembly_identity(assembly: Any) -> tuple[Dict[str, Any], str]:
    if not isinstance(assembly, Mapping):
        raise ProjectPackageError("Assembly field studies require a current AssemblyIR assembly.")
    try:
        from .multiboard_study import physical_assembly
        canonical = physical_assembly(assembly)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ProjectPackageError(f"The current AssemblyIR is invalid: {exc}") from exc
    return canonical, canonical_json_digest(canonical)


def _admit_against_assembly(record: Any, assembly: Any) -> tuple[Dict[str, Any], str]:
    from .assembly_field_study import export_assembly_field_study, import_assembly_field_study
    from .multiboard_study import physical_assembly

    try:
        admitted = import_assembly_field_study(record)
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        raise ProjectPackageError(f"The saved assembly field study is corrupt or unsupported: {exc}") from exc
    current_assembly, assembly_digest = _assembly_identity(assembly)
    request = admitted["request"]
    try:
        saved_assembly = physical_assembly(request["assembly"])
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        raise ProjectPackageError(f"The saved assembly field study has invalid AssemblyIR: {exc}") from exc
    if canonical_json_digest(saved_assembly) != assembly_digest:
        raise AssemblyFieldStudyStale(
            "The saved assembly field study belongs to different physical assembly geometry or placement. "
            "Review the current occurrences and rerun the field study."
        )
    current_request = copy.deepcopy(request)
    current_request["assembly"] = current_assembly
    try:
        canonical = export_assembly_field_study(
            current_request,
            admitted["problem"],
            admitted["result"],
            include_results=admitted["result"] is not None,
            transient_settings=admitted.get("transient_settings"),
        )
        admitted = import_assembly_field_study(
            canonical,
            current_request=current_request,
            current_problem=admitted["problem"],
        )
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        if "ASSEMBLY_FIELD_STALE" in str(exc):
            raise AssemblyFieldStudyStale(
                "The saved assembly field setup no longer matches the current physical assembly. "
                "Review the setup and rerun before using a result."
            ) from exc
        raise ProjectPackageError(f"The saved assembly field study failed admission: {exc}") from exc
    return admitted, assembly_digest


def read_assembly_field_study_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    del application_version
    if not isinstance(params, dict) or set(params) != {"project_path", "expected_manifest_payload_sha256"}:
        raise ProjectPackageError("Assembly field study read requires exact project and manifest identities.")
    path, opened = _open_current_project(params, "reading the assembly field study", include_members=False)
    analyses = opened.payload.get("analyses", {})
    if not isinstance(analyses, Mapping):
        raise ProjectPackageError("The project analysis index must be an object.")
    record = analyses.get(STUDY_KEY)
    current_assembly, assembly_digest = _assembly_identity(opened.payload.get("assembly_ir"))
    if record is None:
        return {
            "contract": "spike/assembly-field-study-project-read-result/v1",
            "state": "missing", "record": None, "has_saved_record": False,
            "saved_result_present": False, "assembly_digest": assembly_digest,
            "assembly": current_assembly,
            "action": "Prepare or import an assembly field study for the current assembly.",
            "project_path": str(path.resolve()),
        }
    result_present = isinstance(record, Mapping) and record.get("result") is not None
    try:
        admitted, assembly_digest = _admit_against_assembly(record, opened.payload.get("assembly_ir"))
    except AssemblyFieldStudyStale as exc:
        return {
            "contract": "spike/assembly-field-study-project-read-result/v1",
            "state": "stale", "record": None, "has_saved_record": True,
            "saved_result_present": result_present, "assembly_digest": assembly_digest,
            "assembly": current_assembly,
            "action": str(exc), "project_path": str(path.resolve()),
        }
    return {
        "contract": "spike/assembly-field-study-project-read-result/v1",
        "state": "current", "record": admitted, "has_saved_record": True,
        "saved_result_present": admitted["result"] is not None,
        "assembly_digest": assembly_digest, "assembly": current_assembly, "action": "",
        "project_path": str(path.resolve()),
    }


def save_assembly_field_study_in_project(params: Dict[str, Any], *, application_version: str) -> Dict[str, Any]:
    required = {"project_path", "expected_manifest_payload_sha256", "record"}
    if not isinstance(params, dict) or set(params) != required:
        raise ProjectPackageError("Assembly field study save requires exact project, manifest, and record fields.")
    path, opened = _open_current_project(params, "saving the assembly field study", include_members=True)
    try:
        record, assembly_digest = _admit_against_assembly(params["record"], opened.payload.get("assembly_ir"))
    except AssemblyFieldStudyStale as exc:
        raise ProjectPackageError(str(exc)) from exc
    payload = copy.deepcopy(opened.payload)
    analyses = payload.setdefault("analyses", {})
    if not isinstance(analyses, dict):
        raise ProjectPackageError("The project analysis index must be an object.")
    analyses[STUDY_KEY] = record
    audit = payload.setdefault("audit", [])
    if not isinstance(audit, list):
        raise ProjectPackageError("The project audit index must be an array.")
    audit.append({
        "event": "assembly_field_study_saved",
        "assembly_digest": assembly_digest,
        "has_result": record["result"] is not None,
        "model_status": "experimental",
    })
    if read_project(path).manifest.get("manifest_payload_sha256") != params["expected_manifest_payload_sha256"]:
        raise ProjectPackageError("The project changed during field study validation; reopen it before saving.")
    manifest = write_spike_package(
        path,
        payload,
        profile=str(opened.manifest.get("profile", "portable_project")),
        preserved_members=opened.members,
        application_version=application_version,
    )
    return {
        "contract": "spike/assembly-field-study-project-save-result/v1",
        "manifest": manifest, "record": record, "assembly_digest": assembly_digest,
        "has_result": record["result"] is not None, "model_status": "experimental",
        "project_path": str(path.resolve()),
    }


def handle_assembly_field_project_request(
    method: Any, params: Dict[str, Any], *, request_id: Any, application_version: str,
) -> Dict[str, Any] | None:
    operations = {
        "read_assembly_field_study_in_project": read_assembly_field_study_in_project,
        "save_assembly_field_study_in_project": save_assembly_field_study_in_project,
    }
    operation = operations.get(method)
    if operation is None:
        return None
    try:
        return {"ok": True, "result": operation(params, application_version=application_version)}
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, ProjectPackageError) as exc:
        return error_response(
            "SPIKE-BE-PACKAGE-E-0002", str(exc), error_type=type(exc).__name__,
            operation_id=operation_id(request_id),
        )
