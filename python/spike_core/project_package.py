"""Secure, bounded ZIP64 reader and writer for SPIKE v3 project packages."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional

from . import __version__
from .contracts import DesignIR, ValidationIssue
from .design_ir_v2 import AssemblyIRV1, DesignIRV2, canonical_uuid, content_digest
from .assembly_package_shapes import AssemblyPackageShapeError, canonicalize_assembly_package_shapes, validate_package_shape_artifacts
from .model_index import ModelIndexError, canonicalize_model_index, validate_model_artifacts
from .assembly_designs import AssemblyDesignError, canonicalize_assembly_designs
from .project_design_artifacts import validate_design_source_artifacts as _validate_design_source_artifacts
from .project_geometry_index import build_geometry_members, validate_geometry_index
from .project_package_limits import PackageLimits


PROJECT_FORMAT_V3 = "spike-project-package/v3"
PROJECT_CONTRACT_V3 = "spike/project-package/v3"
MANIFEST_SIGNATURE_CONTRACT_V1 = "spike/manifest-signature/v1"
PROJECT_PROFILES = {"portable_project", "design_exchange", "result_bundle"}
LEGACY_FORMATS = {"spike-project-package/v1", "spike-project-package/v2"}
_SAFE_MEMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@+-]*(?:/[A-Za-z0-9][A-Za-z0-9._/@+-]*)*$")
_FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)
_VERIFY_CHUNK_BYTES = 1024 * 1024
_PAYLOAD_MEMBER_NAMES = {
    "project/project.json", "workspace/state.json", "design/design-ir.json",
    "design/assembly-designs.json", "design/assembly-ir.json",
    "design/assembly-package-shapes.json", "analyses/index.json",
    "results/index.json", "reports/index.json", "models/index.json",
    "geometry/index.json", "extensions/index.json", "audit/events.jsonl",
}
_CONTROL_PLANE_JSON_MEMBER_NAMES = frozenset(name for name in _PAYLOAD_MEMBER_NAMES if name.endswith(".json"))


class ProjectPackageError(ValueError):
    """Raised when a project package is invalid, unsafe, or unsupported."""


@dataclass
class PackageMember:
    path: str
    sha256: str
    size: int
    media_type: str
    role: str


@dataclass
class PackageReadResult:
    manifest: Dict[str, Any]
    payload: Dict[str, Any]
    members: Dict[str, bytes] = field(default_factory=dict)
    migrated: bool = False
    source_format: str = PROJECT_FORMAT_V3
    signature_present: bool = False
    signature_verified: bool | None = None


ManifestSigner = Callable[[bytes], Mapping[str, Any]]
ManifestVerifier = Callable[[bytes, Mapping[str, Any]], bool]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _signed_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Return the canonical bytes covered by a detached manifest signature."""

    unsigned = dict(manifest)
    unsigned.pop("signature", None)
    return _json_bytes(unsigned)


def manifest_signature_payload(manifest: Mapping[str, Any]) -> bytes:
    """Expose the exact canonical manifest bytes for native trust verification."""

    return _signed_manifest_bytes(manifest)


def _validate_signature_envelope(signature: Mapping[str, Any], signed_payload: bytes) -> Dict[str, str]:
    """Validate signature metadata without claiming cryptographic trust."""

    normalized = {
        "contract": str(signature.get("contract", "")),
        "algorithm": str(signature.get("algorithm", "")),
        "key_id": str(signature.get("key_id", "")),
        "signed_payload_sha256": str(signature.get("signed_payload_sha256", "")),
        "signature_base64url": str(signature.get("signature_base64url", "")),
    }
    if normalized["contract"] != MANIFEST_SIGNATURE_CONTRACT_V1:
        raise ProjectPackageError("Package manifest signature contract is unsupported.")
    if normalized["algorithm"] != "ed25519":
        raise ProjectPackageError("Package manifest signature algorithm must be Ed25519.")
    if not normalized["key_id"].strip():
        raise ProjectPackageError("Package manifest signature key identity is missing.")
    if normalized["signed_payload_sha256"] != _sha256(signed_payload):
        raise ProjectPackageError("Package manifest signed-payload digest is invalid.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized["signature_base64url"]):
        raise ProjectPackageError("Package manifest signature is not valid base64url.")
    return normalized


def _safe_member_path(value: str, *, max_depth: int = 12) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or len(path.parts) > max_depth
        or not _SAFE_MEMBER.fullmatch(normalized)
    ):
        raise ProjectPackageError(f"Unsafe package member path: {value!r}")
    return normalized


def _media_type(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".arrow": "application/vnd.apache.arrow.file",
        ".html": "text/html",
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".step": "model/step",
        ".stp": "model/step",
        ".gltf": "model/gltf+json",
        ".glb": "model/gltf-binary",
        ".spkshape": "application/vnd.spike.package-shape",
    }.get(suffix, "application/octet-stream")


def _member_role(path: str) -> str:
    return path.split("/", 1)[0]


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=_FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def _source_member_name(original_name: str, digest: str) -> str:
    suffixes = "".join(Path(original_name).suffixes[-2:])
    suffix = re.sub(r"[^A-Za-z0-9._+-]", "", suffixes)[:32]
    return f"sources/{digest}{suffix}"


def _has_payload_content(value: Any) -> bool:
    """Return whether an index contains data beyond contract/version metadata."""

    if isinstance(value, Mapping):
        return any(
            _has_payload_content(item)
            for key, item in value.items()
            if str(key) not in {"contract", "schema", "version"}
        )
    if isinstance(value, (list, tuple, set)):
        return any(_has_payload_content(item) for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None and value is not False


def _validate_profile_content(
    profile: str,
    payload: Mapping[str, Any],
    member_names: Iterable[str] = (),
) -> None:
    """Enforce the semantic minimum and exclusions declared by each profile."""

    if profile not in PROJECT_PROFILES:
        raise ProjectPackageError(f"Unsupported SPIKE package profile: {profile or 'missing'}")
    names = set(member_names)
    if profile == "design_exchange":
        if _has_payload_content(payload.get("results", {})):
            raise ProjectPackageError("A design_exchange package cannot contain populated result metadata.")
        if _has_payload_content(payload.get("reports", {})):
            raise ProjectPackageError("A design_exchange package cannot contain populated report metadata.")
        if any(
            name.startswith("reports/artifacts/")
            or (name.startswith("results/") and name != "results/index.json")
            for name in names
        ):
            raise ProjectPackageError("A design_exchange package cannot contain result or report artifacts.")
    elif profile == "result_bundle":
        if not _has_payload_content(payload.get("results", {})):
            raise ProjectPackageError("A result_bundle package requires populated result metadata.")
        audit = payload.get("audit")
        if not isinstance(audit, list) or not any(isinstance(event, Mapping) and event for event in audit):
            raise ProjectPackageError("A result_bundle package requires at least one audit event.")
        design = payload.get("design_ir") if isinstance(payload.get("design_ir"), Mapping) else {}
        if not str(design.get("design_id", "")).strip():
            raise ProjectPackageError("A result_bundle package requires a canonical design identity.")


def _minimal_v2_design(legacy: Mapping[str, Any]) -> DesignIRV2:
    raw_design = legacy.get("design") if isinstance(legacy.get("design"), Mapping) else {}
    source_text = str(raw_design.get("source_board", ""))
    source_bytes = source_text.encode("utf-8")
    digest = _sha256(source_bytes) if source_bytes else content_digest(legacy)
    design_name = str(raw_design.get("name") or raw_design.get("source_file") or legacy.get("project", {}).get("name") or "Migrated design")
    v1_fields = set(DesignIR.__dataclass_fields__)
    if raw_design.get("contract") == "spike/v1":
        candidate = {key: value for key, value in raw_design.items() if key in v1_fields}
        coerced_issues = []
        for issue in candidate.get("issues", []):
            if isinstance(issue, dict):
                coerced_issues.append(ValidationIssue(**{
                    key: issue[key] for key in ValidationIssue.__dataclass_fields__ if key in issue
                }))
            elif isinstance(issue, ValidationIssue):
                coerced_issues.append(issue)
        candidate["issues"] = coerced_issues
        legacy_design = DesignIR(**candidate)
    else:
        legacy_design = DesignIR(
            design_id=str(raw_design.get("design_id", "")),
            name=Path(design_name).stem,
            source_format=str(raw_design.get("source_format") or raw_design.get("source_file", "unknown")).split(".")[-1],
            source_path=str(raw_design.get("source_path", "")),
            layers=list(raw_design.get("layers", [])),
            nets=list(raw_design.get("nets", [])),
            tracks=list(raw_design.get("tracks", [])),
            vias=list(raw_design.get("vias", [])),
            pads=list(raw_design.get("pads", [])),
            zones=list(raw_design.get("zones", [])),
            components=list(raw_design.get("components", [])),
            stackup=list(raw_design.get("stackup", [])),
            metadata={"migration_source_format": str(legacy.get("format", "unknown"))},
        )
    legacy_design.metadata["source_sha256"] = digest
    return DesignIRV2.from_v1(legacy_design, source_digest=digest)


def migrate_legacy_payload(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Migrate a v1/v2 JSON package in memory without discarding unknown data."""

    source_format = str(raw.get("format", ""))
    if source_format not in LEGACY_FORMATS:
        raise ProjectPackageError(f"Unsupported legacy SPIKE project format: {source_format or 'missing'}")
    project = dict(raw.get("project", {}))
    design = _minimal_v2_design(raw)
    project_name = str(project.get("name") or "migrated.spike")
    project_id = str(project.get("id") or canonical_uuid("spike", content_digest(raw), "project", project_name))
    return {
        "project": {**project, "id": project_id, "name": project_name},
        "workspace": raw.get("workspace"),
        "design_ir": design.to_dict(),
        "assembly_ir": raw.get("assembly"),
        "analyses": raw.get("analysis", {}),
        "results": raw.get("results", raw.get("analysis", {}).get("latest_result", {})),
        "reports": raw.get("reports", {}),
        "models": raw.get("models", {}),
        "extensions": {
            "legacy": dict(raw),
            "migration": {"from": source_format, "to": PROJECT_FORMAT_V3, "preserved_unknown_fields": True},
        },
        "audit": [{"event": "project_migrated", "from": source_format, "to": PROJECT_FORMAT_V3}],
    }


def _validate_assembly_model_references(
    assembly_ir: Optional[Mapping[str, Any]],
    model_index: Mapping[str, Any],
) -> None:
    if not assembly_ir:
        return
    model_ids = {
        str(item.get("id", "")) for item in model_index.get("models", [])
        if isinstance(item, Mapping)
    }
    missing = sorted({
        str(item.get("model_id", "")) for item in assembly_ir.get("parts", [])
        if isinstance(item, Mapping) and str(item.get("model_id", "")) not in model_ids and not (item.get("part_type") == "subassembly" and not item.get("model_id"))
    })
    if missing:
        raise ProjectPackageError(
            f"AssemblyIR references missing model identities: {', '.join(missing[:5])}"
        )


def build_package_members(
    payload: Mapping[str, Any],
    *,
    source_artifacts: Optional[Mapping[str, bytes]] = None,
    geometry_tables: Optional[Mapping[str, bytes]] = None,
    generate_geometry_tables: bool = False,
    package_shape_artifacts: Optional[Mapping[str, bytes]] = None,
    package_shape_preview_artifacts: Optional[Mapping[str, bytes]] = None,
    model_artifacts: Optional[Mapping[str, bytes]] = None,
    report_artifacts: Optional[Mapping[str, bytes]] = None,
    preserved_members: Optional[Mapping[str, bytes]] = None,
) -> Dict[str, bytes]:
    """Build the canonical member map without writing to disk."""

    if not isinstance(payload.get("project"), Mapping):
        raise ProjectPackageError("A v3 project payload requires project metadata.")
    design_ir = payload.get("design_ir")
    if not isinstance(design_ir, Mapping) or design_ir.get("contract") != "spike/design-ir/v2":
        raise ProjectPackageError("A v3 project payload requires DesignIR v2.")
    try:
        model_index = canonicalize_model_index(payload.get("models", {}))
    except ModelIndexError as exc:
        raise ProjectPackageError(f"The model index is invalid: {exc}") from exc
    members: Dict[str, bytes] = {
        "project/project.json": _json_bytes(dict(payload["project"])),
        "design/design-ir.json": _json_bytes(dict(design_ir)),
        "analyses/index.json": _json_bytes(payload.get("analyses", {})),
        "results/index.json": _json_bytes(payload.get("results", {})),
        "reports/index.json": _json_bytes(payload.get("reports", {})),
        "models/index.json": _json_bytes(model_index),
        "geometry/index.json": _json_bytes(payload.get("geometry", {"contract": "spike/geometry-index/v1", "tables": []})),
        "extensions/index.json": _json_bytes(payload.get("extensions", {})),
    }
    if isinstance(payload.get("workspace"), Mapping):
        members["workspace/state.json"] = _json_bytes(dict(payload["workspace"]))
    if isinstance(payload.get("assembly_ir"), Mapping):
        try:
            assembly_ir = AssemblyIRV1.from_dict(payload["assembly_ir"]).to_dict()
        except (TypeError, ValueError) as exc:
            raise ProjectPackageError(f"The AssemblyIR payload is invalid: {exc}") from exc
        members["design/assembly-ir.json"] = _json_bytes(assembly_ir)
        _validate_assembly_model_references(assembly_ir, model_index)
    else:
        assembly_ir = None
    try:
        assembly_designs = canonicalize_assembly_designs(payload.get("assembly_designs", {}), design_ir, assembly_ir)
    except AssemblyDesignError as exc:
        raise ProjectPackageError(f"The assembly design set is invalid: {exc}") from exc
    if assembly_designs:
        members["design/assembly-designs.json"] = _json_bytes(assembly_designs)
    try:
        package_shapes = canonicalize_assembly_package_shapes(
            payload.get("assembly_package_shapes", {}), assembly_ir, model_index,
        )
    except AssemblyPackageShapeError as exc:
        raise ProjectPackageError(f"The assembly package-shape index is invalid: {exc}") from exc
    if package_shapes:
        members["design/assembly-package-shapes.json"] = _json_bytes(package_shapes)
    audit = payload.get("audit", [])
    if isinstance(audit, list):
        members["audit/events.jsonl"] = b"".join(_json_bytes(item) for item in audit)

    geometry_members, generated_index = build_geometry_members(
        design_ir, geometry_tables, generate=generate_geometry_tables,
        safe_member_path=_safe_member_path, sha256=_sha256, error_type=ProjectPackageError,
    )
    if geometry_tables is not None or generate_geometry_tables:
        members.update(geometry_members)
        members["geometry/index.json"] = _json_bytes(generated_index)

    for name, data in sorted((package_shape_artifacts or {}).items()):
        safe_name = re.sub(r"[^A-Za-z0-9._+-]", "-", Path(name).name)
        if not safe_name.endswith(".spkshape"):
            raise ProjectPackageError("Package-shape topology artifacts must use the .spkshape extension.")
        members[_safe_member_path(f"geometry/package-shapes/{safe_name}")] = bytes(data)

    for name, data in sorted((package_shape_preview_artifacts or {}).items()):
        safe_name = re.sub(r"[^A-Za-z0-9._+-]", "-", Path(name).name)
        if not safe_name.endswith(".spkselect.glb"):
            raise ProjectPackageError("Package-shape selector-preview artifacts must use the .spkselect.glb extension.")
        members[_safe_member_path(f"geometry/package-shapes/{safe_name}")] = bytes(data)

    for original_name, data in sorted((source_artifacts or {}).items()):
        raw = bytes(data)
        digest = _sha256(raw)
        members[_source_member_name(original_name, digest)] = raw
    for prefix, artifacts in (("models/artifacts", model_artifacts or {}), ("reports/artifacts", report_artifacts or {})):
        for name, data in sorted(artifacts.items()):
            safe_name = re.sub(r"[^A-Za-z0-9._+-]", "-", Path(name).name)
            members[_safe_member_path(f"{prefix}/{safe_name}")] = bytes(data)
    for name, data in sorted((preserved_members or {}).items()):
        safe_name = _safe_member_path(name)
        if safe_name != "manifest.json" and safe_name not in members:
            members[safe_name] = bytes(data)
    member_digests = {name: _sha256(data) for name, data in members.items()}
    geometry_index = validate_geometry_index(
        json.loads(members["geometry/index.json"]), member_digests, design_ir,
        safe_member_path=_safe_member_path, error_type=ProjectPackageError,
    )
    members["geometry/index.json"] = _json_bytes(geometry_index)
    member_digests["geometry/index.json"] = _sha256(members["geometry/index.json"])
    _validate_design_source_artifacts(
        design_ir, assembly_designs, member_digests,
        safe_member_path=_safe_member_path, error_type=ProjectPackageError,
    )
    try:
        validate_model_artifacts(model_index, member_digests)
        validate_package_shape_artifacts(package_shapes, member_digests)
    except (ModelIndexError, AssemblyPackageShapeError) as exc:
        label = "model index" if isinstance(exc, ModelIndexError) else "assembly package-shape index"
        raise ProjectPackageError(f"The {label} is invalid: {exc}") from exc
    return {path: members[path] for path in sorted(members)}


def write_spike_package(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    profile: str = "portable_project",
    source_artifacts: Optional[Mapping[str, bytes]] = None,
    geometry_tables: Optional[Mapping[str, bytes]] = None,
    generate_geometry_tables: bool = False,
    package_shape_artifacts: Optional[Mapping[str, bytes]] = None,
    package_shape_preview_artifacts: Optional[Mapping[str, bytes]] = None,
    model_artifacts: Optional[Mapping[str, bytes]] = None,
    report_artifacts: Optional[Mapping[str, bytes]] = None,
    preserved_members: Optional[Mapping[str, bytes]] = None,
    application_version: str = __version__,
    manifest_signer: ManifestSigner | None = None,
) -> Dict[str, Any]:
    if profile not in PROJECT_PROFILES:
        raise ProjectPackageError(f"Unknown SPIKE package profile: {profile}")
    destination = Path(path)
    if destination.suffix.lower() != ".spike":
        raise ProjectPackageError("SPIKE v3 packages must use the .spike extension.")
    members = build_package_members(
        payload,
        source_artifacts=source_artifacts,
        geometry_tables=geometry_tables,
        generate_geometry_tables=generate_geometry_tables,
        package_shape_artifacts=package_shape_artifacts,
        package_shape_preview_artifacts=package_shape_preview_artifacts,
        model_artifacts=model_artifacts,
        report_artifacts=report_artifacts,
        preserved_members=preserved_members,
    )
    _validate_profile_content(profile, payload, members)
    member_records = [
        PackageMember(path=name, sha256=_sha256(data), size=len(data), media_type=_media_type(name), role=_member_role(name))
        for name, data in members.items()
    ]
    project = payload["project"]
    project_id = str(project.get("id") or canonical_uuid("spike", content_digest(project), "project", str(project.get("name", "project"))))
    manifest: Dict[str, Any] = {
        "format": PROJECT_FORMAT_V3,
        "contract": PROJECT_CONTRACT_V3,
        "profile": profile,
        "package_id": project_id,
        "created_at": str(payload.get("saved_at") or _utc_now()),
        "application": {"name": "SPIKE", "version": application_version},
        "compatibility": {"minimum_reader": "0.2.10" if any(name.startswith(("state/artifacts/", "visuals/artifacts/")) for name in members) else "0.2.0", "unknown_extensions": "preserve"},
        "schemas": {
            "design_ir": "spike/design-ir/v2",
            "assembly_ir": "spike/assembly-ir/v1",
            "assembly_designs": "spike/assembly-designs/v1",
            "assembly_placement_policy": "spike/assembly-placement-policy/v1",
            "assembly_package_shapes": "spike/assembly-package-shapes/v1",
            "model_index": "spike/model-index/v1",
            "geometry_index": "spike/geometry-index/v1",
            "workspace": "spike/workspace-state/v1",
        },
        "audit_identity": {"project_id": project_id, "design_id": payload["design_ir"].get("design_id", "")},
        "members": [asdict(item) for item in member_records],
    }
    manifest["manifest_payload_sha256"] = _sha256(_json_bytes(manifest))
    if manifest_signer is not None:
        signed_payload = _signed_manifest_bytes(manifest)
        supplied = manifest_signer(signed_payload)
        if not isinstance(supplied, Mapping):
            raise ProjectPackageError("The manifest signer did not return signature metadata.")
        signature = {
            "contract": MANIFEST_SIGNATURE_CONTRACT_V1,
            "algorithm": str(supplied.get("algorithm", "ed25519")),
            "key_id": str(supplied.get("key_id", "")),
            "signed_payload_sha256": _sha256(signed_payload),
            "signature_base64url": str(supplied.get("signature_base64url", "")),
        }
        manifest["signature"] = _validate_signature_envelope(signature, signed_payload)
    manifest_bytes = _json_bytes(manifest)

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, mode="w", allowZip64=True, strict_timestamps=True) as archive:
            archive.writestr(_zip_info("manifest.json"), manifest_bytes)
            for name, data in members.items():
                archive.writestr(_zip_info(_safe_member_path(name)), data)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return manifest


def _validate_archive(archive: zipfile.ZipFile, limits: PackageLimits) -> Dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > limits.max_members:
        raise ProjectPackageError(f"Package has {len(infos)} members; limit is {limits.max_members}.")
    by_name: Dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in infos:
        if info.is_dir():
            continue
        name = _safe_member_path(info.filename, max_depth=limits.max_path_depth)
        if name in by_name:
            raise ProjectPackageError(f"Duplicate package member: {name}")
        if info.file_size > limits.max_member_bytes:
            raise ProjectPackageError(f"Package member exceeds the size limit: {name}")
        total += info.file_size
        if total > limits.max_total_bytes:
            raise ProjectPackageError("Package expanded size exceeds the configured limit.")
        compressed = max(1, info.compress_size)
        if info.file_size / compressed > limits.max_compression_ratio:
            raise ProjectPackageError(f"Package member exceeds the compression-ratio limit: {name}")
        by_name[name] = info
    if "manifest.json" not in by_name:
        raise ProjectPackageError("SPIKE v3 package is missing manifest.json.")
    return by_name


def _verify_member_stream(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    *,
    expected_size: int,
    expected_sha256: str,
    retain: bool,
) -> bytes | None:
    """Hash one member incrementally and optionally retain its expanded bytes."""

    digest = hashlib.sha256()
    size = 0
    retained = bytearray() if retain else None
    with archive.open(info, mode="r") as stream:
        while chunk := stream.read(_VERIFY_CHUNK_BYTES):
            size += len(chunk)
            digest.update(chunk)
            if retained is not None:
                retained.extend(chunk)
    if size != expected_size or digest.hexdigest() != expected_sha256:
        raise ProjectPackageError(f"Package member integrity check failed: {info.filename}")
    return bytes(retained) if retained is not None else None


def _read_manifest(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> Dict[str, Any]:
    """Read the manifest as a JSON object with a package-specific failure."""
    try:
        manifest = json.loads(archive.read(info))
    except json.JSONDecodeError as exc:
        raise ProjectPackageError("Package manifest is not valid JSON.") from exc
    if not isinstance(manifest, dict):
        raise ProjectPackageError("Package manifest must be a JSON object.")
    return manifest


def read_spike_package(
    path: str | Path,
    *,
    limits: PackageLimits | None = None,
    include_members: bool = False,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> PackageReadResult:
    limits = limits or PackageLimits()
    source = Path(path)
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = _validate_archive(archive, limits)
            if infos["manifest.json"].file_size > limits.max_manifest_bytes:
                raise ProjectPackageError("Package manifest exceeds the configured limit.")
            manifest = _read_manifest(archive, infos["manifest.json"])
            if manifest.get("format") != PROJECT_FORMAT_V3 or manifest.get("contract") != PROJECT_CONTRACT_V3:
                raise ProjectPackageError(f"Unsupported SPIKE package revision: {manifest.get('format', 'missing')}")
            profile = str(manifest.get("profile", ""))
            if profile not in PROJECT_PROFILES:
                raise ProjectPackageError(f"Unsupported SPIKE package profile: {profile or 'missing'}")
            expected_manifest = str(manifest.get("manifest_payload_sha256", ""))
            unsigned_manifest = dict(manifest)
            unsigned_manifest.pop("signature", None)
            unsigned_manifest.pop("manifest_payload_sha256", None)
            if expected_manifest != _sha256(_json_bytes(unsigned_manifest)):
                raise ProjectPackageError("Package manifest integrity check failed.")
            signature_present = "signature" in manifest
            signature_verified: bool | None = None
            if signature_present:
                raw_signature = manifest.get("signature")
                if not isinstance(raw_signature, Mapping):
                    raise ProjectPackageError("Package manifest signature must be an object.")
                signed_payload = _signed_manifest_bytes(manifest)
                signature = _validate_signature_envelope(raw_signature, signed_payload)
                if signature_verifier is not None:
                    try:
                        signature_verified = bool(signature_verifier(signed_payload, signature))
                    except Exception as exc:
                        raise ProjectPackageError("Package manifest signature verification failed.") from exc
                    if not signature_verified:
                        raise ProjectPackageError("Package manifest signature verification failed.")
                elif require_signature:
                    raise ProjectPackageError("A trusted manifest verifier is required for this package.")
            elif require_signature:
                raise ProjectPackageError("A signed package manifest is required.")
            records = manifest.get("members")
            if not isinstance(records, list):
                raise ProjectPackageError("Package manifest members must be an array.")
            declared: Dict[str, Mapping[str, Any]] = {}
            member_data: Dict[str, bytes] = {}
            payload_data: Dict[str, bytes] = {}
            for record in records:
                if not isinstance(record, Mapping):
                    raise ProjectPackageError("Package manifest contains an invalid member record.")
                name = _safe_member_path(str(record.get("path", "")), max_depth=limits.max_path_depth)
                if name in declared or name not in infos:
                    raise ProjectPackageError(f"Package manifest member is duplicate or missing: {name}")
                expected_size = int(record.get("size", -1))
                expected_sha256 = str(record.get("sha256", ""))
                json_limit = (limits.max_design_ir_json_bytes if name == "design/design-ir.json"
                              else limits.max_control_plane_json_bytes)
                if name in _CONTROL_PLANE_JSON_MEMBER_NAMES and (
                    infos[name].file_size > json_limit
                    or expected_size > json_limit
                ):
                    raise ProjectPackageError(
                        f"Package control-plane JSON member exceeds the configured limit: {name}"
                    )
                retain = include_members or name in _PAYLOAD_MEMBER_NAMES
                data = _verify_member_stream(
                    archive,
                    infos[name],
                    expected_size=expected_size,
                    expected_sha256=expected_sha256,
                    retain=retain,
                )
                declared[name] = record
                if data is not None and name in _PAYLOAD_MEMBER_NAMES:
                    payload_data[name] = data
                if include_members and data is not None:
                    member_data[name] = data
            undeclared = set(infos) - {"manifest.json"} - set(declared)
            if undeclared:
                raise ProjectPackageError(f"Package contains undeclared members: {', '.join(sorted(undeclared)[:5])}")
            required = {"project/project.json", "design/design-ir.json"}
            if missing := required - set(declared):
                raise ProjectPackageError(f"Package is missing required content: {', '.join(sorted(missing))}")

            def read_json(name: str, default: Any) -> Any:
                return json.loads(payload_data[name]) if name in declared else default

            design_ir = read_json("design/design-ir.json", {})
            geometry_index = validate_geometry_index(
                read_json("geometry/index.json", {"contract": "spike/geometry-index/v1", "tables": []}),
                {name: str(record.get("sha256", "")) for name, record in declared.items()},
                design_ir,
                safe_member_path=_safe_member_path,
                error_type=ProjectPackageError,
            )
            assembly_ir = read_json("design/assembly-ir.json", None)
            if assembly_ir is not None:
                try:
                    assembly_ir = AssemblyIRV1.from_dict(assembly_ir).to_dict()
                except (TypeError, ValueError) as exc:
                    raise ProjectPackageError(f"Package AssemblyIR is invalid: {exc}") from exc
            try:
                assembly_designs = canonicalize_assembly_designs(
                    read_json("design/assembly-designs.json", {}),
                    design_ir, assembly_ir,
                )
            except AssemblyDesignError as exc:
                raise ProjectPackageError(f"Package assembly design set is invalid: {exc}") from exc
            _validate_design_source_artifacts(
                design_ir,
                assembly_designs,
                {name: str(record.get("sha256", "")) for name, record in declared.items()},
                safe_member_path=_safe_member_path,
                error_type=ProjectPackageError,
            )
            try:
                model_index = canonicalize_model_index(read_json("models/index.json", {}))
                validate_model_artifacts(
                    model_index,
                    {name: str(record.get("sha256", "")) for name, record in declared.items()},
                )
            except ModelIndexError as exc:
                raise ProjectPackageError(f"Package model index is invalid: {exc}") from exc
            _validate_assembly_model_references(assembly_ir, model_index)
            try:
                package_shapes = canonicalize_assembly_package_shapes(
                    read_json("design/assembly-package-shapes.json", {}), assembly_ir, model_index,
                )
                validate_package_shape_artifacts(
                    package_shapes,
                    {name: str(record.get("sha256", "")) for name, record in declared.items()},
                )
            except AssemblyPackageShapeError as exc:
                raise ProjectPackageError(f"Package assembly package-shape index is invalid: {exc}") from exc
            payload = {
                "project": read_json("project/project.json", {}),
                "workspace": read_json("workspace/state.json", None),
                "design_ir": design_ir,
                "assembly_ir": assembly_ir,
                "assembly_designs": assembly_designs,
                "assembly_package_shapes": package_shapes,
                "analyses": read_json("analyses/index.json", {}),
                "results": read_json("results/index.json", {}),
                "reports": read_json("reports/index.json", {}),
                "models": model_index,
                "geometry": geometry_index,
                "extensions": read_json("extensions/index.json", {}),
            }
            audit_data = payload_data.get("audit/events.jsonl", b"")
            audit: list[Dict[str, Any]] = []
            for line_number, line in enumerate(audit_data.splitlines(), start=1):
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ProjectPackageError(f"Audit event {line_number} is not a JSON object.")
                audit.append(event)
            payload["audit"] = audit
            if payload["design_ir"].get("contract") != "spike/design-ir/v2":
                raise ProjectPackageError("Package design/design-ir.json is not DesignIR v2.")
            _validate_profile_content(profile, payload, declared)
            return PackageReadResult(
                manifest=manifest,
                payload=payload,
                members=member_data,
                signature_present=signature_present,
                signature_verified=signature_verified,
            )
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("The selected file is not a valid SPIKE v3 ZIP package.") from exc

def read_visual_model_artifacts(
    path: str | Path,
    model_ids: list[str],
    *,
    expected_manifest_payload_sha256: str, max_total_bytes: int = 64 * 1024 * 1024,
    signature_verifier: ManifestVerifier | None = None, require_signature: bool = False,
) -> list[Dict[str, Any]]:
    from .project_package_access import read_visual_model_artifacts as implementation
    return implementation(path, model_ids, expected_manifest_payload_sha256=expected_manifest_payload_sha256,
                          max_total_bytes=max_total_bytes, signature_verifier=signature_verifier,
                          require_signature=require_signature)
def read_geometry_arrow_artifact(
    path: str | Path,
    table_path: str,
    *,
    expected_manifest_payload_sha256: str, max_bytes: int = 256 * 1024 * 1024,
    max_ipc_bytes: int | None = None, max_rows: int = 10_000_000,
    signature_verifier: ManifestVerifier | None = None, require_signature: bool = False,
) -> Dict[str, Any]:
    from .project_package_access import read_geometry_arrow_artifact as implementation
    return implementation(path, table_path, expected_manifest_payload_sha256=expected_manifest_payload_sha256,
                          max_bytes=max_bytes, max_ipc_bytes=max_ipc_bytes, max_rows=max_rows,
                          signature_verifier=signature_verifier,
                          require_signature=require_signature)
def read_project(
    path: str | Path,
    *,
    limits: PackageLimits | None = None,
    include_members: bool = False,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> PackageReadResult:
    from .project_package_access import read_project as implementation
    return implementation(path, limits=limits, include_members=include_members,
                          signature_verifier=signature_verifier, require_signature=require_signature)
