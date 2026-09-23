"""Atomic, manifest-bound board and external assembly imports into saved projects."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .assembly_designs import canonicalize_assembly_designs
from .assembly_exchange import import_exchange
from .assembly_frames import IDENTITY
from .design_ir_v2 import AssemblyIRV1, BoardInstance
from .design_ir_v2_schema import CoordinateFrame, content_digest
from .project_package import ProjectPackageError, _source_member_name, read_project, write_spike_package
from .service_project import import_design
from .harness_authoring import validate_harness_connections


def import_into_assembly(params, *, application_version):
    path = Path(params["project_path"])
    opened = read_project(path, include_members=True)
    expected = params.get("expected_manifest_payload_sha256")
    if opened.migrated or not expected or expected != opened.manifest.get("manifest_payload_sha256"):
        raise ProjectPackageError("The project changed since it was verified; reopen and save it before importing.")
    payload = dict(opened.payload)
    active = payload["design_ir"]
    assembly = AssemblyIRV1.from_dict(payload["assembly_ir"]) if payload.get("assembly_ir") else AssemblyIRV1(assembly_id=str(uuid4()), name="Assembly")
    if not assembly.boards:
        identifier = str(uuid4())
        assembly.boards.append(BoardInstance(id=identifier, name=active["name"], design_id=active["design_id"], frame=CoordinateFrame(frame_id=identifier + "-frame", parent_frame_id=assembly.frame.frame_id)))
    source = Path(params["source_path"])
    retained = {d["design_id"]: d for d in (payload.get("assembly_designs") or {}).get("designs", [active])}
    if source.suffix.lower() == ".spikeassembly":
        imported = import_exchange(source, root_frame=assembly.frame.frame_id, namespace=str(uuid4()))
    else:
        source_bytes = source.read_bytes()
        outcome = import_design(str(source), with_report=True)
        design = outcome["design"]
        source_digest = content_digest(source_bytes)
        if design["source"]["source_digest"] != source_digest:
            raise ProjectPackageError("The board source changed during import; retry from a stable source file.")
        design["source"]["artifact_path"] = "package:" + _source_member_name(source.name, source_digest)
        identifier = str(uuid4())
        transform = list(IDENTITY)
        # Start beside the existing board; placement remains editable.
        transform[3] = 100 * len(assembly.boards)
        board = BoardInstance(id=identifier, name=design["name"], design_id=design["design_id"], frame=CoordinateFrame(frame_id=identifier + "-frame", parent_frame_id=assembly.frame.frame_id, transform=tuple(transform)))
        imported = {"assembly": {"boards": [board.__dict__]}, "designs": {design["design_id"]: design}, "models": [], "model_artifacts": {},
            "source_artifacts": {source.name: source_bytes}, "reports": [outcome["report"]]}
    for key, design in imported["designs"].items():
        if key in retained and content_digest(retained[key]) != content_digest(design):
            raise ProjectPackageError(f"Imported DesignIR identity {key} conflicts with the retained design.")
        retained.setdefault(key, design)
    raw = assembly.to_dict()
    for collection in ("boards", "parts", "harnesses", "connector_mappings"):
        raw[collection].extend(imported["assembly"].get(collection, []))
    assembly = AssemblyIRV1.from_dict(raw)
    validate_harness_connections(assembly)
    payload["assembly_ir"] = assembly.to_dict()
    payload["assembly_designs"] = canonicalize_assembly_designs({"contract": "spike/assembly-designs/v1", "active_design_id": active["design_id"], "designs": list(retained.values())}, active, payload["assembly_ir"])
    models = {m["id"]: m for m in (payload.get("models") or {}).get("models", [])}
    models.update({m["id"]: m for m in imported["models"]})
    payload["models"] = {**(payload.get("models") or {}), "contract": "spike/model-index/v1", "models": list(models.values())}
    payload["audit"] = [*(payload.get("audit") or []), {"event": "assembly_sources_imported", "source_name": source.name,
        "board_count": len(imported["assembly"].get("boards", [])), "part_count": len(imported["assembly"].get("parts", [])), "reports": imported["reports"]}]
    # Recheck after import work, before committing a replacement package.
    if read_project(path).manifest.get("manifest_payload_sha256") != expected:
        raise ProjectPackageError("The project changed during import; reopen before retrying.")
    manifest = write_spike_package(path, payload, preserved_members=opened.members, model_artifacts=imported["model_artifacts"],
        source_artifacts=imported["source_artifacts"], profile=opened.manifest.get("profile", "portable_project"), application_version=application_version)
    return {"contract": "spike/assembly-import-result/v1", "manifest": manifest, "board_count": len(assembly.boards), "part_count": len(assembly.parts), "reports": imported["reports"]}
