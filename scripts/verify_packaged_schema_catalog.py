# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Require the complete packaged schema payload to equal current source bytes."""
from hashlib import sha256
from pathlib import Path


def verify_packaged_schema_catalog(executable, source_root=None):
    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parents[1] / "schemas"
    packaged = Path(executable).parent / "_internal" / "schemas"
    source = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*.json")}
    actual = {path.relative_to(packaged).as_posix(): path.read_bytes() for path in packaged.rglob("*.json")}
    if not source or "manifest.json" not in source:
        raise RuntimeError("Source schema catalog is absent")
    missing = sorted(set(source) - set(actual))
    extra = sorted(set(actual) - set(source))
    changed = sorted(name for name in set(source) & set(actual) if source[name] != actual[name])
    if missing or extra or changed:
        raise RuntimeError(f"Packaged schemas differ from source: missing={missing}, extra={extra}, changed={changed}")
    return {"status": "passed", "json_files": len(source),
            "manifest_sha256": sha256(source["manifest.json"]).hexdigest()}
