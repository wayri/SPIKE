"""Fail-closed execution/import boundary for runnable OpenFOAM CHT cases.

The companion translator deliberately emits non-runnable metadata.  This
module accepts only a later, digest-bound runnable manifest and never promotes
an OpenFOAM run beyond experimental adapter evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .openfoam_runtime import detect_openfoam_runtime
from .openfoam import _latest_time, _parse_internal_field, _wsl_case_path
from .sparselizard_process import SparseLizardAdapterError, run_adapter_process


RUNNABLE_CASE_CONTRACT = "spike/openfoam-multiregion-runnable-case/v1"
RESULT_CONTRACT = "spike/thermal-field-result/v1"
MAX_FIELD_SAMPLES = 1_000_000
MAX_IMPORT_BYTES = 256 * 1024**2
MAX_STREAM_BYTES = 8 * 1024**2


class MultiRegionExecutionError(RuntimeError):
    """Raised for an untrusted case, process failure, or malformed fields."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _verify_files(root: Path, files: Any) -> bool:
    if not isinstance(files, Mapping) or not files:
        return False
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str) or len(expected) != 64:
            return False
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
    return True


def load_verified_runnable_case(case_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    root = Path(case_dir).expanduser().resolve(strict=True)
    path = root / "spike_multiregion_runnable_case.json"
    if root.is_symlink() or not path.is_file() or path.is_symlink():
        raise MultiRegionExecutionError("A regular runnable multi-region case manifest is required.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MultiRegionExecutionError("Runnable multi-region manifest is not valid UTF-8 JSON.") from exc
    if not isinstance(manifest, dict) or manifest.get("contract") != RUNNABLE_CASE_CONTRACT or manifest.get("status") != "runnable":
        raise MultiRegionExecutionError("The supplied case is not a runnable SPIKE multi-region manifest.")
    claimed = manifest.get("manifest_digest")
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    if not isinstance(claimed, str) or claimed != _digest(unsigned):
        raise MultiRegionExecutionError("Runnable multi-region manifest identity is not digest verified.")
    if manifest.get("solver") != "chtMultiRegionFoam" or not isinstance(manifest.get("regions"), list) or not manifest["regions"]:
        raise MultiRegionExecutionError("Runnable case lacks its fixed solver or regions.")
    radiating_regions = manifest.get("view_factor_regions")
    region_kinds = manifest.get("region_kinds")
    if (
        not isinstance(radiating_regions, list)
        or len(radiating_regions) != len(set(radiating_regions))
        or not isinstance(region_kinds, Mapping)
        or any(region not in manifest["regions"] or region_kinds.get(region) != "solid" for region in radiating_regions)
    ):
        raise MultiRegionExecutionError("Runnable case has invalid radiating-region ownership.")
    if not _verify_files(root, manifest.get("input_files")):
        raise MultiRegionExecutionError("Runnable case inputs do not match their verified manifest digests.")
    return root, manifest


def _command(runtime: Mapping[str, Any], name: str, root: Path, *args: str) -> list[str]:
    if runtime.get("transport") == "native_process":
        executable = shutil.which(name)
        if not executable:
            raise MultiRegionExecutionError(f"OpenFOAM v2606 command {name} is unavailable.")
        return [executable, "-case", str(root), *args]
    prefix = runtime.get("command_prefix")
    if runtime.get("transport") == "wsl_process" and isinstance(prefix, list) and all(isinstance(item, str) and item for item in prefix):
        # The fixed launcher owns OpenFOAM environment setup.  No shell is used.
        return [*prefix, name, "-case", _wsl_case_path(dict(runtime), root), *args]
    raise MultiRegionExecutionError("No fixed-argv OpenFOAM process transport is available.")


def _bounded_command(
    runtime: Mapping[str, Any], name: str, root: Path, *args: str,
    timeout_s: int, memory_limit_mb: int, output_limit_bytes: int,
) -> list[str]:
    """Apply limits inside WSL instead of only to its Windows proxy.

    A Windows Job active-process limit of one prevents ``wsl.exe`` from
    starting its required host processes. For WSL transports, Linux
    ``prlimit`` therefore owns the actual solver AS/CPU/file limits while the
    Windows job remains a kill-on-close containment boundary with bounded
    helper-process headroom.
    """
    if runtime.get("transport") != "wsl_process":
        return _command(runtime, name, root, *args)
    prefix = runtime.get("command_prefix")
    if not isinstance(prefix, list) or not all(isinstance(item, str) and item for item in prefix):
        raise MultiRegionExecutionError("No fixed-argv OpenFOAM WSL prefix is available.")
    return [
        *prefix,
        "/usr/bin/prlimit",
        f"--as={memory_limit_mb * 1024**2}",
        f"--cpu={timeout_s + 3}",
        f"--fsize={output_limit_bytes}",
        "--",
        name,
        "-case",
        _wsl_case_path(dict(runtime), root),
        *args,
    ]


def _windows_process_allowance(runtime: Mapping[str, Any]) -> int:
    return 64 if runtime.get("transport") == "wsl_process" else 1


def probe_v2606_commands(*, required_commands: Sequence[str] = (), runtime: Mapping[str, Any] | None = None, runner: Callable[..., dict[str, Any]] = run_adapter_process) -> dict[str, Any]:
    runtime = dict(runtime or detect_openfoam_runtime())
    if str(runtime.get("version") or "") != "2606":
        return {"status": "failed", "reason": "OpenFOAM v2606 is required.", "commands": {}}
    allowed = {"faceAgglomerate", "viewFactorsGen"}
    if any(name not in allowed for name in required_commands):
        return {"status": "failed", "reason": "Unsupported OpenFOAM prerequisite command requested.", "commands": {}}
    root = Path.cwd()
    commands: dict[str, Any] = {}
    command_names = ["checkMesh", "chtMultiRegionFoam", "postProcess", *required_commands]
    for name in dict.fromkeys(command_names):
        try:
            argv = _bounded_command(runtime, name, root, "-help", timeout_s=20, memory_limit_mb=512, output_limit_bytes=MAX_STREAM_BYTES)
            process = runner(argv, cwd=root, timeout_s=20, memory_limit_mb=512, output_limit_bytes=MAX_STREAM_BYTES, stream_limit_bytes=MAX_STREAM_BYTES, windows_active_process_limit=_windows_process_allowance(runtime))
            commands[name] = {"argv": argv, "return_code": process["return_code"], "available": process["return_code"] == 0}
        except (OSError, SparseLizardAdapterError, MultiRegionExecutionError) as exc:
            commands[name] = {"available": False, "reason": str(exc)}
    return {"status": "passed" if all(item["available"] for item in commands.values()) else "failed", "runtime_version": "2606", "commands": commands}


def _finite_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise MultiRegionExecutionError(f"{label} is not finite.")
    return float(value)


def _point(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise MultiRegionExecutionError(f"{label} must have three values.")
    return [_finite_number(item, label) for item in value]


def import_multiregion_fields(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Import only one complete, aligned export; any malformed region rejects all."""
    from .openfoam_buoyancy import validate_buoyancy_runtime
    try:
        buoyancy_evidence=validate_buoyancy_runtime(root,manifest)
    except (ValueError,OSError,KeyError) as exc:
        raise MultiRegionExecutionError(f"Buoyancy runtime envelope rejected: {exc}") from exc
    relative = manifest.get("field_export_path")
    if not isinstance(relative, str) or not relative:
        raise MultiRegionExecutionError("Runnable manifest lacks field_export_path.")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_IMPORT_BYTES:
        raise MultiRegionExecutionError("Multi-region field export is unavailable or outside the import budget.")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MultiRegionExecutionError("Multi-region field export is not valid UTF-8 JSON.") from exc
    if not isinstance(raw, Mapping) or raw.get("manifest_digest") != manifest.get("manifest_digest") or not isinstance(raw.get("regions"), list):
        raise MultiRegionExecutionError("Field export is not bound to the verified runnable manifest.")
    expected_regions = {str(item) for item in manifest["regions"]}
    region_kinds = manifest.get("region_kinds") if isinstance(manifest.get("region_kinds"), Mapping) else {}
    thermal_rows: list[dict[str, Any]] = []
    fluid_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for region in raw["regions"]:
        if not isinstance(region, Mapping) or not isinstance(region.get("id"), str) or region["id"] not in expected_regions or region["id"] in seen:
            raise MultiRegionExecutionError("Field export region identity is invalid.")
        seen.add(region["id"])
        arrays = {name: region.get(name) for name in ("positions_m", "temperature_k", "heat_flux_w_m2")}
        if not all(isinstance(value, list) for value in arrays.values()):
            raise MultiRegionExecutionError(f"Region {region['id']} lacks a complete aligned position/T/q export.")
        count = len(arrays["positions_m"])
        if not 0 < count <= MAX_FIELD_SAMPLES or any(len(value) != count for value in arrays.values()):
            raise MultiRegionExecutionError(f"Region {region['id']} field arrays are not aligned or exceed limits.")
        kind = str(region_kinds.get(region["id"]) or region.get("kind") or "fluid")
        velocity_values = region.get("velocity_m_s")
        pressure_values = region.get("pressure_pa")
        if kind == "fluid" and (not isinstance(velocity_values, list) or not isinstance(pressure_values, list) or len(velocity_values) != count or len(pressure_values) != count):
            raise MultiRegionExecutionError(f"Fluid region {region['id']} lacks aligned U/p fields.")
        for index in range(count):
            point = _point(arrays["positions_m"][index], "position")
            temperature_k = _finite_number(arrays["temperature_k"][index], "temperature")
            q = _point(arrays["heat_flux_w_m2"][index], "heat flux")
            row = {"region": region["id"], "position_mm": [value * 1000 for value in point], "temperature_k": temperature_k, "heat_flux_vector_w_m2": q}
            thermal_rows.append(row)
            if kind == "fluid":
                fluid_rows.append({**row, "velocity_m_s": _point(velocity_values[index], "velocity"), "pressure_pa": _finite_number(pressure_values[index], "pressure")})
    if seen != expected_regions or len(thermal_rows) > MAX_FIELD_SAMPLES:
        raise MultiRegionExecutionError("Field export did not contain every manifest region or exceeded total sample limit.")
    artifact_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    preview_limit = min(250_000, MAX_FIELD_SAMPLES)
    preview_rows = thermal_rows[:preview_limit]
    preview_fluid_rows = fluid_rows[:preview_limit]
    artifact = {"id": str(relative), "sha256": artifact_digest, "bytes": path.stat().st_size, "contract": "spike/openfoam-multiregion-field-export/v1"}

    def field(unit: str, values: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(thermal_rows) if unit in {"K", "W/m2"} else len(fluid_rows)
        result: dict[str, Any] = {"unit": unit, "samples": values, "preview_samples": len(values), "total_samples": total}
        if total > len(values):
            result["artifact"] = artifact
        return result

    fields = {
        "temperature_k": field("K", [{"point_mm": row["position_mm"], "value": row["temperature_k"], "region": row["region"]} for row in preview_rows]),
        "heat_flux_w_m2": field("W/m2", [{"point_mm": row["position_mm"], "value": row["heat_flux_vector_w_m2"], "region": row["region"]} for row in preview_rows]),
        "velocity_m_s": field("m/s", [{"point_mm": row["position_mm"], "value": row["velocity_m_s"], "region": row["region"]} for row in preview_fluid_rows]),
        "pressure_pa": field("Pa", [{"point_mm": row["position_mm"], "value": row["pressure_pa"], "region": row["region"]} for row in preview_fluid_rows]),
    }
    temperatures = [row["temperature_k"] for row in thermal_rows]
    heat_flux_definition = raw.get('heat_flux_definition', 'unspecified_by_exporter')
    fields['heat_flux_w_m2']['definition'] = heat_flux_definition
    return {
        "contract": RESULT_CONTRACT, "job_id": str(manifest.get("job_id") or ""),
        "plan_digest": str(manifest.get("plan_digest") or "0" * 64),
        "status": "completed", "model_status": "experimental",
        "summary": {"minimum_temperature_k": min(temperatures), "maximum_temperature_k": max(temperatures), "total_samples": len(thermal_rows), "fluid_samples": len(fluid_rows)},
        "fields": fields, "component_temperatures_k": {},
        "resource_usage": {"rendered_preview_samples": len(preview_rows) * 2 + len(preview_fluid_rows) * 2, "total_field_samples": len(thermal_rows) * 2 + len(fluid_rows) * 2, "field_export_bytes": path.stat().st_size},
        "issues": [],
        "qualification": {"production_qualified": False, "field_result_produced": True, "reason": "Bounded OpenFOAM execution and aligned import do not establish field correlation or release qualification."},
        "provenance": {"solver_id": "external.openfoam", "solver": "chtMultiRegionFoam", "manifest_digest": manifest["manifest_digest"], "field_export_sha256": artifact_digest,"buoyancy_runtime":buoyancy_evidence,"heat_flux_definition":heat_flux_definition},
    }


def _write_native_field_export(root: Path, manifest: Mapping[str, Any]) -> Path:
    """Normalize latest ASCII OpenFOAM region fields into one bound export."""
    latest = _latest_time(root)
    region_kinds = manifest.get("region_kinds")
    conductivities = manifest.get("region_conductivity_w_mk")
    if not isinstance(region_kinds, Mapping) or not isinstance(conductivities, Mapping):
        raise MultiRegionExecutionError("Runnable manifest lacks region kind/conductivity ownership.")
    regions = []
    for region_id in manifest["regions"]:
        region_root = latest / str(region_id)
        centres = _parse_internal_field(region_root / "C", vector=True)
        temperature = _parse_internal_field(region_root / "T", expected_count=len(centres))
        gradient = _parse_internal_field(region_root / "grad(T)", vector=True, expected_count=len(centres))
        if not (len(centres) == len(temperature) == len(gradient)):
            raise MultiRegionExecutionError(f"Region {region_id} C/T/grad(T) fields are not aligned.")
        conductivity = _finite_number(conductivities.get(region_id), f"region {region_id} conductivity")
        record: dict[str, Any] = {
            "id": str(region_id), "kind": str(region_kinds.get(region_id) or ""),
            "positions_m": centres, "temperature_k": temperature,
            "heat_flux_w_m2": [[-conductivity * component for component in value] for value in gradient],
        }
        volume_path = region_root / "V"
        if volume_path.is_file() and not volume_path.is_symlink():
            volumes = _parse_internal_field(volume_path, expected_count=len(centres))
            if len(volumes) != len(centres) or any(value <= 0 for value in volumes):
                raise MultiRegionExecutionError(f"Region {region_id} cell-volume field is invalid.")
            record["cell_volume_m3"] = volumes
        if record["kind"] == "fluid":
            record["velocity_m_s"] = _parse_internal_field(region_root / "U", vector=True, expected_count=len(centres))
            record["pressure_pa"] = _parse_internal_field(region_root / "p_rgh", expected_count=len(centres))
            if len(record["velocity_m_s"]) != len(centres) or len(record["pressure_pa"]) != len(centres):
                raise MultiRegionExecutionError(f"Fluid region {region_id} C/U/p fields are not aligned.")
        regions.append(record)
    payload = {"contract": "spike/openfoam-multiregion-field-export/v1", "manifest_digest": manifest["manifest_digest"], "result_time": latest.name, "regions": regions,"heat_flux_definition":"molecular_conduction_only"}
    target = (root / str(manifest["field_export_path"])).resolve()
    if not target.is_relative_to(root):
        raise MultiRegionExecutionError("Field export path escaped the case root.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return target


def run_multiregion_case(case_dir: str | Path, *, timeout_s: int = 3600, memory_limit_mb: int = 4096, output_limit_bytes: int = 8 * 1024**3, cancellation_event: threading.Event | None = None, runtime: Mapping[str, Any] | None = None, runner: Callable[..., dict[str, Any]] = run_adapter_process) -> dict[str, Any]:
    root, manifest = load_verified_runnable_case(case_dir)
    if cancellation_event is not None and cancellation_event.is_set():
        return {"status": "cancelled", "fields": {}, "message": "Cancelled before multi-region execution."}
    radiating_regions = list(manifest["view_factor_regions"])
    prerequisites = ("faceAgglomerate", "viewFactorsGen") if radiating_regions else ()
    probe = probe_v2606_commands(required_commands=prerequisites, runtime=runtime, runner=runner)
    if probe["status"] != "passed":
        return {"status": "blocked", "fields": {}, "message": "OpenFOAM v2606 runtime probe failed.", "runtime_probe": probe}
    active_runtime = dict(runtime or detect_openfoam_runtime())
    if not 10 <= timeout_s <= 604800 or not 512 <= memory_limit_mb <= 1_048_576 or not 1_048_576 <= output_limit_bytes <= 64 * 1024**3:
        raise MultiRegionExecutionError("Execution budget is outside allowed bounds.")
    export_path = (root / str(manifest["field_export_path"])).resolve()
    if export_path.is_file():
        export_path.unlink()
    started = time.monotonic(); execution: list[dict[str, Any]] = []
    try:
        if cancellation_event is not None and cancellation_event.is_set():
            return {"status": "cancelled", "fields": {}, "message": "Cancelled before multi-region mesh checks.", "execution": execution}
        # Coupled mappedWall patches require both object registries to exist;
        # checking regions separately fails during neighbour lookup even when
        # each mesh is valid. -allRegions validates every region and the AMI.
        argv = _bounded_command(active_runtime, "checkMesh", root, "-allRegions", "-allTopology", "-allGeometry", timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes)
        report = runner(argv, cwd=root, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes, stream_limit_bytes=MAX_STREAM_BYTES, cancellation_event=cancellation_event, windows_active_process_limit=_windows_process_allowance(active_runtime))
        execution.append({"command": "checkMesh", "regions": list(manifest["regions"]), "argv": argv, "return_code": report["return_code"], "stdout": report.get("stdout", "")[-4000:], "stderr": report.get("stderr", "")[-4000:]})
        if report["return_code"] != 0:
            return {"status": "failed", "fields": {}, "message": "checkMesh failed for the coupled region set.", "execution": execution}
        for region in radiating_regions:
            for command_name in ("faceAgglomerate", "viewFactorsGen"):
                argv = _bounded_command(active_runtime, command_name, root, "-region", str(region), timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes)
                report = runner(argv, cwd=root, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes, stream_limit_bytes=MAX_STREAM_BYTES, cancellation_event=cancellation_event, windows_active_process_limit=_windows_process_allowance(active_runtime))
                execution.append({"command": command_name, "region": region, "argv": argv, "return_code": report["return_code"], "stdout": report.get("stdout", "")[-4000:], "stderr": report.get("stderr", "")[-4000:]})
                if report["return_code"] != 0:
                    return {"status": "failed", "fields": {}, "message": f"OpenFOAM {command_name} failed for radiating region {region}.", "execution": execution}
        argv = _bounded_command(active_runtime, "chtMultiRegionFoam", root, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes)
        report = runner(argv, cwd=root, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes, stream_limit_bytes=MAX_STREAM_BYTES, cancellation_event=cancellation_event, windows_active_process_limit=_windows_process_allowance(active_runtime))
        execution.append({"command": "chtMultiRegionFoam", "argv": argv, "return_code": report["return_code"], "stdout": report.get("stdout", "")[-4000:], "stderr": report.get("stderr", "")[-4000:]})
        if report["return_code"] != 0 or (cancellation_event is not None and cancellation_event.is_set()):
            return {"status": "cancelled" if cancellation_event is not None and cancellation_event.is_set() else "failed", "fields": {}, "message": "CHT execution did not complete.", "execution": execution}
        for region in manifest["regions"]:
            for function_name, function_argument in (("writeCellCentres", "writeCellCentres"), ("writeCellVolumes", "writeCellVolumes"), ("grad(T)", "gradT")):
                argv = _bounded_command(active_runtime, "postProcess", root, "-region", str(region), "-func", function_argument, "-latestTime", timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes)
                report = runner(argv, cwd=root, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, output_limit_bytes=output_limit_bytes, stream_limit_bytes=MAX_STREAM_BYTES, cancellation_event=cancellation_event, windows_active_process_limit=_windows_process_allowance(active_runtime))
                execution.append({"command": "postProcess", "region": region, "function": function_name, "argv": argv, "return_code": report["return_code"], "stdout": report.get("stdout", "")[-4000:], "stderr": report.get("stderr", "")[-4000:]})
                if report["return_code"] != 0:
                    return {"status": "failed", "fields": {}, "message": f"OpenFOAM {function_name} export failed for region {region}.", "execution": execution}
        _write_native_field_export(root, manifest)
        result = import_multiregion_fields(root, manifest)
        return {**result, "duration_s": time.monotonic() - started, "execution": execution, "runtime_probe": probe}
    except (OSError, SparseLizardAdapterError, MultiRegionExecutionError) as exc:
        return {"status": "failed", "fields": {}, "message": str(exc), "execution": execution}


__all__ = ["MultiRegionExecutionError", "RESULT_CONTRACT", "RUNNABLE_CASE_CONTRACT", "import_multiregion_fields", "load_verified_runnable_case", "probe_v2606_commands", "run_multiregion_case"]
