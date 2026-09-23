"""Fail-closed physical hard-real-time/HIL qualification evidence gate.

The gate deliberately does not manufacture latency evidence.  It accepts only
a hash-bound raw hardware trace plus target, firmware, calibration, clock and
fault-injection records.  A simulator-only run can never satisfy the contract.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


HIL_EVIDENCE_CONTRACT = "spikes/physical-hil-evidence/v1"
HIL_GATE_CONTRACT = "spikes/physical-hil-gate/v1"
_SHA256 = set("0123456789abcdef")


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _valid_digest(value: Any) -> bool:
    text = str(value).lower()
    return len(text) == 64 and set(text) <= _SHA256


@dataclass(frozen=True, slots=True)
class HilRequirements:
    period_ns: int
    maximum_response_latency_ns: int
    maximum_absolute_jitter_ns: int
    minimum_cycles: int = 100_000
    minimum_duration_s: float = 60.0
    required_fault_tests: tuple[str, ...] = (
        "watchdog_timeout", "transport_disconnect", "stale_input",
        "output_safe_state", "emergency_stop",
    )

    def __post_init__(self) -> None:
        integers = (
            self.period_ns, self.maximum_response_latency_ns,
            self.maximum_absolute_jitter_ns, self.minimum_cycles,
        )
        if any(isinstance(value, bool) or int(value) != value or value <= 0 for value in integers):
            raise ValueError("HIL timing requirements must be positive integers.")
        if not math.isfinite(self.minimum_duration_s) or self.minimum_duration_s <= 0:
            raise ValueError("HIL minimum duration must be finite and positive.")
        if not self.required_fault_tests or len(set(self.required_fault_tests)) != len(self.required_fault_tests):
            raise ValueError("HIL fault-test names must be nonempty and unique.")


def evaluate_physical_hil_evidence(
    evidence: Mapping[str, Any], requirements: HilRequirements, *,
    evidence_root: str | Path,
) -> dict[str, Any]:
    """Validate one physical-run evidence package without trusting its status field."""

    root = Path(evidence_root).resolve()
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "status": "passed" if passed else "blocked", "detail": detail})

    check("contract", evidence.get("contract") == HIL_EVIDENCE_CONTRACT,
          f"expected {HIL_EVIDENCE_CONTRACT}")
    check("physical_execution", evidence.get("execution_mode") == "physical_closed_loop" and evidence.get("synthetic") is False,
          "requires an explicitly non-synthetic physical_closed_loop run")

    target = evidence.get("target", {})
    target_ok = isinstance(target, Mapping) and all(str(target.get(key, "")).strip() for key in (
        "manufacturer", "model", "hardware_serial", "firmware_version",
        "firmware_sha256", "transport", "io_fixture_serial",
    )) and _valid_digest(target.get("firmware_sha256"))
    check("target_identity", target_ok, "manufacturer/model/serial/firmware/fixture identity must be complete and hash-bound")

    host = evidence.get("host", {})
    host_ok = isinstance(host, Mapping) and all(str(host.get(key, "")).strip() for key in (
        "machine_id", "os_build", "cpu", "solver_artifact_sha256",
    )) and _valid_digest(host.get("solver_artifact_sha256"))
    check("host_identity", host_ok, "host and exact solver artifact identity are required")

    calibration = evidence.get("calibration", {})
    calibration_ok = isinstance(calibration, Mapping) and all(str(calibration.get(key, "")).strip() for key in (
        "certificate_id", "laboratory", "valid_from", "valid_until", "artifact", "sha256",
    )) and _valid_digest(calibration.get("sha256"))
    if calibration_ok:
        calibration_path = (root / str(calibration["artifact"])).resolve()
        calibration_ok = root in calibration_path.parents and calibration_path.is_file() and _digest(calibration_path) == str(calibration["sha256"]).lower()
    check("calibration", calibration_ok, "a present, in-root, digest-matched calibration certificate is required")

    trace = evidence.get("raw_trace", {})
    trace_ok = isinstance(trace, Mapping) and all(str(trace.get(key, "")).strip() for key in (
        "artifact", "sha256", "format",
    )) and _valid_digest(trace.get("sha256"))
    if trace_ok:
        trace_path = (root / str(trace["artifact"])).resolve()
        trace_ok = root in trace_path.parents and trace_path.is_file() and _digest(trace_path) == str(trace["sha256"]).lower()
    check("raw_trace", trace_ok, "raw host/target timestamps and physical I/O sequence data must be retained and digest-bound")

    timing = evidence.get("timing", {})
    numeric_timing = isinstance(timing, Mapping) and all(
        isinstance(timing.get(key), (int, float)) and not isinstance(timing.get(key), bool)
        and math.isfinite(float(timing[key])) for key in (
            "period_ns", "duration_s", "cycles", "deadline_misses",
            "response_latency_p99999_ns", "maximum_absolute_jitter_ns",
            "clock_cross_timestamp_max_error_ns",
        )
    )
    timing_ok = numeric_timing and int(timing["period_ns"]) == requirements.period_ns \
        and int(timing["cycles"]) >= requirements.minimum_cycles \
        and float(timing["duration_s"]) >= requirements.minimum_duration_s \
        and int(timing["deadline_misses"]) == 0 \
        and float(timing["response_latency_p99999_ns"]) <= requirements.maximum_response_latency_ns \
        and float(timing["maximum_absolute_jitter_ns"]) <= requirements.maximum_absolute_jitter_ns \
        and float(timing["clock_cross_timestamp_max_error_ns"]) <= requirements.maximum_absolute_jitter_ns
    check("hard_realtime_timing", timing_ok, "period, duration, cycle count, zero misses, p99.999 response, jitter and cross-clock error must meet the declared limits")

    fault_records = evidence.get("fault_tests", ())
    by_name = {
        str(item.get("name")): item for item in fault_records
        if isinstance(item, Mapping)
    } if isinstance(fault_records, Sequence) and not isinstance(fault_records, (str, bytes)) else {}
    fault_ok = all(
        name in by_name and by_name[name].get("physical_injection") is True
        and by_name[name].get("safe_state_observed") is True
        and str(by_name[name].get("trace_id", "")).strip()
        for name in requirements.required_fault_tests
    )
    check("fault_injection", fault_ok, "every required fault must be physically injected, traced and observed in a safe state")

    attestation = evidence.get("attestation", {})
    attestation_ok = isinstance(attestation, Mapping) and attestation.get("signature_verification") == "valid" \
        and all(str(attestation.get(key, "")).strip() for key in (
            "signer", "certificate_thumbprint", "signed_manifest_sha256", "verification_tool",
        )) and _valid_digest(attestation.get("signed_manifest_sha256"))
    check("independent_attestation", attestation_ok, "a separately verified signed manifest is required; an embedded self-assertion is insufficient")

    passed = all(item["status"] == "passed" for item in checks)
    return {
        "contract": HIL_GATE_CONTRACT,
        "status": "passed" if passed else "blocked",
        "certification_eligible": passed,
        "requirements": {
            "period_ns": requirements.period_ns,
            "maximum_response_latency_ns": requirements.maximum_response_latency_ns,
            "maximum_absolute_jitter_ns": requirements.maximum_absolute_jitter_ns,
            "minimum_cycles": requirements.minimum_cycles,
            "minimum_duration_s": requirements.minimum_duration_s,
            "required_fault_tests": list(requirements.required_fault_tests),
        },
        "checks": checks,
        "limitations": [] if passed else [
            "Software tests, simulated loopback, and self-authored timing summaries cannot satisfy this physical gate.",
            "A passing result is qualification evidence for the named host/target/firmware/fixture only, not universal product certification.",
        ],
    }


__all__ = [
    "HIL_EVIDENCE_CONTRACT", "HIL_GATE_CONTRACT", "HilRequirements",
    "evaluate_physical_hil_evidence",
]
