"""Typed, solver-neutral contracts for SPIKE-native numerical engines.

These contracts are intentionally separate from the legacy plugin manifest.
They define the stable boundary used by native C++ engines, isolated workers,
benchmark runners, and future commercial solver deployments.  They contain
only JSON-compatible values and never make an external adapter a native path.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .errors import parse_error_code


NATIVE_SOLVER_DESCRIPTOR_CONTRACT = "spike/native-solver-descriptor/v1"
NATIVE_SOLVE_REQUEST_CONTRACT = "spike/native-solve-request/v1"
NATIVE_SOLVE_RESULT_CONTRACT = "spike/native-solve-result/v1"

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9._-]{1,127}$", flags=re.ASCII)
_HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)


class NativeSolverState(str, Enum):
    """Lifecycle state of a solver implementation, not an inferred result state."""

    PLANNED = "planned"
    IMPLEMENTED = "implemented"
    EXPERIMENTAL = "experimental"
    VALIDATED = "validated"
    RETIRED = "retired"


class ValidationState(str, Enum):
    """Evidence tier that can be carried by a native result."""

    UNVALIDATED = "unvalidated"
    APPROXIMATE = "approximate"
    EXPERIMENTAL = "experimental"
    REFERENCE_VALIDATED = "reference_validated"
    VALIDATED = "validated"
    UNSUPPORTED = "unsupported"


class SolveStatus(str, Enum):
    """Terminal status of one requested native solve."""

    NOT_RUN = "not_run"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


def _validate_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(
            f"{label} must use lowercase ASCII letters, digits, '.', '_', or '-'."
        )


def _string_tuple(values: Sequence[str], label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, str) or not isinstance(values, Sequence):
        raise ValueError(f"{label} must be a sequence of strings.")
    normalized = tuple(values)
    if not allow_empty and not normalized:
        raise ValueError(f"{label} must not be empty.")
    if any(not isinstance(item, str) or not item.strip() for item in normalized):
        raise ValueError(f"{label} must contain non-empty strings.")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{label} must not contain duplicates.")
    return normalized


def _json_object(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping.")
    return dict(value)


@dataclass(frozen=True, slots=True)
class ValidityRange:
    """Published applicability constraints for an individual formulation."""

    frequency_min_hz: float | None = None
    frequency_max_hz: float | None = None
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    assumptions: tuple[str, ...] = ()
    known_failure_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, low, high in (
            ("frequency", self.frequency_min_hz, self.frequency_max_hz),
            ("temperature", self.temperature_min_c, self.temperature_max_c),
        ):
            if low is not None and not isinstance(low, (int, float)):
                raise ValueError(f"{label} lower bound must be numeric or null.")
            if high is not None and not isinstance(high, (int, float)):
                raise ValueError(f"{label} upper bound must be numeric or null.")
            if low is not None and high is not None and float(low) > float(high):
                raise ValueError(f"{label} lower bound must not exceed the upper bound.")
        object.__setattr__(self, "assumptions", _string_tuple(self.assumptions, "assumptions", allow_empty=True))
        object.__setattr__(
            self,
            "known_failure_modes",
            _string_tuple(self.known_failure_modes, "known_failure_modes", allow_empty=True),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    """A traceable benchmark, reference, or measurement record."""

    evidence_id: str
    tier: ValidationState
    fixture_ids: tuple[str, ...]
    acceptance_criteria: str
    published_error_bound_percent: float | None = None
    report_uri: str = ""

    def __post_init__(self) -> None:
        _validate_identifier(self.evidence_id, "evidence_id")
        if not isinstance(self.tier, ValidationState):
            raise ValueError("tier must be a ValidationState.")
        object.__setattr__(self, "fixture_ids", _string_tuple(self.fixture_ids, "fixture_ids"))
        if not isinstance(self.acceptance_criteria, str) or not self.acceptance_criteria.strip():
            raise ValueError("acceptance_criteria must be a non-empty string.")
        if self.published_error_bound_percent is not None and self.published_error_bound_percent < 0:
            raise ValueError("published_error_bound_percent must be non-negative.")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["tier"] = self.tier.value
        return result


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    """Declared resource estimate before executing a job."""

    estimated_memory_bytes: int
    estimated_wall_time_s: float
    recommended_threads: int = 1
    checkpoint_supported: bool = False
    out_of_core_supported: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.estimated_memory_bytes, bool) or self.estimated_memory_bytes < 0:
            raise ValueError("estimated_memory_bytes must be a non-negative integer.")
        if self.estimated_wall_time_s < 0:
            raise ValueError("estimated_wall_time_s must be non-negative.")
        if isinstance(self.recommended_threads, bool) or self.recommended_threads < 1:
            raise ValueError("recommended_threads must be at least one.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NativeSolverDescriptor:
    """Versioned declaration for an internal SPIKE solver engine."""

    solver_id: str
    version: str
    owner: str
    state: NativeSolverState
    workloads: tuple[str, ...]
    formulations: tuple[str, ...]
    required_design_ir_entities: tuple[str, ...]
    supported_geometry: tuple[str, ...]
    capabilities: tuple[str, ...]
    validity: ValidityRange
    validation_evidence: tuple[ValidationEvidence, ...]
    acceleration_backends: tuple[str, ...] = ()
    resource_features: tuple[str, ...] = ()
    contract: str = NATIVE_SOLVER_DESCRIPTOR_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != NATIVE_SOLVER_DESCRIPTOR_CONTRACT:
            raise ValueError("Unsupported native solver descriptor contract.")
        _validate_identifier(self.solver_id, "solver_id")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("version must be a non-empty string.")
        if not isinstance(self.owner, str) or not self.owner.strip():
            raise ValueError("owner must be a non-empty string.")
        if not isinstance(self.state, NativeSolverState):
            raise ValueError("state must be a NativeSolverState.")
        for field_name in (
            "workloads",
            "formulations",
            "required_design_ir_entities",
            "supported_geometry",
            "capabilities",
            "acceleration_backends",
            "resource_features",
        ):
            object.__setattr__(
                self,
                field_name,
                _string_tuple(getattr(self, field_name), field_name, allow_empty=field_name in {"acceleration_backends", "resource_features"}),
            )
        if not isinstance(self.validity, ValidityRange):
            raise ValueError("validity must be a ValidityRange.")
        if not isinstance(self.validation_evidence, tuple) or any(
            not isinstance(item, ValidationEvidence) for item in self.validation_evidence
        ):
            raise ValueError("validation_evidence must be a tuple of ValidationEvidence.")
        if self.state is NativeSolverState.VALIDATED and not self.validation_evidence:
            raise ValueError("Validated solvers must declare validation evidence.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "solver_id": self.solver_id,
            "version": self.version,
            "owner": self.owner,
            "state": self.state.value,
            "workloads": list(self.workloads),
            "formulations": list(self.formulations),
            "required_design_ir_entities": list(self.required_design_ir_entities),
            "supported_geometry": list(self.supported_geometry),
            "capabilities": list(self.capabilities),
            "validity": self.validity.to_dict(),
            "validation_evidence": [item.to_dict() for item in self.validation_evidence],
            "acceleration_backends": list(self.acceleration_backends),
            "resource_features": list(self.resource_features),
        }


@dataclass(frozen=True, slots=True)
class NativeSolveRequest:
    """Validated handoff from a design/mesh pipeline to one native solver."""

    request_id: str
    solver_id: str
    workload_id: str
    design_digest_sha256: str
    design_contract: str
    geometry_contract: str
    analysis: Mapping[str, Any]
    resource_budget: ResourceEstimate
    required_entities: tuple[str, ...]
    result_fields: tuple[str, ...]
    cancellation_token: str = ""
    contract: str = NATIVE_SOLVE_REQUEST_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != NATIVE_SOLVE_REQUEST_CONTRACT:
            raise ValueError("Unsupported native solve request contract.")
        for label in ("request_id", "solver_id", "workload_id"):
            _validate_identifier(getattr(self, label), label)
        if not isinstance(self.design_digest_sha256, str) or _HEX_DIGEST_RE.fullmatch(self.design_digest_sha256) is None:
            raise ValueError("design_digest_sha256 must be a lowercase SHA-256 digest.")
        if not isinstance(self.design_contract, str) or not self.design_contract.strip():
            raise ValueError("design_contract must be a non-empty string.")
        if not isinstance(self.geometry_contract, str) or not self.geometry_contract.strip():
            raise ValueError("geometry_contract must be a non-empty string.")
        object.__setattr__(self, "analysis", _json_object(self.analysis, "analysis"))
        if not isinstance(self.resource_budget, ResourceEstimate):
            raise ValueError("resource_budget must be a ResourceEstimate.")
        object.__setattr__(self, "required_entities", _string_tuple(self.required_entities, "required_entities"))
        object.__setattr__(self, "result_fields", _string_tuple(self.result_fields, "result_fields"))
        if self.cancellation_token and not isinstance(self.cancellation_token, str):
            raise ValueError("cancellation_token must be a string.")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["resource_budget"] = self.resource_budget.to_dict()
        result["required_entities"] = list(self.required_entities)
        result["result_fields"] = list(self.result_fields)
        return result


@dataclass(frozen=True, slots=True)
class NativeSolveResult:
    """Typed terminal result returned by a native solver execution boundary."""

    request_id: str
    solver_id: str
    status: SolveStatus
    validation_state: ValidationState
    fields: Mapping[str, Any]
    networks: Mapping[str, Any]
    provenance: Mapping[str, Any]
    resource_usage: Mapping[str, Any]
    issue_codes: tuple[str, ...] = ()
    result_digest_sha256: str = ""
    contract: str = NATIVE_SOLVE_RESULT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != NATIVE_SOLVE_RESULT_CONTRACT:
            raise ValueError("Unsupported native solve result contract.")
        _validate_identifier(self.request_id, "request_id")
        _validate_identifier(self.solver_id, "solver_id")
        if not isinstance(self.status, SolveStatus):
            raise ValueError("status must be a SolveStatus.")
        if not isinstance(self.validation_state, ValidationState):
            raise ValueError("validation_state must be a ValidationState.")
        for field_name in ("fields", "networks", "provenance", "resource_usage"):
            object.__setattr__(self, field_name, _json_object(getattr(self, field_name), field_name))
        codes = _string_tuple(self.issue_codes, "issue_codes", allow_empty=True)
        for code in codes:
            parse_error_code(code)
        object.__setattr__(self, "issue_codes", codes)
        if self.result_digest_sha256 and _HEX_DIGEST_RE.fullmatch(self.result_digest_sha256) is None:
            raise ValueError("result_digest_sha256 must be empty or a lowercase SHA-256 digest.")
        if self.status is SolveStatus.COMPLETED and self.validation_state is ValidationState.UNSUPPORTED:
            raise ValueError("Completed results cannot use the unsupported validation state.")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["validation_state"] = self.validation_state.value
        result["issue_codes"] = list(self.issue_codes)
        return result


__all__ = [
    "NATIVE_SOLVER_DESCRIPTOR_CONTRACT",
    "NATIVE_SOLVE_REQUEST_CONTRACT",
    "NATIVE_SOLVE_RESULT_CONTRACT",
    "NativeSolverDescriptor",
    "NativeSolverState",
    "NativeSolveRequest",
    "NativeSolveResult",
    "ResourceEstimate",
    "SolveStatus",
    "ValidationEvidence",
    "ValidationState",
    "ValidityRange",
]
