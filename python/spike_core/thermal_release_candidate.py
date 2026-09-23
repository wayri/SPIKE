"""Fail-closed evidence evaluation for field-thermal release candidates.

This is deliberately separate from solver selection and thermal job execution.
It evaluates records emitted by an adapter against small analytic fixtures and
records immutable package/runtime identities.  Passing these checks creates a
*candidate*, never a production or sign-off claim: independent and measured
references plus exact Windows and Linux package records remain mandatory.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping, Sequence

from .project_package import ManifestVerifier, ProjectPackageError
from .project_package_auth import validate_targeted_manifest_signature
from .runtime_qualification import canonical_digest
from .thermal_validation import assess_mesh_convergence, layered_conduction_reference


CANDIDATE_CONTRACT = "spike/thermal-release-qualification-candidate/v1"
PACKAGE_IDENTITY_CONTRACT = "spike/thermal-runtime-package-identity/v1"
REQUIRED_PLATFORMS = frozenset({"windows-x64", "linux-x64"})
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _authenticated_record(record: Mapping[str, Any], *, verifier: ManifestVerifier | None, label: str) -> str | None:
    """Verify an Ed25519-style attestation over every evidence field.

    Reuses the project package's canonical signed-payload semantics.  A digest
    string is only an identifier; it becomes qualification evidence here only
    when an installed trust verifier authenticates the complete record.
    """
    attestation = record.get("attestation")
    if not isinstance(attestation, Mapping):
        return f"{label} requires a signed attestation."
    if verifier is None:
        return f"{label} requires a trusted attestation verifier."
    signed = {key: value for key, value in record.items() if key != "attestation"}
    signed["signature"] = attestation
    try:
        validate_targeted_manifest_signature(signed, signature_verifier=verifier, require_signature=True)
    except ProjectPackageError as exc:
        return f"{label} attestation verification failed: {exc}"
    return None


def validate_package_identity(record: Any, *, solver_id: str, solver_version: str, verifier: ManifestVerifier | None = None) -> dict[str, Any]:
    """Validate one exact adapter/runtime/package identity without opening it."""
    issues: list[str] = []
    if not isinstance(record, Mapping) or set(record) != {
        "contract", "platform", "solver", "adapter_sha256", "runtime", "package", "attestation"
    }:
        return {"valid": False, "issues": ["Package identity must contain exactly the required record fields."]}
    if record.get("contract") != PACKAGE_IDENTITY_CONTRACT:
        issues.append(f"Package identity must use {PACKAGE_IDENTITY_CONTRACT}.")
    platform = record.get("platform")
    if platform not in REQUIRED_PLATFORMS:
        issues.append("Package identity platform must be windows-x64 or linux-x64.")
    solver = record.get("solver")
    if not isinstance(solver, Mapping) or set(solver) != {"id", "version"}:
        issues.append("Package identity solver must contain exact id and version.")
    elif solver.get("id") != solver_id or str(solver.get("version")) != str(solver_version):
        issues.append("Package identity solver id/version does not match the candidate adapter.")
    for label in ("adapter_sha256",):
        if not _SHA256.fullmatch(str(record.get(label) or "")):
            issues.append(f"Package identity {label} must be a lowercase SHA-256 digest.")
    for label in ("runtime", "package"):
        value = record.get(label)
        if not isinstance(value, Mapping) or set(value) != {"id", "version", "sha256"}:
            issues.append(f"Package identity {label} must contain exact id, version, and sha256 fields.")
        elif not str(value.get("id") or "") or not str(value.get("version") or "") or not _SHA256.fullmatch(str(value.get("sha256") or "")):
            issues.append(f"Package identity {label} is incomplete or has an invalid SHA-256 digest.")
    authentication_issue = _authenticated_record(record, verifier=verifier, label="Package identity")
    if authentication_issue:
        issues.append(authentication_issue)
    return {"valid": not issues, "platform": platform, "issues": issues}


def _relative_error(observed: float | None, expected: float) -> float | None:
    return None if observed is None else abs(observed - expected) / max(abs(expected), 1e-30)


def _evaluate_layered_contact(record: Any) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        return {"id": "layered_contact", "passed": False, "issues": ["Layered/contact record must be an object."]}
    try:
        fixture = layered_conduction_reference(
            layers=record["layers"], area_m2=float(record["area_m2"]),
            contact_resistances_k_per_w=record.get("contact_resistances_k_per_w", ()),
            heat_w=float(record.get("heat_w", 1.0)), cold_temperature_k=float(record.get("cold_temperature_k", 293.15)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        return {"id": "layered_contact", "passed": False, "issues": [str(exc)]}
    result = record.get("result") if isinstance(record.get("result"), Mapping) else {}
    tolerance = _finite(record.get("relative_tolerance"))
    if tolerance is None or tolerance < 0:
        return {"id": "layered_contact", "passed": False, "issues": ["Layered/contact tolerance must be finite and non-negative."]}
    temperature_error = _relative_error(_finite(result.get("hot_temperature_k")), fixture["hot_temperature_k"])
    heat_error = _relative_error(_finite(result.get("conducted_heat_w")), fixture["conservation"]["conducted_heat_w"])
    residual = _finite(result.get("energy_residual_w"))
    conservation_limit = max(abs(fixture["heat_w"]) * tolerance, 1e-12)
    passed = temperature_error is not None and heat_error is not None and residual is not None and temperature_error <= tolerance and heat_error <= tolerance and abs(residual) <= conservation_limit
    return {
        "id": "layered_contact", "passed": passed, "fixture_digest": canonical_digest(fixture),
        "temperature_relative_error": temperature_error, "heat_relative_error": heat_error,
        "energy_residual_w": residual, "relative_tolerance": tolerance,
        "issues": [] if passed else ["Candidate must match analytic layered/contact temperature, heat flow, and energy conservation."],
    }


def _evaluate_convergence(levels: Any, *, kind: str, metric_key: str, refinement_key: str, tolerance: Any) -> dict[str, Any]:
    if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
        return {"id": f"{kind}_convergence", "passed": False, "issues": ["Convergence levels must be an array."]}
    relative_tolerance = _finite(tolerance)
    if relative_tolerance is None or relative_tolerance <= 0:
        return {"id": f"{kind}_convergence", "passed": False, "issues": ["Convergence tolerance must be finite and positive."]}
    try:
        records = [dict(item) for item in levels]
        if kind == "mesh":
            report = assess_mesh_convergence(records, metric_key=metric_key, relative_tolerance=relative_tolerance)
        else:
            if len(records) < 3:
                raise ValueError("Thermal time convergence requires at least three coarse-to-fine levels.")
            steps = [float(item[refinement_key]) for item in records]
            values = [float(item[metric_key]) for item in records]
            if any(step <= 0 for step in steps) or any(right >= left for left, right in zip(steps, steps[1:])):
                raise ValueError("Time levels must use strictly decreasing positive time steps.")
            deltas = [abs(right - left) / max(abs(right), 1e-30) for left, right in zip(values, values[1:])]
            report = {"contract": "spike/thermal-time-convergence/v1", "levels": records, "finest_relative_change": deltas[-1], "relative_tolerance": relative_tolerance, "passed": deltas[-1] <= relative_tolerance}
    except (TypeError, ValueError, KeyError) as exc:
        return {"id": f"{kind}_convergence", "passed": False, "issues": [str(exc)]}
    return {"id": f"{kind}_convergence", "passed": bool(report["passed"]), "report": report, "fixture_digest": canonical_digest(report), "issues": [] if report["passed"] else ["Finest convergence pair exceeds tolerance."]}


def evaluate_thermal_release_candidate(candidate: Any, *, evidence_verifier: ManifestVerifier | None = None) -> dict[str, Any]:
    """Evaluate supplied evidence records and return a digest-bound release candidate.

    No paths are opened and no solver is run.  This function is intentionally
    useful for CI/offline evidence ingestion, not as a surrogate thermal solver.
    """
    if not isinstance(candidate, Mapping) or candidate.get("contract") != CANDIDATE_CONTRACT:
        return {"valid": False, "issues": [f"Candidate must use {CANDIDATE_CONTRACT}."]}
    solver = candidate.get("solver")
    if not isinstance(solver, Mapping) or not str(solver.get("id") or "") or not str(solver.get("version") or ""):
        return {"valid": False, "issues": ["Candidate requires solver id and version."]}
    solver_id, solver_version = str(solver["id"]), str(solver["version"])
    records = candidate.get("records") if isinstance(candidate.get("records"), Mapping) else {}
    checks = [
        _evaluate_layered_contact(records.get("layered_contact")),
        _evaluate_convergence(records.get("mesh_levels"), kind="mesh", metric_key="hot_temperature_k", refinement_key="cells", tolerance=records.get("mesh_relative_tolerance")),
        _evaluate_convergence(records.get("time_levels"), kind="time", metric_key="hot_temperature_k", refinement_key="time_step_s", tolerance=records.get("time_relative_tolerance")),
    ]
    package_records = candidate.get("package_identities") if isinstance(candidate.get("package_identities"), list) else []
    package_checks = [validate_package_identity(item, solver_id=solver_id, solver_version=solver_version, verifier=evidence_verifier) for item in package_records]
    valid_platforms = {item.get("platform") for item in package_checks if item.get("valid")}
    references = candidate.get("references") if isinstance(candidate.get("references"), list) else []
    authenticated_references: list[str] = []
    for item in references:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") != "passed" or not str(item.get("id") or ""):
            continue
        if not _SHA256.fullmatch(str(item.get("reference_artifact_sha256") or "")) or not _SHA256.fullmatch(str(item.get("result_sha256") or "")):
            continue
        if _authenticated_record(item, verifier=evidence_verifier, label=f"Reference {item.get('id')}") is None:
            authenticated_references.append(str(item.get("type")))
    reference_types = set(authenticated_references)
    issues = [issue for check in checks for issue in check["issues"]]
    if REQUIRED_PLATFORMS - valid_platforms:
        issues.append("Exact qualified runtime/package identities are required for Windows x64 and Linux x64.")
    if "independent_solver" not in reference_types:
        issues.append("An identified digest-bound independent-solver reference is required.")
    if "measured" not in reference_types:
        issues.append("An identified digest-bound measured reference is required.")
    if references and not authenticated_references:
        issues.append("No supplied reference record passed trusted attestation verification.")
    return {
        "contract": CANDIDATE_CONTRACT,
        "candidate_digest": canonical_digest(candidate), "solver": {"id": solver_id, "version": solver_version},
        "checks": checks, "package_checks": package_checks, "reference_types": sorted(reference_types),
        "valid": not issues, "issues": issues,
        "qualification": "candidate_only; independent/measured and platform identities are release gates",
    }


__all__ = ["CANDIDATE_CONTRACT", "PACKAGE_IDENTITY_CONTRACT", "REQUIRED_PLATFORMS", "evaluate_thermal_release_candidate", "validate_package_identity"]
