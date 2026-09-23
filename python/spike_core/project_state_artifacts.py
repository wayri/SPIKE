"""Portable desktop state and result artifacts, separate from package metadata."""
from __future__ import annotations

import copy
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping

from .project_package import (
    PackageLimits, ProjectPackageError, PROJECT_FORMAT_V3, PROJECT_CONTRACT_V3,
    _json_bytes, _safe_member_path, _sha256, _validate_archive, _verify_member_stream,
)
from .project_package_auth import validate_targeted_manifest_signature

STATE_REFERENCE = "spike/state-artifact-reference/v1"
MAX_STATE_BYTES = 96 * 1024 * 1024


def read_verified_artifacts(path: str | Path, references: list[Mapping[str, Any]], *,
                            expected_manifest_payload_sha256: str,
                            allowed_prefix: str, max_bytes: int = MAX_STATE_BYTES) -> dict[str, bytes]:
    """Read a bounded set from the exact manifest opened by the native host."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_payload_sha256):
        raise ProjectPackageError("An opened manifest identity is required for saved artifact reads.")
    if len(references) > 256:
        raise ProjectPackageError("Too many saved artifacts requested.")
    limits = PackageLimits()
    with zipfile.ZipFile(path) as archive:
        infos = _validate_archive(archive, limits)
        if infos["manifest.json"].file_size > limits.max_manifest_bytes:
            raise ProjectPackageError("Package manifest exceeds the configured limit.")
        manifest = json.loads(archive.read(infos["manifest.json"]))
        if not isinstance(manifest, dict) or manifest.get("format") != PROJECT_FORMAT_V3 or manifest.get("contract") != PROJECT_CONTRACT_V3:
            raise ProjectPackageError("Saved artifact reads require a SPIKE v3 package.")
        unsigned = dict(manifest)
        unsigned.pop("signature", None)
        digest = unsigned.pop("manifest_payload_sha256", None)
        if digest != _sha256(_json_bytes(unsigned)) or digest != expected_manifest_payload_sha256:
            raise ProjectPackageError("The package changed after opening; reopen it before reading saved artifacts.")
        validate_targeted_manifest_signature(manifest, signature_verifier=None, require_signature=False)
        records = {}
        for record in manifest.get("members", []):
            if not isinstance(record, dict):
                raise ProjectPackageError("Invalid package member record.")
            name = _safe_member_path(str(record.get("path", "")), max_depth=limits.max_path_depth)
            if name in records or name not in infos:
                raise ProjectPackageError("Duplicate or missing package member.")
            records[name] = record
        if set(infos) - {"manifest.json"} - set(records):
            raise ProjectPackageError("Package contains undeclared members.")
        requested = {}
        total = 0
        for reference in references:
            name = _safe_member_path(str(reference.get("path", "")), max_depth=limits.max_path_depth)
            if not name.startswith(allowed_prefix):
                raise ProjectPackageError("Saved artifact has an invalid member path.")
            record = records.get(name)
            if not record or record.get("sha256") != reference.get("sha256") or record.get("size") != reference.get("bytes"):
                raise ProjectPackageError("Saved artifact identity does not match the package manifest.")
            size = record["size"]
            if isinstance(size, bool) or not isinstance(size, int) or size < 1 or infos[name].file_size != size:
                raise ProjectPackageError("Saved artifact size does not match the package member.")
            if name not in requested:
                total += size
                requested[name] = record
        if total > max_bytes:
            raise ProjectPackageError(f"Saved artifact request exceeds its {max_bytes} byte limit.")
        return {name: _verify_member_stream(archive, infos[name], expected_size=record["size"],
                                          expected_sha256=record["sha256"], retain=True) or b""
                for name, record in requested.items()}


def externalize_result_state(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Deduplicate complete results while keeping metadata and future fields intact."""
    artifacts: dict[str, bytes] = {}
    references_by_identity: dict[int, dict[str, Any]] = {}

    def walk(value: Any, key: str = "") -> Any:
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, dict):
            return value
        if value.get("contract") == STATE_REFERENCE:
            return copy.deepcopy(value)
        contract = str(value.get("contract", ""))
        is_result = bool(value) and (
            key in {"latest_result", "active_result", "bundle", "latest_channel_result", "field_result"}
            or "analysis_id" in value and ("scalar_fields" in value or "outputs" in value)
            or contract.startswith("spike/") and ("-result/" in contract or "/analysis-result/" in contract)
        )
        if is_result:
            previous = references_by_identity.get(id(value))
            if previous is not None:
                return dict(previous)
            data = _json_bytes(value)
            if len(data) > MAX_STATE_BYTES:
                raise ProjectPackageError("A simulation result exceeds the 96 MiB artifact transport limit.")
            digest = _sha256(data)
            name = f"state/artifacts/{digest}.json"
            artifacts[name] = data
            reference = {"contract": STATE_REFERENCE, "path": name, "sha256": digest, "bytes": len(data)}
            references_by_identity[id(value)] = reference
            return dict(reference)
        return {name: walk(item, name) for name, item in value.items()}

    # Traverse immutable input before copying: a dense result is serialized
    # directly into its artifact, never duplicated as a full Python object tree.
    result = {name: walk(value) if name in {"analyses", "results", "extensions"} else copy.deepcopy(value)
              for name, value in payload.items()}
    return result, artifacts


def hydrate_result_state(value: Any, path: str | Path, digest: str) -> Any:
    """Compatibility path for clients that do not request deferred artifact reads."""
    cache: dict[str, Any] = {}

    def walk(item: Any) -> Any:
        if isinstance(item, list):
            return [walk(child) for child in item]
        if not isinstance(item, dict):
            return item
        if item.get("contract") == STATE_REFERENCE:
            name = item["path"]
            if name not in cache:
                data = read_verified_artifacts(path, [item], expected_manifest_payload_sha256=digest,
                                               allowed_prefix="state/artifacts/")
                cache[name] = json.loads(data[name])
            return cache[name]
        return {name: walk(child) for name, child in item.items()}

    return walk(value)
