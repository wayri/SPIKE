"""Fail-closed public, equal-model cross-engine benchmark contracts.

The protocol passes the exact public deck bytes to a digest-bound adapter and
requires the adapter to attest the digest it executed.  Accuracy evidence is
kept separate from performance eligibility: missing provenance, corpus tiers,
engine runs, timing scopes, memory measurements, or repetitions always blocks
a public performance claim.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Protocol
from urllib.parse import urlparse


PUBLIC_SOURCE_CONTRACT = "spikes/public-benchmark-source/v1"
PUBLIC_CASE_CONTRACT = "spikes/public-benchmark-case/v1"
PUBLIC_MANIFEST_CONTRACT = "spikes/public-benchmark-manifest/v1"
ENGINE_ADAPTER_CONTRACT = "spikes/public-engine-adapter/v1"
ADAPTER_REQUEST_CONTRACT = "spikes/public-benchmark-adapter-request/v1"
ADAPTER_RESULT_CONTRACT = "spikes/public-benchmark-adapter-result/v1"
QUALIFICATION_CONTRACT = "spikes/public-benchmark-qualification/v1"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_LICENSE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+()\- ]{0,127}")
_TIERS = frozenset({"small", "medium", "large"})
_ANALYSES = frozenset({
    "op", "dc", "ac", "tran", "noise", "pz", "sens", "disto", "fourier",
})
_REDUCTIONS = frozenset({"scalar", "final", "minimum", "maximum", "rms", "mean"})


class PublicBenchmarkError(ValueError):
    """The public benchmark contract or evidence is invalid."""


class PublicBenchmarkExecutionError(RuntimeError):
    """A digest-bound adapter failed without producing admissible evidence."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _strict_json_object(payload: bytes) -> dict[str, object]:
    def reject_constant(value: str) -> object:
        raise ValueError(f"non-finite constant {value}")

    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(
        payload.decode("utf-8", errors="strict"), parse_constant=reject_constant,
        object_pairs_hook=reject_duplicates,
    )
    if not isinstance(value, dict):
        raise ValueError("JSON root is not an object")
    return value


def _digest(value: object, name: str) -> str:
    normalized = str(value).lower()
    if _DIGEST.fullmatch(normalized) is None:
        raise PublicBenchmarkError(f"{name} must be a lowercase SHA-256 digest.")
    return normalized


def _identifier(value: object, name: str) -> str:
    normalized = str(value)
    if _IDENTIFIER.fullmatch(normalized) is None:
        raise PublicBenchmarkError(f"{name} is not a bounded identifier.")
    return normalized


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise PublicBenchmarkError(f"{name} must be finite.")
    try:
        normalized = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise PublicBenchmarkError(f"{name} must be finite.") from exc
    if not math.isfinite(normalized):
        raise PublicBenchmarkError(f"{name} must be finite.")
    return normalized


@dataclass(frozen=True, slots=True)
class PublicSource:
    source_id: str
    title: str
    canonical_url: str
    license_spdx: str
    license_url: str
    retrieved_at_utc: str
    artifact_sha256: str
    redistribution_approved: bool
    approval_evidence_sha256: str
    reviewer: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _identifier(self.source_id, "source_id"))
        title = str(self.title).strip()
        if not title or len(title) > 256:
            raise PublicBenchmarkError("source title is empty or too long.")
        object.__setattr__(self, "title", title)
        for field in ("canonical_url", "license_url"):
            value = str(getattr(self, field))
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc or parsed.username:
                raise PublicBenchmarkError(f"{field} must be an absolute HTTPS URL.")
            object.__setattr__(self, field, value)
        license_spdx = str(self.license_spdx)
        if (
            _LICENSE.fullmatch(license_spdx) is None
            or license_spdx.lower() in {"noassertion", "none"}
            or "licenseref-" in license_spdx.lower()
        ):
            raise PublicBenchmarkError("license_spdx must be a reviewed SPDX expression.")
        object.__setattr__(self, "license_spdx", license_spdx)
        retrieved = str(self.retrieved_at_utc)
        if not retrieved.endswith("Z") or "T" not in retrieved or len(retrieved) > 40:
            raise PublicBenchmarkError("retrieved_at_utc must be a bounded UTC timestamp.")
        object.__setattr__(self, "retrieved_at_utc", retrieved)
        object.__setattr__(self, "artifact_sha256", _digest(self.artifact_sha256, "artifact_sha256"))
        object.__setattr__(
            self, "approval_evidence_sha256",
            _digest(self.approval_evidence_sha256, "approval_evidence_sha256"),
        )
        reviewer = str(self.reviewer).strip()
        if not reviewer or len(reviewer) > 128:
            raise PublicBenchmarkError("reviewer is required and must be bounded.")
        object.__setattr__(self, "reviewer", reviewer)
        if self.redistribution_approved is not True:
            raise PublicBenchmarkError("public corpus redistribution approval must be explicit.")

    def to_dict(self) -> dict[str, object]:
        return {"contract": PUBLIC_SOURCE_CONTRACT, **{
            name: getattr(self, name) for name in self.__dataclass_fields__
        }}


@dataclass(frozen=True, slots=True)
class MetricTolerance:
    metric_id: str
    vector: str
    reduction: str
    reference: float
    absolute_tolerance: float
    relative_tolerance: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _identifier(self.metric_id, "metric_id"))
        vector = str(self.vector).strip()
        if not vector or len(vector) > 256 or any(ord(char) < 32 for char in vector):
            raise PublicBenchmarkError("metric vector is empty or invalid.")
        object.__setattr__(self, "vector", vector)
        reduction = str(self.reduction).lower()
        if reduction not in _REDUCTIONS:
            raise PublicBenchmarkError("metric reduction is unsupported.")
        object.__setattr__(self, "reduction", reduction)
        object.__setattr__(self, "reference", _finite(self.reference, "reference"))
        absolute = _finite(self.absolute_tolerance, "absolute_tolerance")
        relative = _finite(self.relative_tolerance, "relative_tolerance")
        if absolute < 0.0 or relative < 0.0 or absolute + relative <= 0.0:
            raise PublicBenchmarkError("metric tolerances must define a positive bound.")
        object.__setattr__(self, "absolute_tolerance", absolute)
        object.__setattr__(self, "relative_tolerance", relative)

    def allowed_error(self) -> float:
        return self.absolute_tolerance + self.relative_tolerance * abs(self.reference)

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class PublicBenchmarkCase:
    case_id: str
    tier: str
    analysis: str
    deck_relative_path: str
    deck_sha256: str
    model_bundle_sha256: str
    source: PublicSource
    metrics: tuple[MetricTolerance, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", _identifier(self.case_id, "case_id"))
        tier = str(self.tier).lower()
        analysis = str(self.analysis).lower()
        if tier not in _TIERS:
            raise PublicBenchmarkError("case tier must be small, medium, or large.")
        if analysis not in _ANALYSES:
            raise PublicBenchmarkError("case analysis is unsupported.")
        object.__setattr__(self, "tier", tier)
        object.__setattr__(self, "analysis", analysis)
        relative = PurePosixPath(str(self.deck_relative_path).replace("\\", "/"))
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise PublicBenchmarkError("deck_relative_path must remain inside the corpus.")
        object.__setattr__(self, "deck_relative_path", relative.as_posix())
        object.__setattr__(self, "deck_sha256", _digest(self.deck_sha256, "deck_sha256"))
        object.__setattr__(self, "model_bundle_sha256", _digest(
            self.model_bundle_sha256, "model_bundle_sha256",
        ))
        metrics = tuple(self.metrics)
        if not metrics or len(metrics) > 64:
            raise PublicBenchmarkError("a case must have 1 through 64 metrics.")
        if len({metric.metric_id for metric in metrics}) != len(metrics):
            raise PublicBenchmarkError("metric IDs must be unique within a case.")
        object.__setattr__(self, "metrics", metrics)

    def verify_deck(self, corpus_root: str | Path) -> Path:
        root = Path(corpus_root).resolve(strict=True)
        path = (root / self.deck_relative_path).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise PublicBenchmarkError("benchmark deck escapes the corpus root.") from exc
        if not path.is_file() or _sha256_file(path) != self.deck_sha256:
            raise PublicBenchmarkError("benchmark deck digest does not match the manifest.")
        if path.stat().st_size > 16 * 1024 * 1024:
            raise PublicBenchmarkError("benchmark deck exceeds the 16 MiB case bound.")
        return path

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": PUBLIC_CASE_CONTRACT, "case_id": self.case_id,
            "tier": self.tier, "analysis": self.analysis,
            "deck_relative_path": self.deck_relative_path,
            "deck_sha256": self.deck_sha256,
            "model_bundle_sha256": self.model_bundle_sha256,
            "source": self.source.to_dict(),
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


@dataclass(frozen=True, slots=True)
class PublicBenchmarkManifest:
    manifest_id: str
    version: str
    required_engines: tuple[str, ...]
    cases: tuple[PublicBenchmarkCase, ...]
    manifest_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "manifest_id", _identifier(self.manifest_id, "manifest_id"))
        version = str(self.version).strip()
        if not version or len(version) > 64:
            raise PublicBenchmarkError("manifest version must be present and bounded.")
        object.__setattr__(self, "version", version)
        engines = tuple(_identifier(item, "engine_id") for item in self.required_engines)
        cases = tuple(self.cases)
        if len(engines) < 2 or len(set(engines)) != len(engines):
            raise PublicBenchmarkError("at least two unique engines are required.")
        if not cases or len(cases) > 512 or len({case.case_id for case in cases}) != len(cases):
            raise PublicBenchmarkError("manifest cases are empty, duplicated, or exceed the bound.")
        object.__setattr__(self, "required_engines", engines)
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "manifest_sha256", _digest(self.manifest_sha256, "manifest_sha256"))
        if self.computed_sha256() != self.manifest_sha256:
            raise PublicBenchmarkError("manifest_sha256 does not match canonical content.")

    def content_dict(self) -> dict[str, object]:
        return {
            "contract": PUBLIC_MANIFEST_CONTRACT, "manifest_id": self.manifest_id,
            "version": self.version, "required_engines": list(self.required_engines),
            "cases": [case.to_dict() for case in self.cases],
        }

    def computed_sha256(self) -> str:
        return _sha256_bytes(_canonical(self.content_dict()))

    @classmethod
    def create(
        cls, *, manifest_id: str, version: str, required_engines: Iterable[str],
        cases: Iterable[PublicBenchmarkCase],
    ) -> "PublicBenchmarkManifest":
        engines = tuple(required_engines)
        configured = tuple(cases)
        content = {
            "contract": PUBLIC_MANIFEST_CONTRACT, "manifest_id": manifest_id,
            "version": version, "required_engines": list(engines),
            "cases": [case.to_dict() for case in configured],
        }
        return cls(
            manifest_id=manifest_id, version=version, required_engines=engines,
            cases=configured, manifest_sha256=_sha256_bytes(_canonical(content)),
        )


@dataclass(frozen=True, slots=True)
class EngineAdapterManifest:
    engine_id: str
    engine_version: str
    executable_name: str
    executable_sha256: str
    arguments: tuple[str, ...]
    adapter_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "engine_id", _identifier(self.engine_id, "engine_id"))
        version = str(self.engine_version).strip()
        if not version or len(version) > 128:
            raise PublicBenchmarkError("engine_version must be present and bounded.")
        object.__setattr__(self, "engine_version", version)
        name = str(self.executable_name)
        if not name or Path(name).name != name or len(name) > 255:
            raise PublicBenchmarkError("adapter executable_name must be one base name.")
        object.__setattr__(self, "executable_name", name)
        object.__setattr__(self, "executable_sha256", _digest(
            self.executable_sha256, "executable_sha256",
        ))
        arguments = tuple(str(value) for value in self.arguments)
        if len(arguments) > 32 or any(len(value) > 4096 or "\x00" in value for value in arguments):
            raise PublicBenchmarkError("adapter arguments exceed the fixed bounds.")
        object.__setattr__(self, "arguments", arguments)
        object.__setattr__(self, "adapter_sha256", _digest(self.adapter_sha256, "adapter_sha256"))
        if _sha256_bytes(_canonical(self.content_dict())) != self.adapter_sha256:
            raise PublicBenchmarkError("adapter_sha256 does not match canonical content.")

    def content_dict(self) -> dict[str, object]:
        return {
            "contract": ENGINE_ADAPTER_CONTRACT, "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "executable_name": self.executable_name,
            "executable_sha256": self.executable_sha256,
            "arguments": list(self.arguments),
        }

    @classmethod
    def create(
        cls, *, engine_id: str, engine_version: str, executable: str | Path,
        arguments: Iterable[str] = (),
    ) -> "EngineAdapterManifest":
        path = Path(executable).resolve(strict=True)
        configured = tuple(arguments)
        content = {
            "contract": ENGINE_ADAPTER_CONTRACT, "engine_id": engine_id,
            "engine_version": engine_version, "executable_name": path.name,
            "executable_sha256": _sha256_file(path), "arguments": list(configured),
        }
        return cls(
            engine_id=engine_id, engine_version=engine_version,
            executable_name=path.name, executable_sha256=str(content["executable_sha256"]),
            arguments=configured, adapter_sha256=_sha256_bytes(_canonical(content)),
        )


@dataclass(frozen=True, slots=True)
class EngineCaseEvidence:
    engine_id: str
    case_id: str
    manifest_sha256: str
    deck_sha256: str
    model_bundle_sha256: str
    host_fingerprint: str
    timing_scope: str
    observed: Mapping[str, float]
    cold_elapsed_ns: tuple[int, ...]
    warm_elapsed_ns: tuple[int, ...]
    peak_memory_bytes: int | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "engine_id", _identifier(self.engine_id, "engine_id"))
        object.__setattr__(self, "case_id", _identifier(self.case_id, "case_id"))
        for field in ("manifest_sha256", "deck_sha256", "model_bundle_sha256"):
            object.__setattr__(self, field, _digest(getattr(self, field), field))
        object.__setattr__(self, "host_fingerprint", _digest(
            self.host_fingerprint, "host_fingerprint",
        ))
        scope = str(self.timing_scope)
        if scope not in {"process_inclusive", "resident_solve_only"}:
            raise PublicBenchmarkError("timing_scope is unsupported.")
        object.__setattr__(self, "timing_scope", scope)
        normalized = {
            _identifier(key, "metric_id"): _finite(value, f"observed.{key}")
            for key, value in self.observed.items()
        }
        object.__setattr__(self, "observed", normalized)
        for field in ("cold_elapsed_ns", "warm_elapsed_ns"):
            values = tuple(getattr(self, field))
            if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in values):
                raise PublicBenchmarkError(f"{field} values must be positive integers.")
            object.__setattr__(self, field, values)
        if self.peak_memory_bytes is not None and (
            isinstance(self.peak_memory_bytes, bool)
            or not isinstance(self.peak_memory_bytes, int)
            or self.peak_memory_bytes <= 0
        ):
            raise PublicBenchmarkError("peak_memory_bytes must be a positive integer.")


class BenchmarkAdapter(Protocol):
    manifest: EngineAdapterManifest

    def run_case(
        self, manifest: PublicBenchmarkManifest, case: PublicBenchmarkCase,
        deck: bytes,
    ) -> EngineCaseEvidence: ...


class JsonProcessBenchmarkAdapter:
    """Execute a trusted, digest-bound adapter using the strict JSON protocol."""

    def __init__(
        self, manifest: EngineAdapterManifest, executable: str | Path,
        *, timeout_s: float = 120.0, max_output_bytes: int = 1024 * 1024,
    ):
        self.manifest = manifest
        self.executable = Path(executable).resolve(strict=True)
        self.timeout_s = _finite(timeout_s, "timeout_s")
        self.max_output_bytes = int(max_output_bytes)
        if not 0.0 < self.timeout_s <= 3600.0 or not 1024 <= self.max_output_bytes <= 64 * 1024 * 1024:
            raise PublicBenchmarkError("adapter runtime limits are invalid.")

    def run_case(
        self, manifest: PublicBenchmarkManifest, case: PublicBenchmarkCase,
        deck: bytes,
    ) -> EngineCaseEvidence:
        adapter = self.manifest
        if self.executable.name != adapter.executable_name or _sha256_file(self.executable) != adapter.executable_sha256:
            raise PublicBenchmarkExecutionError("adapter_identity_mismatch")
        if _sha256_bytes(deck) != case.deck_sha256 or len(deck) > 16 * 1024 * 1024:
            raise PublicBenchmarkExecutionError("deck_identity_mismatch")
        request = {
            "contract": ADAPTER_REQUEST_CONTRACT,
            "benchmark_manifest_sha256": manifest.manifest_sha256,
            "engine_id": adapter.engine_id,
            "case": case.to_dict(),
            "deck_base64": base64.b64encode(deck).decode("ascii"),
        }
        environment = {"SPIKES_BENCHMARK_PROTOCOL": ADAPTER_REQUEST_CONTRACT}
        for key in ("SystemRoot", "WINDIR"):
            if key in os.environ:
                environment[key] = os.environ[key]
        with tempfile.TemporaryDirectory(prefix="spikes-public-benchmark-") as directory:
            try:
                completed = subprocess.run(
                    [str(self.executable), *adapter.arguments],
                    input=_canonical(request) + b"\n", stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, cwd=directory, env=environment,
                    timeout=self.timeout_s, check=False, shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise PublicBenchmarkExecutionError("adapter_process_failed") from exc
        if len(completed.stdout) + len(completed.stderr) > self.max_output_bytes:
            raise PublicBenchmarkExecutionError("adapter_output_limit_exceeded")
        if completed.returncode != 0:
            raise PublicBenchmarkExecutionError("adapter_process_failed")
        try:
            value = _strict_json_object(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise PublicBenchmarkExecutionError("adapter_result_invalid") from exc
        expected_keys = {
            "contract", "engine_id", "case_id", "benchmark_manifest_sha256",
            "executed_deck_sha256", "model_bundle_sha256", "host_fingerprint",
            "timing_scope", "observed", "cold_elapsed_ns", "warm_elapsed_ns",
            "peak_memory_bytes",
        }
        if set(value) != expected_keys or value.get("contract") != ADAPTER_RESULT_CONTRACT:
            raise PublicBenchmarkExecutionError("adapter_result_invalid")
        try:
            evidence = EngineCaseEvidence(
                engine_id=str(value["engine_id"]), case_id=str(value["case_id"]),
                manifest_sha256=str(value["benchmark_manifest_sha256"]),
                deck_sha256=str(value["executed_deck_sha256"]),
                model_bundle_sha256=str(value["model_bundle_sha256"]),
                host_fingerprint=str(value["host_fingerprint"]),
                timing_scope=str(value["timing_scope"]), observed=value["observed"],
                cold_elapsed_ns=tuple(value["cold_elapsed_ns"]),
                warm_elapsed_ns=tuple(value["warm_elapsed_ns"]),
                peak_memory_bytes=value.get("peak_memory_bytes"),
            )
        except (KeyError, TypeError, PublicBenchmarkError) as exc:
            raise PublicBenchmarkExecutionError("adapter_result_invalid") from exc
        if (
            evidence.engine_id != adapter.engine_id or evidence.case_id != case.case_id
            or evidence.manifest_sha256 != manifest.manifest_sha256
            or evidence.deck_sha256 != case.deck_sha256
            or evidence.model_bundle_sha256 != case.model_bundle_sha256
        ):
            raise PublicBenchmarkExecutionError("adapter_attestation_mismatch")
        return evidence


def qualify_public_benchmark(
    manifest: PublicBenchmarkManifest, evidence: Iterable[EngineCaseEvidence],
    *, claimant_engine_id: str = "spikes",
) -> dict[str, object]:
    """Derive accuracy and performance eligibility; no input can assert status."""

    claimant = _identifier(claimant_engine_id, "claimant_engine_id")
    records = tuple(evidence)
    indexed: dict[tuple[str, str], EngineCaseEvidence] = {}
    blockers: list[str] = []
    for record in records:
        key = (record.engine_id, record.case_id)
        if key in indexed:
            raise PublicBenchmarkError("duplicate engine/case evidence.")
        indexed[key] = record
    if set(manifest.required_engines) and claimant not in manifest.required_engines:
        blockers.append("claimant_not_in_required_engines")
    if {case.tier for case in manifest.cases} != _TIERS:
        blockers.append("public_corpus_missing_small_medium_or_large_tier")
    if len({case.source.source_id for case in manifest.cases}) < 1:
        blockers.append("public_source_provenance_missing")

    case_results: list[dict[str, object]] = []
    for engine_id in manifest.required_engines:
        for case in manifest.cases:
            record = indexed.get((engine_id, case.case_id))
            if record is None:
                blockers.append(f"missing_evidence:{engine_id}:{case.case_id}")
                continue
            if record.manifest_sha256 != manifest.manifest_sha256:
                blockers.append(f"manifest_mismatch:{engine_id}:{case.case_id}")
            if record.deck_sha256 != case.deck_sha256:
                blockers.append(f"deck_mismatch:{engine_id}:{case.case_id}")
            if record.model_bundle_sha256 != case.model_bundle_sha256:
                blockers.append(f"model_bundle_mismatch:{engine_id}:{case.case_id}")
            if set(record.observed) != {metric.metric_id for metric in case.metrics}:
                blockers.append(f"metric_set_mismatch:{engine_id}:{case.case_id}")
                passed = False
            else:
                passed = all(
                    abs(record.observed[metric.metric_id] - metric.reference) <= metric.allowed_error()
                    for metric in case.metrics
                )
            if not passed:
                blockers.append(f"accuracy_failed:{engine_id}:{case.case_id}")
            if len(record.cold_elapsed_ns) < 5 or len(record.warm_elapsed_ns) < 5:
                blockers.append(f"insufficient_repetitions:{engine_id}:{case.case_id}")
            if record.peak_memory_bytes is None:
                blockers.append(f"peak_memory_missing:{engine_id}:{case.case_id}")
            case_results.append({
                "engine_id": engine_id, "case_id": case.case_id,
                "accuracy_passed": passed,
                "cold_median_ns": statistics.median(record.cold_elapsed_ns) if record.cold_elapsed_ns else None,
                "warm_median_ns": statistics.median(record.warm_elapsed_ns) if record.warm_elapsed_ns else None,
                "peak_memory_bytes": record.peak_memory_bytes,
            })

    host_fingerprints = {record.host_fingerprint for record in records}
    timing_scopes = {record.timing_scope for record in records}
    if len(host_fingerprints) != 1:
        blockers.append("runs_not_on_one_pinned_host")
    if len(timing_scopes) != 1:
        blockers.append("timing_scopes_not_equal")

    # A speed/memory claim requires the claimant to meet or beat every comparator
    # for every case in cold, warm, and peak-memory observations.
    for case in manifest.cases:
        claimant_record = indexed.get((claimant, case.case_id))
        if claimant_record is None:
            continue
        for competitor in manifest.required_engines:
            if competitor == claimant:
                continue
            other = indexed.get((competitor, case.case_id))
            if other is None or not claimant_record.cold_elapsed_ns or not claimant_record.warm_elapsed_ns:
                continue
            if not other.cold_elapsed_ns or not other.warm_elapsed_ns:
                continue
            if statistics.median(claimant_record.cold_elapsed_ns) > statistics.median(other.cold_elapsed_ns):
                blockers.append(f"claimant_not_faster_cold:{case.case_id}:{competitor}")
            if statistics.median(claimant_record.warm_elapsed_ns) > statistics.median(other.warm_elapsed_ns):
                blockers.append(f"claimant_not_faster_warm:{case.case_id}:{competitor}")
            if (
                claimant_record.peak_memory_bytes is not None and other.peak_memory_bytes is not None
                and claimant_record.peak_memory_bytes > other.peak_memory_bytes
            ):
                blockers.append(f"claimant_uses_more_memory:{case.case_id}:{competitor}")

    blockers = sorted(set(blockers))
    performance_eligible = not blockers
    return {
        "contract": QUALIFICATION_CONTRACT,
        "benchmark_manifest_sha256": manifest.manifest_sha256,
        "claimant_engine_id": claimant,
        "accuracy_passed": not any(item.startswith("accuracy_failed:") for item in blockers)
        and not any(item.startswith("missing_evidence:") for item in blockers),
        "performance_claim_eligible": performance_eligible,
        "status": "passed" if performance_eligible else "blocked",
        "blockers": blockers,
        "case_results": case_results,
        "policy": {
            "equal_deck_bytes_required": True,
            "equal_model_bundle_required": True,
            "minimum_cold_repetitions": 5,
            "minimum_warm_repetitions": 5,
            "peak_memory_required": True,
            "required_corpus_tiers": sorted(_TIERS),
            "claim_is_derived_not_asserted": True,
        },
    }


__all__ = [
    "ADAPTER_REQUEST_CONTRACT", "ADAPTER_RESULT_CONTRACT", "BenchmarkAdapter",
    "EngineAdapterManifest", "EngineCaseEvidence", "JsonProcessBenchmarkAdapter",
    "MetricTolerance", "PUBLIC_MANIFEST_CONTRACT", "PublicBenchmarkCase",
    "PublicBenchmarkError", "PublicBenchmarkExecutionError", "PublicBenchmarkManifest",
    "PublicSource", "QUALIFICATION_CONTRACT", "qualify_public_benchmark",
]
