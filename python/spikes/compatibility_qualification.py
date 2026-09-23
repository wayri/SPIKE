"""Text-deck/native evidence, complementary to the existing direct-ABI corpus.

Run with ``python -m python.spikes.compatibility_qualification --library ... -o ...``.
Timings include parsing, loading, construction, solving and result extraction;
they are not native-kernel-only benchmarks or proof of SPICE parity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import shutil
import statistics
import time
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path

from .netlist import parse_netlist
from .native_runner import run_native_project


def _fixtures():
    return (
        ("deck.scoped_divider", "Scoped parameterized subcircuit", """Scoped divider
.param supply=10
.subckt divider p n o params: r=1k
R1 p o {r}
R2 o n {2*r}
.ends divider
V1 in 0 {supply}
X1 in 0 out divider r=3k
.op
.end
""", "node_voltage_v", "out", lambda t: 20 / 3, 1e-9),
        ("deck.rc_step", "RC charge from zero", """RC
V1 in 0 1
R1 in out 1k
C1 out 0 1u
.tran 1u 5m uic
.end
""", "node_voltage_v", "out", lambda t: -math.expm1(-t / .001), 2e-6),
        ("deck.rl_step", "RL current from zero", """RL
V1 in 0 1
R1 in out 10
L1 out 0 10m
.tran 1u 5m uic
.end
""", "element_current_a", "L1", lambda t: -.1 * math.expm1(-t / .001), 2e-7),
        ("deck.shockley", "Current-biased scoped static Shockley diode", """Diode
.subckt junction_cell a b params: leakage=2e-12 ideality=2
D1 a b junction
.model junction D(IS={leakage} N={ideality})
.ends junction_cell
I1 0 out 1m
X1 out 0 junction_cell leakage=1e-12 ideality=1
.op
.end
""", "node_voltage_v", "out",
         lambda t: (1.380649e-23 * 300.15 / 1.602176634e-19) * math.log1p(1e9), 1e-6),
    )


def _compare_vectors(native_times, native_values, reference_times, reference_values, tolerance):
    """Compare every native point in the reference domain; never extrapolate."""
    for times, values in ((native_times, native_values), (reference_times, reference_values)):
        if not times or len(times) != len(values):
            raise ValueError("Empty or misaligned trace")
        if not all(math.isfinite(v) for v in [*times, *values]):
            raise ValueError("Nonfinite trace")
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("Trace times must be strictly increasing")
    errors = []
    excluded = []
    for t, value in zip(native_times, native_values):
        if t < reference_times[0] or t > reference_times[-1]:
            excluded.append(t)
            continue
        index = bisect_left(reference_times, t)
        if reference_times[index] == t:
            expected = reference_values[index]
        else:
            a, b = reference_times[index-1:index+1]
            expected = reference_values[index-1] + (reference_values[index]-reference_values[index-1]) * (t-a)/(b-a)
        errors.append(abs(value-expected))
    if not errors:
        raise ValueError("No overlapping samples")
    # UIC may omit zero; no other missing native samples are permitted.
    coverage_ok = all(t == 0 for t in excluded)
    return dict(status="passed" if coverage_ok and max(errors) <= tolerance else "failed",
                compared_points=len(errors), excluded_native_times_s=excluded,
                coverage_ok=coverage_ok, maximum_absolute_error=max(errors),
                absolute_tolerance=tolerance, interpolation="linear reference-to-native; no extrapolation")


def _reference_case(executable, deck, table, signal, times, values, tolerance):
    from python.spike_core.contracts import AnalysisSpec, DesignIR
    from python.spike_core.ngspice_plugin import NgspicePlugin
    plugin = NgspicePlugin()
    plugin.executable = str(executable)
    # Match the requested native step with a reference maximum step, without
    # changing any circuit/model values. Reference tolerances are explicit.
    lines = deck.splitlines()
    for i, line in enumerate(lines):
        if line.lower().startswith(".tran "):
            tokens = line.split()
            lines[i] = f".tran {tokens[1]} {tokens[2]} 0 {tokens[1]} uic"
    lines.insert(-1, ".options reltol=1e-8 abstol=1e-14 vntol=1e-10 gmin=1e-15")
    reference_deck = "\n".join(lines) + "\n"
    started = time.perf_counter_ns()
    result = plugin.run(DesignIR(design_id="qualification", name="Qualification"), AnalysisSpec(
        analysis_id="reference", mode="spice", solver_id="spike.ngspice",
        options={"spice_netlist": reference_deck, "timeout_seconds": 30}))
    elapsed = time.perf_counter_ns() - started
    if result.status != "completed" or result.summary.get("parse_status") != "complete":
        raise RuntimeError(f"ngspice failed or incomplete: {result.summary}; {result.issues}")
    vectors = result.fields["waveforms"]
    vector = f"v({signal.lower()})" if table == "node_voltage_v" else f"i({signal.lower()})"
    reference_values = vectors.get(vector, vectors.get(f"{signal.lower()}#branch"))
    if reference_values is None:
        raise ValueError(f"ngspice omitted {vector}")
    reference_times = vectors.get("time", [0.0])
    comparison = _compare_vectors(times, values, reference_times, reference_values, tolerance)
    comparison.update(source=reference_deck, source_sha256=hashlib.sha256(reference_deck.encode()).hexdigest(),
                      elapsed_ns=elapsed, timing_scope="reference subprocess plus result parsing; not comparable to native in-process timing",
                      native_trace=dict(time_s=times, values=values),
                      reference_trace=dict(time_s=reference_times, values=reference_values))
    return comparison


def run_deck_qualification(library_path, *, repetitions=2, include_direct_abi=False, ngspice=None):
    if type(repetitions) is not int or not 1 <= repetitions <= 20:
        raise ValueError("repetitions must be an integer from 1 through 20")
    library = Path(library_path).resolve(strict=True)
    reference_executable = Path(ngspice).resolve(strict=True) if ngspice else None
    if reference_executable and not reference_executable.is_file():
        raise ValueError("ngspice must be an executable file")
    cases = []
    for case_id, title, deck, table, signal, expected, tolerance in _fixtures():
        case = dict(case_id=case_id, title=title, source=deck,
                    source_sha256=hashlib.sha256(deck.encode()).hexdigest(),
                    comparison=dict(table=table, signal=signal, absolute_tolerance=tolerance),
                    timing_scope="in_process_parse_load_build_solve_extract", observations=[])
        for repetition in range(repetitions + 1):
            started = time.perf_counter_ns()
            try:
                project = parse_netlist(deck, source_name=case_id)
                result = run_native_project(project, library)
                elapsed = time.perf_counter_ns() - started
                if result.status != "completed":
                    raise RuntimeError(str(result.issues))
                values = result.data[table][signal]
                values = values if isinstance(values, list) else [values]
                times = result.data.get("time_s", [0.0])
                if not values or len(times) != len(values):
                    raise ValueError("Empty or misaligned native result")
                errors = [abs(value - expected(t)) for t, value in zip(times, values)]
                passed = all(math.isfinite(e) and e <= tolerance for e in errors)
                case["observations"].append(dict(passed=passed, elapsed_ns=elapsed,
                    points=len(values), maximum_absolute_error=max(errors),
                    native_status=result.status, diagnostics=result.diagnostics))
                if repetition == 0 and reference_executable:
                    try:
                        case["reference"] = _reference_case(reference_executable, deck, table, signal, times, values, tolerance)
                    except Exception as exc:
                        case["reference"] = dict(status="failed", error=f"{type(exc).__name__}: {exc}")
            except Exception as exc:
                case["observations"].append(dict(passed=False,
                    elapsed_ns=time.perf_counter_ns()-started, error=f"{type(exc).__name__}: {exc}"))
        case["status"] = "passed" if all(o["passed"] for o in case["observations"]) else "failed"
        if reference_executable and case.get("reference", {}).get("status") != "passed":
            case["status"] = "failed"
        case["first_elapsed_ns"] = case["observations"][0]["elapsed_ns"]
        case["warm_median_elapsed_ns"] = statistics.median(o["elapsed_ns"] for o in case["observations"][1:])
        cases.append(case)
    direct = None
    if include_direct_abi:
        from .qualification import run_qualification_suite
        direct = run_qualification_suite(library, repetitions=repetitions, wall_steps=20)
    discovered = shutil.which("ngspice")
    reference_identity = {}
    if reference_executable:
        reference_identity = dict(executable_sha256=hashlib.sha256(reference_executable.read_bytes()).hexdigest())
        try:
            from python.spike_core.ngspice_plugin import _version
            reference_identity["version"] = _version(str(reference_executable))
        except ImportError as exc:
            reference_identity.update(version="unavailable", dependency_error=str(exc))
    passed = sum(c["status"] == "passed" for c in cases)
    return dict(contract="spikes/deck-qualification/v1", generated_at=datetime.now(timezone.utc).isoformat(),
        library=str(library), library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
        host=dict(platform=platform.platform(), python=platform.python_version()),
        status="passed" if passed == len(cases) and (direct is None or direct["status"] == "passed") else "failed",
        summary=dict(total=len(cases), passed=passed, failed=len(cases)-passed), cases=cases,
        direct_abi=direct, reference_engine=dict(name="ngspice", **reference_identity, executable=str(reference_executable) if reference_executable else discovered,
            status=("passed" if all(c.get("reference", {}).get("status") == "passed" for c in cases) else "failed") if reference_executable else ("not_run" if discovered else "unavailable_on_PATH")),
        claims=dict(full_spice_parity=False, competitive_speed=False, physical_hil=False),
        limitations=["This small textual corpus does not qualify manufacturer models or complete SPICE grammar.",
          "First measurement is first in-process execution, not a cold OS/cache measurement.",
          "Memory and peak RSS are not measured. No cross-engine timing is inferred.",
          "Reference uses identical circuit/model values with tighter explicit ngspice tolerances and a maximum step matching native output spacing; solver tolerances are not claimed equal.",
          "Full native traces are compared by linear interpolation inside reference coverage; a missing UIC t=0 is reported and excluded, never extrapolated.",
          "Diode fixture qualifies static Shockley behavior only, not charge, recovery, noise or breakdown."])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--repetitions", default=2, type=int)
    parser.add_argument("--include-direct-abi", action="store_true")
    parser.add_argument("--ngspice", type=Path, help="Explicit reference executable; never replaces owned C++ execution")
    parser.add_argument("-o", "--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; choose a fresh evidence path")
    report = run_deck_qualification(args.library, repetitions=args.repetitions,
                                    include_direct_abi=args.include_direct_abi, ngspice=args.ngspice)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(status=report["status"], summary=report["summary"], output=str(args.output))))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
