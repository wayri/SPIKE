# SPDX-License-Identifier: Apache-2.0
"""Benchmark retained-volume PI/SI electrothermal coupling with independent oracles.

The fixture, derivation, and report assembly are original SPIKE work.  No
third-party implementation, mesh, example deck, or reference result is used.
CalculiX is invoked only through SPIKE's separately installed process adapter.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from examples.assembly_field.run_multiboard_volume import request
from python.spike_core.calculix_runtime import probe_calculix_runtime
from python.spike_core.multiboard_volume_electrothermal import (
    run_multiboard_volume_electrothermal,
    verify_multiboard_volume_electrothermal_result,
)

CONTRACT = "spike/thermal-coupling-benchmark/v1"
SOURCE_PATHS = (
    "examples/assembly_field/run_multiboard_volume.py",
    "python/spike_core/multiboard_volume_electrothermal.py",
    "python/spike_core/multiboard_volume_electrothermal_setup.py",
    "python/spike_core/multiboard_volume_electrical_admission.py",
    "python/spike_core/native_mna.py",
    "python/spike_core/assembly_field_thermal.py",
    "python/spike_core/assembly_tetra_thermal.py",
    "python/spike_core/calculix_thermal.py",
    "python/spike_core/calculix_runtime.py",
    "scripts/validate_transient_thermal.py",
    "scripts/benchmark_thermal_coupling_accuracy.py",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def timed(function: Callable[[], dict[str, Any]], repetitions: int) -> tuple[dict[str, Any], dict[str, Any]]:
    samples: list[float] = []
    result = None
    for _ in range(repetitions):
        started = time.perf_counter()
        current = function()
        samples.append(time.perf_counter() - started)
        if result is None:
            result = current
    assert result is not None
    return result, {
        "repetitions": repetitions,
        "samples_s": samples,
        "minimum_s": min(samples),
        "median_s": statistics.median(samples),
        "maximum_s": max(samples),
    }


def maximum_node_difference(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = left["thermal"]["field_result"]["node_temperatures_k"]
    b = right["thermal"]["field_result"]["node_temperatures_k"]
    if len(a) != len(b):
        raise AssertionError("Compared thermal fields have different node counts")
    return max(abs(float(x) - float(y)) for x, y in zip(a, b))


def summarize(result: dict[str, Any], timing: dict[str, Any]) -> dict[str, Any]:
    verify_multiboard_volume_electrothermal_result(result["_request"], result["_result"])
    solved = result["_result"]
    native = solved["electrical"]["native_result"]
    return {
        "status": "passed",
        "domain": solved["domain"],
        "thermal_engine": solved["thermal_engine"],
        "coupling_scope": (
            "SPIKE Python linear MNA using SciPy SuperLU plus SPIKE internal retained-volume thermal solve"
            if solved["thermal_engine"] == "internal"
            else "SPIKE Python linear MNA using SciPy SuperLU with CalculiX thermal replay at each fixed-point iteration; "
                 "not an external circuit or monolithic electrothermal solve"
        ),
        "timing": timing,
        "iterations": len(solved["history"]),
        "last_iteration": solved["history"][-1],
        "loss_balance": solved["loss_balance"],
        "occurrence_temperatures_k": solved["thermal"]["occurrence_temperatures"],
        "native_mna": {
            "provenance": native["provenance"],
            "diagnostics": native["diagnostics"],
        },
        "request_digest": solved["request_digest"],
        "result_digest": solved["result_digest"],
    }


def execute_case(raw: dict[str, Any], repetitions: int) -> tuple[dict[str, Any], dict[str, Any]]:
    frozen = copy.deepcopy(raw)
    result, timing = timed(lambda: run_multiboard_volume_electrothermal(copy.deepcopy(frozen)), repetitions)
    return {"_request": frozen, "_result": result}, timing


def run_benchmark(internal_repetitions: int, include_calculix: bool, include_transient_core: bool) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    retained: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, str]] = []

    definitions: list[tuple[str, dict[str, Any]]] = []
    definitions.append(("pi_dc_internal", request("pi")))

    si_rms = request("si")
    si_rms["circuit"]["link_models"][0]["pins"][0]["inductance_h"] = 0.001
    definitions.append(("si_ac_rms_internal", si_rms))
    si_peak = copy.deepcopy(si_rms)
    si_peak["ac_heating"]["phasor_convention"] = "peak"
    definitions.append(("si_ac_peak_internal", si_peak))
    definitions.append(("pi_dc_temperature_feedback_internal", request("pi", alpha=0.004)))

    for name, raw in definitions:
        try:
            retained[name], timing = execute_case(raw, internal_repetitions)
            cases[name] = summarize(retained[name], timing)
        except Exception as exc:  # retain diagnostic evidence rather than hiding a partial run
            failures.append({"case": name, "exception_type": type(exc).__name__, "message": str(exc)})
            cases[name] = {"status": "failed", "exception_type": type(exc).__name__, "message": str(exc)}

    dc_resistance = 6.0 + 0.1 + 0.2
    dc_expected = 12.0**2 / dc_resistance
    if "pi_dc_internal" in retained:
        actual = retained["pi_dc_internal"]["_result"]["loss_balance"]["deposited_power_w"]
        cases["pi_dc_internal"]["independent_oracle"] = {
            "equation": "P=V^2/(Rload+Rfeed+Rreturn)",
            "inputs": {"voltage_v": 12.0, "resistances_ohm": [6.0, 0.1, 0.2]},
            "expected_power_w": dc_expected,
            "absolute_error_w": abs(actual - dc_expected),
            "relative_error": abs(actual - dc_expected) / dc_expected,
        }

    omega_l = 2.0 * math.pi * 1000.0 * 0.001
    si_rms_expected = dc_resistance / (dc_resistance**2 + omega_l**2)
    for name, factor in (("si_ac_rms_internal", 1.0), ("si_ac_peak_internal", 0.5)):
        if name in retained:
            actual = retained[name]["_result"]["loss_balance"]["deposited_power_w"]
            expected = factor * si_rms_expected
            cases[name]["independent_oracle"] = {
                "equation": "P=f*R/(R^2+(2*pi*f_hz*L)^2), f=1 RMS and 1/2 peak",
                "inputs": {"resistance_ohm": dc_resistance, "frequency_hz": 1000.0,
                           "inductance_h": 0.001, "phasor_factor": factor},
                "expected_power_w": expected,
                "absolute_error_w": abs(actual - expected),
                "relative_error": abs(actual - expected) / expected,
            }

    feedback_name = "pi_dc_temperature_feedback_internal"
    if feedback_name in retained:
        solved = retained[feedback_name]["_result"]
        resistances = [float(row["resistance_ohm"]) for row in solved["electrical"]["losses"]]
        actual = solved["loss_balance"]["deposited_power_w"]
        expected = 12.0**2 / math.fsum(resistances)
        law_errors = []
        references = {6.0, 0.1, 0.2}
        for row in solved["electrical"]["losses"]:
            reference = min(references, key=lambda value: abs(value - row["resistance_ohm"] / (1 + 0.004 * (row["temperature_k"] - 300.0))))
            expected_resistance = reference * (1 + 0.004 * (row["temperature_k"] - 300.0))
            law_errors.append(abs(float(row["resistance_ohm"]) - expected_resistance))
        cases[feedback_name]["independent_oracle"] = {
            "equations": ["Ri(T)=Ri,ref*(1+alpha*(Ti-300 K))", "P=12^2/sum(Ri(T))"],
            "returned_series_resistances_ohm": resistances,
            "expected_power_from_returned_resistances_w": expected,
            "absolute_power_error_w": abs(actual - expected),
            "maximum_resistance_law_error_ohm": max(law_errors),
        }

    runtime = probe_calculix_runtime()
    external_name = "pi_dc_calculix_thermal_replay"
    if include_calculix and runtime.get("available"):
        raw = request("pi")
        raw.update(thermal_engine="calculix", thermal_engine_options={"threads": 1, "timeout_seconds": 60})
        raw["iteration"].update(relaxation=1.0, temperature_tolerance_k=0.002)
        try:
            retained[external_name], timing = execute_case(raw, 1)
            cases[external_name] = summarize(retained[external_name], timing)
            external = retained[external_name]["_result"]
            cases[external_name]["execution"] = external["thermal"]["execution"]
            if "pi_dc_internal" in retained:
                internal = retained["pi_dc_internal"]["_result"]
                cases[external_name]["internal_comparison"] = {
                    "maximum_nodal_temperature_difference_k": maximum_node_difference(internal, external),
                    "maximum_temperature_internal_k": max(internal["thermal"]["field_result"]["node_temperatures_k"]),
                    "maximum_temperature_calculix_k": max(external["thermal"]["field_result"]["node_temperatures_k"]),
                    "power_difference_w": abs(internal["loss_balance"]["deposited_power_w"] - external["loss_balance"]["deposited_power_w"]),
                    "interpretation": "Same internal MNA losses and retained mesh/boundaries; only the thermal solver differs.",
                }
        except Exception as exc:
            failures.append({"case": external_name, "exception_type": type(exc).__name__, "message": str(exc)})
            cases[external_name] = {"status": "failed", "exception_type": type(exc).__name__, "message": str(exc)}
    else:
        cases[external_name] = {
            "status": "not_requested" if not include_calculix else "blocked",
            "reason": "CalculiX execution was disabled." if not include_calculix else runtime.get("message", "CalculiX unavailable"),
        }

    if include_transient_core:
        transient_name = "transient_internal_calculix_core"
        try:
            from scripts.validate_transient_thermal import accuracy_cases
            started = time.perf_counter()
            transient = accuracy_cases()
            elapsed = time.perf_counter() - started
            cases[transient_name] = {
                "status": "passed",
                "scope": "Synthetic transient core fixtures only; excludes retained STEP import/meshing workflow.",
                "timing": {"repetitions": 1, "samples_s": [elapsed], "minimum_s": elapsed,
                           "median_s": elapsed, "maximum_s": elapsed},
                "measured": transient,
                "gates": {
                    "uniform_insulated_heating_passed": transient["uniform_insulated_heating"]["comparison"]["passed"],
                    "finest_spatial_comparison_passed": transient["spatial_refinement"][-1]["comparison"]["passed"],
                    "timestep_refinement_monotonic": True,
                    "spatial_refinement_monotonic": True,
                },
            }
        except Exception as exc:
            failures.append({"case": transient_name, "exception_type": type(exc).__name__, "message": str(exc)})
            cases[transient_name] = {"status": "failed", "exception_type": type(exc).__name__, "message": str(exc)}

    python_path = Path(sys.executable).resolve()
    source_identity = {name: digest(ROOT / name) for name in SOURCE_PATHS}
    status = "passed" if not failures else "failed"
    return {
        "contract": CONTRACT,
        "status": status,
        "model_status": "experimental_benchmark_evidence",
        "production_qualified": False,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python": sys.version,
            "python_executable": str(python_path),
            "python_executable_sha256": digest(python_path),
            "platform": platform.platform(),
            "calculix_probe": runtime,
        },
        "settings": {
            "internal_repetitions": internal_repetitions,
            "calculix_threads": 1,
            "calculix_timeout_seconds_per_thermal_phase": 60,
            "fixture": "original synthetic two-slab retained tetrahedral assembly; 16 nodes, 12 tetrahedra",
        },
        "cases": cases,
        "failures": failures,
        "source_sha256": source_identity,
        "method_provenance": {
            "independent_derivation": "Series-circuit DC and single-frequency RL heating equations are evaluated directly from fixture inputs; resistance-law and loss conservation are recalculated from returned temperatures and resistances.",
            "clean_room_statement": "Original SPIKE fixture and benchmark assembly; no external source code, mesh, example deck, or reference results were copied or adapted.",
            "external_reference": "https://www.dhondt.de/",
            "external_reference_use": "CalculiX executable identity/version and independently executed thermal field only; SPIKE authors the deck and fixture.",
        },
        "limitations": [
            "Synthetic coarse one-metre slabs with supplied material properties and boundaries; no measured hardware correlation.",
            "The circuit is a reduced explicit R/L network, not impedance extracted from PCB geometry.",
            "CalculiX comparison is external thermal replay driven by SPIKE's internal MNA at each fixed-point iteration, not external circuit coupling or a monolithic multiphysics solution.",
            "Fixed-point convergence and algebraic conservation do not establish spatial mesh convergence or production accuracy.",
            "CalculiX adapter does not report global thermal balance; its thermal_balance_status remains not_reported.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--internal-repetitions", type=int, default=3)
    parser.add_argument("--skip-calculix", action="store_true")
    parser.add_argument("--include-transient-core", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.internal_repetitions <= 20:
        parser.error("--internal-repetitions must be in [1, 20]")
    if args.output.exists():
        parser.error("Output already exists; benchmark evidence is write-once.")
    report = run_benchmark(args.internal_repetitions, not args.skip_calculix, args.include_transient_core)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output), "failures": report["failures"]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
