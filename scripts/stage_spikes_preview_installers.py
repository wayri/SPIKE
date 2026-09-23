#!/usr/bin/env python3
"""Stage exact SPIKE preview installers and write their SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--application-version", required=True)
    parser.add_argument("--nsis", type=Path, required=True)
    parser.add_argument("--msi", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--msi-validation", choices=("passed", "suppressed_host_unavailable"),
        required=True,
    )
    arguments = parser.parse_args()
    destination = arguments.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for kind, source in (("nsis", arguments.nsis), ("msi", arguments.msi)):
        source = source.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() not in {".exe", ".msi"}:
            raise ValueError(f"invalid {kind} installer: {source}")
        target = destination / source.name
        shutil.copyfile(source, target)
        records.append({
            "file": target.name, "kind": kind, "size": target.stat().st_size,
            "sha256": _sha256(target), "authenticode": "NotSigned",
        })
    manifest = {
        "contract": "spike/windows-installer-manifest/v1",
        "product": "SPIKE", "version": arguments.version,
        "application_version": arguments.application_version,
        "channel": "engineering-preview", "production_qualified": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "msi_ice_validation": arguments.msi_validation,
        "files": records,
    }
    path = destination / f"SPIKE-{arguments.version}-preview-installers.json"
    path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
