# SPDX-License-Identifier: Apache-2.0
"""Bounded process boundary for the experimental native laminar cavity kernel."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {"n": 32, "reynolds": 100.0, "max_steps": 100000,
            "steady_tolerance": 1e-7, "length_m": 1.0,
            "lid_velocity_m_s": 1.0, "density_kg_m3": 1.0}


def _executable(executable: str | Path | None = None) -> Path:
    override = executable or os.environ.get("SPIKE_NATIVE_AIRFLOW_EXECUTABLE")
    if override:
        return Path(override).expanduser().resolve()
    suffix = ".exe" if os.name == "nt" else ""
    base = ROOT / "build-native-airflow"
    paths = [base / "Release" / ("spike_native_airflow" + suffix), base / ("spike_native_airflow" + suffix)]
    return next((path for path in paths if path.is_file()), paths[0])


def detect_native_airflow(executable: str | Path | None = None) -> dict[str, Any]:
    path = _executable(executable)
    return {"available": path.is_file(), "executable": str(path),
            "build_command": "python scripts/build_native_airflow.py"}


def native_airflow_capabilities() -> dict[str, Any]:
    return {**detect_native_airflow(), "schema": "spike-native-cavity-v1",
            "model_status": "experimental", "production_qualified": False, "geometry": "2d_square_lid_driven_cavity",
            "reynolds_range": [1, 400], "grid_range": [8, 128],
            "thermal": False, "turbulence": False, "assembly_geometry": False}


def _settings(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping) or set(request) - set(DEFAULTS):
        raise ValueError("unsupported native cavity request fields")
    settings = {**DEFAULTS, **request}
    for key, value in settings.items():
        try:
            valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"{key} must be finite numeric")
    for key in ("n", "max_steps"):
        if int(settings[key]) != settings[key]:
            raise ValueError(f"{key} must be integral")
        settings[key] = int(settings[key])
    if not 8 <= settings["n"] <= 128 or settings["n"] % 2:
        raise ValueError("n must be even in [8,128]")
    if not 1 <= settings["max_steps"] <= 200000 or not 1 <= settings["reynolds"] <= 400:
        raise ValueError("max_steps or reynolds outside supported range")
    if not 1e-10 <= settings["steady_tolerance"] <= 1e-3:
        raise ValueError("steady_tolerance outside [1e-10,1e-3]")
    for key in ("length_m", "lid_velocity_m_s", "density_kg_m3"):
        if not 1e-9 <= settings[key] <= 1e9:
            raise ValueError(f"{key} outside [1e-9,1e9]")
    return settings


def _centerline(field: list[float], n: int, vertical: bool) -> list[float]:
    # Interpolate cell-centred samples at points away from the corner singularity.
    line = [.5 * (field[j*n+n//2-1] + field[j*n+n//2]) for j in range(n)] if vertical else [
        .5*(field[(n//2-1)*n+i] + field[(n//2)*n+i]) for i in range(n)]
    samples = []
    for point in [i / 20 for i in range(1, 20)]:
        q = point*n-.5
        if q < 0:
            samples.append(line[0] * point * 2*n)
            continue
        if q > n-1:
            wall = 1.0 if vertical else 0.0
            samples.append(wall + (line[-1]-wall)*(1-point)*2*n)
            continue
        k = max(0, min(n-2, math.floor(q)))
        samples.append(line[k] + (q-k)*(line[k+1]-line[k]))
    return samples


def run_native_cavity(request: Mapping[str, Any], *, executable: str | Path | None = None,
                      timeout_s: float = 300) -> dict[str, Any]:
    settings = _settings(request)
    path = _executable(executable)
    if not path.is_file():
        raise RuntimeError("Native airflow unavailable; run python scripts/build_native_airflow.py")
    if not math.isfinite(timeout_s) or not 0 < timeout_s <= 3600:
        raise ValueError("timeout_s outside (0,3600]")
    args = [str(path)] + [str(settings[key]) for key in ("n", "reynolds", "max_steps", "steady_tolerance")]
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, check=False,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Native cavity timed out; no result accepted") from exc
    if process.returncode:
        raise RuntimeError(f"Native cavity failed: {process.stderr[-4000:]}")
    if len(process.stdout) > 4_000_000:
        raise RuntimeError("Native cavity output exceeds contract bound")
    try:
        raw = json.loads(process.stdout)
        if isinstance(raw["n"], bool) or not isinstance(raw["n"], int) or isinstance(raw["reynolds"], bool):
            raise ValueError("invalid identity types")
        if raw["schema"] != "spike-native-cavity-v1" or raw["n"] != settings["n"] or raw["reynolds"] != settings["reynolds"]:
            raise ValueError("identity mismatch")
        if raw["status"] not in ("converged", "failed_to_converge"):
            raise ValueError("unknown status")
        for key in ("time", "dt", "divergence_linf", "steady_rate_linf", "poisson_residual_linf"):
            if isinstance(raw[key], bool) or not isinstance(raw[key], (int, float)) or not math.isfinite(raw[key]) or raw[key]<0:
                raise ValueError("invalid diagnostics")
        if isinstance(raw["steps"], bool) or not isinstance(raw["steps"], int) or not 1<=raw["steps"]<=settings["max_steps"]:
            raise ValueError("invalid step count")
        expected = settings["n"]**2 if raw["status"] == "converged" else 0
        for key in ("u", "v", "pressure"):
            if not isinstance(raw[key], list) or len(raw[key]) != expected or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in raw[key]):
                raise ValueError("invalid field")
        if raw["dt"]<=0 or raw["time"]<raw["dt"] or raw["poisson_residual_linf"]>4e-9:
            raise ValueError("invalid time or pressure diagnostics")
        if raw["status"] == "converged" and (raw["divergence_linf"]>1e-7 or raw["steady_rate_linf"]>=settings["steady_tolerance"]):
            raise ValueError("unconverged diagnostics")
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise RuntimeError("Native cavity returned invalid result") from exc
    n, length, speed, rho = (settings[key] for key in ("n", "length_m", "lid_velocity_m_s", "density_kg_m3"))
    result = {"schema": raw["schema"], "status": raw["status"], "model_status": "experimental", "production_qualified": False,
              "settings": settings, "dynamic_viscosity_pa_s": rho*speed*length/settings["reynolds"],
              "diagnostics": {key: raw[key] for key in ("steps", "time", "dt", "divergence_linf", "steady_rate_linf", "poisson_residual_linf")},
              "diagnostic_units": {"time": "L/U", "dt": "L/U", "divergence_linf": "U/L", "steady_rate_linf": "U^2/L", "poisson_residual_linf": "dimensionless pressure correction equation"},
              "dimensional_diagnostics": {"time_s": raw["time"]*length/speed, "dt_s": raw["dt"]*length/speed,
                                          "divergence_linf_per_s": raw["divergence_linf"]*speed/length,
                                          "steady_rate_linf_m_s2": raw["steady_rate_linf"]*speed*speed/length},
              "provenance": {"engine": "SPIKE original native MAC projection", "executable_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "request_sha256": hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()},
              "fields": None, "centerlines": None,
              "limitations": ["2D constant-density laminar square cavity only", "No thermal, turbulence, fan, solid coupling or CAD geometry", "Knowledgeable numerical human review required before release"]}
    if raw["status"] == "converged":
        result["fields"] = {"x_m": [(i+.5)*length/n for j in range(n) for i in range(n)],
                            "y_m": [(j+.5)*length/n for j in range(n) for i in range(n)],
                            "u_m_s": [v*speed for v in raw["u"]], "v_m_s": [v*speed for v in raw["v"]],
                            "pressure_pa": [v*rho*speed*speed for v in raw["pressure"]]}
        result["centerlines"] = {"coordinates": [i/20 for i in range(1,20)],
                                 "u_over_lid": _centerline(raw["u"], n, True),
                                 "v_over_lid": _centerline(raw["v"], n, False)}
        if any(not math.isfinite(value) for values in result["fields"].values() for value in values):
            raise RuntimeError("Native cavity dimensional field overflow")
    return result


def run_native_airflow(request: Mapping[str, Any]) -> dict[str, Any]:
    """Worker-safe fixed geometry request; executable override is environment-only."""
    return run_native_cavity(request)
