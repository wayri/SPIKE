#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Build, verify, parity-check, and time the native transition-PI CDR reference.

The generated build is standalone and deliberately does not register the kernel
with SPIKE's production worker or Python bindings.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD_PARENT = ROOT / "build"
SOURCE_FILES = (
    ROOT / "src/solvers/signal_integrity/si/transition_pi_cdr.hpp",
    ROOT / "src/solvers/signal_integrity/si/transition_pi_cdr.cpp",
    ROOT / "tests/test_si_transition_pi_cdr.cpp",
    ROOT / "python/spike_core/solvers/signal_integrity/receivers/si_clock_recovery.py",
    Path(__file__).resolve(),
)
BENCHMARK_SIZES = (1_000, 30_000, 65_000)


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _fresh_build_dir(requested: Path | None) -> Path:
    DEFAULT_BUILD_PARENT.mkdir(parents=True, exist_ok=True)
    parent = DEFAULT_BUILD_PARENT.resolve()
    if requested is None:
        return Path(tempfile.mkdtemp(prefix="si-transition-pi-cdr-", dir=parent))
    target = requested.resolve()
    if not target.is_relative_to(parent):
        raise ValueError(f"--build-dir must be strictly under {parent}")
    if target == parent or target.exists():
        raise ValueError("--build-dir must name a fresh, non-existing subdirectory")
    target.mkdir(parents=True)
    return target


def _write_standalone_project(source_dir: Path) -> None:
    source_dir.mkdir()
    root = ROOT.as_posix()
    cmake_source = f"""cmake_minimum_required(VERSION 3.20)
project(spike_si_transition_pi_cdr_reference LANGUAGES CXX)
add_executable(test_si_transition_pi_cdr
    \"{root}/src/solvers/signal_integrity/si/transition_pi_cdr.cpp\"
    \"{root}/tests/test_si_transition_pi_cdr.cpp\")
target_include_directories(test_si_transition_pi_cdr PRIVATE \"{root}\")
target_compile_features(test_si_transition_pi_cdr PRIVATE cxx_std_20)
if(MSVC)
  target_compile_options(test_si_transition_pi_cdr PRIVATE /W4 /WX /permissive- /fp:strict)
else()
  target_compile_options(test_si_transition_pi_cdr PRIVATE
      -Wall -Wextra -Werror -Wpedantic -fno-fast-math -ffp-contract=off)
endif()
"""
    (source_dir / "CMakeLists.txt").write_text(cmake_source, encoding="utf-8")


def _build(build_root: Path) -> tuple[Path, dict[str, Any]]:
    source_dir = build_root / "standalone-source"
    binary_dir = build_root / "compile"
    _write_standalone_project(source_dir)
    configure = _run(
        [
            "cmake",
            "-S",
            str(source_dir),
            "-B",
            str(binary_dir),
            "-DCMAKE_BUILD_TYPE=Release",
        ]
    )
    build = _run(
        ["cmake", "--build", str(binary_dir), "--config", "Release", "--verbose"]
    )
    executable_name = "test_si_transition_pi_cdr.exe" if os.name == "nt" else "test_si_transition_pi_cdr"
    candidates = sorted(binary_dir.rglob(executable_name))
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one {executable_name}, found {len(candidates)}"
        )
    cache = (binary_dir / "CMakeCache.txt").read_text(encoding="utf-8", errors="replace")
    compiler_path = "unknown"
    for line in cache.splitlines():
        if line.startswith("CMAKE_CXX_COMPILER:FILEPATH="):
            compiler_path = line.split("=", 1)[1]
            break
    configure_lines = [line for line in configure.stdout.splitlines() if "compiler" in line.lower()]
    if compiler_path == "unknown":
        for line in configure_lines:
            marker = "working CXX compiler: "
            if marker in line:
                compiler_path = line.split(marker, 1)[1].split(" - ", 1)[0]
                break
    is_msvc = any("identification is MSVC" in line for line in configure_lines)
    identity = {
        "cmake": _run(["cmake", "--version"]).stdout.splitlines()[0],
        "cxx_compiler": compiler_path,
        "configure_compiler_lines": configure_lines,
        "strict_fp_flags": (
            ["/fp:strict", "/W4", "/WX", "/permissive-"]
            if is_msvc
            else ["-fno-fast-math", "-ffp-contract=off", "-Wall", "-Wextra", "-Werror", "-Wpedantic"]
        ),
        "verbose_build_log_sha256": hashlib.sha256(build.stdout.encode("utf-8")).hexdigest(),
    }
    return candidates[0], identity


def _python_reference() -> dict[str, Any]:
    crossings = [0.09, 1.08, 1.11, 2.17, 3.22, 4.20, 5.26, 6.30, 7.31]
    last_x = 7.8
    phase = 0.13
    kp = 0.24
    ki = 0.03
    bound = 20_000.0e-6
    max_symbols = 8
    minimum_period = 1.0 / (1.0 + bound)
    maximum_period = 1.0 / (1.0 - bound)
    boundary = phase
    period = 1.0
    next_crossing = 0
    centers: list[float] = []
    periods: list[float] = []
    errors: list[float] = []
    accepted: list[float] = []
    ambiguous = 0
    saturated = 0
    while boundary + 0.5 * minimum_period <= last_x:
        left = max(next_crossing, bisect.bisect_left(crossings, boundary - 0.45 * period))
        right = bisect.bisect_right(crossings, boundary + 0.45 * period)
        if right - left == 1:
            error = crossings[left] - boundary
            proposed = period + ki * error
            clipped = min(max(proposed, minimum_period), maximum_period)
            saturated += int(proposed != clipped)
            period = clipped
            boundary += kp * error
            errors.append(error)
            accepted.append(crossings[left])
        elif right - left > 1:
            ambiguous += 1
        next_crossing = max(next_crossing, right)
        center = boundary + 0.5 * period
        if center > last_x:
            break
        if center >= 0.0:
            if len(centers) >= max_symbols:
                raise RuntimeError("independent fixture exceeded its explicit budget")
            centers.append(center)
            periods.append(period)
        boundary += period
    return {
        "centers": centers,
        "periods": periods,
        "errors": errors,
        "accepted": accepted,
        "detected_transition_count": len(crossings),
        "accepted_transition_count": len(accepted),
        "ambiguous_gate_count": ambiguous,
        "frequency_bound_hit_count": saturated,
    }


def _owned_python_result() -> dict[str, Any]:
    # This fixture is authored here rather than imported from a test. Its
    # piecewise-linear signed distance has exact zeros at the requested crossing
    # coordinates, including the deliberately ambiguous pair at 1.08/1.11 UI.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import numpy as np

    from python.spike_core.solvers.signal_integrity.receivers.si_clock_recovery import recover_nrz_clock

    crossings = np.asarray(
        [0.09, 1.08, 1.11, 2.17, 3.22, 4.20, 5.26, 6.30, 7.31],
        dtype=float,
    )
    times = np.arange(0, 781, dtype=float) / 100.0
    voltage = np.empty_like(times)
    for index, coordinate in enumerate(times):
        nearest = float(np.min(np.abs(crossings - coordinate)))
        if nearest <= 1.0e-14:
            signed = 0.0
        else:
            completed = int(np.searchsorted(crossings, coordinate, side="right"))
            signed = (-1.0 if completed % 2 == 0 else 1.0) * min(nearest, 0.04)
        voltage[index] = 0.5 + signed
    result = recover_nrz_clock(
        times,
        voltage,
        1.0,
        {
            "initial_phase_ui": 0.13,
            "proportional_gain": 0.24,
            "integral_gain": 0.03,
            "max_frequency_offset_ppm": 20_000.0,
            "max_symbols": 8,
        },
    )
    return {
        "centers": result["sample_times_s"].tolist(),
        "periods": result["period_s"].tolist(),
        "errors": result["phase_error_ui"].tolist(),
        "accepted": result["transition_times_s"].tolist(),
        "detected_transition_count": result["detected_transition_count"],
        "accepted_transition_count": result["accepted_transition_count"],
        "ambiguous_gate_count": result["ambiguous_gate_count"],
        "frequency_bound_hit_count": result["frequency_bound_hit_count"],
    }


def _owned_duplicate_python_result() -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import numpy as np

    from python.spike_core.solvers.signal_integrity.receivers.si_clock_recovery import recover_nrz_clock

    times = np.arange(9, dtype=float) / 4.0
    voltage = np.zeros(9, dtype=float)
    voltage[1] = 0.5
    result = recover_nrz_clock(times, voltage, 1.0, {})
    return {
        "centers": result["sample_times_s"].tolist(),
        "periods": result["period_s"].tolist(),
        "errors": result["phase_error_ui"].tolist(),
        "accepted": result["transition_times_s"].tolist(),
        "detected_transition_count": result["detected_transition_count"],
        "accepted_transition_count": result["accepted_transition_count"],
        "ambiguous_gate_count": result["ambiguous_gate_count"],
        "frequency_bound_hit_count": result["frequency_bound_hit_count"],
    }


def _assert_parity(native: dict[str, Any], reference: dict[str, Any]) -> None:
    for key in ("centers", "periods", "errors", "accepted"):
        if len(native[key]) != len(reference[key]):
            raise RuntimeError(f"parity length mismatch for {key}")
        for index, (actual, expected) in enumerate(zip(native[key], reference[key])):
            if not math.isclose(actual, expected, rel_tol=1.0e-13, abs_tol=1.0e-14):
                raise RuntimeError(
                    f"parity mismatch for {key}[{index}]: {actual!r} != {expected!r}"
                )
    for key in (
        "detected_transition_count",
        "accepted_transition_count",
        "ambiguous_gate_count",
        "frequency_bound_hit_count",
    ):
        if native[key] != reference[key]:
            raise RuntimeError(f"parity mismatch for {key}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(build_dir: Path | None) -> dict[str, Any]:
    source_before = {str(path.relative_to(ROOT)): _sha256(path) for path in SOURCE_FILES}
    build_root = _fresh_build_dir(build_dir)
    executable, compiler = _build(build_root)
    native_tests = _run([str(executable)])
    native_parity = json.loads(_run([str(executable), "--dump-parity"]).stdout)
    reference = _python_reference()
    _assert_parity(native_parity, reference)
    owned_python = _owned_python_result()
    _assert_parity(native_parity, owned_python)
    native_duplicate = json.loads(
        _run([str(executable), "--dump-duplicate-parity"]).stdout
    )
    owned_duplicate = _owned_duplicate_python_result()
    _assert_parity(native_duplicate, owned_duplicate)

    measurements = []
    for size in BENCHMARK_SIZES:
        raw = json.loads(_run([str(executable), "--benchmark", str(size)]).stdout)
        timings = raw["milliseconds"]
        if len(timings) != 5 or any(not math.isfinite(value) or value < 0.0 for value in timings):
            raise RuntimeError(f"invalid timing output for {size} symbols")
        raw["median_milliseconds"] = statistics.median(timings)
        raw["minimum_milliseconds"] = min(timings)
        raw["maximum_milliseconds"] = max(timings)
        measurements.append(raw)

    source_after = {str(path.relative_to(ROOT)): _sha256(path) for path in SOURCE_FILES}
    if source_before != source_after:
        raise RuntimeError("Source changed during native CDR verification; no accepted report")
    return {
        "schema": "spike.si.transition_pi_cdr.native_benchmark.v1",
        "scope": "source reference only; not a production worker backend or protocol qualification",
        "build_root": str(build_root),
        "executable": str(executable),
        "platform": platform.platform(),
        "python": sys.version,
        "compiler": compiler,
        "source_sha256": source_before,
        "source_unchanged": True,
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "executable_sha256": _sha256(executable),
        "standalone_tests": native_tests.stdout.strip(),
        "independent_recurrence_parity": "passed",
        "owned_python_parity": "passed",
        "owned_python_duplicate_crossing_parity": "passed",
        "benchmark_method": "one untimed warm-up followed by five steady-clock measurements",
        "measurements": measurements,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build-dir",
        type=Path,
        help="fresh non-existing directory strictly below the repository build directory",
    )
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    if args.output is not None and args.output.exists():
        parser.error("Evidence output must be fresh; refusing to overwrite a report")
    report = run(args.build_dir)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
