"""Collect bounded, non-decisional notice candidates for a Windows inventory.

This is an evidence collector, not a notice generator or approval gate.  It
only joins artifacts to an inventory by the complete PURL and identity digest.
"""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote


CONTRACT = "spike/windows-notice-evidence-index/v1"
INVENTORY_CONTRACT = "spike/windows-component-inventory/v1"
MAX_BYTES = 4 * 1024 * 1024
_CANDIDATE = re.compile(r"^(?:LICENSE|NOTICE|COPYING|COPYRIGHT).*$", re.IGNORECASE)
_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:([0-9a-f]{64})$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class NoticeEvidenceError(ValueError):
    """Raised for any ambiguous, stale, unsafe, or unbounded evidence input."""


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            hasher.update(block)
    return hasher.hexdigest()


def _canonical_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    # Zip names are POSIX paths.  Backslashes are rejected rather than treated
    # as separators so a Windows extraction cannot reinterpret an entry.
    candidate = PurePosixPath(value)
    if not value or "\\" in value or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise NoticeEvidenceError(f"unsafe archive member path: {value!r}")
    return candidate


def _safe_disk_path(root: Path, candidate: Path) -> Path:
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise NoticeEvidenceError(f"path escapes supplied root: {candidate}") from exc
    if candidate.is_symlink():
        raise NoticeEvidenceError(f"symlink evidence path is not accepted: {candidate}")
    return resolved


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NoticeEvidenceError(f"{label} is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise NoticeEvidenceError(f"{label} must be a JSON object")
    return value


def _normalize_python_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _purl_from_npm_path(package_path: str, version: str) -> str:
    name = package_path.rsplit("node_modules/", 1)[-1]
    if name.startswith("@") and "/" in name:
        scope, package = name.split("/", 1)
        name = f"{quote(scope, safe='')}/{quote(package, safe='')}"
    else:
        name = quote(name, safe="")
    return f"pkg:npm/{name}@{version}"


def _identity(record: Mapping[str, Any]) -> str:
    body = {key: record[key] for key in sorted(record) if key != "identity_sha256"}
    return _canonical_digest(body)


def _inventory(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    document = _read_json(path, "inventory")
    if document.get("contract") != INVENTORY_CONTRACT or document.get("platform") != "windows-x64":
        raise NoticeEvidenceError("unsupported inventory contract or platform")
    components = document.get("components")
    if not isinstance(components, list):
        raise NoticeEvidenceError("inventory lacks a component list")
    result: dict[str, dict[str, Any]] = {}
    for item in components:
        if not isinstance(item, dict) or not isinstance(item.get("purl"), str) or not isinstance(item.get("identity_sha256"), str):
            raise NoticeEvidenceError("inventory contains malformed component")
        purl = item["purl"]
        if purl in result or item["identity_sha256"] != _identity(item):
            raise NoticeEvidenceError(f"inventory has duplicate or stale identity: {purl}")
        result[purl] = item
    return document, result


def _validate_sources(inventory: Mapping[str, Any], paths: Mapping[str, Path]) -> None:
    expected = {key: _digest(value) for key, value in paths.items()}
    sources = inventory.get("sources")
    if not isinstance(sources, list):
        raise NoticeEvidenceError("inventory lacks source hashes")
    actual = {item.get("id"): item.get("sha256") for item in sources if isinstance(item, Mapping)}
    if actual != expected or len(sources) != 4:
        raise NoticeEvidenceError("inventory source hashes are stale or not the exact four locked inputs")


def _require_join(component: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    # The complete reconstructed record is checked, including the calculated
    # identity.  A matching package name alone is deliberately never useful.
    purl = expected["purl"]
    if component.get("purl") != purl or component.get("identity_sha256") != _identity(expected):
        raise NoticeEvidenceError(f"inventory PURL+identity join failed: {purl}")


def _parse_npm(lock_path: Path, components: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, str]]:
    lock = _read_json(lock_path, "npm package lock")
    packages = lock.get("packages")
    if lock.get("lockfileVersion") != 3 or not isinstance(packages, Mapping):
        raise NoticeEvidenceError("npm package lock must use lockfileVersion 3")
    paths: list[tuple[str, str]] = []
    seen: set[str] = set()
    for package_path, item in sorted(packages.items()):
        if not package_path:
            continue
        if not isinstance(package_path, str) or not isinstance(item, Mapping):
            raise NoticeEvidenceError("npm package lock contains malformed package")
        version, integrity, license_expression = str(item.get("version", "")), str(item.get("integrity", "")), str(item.get("license", "")).strip()
        if not version or not integrity.startswith("sha512-") or not license_expression:
            raise NoticeEvidenceError(f"npm lock lacks locked identity data: {package_path}")
        purl = _purl_from_npm_path(package_path, version)
        expected = {"purl": purl, "name": package_path.rsplit("node_modules/", 1)[-1], "version": version,
                    "ecosystem": "npm", "scope": "build-only" if item.get("dev") is True else "bundled",
                    "integrity": {"algorithm": "sha512-sri", "value": integrity}, "declared_license": license_expression,
                    "license_evidence": {"kind": "package-lock", "sha256": _digest(lock_path)}}
        component = components.get(purl)
        if component is None:
            raise NoticeEvidenceError(f"npm locked PURL is absent from inventory: {purl}")
        _require_join(component, expected)
        if purl in seen:
            raise NoticeEvidenceError(f"npm PURL collision in lock: {purl}")
        seen.add(purl)
        paths.append((purl, package_path))
    inventory_purls = {purl for purl, value in components.items() if value.get("ecosystem") == "npm"}
    if seen != inventory_purls:
        raise NoticeEvidenceError("npm inventory coverage is not an exact PURL+identity join")
    return paths


def _parse_requirements(path: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _REQUIREMENT.fullmatch(line)
        if match is None:
            raise NoticeEvidenceError(f"{path.name}:{number} is not exactly SHA-256 pinned")
        name, version, digest = match.groups()
        purl = f"pkg:pypi/{_normalize_python_name(name)}@{version}"
        if purl in result:
            raise NoticeEvidenceError(f"duplicate Python PURL in locks: {purl}")
        result[purl] = (version, digest)
    return result


def _wheel_metadata(wheel: Path) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            infos = sorted(archive.infolist(), key=lambda item: item.filename)
            for info in infos:
                _safe_relative(info.filename)
            metadata = [item for item in infos if item.filename.endswith(".dist-info/METADATA") and len(PurePosixPath(item.filename).parts) == 2]
            if len(metadata) != 1:
                raise NoticeEvidenceError(f"wheel must contain exactly one top-level METADATA: {wheel.name}")
            selected = metadata[0]
            if selected.file_size > MAX_BYTES:
                raise NoticeEvidenceError(f"wheel METADATA exceeds 4 MiB: {wheel.name}")
            raw = archive.read(selected)
            parsed = email.parser.BytesParser().parsebytes(raw)
            name, version = str(parsed.get("Name", "")).strip(), str(parsed.get("Version", "")).strip()
            if not name or not version:
                raise NoticeEvidenceError(f"wheel metadata lacks name/version: {wheel.name}")
            vendored: list[tuple[str, bytes]] = []
            for info in infos:
                if info is selected or not info.filename.endswith(".dist-info/METADATA"):
                    continue
                if info.file_size > MAX_BYTES:
                    raise NoticeEvidenceError(f"wheel vendored METADATA exceeds 4 MiB: {wheel.name}")
                vendored.append((info.filename, archive.read(info)))
            candidate_infos = [
                item for item in infos
                if not item.is_dir() and _CANDIDATE.fullmatch(PurePosixPath(item.filename).name)
            ]
            oversized = next((item for item in candidate_infos if item.file_size > MAX_BYTES), None)
            if oversized is not None:
                raise NoticeEvidenceError(
                    f"wheel candidate exceeds 4 MiB: {wheel.name}:{oversized.filename}"
                )
            return {
                "name": name, "version": version, "metadata": raw,
                "metadata_path": selected.filename, "vendored": vendored,
            }, [(item.filename, archive.read(item)) for item in candidate_infos]
    except (OSError, zipfile.BadZipFile) as exc:
        raise NoticeEvidenceError(f"unreadable wheel: {wheel}") from exc


def _metadata_license(raw: bytes) -> str:
    """Mirror the locked-inventory metadata fallback without interpreting it."""
    metadata = email.parser.BytesParser().parsebytes(raw)
    expression = str(metadata.get("License-Expression", "")).strip()
    if expression:
        return expression
    classifiers = metadata.get_all("Classifier", [])
    licenses = sorted({str(item).split("License :: OSI Approved :: ", 1)[1].strip()
                       for item in classifiers if "License :: OSI Approved :: " in str(item)})
    if len(licenses) == 1:
        return licenses[0]
    value = str(metadata.get("License", "")).strip()
    if value and len(value) <= 160 and "\n" not in value:
        return value
    return f"LicenseRef-Metadata-{hashlib.sha256(raw).hexdigest()[:16]}"


def _source_locator(root_id: str, root: Path, artifact: Path) -> str:
    """Return a deterministic artifact locator rooted in an explicit input."""
    relative = _safe_disk_path(root, artifact).relative_to(root.resolve()).as_posix()
    if not relative:
        raise NoticeEvidenceError(f"source artifact must be below its supplied root: {artifact}")
    return f"{root_id}/{relative}"


def _candidate_records_from_archive(source_locator: str, entries: Iterable[tuple[str, bytes]], source_kind: str) -> list[tuple[str, str, bytes, str]]:
    output = []
    for relative, content in entries:
        _safe_relative(relative)
        if len(content) > MAX_BYTES:
            raise NoticeEvidenceError(f"candidate exceeds 4 MiB: {source_locator}:{relative}")
        output.append((source_locator, relative, content, source_kind))
    return output


def _wheel_candidates(entries: Iterable[tuple[str, bytes]], dist_info: PurePosixPath, *, include_wheel_root: bool) -> list[tuple[str, bytes]]:
    """Select only candidates demonstrably belonging to one wheel component."""
    selected: list[tuple[str, bytes]] = []
    for relative, content in entries:
        candidate = _safe_relative(relative)
        in_dist_info = candidate.parts[:len(dist_info.parts)] == dist_info.parts
        at_wheel_root = len(candidate.parts) == 1
        if in_dist_info or (include_wheel_root and at_wheel_root):
            selected.append((relative, content))
    return selected


def _python_candidates(build_lock: Path, runtime_lock: Path, wheel_dirs: Sequence[tuple[str, Path]], components: Mapping[str, Mapping[str, Any]]) -> dict[str, list[tuple[str, str, bytes, str]]]:
    build_requirements, runtime_requirements = _parse_requirements(build_lock), _parse_requirements(runtime_lock)
    locks = {**build_requirements, **runtime_requirements}
    all_wheels: dict[str, list[tuple[Path, str, dict[str, Any], list[tuple[str, bytes]]]]] = {}
    for root_id, directory in wheel_dirs:
        if not directory.is_dir():
            raise NoticeEvidenceError(f"wheel directory is missing: {directory}")
        for wheel in sorted(directory.glob("*.whl")):
            _safe_disk_path(directory, wheel)
            metadata, candidates = _wheel_metadata(wheel)
            purl = f"pkg:pypi/{_normalize_python_name(metadata['name'])}@{metadata['version']}"
            all_wheels.setdefault(purl, []).append((wheel, _source_locator(root_id, directory, wheel), metadata, candidates))
    result: dict[str, list[tuple[str, str, bytes, str]]] = {}
    expected_purls: set[str] = set()
    for purl, (version, wanted_digest) in sorted(locks.items()):
        expected_purls.add(purl)
        matching = all_wheels.get(purl, [])
        if not matching:
            raise NoticeEvidenceError(f"no wheel presents locked PURL: {purl}")
        digests = {_digest(item[0]) for item in matching}
        if len(digests) != 1:
            raise NoticeEvidenceError(f"non-identical duplicate wheels for {purl}")
        if digests != {wanted_digest}:
            raise NoticeEvidenceError(f"wheel SHA-256 does not equal lock for {purl}")
        wheel, source_locator, metadata, candidates = matching[0]
        component = components.get(purl)
        if component is None:
            raise NoticeEvidenceError(f"locked wheel PURL missing from inventory: {purl}")
        evidence = component.get("license_evidence", {})
        if not isinstance(evidence, Mapping) or evidence.get("kind") != "wheel-metadata" or evidence.get("sha256") != hashlib.sha256(metadata["metadata"]).hexdigest():
            raise NoticeEvidenceError(f"top-level wheel metadata join failed: {purl}")
        if component.get("integrity", {}).get("value") != wanted_digest:
            raise NoticeEvidenceError(f"wheel integrity join failed: {purl}")
        expected = {"purl": purl, "name": _normalize_python_name(metadata["name"]), "version": version,
                    "ecosystem": "python", "scope": "bundled" if purl in runtime_requirements else "build-only",
                    "integrity": {"algorithm": "sha256", "value": wanted_digest},
                    "declared_license": _metadata_license(metadata["metadata"]),
                    "license_evidence": {"kind": "wheel-metadata", "sha256": hashlib.sha256(metadata["metadata"]).hexdigest()}}
        _require_join(component, expected)
        # The selected METADATA is the sole authoritative top-level dist-info
        # subtree.  Wheel-root license files are also attributable to it.
        top_dist_info = _safe_relative(metadata["metadata_path"]).parent
        result[purl] = _candidate_records_from_archive(
            source_locator, _wheel_candidates(candidates, top_dist_info, include_wheel_root=True), "python-wheel")
        for metadata_path, raw in metadata["vendored"]:
            parsed = email.parser.BytesParser().parsebytes(raw)
            name, child_version = str(parsed.get("Name", "")).strip(), str(parsed.get("Version", "")).strip()
            if not name or not child_version:
                raise NoticeEvidenceError(f"vendored wheel metadata lacks name/version: {wheel.name}")
            child = f"pkg:pypi/{_normalize_python_name(name)}@{child_version}?vendor={quote(_normalize_python_name(metadata['name']), safe='')}"
            child_component = components.get(child)
            if child_component is None:
                raise NoticeEvidenceError(f"vendored wheel PURL missing from inventory: {child}")
            child_evidence = child_component.get("license_evidence", {})
            if not isinstance(child_evidence, Mapping) or child_evidence.get("kind") != "vendored-wheel-metadata" or child_evidence.get("parent_purl") != purl or child_evidence.get("sha256") != hashlib.sha256(raw).hexdigest():
                raise NoticeEvidenceError(f"vendored metadata PURL+identity join failed: {child}")
            child_expected = {"purl": child, "name": _normalize_python_name(name), "version": child_version,
                              "ecosystem": "python", "scope": "bundled" if purl in runtime_requirements else "build-only",
                              "integrity": {"algorithm": "sha256", "value": wanted_digest},
                              "declared_license": _metadata_license(raw),
                              "license_evidence": {"kind": "vendored-wheel-metadata", "sha256": hashlib.sha256(raw).hexdigest(), "parent_purl": purl}}
            _require_join(child_component, child_expected)
            child_dist_info = _safe_relative(metadata_path).parent
            result[child] = _candidate_records_from_archive(
                source_locator, _wheel_candidates(candidates, child_dist_info, include_wheel_root=False), "python-wheel")
            expected_purls.add(child)
    inventory_purls = {purl for purl, value in components.items() if value.get("ecosystem") == "python"}
    if expected_purls != inventory_purls:
        raise NoticeEvidenceError("Python inventory coverage is not an exact PURL+identity join")
    return result


def _cargo_candidates(cargo_lock: Path, cargo_manifest: Path, cargo_cache: Path, components: Mapping[str, Mapping[str, Any]]) -> dict[str, list[tuple[str, str, bytes, str]]]:
    try:
        lock = tomllib.loads(cargo_lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise NoticeEvidenceError(f"Cargo.lock is unreadable: {cargo_lock}") from exc
    if not cargo_manifest.is_file():
        raise NoticeEvidenceError(f"Cargo.toml is missing: {cargo_manifest}")
    if not cargo_cache.is_dir():
        raise NoticeEvidenceError(f"explicit Cargo cache directory is missing: {cargo_cache}")
    # Cargo.lock is authoritative for crate bytes, while locked Cargo metadata
    # supplies the license and platform scope that are part of identity.
    if any(value.get("ecosystem") == "rust" for value in components.values()):
        try:  # Module form for tests; script form for ``python scripts/...``.
            from scripts.build_windows_component_inventory import _cargo_components, _merge_components
        except ModuleNotFoundError:
            from build_windows_component_inventory import _cargo_components, _merge_components
        expected_components = {item["purl"]: item for item in _merge_components(_cargo_components(cargo_lock, cargo_manifest))}
        actual_components = {purl: value for purl, value in components.items() if value.get("ecosystem") == "rust"}
        if set(expected_components) != set(actual_components):
            raise NoticeEvidenceError("Cargo inventory PURL coverage is stale")
        for purl, expected in expected_components.items():
            _require_join(actual_components[purl], expected)
    by_filename: dict[str, list[Path]] = {}
    for artifact in cargo_cache.rglob("*.crate"):
        checked = _safe_disk_path(cargo_cache, artifact)
        by_filename.setdefault(checked.name, []).append(checked)
    result: dict[str, list[tuple[str, str, bytes, str]]] = {}
    seen: set[str] = set()
    for item in lock.get("package", []):
        if not isinstance(item, Mapping) or not item.get("source"):
            continue
        name, version, checksum = str(item.get("name", "")), str(item.get("version", "")), str(item.get("checksum", ""))
        purl = f"pkg:cargo/{quote(name, safe='')}@{version}"
        # Cargo.lock can hold packages for other target platforms.  The
        # inventory's locked Windows metadata is the exact scope boundary.
        if purl not in components or components[purl].get("ecosystem") != "rust":
            continue
        if not _SHA256.fullmatch(checksum):
            raise NoticeEvidenceError(f"Cargo package lacks checksum: {name} {version}")
        component = components.get(purl)
        if component is None or component.get("integrity", {}).get("algorithm") != "cargo-sha256" or component.get("integrity", {}).get("value") != checksum:
            raise NoticeEvidenceError(f"Cargo PURL+checksum join failed: {purl}")
        seen.add(purl)
        # Comparing the complete lock name and version to the complete archive
        # filename avoids parsing ambiguity in hyphenated crate names or
        # prerelease/build versions.
        candidates = by_filename.get(f"{name}-{version}.crate", [])
        # A same-name/version stale archive is an ambiguity, even if another
        # cache entry happens to match the checksum.
        if candidates and any(_digest(candidate) != checksum for candidate in candidates):
            raise NoticeEvidenceError(f"Cargo cache collision for {purl}")
        exact = [candidate for candidate in candidates if _digest(candidate) == checksum]
        if not exact:
            result[purl] = []
            continue
        archive = sorted(exact)[0]
        try:
            with tarfile.open(archive, "r:gz") as package:
                infos = sorted(package.getmembers(), key=lambda item: item.name)
                for info in infos:
                    _safe_relative(info.name)
                    if info.issym() or info.islnk() or info.isdev():
                        raise NoticeEvidenceError(f"unsafe crate archive member type: {archive.name}:{info.name}")
                root = PurePosixPath(infos[0].name).parts[0] if infos else ""
                entries = []
                for info in infos:
                    parts = PurePosixPath(info.name).parts
                    if info.isfile() and len(parts) == 2 and parts[0] == root and _CANDIDATE.fullmatch(parts[1]):
                        if info.size > MAX_BYTES:
                            raise NoticeEvidenceError(f"crate candidate exceeds 4 MiB: {archive.name}:{info.name}")
                        stream = package.extractfile(info)
                        if stream is None:
                            raise NoticeEvidenceError(f"crate candidate is unreadable: {archive.name}:{info.name}")
                        entries.append((info.name, stream.read()))
        except (OSError, tarfile.TarError) as exc:
            raise NoticeEvidenceError(f"unreadable crate archive: {archive}") from exc
        result[purl] = _candidate_records_from_archive(
            _source_locator("cargo-cache", cargo_cache, archive), entries, "cargo-crate")
    inventory_purls = {purl for purl, value in components.items() if value.get("ecosystem") == "rust"}
    if seen != inventory_purls:
        raise NoticeEvidenceError("Cargo inventory coverage is not an exact PURL+identity join")
    return result


def _npm_candidates(lock_entries: Sequence[tuple[str, str]], npm_root: Path, components: Mapping[str, Mapping[str, Any]]) -> dict[str, list[tuple[str, str, bytes, str]]]:
    if not npm_root.is_dir():
        raise NoticeEvidenceError(f"npm root is missing: {npm_root}")
    result: dict[str, list[tuple[str, str, bytes, str]]] = {}
    for purl, package_path in lock_entries:
        directory = npm_root.parent / package_path if package_path.startswith("node_modules/") else npm_root
        # npm root is app/node_modules; the package-lock paths are rooted at app.
        directory = _safe_disk_path(npm_root.parent, directory)
        manifest = directory / "package.json"
        if not manifest.is_file():
            result[purl] = []
            continue
        package = _read_json(manifest, "installed npm package.json")
        expected = components[purl]
        if package.get("name") != expected.get("name") or str(package.get("version", "")) != expected.get("version"):
            raise NoticeEvidenceError(f"installed npm package does not match locked PURL: {purl}")
        source_locator = _source_locator("npm-root", npm_root, directory)
        entries: list[tuple[str, str, bytes, str]] = []
        for file in sorted(directory.rglob("*")):
            if not file.is_file() or not _CANDIDATE.fullmatch(file.name):
                continue
            checked = _safe_disk_path(directory, file)
            # Nested node_modules packages are separate lock entries and must
            # never be attributed to their containing package.
            if "node_modules" in checked.relative_to(directory).parts:
                continue
            size = checked.stat().st_size
            if size > MAX_BYTES:
                raise NoticeEvidenceError(f"installed npm candidate exceeds 4 MiB: {purl}:{checked.name}")
            entries.append((source_locator, checked.relative_to(directory).as_posix(), checked.read_bytes(), "npm-installed-tree-candidate-non-authoritative"))
        result[purl] = entries
    return result


def _copy_candidate(evidence_dir: Path, source_locator: str, relative: str, content: bytes, source_kind: str) -> dict[str, Any]:
    digest = hashlib.sha256(content).hexdigest()
    target = evidence_dir / digest
    if target.exists() and (not target.is_file() or _digest(target) != digest):
        raise NoticeEvidenceError(f"evidence content collision: {target}")
    if not target.exists():
        target.write_bytes(content)
    return {"source_locator": source_locator, "relative_path": relative, "sha256": digest, "size": len(content),
            "source_kind": source_kind, "evidence_path": f"windows-notice-evidence/{digest}"}


def collect_notice_evidence(inventory: str | Path, package_lock: str | Path, npm_root: str | Path,
                            cargo_lock: str | Path, cargo_manifest: str | Path, cargo_cache: str | Path,
                            build_requirements: str | Path, runtime_requirements: str | Path,
                            build_wheel_dir: str | Path, runtime_wheel_dir: str | Path,
                            output: str | Path, evidence_dir: str | Path) -> dict[str, Any]:
    inventory_file, package_lock, cargo_lock = Path(inventory).resolve(), Path(package_lock).resolve(), Path(cargo_lock).resolve()
    cargo_manifest, cargo_cache_path = Path(cargo_manifest).resolve(), Path(cargo_cache).resolve()
    build_lock, runtime_lock = Path(build_requirements).resolve(), Path(runtime_requirements).resolve()
    document, components = _inventory(inventory_file)
    _validate_sources(document, {"cargo_lock": cargo_lock, "npm_package_lock": package_lock,
                                 "python_build_lock": build_lock, "python_runtime_lock": runtime_lock})
    npm_entries = _parse_npm(package_lock, components)
    python = _python_candidates(build_lock, runtime_lock, [("build-wheel-dir", Path(build_wheel_dir).resolve()), ("runtime-wheel-dir", Path(runtime_wheel_dir).resolve())], components)
    cargo = _cargo_candidates(cargo_lock, cargo_manifest, cargo_cache_path, components)
    npm = _npm_candidates(npm_entries, Path(npm_root).resolve(), components)
    evidence_root = Path(evidence_dir).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    found = {**python, **cargo, **npm}
    entries = []
    for purl in sorted(components):
        records = sorted((_copy_candidate(evidence_root, *candidate) for candidate in found.get(purl, [])), key=lambda item: (item["sha256"], item["source_locator"], item["relative_path"]))
        item = components[purl]
        entries.append({"purl": purl, "identity_sha256": item["identity_sha256"], "ecosystem": item["ecosystem"], "scope": item["scope"],
                        "candidates": records, "missing": not records})
    summary: dict[str, Any] = {"components": len(entries), "candidates": sum(len(item["candidates"]) for item in entries), "missing_components": sum(item["missing"] for item in entries), "by_ecosystem_scope": {}}
    for ecosystem in ("npm", "python", "rust"):
        for scope in ("bundled", "build-only"):
            matching = [item for item in entries if item["ecosystem"] == ecosystem and item["scope"] == scope]
            summary["by_ecosystem_scope"][f"{ecosystem}/{scope}"] = {"components": len(matching), "candidates": sum(len(item["candidates"]) for item in matching), "missing_components": sum(item["missing"] for item in matching)}
    result = {"contract": CONTRACT, "platform": "windows-x64", "production_qualified": False, "inventory_sha256": _digest(inventory_file),
              "components": entries, "summary": summary}
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path); parser.add_argument("--package-lock", required=True, type=Path)
    parser.add_argument("--npm-root", required=True, type=Path); parser.add_argument("--cargo-lock", required=True, type=Path)
    parser.add_argument("--cargo-manifest", required=True, type=Path); parser.add_argument("--cargo-cache", required=True, type=Path)
    parser.add_argument("--build-requirements", required=True, type=Path); parser.add_argument("--runtime-requirements", required=True, type=Path)
    parser.add_argument("--build-wheel-dir", required=True, type=Path); parser.add_argument("--runtime-wheel-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path); parser.add_argument("--evidence-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = collect_notice_evidence(**vars(args))
    except NoticeEvidenceError as exc:
        raise SystemExit(f"Windows notice evidence rejected: {exc}") from exc
    print(json.dumps(result["summary"], sort_keys=True))
    print("Candidate evidence only; it grants no notice completeness, approval, or redistribution assertion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
