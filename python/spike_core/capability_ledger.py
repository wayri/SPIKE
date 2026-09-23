"""Read and validate the machine-readable native capability ledger.

The ledger is a release control, not a solver selector.  It records whether a
workflow has a native owner and evidence.  External engines can be listed for
comparison but cannot satisfy a native-release requirement.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import error_metadata
from .pi_validation_evidence import PiValidationEvidenceError, validate_release_qualification_binding


CAPABILITY_LEDGER_CONTRACT = "spike/native-capability-ledger/v1"
_LEDGER_PATH = Path(__file__).with_name("validation_data") / "native-capability-ledger-v1.json"
_RELEASE_STATES = {
    "implemented_approximate",
    "experimental",
    "reference_validated",
    "validated",
    "implementation_pending",
    "planned",
}
_VALIDATION_STATES = {
    "unvalidated",
    "approximate",
    "experimental",
    "reference_validated",
    "validated",
    "unsupported",
}


class CapabilityLedgerError(ValueError):
    """Raised when a ledger cannot safely control a release decision."""


def _strings(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise CapabilityLedgerError(f"{label} must be a {'non-empty ' if not allow_empty else ''}list.")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise CapabilityLedgerError(f"{label} must contain non-empty strings.")
    if len(set(value)) != len(value):
        raise CapabilityLedgerError(f"{label} must not contain duplicates.")
    return list(value)


def validate_capability_ledger(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a v1 ledger without consulting installed engines."""

    if not isinstance(payload, Mapping):
        raise CapabilityLedgerError("Capability ledger must be an object.")
    if payload.get("contract") != CAPABILITY_LEDGER_CONTRACT:
        raise CapabilityLedgerError("Unsupported capability-ledger contract.")
    if payload.get("schema_version") != 1:
        raise CapabilityLedgerError("Unsupported capability-ledger schema version.")
    policy = payload.get("policy")
    if not isinstance(policy, Mapping) or policy.get("released_ui_requires_native_owner") is not True:
        raise CapabilityLedgerError("Capability ledger must require a native owner for released UI workflows.")
    workflows = payload.get("workflows")
    if not isinstance(workflows, list) or not workflows:
        raise CapabilityLedgerError("Capability ledger must contain workflows.")
    normalized: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, item in enumerate(workflows):
        if not isinstance(item, Mapping):
            raise CapabilityLedgerError(f"workflows[{index}] must be an object.")
        workflow = dict(item)
        identifier = workflow.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise CapabilityLedgerError(f"workflows[{index}].id must be unique and non-empty.")
        identifiers.add(identifier)
        if not isinstance(workflow.get("domain"), str) or not workflow["domain"]:
            raise CapabilityLedgerError(f"workflows[{index}].domain must be non-empty.")
        if not isinstance(workflow.get("title"), str) or not workflow["title"]:
            raise CapabilityLedgerError(f"workflows[{index}].title must be non-empty.")
        if workflow.get("release_state") not in _RELEASE_STATES:
            raise CapabilityLedgerError(f"workflows[{index}].release_state is not recognized.")
        native_owner = workflow.get("native_owner")
        if not isinstance(native_owner, str) or not native_owner.startswith("spike.native."):
            raise CapabilityLedgerError(f"workflows[{index}].native_owner must name a SPIKE native solver.")
        if not isinstance(workflow.get("native_formulation"), str) or not workflow["native_formulation"]:
            raise CapabilityLedgerError(f"workflows[{index}].native_formulation must be non-empty.")
        for name in (
            "required_design_ir_entities",
            "supported_geometry",
            "validation_evidence",
            "external_comparison_engines",
            "blocking_error_codes",
        ):
            workflow[name] = _strings(workflow.get(name), f"workflows[{index}].{name}", allow_empty=name == "validation_evidence")
        if workflow.get("validation_state") not in _VALIDATION_STATES:
            raise CapabilityLedgerError(f"workflows[{index}].validation_state is not recognized.")
        for engine in workflow["external_comparison_engines"]:
            if not engine.startswith("external."):
                raise CapabilityLedgerError(f"workflows[{index}].external_comparison_engines must not contain native IDs.")
        for code in workflow["blocking_error_codes"]:
            try:
                error_metadata(code)
            except ValueError as exc:
                raise CapabilityLedgerError(f"workflows[{index}] has unregistered blocking error code {code!r}.") from exc
        validated_state = (
            workflow["release_state"] in {"validated", "reference_validated"}
            or workflow["validation_state"] in {"validated", "reference_validated"}
        )
        if validated_state and not workflow["validation_evidence"]:
            raise CapabilityLedgerError(f"workflows[{index}] cannot be validated without evidence.")
        if validated_state or "release_qualification" in workflow:
            try:
                workflow["release_qualification"] = validate_release_qualification_binding(
                    workflow.get("release_qualification")
                )
            except PiValidationEvidenceError as exc:
                raise CapabilityLedgerError(
                    f"workflows[{index}] validated states require digest-bound release_qualification: {exc}"
                ) from exc
        normalized.append(workflow)
    return {
        "contract": CAPABILITY_LEDGER_CONTRACT,
        "schema_version": 1,
        "policy": dict(policy),
        "workflows": normalized,
    }


@lru_cache(maxsize=1)
def native_capability_ledger() -> dict[str, Any]:
    """Return the validated, immutable-on-disk ledger for product release checks."""

    try:
        payload = json.loads(_LEDGER_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapabilityLedgerError(f"Unable to read native capability ledger: {exc}") from exc
    return validate_capability_ledger(payload)


def workflow_capability(workflow_id: str) -> dict[str, Any]:
    """Return one workflow record or raise an explicit lookup error."""

    if not isinstance(workflow_id, str) or not workflow_id:
        raise CapabilityLedgerError("workflow_id must be a non-empty string.")
    workflow = next(
        (item for item in native_capability_ledger()["workflows"] if item["id"] == workflow_id),
        None,
    )
    if workflow is None:
        raise CapabilityLedgerError(f"Unknown capability-ledger workflow: {workflow_id}")
    return dict(workflow)


def release_ready_workflows(records: Iterable[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Return only evidence-bearing workflows eligible for stable product release."""

    candidates = list(records) if records is not None else native_capability_ledger()["workflows"]
    return [
        dict(record)
        for record in candidates
        if record.get("release_state") in {"reference_validated", "validated"}
        and record.get("validation_evidence")
        and record.get("release_qualification")
    ]


__all__ = [
    "CAPABILITY_LEDGER_CONTRACT",
    "CapabilityLedgerError",
    "native_capability_ledger",
    "release_ready_workflows",
    "validate_capability_ledger",
    "workflow_capability",
]
