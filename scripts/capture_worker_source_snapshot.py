# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Retain exactly matching inspected Python/schema inputs, not a release archive.

Later working-tree edits must not erase the baseline a frozen candidate passed.
Native sources, dependencies and uninspected assets are outside this snapshot.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyInstaller.archive.readers import CArchiveReader
from scripts.verify_packaged_source_modules import EM_COSIM_MODULES, normalized

MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024


def _read_source(path, remaining):
    limit = min(MAX_FILE_BYTES, remaining)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Inspected source file or aggregate exceeds snapshot budget")
    return data


def capture(executable, destination, *, source_root=ROOT):
    root = Path(source_root).resolve(strict=True)
    executable = Path(executable).resolve(strict=True)
    destination = Path(destination).resolve()
    build_root = (root / "build").resolve()
    if (not build_root.is_relative_to(root) or destination == build_root
            or not destination.is_relative_to(build_root) or destination.exists()):
        raise ValueError("Snapshot destination must be fresh and strictly below source build/")
    identity = sha256(executable.read_bytes()).hexdigest()
    archive = CArchiveReader(str(executable)).open_embedded_archive("PYZ.pyz")
    payload = {}
    modules = set()
    total = 0
    if len(archive.toc) > 16384:
        raise ValueError("Frozen module catalog exceeds snapshot budget")
    for name in sorted(archive.toc):
        if name != "python" and not name.startswith("python.") and name not in EM_COSIM_MODULES:
            continue
        if any(not part.isidentifier() for part in name.split(".")):
            raise ValueError("Invalid frozen source module name")
        source = root.joinpath(*name.split(".")).with_suffix(".py")
        if not source.is_file():
            source = root.joinpath(*name.split(".")) / "__init__.py"
        resolved = source.resolve(strict=True)
        if source.is_symlink() or not resolved.is_relative_to(root):
            raise ValueError("Source escapes the snapshot root")
        data = _read_source(source, MAX_SOURCE_BYTES - total)
        if normalized(compile(data, str(source), "exec", optimize=0)) != normalized(archive.extract(name)):
            raise ValueError("Frozen/source mismatch prevents snapshot: " + name)
        payload[source.relative_to(root).as_posix()] = data
        total += len(data)
        modules.add(name)
    if not modules or EM_COSIM_MODULES - modules:
        raise ValueError("Required inspected source modules are absent")
    schema_root = root / "schemas"
    packaged_root = executable.parent / "_internal" / "schemas"
    source_names = {p.relative_to(schema_root).as_posix() for p in schema_root.rglob("*.json")}
    actual_names = {p.relative_to(packaged_root).as_posix() for p in packaged_root.rglob("*.json")}
    if "manifest.json" not in source_names or source_names != actual_names:
        raise ValueError("Schema catalog differs")
    for name in sorted(source_names):
        source = schema_root / name
        if source.is_symlink() or not source.resolve().is_relative_to(schema_root.resolve()):
            raise ValueError("Schema escapes its root")
        data = _read_source(source, MAX_SOURCE_BYTES - total)
        if data != (packaged_root / name).read_bytes():
            raise ValueError("Schema bytes differ: " + name)
        payload["schemas/" + name] = data
        total += len(data)
    if sum(map(len, payload.values())) > MAX_SOURCE_BYTES:
        raise ValueError("Inspected source snapshot exceeds 128 MiB")
    if sha256(executable.read_bytes()).hexdigest() != identity:
        raise ValueError("Worker changed during snapshot capture")
    # The executable hash does not bind mutable adjacent schema files.
    final_names = {p.relative_to(packaged_root).as_posix() for p in packaged_root.rglob("*.json")}
    if final_names != actual_names or any(
            (packaged_root / name).read_bytes() != payload["schemas/" + name]
            for name in sorted(actual_names)):
        raise ValueError("Packaged schemas changed during snapshot capture")
    # Validate everything before publishing; never reread a moving source to copy it.
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in payload.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    report = {"contract": "spike/worker-source-snapshot/v1", "status": "passed",
              "executable_sha256": identity, "checked_modules": len(modules),
              "schema_json_files": len(source_names),
              "scope": "Inspected Python code and schemas only; not a complete release-source archive or native-source equivalence",
              "files": [{"path": name, "sha256": sha256(data).hexdigest(), "bytes": len(data)}
                        for name, data in sorted(payload.items())]}
    with (destination / "SOURCE_SNAPSHOT.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    report = capture(args.executable, args.destination)
    print(json.dumps({key: report[key] for key in ("status", "executable_sha256", "checked_modules", "schema_json_files")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
