"""Embed imported PCB visuals and restore them without the original CAD tools."""
from __future__ import annotations

import base64
import binascii
import tempfile
from pathlib import Path
from typing import Any

from .models import _glb_external_resource_uris, _valid_glb
from .project_package import ProjectPackageError, _sha256
from .project_state_artifacts import read_verified_artifacts

VISUALS_CONTRACT = "spike/saved-board-visuals/v1"
MAX_VISUAL_BYTES = 96 * 1024 * 1024


def prepare_visual_artifacts(raw: Any, source_digest: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not isinstance(raw, dict) or raw.get("contract") != VISUALS_CONTRACT:
        raise ProjectPackageError("Unsupported saved board visual contract.")
    entries = raw.get("artifacts")
    if not isinstance(entries, list) or not 0 < len(entries) <= 256:
        raise ProjectPackageError("Saved board visuals require between one and 256 artifacts.")
    records, artifacts, roles = [], {}, set()
    total = 0
    with tempfile.TemporaryDirectory(prefix="spike-visual-save-") as directory:
        for entry in entries:
            if not isinstance(entry, dict):
                raise ProjectPackageError("Malformed saved visual artifact.")
            role = str(entry.get("role", ""))
            if role in roles or not (role in {"board", "components"} or role.startswith("layer:") and len(role) > 6):
                raise ProjectPackageError("Duplicate or invalid visual role.")
            roles.add(role)
            media_type = "image/svg+xml" if role.startswith("layer:") else "model/gltf-binary"
            if entry.get("media_type") != media_type:
                raise ProjectPackageError("Saved visual media type does not match its role.")
            size = entry.get("bytes")
            encoded = entry.get("artifact_base64")
            if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_VISUAL_BYTES:
                raise ProjectPackageError("Saved visual size is invalid.")
            if not isinstance(encoded, str) or len(encoded) > (size + 2) // 3 * 4:
                raise ProjectPackageError("Saved visual encoding exceeds its declared size.")
            total += size
            if total > MAX_VISUAL_BYTES:
                raise ProjectPackageError("Saved visual artifacts exceed the 96 MiB transport limit.")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ProjectPackageError("Invalid saved visual encoding.") from exc
            digest = _sha256(data)
            if len(data) != size or digest != entry.get("sha256"):
                raise ProjectPackageError("Saved visual failed its size or SHA-256 check.")
            suffix = ".svg" if role.startswith("layer:") else ".glb"
            if suffix == ".svg":
                if b"<svg" not in data[:4096].lower():
                    raise ProjectPackageError("Saved layer is not SVG.")
            else:
                local = Path(directory) / f"{digest}.glb"
                local.write_bytes(data)
                if not _valid_glb(local) or _glb_external_resource_uris(local):
                    raise ProjectPackageError("Saved model must be a self-contained GLB.")
            name = f"visuals/artifacts/{digest}{suffix}"
            artifacts[name] = data
            records.append({"role": role, "path": name, "sha256": digest, "bytes": size, "media_type": media_type})
    return {"contract": VISUALS_CONTRACT, "source_digest": source_digest,
            "board_includes_copper": raw.get("board_includes_copper", True) is not False,
            "view_box": raw.get("view_box", []), "quality": raw.get("quality", {}), "artifacts": records}, artifacts


def read_saved_visual_stage(path: str | Path, index: dict[str, Any], stage: str, manifest_digest: str) -> dict[str, Any]:
    if index.get("contract") != VISUALS_CONTRACT or stage not in {"layout", "board", "components"}:
        raise ProjectPackageError("Unsupported saved visual stage.")
    entries = [entry for entry in index.get("artifacts", [])
               if (str(entry.get("role", "")).startswith("layer:") if stage == "layout" else entry.get("role") == stage)]
    if not entries:
        return {"available": False}
    data = read_verified_artifacts(path, entries, expected_manifest_payload_sha256=manifest_digest,
                                   allowed_prefix="visuals/artifacts/", max_bytes=MAX_VISUAL_BYTES)
    scenes, layers = {}, {}
    total = 0
    for entry in entries:
        role = entry["role"]
        artifact = {key: entry[key] for key in ("bytes", "sha256", "media_type")}
        artifact.update({"file_name": Path(entry["path"]).name,
                         "artifact_base64": base64.b64encode(data[entry["path"]]).decode("ascii")})
        total += entry["bytes"]
        if role.startswith("layer:"):
            layers[role[6:]] = artifact
        else:
            scenes[role] = artifact
    return {"contract": "spike/visual-bundle-payload/v1", "status": "ready", "scenes": scenes,
            "layout": {"layers": layers, "view_box": index.get("view_box", [])},
            "quality": {**index.get("quality", {}), "board_includes_copper": index.get("board_includes_copper", True)},
            "artifact_bytes": total, "artifact_limit_bytes": MAX_VISUAL_BYTES,
            "security": {"self_contained_glb_required": True, "external_resource_uris_allowed": False}}
