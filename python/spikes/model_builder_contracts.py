"""Immutable, versioned contracts for the SPIKES model-builder pipeline.

These contracts deliberately separate evidence, fitting, qualification, and
library export.  In particular, machine-extracted datasheet content is draft
evidence until a named reviewer accepts it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


MODEL_PACKAGE_CONTRACT = "spikes/model-package/v1"
SOURCE_ARTIFACT_CONTRACT = "spikes/model-source/v1"
CURVE_DATASET_CONTRACT = "spikes/curve-dataset/v1"
FIT_RESULT_CONTRACT = "spikes/model-fit-result/v1"
QUALIFICATION_CONTRACT = "spikes/model-qualification/v1"
BLACK_BOX_CONTRACT = "spikes/model-black-box/v1"
LIBRARY_EXPORT_CONTRACT = "spikes/model-library-export/v1"

_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_.-]*$", re.ASCII)
_MODEL_ID_RE = re.compile(
    r"^spikes\.(?:generic|power|electromechanical|core):[a-z][a-z0-9_.-]*@[1-9][0-9]*$",
    re.ASCII,
)
_PIN_RE = re.compile(r"^[a-z][a-z0-9_]*$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number, not a boolean.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def _mapping(values: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise ValueError(f"{label} must be a mapping.")
    return MappingProxyType(dict(sorted((str(key), value) for key, value in values.items())))


def canonical_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """A content-addressed input used to construct or validate a model."""

    source_id: str
    kind: str
    sha256: str
    locator: str
    title: str
    review_state: str = "unreviewed"
    reviewed_by: str = ""
    review_notes: str = ""
    license: str = "unknown"
    derived_from: tuple[str, ...] = ()
    contract: str = SOURCE_ARTIFACT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != SOURCE_ARTIFACT_CONTRACT:
            raise ValueError(f"Expected source contract {SOURCE_ARTIFACT_CONTRACT}.")
        if _TOKEN_RE.fullmatch(self.source_id) is None:
            raise ValueError("Source IDs must be lowercase ASCII identifiers.")
        if self.kind not in {"datasheet", "measurement", "simulation", "manual", "llm_extraction"}:
            raise ValueError(f"Unsupported source kind: {self.kind}.")
        if _SHA256_RE.fullmatch(self.sha256) is None:
            raise ValueError("Source artifacts require a lowercase SHA-256 digest.")
        if not self.locator.strip() or not self.title.strip():
            raise ValueError("Source locator and title are required.")
        if self.review_state not in {"unreviewed", "reviewed", "rejected"}:
            raise ValueError("Review state must be unreviewed, reviewed, or rejected.")
        if self.review_state == "reviewed" and not self.reviewed_by.strip():
            raise ValueError("Reviewed evidence requires a named reviewer.")
        if self.review_state != "reviewed" and self.reviewed_by.strip():
            raise ValueError("Only reviewed evidence may name a reviewer.")
        if self.kind == "llm_extraction" and not self.derived_from:
            raise ValueError("LLM extraction must identify the source artifacts it derives from.")
        if len(self.derived_from) != len(set(self.derived_from)):
            raise ValueError("Source derivation references must be unique.")

    @property
    def trusted_for_qualification(self) -> bool:
        return self.review_state == "reviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "id": self.source_id,
            "kind": self.kind,
            "sha256": self.sha256,
            "locator": self.locator,
            "title": self.title,
            "review_state": self.review_state,
            "reviewed_by": self.reviewed_by,
            "review_notes": self.review_notes,
            "license": self.license,
            "derived_from": list(self.derived_from),
            "trusted_for_qualification": self.trusted_for_qualification,
        }


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    """One fitted or declared model parameter with units and hard bounds."""

    name: str
    unit: str
    value: float
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""
    uncertainty: float | None = None
    source_ids: tuple[str, ...] = ()
    fitted: bool = False

    def __post_init__(self) -> None:
        if _TOKEN_RE.fullmatch(self.name) is None:
            raise ValueError("Parameter names must be lowercase ASCII identifiers.")
        if not self.unit.strip():
            raise ValueError("Parameters require an explicit unit or '1'.")
        value = finite(self.value, self.name)
        minimum = None if self.minimum is None else finite(self.minimum, f"{self.name}.minimum")
        maximum = None if self.maximum is None else finite(self.maximum, f"{self.name}.maximum")
        uncertainty = None if self.uncertainty is None else finite(self.uncertainty, f"{self.name}.uncertainty")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"{self.name} minimum exceeds maximum.")
        if minimum is not None and value < minimum or maximum is not None and value > maximum:
            raise ValueError(f"{self.name} value is outside its declared bounds.")
        if uncertainty is not None and uncertainty < 0.0:
            raise ValueError("Parameter uncertainty cannot be negative.")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Parameter source references must be unique.")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "uncertainty", uncertainty)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "value": self.value,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "description": self.description,
            "uncertainty": self.uncertainty,
            "source_ids": list(self.source_ids),
            "fitted": self.fitted,
        }


@dataclass(frozen=True, slots=True)
class DatasetColumn:
    name: str
    unit: str

    def __post_init__(self) -> None:
        if _TOKEN_RE.fullmatch(self.name) is None or not self.unit.strip():
            raise ValueError("Dataset columns require a valid name and explicit unit.")

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "unit": self.unit}


@dataclass(frozen=True, slots=True)
class CurveDataset:
    """A rectangular measured, extracted, or synthetic curve dataset."""

    dataset_id: str
    kind: str
    columns: tuple[DatasetColumn, ...]
    rows: tuple[tuple[float, ...], ...]
    source_ids: tuple[str, ...]
    role: str = "fit"
    conditions: Mapping[str, float] = field(default_factory=dict)
    contract: str = CURVE_DATASET_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != CURVE_DATASET_CONTRACT or _TOKEN_RE.fullmatch(self.dataset_id) is None:
            raise ValueError("Invalid curve dataset contract or ID.")
        if self.kind not in {"measured", "datasheet_extracted", "synthetic"}:
            raise ValueError(f"Unsupported dataset kind: {self.kind}.")
        if self.role not in {"fit", "validation", "both"}:
            raise ValueError("Dataset role must be fit, validation, or both.")
        if len(self.columns) < 2 or len({column.name for column in self.columns}) != len(self.columns):
            raise ValueError("Curve datasets require at least two unique columns.")
        if not self.rows:
            raise ValueError("Curve datasets cannot be empty.")
        normalized_rows = []
        for row_index, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(f"Dataset row {row_index} has the wrong column count.")
            normalized_rows.append(tuple(finite(value, f"row {row_index}") for value in row))
        if not self.source_ids or len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Datasets require unique source references.")
        normalized_conditions = {
            str(name): finite(value, f"condition {name}") for name, value in self.conditions.items()
        }
        object.__setattr__(self, "rows", tuple(normalized_rows))
        object.__setattr__(self, "conditions", _mapping(normalized_conditions, "conditions"))

    def column(self, name: str) -> tuple[float, ...]:
        try:
            index = tuple(column.name for column in self.columns).index(name)
        except ValueError as exc:
            raise ValueError(f"Dataset {self.dataset_id} has no {name!r} column.") from exc
        return tuple(row[index] for row in self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "id": self.dataset_id,
            "kind": self.kind,
            "columns": [column.to_dict() for column in self.columns],
            "rows": [list(row) for row in self.rows],
            "source_ids": list(self.source_ids),
            "role": self.role,
            "conditions": dict(self.conditions),
        }


@dataclass(frozen=True, slots=True)
class DomainBound:
    name: str
    unit: str
    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if _TOKEN_RE.fullmatch(self.name) is None or not self.unit.strip():
            raise ValueError("Validity bounds require a valid name and explicit unit.")
        minimum = finite(self.minimum, f"{self.name}.minimum")
        maximum = finite(self.maximum, f"{self.name}.maximum")
        if minimum >= maximum:
            raise ValueError("Validity minimum must be less than maximum.")
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "unit": self.unit, "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True, slots=True)
class ValidityEnvelope:
    bounds: tuple[DomainBound, ...]
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.bounds or len({bound.name for bound in self.bounds}) != len(self.bounds):
            raise ValueError("A validity envelope requires unique bounds.")

    def to_dict(self) -> dict[str, Any]:
        return {"bounds": [bound.to_dict() for bound in self.bounds], "notes": self.notes}


@dataclass(frozen=True, slots=True)
class ErrorMetrics:
    sample_count: int
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int) or self.sample_count < 1:
            raise ValueError("Error metrics require at least one sample.")
        normalized = {str(name): finite(value, f"metric {name}") for name, value in self.values.items()}
        if not normalized or any(_TOKEN_RE.fullmatch(name) is None or value < 0.0 for name, value in normalized.items()):
            raise ValueError("Error metrics require non-negative, named values.")
        object.__setattr__(self, "values", _mapping(normalized, "metrics"))

    def to_dict(self) -> dict[str, Any]:
        return {"sample_count": self.sample_count, "values": dict(self.values)}


@dataclass(frozen=True, slots=True)
class FitResult:
    fitter_id: str
    fitter_version: str
    dataset_ids: tuple[str, ...]
    parameter_values: Mapping[str, float]
    parameter_uncertainties: Mapping[str, float]
    metrics: ErrorMetrics
    deterministic: bool = True
    contract: str = FIT_RESULT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != FIT_RESULT_CONTRACT or _TOKEN_RE.fullmatch(self.fitter_id) is None:
            raise ValueError("Invalid fit result contract or fitter ID.")
        if not self.fitter_version.strip() or not self.dataset_ids or not self.deterministic:
            raise ValueError("Qualified fitting requires a versioned deterministic fitter and datasets.")
        normalized = {str(name): finite(value, f"fit parameter {name}") for name, value in self.parameter_values.items()}
        if not normalized or any(_TOKEN_RE.fullmatch(name) is None for name in normalized):
            raise ValueError("Fit results require named parameter values.")
        uncertainties = {
            str(name): finite(value, f"fit uncertainty {name}")
            for name, value in self.parameter_uncertainties.items()
        }
        if set(uncertainties) != set(normalized) or any(value < 0.0 for value in uncertainties.values()):
            raise ValueError("Every fitted parameter requires a non-negative uncertainty estimate.")
        object.__setattr__(self, "parameter_values", _mapping(normalized, "fit parameters"))
        object.__setattr__(self, "parameter_uncertainties", _mapping(uncertainties, "fit uncertainties"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "fitter_id": self.fitter_id,
            "fitter_version": self.fitter_version,
            "dataset_ids": list(self.dataset_ids),
            "parameter_values": dict(self.parameter_values),
            "parameter_uncertainties": dict(self.parameter_uncertainties),
            "metrics": self.metrics.to_dict(),
            "deterministic": self.deterministic,
        }


@dataclass(frozen=True, slots=True)
class QualificationRecord:
    state: str = "draft"
    reviewer: str = ""
    policy_id: str = ""
    checks: tuple[str, ...] = ()
    notes: str = ""
    contract: str = QUALIFICATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != QUALIFICATION_CONTRACT or self.state not in {"draft", "qualified", "rejected"}:
            raise ValueError("Invalid qualification contract or state.")
        if self.state == "qualified" and (not self.reviewer.strip() or not self.policy_id.strip() or not self.checks):
            raise ValueError("Qualified models require reviewer, policy, and passed checks.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "state": self.state,
            "reviewer": self.reviewer,
            "policy_id": self.policy_id,
            "checks": list(self.checks),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class BlackBoxDescriptor:
    """Compilation-facing descriptor; it contains no executable payload itself."""

    black_box_id: str
    implementation: str
    pins: tuple[str, ...]
    observables: tuple[str, ...]
    state_variables: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    deterministic: bool = True
    realtime_safe: bool = False
    contract: str = BLACK_BOX_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != BLACK_BOX_CONTRACT or _TOKEN_RE.fullmatch(self.black_box_id) is None:
            raise ValueError("Invalid black-box contract or ID.")
        if not self.implementation.strip() or not self.pins or not self.observables:
            raise ValueError("Black boxes require implementation, pins, and observables.")
        if any(_PIN_RE.fullmatch(pin) is None for pin in self.pins) or len(self.pins) != len(set(self.pins)):
            raise ValueError("Black-box pins must be valid and unique.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "id": self.black_box_id,
            "implementation": self.implementation,
            "pins": list(self.pins),
            "observables": list(self.observables),
            "state_variables": list(self.state_variables),
            "required_capabilities": list(self.required_capabilities),
            "deterministic": self.deterministic,
            "realtime_safe": self.realtime_safe,
        }


@dataclass(frozen=True, slots=True)
class ModelPackage:
    """Immutable model artifact. ``content_sha256`` excludes qualification."""

    model_id: str
    title: str
    family: str
    summary: str
    pins: tuple[str, ...]
    parameters: tuple[ParameterDefinition, ...]
    sources: tuple[SourceArtifact, ...]
    datasets: tuple[CurveDataset, ...]
    fit_results: tuple[FitResult, ...]
    validity: ValidityEnvelope
    black_box: BlackBoxDescriptor
    qualification: QualificationRecord
    content_sha256: str
    contract: str = MODEL_PACKAGE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != MODEL_PACKAGE_CONTRACT or _MODEL_ID_RE.fullmatch(self.model_id) is None:
            raise ValueError("Invalid model-package contract or model ID.")
        if not all((self.title.strip(), self.family.strip(), self.summary.strip())):
            raise ValueError("Model packages require descriptive metadata.")
        if not self.pins or self.pins != self.black_box.pins:
            raise ValueError("Model and black-box pins must match exactly.")
        for collection, label, key in (
            (self.parameters, "parameter", lambda item: item.name),
            (self.sources, "source", lambda item: item.source_id),
            (self.datasets, "dataset", lambda item: item.dataset_id),
        ):
            keys = [key(item) for item in collection]
            if not keys or len(keys) != len(set(keys)):
                raise ValueError(f"Model packages require unique {label}s.")
        if _SHA256_RE.fullmatch(self.content_sha256) is None:
            raise ValueError("Model packages require a SHA-256 content digest.")
        source_ids = {source.source_id for source in self.sources}
        dataset_ids = {dataset.dataset_id for dataset in self.datasets}
        for dataset in self.datasets:
            if not set(dataset.source_ids) <= source_ids:
                raise ValueError(f"Dataset {dataset.dataset_id} references an unknown source.")
        for source in self.sources:
            if not set(source.derived_from) <= source_ids:
                raise ValueError(f"Source {source.source_id} has an unknown derivation source.")
            if source.source_id in source.derived_from:
                raise ValueError(f"Source {source.source_id} cannot derive from itself.")
        derivations = {source.source_id: source.derived_from for source in self.sources}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(source_id: str) -> None:
            if source_id in visiting:
                raise ValueError("Source provenance contains a derivation cycle.")
            if source_id in visited:
                return
            visiting.add(source_id)
            for parent in derivations[source_id]:
                visit(parent)
            visiting.remove(source_id)
            visited.add(source_id)

        for source_id in derivations:
            visit(source_id)
        for fit in self.fit_results:
            if not set(fit.dataset_ids) <= dataset_ids:
                raise ValueError("Fit result references an unknown dataset.")

    def content_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "model_id": self.model_id,
            "title": self.title,
            "family": self.family,
            "summary": self.summary,
            "pins": list(self.pins),
            "parameters": [parameter.to_dict() for parameter in self.parameters],
            "sources": [source.to_dict() for source in self.sources],
            "datasets": [dataset.to_dict() for dataset in self.datasets],
            "fit_results": [fit.to_dict() for fit in self.fit_results],
            "validity": self.validity.to_dict(),
            "black_box": self.black_box.to_dict(),
        }

    def verify_digest(self) -> bool:
        return canonical_digest(self.content_dict()) == self.content_sha256

    def to_dict(self) -> dict[str, Any]:
        result = self.content_dict()
        result["qualification"] = self.qualification.to_dict()
        result["content_sha256"] = self.content_sha256
        return result


__all__ = [
    "BLACK_BOX_CONTRACT", "CURVE_DATASET_CONTRACT", "FIT_RESULT_CONTRACT",
    "LIBRARY_EXPORT_CONTRACT", "MODEL_PACKAGE_CONTRACT", "QUALIFICATION_CONTRACT",
    "SOURCE_ARTIFACT_CONTRACT", "BlackBoxDescriptor", "CurveDataset", "DatasetColumn",
    "DomainBound", "ErrorMetrics", "FitResult", "ModelPackage", "ParameterDefinition",
    "QualificationRecord", "SourceArtifact", "ValidityEnvelope", "canonical_digest", "finite",
]
