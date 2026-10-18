# SPDX-License-Identifier: Apache-2.0
"""Measure owned RC/RL timestep error against an independently derived ramp solution."""
from __future__ import annotations

import argparse
import ast
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]

AMPLITUDE_CONTRACT = "spike/circuit-amplitude-timestep-accuracy/v2"
AMPLITUDE_SCALES = (1.0, -1.0, 1.0e-3, -1.0e-3, 1.0e-6, -1.0e-6, 0.0)
TIME_STEPS_S = (1.0e-6, 5.0e-7, 2.5e-7)
RISE_TIME_S = 1.0e-5
STOP_TIME_S = 1.01e-3
RELATIVE_TOLERANCE = 5.0e-6
ABSOLUTE_TOLERANCES = {"voltage": 1.0e-12, "current": 1.0e-15}
SOURCE_PATHS = (
    "scripts/benchmark_circuit_timestep_accuracy.py",
    "python/spikes/native_runner.py",
    "python/spikes/cli.py",
    "python/spikes/native_abi.py",
    "python/spikes/netlist.py",
    "python/spikes/contracts.py",
    "python/spikes/transient_controls.py",
    "python/spikes/version.py",
    "src/spikes/c_api.cpp",
    "src/spikes/c_api.h",
    "src/spikes/dc_solver.cpp",
    "src/spikes/dc_solver.hpp",
    "src/spikes/transient_session.cpp",
    "src/spikes/transient_session.hpp",
    "src/spikes/transient_solver.cpp",
    "src/spikes/transient_solver.hpp",
    "CMakeLists.txt",
)


def ramp_response(time_s: float, rise_s: float, tau_s: float) -> float:
    """Solve tau*y' + y = min(t/rise, 1), y(0)=0, for t >= rise."""
    if not all(math.isfinite(v) and v > 0 for v in (time_s, rise_s, tau_s)) or time_s < rise_s:
        raise ValueError("Require finite positive times and sample at or after ramp end")
    # At ramp end y = 1 - tau/rise*(1-exp(-rise/tau)); propagate
    # the remaining distance to the unit equilibrium exactly.
    return 1 + tau_s / rise_s * math.expm1(-rise_s / tau_s) * math.exp(-(time_s - rise_s) / tau_s)


def ramp_response_all_times(time_s: float, rise_s: float, tau_s: float) -> float:
    """Exact unit response of ``tau*y' + y = min(t/rise, 1)`` for t >= 0."""
    if not all(math.isfinite(v) for v in (time_s, rise_s, tau_s)):
        raise ValueError("Times must be finite")
    if time_s < 0.0 or rise_s <= 0.0 or tau_s <= 0.0:
        raise ValueError("Require nonnegative sample time and positive rise/tau")
    if time_s <= rise_s:
        return time_s / rise_s + tau_s / rise_s * math.expm1(-time_s / tau_s)
    return ramp_response(time_s, rise_s, tau_s)


def exact_observables(case_id: str, time_s: float, excitation_v: float) -> dict[str, float]:
    """Return independently derived voltage/current references in SI units."""
    if not math.isfinite(excitation_v):
        raise ValueError("Excitation must be finite")
    response = ramp_response_all_times(time_s, RISE_TIME_S, 1.0e-3)
    source_v = excitation_v * min(time_s / RISE_TIME_S, 1.0)
    if case_id == "rc":
        voltage_v = excitation_v * response
        current_a = (source_v - voltage_v) / 1.0e3
    elif case_id == "rl":
        current_a = excitation_v * response / 1.0
        voltage_v = current_a * 1.0
    else:
        raise ValueError(f"Unknown circuit case: {case_id}")
    return {"voltage_v": voltage_v, "current_a": current_a}


def assess_waveforms(
    case_id: str,
    excitation_v: float,
    times_s: Sequence[float],
    observed_voltage_v: Sequence[float],
    observed_current_a: Sequence[float],
) -> dict[str, Any]:
    """Apply the frozen pointwise absolute-plus-relative voltage/current gates."""
    if not times_s or len(times_s) != len(observed_voltage_v) or len(times_s) != len(observed_current_a):
        raise ValueError("Time, voltage and current waveforms must have one common nonzero length")
    numeric = tuple(times_s) + tuple(observed_voltage_v) + tuple(observed_current_a)
    if not all(math.isfinite(float(value)) for value in numeric):
        raise ValueError("Waveforms must contain only finite values")
    if any(float(right) <= float(left) for left, right in zip(times_s, times_s[1:])):
        raise ValueError("Physical sample times must be strictly increasing")

    references = [exact_observables(case_id, float(time_s), excitation_v) for time_s in times_s]
    definitions = (
        ("voltage", "V", "voltage_v", observed_voltage_v, ABSOLUTE_TOLERANCES["voltage"], abs(excitation_v)),
        ("current", "A", "current_a", observed_current_a, ABSOLUTE_TOLERANCES["current"],
         abs(excitation_v) / (1.0e3 if case_id == "rc" else 1.0)),
    )
    observables: dict[str, Any] = {}
    for name, unit, reference_key, observations, absolute_tolerance, normalization_scale in definitions:
        errors = [abs(float(observed) - reference[reference_key])
                  for observed, reference in zip(observations, references, strict=True)]
        tolerances = [absolute_tolerance + RELATIVE_TOLERANCE * abs(reference[reference_key])
                      for reference in references]
        worst_index = max(range(len(errors)), key=lambda index: errors[index] / tolerances[index])
        maximum_error = max(errors)
        observables[name] = {
            "unit": unit,
            "absolute_tolerance": absolute_tolerance,
            "relative_tolerance": RELATIVE_TOLERANCE,
            "passed": all(error <= tolerance for error, tolerance in zip(errors, tolerances, strict=True)),
            "maximum_absolute_error": maximum_error,
            "normalization_scale": normalization_scale if normalization_scale > 0.0 else None,
            "maximum_normalized_error": (
                maximum_error / normalization_scale if normalization_scale > 0.0 else None
            ),
            "maximum_error_to_tolerance": max(error / tolerance for error, tolerance in zip(errors, tolerances, strict=True)),
            "worst_time_s": float(times_s[worst_index]),
            "worst_observed": float(observations[worst_index]),
            "worst_reference": references[worst_index][reference_key],
            "worst_absolute_error": errors[worst_index],
            "worst_tolerance": tolerances[worst_index],
        }
    return {
        "sample_count": len(times_s),
        "first_time_s": float(times_s[0]),
        "last_time_s": float(times_s[-1]),
        "observables": observables,
        "gate_status": "passed" if all(item["passed"] for item in observables.values()) else "failed",
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _absolute_existing_file(path: Path) -> Path:
    """Avoid Windows final-handle canonicalization, which can reject loadable DLLs."""
    candidate = Path(os.path.abspath(path))
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def _source_hashes() -> dict[str, str | None]:
    return {relative: _sha256(ROOT / relative) if (ROOT / relative).is_file() else None
            for relative in SOURCE_PATHS}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="ascii")


def _abi_version(library: Path) -> int:
    loaded = ctypes.CDLL(str(library))
    loaded.spikes_abi_version.argtypes = ()
    loaded.spikes_abi_version.restype = ctypes.c_uint32
    return int(loaded.spikes_abi_version())


def _semantic_engine_version() -> str:
    version_path = ROOT / "python/spikes/version.py"
    tree = ast.parse(version_path.read_text(encoding="utf-8"), filename=str(version_path))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ENGINE_VERSION"
            for target in statement.targets
        ):
            if isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
                return statement.value.value
    raise ValueError("python/spikes/version.py does not declare a literal ENGINE_VERSION")


def _case_definition(case_id: str) -> tuple[str, str, str]:
    if case_id == "rc":
        return "R1 in out 1k\nC1 out 0 1u", "V(out)", "I(R1)"
    if case_id == "rl":
        return "R1 in out 1\nL1 out 0 1m", "V(in,out)", "I(L1)"
    raise ValueError(f"Unknown circuit case: {case_id}")


def _scale_label(scale: float) -> str:
    if scale == 0.0:
        return "zero"
    return ("p" if scale > 0 else "n") + format(abs(scale), ".0e").replace("+", "").replace("-", "m")


def _run_amplitude_stratum(
    library: Path,
    output: Path,
    case_id: str,
    excitation_v: float,
    step_s: float,
    step_index: int,
    requested_abi_version: int,
    source_hashes_before: dict[str, str | None],
    integration_method: str = "hybrid_trapezoidal",
) -> dict[str, Any]:
    elements, voltage_probe, current_probe = _case_definition(case_id)
    stem = f"{case_id}-{_scale_label(excitation_v)}-step-{step_index}"
    deck = (
        f"* ACC01 {case_id} exact finite-ramp amplitude fixture\n"
        f"V1 in 0 PULSE(0 {excitation_v:.17g} 0 10u 10u 10m 20m)\n"
        f"{elements}\n.tran {step_s:.17g} 1.01m\n.end\n"
    )
    deck_path = output / f"{stem}.cir"
    deck_path.write_text(deck, encoding="ascii")
    raw_output_path = output / f"{stem}.stdout.json"
    stderr_path = output / f"{stem}.stderr.txt"
    request_path = output / f"{stem}.request.json"
    command = [
        sys.executable, "-m", "python.spikes", "native-run", str(deck_path.resolve()),
        "--library", str(library), "--probe", voltage_probe, "--probe", current_probe,
        "--method", {"hybrid_trapezoidal": "trap", "backward_euler": "be"}.get(integration_method, integration_method),
    ]
    input_hash_before = _sha256(deck_path)
    request = {
        "contract": "spike/circuit-amplitude-request/v1",
        "case_id": case_id,
        "excitation_v": excitation_v,
        "requested_step_s": step_s,
        "requested_physical_stop_s": STOP_TIME_S,
        "requested_probes": {"voltage": voltage_probe, "current": current_probe},
        "requested_backend": {
            "solver": "SPIKES owned C++ kernel",
            "transport": "python.spikes native-run",
            "integration": integration_method,
            "c_abi_version": requested_abi_version,
            "library": str(library),
        },
        "command": command,
        "cwd": str(ROOT),
        "input": str(deck_path.resolve()),
        "input_sha256_before": input_hash_before,
        "source_sha256_before": source_hashes_before,
    }
    _write_json(request_path, request)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            timeout=60,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        stdout = exc.stdout if isinstance(exc, subprocess.TimeoutExpired) and exc.stdout else b""
        stderr = exc.stderr if isinstance(exc, subprocess.TimeoutExpired) and exc.stderr else str(exc).encode("utf-8")
        raw_output_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        return {
            "case_id": case_id,
            "excitation_v": excitation_v,
            "requested_step_s": step_s,
            "qualification_gate_applied": step_s == TIME_STEPS_S[-1],
            "request": request_path.name,
            "request_sha256": _sha256(request_path),
            "raw_output": raw_output_path.name,
            "raw_output_sha256": _sha256(raw_output_path),
            "stderr": stderr_path.name,
            "stderr_sha256": _sha256(stderr_path),
            "input": deck_path.name,
            "input_sha256_before": input_hash_before,
            "input_sha256_after": _sha256(deck_path),
            "returncode": None,
            "status": "failed",
            "gate_status": "failed",
            "failure": {"type": type(exc).__name__, "message": str(exc)},
        }
    raw_output_path.write_bytes(completed.stdout)
    stderr_path.write_bytes(completed.stderr)
    input_hash_after = _sha256(deck_path)
    record: dict[str, Any] = {
        "case_id": case_id,
        "excitation_v": excitation_v,
        "requested_step_s": step_s,
        "qualification_gate_applied": step_s == TIME_STEPS_S[-1],
        "request": request_path.name,
        "request_sha256": _sha256(request_path),
        "raw_output": raw_output_path.name,
        "raw_output_sha256": _sha256(raw_output_path),
        "stderr": stderr_path.name,
        "stderr_sha256": _sha256(stderr_path),
        "input": deck_path.name,
        "input_sha256_before": input_hash_before,
        "input_sha256_after": input_hash_after,
        "returncode": completed.returncode,
    }
    try:
        payload = json.loads(completed.stdout)
        record["executed_backend"] = {
            "solver": payload.get("provenance", {}).get("solver"),
            "implementation": payload.get("provenance", {}).get("implementation"),
            "integration": payload.get("provenance", {}).get("integration"),
            "owned_cpp_transient": payload.get("provenance", {}).get("owned_cpp_transient"),
            "library": payload.get("provenance", {}).get("library"),
            "c_abi_version": requested_abi_version,
        }
        backend_matches = (
            record["executed_backend"]["solver"] == "SPIKES owned C++ kernel"
            and record["executed_backend"]["owned_cpp_transient"] is True
            and record["executed_backend"]["integration"] == integration_method
            and Path(record["executed_backend"]["library"] or "").resolve() == library
        )
        if completed.returncode != 0 or payload.get("status") != "completed":
            raise RuntimeError(f"native-run returned status {payload.get('status')!r}")
        times = payload["data"]["time_s"]
        voltage_values = payload["probes"][voltage_probe]["values"]
        current_values = payload["probes"][current_probe]["values"]
        assessment = assess_waveforms(case_id, excitation_v, times, voltage_values, current_values)
        if abs(float(times[-1]) - STOP_TIME_S) > 1.0e-14:
            raise ValueError("Solver did not return the prescribed physical stop time")
        record.update(assessment)
        record["diagnostics"] = payload.get("diagnostics", {})
        record["backend_identity_status"] = "matched" if backend_matches else "inconclusive"
        record["status"] = (
            "failed" if assessment["gate_status"] == "failed"
            else "inconclusive" if not backend_matches or input_hash_before != input_hash_after
            else "passed"
        )
    except (KeyError, TypeError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        record.update({
            "status": "failed",
            "gate_status": "failed",
            "failure": {"type": type(exc).__name__, "message": str(exc)},
        })
    return record


def _qualification_summary(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    finest = [record for record in records if record["qualification_gate_applied"]]
    for case_id in ("rc", "rl"):
        case_summary: dict[str, Any] = {}
        for observable in ("voltage", "current"):
            complete = [record for record in finest
                        if record["case_id"] == case_id and "observables" in record]
            passing_nonzero = [abs(record["excitation_v"]) for record in complete
                               if record["excitation_v"] != 0.0
                               and record["observables"][observable]["passed"]]
            zero = next((record for record in complete if record["excitation_v"] == 0.0), None)
            nonzero_errors = [
                record["observables"][observable]["maximum_absolute_error"]
                for record in complete if record["excitation_v"] != 0.0
            ]
            case_summary[observable] = {
                "unit": "V" if observable == "voltage" else "A",
                "minimum_verified_excitation_magnitude_v": min(passing_nonzero) if passing_nonzero else None,
                "zero_input_passed": zero["observables"][observable]["passed"] if zero else False,
                "zero_input_maximum_absolute_error": (
                    zero["observables"][observable]["maximum_absolute_error"] if zero else None
                ),
                "minimum_observed_nonzero_maximum_absolute_error": (
                    min(nonzero_errors) if nonzero_errors else None
                ),
            }
        summary[case_id] = case_summary
    return summary


def run_amplitude(library: Path, output: Path, *, integration_method="hybrid_trapezoidal") -> dict[str, Any]:
    """Execute frozen ACC01 gates with an explicitly identified integration method."""
    if integration_method not in ("hybrid_trapezoidal", "backward_euler", "bdf2", "radau_iia3"):
        raise ValueError("Explicit supported integration method required")
    library = _absolute_existing_file(library)
    if output.exists():
        raise ValueError("Output directory must be new to preserve prior evidence")
    output.mkdir(parents=True)
    library_hash_before = _sha256(library)
    sources_before = _source_hashes()
    abi_version_before = _abi_version(library)
    records = []
    for case_id in ("rc", "rl"):
        for excitation_v in AMPLITUDE_SCALES:
            for step_index, step_s in enumerate(TIME_STEPS_S):
                records.append(_run_amplitude_stratum(
                    library, output, case_id, excitation_v, step_s, step_index,
                    abi_version_before, sources_before,
                    integration_method,
                ))

    library_hash_after = _sha256(library)
    sources_after = _source_hashes()
    abi_version_after = _abi_version(library)
    changed_sources = [path for path in SOURCE_PATHS if sources_before[path] != sources_after[path]]
    binding_status = "conclusive" if (
        library_hash_before == library_hash_after
        and abi_version_before == abi_version_after
        and not changed_sources
        and all(record["input_sha256_before"] == record["input_sha256_after"] for record in records)
        and all(record.get("backend_identity_status") == "matched" for record in records)
    ) else "inconclusive"
    finest = [record for record in records if record["qualification_gate_applied"]]
    numerical_status = "passed" if all(record.get("gate_status") == "passed" for record in finest) else "failed"
    status = numerical_status if numerical_status == "failed" else (
        "inconclusive" if binding_status == "inconclusive" else "passed"
    )
    report = {
        "contract": AMPLITUDE_CONTRACT,
        "status": status,
        "numerical_status": numerical_status,
        "binding_status": binding_status,
        "requested_backend": {
            "solver": "SPIKES owned C++ kernel",
            "transport": "python.spikes native-run",
            "integration": integration_method,
            "c_abi_version": abi_version_before,
            "library": str(library),
        },
        "executed_identity": {
            "semantic_engine_version": _semantic_engine_version(),
            "semantic_version_scope": "Python/native orchestration source; the shared library exports ABI identity only",
            "c_abi_version_before": abi_version_before,
            "c_abi_version_after": abi_version_after,
            "library_sha256_before": library_hash_before,
            "library_sha256_after": library_hash_after,
            "source_sha256_before": sources_before,
            "source_sha256_after": sources_after,
            "changed_sources": changed_sources,
        },
        "matrix": {
            "case_ids": ["rc", "rl"],
            "signed_excitation_v": list(AMPLITUDE_SCALES),
            "requested_steps_s": list(TIME_STEPS_S),
            "rise_time_s": RISE_TIME_S,
            "stop_time_s": STOP_TIME_S,
        },
        "acceptance": {
            "applies_to_requested_step_s": TIME_STEPS_S[-1],
            "pointwise_rule": "abs(observed-reference) <= absolute_tolerance + 5e-6*abs(reference)",
            "voltage_absolute_tolerance_v": ABSOLUTE_TOLERANCES["voltage"],
            "current_absolute_tolerance_a": ABSOLUTE_TOLERANCES["current"],
            "coarser_strata": "Gate results retained for diagnosis; report qualification status is determined by finest strata",
        },
        "qualification_summary": _qualification_summary(records),
        "strata": records,
        "limitations": [
            "Two passive first-order circuits only; no nonlinear or arbitrary-waveform qualification.",
            "The semantic version describes checked orchestration source; this binary exports ABI v1 but no semantic version string.",
            "The fixed-step default and solver tolerances are unchanged; this benchmark does not qualify adaptive LTE control.",
        ],
        "derivation": (
            "For 0<=t<=rise, y=t/rise+(tau/rise)*expm1(-t/tau); after rise, "
            "propagate the exact ramp-end state. RC: Vout=A*y and I=(Vin-Vout)/R. "
            "RL: I=A*y/R and VR=R*I. All comparisons use returned physical sample times."
        ),
    }
    _write_json(output / "report.json", report)
    return report


def run(library: Path, output: Path) -> dict:
    library = _absolute_existing_file(library)
    library_digest = hashlib.sha256(library.read_bytes()).hexdigest()
    if output.exists():
        raise ValueError("Output directory must be new to preserve prior evidence")
    output.mkdir(parents=True)
    expected = ramp_response(1.01e-3, 1e-5, 1e-3)
    records = []
    for kind, elements, probe in (
        ("rc", "R1 in out 1k\nC1 out 0 1u", "V(out)"),
        ("rl", "R1 in out 1\nL1 out 0 1m", "V(in,out)"),
    ):
        levels = []
        for index, step in enumerate((1e-6, 5e-7, 2.5e-7)):
            deck = (f"* Original {kind} finite-ramp fixture\n"
                    "V1 in 0 PULSE(0 1 0 10u 10u 10m 20m)\n"
                    f"{elements}\n.tran {step:.17g} 1.01m\n.end\n")
            deck_path = output / f"{kind}-{index}.cir"
            deck_path.write_text(deck, encoding="ascii")
            completed = subprocess.run(
                [sys.executable, "-m", "python.spikes", "native-run", str(deck_path.resolve()),
                 "--library", str(library), "--probe", probe],
                cwd=ROOT, capture_output=True, timeout=60, shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw_path = output / f"{kind}-{index}.json"
            raw_path.write_bytes(completed.stdout)
            (output / f"{kind}-{index}.stderr.txt").write_bytes(completed.stderr)
            payload = json.loads(completed.stdout)
            if completed.returncode or payload.get("status") != "completed":
                raise RuntimeError(f"{kind} level {index} failed; see {raw_path}")
            times = payload["data"]["time_s"]
            values = payload["probes"][probe]["values"]
            if len(times) != len(values) or not times or abs(times[-1] - 1.01e-3) > 1e-14:
                raise ValueError("Solver did not return the prescribed endpoint")
            observed = float(values[-1])
            if not math.isfinite(observed):
                raise ValueError("Nonfinite solver observation")
            levels.append({"requested_step_s": step, "observed_v": observed,
                           "absolute_error_v": abs(observed - expected),
                           "effective_integration_step_s": payload["diagnostics"].get("effective_integration_step_s"),
                           "integration_counts": {k: payload["diagnostics"].get(k) for k in
                                                  ("backward_euler_steps", "trapezoidal_steps", "bdf2_steps")},
                           "deck_sha256": hashlib.sha256(deck.encode("ascii")).hexdigest(),
                           "raw_result": raw_path.name,
                           "raw_result_sha256": hashlib.sha256(completed.stdout).hexdigest()})
        errors = [v["absolute_error_v"] for v in levels]
        orders = [math.log(a / b, 2) if a > 0 and b > 0 else None
                  for a, b in zip(errors, errors[1:])]
        passed = all(b < a for a, b in zip(errors, errors[1:])) and errors[-1] <= 5e-5
        records.append({"case_id": kind, "expected_v": expected, "levels": levels,
                        "observed_orders": orders, "status": "passed" if passed else "failed"})
    if hashlib.sha256(library.read_bytes()).hexdigest() != library_digest:
        raise RuntimeError("Native library changed during the benchmark; run is not admissible")
    report = {"contract": "spike/circuit-timestep-accuracy/v1",
              "status": "passed" if all(r["status"] == "passed" for r in records) else "failed",
              "library": str(library), "library_sha256": library_digest,
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "python": sys.version, "cases": records,
              "acceptance": "Strictly decreasing endpoint error; finest error <= 5e-5 V, declared before run",
              "limitations": ["Two passive first-order circuits only; no nonlinear or arbitrary-waveform qualification.",
                              "Requested .tran resolution may differ from internal integration steps; raw diagnostics retained.",
                              "Observed order concerns this endpoint and these settings; it is not a global method-order claim."],
              "derivation": "For a unit linear ramp, integrate tau*y'+y=t/rise; then propagate y'= (1-y)/tau after rise."}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("historical", "amplitude"),
        default="historical",
        help="Preserve the historical v1 endpoint benchmark by default; select amplitude for ACC01 v2.",
    )
    parser.add_argument("--method", choices=("hybrid_trapezoidal", "backward_euler", "bdf2", "radau_iia3"),
                        default=None, help="Explicit amplitude-mode method; gates and reporting grid are unchanged.")
    args = parser.parse_args()
    if args.method is not None and args.mode != "amplitude":
        parser.error("--method requires --mode amplitude; historical v1 controls are unchanged")
    report = (
        run_amplitude(args.library, args.output, integration_method=args.method or "hybrid_trapezoidal")
        if args.mode == "amplitude"
        else run(args.library, args.output)
    )
    detail_key = "strata" if args.mode == "amplitude" else "cases"
    print(json.dumps({"status": report["status"], detail_key: report[detail_key]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
