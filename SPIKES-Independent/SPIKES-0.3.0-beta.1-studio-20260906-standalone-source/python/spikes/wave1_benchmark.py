"""Fail-closed Wave 1 qualification for the owned SPIKES C++ kernel.

The corpus deliberately separates numerical qualification from competitive
claims.  It records cold/warm execution, thread routes, convergence, bounded
expected failure, and current-process peak memory in an isolated worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .native_abi import NativeLibrary


REPORT_CONTRACT = "spikes/wave1-benchmark-report/v1"
CASE_CONTRACT = "spikes/wave1-benchmark-case/v1"
WORKER_CONTRACT = "spikes/wave1-worker-result/v1"
THREAD_COUNTS = (1, 2, 4)
MAX_REPETITIONS = 20


@dataclass(frozen=True, slots=True)
class Wave1Case:
    case_id: str
    title: str
    size_class: str
    category: str
    thread_scaling: bool
    expected_failure: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": CASE_CONTRACT,
            "case_id": self.case_id,
            "title": self.title,
            "size_class": self.size_class,
            "category": self.category,
            "thread_scaling": self.thread_scaling,
            "expected_failure": self.expected_failure,
        }


def wave1_cases() -> tuple[Wave1Case, ...]:
    return (
        Wave1Case("sparse.medium_ladder", "500-section threaded sparse ladder", "medium", "linear_sparse", True),
        Wave1Case("sparse.large_ladder", "2,000-section threaded sparse ladder", "large", "linear_sparse", True),
        Wave1Case("nonlinear.switch_convergence", "Controlled-switch Newton convergence", "small", "nonlinear_convergence", True),
        Wave1Case("robustness.singular_expected_failure", "Floating singular network", "small", "expected_failure", False, True),
        Wave1Case("converter.deadtime_parasitic_buck", "Dead-time buck with lumped parasitics", "medium", "switching_converter", False),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _peak_working_set_bytes() -> tuple[int | None, str]:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = (
                    ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                )

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = (
                wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD,
            )
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            if not psapi.GetProcessMemoryInfo(
                kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
            ):
                return None, "windows_peak_working_set_unavailable"
            return int(counters.PeakWorkingSetSize), "windows_peak_working_set"
        except (AttributeError, OSError, ValueError):
            return None, "windows_peak_working_set_unavailable"
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value * (1 if sys.platform == "darwin" else 1024), "posix_ru_maxrss"
    except (ImportError, OSError, ValueError):
        return None, "peak_working_set_unavailable"


def _ladder(library: NativeLibrary, sections: int, threads: int) -> dict[str, Any]:
    with library.circuit() as circuit:
        circuit.add_resistor("R0", "n0", "0", 1.0)
        for index in range(1, sections):
            circuit.add_resistor(f"R{index}", f"n{index - 1}", f"n{index}", 1.0)
        circuit.add_current_source("I1", "0", f"n{sections - 1}", 1.0)
        with circuit.solve_operating_point(
            linear_solver="conjugate_gradient", linear_threads=threads,
            max_linear_iterations=sections * 4,
        ) as result:
            diagnostics = result.diagnostics()
            observed = result.node_voltage(f"n{sections - 1}")
            status = result.status
    expected = float(sections)
    error = abs(observed - expected)
    error_limit = max(2.0e-8, expected * 1.0e-9)
    return {
        "accuracy_passed": (
            status == "converged" and error <= error_limit
            and diagnostics.get("linear_solver") == "conjugate_gradient"
            and diagnostics.get("linear_threads") == threads
            and int(diagnostics.get("linear_iterations", 0)) > 0
        ),
        "status": status,
        "observed_voltage_v": observed,
        "expected_voltage_v": expected,
        "absolute_error_v": error,
        "error_limit_v": error_limit,
        "requested_threads": threads,
        "observed_threads": diagnostics.get("linear_threads"),
        "diagnostics": diagnostics,
    }


def _switch_convergence(library: NativeLibrary, threads: int) -> dict[str, Any]:
    with library.circuit() as circuit:
        circuit.add_voltage_source("Vs", "in", "0", 10.0)
        circuit.add_voltage_source("Vg", "gate", "0", 2.7)
        circuit.add_voltage_controlled_switch(
            "S1", "in", "out", "gate", "0", on_resistance_ohm=0.1,
            off_resistance_ohm=1.0e7, threshold_voltage_v=2.5,
            transition_voltage_v=0.2,
        )
        circuit.add_resistor("Rload", "out", "0", 10.0)
        with circuit.solve_operating_point(
            linear_solver="gmres", linear_threads=threads,
            max_linear_iterations=500,
        ) as result:
            diagnostics = result.diagnostics()
            observed = result.node_voltage("out")
            status = result.status
    conductance_blend = 0.5 * (1.0 + math.tanh((2.7 - 2.5) / 0.2))
    conductance = 1.0 / 1.0e7 + conductance_blend * (1.0 / 0.1 - 1.0 / 1.0e7)
    expected = 10.0 * conductance / (conductance + 0.1)
    error = abs(observed - expected)
    return {
        "accuracy_passed": (
            status == "converged" and error <= 2.0e-8
            and int(diagnostics.get("linear_iterations", 0)) > 0
        ),
        "status": status,
        "observed_voltage_v": observed,
        "expected_voltage_v": expected,
        "absolute_error_v": error,
        "error_limit_v": 2.0e-8,
        "diagnostics": diagnostics,
    }


def _expected_singular_failure(library: NativeLibrary, _threads: int) -> dict[str, Any]:
    with library.circuit() as circuit:
        circuit.add_resistor("R1", "floating_a", "floating_b", 1_000.0)
        with circuit.solve_operating_point(linear_solver="sparse_lu") as result:
            diagnostics = result.diagnostics()
            status = result.status
            message = result.message
    expected = status != "converged"
    return {
        "accuracy_passed": expected,
        "status": status,
        "expected_failure_observed": expected,
        "message": message,
        "diagnostics": diagnostics,
    }


def _time_weighted_mean(times: list[float], values: list[float]) -> float:
    duration = times[-1] - times[0]
    return sum(
        0.5 * (left_v + right_v) * (right_t - left_t)
        for (left_t, left_v), (right_t, right_v)
        in zip(zip(times, values), zip(times[1:], values[1:]))
    ) / duration


def _deadtime_parasitic_buck(library: NativeLibrary, _threads: int) -> dict[str, Any]:
    period = 10.0e-6
    stop = 2.0e-3
    with library.circuit() as circuit:
        circuit.add_voltage_source("Vs", "src", "0", 24.0)
        circuit.add_resistor("Rsrc", "src", "vin", 0.05)
        for source, node, initial, pulsed in (
            ("Vgh", "gh", 0.0, 5.0), ("Vgl", "gl", 5.0, 0.0)
        ):
            circuit.add_pulse_voltage_source(
                source, node, "0", initial_value=initial, pulsed_value=pulsed,
                delay_s=0.0, rise_time_s=0.4e-6, fall_time_s=0.4e-6,
                pulse_width_s=3.6e-6, period_s=period,
            )
        circuit.add_voltage_controlled_switch(
            "Sh", "vin", "sw", "gh", "0", on_resistance_ohm=0.08,
            off_resistance_ohm=1.0e7, threshold_voltage_v=3.0,
            transition_voltage_v=0.25,
        )
        circuit.add_voltage_controlled_switch(
            "Sl", "0", "sw", "gl", "0", on_resistance_ohm=0.08,
            off_resistance_ohm=1.0e7, threshold_voltage_v=3.0,
            transition_voltage_v=0.25,
        )
        circuit.add_inductor("L1", "sw", "ldcr", 47.0e-6)
        circuit.add_resistor("Rdcr", "ldcr", "out", 0.04)
        circuit.add_resistor("Resr", "out", "cout", 0.02)
        circuit.add_capacitor("C1", "cout", "0", 100.0e-6)
        circuit.add_resistor("Rload", "out", "0", 5.0)
        with circuit.solve_transient(
            time_step_s=0.2e-6, stop_time_s=stop,
            initialize_from_operating_point=False,
            integration_method="hybrid_trapezoidal",
            max_newton_iterations=200, max_backtracks=30,
        ) as result:
            diagnostics = result.diagnostics()
            status = result.status
            start = stop - 10.0 * period
            samples = [
                (result.time(index), result.node_voltage(index, "out"))
                for index in range(result.point_count)
                if result.time(index) >= start
            ]
    times = [item[0] for item in samples]
    values = [item[1] for item in samples]
    average = _time_weighted_mean(times, values)
    ripple = max(values) - min(values)
    error = abs(average - 24.0 * 0.4)
    return {
        "accuracy_passed": (
            status == "converged" and error <= 1.5
            and ripple <= 2.0 and min(values) >= -0.5 and max(values) <= 24.5
        ),
        "status": status,
        "steady_average_output_v": average,
        "ideal_nominal_output_v": 24.0 * 0.4,
        "absolute_conversion_error_v": error,
        "conversion_error_limit_v": 1.5,
        "peak_to_peak_ripple_v": ripple,
        "ripple_limit_v": 2.0,
        "dead_time_s": {"high_to_low": 80.0e-9, "low_to_high": 80.0e-9},
        "parasitics": {
            "source_resistance_ohm": 0.05, "switch_on_resistance_ohm": 0.08,
            "switch_off_resistance_ohm": 1.0e7, "inductor_dcr_ohm": 0.04,
            "capacitor_esr_ohm": 0.02,
        },
        "model_limits": [
            "smooth bidirectional controlled switches; no semiconductor charge or reverse recovery",
            "fixed lumped parasitics; no voltage, frequency, or temperature dependence",
            "ideal gate sources; no driver impedance or propagation-delay mismatch",
            "linear L/C; no magnetic saturation, hysteresis, dielectric loss, or electrothermal feedback",
        ],
        "diagnostics": diagnostics,
    }


_RUNNERS: dict[str, Callable[[NativeLibrary, int], dict[str, Any]]] = {
    "sparse.medium_ladder": lambda library, threads: _ladder(library, 500, threads),
    "sparse.large_ladder": lambda library, threads: _ladder(library, 2_000, threads),
    "nonlinear.switch_convergence": _switch_convergence,
    "robustness.singular_expected_failure": _expected_singular_failure,
    "converter.deadtime_parasitic_buck": _deadtime_parasitic_buck,
}


def _worker(library_path: Path, case_id: str, threads: int, repetitions: int) -> dict[str, Any]:
    if case_id not in _RUNNERS:
        raise ValueError("unknown Wave 1 case")
    library = NativeLibrary(library_path)
    runner = _RUNNERS[case_id]
    started = time.perf_counter_ns()
    first = runner(library, threads)
    cold_ns = time.perf_counter_ns() - started
    warm: list[int] = []
    observations = [first]
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        observations.append(runner(library, threads))
        warm.append(time.perf_counter_ns() - started)
    peak, peak_scope = _peak_working_set_bytes()
    return {
        "contract": WORKER_CONTRACT,
        "case_id": case_id,
        "threads": threads,
        "status": "passed" if all(item.get("accuracy_passed") is True for item in observations) else "failed",
        "cold_execution_ns": cold_ns,
        "warm_execution_ns": warm,
        "warm_median_ns": int(statistics.median(warm)) if warm else None,
        "peak_working_set_bytes": peak,
        "peak_memory_scope": peak_scope,
        "observations": observations,
    }


def _launch_worker(
    library: Path, case: Wave1Case, threads: int, repetitions: int, timeout_s: float,
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    completed = subprocess.run(
        [
            sys.executable, "-m", "python.spikes.wave1_benchmark", "--worker",
            "--library", str(library), "--case", case.case_id,
            "--threads", str(threads), "--repetitions", str(repetitions),
        ],
        cwd=Path(__file__).resolve().parents[2], capture_output=True,
        timeout=timeout_s, check=False, shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    process_ns = time.perf_counter_ns() - started
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"Wave 1 worker emitted invalid JSON: {completed.stderr[-2000:]!r}") from exc
    if completed.returncode != 0 or payload.get("contract") != WORKER_CONTRACT:
        raise RuntimeError(f"Wave 1 worker failed: {payload}")
    payload["cold_process_elapsed_ns"] = process_ns
    payload["launcher_sha256"] = _sha256(Path(sys.executable).resolve())
    return payload


def run_wave1_benchmarks(
    library_path: str | Path, *, repetitions: int = 2, timeout_s: float = 120.0,
) -> dict[str, Any]:
    if isinstance(repetitions, bool) or not 1 <= int(repetitions) <= MAX_REPETITIONS:
        raise ValueError(f"repetitions must be from 1 through {MAX_REPETITIONS}")
    library = Path(library_path).resolve(strict=True)
    records: list[dict[str, Any]] = []
    for case in wave1_cases():
        configurations = THREAD_COUNTS if case.thread_scaling else (1,)
        runs = []
        for threads in configurations:
            try:
                runs.append(_launch_worker(library, case, threads, int(repetitions), timeout_s))
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                runs.append({
                    "contract": WORKER_CONTRACT, "case_id": case.case_id,
                    "threads": threads, "status": "failed", "issue": str(exc)[:4096],
                })
        records.append({
            "case": case.to_dict(), "status": "passed" if all(run["status"] == "passed" for run in runs) else "failed",
            "thread_runs": runs,
        })
    passed = sum(record["status"] == "passed" for record in records)
    memory_complete = all(
        run.get("peak_working_set_bytes") is not None
        for record in records for run in record["thread_runs"]
    )
    return {
        "contract": REPORT_CONTRACT,
        "generated_at_epoch_s": time.time(),
        "status": "passed" if passed == len(records) else "failed",
        "summary": {"total": len(records), "passed": passed, "failed": len(records) - passed},
        "host": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": platform.python_version(),
        },
        "native_library": {"path": str(library), "sha256": _sha256(library)},
        "thread_counts": list(THREAD_COUNTS),
        "cold_warm_separated": True,
        "peak_memory_complete": memory_complete,
        "accuracy_gate_passed": passed == len(records),
        "performance_claim_eligible": False,
        "cases": records,
        "limitations": [
            "Medium and large labels are bounded corpus tiers, not public industry circuit sizes.",
            "Cold process time includes Python launch, DLL load, case construction, solve, and JSON output; warm execution rebuilds each circuit in one worker.",
            "Peak memory is the isolated worker process peak; the worker launches no child process.",
            "Thread diagnostics prove requested routes, not useful parallel speedup or deterministic scheduling.",
            "The converter uses smooth controlled switches and explicitly bounded lumped parasitics; it is not a qualified semiconductor loss model.",
            "No competitive performance, parity, hard-real-time, or HIL claim is permitted from this owned-only corpus.",
        ],
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--case")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=1)
    arguments = parser.parse_args()
    if not arguments.worker or not arguments.case:
        parser.error("this module entry point is reserved for bounded worker execution")
    try:
        result = _worker(
            arguments.library.resolve(strict=True), arguments.case,
            arguments.threads, arguments.repetitions,
        )
        print(json.dumps(result, allow_nan=False))
        return 0 if result["status"] == "passed" else 3
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"contract": WORKER_CONTRACT, "status": "error", "issue": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "CASE_CONTRACT", "REPORT_CONTRACT", "THREAD_COUNTS", "Wave1Case",
    "run_wave1_benchmarks", "wave1_cases",
]
