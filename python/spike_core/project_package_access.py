"""Compatibility accessors layered over the secure project-package core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_LEGACY_PROJECT_BYTES = 256 * 1024 * 1024


def read_visual_model_artifacts(path: str | Path, model_ids: list[str], **kwargs: Any):
    from .project_model_artifacts import read_visual_model_artifacts as implementation
    return implementation(path, model_ids, **kwargs)


def read_geometry_arrow_artifact(path: str | Path, table_path: str, **kwargs: Any):
    from .project_geometry_artifacts import read_geometry_arrow_artifact as implementation
    return implementation(path, table_path, **kwargs)


def read_project(path: str | Path, **kwargs: Any):
    from .project_package import (
        PROJECT_CONTRACT_V3, PROJECT_FORMAT_V3, PackageReadResult, ProjectPackageError,
        migrate_legacy_payload, read_spike_package,
    )

    source = Path(path)
    with source.open("rb") as handle:
        signature = handle.read(4)
    if signature.startswith(b"PK"):
        return read_spike_package(source, **kwargs)
    # Large ZIP64 packages stream through the reader, whereas legacy JSON is
    # materialized in memory. Keep that separate allocation boundary explicit.
    if source.stat().st_size > MAX_LEGACY_PROJECT_BYTES:
        raise ProjectPackageError("Legacy JSON project exceeds the 256 MiB text limit; use a SPIKE v3 package.")
    try:
        with source.open("rb") as handle:
            data = handle.read(MAX_LEGACY_PROJECT_BYTES + 1)
        if len(data) > MAX_LEGACY_PROJECT_BYTES:
            raise ProjectPackageError("Legacy JSON project exceeds the 256 MiB text limit; use a SPIKE v3 package.")
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectPackageError("Project is neither a SPIKE v3 package nor supported legacy JSON.") from exc
    if not isinstance(raw, dict):
        raise ProjectPackageError("Legacy SPIKE project must contain a JSON object.")
    payload = migrate_legacy_payload(raw)
    return PackageReadResult(
        manifest={"format": PROJECT_FORMAT_V3, "contract": PROJECT_CONTRACT_V3, "profile": "portable_project"},
        payload=payload, migrated=True, source_format=str(raw.get("format", "unknown")),
    )
