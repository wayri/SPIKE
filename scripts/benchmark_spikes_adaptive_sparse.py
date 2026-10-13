# SPDX-License-Identifier: Apache-2.0
"""Equal-input native microbenchmark; not a converter/grid qualification claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spikes.native_abi import load_native_library


CONTROLS = dict(time_step_s=20e-6, stop_time_s=200e-6,
                initialize_from_operating_point=False,
                integration_method="bdf2", adaptive_time_step=True,
                minimum_time_step_s=1e-10, lte_absolute_tolerance=1e-6,
                lte_relative_tolerance=1e-4)


def execute(library, branches: int, switching: bool):
    with library.circuit() as circuit:
        circuit.add_voltage_source("VS", "in", "0", 0.8)
        supply = "in"
        if switching:
            circuit.add_pulse_voltage_source(
                "VG", "gate", "0", initial_value=0., pulsed_value=5.,
                delay_s=20e-6, rise_time_s=1e-6, fall_time_s=1e-6,
                pulse_width_s=40e-6, period_s=100e-6)
            circuit.add_voltage_controlled_switch(
                "S", "in", "rail", "gate", "0",
                on_resistance_ohm=.1, off_resistance_ohm=1e6,
                threshold_voltage_v=2.5, transition_voltage_v=.1)
            supply = "rail"
        for index in range(branches):
            node = f"n{index}"
            circuit.add_resistor(f"R{index}", supply, node, 100. + index % 7)
            circuit.add_capacitor(f"C{index}", node, "0", 1e-6)
            circuit.add_diode(f"D{index}", node, "0")
        started = time.perf_counter()
        result = circuit.solve_transient(**CONTROLS)
        duration = time.perf_counter() - started
        with result:
            if result.status != "converged":
                raise RuntimeError(f"{library.path}: {result.status}: {result.message}")
            times = [result.time(i) for i in range(result.point_count)]
            traces = {name: [result.node_voltage(i, name) for i in range(result.point_count)]
                      for name in (f"n{index}" for index in range(branches))}
            return duration, times, traces, result.diagnostics()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-description", default="unspecified build; timing attribution is not qualified")
    parser.add_argument("--baseline-source", type=Path)
    parser.add_argument("--candidate-source", type=Path)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 50:
        parser.error("repeats must be 1 through 50")
    libraries = {label: load_native_library(path) for label, path in
                 (("baseline", args.baseline), ("candidate", args.candidate))}
    report = {"schema": "spikes/adaptive-sparse-microbenchmark/v1",
              "platform": platform.platform(), "python": sys.version,
              "processor": platform.processor(), "logical_cpus": os.cpu_count(),
              "controls": CONTROLS, "repeats": args.repeats,
              "baseline_description": args.baseline_description,
              "source_sha256": {
                  label: hashlib.sha256(path.read_bytes()).hexdigest()
                  for label, path in (("baseline", args.baseline_source),
                                      ("candidate", args.candidate_source)) if path is not None},
              "scope": "solve-call time only; DLL load, assembly and extraction excluded; no memory/thread/cross-engine qualification",
              "libraries": {label: {"path": str(lib.path),
                                     "sha256": hashlib.sha256(lib.path.read_bytes()).hexdigest()}
                            for label, lib in libraries.items()}, "cases": []}
    for branches, switching in ((16, False), (128, False), (128, True)):
        runs = {label: [] for label in libraries}
        cold = {}
        for label, lib in libraries.items():
            cold[label] = execute(lib, branches, switching)[0]
        # Alternate order to avoid always giving one build the warmer host.
        for repeat in range(args.repeats):
            labels = list(libraries)
            if repeat % 2:
                labels.reverse()
            for label in labels:
                runs[label].append(execute(libraries[label], branches, switching))
        time_error = voltage_error = 0.0
        for left, right in zip(runs["baseline"], runs["candidate"]):
            if len(left[1]) != len(right[1]):
                raise AssertionError("accepted grids differ; cannot claim unchanged trajectory")
            time_error = max(time_error, max(abs(a-b) for a, b in zip(left[1], right[1])))
            voltage_error = max(voltage_error, max(abs(a-b) for name in left[2]
                                                  for a, b in zip(left[2][name], right[2][name])))
        if time_error > 1e-12 or voltage_error > 1e-9:
            raise AssertionError(f"trajectory disagreement: {time_error=} {voltage_error=}")
        timings = {label: {"first_solve_s": cold[label],
                           "warm_solve_s": [run[0] for run in entries],
                           "median_warm_s": statistics.median(run[0] for run in entries),
                           "diagnostics": entries[0][3]}
                   for label, entries in runs.items()}
        report["cases"].append({"branches": branches, "smooth_switch": switching,
                                "max_time_difference_s": time_error,
                                "max_voltage_difference_v": voltage_error,
                                "runs": timings})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for case in report["cases"]:
        base = case["runs"]["baseline"]["median_warm_s"]
        candidate = case["runs"]["candidate"]["median_warm_s"]
        print(f'{case["branches"]} branches switching={case["smooth_switch"]}: '
              f'{base:.6f}s -> {candidate:.6f}s ({base/candidate:.3f}x)')


if __name__ == "__main__":
    main()
