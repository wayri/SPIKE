"""Accuracy-first cross-engine checks for the currently shared SPICE subset.

This is deliberately a check harness, not a superiority scorer. It records
comparable cold-process timings for the same scalar-output scope, but never
promotes the whole-product performance gate from this small corpus.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from python.spike_core.contracts import AnalysisSpec, DesignIR
from python.spike_core.ngspice_plugin import NgspicePlugin

from .contracts import ProbeDescriptor
from .native_runner import run_native_project
from .netlist import parse_netlist


REPORT_CONTRACT = "spikes/competitive-benchmark-report/v1"
MAX_REPETITIONS = 50


@dataclass(frozen=True, slots=True)
class CompetitiveCase:
    case_id: str
    title: str
    netlist: str
    probe: str
    expected: float
    absolute_tolerance: float = 1.0e-10
    measurement: str = "scalar"
    time_s: float | None = None
    start_s: float | None = None
    stop_s: float | None = None
    classes: tuple[str, ...] = ("small", "dc", "operating_point")

    def __post_init__(self) -> None:
        measurement = str(self.measurement).strip().lower()
        if measurement not in {"scalar", "find_at_time", "average_window"}:
            raise ValueError("measurement must be scalar, find_at_time, or average_window")
        object.__setattr__(self, "measurement", measurement)
        if measurement == "scalar":
            if any(value is not None for value in (self.time_s, self.start_s, self.stop_s)):
                raise ValueError("scalar measurement cannot carry transient bounds")
        elif measurement == "find_at_time":
            if self.time_s is None or not math.isfinite(self.time_s) or self.time_s < 0:
                raise ValueError("find_at_time requires a finite nonnegative time_s")
            if self.start_s is not None or self.stop_s is not None:
                raise ValueError("find_at_time accepts only time_s")
        else:
            if (
                self.start_s is None or self.stop_s is None
                or not math.isfinite(self.start_s) or not math.isfinite(self.stop_s)
                or self.start_s < 0 or self.stop_s <= self.start_s
                or self.time_s is not None
            ):
                raise ValueError("average_window requires finite bounds with stop_s > start_s >= 0")
        if not self.classes or len(set(self.classes)) != len(self.classes):
            raise ValueError("classes must be nonempty and unique")

    @property
    def vector(self) -> str:
        probe = ProbeDescriptor.parse(self.probe)
        if probe.quantity == "node_voltage":
            return f"v({','.join(probe.targets)})"
        if probe.quantity == "element_current":
            return f"i({probe.targets[0]})"
        raise ValueError("competitive baseline accepts one-node voltage or element-current probes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "probe": self.probe,
            "expected": self.expected,
            "absolute_tolerance": self.absolute_tolerance,
            "measurement": {
                "kind": self.measurement,
                **({"time_s": self.time_s} if self.measurement == "find_at_time" else {}),
                **(
                    {"start_s": self.start_s, "stop_s": self.stop_s}
                    if self.measurement == "average_window" else {}
                ),
            },
            "classes": list(self.classes),
            "netlist_sha256": hashlib.sha256(self.netlist.encode("utf-8")).hexdigest(),
        }


def shared_dc_cases() -> tuple[CompetitiveCase, ...]:
    return (
        CompetitiveCase(
            "dc.divider.equal", "Equal divider",
            "Equal divider\nV1 in 0 10\nR1 in out 1k\nR2 out 0 1k\n.op\n.end\n",
            "V(out)", 5.0,
        ),
        CompetitiveCase(
            "dc.divider.unequal", "Unequal divider",
            "Unequal divider\nV1 in 0 12\nR1 in out 2k\nR2 out 0 1k\n.op\n.end\n",
            "V(out)", 4.0,
        ),
        CompetitiveCase(
            "dc.current_load", "Current source load",
            "Current load\nI1 0 out 2m\nR1 out 0 1k\n.op\n.end\n",
            "V(out)", 2.0,
        ),
    )


def shared_first_release_cases() -> tuple[CompetitiveCase, ...]:
    """Bounded same-model cases accepted by SPIKES, ngspice, and LTspice."""

    tau = 1.0e-3
    rise = 10.0e-6
    sample = rise + tau
    at_end_of_ramp = 1.0 - tau / rise * (1.0 - math.exp(-rise / tau))
    first_order = 1.0 - (1.0 - at_end_of_ramp) * math.exp(-tau / tau)
    transient_classes = ("small", "transient", "same_model", "scalar_measurement")
    rf_resistance = 10.0
    rf_inductance = 1.0e-6
    rf_capacitance = 100.0e-12
    rf_sample = 50.0e-9
    rf_alpha = rf_resistance / (2.0 * rf_inductance)
    rf_omega_0 = 1.0 / math.sqrt(rf_inductance * rf_capacitance)
    rf_omega_d = math.sqrt(rf_omega_0**2 - rf_alpha**2)
    rf_step = 1.0 - math.exp(-rf_alpha * rf_sample) * (
        math.cos(rf_omega_d * rf_sample)
        + rf_alpha / rf_omega_d * math.sin(rf_omega_d * rf_sample)
    )
    motor_tau = 10.0e-3 / 2.0
    motor_sample = 5.0e-6 + motor_tau
    motor_current = 24.0 / 2.0 * (1.0 - math.exp(-1.0))
    # Exact square-wave state propagation for the ideal LC buck fixture.  The
    # finite 1 ns source edges are much shorter than its 10 us period and are
    # covered by the explicit comparison tolerance.
    import numpy as np
    from scipy.linalg import expm
    buck_l, buck_c, buck_r = 100.0e-6, 10.0e-6, 10.0
    buck_a = np.asarray([[0.0, -1.0 / buck_l],
                         [1.0 / buck_c, -1.0 / (buck_r * buck_c)]])
    buck_phi = expm(buck_a * 5.0e-6)
    buck_on = np.linalg.solve(
        buck_a, (buck_phi - np.eye(2)) @ np.asarray([24.0 / buck_l, 0.0])
    )
    buck_state = np.zeros(2)
    for _ in range(10):
        buck_state = buck_phi @ buck_state + buck_on
        buck_state = buck_phi @ buck_state

    return shared_dc_cases() + (
        CompetitiveCase(
            "transient.rc_step", "RC unit-step response at one time constant",
            "RC step\nV1 in 0 PULSE(0 1 0 10u 10u 10m 20m)\n"
            "R1 in out 1k\nC1 out 0 1u\n.tran 1u 1.01m\n.end\n",
            "V(out)", first_order, absolute_tolerance=5.0e-5,
            measurement="find_at_time", time_s=sample,
            classes=transient_classes + ("passive_rc",),
        ),
        CompetitiveCase(
            "transient.rl_step", "RL unit-step current through a 1 ohm sense resistor",
            "RL step\nV1 in 0 PULSE(0 1 0 10u 10u 10m 20m)\n"
            "R1 in out 1\nL1 out 0 1m\n.tran 1u 1.01m\n.end\n",
            "V(in,out)", first_order, absolute_tolerance=3.0e-4,
            measurement="find_at_time", time_s=sample,
            classes=transient_classes + ("passive_rl",),
        ),
        CompetitiveCase(
            "switching.pulse_duty", "PULSE-driven resistive-load duty average",
            "PULSE duty\nV1 out 0 PULSE(0 10 0 10u 10u 400u 1m)\n"
            "R1 out 0 10\n.tran 10u 4m\n.end\n",
            "V(out)", 4.1, absolute_tolerance=2.0e-3,
            measurement="average_window", start_s=0.0, stop_s=4.0e-3,
            classes=(
                "small", "transient", "switching", "same_model",
                "scalar_measurement", "ideal_pulse_load",
            ),
        ),
        CompetitiveCase(
            "converter.buck_lc_pwm", "Ideal PWM buck LC endpoint after ten periods",
            "Buck LC\nVSW sw 0 PULSE(0 24 0 1n 1n 5u 10u)\n"
            "L1 sw out 100u\nC1 out 0 10u\nR1 out 0 10\n"
            ".tran 20n 100.02u\n.end\n",
            "V(out)", float(buck_state[1]), absolute_tolerance=6.0e-2,
            measurement="find_at_time", time_s=100.0e-6,
            classes=(
                "small", "transient", "switching", "converter", "smps",
                "energy_storage", "same_model", "scalar_measurement",
                "ideal_pwm_buck",
            ),
        ),
        CompetitiveCase(
            "rf.series_rlc_step", "Underdamped RF RLC step response",
            "RF RLC\nV1 in 0 PULSE(0 1 0 1p 1p 1u 2u)\n"
            "R1 in n1 10\nL1 n1 out 1u\nC1 out 0 100p\n"
            ".tran 50p 50.001n\n.end\n",
            "V(out)", rf_step, absolute_tolerance=1.5e-2,
            measurement="find_at_time", time_s=50.001e-9,
            classes=(
                "small", "transient", "rf", "ringing", "same_model",
                "scalar_measurement", "passive_rlc",
            ),
        ),
        CompetitiveCase(
            "motor.armature_rl", "Motor-armature electrical RL current rise",
            "Motor armature\nV1 drive 0 PULSE(0 24 0 5u 5u 20m 40m)\n"
            "RSENSE drive mid 0.1\nRWIND mid coil 1.9\nLARM coil 0 10m\n"
            ".tran 5u 5.005m\n.end\n",
            "V(drive,mid)", 0.1 * motor_current, absolute_tolerance=2.0e-3,
            measurement="find_at_time", time_s=motor_sample,
            classes=(
                "small", "transient", "motor", "electrical_surrogate",
                "same_model", "scalar_measurement", "passive_rl",
            ),
        ),
    )


def _interpolate(times: list[float], values: list[float], target: float) -> float:
    if len(times) != len(values) or not times:
        raise RuntimeError("transient result has inconsistent time and probe vectors")
    if target < times[0] or target > times[-1]:
        raise RuntimeError("measurement time is outside the transient result")
    index = bisect_left(times, target)
    if index == 0 or (index < len(times) and times[index] == target):
        return values[index]
    if index >= len(times):
        return values[-1]
    left_t, right_t = times[index - 1], times[index]
    if right_t <= left_t:
        raise RuntimeError("transient time vector is not strictly increasing")
    fraction = (target - left_t) / (right_t - left_t)
    return values[index - 1] + fraction * (values[index] - values[index - 1])


def _reduce_transient(case: CompetitiveCase, times_raw: Any, values_raw: Any) -> float:
    times = [float(value) for value in times_raw]
    values = [float(value) for value in values_raw]
    if any(not math.isfinite(value) for value in (*times, *values)):
        raise RuntimeError("transient result contains a non-finite value")
    if any(times[index] <= times[index - 1] for index in range(1, len(times))):
        raise RuntimeError("transient time vector is not strictly increasing")
    if case.measurement == "find_at_time":
        assert case.time_s is not None
        return _interpolate(times, values, case.time_s)
    if case.measurement != "average_window":
        raise RuntimeError("transient case does not define a transient measurement")
    assert case.start_s is not None and case.stop_s is not None
    points = [(case.start_s, _interpolate(times, values, case.start_s))]
    points.extend(
        (time_s, value) for time_s, value in zip(times, values, strict=True)
        if case.start_s < time_s < case.stop_s
    )
    points.append((case.stop_s, _interpolate(times, values, case.stop_s)))
    integral = sum(
        0.5 * (left_v + right_v) * (right_t - left_t)
        for (left_t, left_v), (right_t, right_v) in zip(points, points[1:])
    )
    return integral / (case.stop_s - case.start_s)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _native_observer(library: Path) -> Callable[[CompetitiveCase], float]:
    def observe(case: CompetitiveCase) -> float:
        probe = ProbeDescriptor.parse(case.probe)
        project = parse_netlist(
            case.netlist, source_name=case.case_id, probes=(probe,),
            native_extensions=True,
        )
        result = run_native_project(project, library).to_dict()
        if result.get("status") != "completed":
            raise RuntimeError(f"SPIKES failed: {result.get('issues', [])}")
        return float(result["probes"][probe.name]["value"])

    return observe


def _native_process_observer(library: Path) -> Callable[[CompetitiveCase], float]:
    root = Path(__file__).resolve().parents[2]

    def observe(case: CompetitiveCase) -> float:
        with tempfile.TemporaryDirectory(prefix="spikes-owned-") as directory:
            deck = Path(directory) / "case.cir"
            deck.write_text(case.netlist, encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable, "-m", "python.spikes", "native-run", str(deck),
                    "--library", str(library), "--probe", case.probe,
                ],
                cwd=root, capture_output=True, timeout=30, check=False, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                payload = json.loads(completed.stdout.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise RuntimeError(
                    f"SPIKES emitted invalid JSON: {completed.stdout[-1000:]!r}"
                ) from exc
            if completed.returncode != 0 or payload.get("status") != "completed":
                raise RuntimeError(f"SPIKES failed: {payload.get('issues', [])}")
            probe_record = payload["probes"][case.probe]
            if case.measurement == "scalar":
                return float(probe_record["value"])
            return _reduce_transient(
                case, payload["data"]["time_s"], probe_record["values"]
            )

    return observe


def _ngspice_observer(plugin: NgspicePlugin) -> Callable[[CompetitiveCase], float]:
    design = DesignIR(design_id="competitive-circuit", name="Competitive circuit")

    def observe(case: CompetitiveCase) -> float:
        result = plugin.run(design, AnalysisSpec(
            analysis_id=case.case_id,
            mode="spice",
            solver_id="spike.ngspice",
            options={"spice_netlist": case.netlist, "timeout_seconds": 30},
        ))
        if result.status != "completed":
            raise RuntimeError(f"ngspice failed: {[item.message for item in result.issues]}")
        vectors = result.fields.get("waveforms", {})
        probe = ProbeDescriptor.parse(case.probe)
        values = vectors.get(case.vector, ())
        if not values and probe.quantity == "node_voltage" and len(probe.targets) == 2:
            positive = vectors.get(f"v({probe.targets[0]})", ())
            negative = vectors.get(f"v({probe.targets[1]})", ())
            if positive and len(positive) == len(negative):
                values = [
                    float(left) - float(right)
                    for left, right in zip(positive, negative, strict=True)
                ]
        if not values:
            raise RuntimeError(f"ngspice omitted {case.vector}")
        if case.measurement == "scalar":
            return float(values[-1])
        times = vectors.get("time", ())
        if not times:
            raise RuntimeError("ngspice omitted the transient time vector")
        return _reduce_transient(case, times, values)

    return observe


def find_ltspice() -> Path | None:
    configured = os.environ.get("SPIKES_LTSPICE_PATH", "").strip()
    candidates = [Path(configured)] if configured else []
    local = os.environ.get("LOCALAPPDATA", "").strip()
    program_files = os.environ.get("PROGRAMFILES", "").strip()
    if local:
        candidates.append(Path(local) / "Programs" / "ADI" / "LTspice" / "LTspice.exe")
    if program_files:
        candidates.extend((
            Path(program_files) / "ADI" / "LTspice" / "LTspice.exe",
            Path(program_files) / "LTC" / "LTspiceXVII" / "XVIIx64.exe",
        ))
    return next((item.resolve() for item in candidates if item.is_file()), None)


_MEASURE = re.compile(
    r"(?im)^\s*bench_value\s*[:=].*?([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)"
)


def _ltspice_deck(case: CompetitiveCase) -> str:
    lines = case.netlist.rstrip().splitlines()
    end = next((index for index, line in enumerate(lines) if line.strip().lower() == ".end"), None)
    had_end = end is not None
    if end is None:
        end = len(lines)
    if case.measurement == "scalar":
        measure = f".meas op bench_value FIND {case.vector}"
    elif case.measurement == "find_at_time":
        assert case.time_s is not None
        measure = f".meas tran bench_value FIND {case.vector} AT={case.time_s:.17g}"
    else:
        assert case.start_s is not None and case.stop_s is not None
        measure = (
            f".meas tran bench_value AVG {case.vector} "
            f"FROM={case.start_s:.17g} TO={case.stop_s:.17g}"
        )
    lines.insert(end, measure)
    if not had_end:
        lines.append(".end")
    return "\n".join(lines) + "\n"


def _ltspice_observer(executable: Path) -> Callable[[CompetitiveCase], float]:
    def observe(case: CompetitiveCase) -> float:
        with tempfile.TemporaryDirectory(prefix="spikes-ltspice-") as directory:
            root = Path(directory)
            deck = root / "case.cir"
            deck.write_text(_ltspice_deck(case), encoding="utf-8")
            completed = subprocess.run(
                [str(executable), "-b", str(deck)], cwd=root,
                capture_output=True, timeout=30, check=False, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            log = deck.with_suffix(".log")
            text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
            if completed.returncode != 0:
                raise RuntimeError(f"LTspice exited with {completed.returncode}: {text[-1000:]}")
            matched = _MEASURE.search(text)
            if matched is None:
                raise RuntimeError(f"LTspice did not emit bench_value: {text[-1000:]}")
            return float(matched.group(1))

    return observe


def _run_engine(
    engine_id: str,
    observer: Callable[[CompetitiveCase], float] | None,
    cases: tuple[CompetitiveCase, ...],
    repetitions: int,
    *,
    executable: Path | None,
    implementation: Path | None = None,
    timing_scope: str,
    unavailable_reason: str = "",
) -> dict[str, Any]:
    identity = {
        "executable": str(executable) if executable else "",
        "sha256": _sha256(executable) if executable and executable.is_file() else "",
        "implementation_artifact": str(implementation) if implementation else "",
        "implementation_sha256": (
            _sha256(implementation)
            if implementation and implementation.is_file() else ""
        ),
    }
    if observer is None:
        return {
            "engine_id": engine_id, "status": "blocked", "identity": identity,
            "timing_scope": timing_scope, "cases": [], "reason": unavailable_reason,
        }
    results = []
    for case in cases:
        values: list[float] = []
        timings: list[int] = []
        issue = ""
        try:
            observer(case)
            for _ in range(repetitions):
                started = time.perf_counter_ns()
                values.append(observer(case))
                timings.append(time.perf_counter_ns() - started)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            issue = str(exc)[:4096]
        maximum_error = max((abs(value - case.expected) for value in values), default=math.inf)
        passed = bool(values) and not issue and maximum_error <= case.absolute_tolerance
        results.append({
            "case": case.to_dict(),
            "status": "passed" if passed else "failed",
            "observed": {
                "minimum": min(values) if values else None,
                "median": statistics.median(values) if values else None,
                "maximum": max(values) if values else None,
            },
            "maximum_absolute_error": maximum_error if math.isfinite(maximum_error) else None,
            "timing_ns": timings,
            "median_elapsed_ns": int(statistics.median(timings)) if timings else None,
            "issue": issue,
        })
    passed = sum(item["status"] == "passed" for item in results)
    return {
        "engine_id": engine_id,
        "status": "passed" if passed == len(results) else "failed",
        "identity": identity,
        "timing_scope": timing_scope,
        "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
        "aggregate": {
            "median_case_elapsed_ns": int(statistics.median(
                item["median_elapsed_ns"] for item in results
                if item["median_elapsed_ns"] is not None
            )) if any(item["median_elapsed_ns"] is not None for item in results) else None,
        },
        "cases": results,
    }


def run_competitive_benchmarks(
    library_path: str | Path, *, repetitions: int = 5,
) -> dict[str, Any]:
    if isinstance(repetitions, bool) or not 1 <= int(repetitions) <= MAX_REPETITIONS:
        raise ValueError(f"repetitions must be from 1 through {MAX_REPETITIONS}")
    library = Path(library_path).resolve(strict=True)
    cases = shared_first_release_cases()
    ngspice = NgspicePlugin()
    ngspice_path = Path(ngspice.executable).resolve() if ngspice.executable else None
    ltspice_path = find_ltspice()
    engines = [
        _run_engine(
            "spikes.owned_cpp", _native_process_observer(library), cases, int(repetitions),
            executable=Path(sys.executable).resolve(), implementation=library,
            timing_scope="isolated_process_per_run_including_startup_and_result_parse",
        ),
        _run_engine(
            "ngspice", _ngspice_observer(ngspice) if ngspice.executable else None,
            cases, int(repetitions), executable=ngspice_path,
            timing_scope="isolated_process_per_run_including_startup_and_result_parse",
            unavailable_reason="ngspice is not installed or discoverable",
        ),
        _run_engine(
            "ltspice", _ltspice_observer(ltspice_path) if ltspice_path else None,
            cases, int(repetitions), executable=ltspice_path,
            timing_scope="isolated_process_per_run_including_startup_and_result_parse",
            unavailable_reason="LTspice is not installed or discoverable",
        ),
    ]
    accuracy_passed = all(item["status"] == "passed" for item in engines)
    timing_comparable = accuracy_passed and len({
        item["timing_scope"] for item in engines
    }) == 1
    return {
        "contract": REPORT_CONTRACT,
        "generated_at_epoch_s": time.time(),
        "host": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": platform.python_version(),
        },
        "status": "passed" if accuracy_passed else "blocked",
        "shared_subset_accuracy_passed": accuracy_passed,
        "performance_claim_eligible": False,
        "timing_comparable": timing_comparable,
        "corpus": {
            "case_count": len(cases),
            "classes": sorted({name for case in cases for name in case.classes}),
            "missing_required_classes": [
                "medium", "large", "ac", "noise", "physical_motor_mechanics",
                "compact_models", "robustness", "thread_scaling", "peak_memory",
            ],
        },
        "engines": engines,
        "limitations": [
            "The shared corpus contains three small DC cases, two passive first-order transients, one duty reduction, and idealized converter/RF/motor electrical fixtures.",
            "Cold process-launch wall time is comparable only for this scalar-output subset; it is not a warm-solver throughput result.",
            "The converter fixture includes LC energy storage but uses an ideal PWM source; it has no semiconductor compact model, parasitic switching loss, reverse recovery, dead time, or control loop.",
            "The RF case is a passive time-domain RLC ringing check, not an S-parameter/noise/nonlinear RF qualification.",
            "The motor case is an armature R-L electrical surrogate, not a mechanical, magnetic, torque, saturation, or back-EMF co-simulation.",
            "Peak memory, warm solves, thread scaling, and large public decks are not measured.",
            "No parity or superiority claim is permitted from this report.",
        ],
    }


__all__ = [
    "CompetitiveCase", "REPORT_CONTRACT", "find_ltspice",
    "run_competitive_benchmarks", "shared_dc_cases", "shared_first_release_cases",
]
