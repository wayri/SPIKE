"""Integrity-bound readiness report for the SPIKES 0.2 engineering preview."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


REPORT_CONTRACT = "spikes/first-release-readiness/v1"
_CONTRACTS = {
    "benchmark": "spikes/competitive-benchmark-report/v1",
    "qualification": "spikes/qualification-report/v1",
    "parity": "spikes/parity-check-report/v1",
    "runtime": "spike/release-runtime-qualification/v1",
    "portable": "spike/portable-manifest/v1",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: str | Path, contract: str) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve(strict=True)
    value = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.get("contract") != contract:
        raise ValueError(f"{resolved} must use {contract}")
    return resolved, value


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}


def verify_portable_tree(portable_dir: str | Path) -> dict[str, Any]:
    root = Path(portable_dir).resolve(strict=True)
    manifest_path, manifest = _load(
        root / "portable.manifest.json", _CONTRACTS["portable"]
    )
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("Portable manifest must contain a non-empty file inventory")
    expected: set[str] = set()
    failures: list[dict[str, str]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Portable file records must be objects")
        relative = str(record.get("path", ""))
        pure = PurePosixPath(relative)
        if (
            not relative or pure.is_absolute() or ".." in pure.parts
            or relative in expected or "\\" in relative
        ):
            raise ValueError(f"Unsafe or duplicate portable path: {relative!r}")
        expected.add(relative)
        candidate = root.joinpath(*pure.parts)
        if not candidate.is_file():
            failures.append({"path": relative, "reason": "missing"})
            continue
        if candidate.stat().st_size != record.get("size"):
            failures.append({"path": relative, "reason": "size_mismatch"})
            continue
        if _sha256(candidate) != record.get("sha256"):
            failures.append({"path": relative, "reason": "sha256_mismatch"})
    actual = {
        item.relative_to(root).as_posix()
        for item in root.rglob("*")
        if item.is_file() and item != manifest_path
    }
    for relative in sorted(actual - expected):
        failures.append({"path": relative, "reason": "unmanifested"})
    return {
        "status": "passed" if not failures else "failed",
        "files": len(expected),
        "bytes": sum(int(item.get("size", 0)) for item in records),
        "failures": failures,
        "manifest": _artifact(manifest_path),
        "version": manifest.get("version"),
        "architecture": manifest.get("architecture"),
    }


def verify_portable_archive(portable_zip: str | Path) -> dict[str, Any]:
    archive = Path(portable_zip).resolve(strict=True)
    failures: list[dict[str, str]] = []
    with zipfile.ZipFile(archive) as bundle:
        file_names = [item.filename for item in bundle.infolist() if not item.is_dir()]
        manifest_names = [
            name for name in file_names if name.endswith("/portable.manifest.json")
        ]
        if len(manifest_names) != 1:
            raise ValueError("Portable archive must contain exactly one root manifest")
        manifest_name = manifest_names[0]
        prefix = manifest_name.removesuffix("portable.manifest.json")
        manifest = json.loads(bundle.read(manifest_name).decode("utf-8-sig"))
        if manifest.get("contract") != _CONTRACTS["portable"]:
            raise ValueError("Portable archive manifest contract is invalid")
        records = manifest.get("files")
        if not isinstance(records, list) or not records:
            raise ValueError("Portable archive manifest inventory is empty")
        expected = {str(item.get("path", "")): item for item in records}
        if len(expected) != len(records):
            raise ValueError("Portable archive manifest paths must be unique")
        actual = {
            name.removeprefix(prefix)
            for name in file_names if name != manifest_name and name.startswith(prefix)
        }
        for relative, record in expected.items():
            pure = PurePosixPath(relative)
            if not relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative:
                raise ValueError(f"Unsafe portable archive path: {relative!r}")
            member_name = prefix + relative
            try:
                info = bundle.getinfo(member_name)
            except KeyError:
                failures.append({"path": relative, "reason": "missing"})
                continue
            if info.file_size != record.get("size"):
                failures.append({"path": relative, "reason": "size_mismatch"})
                continue
            digest = hashlib.sha256()
            with bundle.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != record.get("sha256"):
                failures.append({"path": relative, "reason": "sha256_mismatch"})
        for relative in sorted(actual - set(expected)):
            failures.append({"path": relative, "reason": "unmanifested"})
    return {
        "status": "passed" if not failures else "failed",
        "files": len(expected),
        "failures": failures,
        "archive": _artifact(archive),
        "version": manifest.get("version"),
        "architecture": manifest.get("architecture"),
    }
def build_first_release_report(
    *,
    version: str,
    benchmark_path: str | Path,
    qualification_path: str | Path,
    parity_path: str | Path,
    runtime_path: str | Path,
    portable_dir: str | Path,
    portable_zip: str | Path,
) -> dict[str, Any]:
    benchmark_file, benchmark = _load(benchmark_path, _CONTRACTS["benchmark"])
    qualification_file, qualification = _load(
        qualification_path, _CONTRACTS["qualification"]
    )
    parity_file, parity = _load(parity_path, _CONTRACTS["parity"])
    runtime_file, runtime = _load(runtime_path, _CONTRACTS["runtime"])
    portable = verify_portable_tree(portable_dir)
    archive = verify_portable_archive(portable_zip)
    checks = [
        {
            "id": "competitive.shared_subset_accuracy",
            "passed": benchmark.get("status") == "passed"
            and benchmark.get("shared_subset_accuracy_passed") is True,
        },
        {
            "id": "native.qualification",
            "passed": qualification.get("status") == "passed"
            and qualification.get("summary", {}).get("failed") == 0,
        },
        {
            "id": "runtime.source_package_parity",
            "passed": runtime.get("status") == "passed"
            and runtime.get("summary", {}).get("failed") == 0,
        },
        {"id": "portable.integrity", "passed": portable["status"] == "passed"},
        {"id": "portable.archive_integrity", "passed": archive["status"] == "passed"},
        {
            "id": "portable.version_architecture",
            "passed": portable["version"] == version
            and portable["architecture"] == "x64",
        },
        {
            "id": "claims.competitive_fail_closed",
            "passed": parity.get("status") == "blocked"
            and parity.get("claim_eligible") is False
            and benchmark.get("performance_claim_eligible") is False,
        },
        {
            "id": "claims.realtime_hil_fail_closed",
            "passed": qualification.get("qualification", {}).get(
                "hard_realtime_qualified"
            ) is False
            and qualification.get("qualification", {}).get("hil_qualified") is False,
        },
    ]
    passed = sum(item["passed"] for item in checks)
    ready = passed == len(checks)
    return {
        "contract": REPORT_CONTRACT,
        "product": "SPIKES engine with SPIKE desktop",
        "version": version,
        "channel": "engineering_preview",
        "status": "ready" if ready else "blocked",
        "summary": {
            "total": len(checks), "passed": passed, "failed": len(checks) - passed,
        },
        "checks": checks,
        "artifacts": {
            "benchmark": _artifact(benchmark_file),
            "qualification": _artifact(qualification_file),
            "parity": _artifact(parity_file),
            "runtime": _artifact(runtime_file),
            "portable_archive": archive,
            "portable_tree": portable,
        },
        "claims": {
            "engineering_preview_ready": ready,
            "spice3_parity": False,
            "competitive_superiority": False,
            "hard_realtime": False,
            "physical_hil": False,
            "production_signed": False,
        },
        "policy": (
            "Ready authorizes only the declared engineering-preview scope; it does "
            "not promote blocked competitive, hard-real-time, HIL, or signing claims."
        ),
    }


__all__ = [
    "REPORT_CONTRACT", "build_first_release_report", "verify_portable_archive",
    "verify_portable_tree",
]
