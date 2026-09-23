"""Bounded CAD-neutral MCAD artifact ingestion for AssemblyIR.

This importer establishes identity, package persistence, and explicit import
quality.  It deliberately does not claim that STEP topology has been
tessellated or that an imported model is solver-ready.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Mapping

from .assembly_placement_policy import AssemblyPlacementPolicy
from .design_ir_v2 import AssemblyPart
from .design_ir_v2_schema import CoordinateFrame, ModelReference, canonical_uuid
from .importers import ImportPolicy, ImportReport


MCAD_IMPORT_CONTRACT = "spike/mcad-import-outcome/v1"
SUPPORTED_MCAD_EXTENSIONS = {".step": "step", ".stp": "step", ".gltf": "gltf", ".glb": "glb"}
_CHUNK_BYTES = 1024 * 1024


class McadImportError(ValueError):
    """Raised when an MCAD artifact cannot be safely and losslessly attached."""


@dataclass(frozen=True)
class McadImportOutcome:
    part: AssemblyPart
    model: ModelReference
    report: ImportReport
    artifact_name: str
    artifact_bytes: bytes
    contract: str = MCAD_IMPORT_CONTRACT

    def to_dict(self) -> Dict[str, Any]:
        """Return the JSON-safe public result; package bytes stay process-local."""

        return {
            "contract": self.contract,
            "part": asdict(self.part),
            "model": asdict(self.model),
            "report": self.report.to_dict(),
            "artifact_name": self.artifact_name,
        }


def _read_bounded(path: Path, policy: ImportPolicy) -> tuple[bytes, str]:
    size = path.stat().st_size
    if size <= 0:
        raise McadImportError("The selected MCAD artifact is empty.")
    if size > policy.max_source_bytes:
        raise McadImportError(
            f"MCAD artifact is {size} bytes; configured limit is {policy.max_source_bytes}."
        )
    digest = hashlib.sha256()
    payload = bytearray()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_BYTES):
            digest.update(chunk)
            payload.extend(chunk)
    return bytes(payload), digest.hexdigest()


def _validate_step(payload: bytes) -> Dict[str, Any]:
    head = payload[:4096].upper()
    tail = payload[-4096:].upper()
    if b"ISO-10303-21" not in head or b"END-ISO-10303-21" not in tail:
        raise McadImportError("STEP artifact is missing the ISO-10303-21 envelope.")
    return {"asset_version": "ISO-10303-21", "embedded_resources": True}


def validate_step_mcad_artifact(payload: bytes) -> Dict[str, Any]:
    """Revalidate retained STEP bytes before an optional visual conversion."""

    return _validate_step(payload)


def _reject_external_gltf_resources(document: Mapping[str, Any]) -> None:
    for collection_name in ("buffers", "images"):
        collection = document.get(collection_name, [])
        if not isinstance(collection, list):
            raise McadImportError(f"glTF {collection_name} must be an array.")
        for index, item in enumerate(collection):
            if not isinstance(item, Mapping):
                raise McadImportError(f"glTF {collection_name}[{index}] must be an object.")
            uri = item.get("uri")
            if uri is not None and not str(uri).startswith("data:"):
                raise McadImportError(
                    "glTF references external resources. Use GLB or embed all buffers and images before import."
                )


def _validate_gltf_document(document: Any) -> Dict[str, Any]:
    if not isinstance(document, Mapping):
        raise McadImportError("glTF root must be a JSON object.")
    asset = document.get("asset")
    if not isinstance(asset, Mapping) or not str(asset.get("version", "")).startswith("2"):
        raise McadImportError("Only glTF 2.x artifacts are supported.")
    _reject_external_gltf_resources(document)
    return {
        "asset_version": str(asset.get("version")),
        "generator": str(asset.get("generator", "")),
        "scene_count": len(document.get("scenes", [])) if isinstance(document.get("scenes", []), list) else 0,
        "node_count": len(document.get("nodes", [])) if isinstance(document.get("nodes", []), list) else 0,
        "embedded_resources": True,
    }


def _validate_gltf(payload: bytes) -> Dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise McadImportError("glTF artifact is not valid UTF-8 JSON.") from exc
    return _validate_gltf_document(document)


def _validate_glb(payload: bytes) -> Dict[str, Any]:
    if len(payload) < 20:
        raise McadImportError("GLB artifact is shorter than its required header and JSON chunk.")
    magic, version, declared_length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or declared_length != len(payload):
        raise McadImportError("GLB header, version, or declared length is invalid.")
    chunk_length, chunk_type = struct.unpack_from("<II", payload, 12)
    if chunk_type != 0x4E4F534A or 20 + chunk_length > len(payload):
        raise McadImportError("GLB does not contain a valid leading JSON chunk.")
    try:
        document = json.loads(payload[20:20 + chunk_length].rstrip(b"\x00 \t\r\n").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise McadImportError("GLB JSON chunk is invalid.") from exc
    metadata = _validate_gltf_document(document)
    metadata["binary_container"] = True
    return metadata


def validate_visual_mcad_artifact(model_type: str, payload: bytes) -> Dict[str, Any]:
    """Revalidate packaged viewport bytes without trusting their import history."""

    if model_type == "gltf":
        return _validate_gltf(payload)
    if model_type == "glb":
        return _validate_glb(payload)
    raise McadImportError("Only self-contained glTF 2.x and GLB artifacts are viewport-readable.")


def _safe_artifact_name(path: Path, digest: str) -> str:
    stem = "".join(character if character.isalnum() or character in "._+-" else "-" for character in path.stem)
    return f"{stem or 'model'}-{digest[:16]}{path.suffix.lower()}"


def import_mcad_artifact(
    source_path: str | Path,
    *,
    name: str = "",
    part_type: str = "mechanical",
    material_id: str = "",
    frame: CoordinateFrame | Mapping[str, Any] | None = None,
    policy: ImportPolicy | None = None,
) -> McadImportOutcome:
    """Validate one STEP/glTF artifact and create deterministic assembly entities."""

    policy = policy or ImportPolicy()
    source = Path(source_path)
    if not source.is_file():
        raise McadImportError("The selected MCAD artifact does not exist or is not a file.")
    source_format = SUPPORTED_MCAD_EXTENSIONS.get(source.suffix.lower())
    if not source_format:
        raise McadImportError("Supported MCAD artifacts are STEP, STP, glTF, and GLB.")
    payload, digest = _read_bounded(source, policy)
    metadata = (
        _validate_step(payload)
        if source_format == "step"
        else validate_visual_mcad_artifact(source_format, payload)
    )

    artifact_name = _safe_artifact_name(source, digest)
    source_id = f"artifact:{digest}"
    model_id = canonical_uuid(source_format, digest, "model", source_id)
    part_id = canonical_uuid(source_format, digest, "assembly-part", source_id)
    if isinstance(frame, CoordinateFrame):
        part_frame = frame
    else:
        frame_values = {
            key: value for key, value in dict(frame or {}).items()
            if key in CoordinateFrame.__dataclass_fields__
        }
        frame_values.setdefault("frame_id", canonical_uuid(source_format, digest, "frame", source_id))
        frame_values.setdefault("parent_frame_id", "assembly")
        part_frame = CoordinateFrame(**frame_values)
    display_name = name.strip() or source.stem
    package_uri = f"package:models/artifacts/{artifact_name}"
    model = ModelReference(
        id=model_id,
        source_id=source_id,
        name=display_name,
        model_type=source_format,
        uri=package_uri,
        digest=digest,
        extensions={"spike.mcad": {"original_name": source.name, **metadata}},
    )
    part = AssemblyPart(
        id=part_id,
        source_id=source_id,
        name=display_name,
        part_type=part_type.strip() or "mechanical",
        model_id=model_id,
        frame=part_frame,
        material_id=material_id.strip(),
        placement_policy=AssemblyPlacementPolicy(translation_snap_mm=1.0, rotation_snap_deg=15.0),
        extensions={"spike.mcad": {"source_format": source_format, "source_sha256": digest}},
    )
    report = ImportReport(
        importer_id="spike.mcad-neutral.v1",
        source_format=source_format,
        source_sha256=digest,
        source_size_bytes=len(payload),
        coverage={"assembly_parts": 1, "model_references": 1},
        object_map={source_id: part_id},
        model_resolution={"embedded": 1, "unresolved": 0},
        unsupported=[{
            "kind": "solver_semantics",
            "message": "Material, contact, boundary, and solver semantics require explicit assignment.",
        }],
        solver_readiness={
            "assembly_visualization": {"state": "available" if source_format in {"gltf", "glb"} else "requires_tessellation"},
            "multiphysics": {"state": "unsupported", "reason": "No material/contact/region semantics were inferred."},
        },
        diagnostics=[{"code": "MCAD_IDENTITY_CAPTURED", "message": "Artifact identity and package URI are deterministic."}],
    )
    return McadImportOutcome(part, model, report, artifact_name, payload)
