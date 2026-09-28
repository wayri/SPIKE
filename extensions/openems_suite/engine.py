# SPDX-License-Identifier: Apache-2.0
"""Secure, offline-first adapters for optional external engineering engines."""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import math
import os
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from python.spike_core.contracts import AnalysisSpec, DesignIR
from .openems_adapter_source import OPENEMS_DRIVER
from .openems_geometry_admission import screen_geometry
from .pcb_entity_ports import validate_entity_port_binding
from .openems_case_integrity import (
    MAX_JOB_JSON_BYTES,
    attach_case_integrity,
    load_strict_json,
    parse_strict_json_bytes,
    verify_case_integrity,
)
from .openems_validation import (
    DEFAULT_CELL_LIMIT,
    DEFAULT_MEMORY_LIMIT,
    validate_far_field_request,
    validate_normalized_result,
    validate_physics_and_resources,
    validate_port_geometry,
)
from .openems_validation_evidence import matching_openems_reference_evidence
from .runtime import openems_install_root as _openems_install_root
from .runtime import openems_python as _openems_python
from python.spike_core.solver_geometry import build_solver_geometry


ENGINE_CATALOG_CONTRACT = "spike/external-engine-catalog/v1"
ENGINE_JOB_CONTRACT = "spike/external-engine-job/v1"
ENGINE_RESULT_CONTRACT = "spike/external-result/v1"
MAX_CASE_INPUT_BYTES = 512 * 1024 * 1024
MAX_RESULT_BYTES = 256 * 1024 * 1024
MAX_LOG_BYTES = 8 * 1024 * 1024
MAX_ENGINE_OUTPUT_BYTES = 16 * 1024 * 1024 * 1024
RUNNABLE_OPENEMS_STATES = frozenset({"available", "experimental", "reference_validated"})


@dataclass(frozen=True)
class ExternalEngineDescriptor:
    id: str
    name: str
    role: str
    license: str
    homepage: str
    executable: str = ""
    version: str = ""
    state: str = "unavailable"
    interface: str = "process"
    capabilities: List[str] = field(default_factory=list)
    candidate_capabilities: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=lambda: ["detect"])
    reason: str = ""
    adapter_version: str = "1.0.0"
    result_contract: str = ""
    trust: str = "discovery_only"
    bundled: bool = False
    model_status: str = "unsupported"
    validation: str = ""
    validation_scope: str = ""
    validation_evidence: str = ""
    runtime_validation: Dict[str, Any] = field(default_factory=dict)
    runtime_backend: Dict[str, Any] = field(default_factory=dict)
    qualification: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def _find(names: Iterable[str], roots: Iterable[Path] = ()) -> str:
    for name in names:
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
        for root in roots:
            if not root:
                continue
            for candidate in (root / name, root / "bin" / name):
                if candidate.is_file():
                    return str(candidate.resolve())
    return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bounded_directory_size(root: Path, ceiling: int) -> int:
    total = 0
    if not root.exists():
        return total
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
        if total > ceiling:
            break
    return total


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            termination = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            # taskkill may itself be denied by a restricted Windows token.
            # A nonzero exit status is not an exception; stop the direct child
            # so a timed-out FDTD run cannot continue consuming resources.
            if termination.returncode and process.poll() is None:
                process.kill()
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            process.kill()
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _run_isolated_python(
    executable: str,
    source: bytes,
    arguments: List[str],
    *,
    cwd: Path,
    environment: Dict[str, str],
    log_path: Path,
    output_root: Path,
    timeout_seconds: int,
    output_limit_bytes: int = MAX_ENGINE_OUTPUT_BYTES,
) -> Dict[str, Any]:
    command = [executable, "-I", "-", *arguments]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        creationflags=creationflags,
        start_new_session=os.name != "nt",
    )
    stream_state = {"bytes": 0, "truncated": False}

    def capture_output() -> None:
        with log_path.open("wb") as log:
            if process.stdout is None:
                return
            for block in iter(lambda: process.stdout.read(64 * 1024), b""):
                remaining = max(MAX_LOG_BYTES - stream_state["bytes"], 0)
                if remaining:
                    log.write(block[:remaining])
                stream_state["bytes"] += len(block)
                stream_state["truncated"] = stream_state["bytes"] > MAX_LOG_BYTES

    reader = threading.Thread(target=capture_output, name="spike-external-log", daemon=True)
    reader.start()
    if process.stdin is not None:
        try:
            process.stdin.write(source)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    quota_exceeded = False
    while process.poll() is None:
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_process_tree(process)
            break
        if _bounded_directory_size(output_root, output_limit_bytes) > output_limit_bytes:
            quota_exceeded = True
            _terminate_process_tree(process)
            break
        time.sleep(0.25)
    try:
        return_code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        return_code = process.wait(timeout=10)
    reader.join(timeout=10)
    if process.stdout is not None:
        process.stdout.close()
    return {
        "command": command,
        "returncode": int(return_code),
        "timed_out": timed_out,
        "quota_exceeded": quota_exceeded,
        "log_bytes_seen": int(stream_state["bytes"]),
        "log_truncated": bool(stream_state["truncated"]),
    }


@functools.lru_cache(maxsize=8)
def _probe_openems_python(executable: str, install_root: str = "") -> tuple[bool, str, str]:
    if not executable or not Path(executable).is_file():
        return False, "", "No compatible Python executable is configured."
    if Path(executable).resolve() == Path(sys.executable).resolve():
        if importlib.util.find_spec("CSXCAD") is None or importlib.util.find_spec("openEMS") is None:
            return False, "", "The SPIKE worker Python does not contain the CSXCAD and openEMS interfaces."
    command = [
        executable,
        "-I",
        "-c",
        "from importlib.metadata import version; "
        "from CSXCAD import ContinuousStructure; from openEMS import openEMS; "
        "fdtd=openEMS(); fdtd.SetCSX(ContinuousStructure()); "
        "print(version('openEMS'))",
    ]
    try:
        environment = os.environ.copy()
        if install_root:
            environment["OPENEMS_INSTALL_PATH"] = install_root
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", f"openEMS Python probe failed: {exc}"
    if process.returncode:
        detail = (process.stderr or process.stdout).strip().splitlines()
        return False, "", detail[-1] if detail else "The openEMS Python interface could not be imported."
    return True, process.stdout.strip().splitlines()[-1] if process.stdout.strip() else "unknown", ""


def _openems_descriptor() -> ExternalEngineDescriptor:
    adapter_version = "1.3.4"
    install_root_value = _openems_install_root()
    install_root = Path(install_root_value) if install_root_value else Path()
    roots = [install_root] if install_root_value else []
    executable = _find(("openEMS", "openEMS.exe"), roots)
    python_executable = _openems_python()
    python_ready, version, reason = _probe_openems_python(python_executable, install_root_value)
    evidence = matching_openems_reference_evidence(version, adapter_version) if python_ready else None
    if python_ready:
        state = "reference_validated" if evidence else "experimental"
        actions = ["detect", "prepare", "build_setup", "run", "import_results"]
        interface = "python_process"
    elif executable:
        state = "installed_interface_missing"
        actions = ["detect", "prepare"]
        interface = "executable_only"
        reason = reason or "The solver executable is present, but the CSXCAD/openEMS Python interface is unavailable."
    else:
        state = "unavailable"
        actions = ["detect", "prepare"]
        interface = "python_process"
        reason = reason or "openEMS is not installed or discoverable."
    capabilities = [
        "fdtd_3d_experimental", "pcb_conductor_export", "dielectric_slab_export",
        "explicit_lumped_ports", "single_excitation_s_parameters", "csxcad_setup",
        "nf2ff_far_field",
    ]
    if evidence:
        capabilities.extend(["far_field", "ports", "lossy_dielectrics"])
    return ExternalEngineDescriptor(
        id="external.openems",
        name="openEMS FDTD",
        role="Experimental PCB full-wave setup, single-excitation S-parameters, and opt-in NF2FF far-field execution",
        license="GPL-3.0-or-later; SPIKE adapter Apache-2.0",
        homepage="https://docs.openems.de/",
        executable=executable,
        version=version,
        state=state,
        interface=interface,
        capabilities=capabilities,
        actions=actions,
        reason=reason,
        adapter_version=adapter_version,
        result_contract=ENGINE_RESULT_CONTRACT,
        trust="authenticated_case_and_bounded_process",
        model_status="reference_validated" if evidence else "unvalidated" if python_ready else "unsupported",
        validation=(
            "Three-level mesh convergence passed for the official simple-patch reference fixture; "
            "arbitrary-PCB and compliance accuracy remain unvalidated."
            if evidence else ""
        ),
        validation_scope=str(evidence.get("validation_scope", "")) if evidence else "",
        validation_evidence="validation_data/openems-simple-patch-v1.json" if evidence else "",
    )


def external_engine_catalog(*, refresh: bool = False) -> Dict[str, Any]:
    if refresh:
        _probe_openems_python.cache_clear()
    from python.spike_core.external_engine_discovery import discover_adapter_pending_engines

    engines = [_openems_descriptor()]
    engines.extend(ExternalEngineDescriptor(**item) for item in discover_adapter_pending_engines(refresh=refresh))
    return {
        "contract": ENGINE_CATALOG_CONTRACT,
        "offline": True,
        "installation_policy": "explicit_local_discovery_no_implicit_downloads",
        "engines": [engine.to_dict() for engine in engines],
    }


def _number(value: Any, default: float = float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _validate_openems_case(design: DesignIR, spec: AnalysisSpec, options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = validate_entity_port_binding(design, spec)
    warnings: List[Dict[str, str]] = []
    options = options or {}
    ports = spec.options.get("ports", [])
    selected = {str(net) for net in spec.net_names if str(net)}
    if not selected:
        errors.append({"code": "OPENEMS_NET_REQUIRED", "message": "Select at least one complete net for openEMS export."})
    if design.units != "mm":
        errors.append({"code": "OPENEMS_UNITS_INVALID", "message": "The openEMS adapter requires geometry normalized to millimetres."})
    if not design.stackup:
        errors.append({"code": "OPENEMS_STACKUP_REQUIRED", "message": "A physical stackup is required for a full-wave case."})
    copper_layers = [
        layer for layer in design.stackup
        if str(layer.get("type", "")).lower() in {"copper", "conductor"}
        or str(layer.get("name", "")).endswith(".Cu")
    ]
    if design.stackup and not copper_layers:
        errors.append({"code": "OPENEMS_COPPER_STACKUP_REQUIRED", "message": "The stackup does not identify a copper conductor layer."})
    dielectric_layers = [
        layer for layer in design.stackup
        if str(layer.get("type", "")).lower() not in {"copper", "conductor"}
        and (
            str(layer.get("type", "")).lower() in {"core", "prepreg", "dielectric", "soldermask", "mask"}
            or "epsilon_r" in layer or "epsilonR" in layer
        )
    ]
    start = _number(spec.frequency_start_hz or 0, 0.0)
    stop = _number(spec.frequency_stop_hz or 0, 0.0)
    try:
        points = int(spec.frequency_points or 0)
    except (TypeError, ValueError):
        points = 0
    if not math.isfinite(start) or not math.isfinite(stop) or start <= 0 or stop <= start or stop > 1e15:
        errors.append({"code": "OPENEMS_FREQUENCY_INVALID", "message": "A finite positive increasing frequency range up to 1 PHz is required."})
    if points < 2 or points > 100_000:
        errors.append({"code": "OPENEMS_FREQUENCY_POINTS_INVALID", "message": "Frequency output requires between 2 and 100,000 points."})
    if design.technology != "rigid":
        errors.append({"code": "OPENEMS_RIGID_FLEX_UNSUPPORTED", "message": "The first openEMS adapter does not flatten or bend rigid-flex geometry."})
    selected_geometry = [
        value
        for values in (design.tracks, design.zones, design.vias, design.pads)
        for value in values
        if str(value.get("net_name") or value.get("net") or "") in selected
    ]
    if selected and not selected_geometry:
        errors.append({"code": "OPENEMS_SELECTED_GEOMETRY_REQUIRED", "message": "No conductor geometry belongs to the selected net names."})
    copper_names = {str(layer.get("name", "")) for layer in copper_layers}
    unmapped_layers = set()
    for value in selected_geometry:
        layers = value.get("layers", [value.get("layer", "")])
        if not isinstance(layers, (list, tuple)):
            layers = [layers]
        for layer in layers:
            name = str(layer or "")
            # KiCad pads also list mask and paste, which are not conductors.
            # Via spans may arrive as tuples after DesignIR normalization.
            if name.endswith(".Cu") and name != "*.Cu" and name not in copper_names:
                unmapped_layers.add(name)
    if design.stackup and unmapped_layers:
        errors.append({"code": "OPENEMS_LAYER_MAPPING_REQUIRED", "message": f"Selected geometry references unmapped copper layers: {', '.join(sorted(unmapped_layers))}."})
    try:
        mesh_resolution = float(options.get("mesh_resolution_mm", 0.5))
        max_solver_time = float(options.get("max_solver_time_s", 3600))
        max_timesteps = int(options.get("max_timesteps", 10_000_000))
        dielectric_cells = int(options.get("dielectric_cells_per_layer", 3))
        threads = int(options.get("threads", 0))
    except (TypeError, ValueError):
        mesh_resolution, max_solver_time, max_timesteps, dielectric_cells, threads = float("nan"), float("nan"), -1, -1, -1
    if not math.isfinite(mesh_resolution) or not 0.0001 <= mesh_resolution <= 100:
        errors.append({"code": "OPENEMS_MESH_INVALID", "message": "Mesh resolution must be finite and between 0.0001 mm and 100 mm."})
    if not math.isfinite(max_solver_time) or not 1 <= max_solver_time <= 604_800:
        errors.append({"code": "OPENEMS_RUNTIME_LIMIT_INVALID", "message": "Maximum solver time must be between 1 second and 7 days."})
    if not 1_000 <= max_timesteps <= 2_000_000_000:
        errors.append({"code": "OPENEMS_TIMESTEP_LIMIT_INVALID", "message": "Maximum FDTD timesteps must be between 1,000 and 2,000,000,000."})
    if not 1 <= dielectric_cells <= 64:
        errors.append({"code": "OPENEMS_DIELECTRIC_MESH_INVALID", "message": "Each dielectric layer must use between 1 and 64 through-thickness cells."})
    if not 0 <= threads <= 1024:
        errors.append({"code": "OPENEMS_THREAD_LIMIT_INVALID", "message": "Thread count must be between 0 (automatic) and 1024."})
    physical = validate_physics_and_resources(design, spec, options)
    errors.extend(physical["errors"])
    far_field_options = dict(options)
    far_field_options.setdefault("air_padding_mm", physical["resources"].get("air_padding_mm"))
    far_field = validate_far_field_request(
        spec.options.get("far_field"),
        frequency_start_hz=start,
        frequency_stop_hz=stop,
        options=far_field_options,
        simulation_bounds_mm=physical["resources"].get("simulation_bounds_mm"),
        mesh_resolution_mm=mesh_resolution,
    )
    errors.extend(far_field["errors"])
    if not isinstance(ports, list) or not ports:
        warnings.append({"code": "OPENEMS_PORTS_REQUIRED_TO_RUN", "message": "The case can be prepared for geometry inspection, but solving requires explicit ports."})
    else:
        excited = sum(bool(port.get("excite", False)) for port in ports if isinstance(port, dict))
        if excited != 1:
            errors.append({"code": "OPENEMS_EXCITATION_REQUIRED", "message": "Exactly one port must be excited for each openEMS run."})
        for index, port in enumerate(ports):
            if not isinstance(port, dict) or not isinstance(port.get("start"), (list, tuple)) or not isinstance(port.get("stop"), (list, tuple)):
                errors.append({"code": "OPENEMS_PORT_INVALID", "message": f"Port {index + 1} needs explicit 3D start and stop coordinates."})
                continue
            start_point = port["start"]
            stop_point = port["stop"]
            coordinates = [*start_point, *stop_point]
            if len(start_point) != 3 or len(stop_point) != 3 or not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in coordinates) or list(start_point) == list(stop_point):
                errors.append({"code": "OPENEMS_PORT_INVALID", "message": f"Port {index + 1} needs two distinct finite 3D coordinates."})
            impedance = port.get("impedance_ohm", 50)
            if not isinstance(impedance, (int, float)) or not math.isfinite(float(impedance)) or float(impedance) <= 0:
                errors.append({"code": "OPENEMS_PORT_IMPEDANCE_INVALID", "message": f"Port {index + 1} needs a finite positive impedance."})
            if str(port.get("direction", "z")).lower() not in {"x", "y", "z"}:
                errors.append({"code": "OPENEMS_PORT_DIRECTION_INVALID", "message": f"Port {index + 1} direction must be x, y, or z."})
        errors.extend(validate_port_geometry(design, spec, ports, mesh_resolution))
    if any(_number(layer.get("loss_tangent", layer.get("lossTangent", 0)), 0.0) > 0 for layer in dielectric_layers):
        warnings.append({"code": "OPENEMS_DIELECTRIC_LOSS_APPROXIMATION", "message": "Loss tangent is converted to an equivalent conductivity at the band-center frequency; broadband dispersive material fitting is not implemented."})
    selected_vias = [via for via in design.vias if str(via.get("net_name") or via.get("net") or "") in selected]
    if selected_vias:
        warnings.append({"code": "OPENEMS_VIA_BARREL_APPROXIMATION", "message": f"{len(selected_vias)} vias use extracted drill/span with configured plating thickness; padstack detail requires setup review."})
    curved_pads = [pad for pad in design.pads
                   if str(pad.get("net_name") or pad.get("net") or "") in selected
                   and str(pad.get("shape", "")).lower() in {"circle", "oval", "roundrect"}]
    if curved_pads:
        warnings.append({"code": "OPENEMS_PAD_CONTOUR_FACETING", "message": f"{len(curved_pads)} curved pads use polygons with at most 0.001 mm radial sagitta; verify contour and mesh convergence."})
    selected_bonds = [bond for bond in design.component_bonds if bool(bond.get("enabled", True))
                      and str(bond.get("net_name") or bond.get("net") or "") in selected]
    invalid_bonds = [bond for bond in selected_bonds if str(bond.get("status", "")) not in {"ready", "explicit", "inferred"}]
    if invalid_bonds:
        errors.append({"code": "OPENEMS_COMPONENT_BOND_INVALID", "message": f"{len(invalid_bonds)} selected component bonds require review before full-wave case generation."})
    warnings.append({"code": "OPENEMS_OUTLINE_APPROXIMATION", "message": "The first adapter uses the selected conductor bounds for dielectric slabs; inspect the generated setup where the physical board outline is significant."})
    warnings.append({"code": "OPENEMS_TRANSLATION_EXPERIMENTAL", "message": "PCB-to-CSXCAD translation is experimental and requires mesh, port, and geometry inspection before interpretation."})
    if far_field["enabled"]:
        warnings.append({
            "code": "OPENEMS_FAR_FIELD_VALIDATION_REQUIRED",
            "message": "NF2FF execution and numeric normalization do not establish solver validation; mesh convergence and benchmark or measurement comparison remain required.",
        })
    descriptor = _openems_descriptor()
    geometry_screen = screen_geometry(design, spec)
    # Geometry-loss blockers prohibit field solves, while retaining setup-only inspection.
    run_blockers = [
        {"code": issue["code"], "message": issue["reason"], "source_id": issue["source_id"]}
        for issue in geometry_screen["issues"]
    ]
    return {
        "contract": "spike/openems-preflight/v1",
        "can_prepare": not errors,
        "can_run": not errors and not run_blockers and bool(ports) and descriptor.state in RUNNABLE_OPENEMS_STATES,
        "run_blockers": run_blockers,
        "geometry_screen": geometry_screen,
        "errors": errors,
        "warnings": warnings,
        "engine": descriptor.to_dict(),
        "coverage": {
            "tracks": len(design.tracks),
            "zones": len(design.zones),
            "vias": len(design.vias),
            "pads": len(design.pads),
            "component_bonds": len(selected_bonds),
            "stackup_layers": len(design.stackup),
            "ports": len(ports) if isinstance(ports, list) else 0,
        },
        "resources": physical["resources"],
        "far_field": far_field,
    }


def _object_map(design: DesignIR) -> Dict[str, Any]:
    entities = []
    for kind, values in (
        ("track", design.tracks), ("zone", design.zones), ("via", design.vias),
        ("pad", design.pads), ("component", design.components), ("component_bond", design.component_bonds),
    ):
        for index, value in enumerate(values):
            entities.append({
                "engine_id": f"{kind}-{index + 1}",
                "design_id": str(value.get("id", f"{kind}-{index + 1}")),
                "kind": kind,
                "net": str(value.get("net_name") or value.get("net") or ""),
                "layer": str(value.get("layer") or ""),
            })
    return {
        "contract": "spike/external-object-map/v1",
        "coordinate_transform": {
            "source_plane": "XY",
            "source_normal": "+Z",
            "engine_plane": "XY",
            "engine_normal": "+Z",
            "length_unit": "mm",
            "scale_to_m": 0.001,
            "origin_mm": design.metadata.get("origin", [0, 0, 0]),
        },
        "entities": entities,
    }




def _adapter_source_sha256() -> str:
    return hashlib.sha256(OPENEMS_DRIVER.encode("utf-8")).hexdigest()


def _default_job_base() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "SPIKE" / "jobs" / "openems"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SPIKE" / "jobs" / "openems"
    state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state") / "spike" / "jobs" / "openems"


def _job_root(output_dir: str | Path | None) -> Path:
    if output_dir:
        root = Path(output_dir).expanduser().resolve()
    else:
        root = (_default_job_base() / str(uuid.uuid4())).resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    if os.name != "nt":
        root.chmod(0o700)
    return root


def prepare_openems_case(
    design: DesignIR,
    spec: AnalysisSpec,
    output_dir: str | Path | None = None,
    options: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_options = dict(options or {})
    validation = _validate_openems_case(design, spec, normalized_options)
    if not validation["can_prepare"]:
        return {"status": "blocked", "validation": validation, "engine": validation["engine"]}
    root = _job_root(output_dir)
    for name in ("engine-input", "engine-output", "logs"):
        (root / name).mkdir()
    geometry = build_solver_geometry(design, spec)
    object_map = _object_map(design)
    engine = _openems_descriptor()
    job = {
        "contract": ENGINE_JOB_CONTRACT,
        "job_id": spec.analysis_id or str(uuid.uuid4()),
        "created_at_epoch_s": time.time(),
        "engine": engine.to_dict(),
        "adapter_source_sha256": _adapter_source_sha256(),
        "execution_source": "trusted_adapter_over_isolated_stdin",
        "analysis": spec.to_dict(),
        "options": normalized_options,
        "validation": validation,
        "files": {
            "geometry": "geometry.json",
            "object_map": "object-map.json",
            "driver": "engine-input/run_openems.py",
            "result": "engine-output/normalized-result.json",
        },
    }
    payload_files = {
        root / "geometry.json": geometry,
        root / "object-map.json": object_map,
    }
    for path, payload in payload_files.items():
        path.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    driver = root / "engine-input" / "run_openems.py"
    driver.write_text(OPENEMS_DRIVER, encoding="utf-8", newline="\n")
    attach_case_integrity(job, root)
    job_path = root / "job.json"
    job_path.write_text(json.dumps(job, indent=2, allow_nan=False), encoding="utf-8")
    case_files = (job_path, *payload_files.keys(), driver)
    manifest = {
        "contract": "spike/external-artifacts/v1",
        "engine": engine.id,
        "adapter_version": engine.adapter_version,
        "files": [
            {"path": str(path.relative_to(root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in case_files
        ],
    }
    (root / "artifacts.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total_bytes = sum(item["bytes"] for item in manifest["files"])
    if total_bytes > MAX_CASE_INPUT_BYTES:
        raise ValueError("The generated openEMS case exceeds the 512 MiB input limit.")
    return {
        "contract": "spike/openems-case-status/v1",
        "status": "ready_to_run" if validation["can_run"] else "prepared_review_required",
        "case_dir": str(root),
        "validation": validation,
        "engine": engine.to_dict(),
        "artifacts": manifest,
    }


def _case_inputs(job: Dict[str, Any], geometry: Dict[str, Any]) -> tuple[DesignIR, AnalysisSpec]:
    if geometry.get("contract") != "spike/solver-geometry/v1":
        raise ValueError("The prepared case has an unsupported geometry contract.")
    analysis = job.get("analysis")
    conductors = geometry.get("conductors")
    assembly = geometry.get("assembly")
    if not isinstance(analysis, dict) or not isinstance(conductors, dict) or not isinstance(assembly, dict):
        raise ValueError("The prepared case is missing normalized analysis or geometry data.")
    try:
        spec = AnalysisSpec(**analysis)
    except TypeError as exc:
        raise ValueError(f"The prepared analysis definition is invalid: {exc}") from exc
    design = DesignIR(
        design_id=str(geometry.get("design_id", "")),
        units=str(geometry.get("units", "")),
        layers=list(assembly.get("layers", [])),
        tracks=list(conductors.get("tracks", [])),
        zones=list(conductors.get("zones", [])),
        vias=list(conductors.get("vias", [])),
        pads=list(conductors.get("pads", [])),
        components=list(assembly.get("components", [])),
        component_bonds=list(assembly.get("component_bonds", [])),
        connectors=list(assembly.get("connectors", [])),
        stackup=list(assembly.get("stackup", [])),
        technology=str(assembly.get("technology", "rigid")),
        regions=list(assembly.get("regions", [])),
        bends=list(assembly.get("bends", [])),
        metadata=dict(geometry.get("source_metadata", {})),
    )
    return design, spec


def _validated_job(
    case_dir: str | Path,
) -> tuple[Path, Dict[str, Any], Dict[str, Any], AnalysisSpec, Dict[str, Any]]:
    root = Path(case_dir).expanduser().resolve()
    job_path = root / "job.json"
    if not job_path.is_file():
        raise ValueError("The selected directory is not a SPIKE external-engine job.")
    job = load_strict_json(job_path, max_bytes=MAX_JOB_JSON_BYTES, label="external-engine job")
    if job.get("contract") != ENGINE_JOB_CONTRACT or job.get("engine", {}).get("id") != "external.openems":
        raise ValueError("The selected job is not a compatible SPIKE openEMS case.")
    if job.get("adapter_source_sha256") != _adapter_source_sha256():
        raise ValueError("The prepared case uses a different openEMS adapter revision; prepare it again before execution.")
    files = job.get("files")
    if not isinstance(files, dict):
        raise ValueError("The external-engine job does not contain a file manifest.")
    driver_name = files.get("driver")
    result_name = files.get("result")
    geometry_name = files.get("geometry")
    if not isinstance(driver_name, str) or not isinstance(result_name, str) or not isinstance(geometry_name, str):
        raise ValueError("The external-engine job has an invalid driver, geometry, or result path.")
    driver = (root / driver_name).resolve()
    result = (root / result_name).resolve()
    geometry_path = (root / geometry_name).resolve()
    if not driver.is_relative_to(root) or not driver.is_file():
        raise ValueError("The generated openEMS driver is missing or outside the job directory.")
    if not result.is_relative_to(root):
        raise ValueError("The normalized openEMS result path is outside the job directory.")
    if not geometry_path.is_relative_to(root) or not geometry_path.is_file():
        raise ValueError("The normalized openEMS geometry is missing or outside the job directory.")
    signed_inputs = verify_case_integrity(job, root)
    geometry = parse_strict_json_bytes(signed_inputs["geometry"], label="external-engine geometry")
    design, spec = _case_inputs(job, geometry)
    options = job.get("options")
    if not isinstance(options, dict):
        raise ValueError("The prepared case options are invalid.")
    validation = _validate_openems_case(design, spec, options)
    return root, job, validation, spec, geometry


def _execution_source(job: Dict[str, Any], geometry: Dict[str, Any]) -> bytes:
    job_snapshot = json.dumps(job, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    geometry_snapshot = json.dumps(geometry, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    source = (
        f"SPIKE_JOB_SNAPSHOT = {job_snapshot!r}\n"
        f"SPIKE_GEOMETRY_SNAPSHOT = {geometry_snapshot!r}\n"
        + OPENEMS_DRIVER
    ).encode("utf-8")
    if len(source) > MAX_CASE_INPUT_BYTES:
        raise ValueError("The authenticated openEMS execution snapshot exceeds the 512 MiB input limit.")
    return source


def run_openems_case(
    case_dir: str | Path,
    *,
    setup_only: bool = False,
    timeout_seconds: int = 3600,
) -> Dict[str, Any]:
    root, job, validation, spec, geometry = _validated_job(case_dir)
    engine = _openems_descriptor()
    if engine.state not in RUNNABLE_OPENEMS_STATES:
        return {"status": "solver_unavailable", "message": engine.reason, "engine": engine.to_dict(), "case_dir": str(root)}
    if not validation.get("can_prepare", False):
        return {"status": "blocked", "message": "The prepared openEMS inputs no longer pass preflight.", "validation": validation, "case_dir": str(root)}
    if setup_only and validation.get("run_blockers"):
        return {"status": "blocked", "message": "The selected geometry has unsupported openEMS translations; a complete CSXCAD setup cannot be generated.", "validation": validation, "case_dir": str(root)}
    if not setup_only and not validation.get("can_run", False):
        return {"status": "blocked", "message": "The openEMS preflight does not permit a solver run.", "validation": validation, "case_dir": str(root)}
    python_executable = _openems_python()
    arguments = ["--job", str(root)]
    if setup_only:
        arguments.append("--setup-only")
    environment = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "WINDIR", "HOME", "USERPROFILE", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
        if os.environ.get(key)
    }
    environment.update({
        "TEMP": str(root / "engine-output"),
        "TMP": str(root / "engine-output"),
        "TMPDIR": str(root / "engine-output"),
        "OPENEMS_INSTALL_PATH": _openems_install_root(),
    })
    configured_limit = math.ceil(float(job["options"].get("max_solver_time_s", 3600)))
    timeout = max(10, min(int(timeout_seconds), configured_limit, 7 * 24 * 3600))
    log_path = root / "logs" / "openems.log"
    run_id = str(uuid.uuid4())
    execution_job = json.loads(json.dumps(job, allow_nan=False))
    execution_job["run_context"] = {
        "run_id": run_id,
        "job_id": str(job.get("job_id", "")),
        "input_digest": str(job.get("integrity", {}).get("payload_sha256", "")),
    }
    try:
        source = _execution_source(execution_job, geometry)
    except (TypeError, ValueError) as exc:
        return {"status": "blocked", "message": f"The authenticated execution snapshot is invalid: {exc}", "case_dir": str(root)}
    started = time.perf_counter()
    try:
        process = _run_isolated_python(
            python_executable,
            source,
            arguments,
            cwd=root,
            environment=environment,
            log_path=log_path,
            output_root=root / "engine-output",
            timeout_seconds=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"status": "failed", "message": f"openEMS could not be launched: {exc}", "case_dir": str(root)}
    duration = time.perf_counter() - started
    if process["timed_out"]:
        return {"status": "failed", "message": f"openEMS exceeded the {timeout}-second execution limit and its process tree was terminated.", "duration_s": duration, "case_dir": str(root)}
    if process["quota_exceeded"]:
        return {"status": "failed", "message": "openEMS exceeded the 16 GiB case-output quota and its process tree was terminated.", "duration_s": duration, "case_dir": str(root)}
    result_path = (root / job["files"]["result"]).resolve()
    if process["returncode"] or not result_path.is_file():
        diagnostic = log_path.read_text(encoding="utf-8", errors="replace")[-8000:] if log_path.is_file() else ""
        return {"status": "failed", "message": f"openEMS exited with code {process['returncode']}.", "diagnostic": diagnostic, "duration_s": duration, "log_truncated": process["log_truncated"], "case_dir": str(root)}
    if result_path.stat().st_size > MAX_RESULT_BYTES:
        return {"status": "failed", "message": "The normalized openEMS result exceeds the 256 MiB import limit.", "duration_s": duration, "case_dir": str(root)}
    try:
        result = validate_normalized_result(
            load_strict_json(result_path, max_bytes=MAX_RESULT_BYTES, label="normalized openEMS result"),
            setup_only=setup_only,
            expected_points=int(spec.frequency_points),
            expected_start_hz=float(spec.frequency_start_hz),
            expected_stop_hz=float(spec.frequency_stop_hz),
            expected_job_id=str(job.get("job_id", "")),
            expected_input_digest=str(job.get("integrity", {}).get("payload_sha256", "")),
            expected_run_id=run_id,
            expected_max_timesteps=int(job["options"].get("max_timesteps", 10_000_000)),
            expected_cell_limit=int(job["options"].get("max_estimated_cells", DEFAULT_CELL_LIMIT)),
            expected_memory_limit_bytes=int(job["options"].get("max_estimated_memory_bytes", DEFAULT_MEMORY_LIMIT)),
            expected_compact_edges=job["options"].get("experimental_compact_edge_grid", False) is True,
            ports=list(spec.options.get("ports", [])),
            root=root,
            expected_far_field=validation.get("far_field", {}).get("request"),
        )
    except (TypeError, ValueError) as exc:
        return {"status": "failed", "message": f"openEMS returned an invalid normalized result: {exc}", "duration_s": duration, "case_dir": str(root)}
    result["provenance"] = {
        "engine": engine.id,
        "engine_version": engine.version,
        "adapter_version": engine.adapter_version,
        "python_executable_sha256": _sha256(Path(python_executable)),
        "duration_s": duration,
        "job_id": job.get("job_id"),
        "isolated_python": True,
        "log_truncated": process["log_truncated"],
    }
    result["case_dir"] = str(root)
    return result
