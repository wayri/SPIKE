"""CAD import and project-package translation used by the worker service."""

from __future__ import annotations

import tempfile
import json
import copy
from pathlib import Path
from typing import Any, Dict

from .design_ir_v2 import DesignIRV2
from .importers import FunctionImporter, ImporterDescriptor, ImporterRegistry
from .ipc2581_importer import import_ipc2581_design
from .kicad_importer import import_kicad_design
from .project_package import LEGACY_FORMATS, PROJECT_FORMAT_V3, ProjectPackageError, _source_member_name, migrate_legacy_payload
from .normalized_source_codec import decode_normalized_source
from .service_project_persistence import merge_future_fields


_IMPORTERS = ImporterRegistry([
    FunctionImporter(
        descriptor=ImporterDescriptor(
            importer_id="kicad-pcb",
            display_name="KiCad PCB",
            source_formats=("kicad", "kicad_pcb"),
            extensions=(".kicad_pcb",),
        ),
        implementation=import_kicad_design,
    ),
    FunctionImporter(
        descriptor=ImporterDescriptor(
            importer_id="ipc-2581",
            display_name="IPC-2581",
            source_formats=("ipc-2581", "ipc2581"),
            extensions=(".ipc2581",),
        ),
        implementation=import_ipc2581_design,
    ),
])


def register_extension_importers(registry):
    for importer in registry.design_importers():
        existing = _IMPORTERS._importers.get(importer.descriptor.importer_id)
        if existing is None:
            _IMPORTERS.register(importer)
        elif existing.descriptor.extension_id != importer.descriptor.extension_id:
            raise ValueError(f"Extension importer ID collision: {importer.descriptor.importer_id}")


# CLI and worker use the same trusted distribution extensions.
from .extensions import ExtensionRegistry, default_extension_roots
_IMPORT_EXTENSIONS = ExtensionRegistry()
_IMPORT_EXTENSIONS.discover(default_extension_roots(), trusted_roots=[Path(__file__).resolve().parents[2] / "extensions"])
register_extension_importers(_IMPORT_EXTENSIONS)


def importer_catalog() -> list[Dict[str, Any]]:
    return _IMPORTERS.catalog()


def import_design(path: str, format_hint: str = "", *, with_report: bool = False, options=None) -> Dict[str, Any]:
    if with_report:
        return _IMPORTERS.import_outcome(path, format_hint, options=options).to_dict()
    return _IMPORTERS.import_design(path, format_hint, options=options).to_dict()


def canonicalize_project_payload(raw: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, bytes]]:
    """Convert a desktop snapshot into the canonical v3 package payload."""

    design_ir = raw.get("design_ir") if isinstance(raw.get("design_ir"), dict) else {}
    if design_ir.get("contract") == "spike/design-ir/v2":
        return dict(raw), {}
    if str(raw.get("format", "")) not in LEGACY_FORMATS:
        raise ProjectPackageError("A project save requires a supported SPIKE snapshot or v3 payload.")
    payload = migrate_legacy_payload(raw)
    design = raw.get("design") if isinstance(raw.get("design"), dict) else {}
    source_text = decode_normalized_source(design.get("source_board", ""))
    source_name = Path(str(design.get("source_file") or "embedded.kicad_pcb")).name
    source_artifacts: Dict[str, bytes] = {}
    if source_text:
        source_artifacts[source_name] = source_text.encode("utf-8")
        if design.get("source_format") == "spike-normalized":
            snapshot = json.loads(source_text)
            if snapshot.get("contract") != "spike/design-snapshot/v1":
                raise ProjectPackageError("Invalid normalized source snapshot.")
            DesignIRV2.from_dict(snapshot["canonical_design"])  # Validate without discarding newer fields.
            canonical = copy.deepcopy(snapshot["canonical_design"])
            # The original archive/directory digest remains the source identity.
            # A portable normalized snapshot is an additional artifact, not a
            # claim that the original binary archive was embedded as UTF-8.
            canonical.setdefault("metadata", {}).setdefault("original_source_artifact_path", canonical["source"]["artifact_path"])
            canonical["source"]["artifact_path"] = ""
            payload["design_ir"] = canonical
        if source_name.lower().endswith(".kicad_pcb"):
            with tempfile.TemporaryDirectory(prefix="spike-project-import-") as directory:
                source_path = Path(directory) / source_name
                # The imported DesignIR digest must describe the exact bytes
                # embedded in the package.  write_text() performs newline
                # translation on Windows, producing a digest for CRLF input
                # while the source artifact below retains its original LF.
                source_path.write_bytes(source_text.encode("utf-8"))
                imported = _IMPORTERS.import_design(source_path, "kicad_pcb")
                imported.source_path = f"package:sources/{source_name}"
                imported.metadata["source_embedded"] = True
                payload["design_ir"] = DesignIRV2.from_v1(imported).to_dict()
                payload["design_ir"]["source"]["artifact_path"] = (
                    "package:" + _source_member_name(
                        source_name, payload["design_ir"]["source"]["source_digest"],
                    )
                )
    retained = design.get("canonical_design")
    if isinstance(retained, dict) and retained.get("contract") == "spike/design-ir/v2":
        current = payload.get("design_ir") or {}
        if retained.get("source", {}).get("source_digest") == current.get("source", {}).get("source_digest"):
            payload["design_ir"] = merge_future_fields(retained, current)
    payload["saved_at"] = str(raw.get("saved_at") or "")
    if isinstance(raw.get("workspace"), dict):
        payload["workspace"] = dict(raw["workspace"])
    return payload, source_artifacts


def merge_project_payload(base: Dict[str, Any], updated: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an edited UI snapshot into a verified canonical package payload."""

    merged = dict(base)
    for key in ("project", "workspace", "design_ir", "assembly_designs", "assembly_package_shapes", "analyses", "results", "reports", "models", "saved_at"):
        if key in updated and updated[key] is not None:
            merged[key] = updated[key]
    if isinstance(updated.get("assembly_ir"), dict):
        merged["assembly_ir"] = updated["assembly_ir"]
    base_extensions = base.get("extensions") if isinstance(base.get("extensions"), dict) else {}
    updated_extensions = updated.get("extensions") if isinstance(updated.get("extensions"), dict) else {}
    merged["extensions"] = merge_future_fields(base_extensions, updated_extensions)
    base_audit = base.get("audit") if isinstance(base.get("audit"), list) else []
    updated_audit = updated.get("audit") if isinstance(updated.get("audit"), list) else []
    audit: list[Any] = []
    for event in [*base_audit, *updated_audit]:
        if event not in audit:
            audit.append(event)
    audit.append({"event": "project_saved", "source": "desktop", "saved_at": str(updated.get("saved_at") or "")})
    merged["audit"] = audit
    if "geometry" in base:
        merged["geometry"] = base["geometry"]
    return merged


def design_source_digest(payload: Dict[str, Any]) -> str:
    """Return the canonical source digest used to validate derived caches."""

    design = payload.get("design_ir") if isinstance(payload.get("design_ir"), dict) else {}
    source = design.get("source") if isinstance(design.get("source"), dict) else {}
    return str(source.get("source_digest") or "").strip()


def has_authoritative_source_identity(snapshot: Dict[str, Any]) -> bool:
    """Report whether a save request explicitly identifies its source artifact."""

    design_ir = snapshot.get("design_ir") if isinstance(snapshot.get("design_ir"), dict) else {}
    source = design_ir.get("source") if isinstance(design_ir.get("source"), dict) else {}
    if design_ir.get("contract") == "spike/design-ir/v2" and source.get("source_digest"):
        return True
    design = snapshot.get("design") if isinstance(snapshot.get("design"), dict) else {}
    source_board = design.get("source_board")
    return bool(source_board if isinstance(source_board, str) else isinstance(source_board, dict))


def frontend_project_payload(package_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the exact UI snapshot when present, otherwise a v2 projection."""

    extensions = package_payload.get("extensions")
    legacy = extensions.get("legacy") if isinstance(extensions, dict) else None
    if isinstance(legacy, dict):
        projected = dict(legacy)
        if isinstance(package_payload.get("assembly_ir"), dict):
            projected["assembly_ir"] = package_payload["assembly_ir"]
        if isinstance(package_payload.get("models"), dict):
            projected["models"] = package_payload["models"]
        if isinstance(package_payload.get("assembly_package_shapes"), dict):
            projected["assembly_package_shapes"] = package_payload["assembly_package_shapes"]
        if isinstance(package_payload.get("assembly_designs"), dict):
            projected["assembly_designs"] = package_payload["assembly_designs"]
        return projected
    design = DesignIRV2.from_dict(package_payload.get("design_ir") or {}).to_v1().to_dict()
    projected = {
        "format": "spike-project-package/v2",
        "contract": "spike/project/v2",
        "project": package_payload.get("project") or {"name": "project.spike"},
        "design": design,
        "analysis": package_payload.get("analyses") or {},
        "results": package_payload.get("results") or {},
        "reports": package_payload.get("reports") or {},
        "models": package_payload.get("models") or {},
    }
    if isinstance(package_payload.get("workspace"), dict):
        projected["workspace"] = package_payload["workspace"]
    if isinstance(package_payload.get("assembly_ir"), dict):
        projected["assembly_ir"] = package_payload["assembly_ir"]
    if isinstance(package_payload.get("assembly_package_shapes"), dict):
        projected["assembly_package_shapes"] = package_payload["assembly_package_shapes"]
    if isinstance(package_payload.get("assembly_designs"), dict):
        projected["assembly_designs"] = package_payload["assembly_designs"]
    return projected
