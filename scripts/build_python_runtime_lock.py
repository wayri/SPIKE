"""Generate a deterministic hash-pinned Python lock from an offline wheel set."""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import re
import zipfile
from pathlib import Path
from typing import Sequence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _wheel_identity(path: Path) -> tuple[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(candidates) != 1:
                raise ValueError(f"Wheel must contain exactly one METADATA member: {path.name}")
            info = archive.getinfo(candidates[0])
            if info.file_size > 4 * 1024 * 1024:
                raise ValueError(f"Wheel METADATA exceeds 4 MiB: {path.name}")
            metadata = email.parser.BytesParser().parsebytes(archive.read(info))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Unreadable wheel: {path}") from exc
    name = str(metadata.get("Name", "")).strip()
    version = str(metadata.get("Version", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+!-]*", version):
        raise ValueError(f"Wheel has invalid package identity: {path.name}")
    return name, version


def build_runtime_lock(wheel_dir: str | Path, output: str | Path) -> list[tuple[str, str, str]]:
    root = Path(wheel_dir).resolve()
    if not root.is_dir():
        raise ValueError(f"Wheel directory does not exist: {root}")
    wheels = sorted(root.glob("*.whl"), key=lambda path: path.name.lower())
    if not wheels:
        raise ValueError("Wheel directory contains no wheels")
    records = [(*_wheel_identity(path), _sha256(path)) for path in wheels]
    records.sort(key=lambda item: (item[0].lower().replace("_", "-"), item[1]))
    normalized = [item[0].lower().replace("_", "-").replace(".", "-") for item in records]
    if len(normalized) != len(set(normalized)):
        raise ValueError("Wheel set contains duplicate package identities")
    lines = [
        "# Windows x64 CPython 3.12 runtime lock generated from reviewed wheel bytes.",
        "# Install offline with: python -m pip install --no-index --require-hashes -r requirements-runtime-windows-x64.txt",
    ]
    lines.extend(f"{name}=={version} --hash=sha256:{digest}" for name, version, digest in records)
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    records = build_runtime_lock(args.wheel_dir, args.output)
    print(f"Wrote {len(records)} hash-pinned wheels to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
