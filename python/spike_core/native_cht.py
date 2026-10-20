# SPDX-License-Identifier: Apache-2.0
"""SI admission and supervised execution of the experimental native CHT case.

Constant-property, incompressible, Newtonian fluid in a square cavity between
two solid slabs. This is not arbitrary-geometry CFD, compressible gas or FSI.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

from .sparselizard_process import run_adapter_process

REQUEST = "spike/native-cht-request/v1"
RESULT = "spike/native-cht-result/v1"
ROOT = Path(__file__).resolve().parents[2]
MAX_OUTPUT = 8 * 1024**2
DEFAULTS = {
    "n": 16, "length_m": 1., "span_m": 1., "lid_velocity_m_s": 1.,
    "density_kg_m3": 1., "dynamic_viscosity_pa_s": .01,
    "specific_heat_j_kgk": 1., "fluid_conductivity_w_mk": .01,
    "solid_conductivity_w_mk": .1, "hot_temperature_k": 310.,
    "cold_temperature_k": 300., "max_flow_steps": 100000,
    "steady_tolerance": 1e-7, "thermal_tolerance": 1e-9,
    "max_thermal_iterations": 200000, "timeout_s": 300,
}
LIMITS = {
    "n": (8, 64), "length_m": (1e-6, 1e3), "span_m": (1e-6, 1e3),
    "lid_velocity_m_s": (0., 100.), "density_kg_m3": (1e-6, 1e5),
    "dynamic_viscosity_pa_s": (1e-9, 1e3), "specific_heat_j_kgk": (1e-3, 1e6),
    "fluid_conductivity_w_mk": (1e-6, 1e4), "solid_conductivity_w_mk": (1e-6, 1e4),
    "hot_temperature_k": (1., 10000.), "cold_temperature_k": (1., 10000.),
    "max_flow_steps": (1, 200000), "steady_tolerance": (1e-10, 1e-3),
    "thermal_tolerance": (1e-12, 1e-4), "max_thermal_iterations": (1, 200000),
    "timeout_s": (1, 1800),
}
INTEGER_KEYS = {"n", "max_flow_steps", "max_thermal_iterations", "timeout_s"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def settings(request):
    if not isinstance(request, dict) or request.get("contract") != REQUEST:
        raise ValueError(f"Expected {REQUEST}")
    if set(request) - {"contract", *DEFAULTS}:
        raise ValueError("Unknown native CHT request fields")
    result = {**DEFAULTS, **{k: v for k, v in request.items() if k != "contract"}}
    for key, value in result.items():
        low, high = LIMITS[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not low <= value <= high):
            raise ValueError(f"{key} outside [{low},{high}]")
        if key in INTEGER_KEYS:
            if int(value) != value:
                raise ValueError(f"{key} must be integral")
            result[key] = int(value)
    if result["n"] % 4:
        raise ValueError("n must be a multiple of four")
    if result["hot_temperature_k"] < result["cold_temperature_k"]:
        raise ValueError("hot_temperature_k must be >= cold_temperature_k")
    rho, length, mu, speed, cp, k = (result[key] for key in (
        "density_kg_m3", "length_m", "dynamic_viscosity_pa_s", "lid_velocity_m_s",
        "specific_heat_j_kgk", "fluid_conductivity_w_mk"))
    # At rest a positive reference velocity only sets nondimensional units.
    # Actual velocity/Re remain zero; no fictitious flow is introduced.
    reference = speed if speed > 0 else mu / (rho * length)
    reynolds = rho * speed * length / mu
    pe = rho * cp * reference * length / k
    ratio = result["solid_conductivity_w_mk"] / k
    if not (reynolds == 0 or 1 <= reynolds <= 400):
        raise ValueError("Moving-lid flow requires 1 <= Reynolds <= 400")
    if not 0 <= pe <= 5000 or not .01 <= ratio <= 1e5:
        raise ValueError("Reference Peclet or solid/fluid conductivity ratio unsupported")
    scales = {"velocity_scale_m_s": reference, "actual_reynolds": reynolds,
              "kernel_reynolds": reynolds if speed > 0 else 1., "peclet": pe,
              "solid_k_ratio": ratio, "lid": 1. if speed > 0 else 0.}
    if not all(math.isfinite(v) for v in scales.values()):
        raise ValueError("Unrepresentable CHT scaling")
    return result, scales


def executable_path(executable=None):
    override = executable or os.environ.get("SPIKE_NATIVE_CHT_EXECUTABLE")
    if override:
        return Path(override).expanduser().resolve()
    name = "spike_native_cht" + (".exe" if os.name == "nt" else "")
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "native" / name
    base = ROOT / "build-native-airflow"
    paths = (base / "Release" / name, base / name)
    return next((p for p in paths if p.is_file()), paths[0])


def native_cht_capabilities():
    path = executable_path()
    return {"available": path.is_file(), "executable": str(path),
            "contract": REQUEST, "model_status": "experimental", "production_qualified": False,
            "geometry": "2d_square_cavity_between_two_solid_slabs",
            "flow": "constant_property_incompressible_laminar",
            "fluid_materials": "supplied_constant_property_liquids_or_low_Mach_gases",
            "thermal": True, "conjugate_interfaces": True, "turbulence": False,
            "assembly_geometry": False, "two_way_fsi": False,
            "build_command": "python scripts/build_native_airflow.py"}


def kernel_arguments(s, scales):
    return [s["n"], scales["kernel_reynolds"], scales["lid"], scales["peclet"],
            scales["solid_k_ratio"], s["hot_temperature_k"], s["cold_temperature_k"],
            s["max_flow_steps"], s["steady_tolerance"], s["thermal_tolerance"],
            s["max_thermal_iterations"]]


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate native CHT output key")
        value[key] = item
    return value


def run_native_cht(request, *, executable=None, cancellation_event=None):
    s, scales = settings(request)
    path = executable_path(executable)
    if not path.is_file():
        raise RuntimeError("Native CHT unavailable; build src/airflow with scripts/build_native_airflow.py")
    binary_before = hashlib.sha256(path.read_bytes()).hexdigest()
    args = [str(path), *(str(x) for x in kernel_arguments(s, scales))]
    # Reuse the existing OS containment: fixed argv, Job/process group, one
    # process, hard 512 MiB memory and bounded stdout/stderr. No shell text.
    with tempfile.TemporaryDirectory(prefix="spike-native-cht-") as directory:
        process = run_adapter_process(args, cwd=Path(directory), timeout_s=s["timeout_s"],
            memory_limit_mb=512, output_limit_bytes=MAX_OUTPUT, stream_limit_bytes=MAX_OUTPUT,
            cancellation_event=cancellation_event)
    if process["return_code"] != 0:
        raise RuntimeError("Native CHT process failed: " + process["stderr"][-2000:])
    if hashlib.sha256(path.read_bytes()).hexdigest() != binary_before:
        raise RuntimeError("Native CHT executable changed during execution")
    try:
        raw = json.loads(process["stdout"], object_pairs_hook=_unique_object,
                         parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        from .native_cht_result import admit_native_cht_result
        result = admit_native_cht_result(raw, s, scales)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise RuntimeError("Native CHT returned invalid result: " + str(exc)) from exc
    result["provenance"] = {"engine": "SPIKE native MAC/FV CHT", "executable_sha256": binary_before,
        "request_sha256": digest({"contract": REQUEST, **s}), "raw_result_sha256": digest(raw),
        "memory_limit_mb": 512, "stream_limit_bytes": MAX_OUTPUT,
        "process_containment": {k: process[k] for k in (
            "memory_limit_enforced", "suspended_before_job_assignment", "job_assignment_race_closed")}}
    return result
