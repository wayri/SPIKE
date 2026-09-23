"""Build a deterministic Windows component inventory from checked lock inputs.

The inventory records machine-derived identities and declared license metadata.
It deliberately does not grant redistribution approval or claim notice coverage.
"""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import re
import subprocess
import tomllib
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote


CONTRACT = "spike/windows-component-inventory/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9][A-Za-z0-9._+!-]*)\s+--hash=sha256:([0-9a-f]{64})$"
)


class ComponentInventoryError(ValueError):
    """Raised when a lock or artifact cannot produce exact inventory evidence."""


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComponentInventoryError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ComponentInventoryError(f"{label} must be a JSON object")
    return value


def _normalize_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _license_from_metadata(metadata: Mapping[str, Any], evidence_digest: str) -> str:
    expression = str(metadata.get("License-Expression", "")).strip()
    if expression:
        return expression
    classifiers = metadata.get_all("Classifier", []) if hasattr(metadata, "get_all") else []
    licenses = sorted({
        str(item).split("License :: OSI Approved :: ", 1)[1].strip()
        for item in classifiers if "License :: OSI Approved :: " in str(item)
    })
    if len(licenses) == 1:
        return licenses[0]
    raw = str(metadata.get("License", "")).strip()
    if raw and len(raw) <= 160 and "\n" not in raw:
        return raw
    return f"LicenseRef-Metadata-{evidence_digest[:16]}"


def _wheel_metadata_records(path: Path) -> list[tuple[str, str, str, str, str]]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = sorted(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            top_level = [name for name in names if name.count("/") == 1]
            if len(top_level) != 1:
                raise ComponentInventoryError(f"Wheel has ambiguous top-level METADATA: {path.name}")
            selected = [top_level[0], *(name for name in names if name not in top_level)]
            raw_records = []
            for name in selected:
                info = archive.getinfo(name)
                if info.file_size > 4 * 1024 * 1024:
                    raise ComponentInventoryError(f"Wheel METADATA exceeds 4 MiB: {path.name}")
                raw_records.append((name, archive.read(info)))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ComponentInventoryError(f"Wheel is unreadable: {path}") from exc
    result = []
    for metadata_path, raw in raw_records:
        metadata = email.parser.BytesParser().parsebytes(raw)
        name = str(metadata.get("Name", "")).strip()
        version = str(metadata.get("Version", "")).strip()
        if not name or not version:
            raise ComponentInventoryError(f"Wheel lacks name/version metadata: {path.name}")
        evidence_digest = hashlib.sha256(raw).hexdigest()
        relationship = "top-level" if metadata_path.count("/") == 1 else "vendored"
        result.append((name, version, _license_from_metadata(metadata, evidence_digest), evidence_digest, relationship))
    return result


def _python_lock(path: Path, wheel_dirs: Sequence[Path], scope: str) -> list[dict[str, Any]]:
    wheels: dict[
        tuple[str, str],
        tuple[Path, str, str, list[tuple[str, str, str, str, str]]],
    ] = {}
    for directory in wheel_dirs:
        if not directory.is_dir():
            continue
        for wheel in sorted(directory.glob("*.whl")):
            metadata_records = _wheel_metadata_records(wheel)
            name, version, license_expression, metadata_digest, _ = metadata_records[0]
            key = (_normalize_python_name(name), version)
            candidate = (wheel, license_expression, metadata_digest, metadata_records[1:])
            previous = wheels.get(key)
            if previous and _digest(previous[0]) != _digest(wheel):
                raise ComponentInventoryError(f"Conflicting wheels for {name} {version}")
            wheels[key] = candidate
    records: list[dict[str, Any]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _REQUIREMENT.fullmatch(line)
        if match is None:
            raise ComponentInventoryError(f"{path.name}:{number} is not exact and hash-pinned")
        raw_name, version, digest = match.groups()
        name = _normalize_python_name(raw_name)
        wheel = wheels.get((name, version))
        if wheel is None or _digest(wheel[0]) != digest:
            raise ComponentInventoryError(f"No exact wheel bytes match {name}=={version}")
        records.append({
            "purl": f"pkg:pypi/{name}@{version}", "name": name, "version": version,
            "ecosystem": "python", "scope": scope,
            "integrity": {"algorithm": "sha256", "value": digest},
            "declared_license": wheel[1],
            "license_evidence": {"kind": "wheel-metadata", "sha256": wheel[2]},
        })
        for vendored_name, vendored_version, vendored_license, vendored_metadata_digest, _ in wheel[3]:
            vendored_normalized = _normalize_python_name(vendored_name)
            records.append({
                "purl": (
                    f"pkg:pypi/{vendored_normalized}@{vendored_version}"
                    f"?vendor={quote(name, safe='')}"
                ),
                "name": vendored_normalized, "version": vendored_version,
                "ecosystem": "python", "scope": scope,
                "integrity": {"algorithm": "sha256", "value": digest},
                "declared_license": vendored_license,
                "license_evidence": {
                    "kind": "vendored-wheel-metadata", "sha256": vendored_metadata_digest,
                    "parent_purl": f"pkg:pypi/{name}@{version}",
                },
            })
    return records


def _npm_components(path: Path) -> list[dict[str, Any]]:
    lock = _read_json(path, "npm package lock")
    packages = lock.get("packages")
    if lock.get("lockfileVersion") != 3 or not isinstance(packages, Mapping):
        raise ComponentInventoryError("npm package lock must use lockfileVersion 3")
    records = []
    for package_path, item in packages.items():
        if not package_path or not isinstance(item, Mapping):
            continue
        name = str(package_path).rsplit("node_modules/", 1)[-1]
        version = str(item.get("version", ""))
        integrity = str(item.get("integrity", ""))
        license_expression = str(item.get("license", "")).strip()
        if not version or not integrity.startswith("sha512-") or not license_expression:
            raise ComponentInventoryError(f"npm component {name!r} lacks exact integrity/license evidence")
        if name.startswith("@") and "/" in name:
            scope_name, package = name.split("/", 1)
            purl_name = f"{quote(scope_name, safe='')}/{quote(package, safe='')}"
        else:
            purl_name = quote(name, safe="")
        records.append({
            "purl": f"pkg:npm/{purl_name}@{version}", "name": name, "version": version,
            "ecosystem": "npm", "scope": "build-only" if item.get("dev") is True else "bundled",
            "integrity": {"algorithm": "sha512-sri", "value": integrity},
            "declared_license": license_expression,
            "license_evidence": {"kind": "package-lock", "sha256": _digest(path)},
        })
    return records


def _cargo_metadata(manifest_path: Path) -> dict[str, Any]:
    process = subprocess.run(
        ["cargo", "metadata", "--locked", "--offline", "--format-version", "1",
         "--filter-platform", "x86_64-pc-windows-msvc", "--manifest-path", str(manifest_path)],
        cwd=manifest_path.parents[2], text=True, encoding="utf-8", errors="strict",
        capture_output=True, check=False, timeout=120,
    )
    if process.returncode != 0:
        raise ComponentInventoryError(f"Locked offline Cargo metadata failed: {process.stderr.strip()}")
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ComponentInventoryError("Cargo metadata returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ComponentInventoryError("Cargo metadata returned a non-object")
    return value


def _cargo_components(cargo_lock_path: Path, manifest_path: Path) -> list[dict[str, Any]]:
    lock = tomllib.loads(cargo_lock_path.read_text(encoding="utf-8"))
    checksums = {
        (str(item.get("name", "")), str(item.get("version", ""))): str(item.get("checksum", ""))
        for item in lock.get("package", []) if isinstance(item, Mapping) and item.get("source")
    }
    metadata = _cargo_metadata(manifest_path)
    packages = {str(item.get("id", "")): item for item in metadata.get("packages", []) if isinstance(item, Mapping)}
    resolve = metadata.get("resolve") if isinstance(metadata.get("resolve"), Mapping) else {}
    root_id = str(resolve.get("root", ""))
    nodes = {str(item.get("id", "")): item for item in resolve.get("nodes", []) if isinstance(item, Mapping)}
    scopes: dict[str, str] = {root_id: "bundled"}
    queue = [root_id]
    while queue:
        current = queue.pop(0)
        current_scope = scopes[current]
        node = nodes.get(current, {})
        for dependency in node.get("deps", []) if isinstance(node.get("deps"), list) else []:
            target = str(dependency.get("pkg", ""))
            kinds = dependency.get("dep_kinds") if isinstance(dependency, Mapping) else []
            edge_scope = "build-only" if kinds and all(item.get("kind") == "build" for item in kinds) else current_scope
            desired = "bundled" if current_scope == "bundled" and edge_scope != "build-only" else "build-only"
            if scopes.get(target) != "bundled" and scopes.get(target) != desired:
                scopes[target] = desired
                queue.append(target)
    records = []
    for package_id, item in packages.items():
        if not item.get("source"):
            continue
        name, version = str(item.get("name", "")), str(item.get("version", ""))
        checksum = checksums.get((name, version), "")
        license_expression = str(item.get("license", "")).strip()
        if not _SHA256.fullmatch(checksum) or not license_expression:
            raise ComponentInventoryError(f"Cargo component {name} {version} lacks checksum/license evidence")
        records.append({
            "purl": f"pkg:cargo/{quote(name, safe='')}@{version}", "name": name,
            "version": version, "ecosystem": "rust", "scope": scopes.get(package_id, "build-only"),
            "integrity": {"algorithm": "cargo-sha256", "value": checksum},
            "declared_license": license_expression,
            "license_evidence": {"kind": "cargo-metadata-locked", "sha256": checksum},
        })
    return records


def _merge_components(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in records:
        item = dict(raw)
        purl = str(item.get("purl", ""))
        if not purl:
            raise ComponentInventoryError("Component purl is missing")
        existing = merged.get(purl)
        if existing is None:
            merged[purl] = item
            continue
        comparable = {key: value for key, value in item.items() if key != "scope"}
        previous = {key: value for key, value in existing.items() if key != "scope"}
        if comparable != previous:
            raise ComponentInventoryError(f"Conflicting component evidence for {purl}")
        if item["scope"] == "bundled":
            existing["scope"] = "bundled"
    output = []
    for purl in sorted(merged):
        item = merged[purl]
        identity = {key: item[key] for key in sorted(item)}
        item["identity_sha256"] = _canonical_digest(identity)
        output.append(item)
    return output


def build_component_inventory(
    package_lock_path: str | Path, cargo_lock_path: str | Path, cargo_manifest_path: str | Path,
    build_requirements_path: str | Path, runtime_requirements_path: str | Path,
    build_wheel_dir: str | Path, runtime_wheel_dir: str | Path, output_path: str | Path,
) -> dict[str, Any]:
    package_lock = Path(package_lock_path).resolve()
    cargo_lock = Path(cargo_lock_path).resolve()
    cargo_manifest = Path(cargo_manifest_path).resolve()
    build_lock = Path(build_requirements_path).resolve()
    runtime_lock = Path(runtime_requirements_path).resolve()
    records = []
    records.extend(_npm_components(package_lock))
    records.extend(_cargo_components(cargo_lock, cargo_manifest))
    records.extend(_python_lock(build_lock, [Path(build_wheel_dir), Path(runtime_wheel_dir)], "build-only"))
    records.extend(_python_lock(runtime_lock, [Path(runtime_wheel_dir), Path(build_wheel_dir)], "bundled"))
    document = {
        "contract": CONTRACT, "platform": "windows-x64", "production_qualified": False,
        "sources": [
            {"id": "cargo_lock", "sha256": _digest(cargo_lock)},
            {"id": "npm_package_lock", "sha256": _digest(package_lock)},
            {"id": "python_build_lock", "sha256": _digest(build_lock)},
            {"id": "python_runtime_lock", "sha256": _digest(runtime_lock)},
        ],
        "components": _merge_components(records),
    }
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-lock", required=True, type=Path)
    parser.add_argument("--cargo-lock", required=True, type=Path)
    parser.add_argument("--cargo-manifest", required=True, type=Path)
    parser.add_argument("--build-requirements", required=True, type=Path)
    parser.add_argument("--runtime-requirements", required=True, type=Path)
    parser.add_argument("--build-wheel-dir", required=True, type=Path)
    parser.add_argument("--runtime-wheel-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_component_inventory(
            args.package_lock, args.cargo_lock, args.cargo_manifest, args.build_requirements,
            args.runtime_requirements, args.build_wheel_dir, args.runtime_wheel_dir, args.output,
        )
    except ComponentInventoryError as exc:
        raise SystemExit(f"Windows component inventory rejected: {exc}") from exc
    print(f"Wrote {len(result['components'])} locked components to {args.output.resolve()}")
    print("Redistribution approval and notice coverage remain separate required gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
