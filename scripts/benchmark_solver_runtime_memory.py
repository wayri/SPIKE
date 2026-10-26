# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Fresh-process speed, memory, and equivalence benchmark for AC/flowing CHT.

This records observations; it does not invent resource acceptance thresholds or
change the physical and numerical acceptance gates owned by the source benchmark.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "OPENBLAS_DEFAULT_NUM_THREADS",
    "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS",
    "NUMEXPR_MAX_THREADS", "BLIS_NUM_THREADS", "SPIKE_CPU_THREADS",
    "SPIKE_BLAS_THREADS", "NUMBA_NUM_THREADS", "OMP_MAX_ACTIVE_LEVELS", "MKL_DOMAIN_NUM_THREADS",
)
SOURCES = (
    "scripts/benchmark_solver_runtime_memory.py",
    "scripts/benchmark_em_network_cht.py",
    "python/spike_core/process_memory_observation.py",
    "python/spike_core/numerical_runtime.py",
    "python/spike_core/solvers/execution/coupling/em_network_ac.py",
    "python/spike_core/solvers/execution/coupling/em_network_resistor_cht.py",
    "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_cht.py",
    "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_mesh.py",
    "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_stokes.py",
    "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_energy.py",
    "tests/python/test_em_network_resistor_cht.py",
    "tests/python/test_cfd_tetra_cht.py",
    "tests/python/test_em_network_cosimulation.py",
)


def _hash_sources() -> dict[str, str]:
    missing = [name for name in SOURCES if not (ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError(f"benchmark source missing: {', '.join(missing)}")
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


def _child_run(configuration: str) -> dict[str, object]:
    # The parent establishes the environment before this fresh interpreter is
    # created. Keep numerical packages out of module-level imports.
    sys.path.insert(0, str(ROOT))
    from python.spike_core.process_memory_observation import observe_process_memory
    before_import = observe_process_memory()
    import numpy as np
    import scipy
    from scripts.benchmark_em_network_cht import run_level
    from python.spike_core.solvers.execution.coupling.em_network_ac import solve_em_network_ac, REQUEST_CONTRACT, WAVE_CONVENTION
    after_import = observe_process_memory()

    frequencies = [1.0e6 + i * 1.0e5 for i in range(64)]
    source_rows = [[[{"real": 0.0, "imag": 0.0}]] for _ in frequencies]
    boundaries = [{"p0": {"voltage_v": [2.0, 0.0], "impedance_ohm": [50.0, 0.0]}}
                  for _ in frequencies]
    ac_request = {
        "contract": REQUEST_CONTRACT, "wave_convention": WAVE_CONVENTION,
        "source": {"id": "analytic-matched-one-port", "port_names": ["p0"],
                   "reference_impedance_ohm": 50.0, "frequencies_hz": frequencies,
                   "s_parameters": source_rows},
        "boundaries": boundaries,
    }
    started = time.perf_counter()
    ac_result = solve_em_network_ac(ac_request)
    cht_request, cht_result, cht = run_level(2, flowing=True)
    elapsed = time.perf_counter() - started
    after_solve = observe_process_memory()

    # Independent matched-load result: Vs=2 Vrms divides equally across two
    # 50 ohm resistances, so V=1 V, I=.02 A, and each resistance dissipates .02 W.
    ac_errors = []
    for sample in ac_result["samples"]:
        voltage = complex(*sample["voltage_rms_v"][0])
        current = complex(*sample["current_into_network_rms_a"][0])
        ac_errors.extend((abs(voltage - 1.0), abs(current - 0.02),
                          abs(sample["series_resistor_power_w"][0] - 0.02),
                          abs(sample["unclassified_network_power_w"] - 0.02)))
    accuracy = {
        "ac_max_absolute_error": max(ac_errors),
        "cht_relative_rise_l2_error": cht["relative_rise_l2_error"],
        "cht_cell_energy_relative_defect": cht["energy"]["cell_energy_relative_defect"],
        "cht_global_energy_relative_defect": cht["energy"]["global_energy_relative_defect"],
        "cht_mixed_relative_residual": cht["energy"]["mixed_relative_residual"],
        "cht_maximum_face_mass_flow_kg_s": cht["maximum_face_mass_flow_kg_s"],
    }
    return {
        "configuration": configuration, "elapsed_seconds": elapsed,
        "memory": {"before_import": before_import, "after_import": after_import,
                   "after_solve": after_solve},
        "accuracy": accuracy,
        "input_sha256": {
            "ac": sha256(json.dumps(ac_request, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "cht": sha256(json.dumps(cht_request, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        },
        "equivalence_payload": {
            "ac_voltage_rms_v": [sample["voltage_rms_v"] for sample in ac_result["samples"]],
            "ac_current_into_network_rms_a": [sample["current_into_network_rms_a"] for sample in ac_result["samples"]],
            "cht_temperature_k": cht_result["cht"]["fields"]["energy"]["temperature_k"],
            "cht_face_mass_flow_kg_s": cht_result["cht"]["fields"]["face_mass_flow_kg_s"],
        },
        "runtime": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__},
        "thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
    }


def _environment(configuration: str) -> dict[str, str]:
    base = dict(os.environ)
    if configuration == "backend-default":
        for name in THREAD_VARIABLES:
            base.pop(name, None)
        return base
    sys.path.insert(0, str(ROOT))
    from python.spike_core.numerical_runtime import numerical_child_environment
    return numerical_child_environment(cpu_threads=1, blas_threads=1, base=base)


def _run_child(configuration: str, timeout: float) -> dict[str, object]:
    command = [sys.executable, str(Path(__file__).resolve()), "--child", configuration]
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        completed = subprocess.run(command, cwd=ROOT, env=_environment(configuration),
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   shell=False, timeout=timeout, check=False)
        stdout_size, stderr_size = stdout.tell(), stderr.tell()
        if stdout_size > 1024 * 1024 or stderr_size > 1024 * 1024:
            raise RuntimeError(f"{configuration} child output exceeded 1 MiB bound")
        stdout.seek(0); stderr.seek(0)
        stdout_text = stdout.read().decode("utf-8", errors="replace")
        stderr_text = stderr.read().decode("utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError(f"{configuration} child failed ({completed.returncode}): {stderr_text[-2000:]}")
    try:
        return json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{configuration} child emitted invalid JSON: {stdout_text[-1000:]}") from exc


def _median_summary(samples: list[dict[str, object]]) -> dict[str, object]:
    elapsed = [float(sample["elapsed_seconds"]) for sample in samples]
    memory: dict[str, float | None] = {}
    for phase in ("before_import", "after_import", "after_solve"):
        for metric in ("resident_current_bytes", "resident_peak_bytes",
                       "private_commit_current_bytes", "private_commit_peak_bytes"):
            values = [sample["memory"][phase][metric] for sample in samples]
            present = [float(value) for value in values if value is not None]
            memory[f"{phase}.{metric}"] = statistics.median(present) if present else None
    return {"elapsed_seconds": statistics.median(elapsed), "memory_bytes": memory}


def _equivalent(actual, expected, *, rtol=1e-10, atol=1e-10) -> bool:
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(_equivalent(actual[key], value, rtol=rtol, atol=atol)
                        for key, value in expected.items()))
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(_equivalent(a, b, rtol=rtol, atol=atol)
                        for a, b in zip(actual, expected)))
    if isinstance(actual, (dict, list)):
        return False
    try:
        a, b = float(actual), float(expected)
    except (TypeError, ValueError):
        return False
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= atol + rtol * abs(b)


def _validate_parent_arguments(output: Path | None, samples: int, timeout: float) -> None:
    if output is None:
        raise ValueError("--output is required")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output}")
    if not 1 <= samples <= 20:
        raise ValueError("--samples must be in 1..20")
    if not math.isfinite(timeout) or not 0.0 < timeout <= 600.0:
        raise ValueError("--timeout-seconds must be finite and in (0, 600]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--child", choices=("backend-default", "explicit-one-thread"))
    args = parser.parse_args(argv)
    if args.child:
        print(json.dumps(_child_run(args.child), allow_nan=False, separators=(",", ":")))
        return 0
    try:
        _validate_parent_arguments(args.output, args.samples, args.timeout_seconds)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))

    source_before = _hash_sources()
    # One discarded warmup per configuration, then fresh alternating processes.
    warmups = [_run_child(name, args.timeout_seconds)
               for name in ("backend-default", "explicit-one-thread")]
    samples = {"backend-default": [], "explicit-one-thread": []}
    for _ in range(args.samples):
        for name in samples:
            samples[name].append(_run_child(name, args.timeout_seconds))
    source_after = _hash_sources()

    reference = samples["backend-default"][0]["equivalence_payload"]
    input_reference = samples["backend-default"][0]["input_sha256"]
    equivalent = True
    for group in samples.values():
        for sample in group:
            equivalent = equivalent and _equivalent(sample["equivalence_payload"], reference)
    gates = {
        "sources_unchanged": source_before == source_after,
        "ac_analytic_max_absolute_error_le_1e-12": all(
            sample["accuracy"]["ac_max_absolute_error"] <= 1e-12
            for group in samples.values() for sample in group),
        "cht_energy_defects_le_1e-9": all(
            max(sample["accuracy"]["cht_cell_energy_relative_defect"],
                sample["accuracy"]["cht_global_energy_relative_defect"]) <= 1e-9
            for group in samples.values() for sample in group),
        "cht_mixed_residual_le_1e-10": all(
            sample["accuracy"]["cht_mixed_relative_residual"] <= 1e-10
            for group in samples.values() for sample in group),
        "flow_is_nonzero": all(sample["accuracy"]["cht_maximum_face_mass_flow_kg_s"] > 0.0
                               for group in samples.values() for sample in group),
        "cross_configuration_numerically_equivalent": equivalent,
        "identical_input_digests": all(sample["input_sha256"] == input_reference
                                        for group in samples.values() for sample in group),
    }
    report = {
        "contract": "spike/solver-runtime-memory-benchmark/v1",
        "status": "passed" if all(gates.values()) else "failed",
        "scope": "synthetic sampled matched AC plus level-2 flowing analytical CHT",
        "resource_acceptance_thresholds": None,
        "accuracy_note": "Level 2 is profiled, so its L2 error is reported but is not substituted for the unchanged level-4 <=0.05 refinement gate.",
        "measurement_note": "Peak fields cover the child lifetime through both solves; missing OS metrics are null. Child stdout/stderr use temporary files and are rejected above 1 MiB before bounded reads, bounding parent memory rather than temporary disk growth.",
        "equivalence_tolerance": {"relative": 1e-10, "absolute": 1e-10},
        "machine": {"system": platform.system(), "release": platform.release(),
                    "machine": platform.machine(), "processor": platform.processor(),
                    "logical_cpu_count": os.cpu_count()},
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            shell=False, check=False, timeout=10.0).stdout.strip() or None,
        "source_sha256_before": source_before, "source_sha256_after": source_after,
        "warmups_discarded": warmups, "measured_samples_per_configuration": args.samples,
        "samples": samples,
        "medians": {name: _median_summary(group) for name, group in samples.items()},
        "gates": gates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output),
                      "medians": report["medians"], "gates": gates}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
