# SPDX-License-Identifier: MIT
"""Evidence-backed capability negotiation for layout metric evaluators.

The registry is intentionally separate from layout job construction.  Call
``validate_requirements_for_launch`` before preparing any evaluator jobs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, Mapping, Sequence, Tuple


LAYOUT_METRIC_REGISTRY_CONTRACT = "spike/layout-metric-registry/v1"
MAX_METRICS = 4096
MAX_EVIDENCE_PER_METRIC = 64

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9._-]{1,127}$", flags=re.ASCII)
_RESULT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$", flags=re.ASCII)
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$", flags=re.ASCII)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)

_EVALUATORS = {"cad_drc", "native_solver", "custom"}
_CONSUMERS = {"autorouter", "autoplacer", "joint"}
_KINDS = {"hard_constraint", "soft_constraint", "objective"}
_RELATIONS = {"le", "ge", "between", "target", "minimize", "maximize"}
_VALIDATION_STATES = {
    "qualified", "validated", "reference_validated", "verification_only",
    "cad_drc", "experimental", "approximate", "unvalidated",
}
_HARD_ACCEPTED_STATES = {
    "qualified", "validated", "reference_validated", "verification_only", "cad_drc",
}
_EVIDENCE_KINDS = {
    "validation_report", "benchmark", "conformance_suite",
    "manufactured_solution", "third_party_certification",
}
_CHANGE_KINDS = {
    "placement", "routing", "stackup", "geometry", "material", "boundary_condition",
}


class LayoutMetricRegistryError(ValueError):
    """A registry or requested capability failed a stable boundary check."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(code: str, message: str) -> None:
    raise LayoutMetricRegistryError(code, message)


def _object(value: Any, allowed: set[str], required: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        _fail("SPIKE-LAYOUT-REGISTRY-0001", f"{label} must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        _fail("SPIKE-LAYOUT-REGISTRY-0001", f"{label} has unknown or missing fields")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} is not a bounded identifier")
    return value


def _string(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} is invalid")
    return value


def _unique_enum_list(value: Any, allowed: set[str], label: str, maximum: int) -> Tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", f"{label} is invalid")
    if any(not isinstance(item, str) or item not in allowed for item in value) or len(set(value)) != len(value):
        _fail("SPIKE-LAYOUT-REGISTRY-0003", f"{label} contains unsupported or duplicate values")
    return tuple(value)


def _dimension(value: Any, label: str = "dimension") -> Tuple[Fraction, ...]:
    if not isinstance(value, list) or len(value) != 7:
        _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} must contain seven SI exponents")
    result = []
    for exponent in value:
        if isinstance(exponent, bool):
            _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} exponent is invalid")
        if isinstance(exponent, int) and -1024 <= exponent <= 1024:
            result.append(Fraction(exponent))
        elif (
            isinstance(exponent, list)
            and len(exponent) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) for item in exponent)
            and -1024 <= exponent[0] <= 1024
            and 1 <= exponent[1] <= 1024
        ):
            result.append(Fraction(exponent[0], exponent[1]))
        else:
            _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} exponent is invalid")
    return tuple(result)


def _dimension_json(value: Sequence[Fraction]) -> list[Any]:
    return [item.numerator if item.denominator == 1 else [item.numerator, item.denominator] for item in value]


def _relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str):
        _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} is invalid")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized or len(normalized) > 1024 or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in ("", ".", "..") for part in parts)
    ):
        _fail("SPIKE-LAYOUT-REGISTRY-0002", f"{label} must be normalized and relative")
    return normalized


@dataclass(frozen=True)
class EvidenceArtifact:
    path: str
    sha256: str
    bytes: int
    contract: str

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes, "contract": self.contract}


@dataclass(frozen=True)
class ValidationEvidence:
    id: str
    kind: str
    artifact: EvidenceArtifact
    claim: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"id": self.id, "kind": self.kind, "artifact": self.artifact.to_dict()}
        if self.claim is not None:
            result["claim"] = self.claim
        return result


@dataclass(frozen=True)
class BatchCapability:
    supported: bool
    max_candidates: int

    def to_dict(self) -> Dict[str, Any]:
        return {"supported": self.supported, "max_candidates": self.max_candidates}


@dataclass(frozen=True)
class IncrementalCapability:
    supported: bool
    change_kinds: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"supported": self.supported, "change_kinds": list(self.change_kinds)}


@dataclass(frozen=True)
class LayoutMetricCapability:
    id: str
    dimension: Tuple[Fraction, ...]
    evaluator: str
    result_key: str | None
    supported_consumers: Tuple[str, ...]
    supported_kinds: Tuple[str, ...]
    supported_relations: Tuple[str, ...]
    validation_state: str
    evidence: Tuple[ValidationEvidence, ...]
    batch: BatchCapability
    incremental: IncrementalCapability

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "dimension": _dimension_json(self.dimension),
            "evaluator": self.evaluator,
            "supported_consumers": list(self.supported_consumers),
            "supported_kinds": list(self.supported_kinds),
            "supported_relations": list(self.supported_relations),
            "validation_state": self.validation_state,
            "evidence": [item.to_dict() for item in self.evidence],
            "batch": self.batch.to_dict(),
            "incremental": self.incremental.to_dict(),
        }
        if self.result_key is not None:
            result["result_key"] = self.result_key
        return result


@dataclass(frozen=True)
class LayoutMetricRegistry:
    registry_id: str
    registry_version: str
    producer_implementation: str
    producer_version: str
    metrics: Tuple[LayoutMetricCapability, ...]

    def capability(self, metric_id: str) -> LayoutMetricCapability | None:
        return next((metric for metric in self.metrics if metric.id == metric_id), None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract": LAYOUT_METRIC_REGISTRY_CONTRACT,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "producer": {"implementation": self.producer_implementation, "version": self.producer_version},
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


@dataclass(frozen=True)
class RequirementCapabilityDecision:
    requirement_id: str
    metric_id: str
    evaluator: str
    validation_state: str


@dataclass(frozen=True)
class LayoutCapabilityNegotiation:
    registry_id: str
    registry_version: str
    consumer_kind: str
    batch_size: int
    incremental: bool
    change_kind: str | None
    decisions: Tuple[RequirementCapabilityDecision, ...]


def _parse_artifact(value: Any) -> EvidenceArtifact:
    obj = _object(value, {"path", "sha256", "bytes", "contract"}, {"path", "sha256", "bytes", "contract"}, "evidence.artifact")
    digest = obj["sha256"]
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        _fail("SPIKE-LAYOUT-REGISTRY-0002", "evidence artifact digest is invalid")
    size = obj["bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 1_073_741_824:
        _fail("SPIKE-LAYOUT-REGISTRY-0002", "evidence artifact size is invalid")
    return EvidenceArtifact(
        _relative_path(obj["path"], "evidence.artifact.path"), digest, size,
        _string(obj["contract"], "evidence.artifact.contract", 128),
    )


def _parse_evidence(value: Any) -> ValidationEvidence:
    obj = _object(value, {"id", "kind", "artifact", "claim"}, {"id", "kind", "artifact"}, "evidence")
    kind = obj["kind"]
    if kind not in _EVIDENCE_KINDS:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "evidence kind is unsupported")
    claim = _string(obj["claim"], "evidence.claim", 512) if "claim" in obj else None
    return ValidationEvidence(_identifier(obj["id"], "evidence.id"), kind, _parse_artifact(obj["artifact"]), claim)


def _parse_batch(value: Any) -> BatchCapability:
    obj = _object(value, {"supported", "max_candidates"}, {"supported", "max_candidates"}, "metric.batch")
    supported, maximum = obj["supported"], obj["max_candidates"]
    if not isinstance(supported, bool) or isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 65536:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric batch capability is invalid")
    if (supported and maximum < 2) or (not supported and maximum != 1):
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric batch limit contradicts support")
    return BatchCapability(supported, maximum)


def _parse_incremental(value: Any) -> IncrementalCapability:
    obj = _object(value, {"supported", "change_kinds"}, {"supported", "change_kinds"}, "metric.incremental")
    supported, changes = obj["supported"], obj["change_kinds"]
    if not isinstance(supported, bool) or not isinstance(changes, list):
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric incremental capability is invalid")
    if any(item not in _CHANGE_KINDS for item in changes) or len(set(changes)) != len(changes):
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "incremental change kinds are unsupported or duplicate")
    if (supported and not changes) or (not supported and changes):
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric incremental declaration contradicts support")
    return IncrementalCapability(supported, tuple(changes))


def _parse_metric(value: Any) -> LayoutMetricCapability:
    allowed = {
        "id", "dimension", "evaluator", "result_key", "supported_consumers",
        "supported_kinds", "supported_relations", "validation_state", "evidence",
        "batch", "incremental",
    }
    required = allowed - {"result_key"}
    obj = _object(value, allowed, required, "metric")
    evaluator = obj["evaluator"]
    if evaluator not in _EVALUATORS:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric evaluator is unsupported")
    result_key = obj.get("result_key")
    if evaluator == "native_solver":
        if not isinstance(result_key, str) or _RESULT_KEY_RE.fullmatch(result_key) is None:
            _fail("SPIKE-LAYOUT-REGISTRY-0003", "native metric requires a bounded result_key")
    elif result_key is not None:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "result_key is native-solver-only")
    state = obj["validation_state"]
    if state not in _VALIDATION_STATES or (state == "cad_drc" and evaluator != "cad_drc"):
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric validation state is invalid")
    evidence_value = obj["evidence"]
    if not isinstance(evidence_value, list) or not 1 <= len(evidence_value) <= MAX_EVIDENCE_PER_METRIC:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "metric must declare bounded validation evidence")
    evidence = tuple(_parse_evidence(item) for item in evidence_value)
    if len({item.id for item in evidence}) != len(evidence):
        _fail("SPIKE-LAYOUT-REGISTRY-0004", "metric contains duplicate evidence IDs")
    return LayoutMetricCapability(
        id=_identifier(obj["id"], "metric.id"),
        dimension=_dimension(obj["dimension"], "metric.dimension"),
        evaluator=evaluator,
        result_key=result_key,
        supported_consumers=_unique_enum_list(obj["supported_consumers"], _CONSUMERS, "supported_consumers", 3),
        supported_kinds=_unique_enum_list(obj["supported_kinds"], _KINDS, "supported_kinds", 3),
        supported_relations=_unique_enum_list(obj["supported_relations"], _RELATIONS, "supported_relations", 6),
        validation_state=state,
        evidence=evidence,
        batch=_parse_batch(obj["batch"]),
        incremental=_parse_incremental(obj["incremental"]),
    )


def validate_metric_registry(value: Any) -> LayoutMetricRegistry:
    """Decode a strict registry into immutable typed capabilities."""

    obj = _object(value, {"contract", "registry_id", "registry_version", "producer", "metrics"}, {"contract", "registry_id", "registry_version", "producer", "metrics"}, "registry")
    if obj["contract"] != LAYOUT_METRIC_REGISTRY_CONTRACT:
        _fail("SPIKE-LAYOUT-REGISTRY-0001", "registry contract is unsupported")
    version = obj["registry_version"]
    if not isinstance(version, str) or len(version) > 64 or _SEMVER_RE.fullmatch(version) is None:
        _fail("SPIKE-LAYOUT-REGISTRY-0002", "registry_version must be semantic versioning")
    producer = _object(obj["producer"], {"implementation", "version"}, {"implementation", "version"}, "producer")
    metric_values = obj["metrics"]
    if not isinstance(metric_values, list) or not 1 <= len(metric_values) <= MAX_METRICS:
        _fail("SPIKE-LAYOUT-REGISTRY-0003", "registry metric count is invalid")
    metrics = tuple(_parse_metric(metric) for metric in metric_values)
    if len({metric.id for metric in metrics}) != len(metrics):
        _fail("SPIKE-LAYOUT-REGISTRY-0004", "registry contains duplicate metric IDs")
    return LayoutMetricRegistry(
        registry_id=_identifier(obj["registry_id"], "registry_id"),
        registry_version=version,
        producer_implementation=_string(producer["implementation"], "producer.implementation", 128),
        producer_version=_string(producer["version"], "producer.version", 128),
        metrics=metrics,
    )


def canonical_metric_registry_json(value: Any) -> str:
    registry = value if isinstance(value, LayoutMetricRegistry) else validate_metric_registry(value)
    return json.dumps(registry.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def negotiate_layout_requirements(
    request: Mapping[str, Any],
    registry: LayoutMetricRegistry | Mapping[str, Any],
    *,
    batch_size: int = 1,
    incremental: bool = False,
    change_kind: str | None = None,
    accepted_hard_validation_states: Sequence[str] = tuple(sorted(_HARD_ACCEPTED_STATES)),
) -> LayoutCapabilityNegotiation:
    """Return a typed negotiation result or reject the first unsupported requirement."""

    typed = registry if isinstance(registry, LayoutMetricRegistry) else validate_metric_registry(registry)
    if not isinstance(request, Mapping) or request.get("contract") != "spike/layout-evaluation/v1":
        _fail("SPIKE-LAYOUT-REGISTRY-0001", "request is not spike/layout-evaluation/v1")
    consumer = request.get("consumer")
    consumer_kind = consumer.get("kind") if isinstance(consumer, Mapping) else None
    if consumer_kind not in _CONSUMERS:
        _fail("SPIKE-LAYOUT-REGISTRY-0006", "request consumer is unsupported")
    requirements = request.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        _fail("SPIKE-LAYOUT-REGISTRY-0001", "request requirements are missing")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        _fail("SPIKE-LAYOUT-REGISTRY-0008", "batch_size must be a positive integer")
    if not isinstance(incremental, bool):
        _fail("SPIKE-LAYOUT-REGISTRY-0008", "incremental must be boolean")
    if incremental and change_kind not in _CHANGE_KINDS:
        _fail("SPIKE-LAYOUT-REGISTRY-0008", "incremental execution requires a supported change_kind")
    if not incremental and change_kind is not None:
        _fail("SPIKE-LAYOUT-REGISTRY-0008", "change_kind is only valid for incremental execution")
    accepted = set(accepted_hard_validation_states)
    if not accepted <= _VALIDATION_STATES:
        _fail("SPIKE-LAYOUT-REGISTRY-0007", "accepted hard validation policy contains an unknown state")

    decisions = []
    seen_requirements: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, Mapping):
            _fail("SPIKE-LAYOUT-REGISTRY-0001", "requirement must be an object")
        requirement_id = _identifier(requirement.get("id"), "requirement.id")
        if requirement_id in seen_requirements:
            _fail("SPIKE-LAYOUT-REGISTRY-0004", "request contains duplicate requirement IDs")
        seen_requirements.add(requirement_id)
        metric_id = _identifier(requirement.get("metric_id"), "requirement.metric_id")
        capability = typed.capability(metric_id)
        if capability is None:
            _fail("SPIKE-LAYOUT-REGISTRY-0005", f"metric {metric_id!r} is not registered")
        evaluator = requirement.get("evaluator")
        kind = requirement.get("kind")
        relation = requirement.get("relation")
        if evaluator != capability.evaluator:
            _fail("SPIKE-LAYOUT-REGISTRY-0006", f"metric {metric_id!r} evaluator does not match")
        if consumer_kind not in capability.supported_consumers:
            _fail("SPIKE-LAYOUT-REGISTRY-0006", f"metric {metric_id!r} does not support {consumer_kind}")
        if kind not in capability.supported_kinds:
            _fail("SPIKE-LAYOUT-REGISTRY-0006", f"metric {metric_id!r} does not support requirement kind {kind!r}")
        if relation not in capability.supported_relations:
            _fail("SPIKE-LAYOUT-REGISTRY-0006", f"metric {metric_id!r} does not support relation {relation!r}")
        if _dimension(requirement.get("dimension"), "requirement.dimension") != capability.dimension:
            _fail("SPIKE-LAYOUT-REGISTRY-0006", f"metric {metric_id!r} SI dimension does not match")
        if capability.evaluator == "native_solver" and requirement.get("result_key") != capability.result_key:
            _fail("SPIKE-LAYOUT-REGISTRY-0006", f"metric {metric_id!r} result_key does not match")
        if kind == "hard_constraint" and capability.validation_state not in accepted:
            _fail("SPIKE-LAYOUT-REGISTRY-0007", f"metric {metric_id!r} validation state is insufficient for a hard constraint")
        if batch_size > 1 and (not capability.batch.supported or batch_size > capability.batch.max_candidates):
            _fail("SPIKE-LAYOUT-REGISTRY-0008", f"metric {metric_id!r} cannot evaluate a batch of {batch_size}")
        if incremental and (not capability.incremental.supported or change_kind not in capability.incremental.change_kinds):
            _fail("SPIKE-LAYOUT-REGISTRY-0008", f"metric {metric_id!r} cannot incrementally evaluate {change_kind}")
        decisions.append(RequirementCapabilityDecision(requirement_id, metric_id, evaluator, capability.validation_state))
    return LayoutCapabilityNegotiation(
        typed.registry_id, typed.registry_version, consumer_kind, batch_size,
        incremental, change_kind, tuple(decisions),
    )


def validate_requirements_for_launch(
    request: Mapping[str, Any],
    registry: LayoutMetricRegistry | Mapping[str, Any],
    **options: Any,
) -> LayoutCapabilityNegotiation:
    """Fail-closed launch preflight; no jobs should be prepared before this succeeds."""

    return negotiate_layout_requirements(request, registry, **options)


__all__ = [
    "BatchCapability", "EvidenceArtifact", "IncrementalCapability",
    "LAYOUT_METRIC_REGISTRY_CONTRACT", "LayoutCapabilityNegotiation",
    "LayoutMetricCapability", "LayoutMetricRegistry", "LayoutMetricRegistryError",
    "RequirementCapabilityDecision", "ValidationEvidence",
    "canonical_metric_registry_json", "negotiate_layout_requirements",
    "validate_metric_registry", "validate_requirements_for_launch",
]
