"""Deterministic, fail-closed model construction for SPIKES.

This module is intentionally independent of any future GUI or local LLM.  An
LLM may create evidence through :func:`llm_draft_source`, but that evidence is
untrusted until a human review is recorded and all numerical qualification
gates pass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .library_contracts import ArchetypeDescriptor, ParameterSpec
from .model_builder_contracts import (
    LIBRARY_EXPORT_CONTRACT,
    BlackBoxDescriptor,
    CurveDataset,
    ErrorMetrics,
    FitResult,
    ModelPackage,
    ParameterDefinition,
    QualificationRecord,
    SourceArtifact,
    ValidityEnvelope,
    canonical_digest,
    finite,
)


class ModelBuilderError(ValueError):
    """Base error for deterministic model construction."""


class QualificationError(ModelBuilderError):
    """The draft failed a required qualification or trust gate."""


class LibraryExportError(ModelBuilderError):
    """The package is not safe to expose as a runnable library model."""


class ModelFitter(Protocol):
    """Contract implemented by deterministic fitting algorithms."""

    fitter_id: str
    version: str

    def fit(
        self,
        dataset: CurveDataset,
        parameters: Mapping[str, ParameterDefinition],
    ) -> FitResult: ...


@dataclass(frozen=True, slots=True)
class QualificationPolicy:
    policy_id: str = "spikes.model.standard-v1"
    metric_maximums: Mapping[str, float] | None = None
    minimum_samples: int = 5
    require_validation_dataset: bool = True

    def __post_init__(self) -> None:
        maxima = {"log_rmse": 0.15, "max_relative_error": 0.35} if self.metric_maximums is None else dict(self.metric_maximums)
        normalized = {str(name): finite(value, f"metric limit {name}") for name, value in maxima.items()}
        if not self.policy_id.strip() or not normalized or any(value < 0.0 for value in normalized.values()):
            raise ValueError("Qualification policy requires an ID and non-negative metric limits.")
        if isinstance(self.minimum_samples, bool) or not isinstance(self.minimum_samples, int) or self.minimum_samples < 2:
            raise ValueError("Qualification requires at least two samples.")
        object.__setattr__(self, "metric_maximums", MappingProxyType(dict(sorted(normalized.items()))))


@dataclass(frozen=True, slots=True)
class ModelLibraryExport:
    """Immutable hand-off from qualification into the archetype registry."""

    package: ModelPackage
    archetype: ArchetypeDescriptor
    contract: str = LIBRARY_EXPORT_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != LIBRARY_EXPORT_CONTRACT:
            raise ValueError(f"Expected export contract {LIBRARY_EXPORT_CONTRACT}.")
        if self.package.qualification.state != "qualified" or not self.package.verify_digest():
            raise LibraryExportError("Only intact, qualified packages can form a library export.")
        if self.archetype.archetype_id != self.package.model_id or not self.archetype.available:
            raise LibraryExportError("Library descriptor does not match its qualified model package.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "package": self.package.to_dict(),
            "archetype": self.archetype.to_dict(),
        }


def llm_draft_source(
    source_id: str,
    sha256: str,
    locator: str,
    title: str,
    derived_from: tuple[str, ...],
    *,
    license: str = "unknown",
) -> SourceArtifact:
    """Create untrusted machine-extracted evidence; never a trusted source."""

    return SourceArtifact(
        source_id=source_id,
        kind="llm_extraction",
        sha256=sha256,
        locator=locator,
        title=title,
        review_state="unreviewed",
        license=license,
        derived_from=derived_from,
    )


class ShockleyDiodeFitter:
    """Deterministically fit ``I=Is*(exp(V/(n*Vt))-1)`` in log-current space."""

    fitter_id = "shockley_diode"
    version = "1.0.0"
    saturation_parameter = "saturation_current_a"
    ideality_parameter = "ideality_factor"
    _BOLTZMANN = 1.380649e-23
    _ELECTRON_CHARGE = 1.602176634e-19

    @staticmethod
    def _required_parameter(
        parameters: Mapping[str, ParameterDefinition], name: str
    ) -> ParameterDefinition:
        try:
            return parameters[name]
        except KeyError as exc:
            raise ModelBuilderError(f"Diode fitting requires parameter {name!r}.") from exc

    def fit(
        self,
        dataset: CurveDataset,
        parameters: Mapping[str, ParameterDefinition],
    ) -> FitResult:
        voltage = dataset.column("voltage_v")
        current = dataset.column("current_a")
        samples = tuple((v, i) for v, i in zip(voltage, current) if v > 0.0 and i > 0.0)
        if len(samples) < 3:
            raise ModelBuilderError("Shockley fitting requires at least three positive forward-bias samples.")
        temperature_c = finite(dataset.conditions.get("temperature_c", 25.0), "temperature_c")
        temperature_k = temperature_c + 273.15
        if temperature_k <= 0.0:
            raise ModelBuilderError("Dataset temperature must be above absolute zero.")
        thermal_voltage = self._BOLTZMANN * temperature_k / self._ELECTRON_CHARGE

        is_spec = self._required_parameter(parameters, self.saturation_parameter)
        n_spec = self._required_parameter(parameters, self.ideality_parameter)
        lower = 0.5 if n_spec.minimum is None else n_spec.minimum
        upper = 4.0 if n_spec.maximum is None else n_spec.maximum
        if lower <= 0.0 or lower >= upper:
            raise ModelBuilderError("Ideality-factor bounds must define a positive interval.")

        def solution(candidate_n: float) -> tuple[float, float]:
            offsets = []
            for volts, amps in samples:
                argument = volts / (candidate_n * thermal_voltage)
                if argument > 700.0:
                    log_term = argument
                else:
                    term = math.expm1(argument)
                    if term <= 0.0:
                        return math.inf, math.nan
                    log_term = math.log(term)
                offsets.append(math.log(amps) - log_term)
            log_is = sum(offsets) / len(offsets)
            error = sum((offset - log_is) ** 2 for offset in offsets) / len(offsets)
            return error, math.exp(log_is)

        # Fixed-iteration golden-section minimization gives bit-stable control
        # flow for a given Python/libm build and avoids optimizer dependencies.
        ratio = (math.sqrt(5.0) - 1.0) / 2.0
        left, right = lower, upper
        c = right - ratio * (right - left)
        d = left + ratio * (right - left)
        fc, _ = solution(c)
        fd, _ = solution(d)
        for _ in range(96):
            if fc <= fd:
                right, d, fd = d, c, fc
                c = right - ratio * (right - left)
                fc, _ = solution(c)
            else:
                left, c, fc = c, d, fd
                d = left + ratio * (right - left)
                fd, _ = solution(d)
        ideality = (left + right) * 0.5
        _, saturation = solution(ideality)
        saturation = is_spec.value if not math.isfinite(saturation) else saturation
        if is_spec.minimum is not None:
            saturation = max(saturation, is_spec.minimum)
        if is_spec.maximum is not None:
            saturation = min(saturation, is_spec.maximum)

        predictions = []
        log_errors = []
        for volts, amps in samples:
            argument = min(volts / (ideality * thermal_voltage), 700.0)
            predicted = saturation * math.expm1(argument)
            predictions.append(predicted)
            log_errors.append(math.log(predicted) - math.log(amps))
        residuals = tuple(predicted - actual for predicted, (_, actual) in zip(predictions, samples))
        relative = tuple(abs(error) / actual for error, (_, actual) in zip(residuals, samples))
        count = len(samples)
        log_rmse = math.sqrt(sum(error * error for error in log_errors) / count)
        mean_squared = sum(error * error for error in residuals) / count
        spread = math.sqrt(sum((error - sum(log_errors) / count) ** 2 for error in log_errors) / max(1, count - 1))
        # These are conservative fit-spread indicators, not claims of a full
        # covariance analysis.
        uncertainties = {
            self.saturation_parameter: saturation * spread,
            self.ideality_parameter: ideality * spread,
        }
        return FitResult(
            fitter_id=self.fitter_id,
            fitter_version=self.version,
            dataset_ids=(dataset.dataset_id,),
            parameter_values={
                self.saturation_parameter: saturation,
                self.ideality_parameter: ideality,
            },
            parameter_uncertainties=uncertainties,
            metrics=ErrorMetrics(
                sample_count=count,
                values={
                    "log_rmse": log_rmse,
                    "rmse_a": math.sqrt(mean_squared),
                    "mae_a": sum(abs(error) for error in residuals) / count,
                    "max_relative_error": max(relative),
                },
            ),
        )


class ModelBuilder:
    """Mutable assembly workspace which emits immutable content-addressed drafts."""

    def __init__(
        self,
        model_id: str,
        title: str,
        family: str,
        summary: str,
        pins: tuple[str, ...],
    ) -> None:
        self.model_id = model_id
        self.title = title
        self.family = family
        self.summary = summary
        self.pins = tuple(pins)
        self._sources: dict[str, SourceArtifact] = {}
        self._parameters: dict[str, ParameterDefinition] = {}
        self._datasets: dict[str, CurveDataset] = {}
        self._fits: list[FitResult] = []
        self._validity: ValidityEnvelope | None = None
        self._black_box: BlackBoxDescriptor | None = None

    def add_source(self, source: SourceArtifact) -> "ModelBuilder":
        if source.source_id in self._sources:
            raise ModelBuilderError(f"Duplicate source: {source.source_id}.")
        self._sources[source.source_id] = source
        return self

    def review_source(self, source_id: str, reviewer: str, notes: str = "") -> "ModelBuilder":
        if not reviewer.strip():
            raise ModelBuilderError("Evidence review requires a named reviewer.")
        try:
            source = self._sources[source_id]
        except KeyError as exc:
            raise ModelBuilderError(f"Unknown source: {source_id}.") from exc
        if source.review_state == "rejected":
            raise ModelBuilderError("Rejected evidence cannot be reviewed without being re-imported.")
        self._sources[source_id] = replace(
            source, review_state="reviewed", reviewed_by=reviewer, review_notes=notes
        )
        return self

    def reject_source(self, source_id: str, notes: str) -> "ModelBuilder":
        try:
            source = self._sources[source_id]
        except KeyError as exc:
            raise ModelBuilderError(f"Unknown source: {source_id}.") from exc
        self._sources[source_id] = replace(
            source, review_state="rejected", reviewed_by="", review_notes=notes
        )
        return self

    def add_parameter(self, parameter: ParameterDefinition) -> "ModelBuilder":
        if parameter.name in self._parameters:
            raise ModelBuilderError(f"Duplicate parameter: {parameter.name}.")
        self._parameters[parameter.name] = parameter
        return self

    def add_dataset(self, dataset: CurveDataset) -> "ModelBuilder":
        if dataset.dataset_id in self._datasets:
            raise ModelBuilderError(f"Duplicate dataset: {dataset.dataset_id}.")
        unknown = set(dataset.source_ids) - set(self._sources)
        if unknown:
            raise ModelBuilderError(f"Dataset references unknown sources: {sorted(unknown)}.")
        self._datasets[dataset.dataset_id] = dataset
        return self

    def set_validity(self, validity: ValidityEnvelope) -> "ModelBuilder":
        self._validity = validity
        return self

    def set_black_box(self, black_box: BlackBoxDescriptor) -> "ModelBuilder":
        if black_box.pins != self.pins:
            raise ModelBuilderError("Black-box pins must match the model pins exactly.")
        self._black_box = black_box
        return self

    def fit(self, dataset_id: str, fitter: ModelFitter) -> FitResult:
        try:
            dataset = self._datasets[dataset_id]
        except KeyError as exc:
            raise ModelBuilderError(f"Unknown dataset: {dataset_id}.") from exc
        result = fitter.fit(dataset, MappingProxyType(dict(self._parameters)))
        unknown = set(result.parameter_values) - set(self._parameters)
        if unknown:
            raise ModelBuilderError(f"Fitter returned undeclared parameters: {sorted(unknown)}.")
        source_ids = tuple(sorted(set(dataset.source_ids)))
        for name, value in result.parameter_values.items():
            definition = self._parameters[name]
            replacement = replace(
                definition,
                value=value,
                uncertainty=result.parameter_uncertainties[name],
                source_ids=tuple(sorted(set(definition.source_ids) | set(source_ids))),
                fitted=True,
            )
            self._parameters[name] = replacement
        self._fits.append(result)
        return result

    def build_draft(self) -> ModelPackage:
        if self._validity is None or self._black_box is None:
            raise ModelBuilderError("A model draft requires a validity envelope and black-box descriptor.")
        provisional = ModelPackage(
            model_id=self.model_id,
            title=self.title,
            family=self.family,
            summary=self.summary,
            pins=self.pins,
            parameters=tuple(self._parameters[name] for name in sorted(self._parameters)),
            sources=tuple(self._sources[name] for name in sorted(self._sources)),
            datasets=tuple(self._datasets[name] for name in sorted(self._datasets)),
            fit_results=tuple(self._fits),
            validity=self._validity,
            black_box=self._black_box,
            qualification=QualificationRecord(),
            content_sha256="0" * 64,
        )
        package = replace(provisional, content_sha256=canonical_digest(provisional.content_dict()))
        if not package.verify_digest():  # defensive contract assertion
            raise ModelBuilderError("Internal error while content-addressing model package.")
        return package


def qualify_model(
    package: ModelPackage,
    reviewer: str,
    policy: QualificationPolicy | None = None,
    *,
    notes: str = "",
) -> ModelPackage:
    """Return a qualified immutable copy or raise without changing the draft."""

    selected = QualificationPolicy() if policy is None else policy
    failures: list[str] = []
    checks: list[str] = []
    if not reviewer.strip():
        failures.append("a named qualification reviewer is required")
    if not package.verify_digest():
        failures.append("content digest mismatch")
    else:
        checks.append("content_digest_verified")

    untrusted = [source.source_id for source in package.sources if not source.trusted_for_qualification]
    if untrusted:
        failures.append(f"unreviewed or rejected evidence: {', '.join(untrusted)}")
    else:
        checks.append("all_evidence_reviewed")
    if any(source.kind == "llm_extraction" for source in package.sources):
        checks.append("llm_drafts_human_reviewed")

    validation = [dataset for dataset in package.datasets if dataset.role in {"validation", "both"}]
    if selected.require_validation_dataset and not validation:
        failures.append("an independent or shared validation dataset is required")
    else:
        checks.append("validation_dataset_present")
    if not package.fit_results:
        failures.append("at least one deterministic fit result is required")
    for fit in package.fit_results:
        if not fit.deterministic:
            failures.append(f"fit {fit.fitter_id} is non-deterministic")
        if fit.metrics.sample_count < selected.minimum_samples:
            failures.append(f"fit {fit.fitter_id} has too few samples")
        for metric, limit in selected.metric_maximums.items():
            actual = fit.metrics.values.get(metric)
            if actual is None:
                failures.append(f"fit {fit.fitter_id} lacks required metric {metric}")
            elif actual > limit:
                failures.append(f"fit {fit.fitter_id} {metric}={actual:g} exceeds {limit:g}")
    if package.fit_results and not any(failure.startswith("fit ") for failure in failures):
        checks.append("fit_metrics_passed")
    if not package.validity.bounds:
        failures.append("validity envelope is empty")
    else:
        checks.append("validity_envelope_declared")
    if failures:
        raise QualificationError("Model qualification failed: " + "; ".join(failures) + ".")
    return replace(
        package,
        qualification=QualificationRecord(
            state="qualified",
            reviewer=reviewer,
            policy_id=selected.policy_id,
            checks=tuple(checks),
            notes=notes,
        ),
    )


def export_archetype(package: ModelPackage) -> ModelLibraryExport:
    """Fail closed unless the exact package content has passed qualification."""

    if package.qualification.state != "qualified":
        raise LibraryExportError("Draft or rejected model packages cannot be exported as runnable archetypes.")
    if not package.verify_digest():
        raise LibraryExportError("Model package content digest does not match its payload.")
    # Re-run the built-in safety floor rather than trusting a caller-created
    # QualificationRecord.  Custom policies may be stricter, never looser than
    # this export gate.
    try:
        qualify_model(
            replace(package, qualification=QualificationRecord()),
            package.qualification.reviewer,
            QualificationPolicy(),
        )
    except QualificationError as exc:
        raise LibraryExportError(f"Model package fails the library export safety floor: {exc}") from exc
    descriptor = ArchetypeDescriptor(
        archetype_id=package.model_id,
        title=package.title,
        family=package.family,
        summary=package.summary,
        status="runnable",
        fidelity="compact",
        pins=package.pins,
        parameters=tuple(
            ParameterSpec(
                name=parameter.name,
                unit=parameter.unit,
                default=parameter.value,
                minimum=parameter.minimum,
                maximum=parameter.maximum,
                description=parameter.description,
            )
            for parameter in package.parameters
        ),
        tags=("model-builder", "qualified"),
        required_capabilities=package.black_box.required_capabilities,
        elaborator=f"model-package:{package.content_sha256}",
        limitations=(f"Valid only within the packaged {package.validity.notes or 'validity envelope'}.",),
        provenance={
            "model_package_contract": package.contract,
            "content_sha256": package.content_sha256,
            "qualification_policy": package.qualification.policy_id,
            "qualified_by": package.qualification.reviewer,
            "source_sha256": {source.source_id: source.sha256 for source in package.sources},
        },
    )
    return ModelLibraryExport(package=package, archetype=descriptor)


__all__ = [
    "LibraryExportError", "ModelBuilder", "ModelBuilderError", "ModelFitter",
    "ModelLibraryExport", "QualificationError", "QualificationPolicy", "ShockleyDiodeFitter",
    "export_archetype", "llm_draft_source", "qualify_model",
]
