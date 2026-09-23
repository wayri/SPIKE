"""Bounded, verified-package visual-model reads for the desktop viewport."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .mcad_importer import McadImportError, validate_step_mcad_artifact, validate_visual_mcad_artifact
from .assembly_package_shapes import (
    AssemblyPackageShapeError, canonicalize_assembly_package_shapes, validate_package_shape_artifacts,
)
from .design_ir_v2 import AssemblyIRV1
from .mcad_selector_preview import McadSelectorPreviewError, SelectorPreviewPolicy, _validate_selector_glb
from .model_index import ModelIndexError, canonicalize_model_index, validate_model_artifacts
from .project_package import (
    PROJECT_CONTRACT_V3,
    PROJECT_FORMAT_V3,
    ManifestVerifier,
    PackageLimits,
    ProjectPackageError,
    _json_bytes,
    _safe_member_path,
    _sha256,
    _validate_archive,
    _verify_member_stream,
)
from .project_package_auth import validate_targeted_manifest_signature


MAX_VISUAL_MODEL_BYTES = 64 * 1024 * 1024
MAX_VISUAL_MODEL_COUNT = 100
MAX_SELECTOR_PREVIEW_BYTES = 128 * 1024 * 1024
MAX_SELECTOR_PREVIEW_COUNT = 100
MAX_PROJECT_SOURCE_BYTES = 64 * 1024 * 1024


def read_project_source_artifact(
    path: str | Path,
    artifact_uri: str,
    *,
    expected_manifest_payload_sha256: str,
    expected_source_sha256: str,
    max_bytes: int = MAX_PROJECT_SOURCE_BYTES,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> bytes:
    """Read one canonical design source without retaining unrelated package members."""

    if (
        not isinstance(artifact_uri, str)
        or not artifact_uri.startswith("package:sources/")
        or "\\" in artifact_uri
        or ".." in Path(artifact_uri.removeprefix("package:")).parts
    ):
        raise ProjectPackageError("The canonical design source must use a safe package:sources URI.")
    if re.fullmatch(r"[0-9a-f]{64}", str(expected_manifest_payload_sha256)) is None:
        raise ProjectPackageError("An opened project manifest identity is required for source reads.")
    if re.fullmatch(r"[0-9a-f]{64}", str(expected_source_sha256)) is None:
        raise ProjectPackageError("A canonical design source digest is required for source reads.")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 0 < max_bytes <= MAX_PROJECT_SOURCE_BYTES:
        raise ProjectPackageError("The project source byte budget is invalid.")
    member_path = _safe_member_path(
        artifact_uri.removeprefix("package:"), max_depth=PackageLimits().max_path_depth,
    )
    source = Path(path)
    limits = PackageLimits()
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = _validate_archive(archive, limits)
            if infos["manifest.json"].file_size > limits.max_manifest_bytes:
                raise ProjectPackageError("Package manifest exceeds the configured limit.")
            manifest = json.loads(archive.read(infos["manifest.json"]))
            if not isinstance(manifest, Mapping) or manifest.get("format") != PROJECT_FORMAT_V3 or manifest.get("contract") != PROJECT_CONTRACT_V3:
                raise ProjectPackageError("Canonical source reads require a SPIKE v3 project package.")
            recorded_digest = str(manifest.get("manifest_payload_sha256", ""))
            unsigned = dict(manifest)
            unsigned.pop("signature", None)
            unsigned.pop("manifest_payload_sha256", None)
            if recorded_digest != _sha256(_json_bytes(unsigned)):
                raise ProjectPackageError("Package manifest integrity check failed.")
            validate_targeted_manifest_signature(
                manifest, signature_verifier=signature_verifier, require_signature=require_signature,
            )
            if recorded_digest != expected_manifest_payload_sha256:
                raise ProjectPackageError("The project package changed after its opened manifest identity; reopen it before loading the design source.")
            raw_records = manifest.get("members")
            if not isinstance(raw_records, list):
                raise ProjectPackageError("Package manifest members must be an array.")
            records: Dict[str, Mapping[str, Any]] = {}
            for record in raw_records:
                if not isinstance(record, Mapping):
                    raise ProjectPackageError("Package manifest contains an invalid member record.")
                declared_path = _safe_member_path(str(record.get("path", "")), max_depth=limits.max_path_depth)
                if declared_path in records or declared_path not in infos:
                    raise ProjectPackageError(f"Package manifest member is duplicate or missing: {declared_path}")
                records[declared_path] = record
            undeclared = set(infos) - {"manifest.json"} - set(records)
            if undeclared:
                raise ProjectPackageError(f"Package contains undeclared members: {', '.join(sorted(undeclared)[:5])}")
            record = records.get(member_path)
            if record is None:
                raise ProjectPackageError(f"Canonical design source is missing from the manifest: {member_path}")
            try:
                size = int(record.get("size", -1))
            except (TypeError, ValueError) as exc:
                raise ProjectPackageError("Canonical design source has an invalid size.") from exc
            info = infos[member_path]
            # Neither the manifest nor the central directory is authoritative
            # by itself.  Reject both an over-budget entry and disagreement
            # before _verify_member_stream can retain expanded source bytes.
            if size < 0 or size > max_bytes or info.file_size > max_bytes:
                raise ProjectPackageError(f"Canonical design source exceeds the {max_bytes} byte desktop limit.")
            if info.file_size != size:
                raise ProjectPackageError("Canonical design source size does not match its manifest record.")
            if str(record.get("sha256", "")) != expected_source_sha256:
                raise ProjectPackageError("Canonical design source identity does not match DesignIR.")
            return _verify_member_stream(
                archive,
                info,
                expected_size=size,
                expected_sha256=expected_source_sha256,
                retain=True,
            ) or b""
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("The selected file is not a valid SPIKE v3 ZIP package.") from exc


def _read_model_artifacts(
    path: str | Path,
    model_ids: Sequence[str],
    *,
    expected_manifest_payload_sha256: str,
    max_total_bytes: int = MAX_VISUAL_MODEL_BYTES,
    allowed_model_types: frozenset[str],
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> list[Dict[str, Any]]:
    """Read only selected self-contained glTF/GLB members.

    The caller supplies the manifest identity established during approved
    project open. One archive handle validates the central directory and that
    manifest, then reads only the model index and requested members. This binds
    the viewport to the opened package without rehashing unrelated multi-GiB
    results/source artifacts.
    """

    if isinstance(model_ids, (str, bytes)) or not isinstance(model_ids, Sequence):
        raise ProjectPackageError("Visual model identifiers must be an array.")
    if not model_ids:
        return []
    if len(model_ids) > MAX_VISUAL_MODEL_COUNT:
        raise ProjectPackageError(
            f"A viewport request may contain at most {MAX_VISUAL_MODEL_COUNT} model identifiers."
        )
    if not isinstance(max_total_bytes, int) or isinstance(max_total_bytes, bool) or max_total_bytes <= 0:
        raise ProjectPackageError("The visual model byte budget must be a positive integer.")
    max_total_bytes = min(max_total_bytes, MAX_VISUAL_MODEL_BYTES)
    if (
        not isinstance(expected_manifest_payload_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_payload_sha256) is None
    ):
        raise ProjectPackageError("An opened project manifest identity is required for visual model reads.")

    requested: list[str] = []
    seen: set[str] = set()
    for value in model_ids:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ProjectPackageError("Visual model identifiers must be non-empty strings.")
        if value in seen:
            continue
        requested.append(value)
        seen.add(value)

    source = Path(path)
    limits = PackageLimits()
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = _validate_archive(archive, limits)
            if infos["manifest.json"].file_size > limits.max_manifest_bytes:
                raise ProjectPackageError("Package manifest exceeds the configured limit.")
            manifest = json.loads(archive.read(infos["manifest.json"]))
            if not isinstance(manifest, Mapping):
                raise ProjectPackageError("Package manifest must be a JSON object.")
            if manifest.get("format") != PROJECT_FORMAT_V3 or manifest.get("contract") != PROJECT_CONTRACT_V3:
                raise ProjectPackageError("Model artifact reads require a SPIKE v3 project package.")
            recorded_manifest_digest = str(manifest.get("manifest_payload_sha256", ""))
            unsigned_manifest = dict(manifest)
            unsigned_manifest.pop("signature", None)
            unsigned_manifest.pop("manifest_payload_sha256", None)
            if recorded_manifest_digest != _sha256(_json_bytes(unsigned_manifest)):
                raise ProjectPackageError("Package manifest integrity check failed.")
            validate_targeted_manifest_signature(
                manifest, signature_verifier=signature_verifier, require_signature=require_signature,
            )
            if recorded_manifest_digest != expected_manifest_payload_sha256:
                raise ProjectPackageError(
                    "The project package changed after its opened manifest identity; reopen it before loading visual models."
                )

            raw_records = manifest.get("members")
            if not isinstance(raw_records, list):
                raise ProjectPackageError("Package manifest members must be an array.")
            records: Dict[str, Mapping[str, Any]] = {}
            for record in raw_records:
                if not isinstance(record, Mapping):
                    raise ProjectPackageError("Package manifest contains an invalid member record.")
                member_path = _safe_member_path(str(record.get("path", "")), max_depth=limits.max_path_depth)
                if member_path in records or member_path not in infos:
                    raise ProjectPackageError(f"Package manifest member is duplicate or missing: {member_path}")
                records[member_path] = record
            undeclared = set(infos) - {"manifest.json"} - set(records)
            if undeclared:
                raise ProjectPackageError(f"Package contains undeclared members: {', '.join(sorted(undeclared)[:5])}")

            index_path = "models/index.json"
            index_record = records.get(index_path)
            if index_record is None:
                raise ProjectPackageError("SPIKE project is missing its model index.")
            try:
                index_size = int(index_record.get("size", -1))
            except (TypeError, ValueError) as exc:
                raise ProjectPackageError("Package model index has an invalid size.") from exc
            index_info = infos[index_path]
            if (
                index_size < 0
                or index_size > limits.max_manifest_bytes
                or index_info.file_size > limits.max_manifest_bytes
            ):
                raise ProjectPackageError("Package model index exceeds the configured limit.")
            if index_info.file_size != index_size:
                raise ProjectPackageError("Package model index size does not match its manifest record.")
            try:
                index_data = _verify_member_stream(
                    archive,
                    index_info,
                    expected_size=index_size,
                    expected_sha256=str(index_record.get("sha256", "")),
                    retain=True,
                )
                model_index = canonicalize_model_index(json.loads(index_data or b"{}"))
                validate_model_artifacts(
                    model_index,
                    {name: str(record.get("sha256", "")) for name, record in records.items()},
                )
            except (ModelIndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ProjectPackageError(f"Package model index is invalid: {exc}") from exc

            by_id = {
                str(model.get("id")): model
                for model in model_index.get("models", [])
                if isinstance(model, Mapping)
            }
            selections: Dict[str, Dict[str, Any]] = {}
            total = 0
            for model_id in requested:
                model = by_id.get(model_id)
                if model is None:
                    raise ProjectPackageError(f"The requested visual model is not indexed: {model_id}")
                model_type = str(model.get("model_type", ""))
                if model_type not in allowed_model_types:
                    if model_type == "step" and allowed_model_types == frozenset({"gltf", "glb"}):
                        raise ProjectPackageError(
                            f"Model {model_id} is step; STEP requires tessellation before viewport display."
                        )
                    raise ProjectPackageError(
                        f"Model {model_id} is {model_type or 'untyped'} and is not permitted for this artifact operation."
                    )
                member_path = str(model.get("uri", "")).removeprefix("package:")
                record = records.get(member_path)
                if record is None:
                    raise ProjectPackageError(f"Visual model artifact is missing from the manifest: {member_path}")
                selection = selections.get(member_path)
                if selection is not None:
                    selection["model_ids"].append(model_id)
                    continue
                try:
                    member_size = int(record.get("size", -1))
                except (TypeError, ValueError) as exc:
                    raise ProjectPackageError(f"Visual model artifact has an invalid size: {member_path}") from exc
                info = infos.get(member_path)
                if info is None:
                    raise ProjectPackageError(f"Visual model artifact is missing: {member_path}")
                remaining = max_total_bytes - total
                if member_size < 0 or member_size > remaining or info.file_size > remaining:
                    raise ProjectPackageError(
                        f"Requested visual model artifacts exceed the {max_total_bytes} byte viewport limit."
                    )
                if info.file_size != member_size:
                    raise ProjectPackageError(
                        f"Visual model artifact size does not match its manifest record: {member_path}"
                    )
                total += member_size
                selections[member_path] = {"model": model, "record": record, "model_ids": [model_id]}

            artifacts: list[Dict[str, Any]] = []
            for selection in selections.values():
                model = selection["model"]
                record = selection["record"]
                member_path = str(record["path"])
                info = infos.get(member_path)
                if info is None:
                    raise ProjectPackageError(f"Visual model artifact is missing: {member_path}")
                data = _verify_member_stream(
                    archive,
                    info,
                    expected_size=int(record["size"]),
                    expected_sha256=str(record["sha256"]),
                    retain=True,
                )
                try:
                    if str(model["model_type"]) == "step":
                        validate_step_mcad_artifact(data or b"")
                    else:
                        validate_visual_mcad_artifact(str(model["model_type"]), data or b"")
                except McadImportError as exc:
                    raise ProjectPackageError(
                        f"Visual model artifact is unsafe or invalid: {member_path}: {exc}"
                    ) from exc
                artifacts.append({
                    "model_id": str(model["id"]),
                    "model_ids": list(selection["model_ids"]),
                    "model_type": str(model["model_type"]),
                    "digest": str(model["digest"]),
                    "media_type": str(record.get("media_type", "application/octet-stream")),
                    "artifact": data or b"",
                })
            return artifacts
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("The selected file is not a valid SPIKE v3 ZIP package.") from exc


def read_visual_model_artifacts(
    path: str | Path,
    model_ids: Sequence[str],
    *,
    expected_manifest_payload_sha256: str,
    max_total_bytes: int = MAX_VISUAL_MODEL_BYTES,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> list[Dict[str, Any]]:
    """Read only selected self-contained glTF/GLB members for the viewport."""

    return _read_model_artifacts(
        path, model_ids, expected_manifest_payload_sha256=expected_manifest_payload_sha256,
        max_total_bytes=max_total_bytes, allowed_model_types=frozenset({"gltf", "glb"}),
        signature_verifier=signature_verifier, require_signature=require_signature,
    )


def read_step_model_artifact(
    path: str | Path,
    model_id: str,
    *,
    expected_manifest_payload_sha256: str,
    max_total_bytes: int = MAX_VISUAL_MODEL_BYTES,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> Dict[str, Any]:
    """Read one digest-verified retained STEP model for visual tessellation only."""

    artifacts = _read_model_artifacts(
        path, [model_id], expected_manifest_payload_sha256=expected_manifest_payload_sha256,
        max_total_bytes=max_total_bytes, allowed_model_types=frozenset({"step"}),
        signature_verifier=signature_verifier, require_signature=require_signature,
    )
    return artifacts[0]


def read_package_shape_selector_previews(
    path: str | Path,
    shape_ids: Sequence[str],
    *,
    expected_manifest_payload_sha256: str,
    max_total_bytes: int = MAX_SELECTOR_PREVIEW_BYTES,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> list[Dict[str, Any]]:
    """Read only requested, manifest-bound exact-selector preview GLBs."""

    if isinstance(shape_ids, (str, bytes)) or not isinstance(shape_ids, Sequence) or not shape_ids:
        raise ProjectPackageError("Selector-preview shape identifiers must be a non-empty array.")
    if len(shape_ids) > MAX_SELECTOR_PREVIEW_COUNT:
        raise ProjectPackageError(f"A selector-preview request may contain at most {MAX_SELECTOR_PREVIEW_COUNT} shape identifiers.")
    if not isinstance(max_total_bytes, int) or isinstance(max_total_bytes, bool) or max_total_bytes <= 0:
        raise ProjectPackageError("The selector-preview byte budget must be a positive integer.")
    max_total_bytes = min(max_total_bytes, MAX_SELECTOR_PREVIEW_BYTES)
    if not isinstance(expected_manifest_payload_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_payload_sha256) is None:
        raise ProjectPackageError("An opened project manifest identity is required for selector-preview reads.")
    requested = []
    seen = set()
    for value in shape_ids:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ProjectPackageError("Selector-preview shape identifiers must be non-empty strings.")
        if value in seen:
            raise ProjectPackageError(f"Selector-preview shape identifier is duplicated: {value}")
        seen.add(value)
        requested.append(value)

    source = Path(path)
    limits = PackageLimits()
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = _validate_archive(archive, limits)
            if infos["manifest.json"].file_size > limits.max_manifest_bytes:
                raise ProjectPackageError("Package manifest exceeds the configured limit.")
            manifest = json.loads(archive.read(infos["manifest.json"]))
            if not isinstance(manifest, Mapping) or manifest.get("format") != PROJECT_FORMAT_V3 or manifest.get("contract") != PROJECT_CONTRACT_V3:
                raise ProjectPackageError("Selector-preview reads require a SPIKE v3 project package.")
            recorded_digest = str(manifest.get("manifest_payload_sha256", ""))
            unsigned = dict(manifest); unsigned.pop("signature", None); unsigned.pop("manifest_payload_sha256", None)
            if recorded_digest != _sha256(_json_bytes(unsigned)):
                raise ProjectPackageError("Package manifest integrity check failed.")
            validate_targeted_manifest_signature(
                manifest, signature_verifier=signature_verifier, require_signature=require_signature,
            )
            if recorded_digest != expected_manifest_payload_sha256:
                raise ProjectPackageError("The project package changed after its opened manifest identity; reopen it before loading selector previews.")
            raw_records = manifest.get("members")
            if not isinstance(raw_records, list):
                raise ProjectPackageError("Package manifest members must be an array.")
            records: Dict[str, Mapping[str, Any]] = {}
            for record in raw_records:
                if not isinstance(record, Mapping):
                    raise ProjectPackageError("Package manifest contains an invalid member record.")
                member_path = _safe_member_path(str(record.get("path", "")), max_depth=limits.max_path_depth)
                if member_path in records or member_path not in infos:
                    raise ProjectPackageError(f"Package manifest member is duplicate or missing: {member_path}")
                records[member_path] = record
            undeclared = set(infos) - {"manifest.json"} - set(records)
            if undeclared:
                raise ProjectPackageError(f"Package contains undeclared members: {', '.join(sorted(undeclared)[:5])}")

            def read_index(member_path: str) -> Any:
                record = records.get(member_path)
                if record is None:
                    raise ProjectPackageError(f"SPIKE project is missing or exceeds the limit for {member_path}.")
                try:
                    size = int(record.get("size", -1))
                except (TypeError, ValueError) as exc:
                    raise ProjectPackageError(f"SPIKE project index has an invalid size: {member_path}") from exc
                info = infos[member_path]
                if size < 0 or size > limits.max_manifest_bytes or info.file_size > limits.max_manifest_bytes:
                    raise ProjectPackageError(f"SPIKE project is missing or exceeds the limit for {member_path}.")
                if info.file_size != size:
                    raise ProjectPackageError(f"SPIKE project index size does not match its manifest record: {member_path}")
                data = _verify_member_stream(archive, info, expected_size=size, expected_sha256=str(record.get("sha256", "")), retain=True)
                return json.loads(data or b"{}")

            try:
                model_index = canonicalize_model_index(read_index("models/index.json"))
                validate_model_artifacts(model_index, {name: str(record.get("sha256", "")) for name, record in records.items()})
                assembly = AssemblyIRV1.from_dict(read_index("design/assembly-ir.json")).to_dict()
                shape_index = canonicalize_assembly_package_shapes(read_index("design/assembly-package-shapes.json"), assembly, model_index)
                validate_package_shape_artifacts(shape_index, {name: str(record.get("sha256", "")) for name, record in records.items()})
            except (AssemblyPackageShapeError, ModelIndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ProjectPackageError(f"Package selector-preview index is invalid: {exc}") from exc
            by_id = {str(item.get("shape_id")): item for item in shape_index.get("shapes", []) if isinstance(item, Mapping)}
            selections = []
            total = 0
            for shape_id in requested:
                shape = by_id.get(shape_id)
                preview = shape.get("selector_preview") if shape is not None else None
                if shape is None or not isinstance(preview, Mapping):
                    raise ProjectPackageError(f"The requested exact shape has no selector preview: {shape_id}")
                member_path = str(preview.get("artifact_uri", "")).removeprefix("package:")
                record = records.get(member_path)
                if record is None:
                    raise ProjectPackageError(f"Selector-preview artifact is missing from the manifest: {member_path}")
                try:
                    size = int(record.get("size", -1))
                except (TypeError, ValueError) as exc:
                    raise ProjectPackageError(f"Selector-preview artifact has an invalid size: {member_path}") from exc
                info = infos.get(member_path)
                if info is None:
                    raise ProjectPackageError(f"Selector-preview artifact is missing: {member_path}")
                remaining = max_total_bytes - total
                if size < 0 or size > remaining or info.file_size > remaining:
                    raise ProjectPackageError(f"Requested selector-preview artifacts exceed the {max_total_bytes} byte limit.")
                if info.file_size != size:
                    raise ProjectPackageError(f"Selector-preview artifact size does not match its manifest record: {member_path}")
                total += size
                selections.append((shape, preview, member_path, record))
            artifacts = []
            preview_policy = SelectorPreviewPolicy(max_output_bytes=max_total_bytes)
            for shape, preview, member_path, record in selections:
                data = _verify_member_stream(archive, infos[member_path], expected_size=int(record["size"]), expected_sha256=str(record["sha256"]), retain=True) or b""
                try:
                    counts = _validate_selector_glb(data, shape["entities"], preview_policy)
                except McadSelectorPreviewError as exc:
                    raise ProjectPackageError(f"Selector-preview artifact is unsafe or invalid: {member_path}: {exc}") from exc
                if any(counts[field] != preview[field] for field in ("face_count", "edge_count", "axis_count")):
                    raise ProjectPackageError(f"Selector-preview artifact counts do not match the canonical index: {member_path}")
                artifacts.append({
                    "shape_id": shape["shape_id"], "part_id": shape["part_id"],
                    "artifact_sha256": preview["artifact_sha256"], "source_sha256": preview["source_sha256"],
                    "topology_artifact_sha256": preview["topology_artifact_sha256"],
                    "selector_inventory_sha256": preview["selector_inventory_sha256"],
                    "artifact": data,
                })
            return artifacts
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("The selected file is not a valid SPIKE v3 ZIP package.") from exc
