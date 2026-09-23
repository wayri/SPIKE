"""Process-isolated ngspice adapter for explicit, self-contained netlists."""

from __future__ import annotations

import re
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .solver_plugins import SolverPluginManifest
from .runtime_locations import app_root, registered_engine_path
from .spice_netlist_safety import (
    FORBIDDEN_DIRECTIVES,
    MAX_NETLIST_BYTES,
    validate_netlist,
)


MAX_RAW_BYTES = 64 * 1024 * 1024
MAX_RESULT_POINTS = 250_000


def _find_ngspice() -> str:
    discovered = shutil.which("ngspice") or shutil.which("ngspice_con.exe") or shutil.which("ngspice.exe")
    if discovered:
        return str(Path(discovered).resolve())
    configured = registered_engine_path("external.ngspice") or os.environ.get("SPIKE_NGSPICE_HOME", "").strip()
    roots = [Path(configured).expanduser()] if configured else []
    roots.extend([app_root() / "runtime" / "external" / "Spice64", app_root() / "runtime" / "external" / "ngspice"])
    for root in roots:
        if root.is_file():
            return str(root.resolve())
        for name in ("ngspice_con.exe", "ngspice.exe", "ngspice"):
            for candidate in (root / name, root / "bin" / name):
                if candidate.is_file():
                    return str(candidate.resolve())
    return ""


def _version(executable: str) -> str:
    if not executable:
        return ""
    try:
        process = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            shell=False,
        )
        match = re.search(r"ngspice[- ](\d+(?:\.\d+)*)", process.stdout + process.stderr, re.IGNORECASE)
        return match.group(1) if match else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def ngspice_manifest() -> SolverPluginManifest:
    executable = _find_ngspice()
    return SolverPluginManifest(
        id="spike.ngspice",
        name="ngspice Circuit Co-simulation",
        version=_version(executable) or "not-installed",
        provider="ngspice project / SPIKE adapter",
        analyses=["spice", "dc_operating_point", "ac", "transient"],
        formulations=["modified_nodal_analysis"],
        capabilities=["spice_netlist", "dc_operating_point", "ac_sweep", "transient_waveforms", "behavioral_sources"],
        state="available" if executable else "unavailable",
        model_status="solver_dependent" if executable else "unsupported",
        validation="The adapter is operational only for explicit netlists. Extracted PCB RLC co-simulation requires separate validation.",
        license="ngspice: primarily BSD-3-Clause with component exceptions; SPIKE adapter: MIT",
        bundled=False,
        priority=60,
        limits={
            "isolation": "Separate process with user init disabled.",
            "netlist": "Inline self-contained netlists only; control, shell, include, and library directives are rejected.",
            "points": MAX_RESULT_POINTS,
        },
    )


_validate_netlist = validate_netlist


def _number(value: str) -> float | Dict[str, float]:
    stripped = value.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        real, imaginary = stripped[1:-1].split(",", 1)
        return {"real": float(real), "imag": float(imaginary)}
    return float(stripped)


def _tail_text(path: Path, limit: int = 65536) -> str:
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(max(0, size - limit))
        return stream.read(limit).decode("utf-8", errors="replace")


def _parse_ascii_raw(path: Path) -> Dict[str, Any]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    variables_index = next((index for index, line in enumerate(lines) if line.strip() == "Variables:"), -1)
    values_index = next((index for index, line in enumerate(lines) if line.strip() == "Values:"), -1)
    if variables_index < 0 or values_index < 0 or values_index <= variables_index:
        return {"metadata": {"parse_status": "raw_format_unrecognized"}, "vectors": {}}
    variable_rows = [line.split() for line in lines[variables_index + 1:values_index] if line.strip()]
    names = [row[1] for row in variable_rows if len(row) >= 3]
    types = [row[2] for row in variable_rows if len(row) >= 3]
    vectors: Dict[str, List[Any]] = {name: [] for name in names}
    current_variable = 0
    points = 0
    for line in lines[values_index + 1:]:
        parts = line.split()
        if not parts:
            continue
        value_text = ""
        if len(parts) >= 2 and parts[0].isdigit():
            current_variable = 0
            value_text = parts[1]
            points += 1
            if points > MAX_RESULT_POINTS:
                break
        else:
            value_text = parts[-1]
        if current_variable < len(names):
            try:
                vectors[names[current_variable]].append(_number(value_text))
            except (ValueError, IndexError):
                pass
        current_variable += 1
    return {
        "metadata": {
            "parse_status": "complete" if points <= MAX_RESULT_POINTS else "truncated",
            "point_count": min(points, MAX_RESULT_POINTS),
            "variable_types": dict(zip(names, types)),
        },
        "vectors": vectors,
    }


def _build_transient_visualization(parsed: Dict[str, Any], bindings: Any) -> Dict[str, Any]:
    vectors = parsed.get("vectors", {})
    time = vectors.get("time", [])
    if not time or not isinstance(bindings, list):
        return {"times_s": [], "frames": []}
    supported = {"voltage_v", "voltage_drop_v", "current_a", "current_density_a_mm2"}
    frames = []
    for point_index, time_s in enumerate(time):
        scalar_fields: Dict[str, list] = {name: [] for name in supported}
        for binding in bindings:
            if not isinstance(binding, dict):
                continue
            quantity = str(binding.get("quantity", ""))
            vector = vectors.get(str(binding.get("vector", "")), [])
            if quantity not in supported or point_index >= len(vector):
                continue
            scalar_fields[quantity].append({
                "x_mm": float(binding.get("x_mm", 0)),
                "y_mm": float(binding.get("y_mm", 0)),
                "z_mm": float(binding.get("z_mm", 0)),
                "layer": str(binding.get("layer", "")),
                "net": str(binding.get("net", "")),
                "element_id": str(binding.get("element_id", binding.get("vector", ""))),
                "value": float(vector[point_index]),
            })
        frames.append({"time_s": float(time_s), "scalar_fields": scalar_fields})
    return {"times_s": [float(value) for value in time], "frames": frames}


def _component_stress(parsed: Dict[str, Any], bindings: Any) -> list:
    vectors = parsed.get("vectors", {})
    if not isinstance(bindings, list):
        return []
    output = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        voltage = [abs(float(value)) for value in vectors.get(str(binding.get("voltage_vector", "")), [])]
        current = [abs(float(value)) for value in vectors.get(str(binding.get("current_vector", "")), [])]
        power = [float(value) for value in vectors.get(str(binding.get("power_vector", "")), [])]
        if not power and voltage and current:
            power = [v * i for v, i in zip(voltage, current)]
        ratings = binding.get("ratings", {}) if isinstance(binding.get("ratings", {}), dict) else {}
        peak_voltage = max(voltage, default=0.0)
        peak_current = max(current, default=0.0)
        rms_current = (sum(value * value for value in current) / len(current)) ** 0.5 if current else 0.0
        peak_power = max((abs(value) for value in power), default=0.0)
        average_power = sum(power) / len(power) if power else 0.0
        def utilization(value: float, rating_name: str) -> Any:
            rating = float(ratings.get(rating_name, 0) or 0)
            return value / rating * 100 if rating > 0 else None
        utilizations = {
            "voltage_percent": utilization(peak_voltage, "voltage_v"),
            "current_percent": utilization(peak_current, "current_a"),
            "power_percent": utilization(peak_power, "power_w"),
        }
        output.append({
            "component_id": str(binding.get("component_id", "")),
            "reference": str(binding.get("reference", binding.get("component_id", ""))),
            "peak_voltage_v": peak_voltage,
            "peak_current_a": peak_current,
            "rms_current_a": rms_current,
            "peak_power_w": peak_power,
            "average_power_w": average_power,
            "ratings": ratings,
            "utilization": utilizations,
            "status": "over_limit" if any(value is not None and value > 100 for value in utilizations.values()) else "within_assigned_limits",
        })
    return output


class NgspicePlugin:
    def __init__(self) -> None:
        self.manifest = ngspice_manifest()
        self.executable = _find_ngspice()

    def run(self, design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
        if not self.executable:
            return AnalysisResult(
                analysis_id=spec.analysis_id,
                mode=spec.mode,
                status="blocked",
                model_status="unsupported",
                issues=[ValidationIssue(
                    code="NGSPICE_NOT_INSTALLED",
                    severity="error",
                    message="ngspice is not installed or discoverable.",
                    suggestion="Install an approved ngspice build or add a signed solver bundle.",
                )],
                provenance={"solver_plugin": self.manifest.id},
            )
        try:
            netlist = _validate_netlist(str(spec.options.get("spice_netlist", "")))
        except ValueError as exc:
            return AnalysisResult(
                analysis_id=spec.analysis_id,
                mode=spec.mode,
                status="failed",
                model_status="unsupported",
                issues=[ValidationIssue(code="SPICE_NETLIST_REJECTED", severity="error", message=str(exc))],
                provenance={"solver_plugin": self.manifest.id},
            )

        timeout_seconds = max(1, min(int(spec.options.get("timeout_seconds", 120)), 3600))
        with tempfile.TemporaryDirectory(prefix="spike-ngspice-") as directory:
            root = Path(directory)
            input_path = root / "input.cir"
            output_path = root / "ngspice.log"
            raw_path = root / "result.raw"
            input_path.write_text(netlist, encoding="utf-8")
            try:
                process = subprocess.run(
                    [self.executable, "-n", "-b", "-o", str(output_path), "-r", str(raw_path), str(input_path)],
                    cwd=root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_seconds,
                    shell=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired:
                return AnalysisResult(
                    analysis_id=spec.analysis_id,
                    mode=spec.mode,
                    status="failed",
                    model_status="solver_dependent",
                    issues=[ValidationIssue(code="NGSPICE_TIMEOUT", severity="error", message=f"ngspice exceeded the {timeout_seconds}-second execution limit.")],
                    provenance={"solver_plugin": self.manifest.id, "ngspice_version": self.manifest.version},
                )
            except OSError as exc:
                return AnalysisResult(
                    analysis_id=spec.analysis_id,
                    mode=spec.mode,
                    status="failed",
                    model_status="solver_dependent",
                    issues=[ValidationIssue(code="NGSPICE_LAUNCH_FAILED", severity="error", message="ngspice could not be launched.", suggestion=str(exc))],
                    provenance={"solver_plugin": self.manifest.id, "ngspice_version": self.manifest.version},
                )
            log = _tail_text(output_path) if output_path.is_file() else "No ngspice diagnostic was returned."
            if process.returncode != 0 or not raw_path.is_file():
                return AnalysisResult(
                    analysis_id=spec.analysis_id,
                    mode=spec.mode,
                    status="failed",
                    model_status="solver_dependent",
                    issues=[ValidationIssue(code="NGSPICE_FAILED", severity="error", message="ngspice did not complete the requested analysis.", suggestion=log[-2000:])],
                    provenance={"solver_plugin": self.manifest.id, "ngspice_version": self.manifest.version},
                )
            if raw_path.stat().st_size > MAX_RAW_BYTES:
                return AnalysisResult(
                    analysis_id=spec.analysis_id,
                    mode=spec.mode,
                    status="failed",
                    model_status="solver_dependent",
                    issues=[ValidationIssue(code="NGSPICE_RESULT_TOO_LARGE", severity="error", message="ngspice exceeded the 64 MiB raw-result limit.")],
                    provenance={"solver_plugin": self.manifest.id, "ngspice_version": self.manifest.version},
                )
            parsed = _parse_ascii_raw(raw_path)
            visualization = _build_transient_visualization(parsed, spec.options.get("spice_overlay_bindings", []))
            stress = _component_stress(parsed, spec.options.get("component_stress_bindings", []))
            return AnalysisResult(
                analysis_id=spec.analysis_id,
                mode=spec.mode,
                status="completed",
                model_status="solver_dependent",
                summary=parsed["metadata"],
                fields={"waveforms": parsed["vectors"], "visualization": {"time_series": visualization}},
                networks={"component_stress": stress},
                issues=[ValidationIssue(
                    code="EXPLICIT_NETLIST_ONLY",
                    severity="warning",
                    message="ngspice ran an explicit netlist; PCB geometry-derived parasitics were not inferred by this adapter.",
                    status="approximate",
                )],
                provenance={
                    "solver": "ngspice",
                    "solver_plugin": self.manifest.id,
                    "ngspice_version": self.manifest.version,
                    "execution": "isolated_process",
                    "user_init": "disabled",
                },
            )
