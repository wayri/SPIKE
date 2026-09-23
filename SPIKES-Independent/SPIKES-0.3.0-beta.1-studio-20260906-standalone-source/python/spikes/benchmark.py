"""Accuracy-qualified, reproducible micro-benchmarks for SPIKES.

The harness deliberately reports measurements instead of competitive claims.
An engine receives a speed score only after every measured repeat satisfies the
case's independent analytical error gate.
"""

from __future__ import annotations

import json
import hashlib
import math
import statistics
import subprocess
import time
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Protocol, Sequence

from .contracts import ProbeDescriptor
from .netlist import parse_netlist
from .runner import run_project


CASE_CONTRACT = "spikes/benchmark-case/v1"
OBSERVATION_CONTRACT = "spikes/benchmark-observation/v1"
REQUEST_CONTRACT = "spikes/benchmark-request/v1"
RESULT_CONTRACT = "spikes/benchmark-result/v1"
REPORT_CONTRACT = "spikes/benchmark-report/v1"

MAX_CASES = 128
MAX_WARMUPS = 20
MAX_REPETITIONS = 100
MAX_COMMAND_ARGUMENTS = 128
MAX_COMMAND_TEXT_BYTES = 32 * 1024
MAX_EXTERNAL_OUTPUT_BYTES = 1024 * 1024
MAX_EXTERNAL_TIMEOUT_S = 3600.0


class BenchmarkExecutionError(RuntimeError):
    """An adapter could not produce a trustworthy observation."""


def _finite(value: Any, label: str, *, nonnegative: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or (nonnegative and number < 0.0):
        raise ValueError(f"{label} must be finite{' and nonnegative' if nonnegative else ''}.")
    return number


def _bounded_count(value: Any, label: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise ValueError(f"{label} must be an integer from 0 through {maximum}.")
    return value


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One scalar analytical fixture with explicit accuracy and timing policy."""

    case_id: str
    title: str
    netlist: str
    probe: str
    expected: float
    unit: str
    absolute_tolerance: float = 1e-12
    relative_tolerance: float = 1e-10
    warmups: int = 2
    repetitions: int = 7
    contract: str = CASE_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != CASE_CONTRACT:
            raise ValueError(f"Expected benchmark case contract {CASE_CONTRACT}.")
        if not self.case_id or len(self.case_id) > 128 or not all(ch.isalnum() or ch in "._-" for ch in self.case_id):
            raise ValueError("case_id must be a bounded portable identifier.")
        if not self.title or len(self.title) > 256:
            raise ValueError("title must contain 1 to 256 characters.")
        if not self.netlist or len(self.netlist.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("netlist is empty or exceeds the 2 MiB benchmark bound.")
        ProbeDescriptor.parse(self.probe)
        object.__setattr__(self, "expected", _finite(self.expected, "expected"))
        object.__setattr__(self, "absolute_tolerance", _finite(self.absolute_tolerance, "absolute_tolerance", nonnegative=True))
        object.__setattr__(self, "relative_tolerance", _finite(self.relative_tolerance, "relative_tolerance", nonnegative=True))
        _bounded_count(self.warmups, "warmups", MAX_WARMUPS)
        repetitions = _bounded_count(self.repetitions, "repetitions", MAX_REPETITIONS)
        if repetitions < 1:
            raise ValueError("repetitions must be at least one.")

    @property
    def error_limit(self) -> float:
        return self.absolute_tolerance + self.relative_tolerance * abs(self.expected)

    def to_dict(self, *, include_netlist: bool = False) -> dict[str, Any]:
        payload = {
            "contract": self.contract,
            "case_id": self.case_id,
            "title": self.title,
            "probe": self.probe,
            "expected": self.expected,
            "unit": self.unit,
            "absolute_tolerance": self.absolute_tolerance,
            "relative_tolerance": self.relative_tolerance,
            "warmups": self.warmups,
            "repetitions": self.repetitions,
            "netlist_sha256": hashlib.sha256(self.netlist.encode("utf-8")).hexdigest(),
        }
        if include_netlist:
            payload["netlist"] = self.netlist
        return payload


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    value: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    contract: str = OBSERVATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != OBSERVATION_CONTRACT:
            raise BenchmarkExecutionError(f"Expected observation contract {OBSERVATION_CONTRACT}.")
        object.__setattr__(self, "value", _finite(self.value, "observation value"))


class BenchmarkAdapter(Protocol):
    """Minimal adapter boundary; implementations execute exactly one case."""

    engine_id: str
    timing_scope: str

    def observe(self, case: BenchmarkCase) -> BenchmarkObservation: ...


class NativeDcAdapter:
    """Execute analytical DC cases through the current SPIKES public runner."""

    engine_id = "spikes.native-linear"
    timing_scope = "in_process_parse_and_solve"

    def observe(self, case: BenchmarkCase) -> BenchmarkObservation:
        probe = ProbeDescriptor.parse(case.probe)
        result = run_project(parse_netlist(case.netlist, source_name=case.case_id, probes=(probe,))).to_dict()
        if result.get("status") != "completed":
            raise BenchmarkExecutionError(f"SPIKES did not complete {case.case_id}: {result.get('issues', [])}")
        record = (result.get("probes") or {}).get(probe.name)
        if not isinstance(record, Mapping) or "value" not in record:
            raise BenchmarkExecutionError(f"SPIKES omitted probe {probe.name} for {case.case_id}.")
        return BenchmarkObservation(
            value=record["value"],
            diagnostics={"model_status": result.get("model_status", "unknown")},
        )


@dataclass(frozen=True, slots=True)
class ExternalJsonCommandAdapter:
    """Run an explicitly supplied JSON wrapper command without a shell.

    The wrapper reads ``spikes/benchmark-request/v1`` JSON from stdin and must
    emit one ``spikes/benchmark-observation/v1`` object on stdout. Process
    startup is intentionally included in this adapter's timing scope.
    """

    engine_id: str
    argv: tuple[str, ...]
    timeout_s: float = 30.0
    timing_scope: str = "process_per_repeat_including_startup"

    def __post_init__(self) -> None:
        if not self.engine_id or len(self.engine_id) > 128:
            raise ValueError("external engine_id must contain 1 to 128 characters.")
        if not self.argv or len(self.argv) > MAX_COMMAND_ARGUMENTS:
            raise ValueError(f"external argv must contain 1 to {MAX_COMMAND_ARGUMENTS} entries.")
        if any(not isinstance(item, str) or not item or "\0" in item for item in self.argv):
            raise ValueError("external argv entries must be nonempty strings without NUL bytes.")
        if sum(len(item.encode("utf-8")) for item in self.argv) > MAX_COMMAND_TEXT_BYTES:
            raise ValueError("external argv exceeds the command text bound.")
        timeout = _finite(self.timeout_s, "timeout_s")
        if not 0.0 < timeout <= MAX_EXTERNAL_TIMEOUT_S:
            raise ValueError(f"timeout_s must be greater than zero and at most {MAX_EXTERNAL_TIMEOUT_S}.")
        object.__setattr__(self, "timeout_s", timeout)

    def observe(self, case: BenchmarkCase) -> BenchmarkObservation:
        request = json.dumps({
            "contract": REQUEST_CONTRACT,
            "case_id": case.case_id,
            "netlist": case.netlist,
            "probe": case.probe,
        }, sort_keys=True, allow_nan=False)
        try:
            completed = subprocess.run(
                list(self.argv),
                input=request,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=self.timeout_s,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BenchmarkExecutionError(
                f"External adapter {self.engine_id} exceeded its {self.timeout_s:g} s timeout."
            ) from exc
        except (OSError, UnicodeError) as exc:
            raise BenchmarkExecutionError(f"External adapter {self.engine_id} could not run: {exc}") from exc
        output_bytes = len(completed.stdout.encode("utf-8")) + len(completed.stderr.encode("utf-8"))
        if output_bytes > MAX_EXTERNAL_OUTPUT_BYTES:
            raise BenchmarkExecutionError("External adapter output exceeds the 1 MiB bound.")
        if completed.returncode != 0:
            detail = completed.stderr.strip()[:4096]
            raise BenchmarkExecutionError(
                f"External adapter {self.engine_id} exited with {completed.returncode}: {detail}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise BenchmarkExecutionError("External adapter did not emit one JSON observation.") from exc
        if not isinstance(payload, Mapping) or payload.get("contract") != OBSERVATION_CONTRACT:
            raise BenchmarkExecutionError(f"External adapter must emit {OBSERVATION_CONTRACT}.")
        if payload.get("case_id") != case.case_id:
            raise BenchmarkExecutionError("External adapter observation case_id does not match the request.")
        diagnostics = payload.get("diagnostics", {})
        if not isinstance(diagnostics, Mapping):
            raise BenchmarkExecutionError("External adapter diagnostics must be an object.")
        return BenchmarkObservation(value=payload.get("value"), diagnostics=dict(diagnostics))


def analytical_dc_cases(*, warmups: int = 2, repetitions: int = 7) -> tuple[BenchmarkCase, ...]:
    """Return stable closed-form fixtures; no competitor installation is needed."""

    return (
        BenchmarkCase(
            case_id="dc.divider.equal",
            title="Equal-resistance voltage divider",
            netlist="Voltage divider\nV1 in 0 10\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n",
            probe="V(out)", expected=5.0, unit="V", warmups=warmups, repetitions=repetitions,
        ),
        BenchmarkCase(
            case_id="dc.current_source.load",
            title="Current source into grounded resistor",
            netlist="Current-source load\nI1 0 out 2m\nR1 out 0 1k\n.op\n.end\n",
            probe="V(out)", expected=2.0, unit="V", warmups=warmups, repetitions=repetitions,
        ),
        BenchmarkCase(
            case_id="dc.divider.unequal",
            title="Unequal-resistance voltage divider current",
            netlist="Unequal divider\nV1 in 0 12\nR1 in out 2k\nR2 out 0 1k\n.op\n.end\n",
            probe="I(R1)", expected=0.004, unit="A", warmups=warmups, repetitions=repetitions,
        ),
    )


def _failed_result(case: BenchmarkCase, adapter: BenchmarkAdapter, issue: str) -> dict[str, Any]:
    return {
        "contract": RESULT_CONTRACT,
        "case": case.to_dict(),
        "engine_id": adapter.engine_id,
        "timing_scope": adapter.timing_scope,
        "status": "failed",
        "accuracy_passed": False,
        "speed_eligible": False,
        "speed_score_runs_per_s": None,
        "observed": None,
        "absolute_error_max": None,
        "error_limit": case.error_limit,
        "timing_ns": [],
        "median_elapsed_ns": None,
        "issues": [{"code": "SPIKES_BENCHMARK_EXECUTION_FAILED", "message": issue[:4096]}],
    }


def run_benchmark_case(case: BenchmarkCase, adapter: BenchmarkAdapter) -> dict[str, Any]:
    """Warm, repeat, qualify accuracy, then and only then calculate speed."""

    try:
        for _ in range(case.warmups):
            adapter.observe(case)
        values: list[float] = []
        timings: list[int] = []
        for _ in range(case.repetitions):
            started = time.perf_counter_ns()
            observation = adapter.observe(case)
            elapsed = time.perf_counter_ns() - started
            if elapsed <= 0:
                raise BenchmarkExecutionError("The monotonic timer returned a nonpositive duration.")
            values.append(observation.value)
            timings.append(elapsed)
    except (BenchmarkExecutionError, OSError, ValueError, KeyError) as exc:
        return _failed_result(case, adapter, str(exc))

    errors = [abs(value - case.expected) for value in values]
    accuracy_passed = all(error <= case.error_limit for error in errors)
    median_elapsed = int(statistics.median(timings))
    speed_score = 1e9 / median_elapsed if accuracy_passed else None
    issues = [] if accuracy_passed else [{
        "code": "SPIKES_BENCHMARK_ACCURACY_GATE_FAILED",
        "message": (
            f"Maximum absolute error {max(errors):.12g} exceeds the "
            f"analytical limit {case.error_limit:.12g}; speed is not scored."
        ),
    }]
    return {
        "contract": RESULT_CONTRACT,
        "case": case.to_dict(),
        "engine_id": adapter.engine_id,
        "timing_scope": adapter.timing_scope,
        "status": "passed" if accuracy_passed else "failed",
        "accuracy_passed": accuracy_passed,
        "speed_eligible": accuracy_passed,
        "speed_score_runs_per_s": speed_score,
        "observed": {
            "minimum": min(values),
            "median": statistics.median(values),
            "maximum": max(values),
        },
        "absolute_error_max": max(errors),
        "error_limit": case.error_limit,
        "timing_ns": timings,
        "median_elapsed_ns": median_elapsed,
        "issues": issues,
    }


def run_benchmark_suite(
    adapter: BenchmarkAdapter | None = None,
    cases: Sequence[BenchmarkCase] | None = None,
    *,
    warmups: int | None = None,
    repetitions: int | None = None,
) -> dict[str, Any]:
    """Run a bounded corpus and return a versioned, claim-free report."""

    selected_adapter = adapter or NativeDcAdapter()
    selected_cases = tuple(cases or analytical_dc_cases())
    if not selected_cases or len(selected_cases) > MAX_CASES:
        raise ValueError(f"benchmark suite must contain 1 to {MAX_CASES} cases.")
    if len({case.case_id for case in selected_cases}) != len(selected_cases):
        raise ValueError("benchmark case IDs must be unique.")
    if warmups is not None:
        _bounded_count(warmups, "warmups", MAX_WARMUPS)
    if repetitions is not None:
        if _bounded_count(repetitions, "repetitions", MAX_REPETITIONS) < 1:
            raise ValueError("repetitions must be at least one.")
    configured = tuple(
        replace(
            case,
            warmups=case.warmups if warmups is None else warmups,
            repetitions=case.repetitions if repetitions is None else repetitions,
        )
        for case in selected_cases
    )
    results = [run_benchmark_case(case, selected_adapter) for case in configured]
    passed = sum(result["status"] == "passed" for result in results)
    return {
        "contract": REPORT_CONTRACT,
        "status": "passed" if passed == len(results) else "failed",
        "engine_id": selected_adapter.engine_id,
        "timing_scope": selected_adapter.timing_scope,
        "summary": {
            "total": len(results),
            "accuracy_passed": passed,
            "failed": len(results) - passed,
            "speed_scored": sum(result["speed_eligible"] for result in results),
        },
        "results": results,
        "claims": [],
        "limitations": [
            "Timing values are valid only for the reported engine, machine, timing scope, and workload.",
            "No competitive superiority is inferred or claimed by this harness.",
            "Process-per-repeat adapters include startup overhead and must not be compared to another timing scope.",
        ],
    }


__all__ = [
    "BenchmarkAdapter",
    "BenchmarkCase",
    "BenchmarkExecutionError",
    "BenchmarkObservation",
    "ExternalJsonCommandAdapter",
    "NativeDcAdapter",
    "analytical_dc_cases",
    "run_benchmark_case",
    "run_benchmark_suite",
]
