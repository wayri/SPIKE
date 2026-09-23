"""Deterministic OpenFOAM thermal-case adapter.

The supported slice is deliberately narrow: steady-state single-region air cases
for natural or forced convection. It does not claim PCB conjugate heat transfer
or external numerical validation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict

from .openfoam_runtime import detect_openfoam_runtime
from .sparselizard_process import SparseLizardAdapterError, run_adapter_process
from .thermal import ThermalScenario, validate_scenario


CASE_CONTRACT = "spike/openfoam-thermal-case/v1"
RESULT_CONTRACT = "spike/openfoam-thermal-result/v1"
ADAPTER_CONTRACT = "spike/openfoam-adapter/v1"
ADAPTER_VERSION = "1.0.0"
MAX_RESULT_BYTES = 256 * 1024**2
MAX_FIELD_SAMPLES = 1_000_000
_REQUIRED_COMMANDS = ("blockMesh", "topoSet", "buoyantBoussinesqSimpleFoam", "postProcess")
_SAFE_IDENTIFIER = re.compile(r"[^A-Za-z0-9_.-]+")
_SCALAR_LIST = re.compile(r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;", re.DOTALL)
_VECTOR_LIST = re.compile(r"internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;", re.DOTALL)
_VECTOR_VALUE = re.compile(r"\(\s*([^()]+?)\s*\)")
_SCALAR_UNIFORM = re.compile(r"internalField\s+uniform\s+([^;\s]+)\s*;")
_VECTOR_UNIFORM = re.compile(r"internalField\s+uniform\s+\(\s*([^()]+?)\s*\)\s*;")


class OpenFoamAdapterError(RuntimeError):
    """Raised when a case is outside the adapter's safe execution contract."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise OpenFoamAdapterError(f"{label} must be finite.")
    result = float(value)
    if positive and result <= 0:
        raise OpenFoamAdapterError(f"{label} must be positive.")
    return result


def _point(value: Any, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise OpenFoamAdapterError(f"{label} must contain three coordinates.")
    return [_number(item, label) for item in value]


def _safe_id(value: Any, fallback: str) -> str:
    result = _SAFE_IDENTIFIER.sub("_", str(value or "")).strip("._")[:64]
    return result or fallback


def _write(root: Path, relative: str, content: str) -> None:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise OpenFoamAdapterError("Generated case file escaped its case directory.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def _case_files(root: Path) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and path.name != "spike_case.json":
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _verify_case_files(root: Path, expected: Dict[str, Any]) -> bool:
    """Verify generated inputs without treating solver output as tampering."""
    if not isinstance(expected, dict):
        return False
    for relative, digest in expected.items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            return False
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.is_symlink():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return False
    return True


def _block_mesh(scenario: ThermalScenario) -> str:
    size = _number(scenario.mesh.get("cell_size_mm"), "mesh.cell_size_mm", positive=True)
    dimensions = {axis: _number(scenario.bounding_volume_mm.get(axis), f"bounding_volume_mm.{axis}", positive=True) / 1000 for axis in ("x", "y", "z")}
    cells = {axis: max(1, math.ceil(dimensions[axis] * 1000 / size)) for axis in dimensions}
    if math.prod(cells.values()) > int(scenario.mesh.get("max_cells", 0)):
        raise OpenFoamAdapterError("Requested OpenFOAM mesh exceeds mesh.max_cells.")
    return f"""FoamFile
{{
 version 2.0; format ascii; class dictionary; object blockMeshDict;
}}
scale 1;
vertices
(
 (0 0 0) ({dimensions["x"]:.12g} 0 0) ({dimensions["x"]:.12g} {dimensions["y"]:.12g} 0) (0 {dimensions["y"]:.12g} 0)
 (0 0 {dimensions["z"]:.12g}) ({dimensions["x"]:.12g} 0 {dimensions["z"]:.12g}) ({dimensions["x"]:.12g} {dimensions["y"]:.12g} {dimensions["z"]:.12g}) (0 {dimensions["y"]:.12g} {dimensions["z"]:.12g})
);
blocks (hex (0 1 2 3 4 5 6 7) ({cells["x"]} {cells["y"]} {cells["z"]}) simpleGrading (1 1 1));
edges ();
boundary
(
 inlet {{ type patch; faces ((0 4 7 3)); }}
 outlet {{ type patch; faces ((1 2 6 5)); }}
 walls {{ type wall; faces ((0 1 5 4) (3 7 6 2) (0 3 2 1) (4 5 6 7)); }}
);
mergePatchPairs ();
"""


def _topo_set(scenario: ThermalScenario) -> tuple[str, list[Dict[str, Any]]]:
    half = max(_number(scenario.mesh.get("cell_size_mm"), "mesh.cell_size_mm", positive=True), 1.0) / 2000
    actions, sources = [], []
    for index, source in enumerate(scenario.heat_sources):
        source_id = _safe_id(source.get("id"), f"source_{index + 1}")
        x, y, z = (coordinate / 1000 for coordinate in _point(source.get("position"), f"source {source_id} position"))
        power = _number(source.get("power_w", 0), f"source {source_id} power_w")
        actions.append(f""" {{
  name {source_id}; type cellSet; action new; source boxToCell;
  sourceInfo {{ box ({x-half:.12g} {y-half:.12g} {z-half:.12g}) ({x+half:.12g} {y+half:.12g} {z+half:.12g}); }}
 }}""")
        sources.append({"id": str(source.get("id") or source_id), "cell_set": source_id, "power_w": power})
    return "FoamFile\n{ version 2.0; format ascii; class dictionary; object topoSetDict; }\nactions\n(\n" + "\n".join(actions) + "\n);\n", sources


def _initial_fields(scenario: ThermalScenario) -> Dict[str, str]:
    ambient = _number(scenario.ambient_temperature_c, "ambient_temperature_c") + 273.15
    velocity = [0.0, 0.0, 0.0]
    if scenario.convection == "forced":
        fan = next((item for item in scenario.fans if _number(item.get("flow_rate_m3_s", 0), "fan flow") > 0), None)
        if fan is None:
            raise OpenFoamAdapterError("Forced-convection case requires a positive-flow fan.")
        direction = _point(fan.get("direction"), "fan direction")
        magnitude = math.sqrt(sum(item * item for item in direction))
        if magnitude <= 0:
            raise OpenFoamAdapterError("fan direction must not be zero.")
        area = _number(scenario.bounding_volume_mm.get("y"), "bounding_volume_mm.y", positive=True) * _number(scenario.bounding_volume_mm.get("z"), "bounding_volume_mm.z", positive=True) / 1_000_000
        speed = _number(fan.get("flow_rate_m3_s"), "fan flow_rate_m3_s", positive=True) / area
        velocity = [speed * item / magnitude for item in direction]
    vector = " ".join(f"{item:.12g}" for item in velocity)
    return {
        "0/T": f"""FoamFile {{ version 2.0; format ascii; class volScalarField; object T; }}
dimensions [0 0 0 1 0 0 0]; internalField uniform {ambient:.12g};
boundaryField {{ inlet {{ type fixedValue; value uniform {ambient:.12g}; }} outlet {{ type inletOutlet; inletValue uniform {ambient:.12g}; value uniform {ambient:.12g}; }} walls {{ type zeroGradient; }} }}
""",
        "0/U": f"""FoamFile {{ version 2.0; format ascii; class volVectorField; object U; }}
dimensions [0 1 -1 0 0 0 0]; internalField uniform ({vector});
boundaryField {{ inlet {{ type fixedValue; value uniform ({vector}); }} outlet {{ type zeroGradient; }} walls {{ type noSlip; }} }}
""",
        "0/p_rgh": """FoamFile { version 2.0; format ascii; class volScalarField; object p_rgh; }
dimensions [0 2 -2 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type fixedFluxPressure; value uniform 0; } outlet { type fixedValue; value uniform 0; } walls { type fixedFluxPressure; value uniform 0; } }
""",
        "0/alphat": """FoamFile { version 2.0; format ascii; class volScalarField; object alphat; }
dimensions [0 2 -1 0 0 0 0]; internalField uniform 0;
boundaryField { inlet { type fixedValue; value uniform 0; } outlet { type zeroGradient; } walls { type fixedValue; value uniform 0; } }
""",
    }


def _gravity(value: str) -> str:
    vectors = {"+X": "(9.81 0 0)", "-X": "(-9.81 0 0)", "+Y": "(0 9.81 0)", "-Y": "(0 -9.81 0)", "+Z": "(0 0 9.81)", "-Z": "(0 0 -9.81)"}
    return f"""FoamFile {{ version 2.0; format ascii; class uniformDimensionedVectorField; object g; }}
dimensions [0 1 -2 0 0 0 0]; value {vectors[value]};
"""


def _static_files(scenario: ThermalScenario, sources: list[Dict[str, Any]]) -> Dict[str, str]:
    # buoyantBoussinesqSimpleFoam solves temperature directly. Convert each
    # requested thermal power to an absolute temperature-equation source using
    # reference air density and heat capacity. This is an air heating surrogate,
    # not a PCB solid or conjugate heat-transfer model.
    rho_air = 1.225
    cp_air = 1005.0
    options = "\n\n".join(
        f"""{source["cell_set"]}
{{
 type scalarSemiImplicitSource;
 active true;
 selectionMode cellSet;
 cellSet {source["cell_set"]};
 volumeMode absolute;
 sources {{ T ({source["power_w"] / (rho_air * cp_air):.12g} 0); }}
}}""" for source in sources
    )
    max_iterations = int(scenario.run.get("max_iterations", 2000))
    residual_target = _number(scenario.run.get("residual_target", 1e-6), "run.residual_target", positive=True)
    return {
        "system/controlDict": f"""FoamFile {{ version 2.0; format ascii; class dictionary; object controlDict; }}
application buoyantBoussinesqSimpleFoam; startFrom startTime; startTime 0; stopAt endTime; endTime {max_iterations}; deltaT 1; writeControl timeStep; writeInterval {max_iterations}; writeFormat ascii; writePrecision 12; runTimeModifiable false;
""",
        "system/fvSchemes": """FoamFile { version 2.0; format ascii; class dictionary; object fvSchemes; }
ddtSchemes { default steadyState; } gradSchemes { default cellLimited Gauss linear 1; }
divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U); div(phi,T) bounded Gauss linearUpwind grad(T); div((nuEff*dev2(T(grad(U))))) Gauss linear; }
laplacianSchemes { default Gauss linear limited 0.5; } interpolationSchemes { default linear; } snGradSchemes { default limited 0.5; } wallDist { method meshWave; }
""",
        "system/fvSolution": f"""FoamFile {{ version 2.0; format ascii; class dictionary; object fvSolution; }}
solvers {{ p_rgh {{ solver GAMG; tolerance 1e-8; relTol 0.05; smoother GaussSeidel; }} "(U|T)" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-8; relTol 0.05; }} }}
SIMPLE {{ nNonOrthogonalCorrectors 0; residualControl {{ p_rgh {residual_target:.12g}; U {residual_target:.12g}; T {residual_target:.12g}; }} }} relaxationFactors {{ fields {{ p_rgh 0.3; }} equations {{ U 0.7; T 0.7; }} }}
""",
        "constant/transportProperties": """FoamFile { version 2.0; format ascii; class dictionary; object transportProperties; }
transportModel Newtonian; nu [0 2 -1 0 0 0 0] 1.5e-05; Pr [0 0 0 0 0 0 0] 0.71; Prt [0 0 0 0 0 0 0] 0.85; beta [0 0 0 -1 0 0 0] 0.0034; TRef 298.15;
""",
        "constant/turbulenceProperties": """FoamFile { version 2.0; format ascii; class dictionary; object turbulenceProperties; }
simulationType laminar;
""",
        "system/fvOptions": "FoamFile { version 2.0; format ascii; class dictionary; object fvOptions; }\n" + options + "\n",
        "README.generated": """Generated by SPIKE OpenFOAM adapter v1.
Scope: experimental steady-state single-region air convection only.
Excluded: PCB solids, component bonds, radiation, potting, cabinet, and external validation.
Execution requires explicit experimental enablement and a native Linux or fixed-argv WSL OpenFOAM runtime.
Normalized output: postProcessing/spike/thermal-result.json
""",
    }


def _load_case(case_dir: str | Path) -> tuple[Path, Dict[str, Any]]:
    root = Path(case_dir).expanduser().resolve(strict=True)
    manifest_path = root / "spike_case.json"
    if root.is_symlink() or not manifest_path.is_file() or manifest_path.is_symlink():
        raise OpenFoamAdapterError("The directory is not a regular prepared SPIKE OpenFOAM case.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenFoamAdapterError("The OpenFOAM case manifest is not valid UTF-8 JSON.") from exc
    if not isinstance(manifest, dict) or manifest.get("contract") != CASE_CONTRACT:
        raise OpenFoamAdapterError("The supplied directory is not an OpenFOAM thermal case v1.")
    if not _verify_case_files(root, manifest.get("files", {})):
        raise OpenFoamAdapterError("The OpenFOAM case files changed after preparation; generate a new case.")
    return root, manifest


def openfoam_capabilities() -> Dict[str, Any]:
    runtime = detect_openfoam_runtime()
    multi_region_commands = ("chtMultiRegionFoam", "chtMultiRegionSimpleFoam", "splitMeshRegions", "checkMesh")
    commands = {name: shutil.which(name) or "" for name in (*_REQUIRED_COMMANDS, "foamRun", *multi_region_commands)}
    native_ready = runtime["transport"] == "native_process" and all(commands[name] for name in _REQUIRED_COMMANDS)
    wsl_ready = runtime["transport"] == "wsl_process" and bool(runtime.get("command_prefix"))
    if wsl_ready:
        commands = {name: f'{runtime["executable"]} {name}' for name in (*_REQUIRED_COMMANDS, "foamRun", *multi_region_commands)}
    return {
        "available": bool(runtime["available"]),
        "commands": commands,
        "transport": runtime["transport"],
        "executable": runtime["executable"],
        "version": runtime["version"],
        "distribution": runtime["distribution"],
        "case_generator": "deterministic_air_convection_v1",
        "supported_case_modes": ["steady_state_natural_convection", "steady_state_forced_convection"],
        "multi_region": {
            "translator_contract": "spike/openfoam-multiregion-adapter/v1",
            "case_contract": "spike/openfoam-multiregion-case/v1",
            "translation_ready": True,
            "execution_ready": False,
            "required_commands": list(multi_region_commands),
            "reason": "Evidence-backed region/material/contact translation is available; qualified mesh materialization, runnable dictionaries, numerical correlation, and package qualification remain required.",
        },
        "execution_ready": native_ready or wsl_ready,
        "execution_gate": "explicit_experimental_enablement",
        "validation_status": "not_externally_validated",
        "offline": True,
        "process_transport": "fixed_argv_no_shell",
    }


def _wsl_case_path(runtime: Dict[str, Any], root: Path) -> str:
    """Convert a verified local case directory through WSL without shell parsing."""
    launcher = str(runtime.get("launcher") or "")
    distribution = str(runtime.get("distribution") or "")
    if not launcher or not distribution:
        raise OpenFoamAdapterError("WSL OpenFOAM runtime is missing its launcher or distribution.")
    resolved = root.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if len(drive) != 1 or not drive.isalpha():
        raise OpenFoamAdapterError("WSL OpenFOAM execution requires a Windows drive-backed prepared case directory.")
    relative = resolved.as_posix()[2:].lstrip("/")
    candidate = f"/mnt/{drive}/{relative}"
    # WSL rewrites Windows-path arguments before wslpath receives them.  Build
    # its standard mounted-drive path ourselves and validate it with fixed argv.
    process = subprocess.run(
        [launcher, "-d", distribution, "--", "test", "-d", candidate],
        capture_output=True,
        text=True,
        timeout=20,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.returncode != 0:
        raise OpenFoamAdapterError("WSL could not map the prepared case directory to a Linux path.")
    return candidate


def _execution_command(runtime: Dict[str, Any], command: str, root: Path, extra: list[str] | None = None) -> list[str]:
    arguments = list(extra or [])
    if runtime.get("transport") == "native_process":
        executable = shutil.which(command)
        if not executable:
            raise OpenFoamAdapterError(f"Native OpenFOAM command {command} is unavailable.")
        return [executable, "-case", str(root), *arguments]
    if runtime.get("transport") == "wsl_process":
        prefix = runtime.get("command_prefix")
        if not isinstance(prefix, list) or not all(isinstance(item, str) and item for item in prefix):
            raise OpenFoamAdapterError("WSL OpenFOAM runtime has an invalid command prefix.")
        # /usr/bin/openfoam2606 initializes its own environment, then runs this
        # known application and argument vector. Python never invokes a shell.
        return [*prefix, command, "-case", _wsl_case_path(runtime, root), *arguments]
    raise OpenFoamAdapterError("No supported OpenFOAM process transport is available.")


def prepare_case(scenario: ThermalScenario, output_dir: str | Path) -> Dict[str, Any]:
    validation = validate_scenario(scenario)
    root = Path(output_dir).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        return {"status": "blocked", "message": "OpenFOAM case directory must be empty to prevent stale output import.", "case_dir": str(root), "validation": validation}
    if not validation["valid"] or not validation["capability"].get("case_generation_ready", False):
        return {"status": "blocked", "message": "The thermal scenario is outside the supported deterministic OpenFOAM case boundary.", "case_dir": str(root), "validation": validation}
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        return {"status": "blocked", "message": "OpenFOAM case directory must not be a symbolic link.", "case_dir": str(root), "validation": validation}
    try:
        scenario_data = scenario.to_dict()
        _write(root, "spike_scenario.json", json.dumps(scenario_data, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
        _write(root, "system/blockMeshDict", _block_mesh(scenario))
        topo_set, sources = _topo_set(scenario)
        _write(root, "system/topoSetDict", topo_set)
        for relative, content in _static_files(scenario, sources).items():
            _write(root, relative, content)
        _write(root, "constant/g", _gravity(scenario.gravity))
        for relative, content in _initial_fields(scenario).items():
            _write(root, relative, content)
    except (OSError, TypeError, ValueError, OpenFoamAdapterError) as exc:
        return {"status": "blocked", "message": f"OpenFOAM case generation failed: {exc}", "case_dir": str(root), "validation": validation}
    manifest = {
        "contract": CASE_CONTRACT, "adapter_contract": ADAPTER_CONTRACT, "adapter_version": ADAPTER_VERSION,
        "scenario": {"id": scenario.scenario_id, "name": scenario.name, "digest": _digest(scenario.to_dict())},
        "mode": f"steady_state_{scenario.convection}_convection",
        "result_path": "postProcessing/spike/thermal-result.json",
        "model_status": "experimental", "validation_status": "not_externally_validated", "sources": sources, "files": _case_files(root),
    }
    _write(root, "spike_case.json", json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n")
    capabilities = openfoam_capabilities()
    return {
        "contract": CASE_CONTRACT, "case_dir": str(root),
        "status": "prepared_experimental_case" if capabilities["execution_ready"] else "prepared_runtime_unavailable",
        "can_run": bool(capabilities["execution_ready"]),
        "validation": validation, "capabilities": capabilities,
        "provenance": {"adapter_contract": ADAPTER_CONTRACT, "adapter_version": ADAPTER_VERSION, "scenario_digest": manifest["scenario"]["digest"], "model_status": "experimental"},
    }


def _field(payload: Dict[str, Any], name: str, unit: str, vector: bool = False) -> list[Dict[str, Any]]:
    fields = payload.get("fields")
    field = fields.get(name) if isinstance(fields, dict) else None
    if not isinstance(field, dict) or field.get("unit") != unit or not isinstance(field.get("samples"), list):
        raise OpenFoamAdapterError(f"OpenFOAM result requires {name} samples in {unit}.")
    if not 0 < len(field["samples"]) <= MAX_FIELD_SAMPLES:
        raise OpenFoamAdapterError(f"OpenFOAM result {name} sample count is outside its limit.")
    result = []
    for index, sample in enumerate(field["samples"]):
        if not isinstance(sample, dict):
            raise OpenFoamAdapterError(f"OpenFOAM result {name} sample {index} must be an object.")
        value = _point(sample.get("value"), f"{name} sample {index} value") if vector else _number(sample.get("value"), f"{name} sample {index} value")
        result.append({"point_m": _point(sample.get("point_m"), f"{name} sample {index} point_m"), "value": value, "region": str(sample.get("region", "air"))})
    return result


def import_case_result(case_dir: str | Path) -> Dict[str, Any]:
    root, case = _load_case(case_dir)
    path = (root / str(case.get("result_path", ""))).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_RESULT_BYTES:
        raise OpenFoamAdapterError("OpenFOAM normalized result is missing, symbolic, outside the case, or over its import limit.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpenFoamAdapterError("OpenFOAM normalized result is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict) or payload.get("contract") != RESULT_CONTRACT or payload.get("adapter_contract") != ADAPTER_CONTRACT:
        raise OpenFoamAdapterError("OpenFOAM normalized result has an unsupported contract.")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("scenario_digest") != case["scenario"]["digest"] or provenance.get("case_file_digest") != _digest(case["files"]):
        raise OpenFoamAdapterError("OpenFOAM normalized result provenance does not match the prepared case.")
    if payload.get("status") not in {"completed", "failed_to_converge"} or payload.get("model_status") != "experimental":
        raise OpenFoamAdapterError("OpenFOAM result must have a supported status and remain labelled experimental.")
    summary = payload.get("summary", {})
    issues = payload.get("issues", [])
    if not isinstance(summary, dict) or not isinstance(issues, list) or not all(isinstance(item, dict) for item in issues):
        raise OpenFoamAdapterError("OpenFOAM normalized result summary and issues must be structured objects.")
    return {
        "contract": "spike/thermal-result/v1", "status": payload["status"], "model_status": "experimental",
        "scenario_id": str(case["scenario"]["id"]), "summary": dict(summary),
        "fields": {"temperature_k": _field(payload, "temperature_k", "K"), "velocity_m_s": _field(payload, "velocity_m_s", "m/s", vector=True), "pressure_pa": _field(payload, "pressure_pa", "Pa")},
        "issues": list(issues) + [{"code": "OPENFOAM_EXPERIMENTAL_NOT_VALIDATED", "severity": "warning", "message": "OpenFOAM output has strict provenance but no external validation fixture."}],
        "provenance": {**provenance, "engine_id": "external.openfoam", "adapter_contract": ADAPTER_CONTRACT, "adapter_version": ADAPTER_VERSION, "case_contract": CASE_CONTRACT},
    }


def _bounded(value: int, label: str, minimum: int, maximum: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise OpenFoamAdapterError(f"{label} must be an integer.") from exc
    if not minimum <= numeric <= maximum:
        raise OpenFoamAdapterError(f"{label} must be between {minimum} and {maximum}.")
    return numeric


def _latest_time(root: Path) -> Path:
    candidates = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        try:
            candidates.append((float(path.name), path))
        except ValueError:
            continue
    if not candidates:
        raise OpenFoamAdapterError("OpenFOAM produced no numeric result time directory.")
    return max(candidates, key=lambda item: item[0])[1]


def _parse_internal_field(path: Path, *, vector: bool = False, expected_count: int | None = None) -> list[Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_RESULT_BYTES:
        raise OpenFoamAdapterError(f"OpenFOAM field {path.name} is missing or outside its import limit.")
    text = path.read_text(encoding="utf-8")
    match = (_VECTOR_LIST if vector else _SCALAR_LIST).search(text)
    if not match:
        uniform = (_VECTOR_UNIFORM if vector else _SCALAR_UNIFORM).search(text)
        if not uniform:
            raise OpenFoamAdapterError(f"OpenFOAM field {path.name} is not a supported ASCII internal field.")
        count = 1 if expected_count is None else expected_count
        if not 0 < count <= MAX_FIELD_SAMPLES:
            raise OpenFoamAdapterError(f"OpenFOAM field {path.name} sample count is outside its limit.")
        if vector:
            value = [_number(float(token), path.name) for token in uniform.group(1).split()]
            if len(value) != 3:
                raise OpenFoamAdapterError(f"OpenFOAM vector field {path.name} contains a malformed uniform value.")
        else:
            value = _number(float(uniform.group(1)), path.name)
        return [value[:] if vector else value for _ in range(count)]
    count = int(match.group(1))
    if not 0 < count <= MAX_FIELD_SAMPLES:
        raise OpenFoamAdapterError(f"OpenFOAM field {path.name} sample count is outside its limit.")
    if vector:
        values = [[_number(float(token), path.name) for token in item.split()] for item in _VECTOR_VALUE.findall(match.group(2))]
        if any(len(value) != 3 for value in values):
            raise OpenFoamAdapterError(f"OpenFOAM vector field {path.name} contains malformed values.")
    else:
        values = [_number(float(token), path.name) for token in match.group(2).split()]
    if len(values) != count:
        raise OpenFoamAdapterError(f"OpenFOAM field {path.name} declared {count} values but contained {len(values)}.")
    return values


def _write_normalized_result(root: Path, case: Dict[str, Any], runtime: Dict[str, Any], solver_stdout: str) -> Dict[str, Any]:
    latest = _latest_time(root)
    centres = _parse_internal_field(latest / "C", vector=True)
    temperature = _parse_internal_field(latest / "T", expected_count=len(centres))
    velocity = _parse_internal_field(latest / "U", vector=True, expected_count=len(centres))
    pressure_kinematic = _parse_internal_field(latest / "p_rgh", expected_count=len(centres))
    if not (len(centres) == len(temperature) == len(velocity) == len(pressure_kinematic)):
        raise OpenFoamAdapterError("OpenFOAM field arrays do not share a common cell count.")
    solver_reported_convergence = "solution converged" in solver_stdout.lower()
    residual_matches = re.findall(r"Solving for\s+([^,]+),\s+Initial residual =\s+([^,]+),\s+Final residual =\s+([^,]+)", solver_stdout)
    final_residuals: Dict[str, float] = {}
    for field_name, _initial, final in residual_matches:
        final_residuals[field_name.strip()] = _number(float(final), f"final residual {field_name}")
    rho_air = 1.225
    samples = list(zip(centres, temperature, velocity, pressure_kinematic))
    source_power_w = sum(_number(item.get("power_w", 0), "case source power_w") for item in case.get("sources", []))
    max_velocity_m_s = max(math.sqrt(sum(component * component for component in value)) for value in velocity)
    scenario_path = root / "spike_scenario.json"
    try:
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        ambient_k = _number(scenario.get("ambient_temperature_c"), "ambient_temperature_c") + 273.15
        residual_target = _number(scenario.get("run", {}).get("residual_target", 1e-6), "run.residual_target", positive=True)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, OpenFoamAdapterError) as exc:
        raise OpenFoamAdapterError("The verified OpenFOAM scenario cannot be used for result qualification.") from exc
    zero_load_equilibrium = (
        abs(source_power_w) <= 1e-12
        and max(abs(value - ambient_k) for value in temperature) <= 1e-8
        and max_velocity_m_s <= 1e-10
    )
    converged = solver_reported_convergence or zero_load_equilibrium
    convergence_criterion = "solver_residual_control" if solver_reported_convergence else ("zero_load_field_equilibrium" if zero_load_equilibrium else "iteration_ceiling")
    payload = {
        "contract": RESULT_CONTRACT,
        "adapter_contract": ADAPTER_CONTRACT,
        "status": "completed" if converged else "failed_to_converge",
        "model_status": "experimental",
        "summary": {
            "cell_count": len(samples),
            "min_temperature_k": min(temperature),
            "max_temperature_k": max(temperature),
            "mean_temperature_k": sum(temperature) / len(temperature),
            "max_velocity_m_s": max_velocity_m_s,
            "converged": converged,
            "convergence_criterion": convergence_criterion,
            "final_residuals": final_residuals,
            "residual_target": residual_target,
            "result_time": latest.name,
        },
        "issues": [] if converged else [{"code": "OPENFOAM_FAILED_TO_CONVERGE", "severity": "error", "message": "OpenFOAM reached its iteration ceiling without satisfying residual control."}],
        "provenance": {
            "scenario_digest": case["scenario"]["digest"],
            "case_file_digest": _digest(case["files"]),
            "runtime": str(runtime.get("version") or runtime.get("executable") or "openfoam"),
            "result_time": latest.name,
        },
        "fields": {
            "temperature_k": {"unit": "K", "samples": [{"point_m": point, "value": value, "region": "air"} for point, value, _u, _p in samples]},
            "velocity_m_s": {"unit": "m/s", "samples": [{"point_m": point, "value": value, "region": "air"} for point, _t, value, _p in samples]},
            "pressure_pa": {"unit": "Pa", "samples": [{"point_m": point, "value": value * rho_air, "region": "air"} for point, _t, _u, value in samples]},
        },
    }
    target = root / str(case["result_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return payload


def run_case(case_dir: str | Path, *, timeout_s: int = 3600, memory_limit_mb: int = 4096, output_limit_bytes: int = 8 * 1024**3, cancellation_event: threading.Event | None = None, allow_experimental: bool = False) -> Dict[str, Any]:
    root, case = _load_case(case_dir)
    capabilities = openfoam_capabilities()
    if not allow_experimental:
        return {"status": "blocked", "message": "OpenFOAM execution requires explicit allow_experimental=true.", "case_dir": str(root), "capabilities": capabilities}
    if not capabilities["execution_ready"]:
        return {"status": "solver_unavailable", "message": "A native Linux or fixed-argv WSL OpenFOAM runtime with blockMesh, topoSet, and buoyantBoussinesqSimpleFoam is required.", "case_dir": str(root), "capabilities": capabilities}
    timeout = _bounded(timeout_s, "timeout_s", 10, 604800)
    memory = _bounded(memory_limit_mb, "memory_limit_mb", 512, 1_048_576)
    output_limit = _bounded(output_limit_bytes, "output_limit_bytes", 1_048_576, 64 * 1024**3)
    started = time.monotonic()
    execution = []
    solver_stdout = ""
    runtime = detect_openfoam_runtime()
    try:
        for name in _REQUIRED_COMMANDS[:-1]:
            command = _execution_command(runtime, name, root)
            process = run_adapter_process(command, cwd=root, timeout_s=timeout, memory_limit_mb=memory, output_limit_bytes=output_limit, stream_limit_bytes=8 * 1024**2, cancellation_event=cancellation_event)
            execution.append({"command": name, "argv": command, "return_code": process["return_code"], "stdout": process["stdout"][-4000:], "stderr": process["stderr"][-4000:]})
            if process["return_code"] != 0:
                return {"status": "failed", "message": f"OpenFOAM command {name} failed.", "case_dir": str(root), "duration_s": time.monotonic() - started, "execution": execution}
            if name == "topoSet" and re.search(r"cellSet\s+\S+\s+now\s+size\s+0\b", process["stdout"], re.IGNORECASE):
                return {
                    "status": "failed",
                    "message": "OpenFOAM produced an empty heat-source cell set; refine the mesh or move the source inside the domain.",
                    "case_dir": str(root),
                    "duration_s": time.monotonic() - started,
                    "execution": execution,
                }
            if name == "buoyantBoussinesqSimpleFoam":
                solver_stdout = process["stdout"]
        command = _execution_command(runtime, "postProcess", root, ["-func", "writeCellCentres", "-latestTime"])
        process = run_adapter_process(command, cwd=root, timeout_s=timeout, memory_limit_mb=memory, output_limit_bytes=output_limit, stream_limit_bytes=8 * 1024**2, cancellation_event=cancellation_event)
        execution.append({"command": "postProcess", "argv": command, "return_code": process["return_code"], "stdout": process["stdout"][-4000:], "stderr": process["stderr"][-4000:]})
        if process["return_code"] != 0:
            return {"status": "failed", "message": "OpenFOAM cell-centre export failed.", "case_dir": str(root), "duration_s": time.monotonic() - started, "execution": execution}
        _write_normalized_result(root, case, runtime, solver_stdout)
    except (OSError, SparseLizardAdapterError, OpenFoamAdapterError) as exc:
        return {"status": "failed", "message": f"OpenFOAM process execution failed: {exc}", "case_dir": str(root), "duration_s": time.monotonic() - started, "execution": execution}
    try:
        result = import_case_result(root)
    except OpenFoamAdapterError as exc:
        return {"status": "failed", "message": f"OpenFOAM did not produce a strict normalized SPIKE result: {exc}", "case_dir": str(root), "duration_s": time.monotonic() - started, "execution": execution}
    return {"status": result["status"], "model_status": "experimental", "case_dir": str(root), "duration_s": time.monotonic() - started, "execution": execution, "result": result, "provenance": {"case_digest": _digest(case["files"]), "runtime": capabilities["executable"], "runtime_version": capabilities["version"]}}


__all__ = ["ADAPTER_CONTRACT", "CASE_CONTRACT", "RESULT_CONTRACT", "OpenFoamAdapterError", "import_case_result", "openfoam_capabilities", "prepare_case", "run_case"]
