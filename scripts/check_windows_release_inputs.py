"""Fail closed unless Windows release dependency inputs are complete and pinned.

The check is deterministic and offline.  It compares the approved component
inventory against npm, Cargo, and Python lock inputs; it never queries package
registries or infers license approval.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_windows_release_provenance import (
    ReleaseProvenanceError,
    _digest,
    _load_object,
    _normalize_component,
)
from scripts.build_windows_component_inventory import build_component_inventory
from scripts.verify_windows_component_approvals import verify_component_approvals


_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9][A-Za-z0-9._+!-]*)\s+--hash=sha256:([0-9a-f]{64})$"
)


def _npm_purl(name: str, version: str) -> str:
    if name.startswith("@") and "/" in name:
        scope, package = name.split("/", 1)
        return f"pkg:npm/{quote(scope, safe='')}/{quote(package, safe='')}@{version}"
    return f"pkg:npm/{quote(name, safe='')}@{version}"


def _python_lock(path: Path, label: str) -> dict[str, tuple[str, str]]:
    if not path.is_file():
        raise ReleaseProvenanceError(f"Required {label} lock is missing: {path}")
    records: dict[str, tuple[str, str]] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _REQUIREMENT.fullmatch(line)
        if match is None:
            raise ReleaseProvenanceError(
                f"{label} lock line {number} must use exact == version and one SHA-256 hash"
            )
        name, version, digest = match.groups()
        normalized = name.lower().replace("_", "-").replace(".", "-")
        if normalized in records:
            raise ReleaseProvenanceError(f"{label} lock repeats Python package {normalized}")
        records[normalized] = (version, digest)
    if not records:
        raise ReleaseProvenanceError(f"{label} lock contains no packages")
    return records


def _expected_lock_components(
    package_lock_path: Path,
    cargo_lock_path: Path,
    build_requirements_path: Path,
    runtime_requirements_path: Path,
) -> dict[str, dict[str, tuple[str, str, set[str]]]]:
    npm = _load_object(package_lock_path, "npm package lock")
    if npm.get("lockfileVersion") != 3 or not isinstance(npm.get("packages"), Mapping):
        raise ReleaseProvenanceError("npm package lock must be lockfileVersion 3")
    npm_components: dict[str, tuple[str, str, set[str]]] = {}
    for package_path, record in npm["packages"].items():
        if not package_path or not isinstance(record, Mapping):
            continue
        name = str(package_path).rsplit("node_modules/", 1)[-1]
        version = str(record.get("version", ""))
        integrity = str(record.get("integrity", ""))
        license_expression = str(record.get("license", ""))
        if not version or not integrity.startswith("sha512-") or not license_expression:
            raise ReleaseProvenanceError(f"npm lock component {name!r} lacks version, SHA-512 SRI, or license")
        purl = _npm_purl(name, version)
        scope = "build-only" if record.get("dev") is True else "bundled"
        npm_components[purl] = ("sha512-sri", integrity, {scope})

    try:
        cargo = tomllib.loads(cargo_lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseProvenanceError(f"Cargo lock is unreadable: {cargo_lock_path}") from exc
    if cargo.get("version") != 4 or not isinstance(cargo.get("package"), list):
        raise ReleaseProvenanceError("Cargo lock must use version 4")
    rust_components: dict[str, tuple[str, str, set[str]]] = {}
    for record in cargo["package"]:
        if not isinstance(record, Mapping) or not record.get("source"):
            continue
        name = str(record.get("name", ""))
        version = str(record.get("version", ""))
        checksum = str(record.get("checksum", ""))
        if not name or not version or not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ReleaseProvenanceError(f"Cargo lock component {name!r} lacks exact checksum identity")
        rust_components[f"pkg:cargo/{quote(name, safe='')}@{version}"] = (
            "cargo-sha256", checksum, {"bundled", "build-only"}
        )

    python_build = _python_lock(build_requirements_path, "Windows build Python")
    python_runtime = _python_lock(runtime_requirements_path, "Windows runtime Python")
    result = {
        "npm": npm_components,
        "rust": rust_components,
        "python_build": {
            f"pkg:pypi/{name}@{value[0]}": ("sha256", value[1], {"build-only"})
            for name, value in python_build.items()
        },
        "python_runtime": {
            f"pkg:pypi/{name}@{value[0]}": ("sha256", value[1], {"bundled"})
            for name, value in python_runtime.items()
        },
    }
    for purl in set(result["python_build"]) & set(result["python_runtime"]):
        algorithm, value, _ = result["python_build"][purl]
        result["python_build"][purl] = (algorithm, value, {"bundled", "build-only"})
    return result


def check_release_inputs(
    dependencies_lock_path: str | Path,
    notices_path: str | Path,
    package_lock_path: str | Path,
    cargo_lock_path: str | Path,
    build_requirements_path: str | Path,
    runtime_requirements_path: str | Path,
) -> dict[str, Any]:
    dependencies_path = Path(dependencies_lock_path).resolve()
    notice_path = Path(notices_path).resolve()
    dependencies = _load_object(dependencies_path, "dependency lock")
    if dependencies.get("manifest") != "spike/dependencies/v1":
        raise ReleaseProvenanceError("Dependency lock contract is not spike/dependencies/v1")
    if not notice_path.is_file():
        raise ReleaseProvenanceError(f"Third-party notice bundle is missing: {notice_path}")
    notices = notice_path.read_text(encoding="utf-8")
    lowered = notices.lower()
    if "this register is incomplete" in lowered or "release-blocking" in lowered:
        raise ReleaseProvenanceError("Third-party notices remain explicitly incomplete or release-blocking")
    raw_components = dependencies.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        raise ReleaseProvenanceError("Dependency lock has no approved release component inventory")
    notice_reference = {"file": notice_path.name, "sha256": _digest(notice_path)}
    components = [
        _normalize_component(item, notices, notice_reference)
        for item in raw_components if isinstance(item, Mapping)
    ]
    if len(components) != len(raw_components):
        raise ReleaseProvenanceError("Dependency lock contains a malformed component record")
    purls = [str(item["purl"]) for item in components]
    if len(purls) != len(set(purls)):
        raise ReleaseProvenanceError("Approved release component purls must be unique")
    approved = set(purls)
    expected = _expected_lock_components(
        Path(package_lock_path), Path(cargo_lock_path),
        Path(build_requirements_path), Path(runtime_requirements_path),
    )
    missing = {
        group: sorted(set(group_components) - approved)
        for group, group_components in expected.items() if set(group_components) - approved
    }
    if missing:
        summary = "; ".join(f"{group}={len(values)}" for group, values in sorted(missing.items()))
        raise ReleaseProvenanceError(f"Approved component inventory does not cover lock inputs: {summary}")
    known = set().union(*(set(items) for items in expected.values()))
    by_purl = {str(item["purl"]): item for item in components}
    mismatches: list[str] = []
    for group_components in expected.values():
        for purl, (algorithm, value, scopes) in group_components.items():
            item = by_purl.get(purl)
            if item is None:
                continue
            integrity = item["integrity"]
            if integrity["algorithm"] != algorithm or integrity["value"] != value or item["scope"] not in scopes:
                mismatches.append(purl)
    if mismatches:
        raise ReleaseProvenanceError(
            f"Approved component integrity/scope differs from lock inputs: {len(mismatches)}"
        )
    bundled_or_build = {
        str(item["purl"]) for item in components if item["scope"] in {"bundled", "build-only"}
    }
    unexplained = sorted(bundled_or_build - known)
    if unexplained:
        raise ReleaseProvenanceError(
            f"Bundled/build-only components lack an authoritative lock identity: {len(unexplained)}"
        )
    return {
        "contract": "spike/windows-release-input-check/v1",
        "status": "passed",
        "production_qualified": False,
        "components": len(components),
        "lock_components": {key: len(value) for key, value in sorted(expected.items())},
        "input_sha256": {
            "dependencies_lock": _digest(dependencies_path),
            "notices": _digest(notice_path),
            "package_lock": _digest(Path(package_lock_path)),
            "cargo_lock": _digest(Path(cargo_lock_path)),
            "build_requirements": _digest(Path(build_requirements_path)),
            "runtime_requirements": _digest(Path(runtime_requirements_path)),
        },
    }


def check_generated_release_inputs(
    dependencies_lock_path: str | Path,
    notices_path: str | Path,
    package_lock_path: str | Path,
    cargo_lock_path: str | Path,
    cargo_manifest_path: str | Path,
    build_requirements_path: str | Path,
    runtime_requirements_path: str | Path,
    build_wheel_dir: str | Path,
    runtime_wheel_dir: str | Path,
    inventory_path: str | Path,
    approvals_path: str | Path,
    evidence_root: str | Path,
) -> dict[str, Any]:
    dependencies = _load_object(Path(dependencies_lock_path), "dependency lock")
    if dependencies.get("manifest") != "spike/dependencies/v1":
        raise ReleaseProvenanceError("Dependency lock contract is not spike/dependencies/v1")
    signature = dependencies.get("signature")
    if not isinstance(signature, Mapping) or signature.get("required") is not True or signature.get("format") != "cms-detached-sha256":
        raise ReleaseProvenanceError("Dependency lock must require detached SHA-256 CMS")
    inventory_file = Path(inventory_path).resolve()
    with tempfile.TemporaryDirectory(prefix="spike-component-inventory-") as directory:
        rebuilt_path = Path(directory) / "windows-component-inventory.json"
        rebuilt = build_component_inventory(
            package_lock_path, cargo_lock_path, cargo_manifest_path,
            build_requirements_path, runtime_requirements_path,
            build_wheel_dir, runtime_wheel_dir, rebuilt_path,
        )
        if not inventory_file.is_file() or _digest(inventory_file) != _digest(rebuilt_path):
            raise ReleaseProvenanceError("Checked-in Windows component inventory is stale or incomplete")
    approval = verify_component_approvals(
        inventory_file, approvals_path, notices_path, evidence_root,
    )
    return {
        "contract": "spike/windows-release-input-check/v2",
        "status": "passed", "production_qualified": False,
        "components": len(rebuilt["components"]),
        "inventory_sha256": _digest(inventory_file),
        "approval_verification": approval,
        "input_sha256": {
            "dependencies_lock": _digest(Path(dependencies_lock_path)),
            "notices": _digest(Path(notices_path)),
            "package_lock": _digest(Path(package_lock_path)),
            "cargo_lock": _digest(Path(cargo_lock_path)),
            "build_requirements": _digest(Path(build_requirements_path)),
            "runtime_requirements": _digest(Path(runtime_requirements_path)),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dependencies-lock", type=Path, default=ROOT / "dependencies.lock.json")
    parser.add_argument("--notices", type=Path, default=ROOT / "THIRD_PARTY_NOTICES.md")
    parser.add_argument("--package-lock", type=Path, default=ROOT / "app" / "package-lock.json")
    parser.add_argument("--cargo-lock", type=Path, default=ROOT / "app" / "src-tauri" / "Cargo.lock")
    parser.add_argument("--cargo-manifest", type=Path, default=ROOT / "app" / "src-tauri" / "Cargo.toml")
    parser.add_argument("--build-requirements", type=Path, default=ROOT / "requirements-build-windows-x64.txt")
    parser.add_argument("--runtime-requirements", type=Path, default=ROOT / "requirements-runtime-windows-x64.txt")
    parser.add_argument("--build-wheel-dir", type=Path, default=ROOT / ".tmp" / "build-lock-wheels-20260827-a")
    parser.add_argument("--runtime-wheel-dir", type=Path, default=ROOT / ".tmp" / "runtime-lock-wheels-20260827-a")
    parser.add_argument("--inventory", type=Path, default=ROOT / "config" / "windows-component-inventory.json")
    parser.add_argument("--approvals", type=Path, default=ROOT / "licenses" / "windows-component-approvals.json")
    parser.add_argument("--evidence-root", type=Path, default=ROOT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = check_generated_release_inputs(
            args.dependencies_lock, args.notices, args.package_lock, args.cargo_lock,
            args.cargo_manifest, args.build_requirements, args.runtime_requirements,
            args.build_wheel_dir, args.runtime_wheel_dir, args.inventory,
            args.approvals, args.evidence_root,
        )
    except ValueError as exc:
        raise SystemExit(f"Windows release inputs rejected: {exc}") from exc
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
