"""Digest-bound PI workflow qualification evidence admission."""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping


EVIDENCE_CONTRACT = "spike/pi-workflow-qualification-evidence/v1"
PROFILE_CONTRACT = "spike/pi-qualification-profiles/v1"
MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_PATH = Path(__file__).with_name("validation_data") / "pi-qualification-profiles-v1.json"


class PiValidationEvidenceError(ValueError):
    pass


def _profiles() -> dict[str, dict[str, Any]]:
    payload = json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    if payload.get("contract") != PROFILE_CONTRACT or not isinstance(payload.get("profiles"), list):
        raise PiValidationEvidenceError("PI qualification profile catalog is invalid.")
    return {str(item["profile_id"]): dict(item) for item in payload["profiles"] if isinstance(item, Mapping)}


def validate_release_qualification_binding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"evidence_id", "profile_id", "artifact_uri", "sha256"}:
        raise PiValidationEvidenceError("release_qualification must contain evidence_id, profile_id, artifact_uri, and sha256.")
    binding = {key: str(value[key]) for key in value}
    uri = binding["artifact_uri"]
    path = PurePosixPath(uri)
    if not uri or "\\" in uri or path.is_absolute() or ":" in uri or any(part in {"", ".", ".."} for part in path.parts):
        raise PiValidationEvidenceError("release_qualification artifact_uri must be a normalized safe relative URI.")
    if not _SHA256.fullmatch(binding["sha256"]):
        raise PiValidationEvidenceError("release_qualification sha256 must be lowercase hexadecimal.")
    for name in ("evidence_id", "profile_id"):
        if not re.fullmatch(r"[a-z][a-z0-9._-]{1,127}", binding[name]):
            raise PiValidationEvidenceError(f"release_qualification {name} is invalid.")
    return binding


def validate_pi_workflow_evidence(payload: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or payload.get("contract") != EVIDENCE_CONTRACT:
        raise PiValidationEvidenceError("Unsupported PI workflow evidence contract.")
    if payload.get("qualification_profile_id") != profile.get("profile_id"):
        raise PiValidationEvidenceError("Evidence qualification profile does not match the gate-owned profile.")
    for field in ("workflow_id", "native_owner", "qualification_level"):
        if payload.get(field) != profile.get(field):
            raise PiValidationEvidenceError(f"Evidence {field} does not match the gate-owned profile.")
    if payload.get("status") != "passed":
        raise PiValidationEvidenceError("PI qualification evidence must have passed.")
    candidate = payload.get("candidate")
    if not isinstance(candidate, Mapping) or candidate.get("solver_id") != profile.get("native_owner"):
        raise PiValidationEvidenceError("Evidence candidate is not the profiled native owner.")
    for field in ("worker_executable_sha256", "worker_manifest_sha256", "runtime_snapshot_digest"):
        if not isinstance(candidate.get(field), str) or not _SHA256.fullmatch(candidate[field]):
            raise PiValidationEvidenceError(f"Evidence candidate {field} is invalid.")
    cases = payload.get("cases")
    summary = payload.get("summary")
    if not isinstance(cases, list) or not cases or len(cases) > 10000 or not isinstance(summary, Mapping):
        raise PiValidationEvidenceError("Evidence requires bounded cases and a summary.")
    identifiers: set[str] = set()
    covered: set[str] = set()
    engines: set[str] = set()
    for case in cases:
        if not isinstance(case, Mapping) or case.get("status") != "passed":
            raise PiValidationEvidenceError("Every qualification case must pass.")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id in identifiers:
            raise PiValidationEvidenceError("Qualification case IDs must be unique strings.")
        identifiers.add(case_id)
        classes = case.get("classes")
        if not isinstance(classes, list) or any(not isinstance(item, str) or not item for item in classes):
            raise PiValidationEvidenceError(f"Qualification case {case_id} has invalid classes.")
        covered.update(classes)
        reference = case.get("reference")
        if not isinstance(reference, Mapping):
            raise PiValidationEvidenceError(f"Qualification case {case_id} has no reference.")
        engine_id = reference.get("engine_id")
        if isinstance(engine_id, str):
            engines.add(engine_id)
        if reference.get("kind") == "independent_solver" and (not isinstance(engine_id, str) or engine_id.startswith("spike.native.")):
            raise PiValidationEvidenceError("Independent-solver evidence must use a non-native engine.")
        metrics = case.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            raise PiValidationEvidenceError(f"Qualification case {case_id} has no metrics.")
        for metric in metrics:
            if not isinstance(metric, Mapping):
                raise PiValidationEvidenceError(f"Qualification case {case_id} has a malformed metric.")
            for name in ("candidate", "reference"):
                value = metric.get(name)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(float(value)):
                    raise PiValidationEvidenceError(f"Qualification metric {name} must be finite.")
    required_classes = set(profile.get("required_case_classes", []))
    missing_classes = sorted(required_classes - covered)
    if missing_classes:
        raise PiValidationEvidenceError("Evidence is missing required case classes: " + ", ".join(missing_classes) + ".")
    missing_engines = sorted(set(profile.get("required_reference_engines", [])) - engines)
    if missing_engines:
        raise PiValidationEvidenceError("Evidence is missing required reference engines: " + ", ".join(missing_engines) + ".")
    if summary.get("total") != len(cases) or summary.get("passed") != len(cases) or summary.get("failed") != 0 or summary.get("skipped") != 0:
        raise PiValidationEvidenceError("Evidence summary does not match its passing case rows.")
    limitations = payload.get("limitations")
    if not isinstance(limitations, list) or not limitations:
        raise PiValidationEvidenceError("Evidence must state its limitations.")
    return dict(payload)


def load_bound_pi_workflow_evidence(root: Path, binding_value: Any) -> dict[str, Any]:
    binding = validate_release_qualification_binding(binding_value)
    base = root.resolve(strict=True)
    path = (base / PurePosixPath(binding["artifact_uri"])).resolve(strict=True)
    if not path.is_relative_to(base) or not path.is_file() or path.is_symlink():
        raise PiValidationEvidenceError("Evidence artifact escaped its validation root or is not a regular file.")
    if any(parent.is_symlink() for parent in path.parents if parent != base):
        raise PiValidationEvidenceError("Evidence artifact path may not traverse symlinks.")
    data = path.read_bytes()
    if len(data) > MAX_EVIDENCE_BYTES:
        raise PiValidationEvidenceError("Evidence artifact exceeds the byte limit.")
    if sha256(data).hexdigest() != binding["sha256"]:
        raise PiValidationEvidenceError("Evidence artifact digest does not match the ledger binding.")
    try:
        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PiValidationEvidenceError("Evidence artifact is not strict UTF-8 JSON.") from exc
    if not isinstance(payload, Mapping) or payload.get("evidence_id") != binding["evidence_id"]:
        raise PiValidationEvidenceError("Evidence artifact identity does not match the ledger binding.")
    profile = _profiles().get(binding["profile_id"])
    if profile is None:
        raise PiValidationEvidenceError("Ledger references an unknown gate-owned qualification profile.")
    return validate_pi_workflow_evidence(payload, profile)


__all__ = [
    "EVIDENCE_CONTRACT", "PiValidationEvidenceError", "load_bound_pi_workflow_evidence",
    "validate_pi_workflow_evidence", "validate_release_qualification_binding",
]
