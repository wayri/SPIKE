# SPDX-License-Identifier: MIT
"""Machine-readable public release gate for the bounded SPIKES engine."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from python.spikes.release_verifier import verify_engine_release
from python.spikes.version import ENGINE_VERSION


CONTRACT = "spike/public-release-readiness/v1"
PASS = "PASS"
BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
FAIL = "FAIL"


class PublicReleaseGateError(ValueError):
    """A technical public-release invariant failed."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicReleaseGateError(f"invalid JSON control file: {path.name}") from exc
    if not isinstance(value, dict):
        raise PublicReleaseGateError(f"JSON control file must be an object: {path.name}")
    return value


def _version_check(root: Path) -> dict[str, Any]:
    cmake = (root / "CMakeLists.txt").read_text(encoding="utf-8")
    project = re.search(r"project\(SPIKE VERSION ([0-9.]+)", cmake)
    prerelease = re.search(r'set\(SPIKES_ENGINE_PRERELEASE "([^"]+)"', cmake)
    if project is None or prerelease is None:
        raise PublicReleaseGateError("CMake engine version declarations are missing")
    cmake_version = f"{project.group(1)}-{prerelease.group(1)}"
    vcpkg = _read_object(root / "standalone" / "spikes_project" / "vcpkg.json")
    observed = {
        "python": ENGINE_VERSION,
        "cmake": cmake_version,
        "standalone_vcpkg": vcpkg.get("version-string"),
    }
    if any(value != ENGINE_VERSION for value in observed.values()):
        raise PublicReleaseGateError(f"SPIKES engine version drift: {observed}")
    return {"status": PASS, "engine_version": ENGINE_VERSION, "surfaces": observed}


def _schema_check(root: Path) -> dict[str, Any]:
    directory = root / "schemas"
    catalog = _read_object(directory / "manifest.json")
    entries = catalog.get("schemas")
    if catalog.get("contract") != "spike/schema-catalog/v1" or not isinstance(entries, dict):
        raise PublicReleaseGateError("public schema catalog is incompatible")
    seen_files: set[str] = set()
    seen_ids: set[str] = set()
    for contract, filename in entries.items():
        if not isinstance(contract, str) or not isinstance(filename, str) or Path(filename).name != filename:
            raise PublicReleaseGateError("public schema catalog contains an unsafe entry")
        if filename in seen_files:
            raise PublicReleaseGateError(f"public schema file is mapped twice: {filename}")
        schema = _read_object(directory / filename)
        schema_id = schema.get("$id")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise PublicReleaseGateError(f"public schema does not use draft 2020-12: {filename}")
        if not isinstance(schema_id, str) or not schema_id or schema_id in seen_ids:
            raise PublicReleaseGateError(f"public schema $id is absent or repeated: {filename}")
        seen_files.add(filename)
        seen_ids.add(schema_id)
    required = {
        "spike/layout-scoring-process-job/v1",
        "spike/beta-runtime-readiness/v1",
        "spike/public-release-readiness/v1",
    }
    missing = sorted(required - set(entries))
    if missing:
        raise PublicReleaseGateError(f"public schema catalog omits required contracts: {missing}")
    return {"status": PASS, "catalogued_contracts": len(entries), "unique_schema_ids": len(seen_ids)}


def evaluate_public_release(
    repository: str | Path,
    *,
    engine_report: str | Path,
) -> dict[str, Any]:
    """Evaluate technical gates and expose external authorization blockers."""

    root = Path(repository).resolve(strict=True)
    checks: dict[str, Any] = {}
    failures: list[str] = []
    try:
        checks["version_coherence"] = _version_check(root)
    except (OSError, PublicReleaseGateError) as exc:
        failures.append(str(exc))
        checks["version_coherence"] = {"status": FAIL, "reason": str(exc)}
    try:
        checks["public_schema_catalog"] = _schema_check(root)
    except (OSError, PublicReleaseGateError) as exc:
        failures.append(str(exc))
        checks["public_schema_catalog"] = {"status": FAIL, "reason": str(exc)}
    try:
        verification = verify_engine_release(engine_report)
        if verification.get("version") != ENGINE_VERSION:
            raise PublicReleaseGateError("verified artifact version differs from the source engine")
        checks["artifact_integrity_and_smoke"] = verification
    except (OSError, ValueError) as exc:
        failures.append(str(exc))
        checks["artifact_integrity_and_smoke"] = {"status": FAIL, "reason": str(exc)}

    blockers: list[dict[str, str]] = []
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    notices_text = (root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    if "does not currently have one blanket license" in license_text.lower():
        blockers.append({
            "code": "PUBLIC_RELEASE_OWNERSHIP_APPROVAL_REQUIRED",
            "owner_action": "Confirm ownership and replace the mixed repository notice with counsel-approved grants for every distributed path.",
        })
    if "register is incomplete" in notices_text.lower():
        blockers.append({
            "code": "PUBLIC_RELEASE_DEPENDENCY_APPROVAL_REQUIRED",
            "owner_action": "Complete the version-specific SBOM, notices, asset provenance, and redistribution approval review.",
        })
    artifact = checks.get("artifact_integrity_and_smoke", {})
    if isinstance(artifact, dict) and artifact.get("status") == "passed":
        blockers.extend((
            {
                "code": "PUBLIC_RELEASE_SIGNATURE_REQUIRED",
                "owner_action": "Sign the final immutable archive and publish the trusted verification key and signature policy.",
            },
            {
                "code": "PUBLIC_RELEASE_CLEAN_MACHINE_EVIDENCE_REQUIRED",
                "owner_action": "Run installation, launch, rollback, and uninstall on supported clean Windows images.",
            },
            {
                "code": "PUBLIC_RELEASE_AUDITABLE_CI_REQUIRED",
                "owner_action": "Retain private-CI build, test, dependency, and provenance evidence for the exact archive digest.",
            },
        ))
    status = FAIL if failures else (BLOCKED_EXTERNAL if blockers else PASS)
    return {
        "contract": CONTRACT,
        "product": "SPIKES circuit engine and SDK",
        "version": ENGINE_VERSION,
        "status": status,
        "public_distribution_authorized": status == PASS,
        "technical_candidate": not failures,
        "checks": checks,
        "failures": failures,
        "external_blockers": blockers,
        "claim_boundary": {
            "complete_spice3_parity": False,
            "arbitrary_ibis": False,
            "pcb_field_physics": False,
            "competitive_superiority": False,
            "hard_realtime": False,
            "production_signed": False,
        },
    }


__all__ = [
    "BLOCKED_EXTERNAL", "CONTRACT", "FAIL", "PASS",
    "PublicReleaseGateError", "evaluate_public_release",
]
