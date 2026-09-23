"""Targeted, manifest-bound reads for generated Arrow geometry tables."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping

from .design_ir_v2 import DesignIRV2
from .geometry_arrow import (
    GEOMETRY_ARROW_CONTRACTS, MAX_GEOMETRY_ARROW_IPC_BYTES, MAX_GEOMETRY_ARROW_ROWS,
    GeometryArrowError, validate_geometry_arrow,
)
from .project_geometry_index import validate_geometry_index
from .project_package import (
    PROJECT_CONTRACT_V3, PROJECT_FORMAT_V3, ManifestVerifier, PackageLimits, ProjectPackageError,
    _json_bytes, _safe_member_path, _sha256, _validate_archive, _verify_member_stream,
)
from .project_package_auth import validate_targeted_manifest_signature


# Public compatibility alias for callers using the targeted package reader.
MAX_GEOMETRY_ARROW_BYTES = MAX_GEOMETRY_ARROW_IPC_BYTES


def read_geometry_arrow_artifact(
    path: str | Path,
    table_path: str,
    *,
    expected_manifest_payload_sha256: str,
    max_bytes: int = MAX_GEOMETRY_ARROW_BYTES,
    max_ipc_bytes: int | None = None,
    max_rows: int = MAX_GEOMETRY_ARROW_ROWS,
    signature_verifier: ManifestVerifier | None = None,
    require_signature: bool = False,
) -> Dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{64}", str(expected_manifest_payload_sha256)) is None:
        raise ProjectPackageError("An opened project manifest identity is required for Arrow geometry reads.")
    if max_ipc_bytes is not None:
        if max_bytes != MAX_GEOMETRY_ARROW_BYTES and max_bytes != max_ipc_bytes:
            raise ProjectPackageError("Conflicting Arrow geometry byte budgets were supplied.")
        max_bytes = max_ipc_bytes
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 0 < max_bytes <= MAX_GEOMETRY_ARROW_BYTES:
        raise ProjectPackageError("The Arrow geometry byte budget is invalid.")
    if (not isinstance(max_rows, int) or isinstance(max_rows, bool)
            or not 0 < max_rows <= MAX_GEOMETRY_ARROW_ROWS):
        raise ProjectPackageError("The Arrow geometry row budget is invalid.")
    requested_path = _safe_member_path(table_path)
    source = Path(path)
    limits = PackageLimits()
    try:
        with zipfile.ZipFile(source, mode="r") as archive:
            infos = _validate_archive(archive, limits)
            if infos["manifest.json"].file_size > limits.max_manifest_bytes:
                raise ProjectPackageError("Package manifest exceeds the configured limit.")
            manifest = json.loads(archive.read(infos["manifest.json"]))
            if not isinstance(manifest, Mapping) or manifest.get("format") != PROJECT_FORMAT_V3 or manifest.get("contract") != PROJECT_CONTRACT_V3:
                raise ProjectPackageError("Arrow geometry reads require a SPIKE v3 project package.")
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
                raise ProjectPackageError("The project package changed after its opened manifest identity; reopen it before reading Arrow geometry.")
            raw_records = manifest.get("members")
            if not isinstance(raw_records, list):
                raise ProjectPackageError("Package manifest members must be an array.")
            records: Dict[str, Mapping[str, Any]] = {}
            for raw in raw_records:
                if not isinstance(raw, Mapping):
                    raise ProjectPackageError("Package manifest contains an invalid member record.")
                member_path = _safe_member_path(str(raw.get("path", "")), max_depth=limits.max_path_depth)
                if member_path in records or member_path not in infos:
                    raise ProjectPackageError(f"Package manifest member is duplicate or missing: {member_path}")
                records[member_path] = raw
            undeclared = set(infos) - {"manifest.json"} - set(records)
            if undeclared:
                raise ProjectPackageError(f"Package contains undeclared members: {', '.join(sorted(undeclared)[:5])}")

            def verified_json(member_path: str) -> Any:
                record = records.get(member_path)
                if record is None:
                    raise ProjectPackageError(f"Package is missing required Arrow binding member: {member_path}")
                if infos[member_path].file_size > limits.max_manifest_bytes:
                    raise ProjectPackageError(f"Arrow binding member exceeds the configured limit: {member_path}")
                data = _verify_member_stream(
                    archive, infos[member_path], expected_size=int(record.get("size", -1)),
                    expected_sha256=str(record.get("sha256", "")), retain=True,
                )
                return json.loads(data or b"{}")

            design_raw = verified_json("design/design-ir.json")
            index = validate_geometry_index(
                verified_json("geometry/index.json"),
                {name: str(record.get("sha256", "")) for name, record in records.items()},
                design_raw,
                safe_member_path=_safe_member_path,
                error_type=ProjectPackageError,
            )
            table = next((item for item in index["tables"] if item["path"] == requested_path), None)
            if table is None:
                raise ProjectPackageError(f"The requested Arrow geometry table is not indexed: {requested_path}")
            if table.get("schema") not in GEOMETRY_ARROW_CONTRACTS:
                raise ProjectPackageError("Only canonical generated Arrow geometry tables can be decoded.")
            record = records[requested_path]
            size = int(record.get("size", -1))
            actual_size = infos[requested_path].file_size
            # Both values are untrusted package metadata.  Check them before
            # asking ZipFile to decompress and retain the Arrow payload.
            if size < 0 or size > max_bytes or actual_size > max_bytes:
                raise ProjectPackageError(f"Arrow geometry table exceeds the {max_bytes} byte limit.")
            if actual_size != size:
                raise ProjectPackageError("Arrow geometry table size does not match its manifest record.")
            data = _verify_member_stream(
                archive, infos[requested_path], expected_size=size,
                expected_sha256=str(record.get("sha256", "")), retain=True,
            ) or b""
            try:
                rows = validate_geometry_arrow(
                    data, DesignIRV2.from_dict(design_raw),
                    max_ipc_bytes=max_bytes, max_rows=max_rows,
                )
            except (GeometryArrowError, TypeError, ValueError) as exc:
                raise ProjectPackageError(f"Arrow geometry table is invalid: {exc}") from exc
            return {"table": table, "artifact": data, "rows": rows}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, ProjectPackageError):
            raise
        raise ProjectPackageError(f"Arrow geometry package metadata is invalid: {exc}") from exc
    except zipfile.BadZipFile as exc:
        raise ProjectPackageError("The selected file is not a valid SPIKE v3 ZIP package.") from exc
