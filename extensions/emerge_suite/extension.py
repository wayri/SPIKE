# SPDX-License-Identifier: Apache-2.0
"""Bridge imported SPIKE boards to the optional EMerge FEM runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extension_sdk.python.spike_extension_sdk import (
    analysis_envelope, analysis_result, read_request, write_result,
)
from extensions.emerge_suite.board_adapter import compile_board
from extensions.emerge_suite.gerber_case import compile_gerber
from extensions.emerge_suite.gerber_source import (
    import_gerber_design, snapshot_from_source,
)
from extensions.emerge_suite.normalize import network, radiation, nearfield
from extensions.emerge_suite.script_builder import generate_script
from extensions.emerge_suite.capability_inventory import capability_inventory
from extensions.emerge_suite.mesh_extension import execute_mesh
from extensions.engine_runtime import engine_interpreter_candidates


CONTRIBUTIONS = {"emerge-radiation": "emi", "emerge-si": "si"}
MAX_ENGINE_BYTES = 8 * 1024 * 1024
_MINIMUM_MAJOR_VERSION = 3
_EXECUTED_FIXTURE_VERSIONS = frozenset({"3.0.0a19", "3.0.0a20"})
_REQUIRED_API = ("pcb_layer_polygons", "pcb_geometry", "microwave_sweep",
                 "microwave_boundaries", "mesh_generation", "mesh_sizing")
_PROBE_SCRIPT = """
import emerge as em
import importlib.util
import inspect
import json
from importlib.metadata import version

model = em.Simulation('SPIKE_runtime_probe')
geo = getattr(em, 'geo', None)
pcb = getattr(geo, 'PCBNew', None)
poly = getattr(pcb, 'add_poly', None)
try:
    layer_argument = 'layer' in inspect.signature(poly).parameters
except (TypeError, ValueError):
    layer_argument = False
mesh = getattr(model, 'mesh', None)
mw = getattr(model, 'mw', None)
bc = getattr(mw, 'bc', None)
mesher = getattr(model, 'mesher', None)
checks = {
    'pcb_layer_polygons': callable(poly) and layer_argument,
    'pcb_geometry': all(callable(getattr(pcb, name, None)) for name in
                        ('compile_paths', 'set_bounds', 'generate_pcb')) and
                    all(callable(getattr(geo, name, None)) for name in
                        ('Plate', 'Box', 'open_region')) and
                    callable(getattr(em, 'Material', None)) and
                    hasattr(getattr(em, 'lib', None), 'PEC'),
    'microwave_sweep': all(callable(getattr(mw, name, None)) for name in
                           ('set_frequency_range', 'run_sweep')),
    'microwave_boundaries': all(callable(getattr(bc, name, None)) for name in
                                ('LumpedPort', 'AbsorbingBoundary')) and
                            hasattr(em, 'ZAX'),
    'mesh_generation': callable(getattr(model, 'commit_geometry', None)) and
                       callable(getattr(model, 'generate_mesh', None)),
    'mesh_sizing': all(callable(getattr(mesher, name, None)) for name in
                       ('set_boundary_size', 'set_face_size')),
    'mesh_export': all(hasattr(mesh, name) for name in
                       ('nodes', 'tets', 'tris', 'vtag_to_tet', 'ftag_to_tri')),
}
gerber_reason = ''
try:
    from emerge.beta.gerber import FileBasedPCB
    loader = getattr(FileBasedPCB, 'layer_from_file', None)
    loader_parameters = inspect.signature(loader).parameters
    constructor_parameters = inspect.signature(FileBasedPCB).parameters
    gerber_dependency = importlib.util.find_spec('pygerber') is not None
    checks['gerber_loader'] = (callable(loader) and gerber_dependency and
        all(name in loader_parameters for name in ('layer', 'filename', 'res_mm')) and
        all(name in constructor_parameters for name in ('thickness', 'unit', 'layers', 'zs')))
    if not gerber_dependency:
        gerber_reason = 'Install emerge[gerber] in the selected solver Python environment.'
    elif not checks['gerber_loader']:
        gerber_reason = 'The selected EMerge runtime does not expose the required FileBasedPCB API.'
except (ImportError, ModuleNotFoundError, TypeError, ValueError) as error:
    checks['gerber_loader'] = False
    gerber_reason = ('Native Gerber loading is unavailable; install emerge[gerber] in the '
                     'selected solver Python environment: ' + str(error))
present = importlib.util.find_spec('emcad') is not None
print(json.dumps({'version': str(em.__version__), 'emcad_version':
                  version('emcad') if present else None, 'api_checks': checks,
                  'gerber_reason': gerber_reason}))
"""


def _major_version(version: str) -> int | None:
    """Accept PEP 440 style release prefixes, including 3.x prereleases."""
    match = re.match(r"^([0-9]+)\.[0-9]+\.[0-9]+(?:$|[abrc.+-])", version)
    return int(match.group(1)) if match else None


def _probe_executable(executable: Path) -> dict:
    if not executable.is_file():
        return {"available": False, "reason": "Python executable does not exist.", "capabilities": []}
    try:
        process = subprocess.run(
            [str(executable), "-I", "-X", "utf8", "-c", _PROBE_SCRIPT],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "reason": str(error), "capabilities": []}
    if process.returncode:
        return {"available": False,
                "reason": process.stderr[-1000:].decode("utf-8", errors="replace"),
                "capabilities": []}
    version_lines = process.stdout.decode("utf-8", errors="replace").splitlines()
    try:
        metadata = json.loads(version_lines[-1]) if version_lines else {}
        if not isinstance(metadata, dict):
            raise ValueError("Runtime metadata must be an object.")
    except (ValueError, TypeError) as error:
        return {"available": False, "reason": f"EMerge runtime metadata is malformed: {error}", "capabilities": []}
    version = metadata.get("version", "")
    if not isinstance(version, str) or not version:
        return {"available": False, "reason": "EMerge did not report its version.",
                "capabilities": []}
    major = _major_version(version)
    if major is None or major < _MINIMUM_MAJOR_VERSION:
        return {"available": False, "version": version,
                "reason": "This adapter requires EMerge major version 3 or newer; select an EMerge 3+ interpreter.",
                "capabilities": []}
    checks = metadata.get("api_checks")
    if not isinstance(checks, dict) or any(not isinstance(value, bool) for value in checks.values()):
        return {"available": False, "version": version,
                "reason": "EMerge did not report valid runtime API checks.", "capabilities": []}
    missing = [name for name in _REQUIRED_API if checks.get(name) is not True]
    if missing:
        return {"available": False, "version": version, "api_checks": checks,
                "missing_api": missing,
                "reason": "EMerge runtime lacks required PCB/FEM APIs: " + ", ".join(missing),
                "capabilities": []}
    mesh_export = checks.get("mesh_export") is True
    gerber_available = major == 3 and checks.get("gerber_loader") is True
    gerber_reason = str(metadata.get("gerber_reason") or "")
    if major > 3:
        gerber_reason = "Native Gerber loading is fail-closed for unqualified EMerge major versions newer than 3."
    elif not gerber_available and not gerber_reason:
        gerber_reason = "Install emerge[gerber] in the selected solver Python environment."
    return {"available": True, "version": version,
            "adapter_evidence": "executed_fixture" if version in _EXECUTED_FIXTURE_VERSIONS else "api_detected",
            "api_checks": checks,
            "emcad_available": bool(metadata.get("emcad_version")),
            "emcad_version": metadata.get("emcad_version"),
            "geometry_backends": ["emerge"] + (["emcad"] if metadata.get("emcad_version") else []),
            "max_copper_layers": 16,
            "feature_inventory": capability_inventory(),
            "python_executable": str(executable),
            "mesh_export_api": mesh_export,
            "gerber_available": gerber_available,
            "gerber_reason": "" if gerber_available else gerber_reason,
            "capabilities": ["si_s_parameters", "radiation_pattern"] +
                            (["pcb_tetrahedral_mesh"] if mesh_export else []) +
                            (["native_gerber_geometry"] if gerber_available else [])}


def probe_engine(python_executable: str | None) -> dict:
    project = Path(__file__).resolve().parents[2]
    candidates = engine_interpreter_candidates("emerge", project, python_executable)
    last = None
    for candidate in candidates:
        last = _probe_executable(candidate)
        if last["available"]:
            return last
    return last or {"available": False, "reason": "No EMerge Python interpreter found.", "capabilities": []}


def run_engine(case: dict, *, radiation_requested: bool, python_executable: str | None,
               expected_script_sha256: str | None = None, mesh_only: bool = False) -> dict:
    readiness = probe_engine(python_executable)
    if not readiness["available"]:
        raise RuntimeError("EMerge runtime is unavailable: " + readiness["reason"])
    if mesh_only and not readiness.get("mesh_export_api"):
        raise RuntimeError("The selected EMerge runtime does not expose the required mesh-generation/export API.")
    if case.get("source_format") == "emerge-gerber" and not readiness.get("gerber_available"):
        raise RuntimeError("The selected EMerge runtime cannot load native Gerber: " +
                           readiness.get("gerber_reason", "install emerge[gerber] in that solver Python environment."))
    executable = Path(readiness["python_executable"])
    with tempfile.TemporaryDirectory(prefix="spike-emerge-") as directory:
        root = Path(directory)
        script_path, result_path = root / "simulation.py", root / "result.json"
        script = generate_script(case, radiation_requested=radiation_requested, mesh_only=mesh_only)
        if expected_script_sha256 is not None and expected_script_sha256 != script["script_sha256"]:
            raise ValueError("The EMerge script changed after preview. Prepare the current GUI model again before running.")
        script_path.write_bytes(script["script"].encode("utf-8"))
        command = [str(executable), "-I", "-X", "utf8", str(script_path),
                   "--result", str(result_path)]
        try:
            with (root / "emerge.log").open("wb") as log:
                process = subprocess.run(command, cwd=root, stdout=log,
                                         stderr=subprocess.STDOUT, timeout=3300, shell=False,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("EMerge timed out after 3300 seconds.") from error
        if process.returncode:
            with (root / "emerge.log").open("rb") as log:
                size = log.seek(0, 2)
                log.seek(max(0, size - 4000))
                diagnostic = log.read().decode("utf-8", errors="replace")
            raise RuntimeError("EMerge solve failed: " + diagnostic)
        if not result_path.is_file() or result_path.stat().st_size > MAX_ENGINE_BYTES:
            raise RuntimeError("EMerge returned no bounded result file.")
        result = json.loads(result_path.read_text(encoding="utf-8"),
                            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        result["generated_script_sha256"] = script["script_sha256"]
        return result


def execute(request: dict, *, backend=None, probe=None) -> dict:
    if request.get("contract") != "spike/extension/v1":
        raise ValueError("Unsupported extension request contract.")
    contribution = request.get("contribution_id")
    if contribution == "emerge-probe":
        context = request.get("context")
        parameters = context.get("parameters", {}) if isinstance(context, dict) else {}
        if not isinstance(parameters, dict):
            raise ValueError("EMerge probe parameters must be an object.")
        data = (probe or probe_engine)(parameters.get("python_executable"))
        return {"contract": "spike/extension-result/v1",
                "status": "completed" if data["available"] else "completed_with_warnings",
                "title": "EMerge runtime readiness", "data": data}
    if contribution == "emerge-gerber-import":
        context = request.get("context")
        parameters = context.get("parameters") if isinstance(context, dict) else None
        if not isinstance(parameters, dict) or not isinstance(parameters.get("source"), dict):
            raise ValueError("EMerge Gerber import requires parameters.source.")
        snapshot = snapshot_from_source(parameters["source"])
        readiness = None
        executable = parameters.get("python_executable")
        if executable is not None:
            if not isinstance(executable, str) or not executable.strip():
                raise ValueError("python_executable must be a non-empty string when supplied.")
            readiness = (probe or probe_engine)(executable)
        warnings = [item for item in snapshot["design"].get("issues", [])
                    if item.get("severity") == "warning"]
        data = {"snapshot": snapshot,
                "setup": {"geometry_source": "gerber", "signal_net": "GerberRF",
                          "return_net": "GerberReturn",
                          "field_excited_port": 1},
                "report": snapshot["report"], "warnings": warnings}
        if readiness is not None:
            data["runtime"] = readiness
        return {"contract": "spike/extension-result/v1", "status": "completed_with_warnings",
                "title": "Imported native EMerge Gerber source", "data": data}
    if contribution == "emerge-gerber-design":
        context = request.get("context")
        source = context.get("source") if isinstance(context, dict) else None
        if not isinstance(source, dict) or not isinstance(source.get("path"), str):
            raise ValueError("EMerge Gerber file import requires a workspace source path.")
        if source.get("options") not in (None, {}):
            raise ValueError("EMerge Gerber file import does not accept options.")
        design = import_gerber_design(source["path"])
        return {"contract": "spike/extension-result/v1", "status": "completed_with_warnings",
                "title": "Imported native EMerge Gerber package", "data": {"design": design.to_dict()}}
    if contribution not in {*CONTRIBUTIONS, "emerge-preview", "emerge-mesh", "emerge-mesh-preview"}:
        raise ValueError("Unsupported EMerge contribution.")
    context = request.get("context")
    if not isinstance(context, dict) or not isinstance(context.get("design"), dict):
        raise ValueError("Import a board before running EMerge.")
    parameters = context.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Set up EMerge nets, port pads, frequency, and mesh in SPIKE.")
    design = context["design"]
    if design.get("source_format") == "emerge-gerber":
        case = compile_gerber(design, parameters)
    else:
        if parameters.get("geometry_source") == "gerber":
            raise ValueError("geometry_source gerber does not match the imported board design.")
        case = compile_board(design, parameters)
    if contribution in {"emerge-mesh", "emerge-mesh-preview"}:
        return execute_mesh(request, case, backend=backend or run_engine)
    if contribution == "emerge-preview":
        radiation_requested = parameters.get("preview_radiation", True)
        if not isinstance(radiation_requested, bool):
            raise ValueError("preview_radiation must be a boolean.")
        generated = generate_script(case, radiation_requested=radiation_requested)
        return {"contract": "spike/extension-result/v1", "status": "completed",
                "title": "Prepared EMerge GUI model (not solved)",
                "data": {"case": case, **generated, "capabilities": capability_inventory(),
                         "solved": False, "model_status": "unvalidated"}}
    expected_script = parameters.get("expected_generated_script_sha256")
    if expected_script is not None:
        if not isinstance(expected_script, str) or len(expected_script) != 64:
            raise ValueError("Expected generated-script digest must be a SHA-256 string.")
        current_script = generate_script(case, radiation_requested=contribution == "emerge-radiation")
        if current_script["script_sha256"] != expected_script:
            raise ValueError("The EMerge script does not match the displayed preview. Prepare the current GUI model again.")
    engine_kwargs = {"radiation_requested": contribution == "emerge-radiation",
                     "python_executable": parameters.get("python_executable")}
    if backend is None:
        engine_kwargs["expected_script_sha256"] = expected_script
    raw = (backend or run_engine)(case, **engine_kwargs)
    if not isinstance(raw, dict) or not isinstance(raw.get("engine_version"), str) or not raw["engine_version"]:
        raise ValueError("EMerge returned no versioned result.")
    network_data, network_summary = network(raw.get("s_parameters"))
    frequencies = network_data["frequencies_hz"]
    if (len(frequencies) != case["frequency_points"]
            or not math.isclose(frequencies[0], case["frequency_start_hz"], rel_tol=1e-6)
            or not math.isclose(frequencies[-1], case["frequency_stop_hz"], rel_tol=1e-6)
            or network_data["ports"] != [f"P{index}" for index in range(1, len(case["ports"]) + 1)]
            or not math.isclose(network_data["reference_impedance_ohm"], case["ports"][0]["reference_impedance_ohm"], rel_tol=1e-12)):
        raise ValueError("EMerge returned a sweep or port set that does not match the board case.")
    networks = {"s_parameters": network_data}
    fields: dict = {}
    summary = {"engine": "EMerge", "engine_version": raw["engine_version"],
               "s_parameters": network_summary, "modeled_nets": case["modeled_nets"],
               "port_mapping": case["port_mapping"],
               "geometry_status": case["geometry_status"],
               "copper_layers": case["copper_layers"],
               "dielectric_layers": case["dielectric_layers"],
               "geometry_backend": case["geometry_backend"],
               "geometry_backend_version": raw.get("geometry_backend_version"),
               "copper_polygon_count": raw.get("copper_polygon_count", len(case["polygons"])),
               "native_gerber_layer_count": raw.get("native_gerber_layer_count"),
               "setup": {key: case[key] for key in ("frequency_start_hz", "frequency_stop_hz", "frequency_points", "mesh_resolution_mm", "planar_cell_estimate", "layered_cell_estimate", "ports", "include_dielectric_loss", "reference_impedance_ohm", "air_margin_mm", "parallel", "n_workers", "sparse_solver", "radiation_theta_step_deg", "radiation_phi_step_deg", "radiation_cut_phi_deg", "nearfield_enabled", "nearfield_z_mm", "nearfield_grid_points", "field_excited_port")},
               "surrounding_geometry": case.get("surrounding_geometry", [])}
    if contribution == "emerge-radiation":
        field_data, field_summary = radiation(raw.get("radiation"))
        if field_data["frequencies_hz"] != frequencies:
            raise ValueError("EMerge far-field frequencies do not match the solved port sweep.")
        fields["radiation"] = field_data
        summary["radiation"] = field_summary
    if case.get("nearfield_enabled"):
        field_data, field_summary = nearfield(raw.get("nearfield"))
        if field_data["frequencies_hz"] != frequencies:
            raise ValueError("EMerge near-field frequencies do not match the solved port sweep.")
        n = case["nearfield_grid_points"]
        xmin, ymin, xmax, ymax = case["bounds_mm"]
        for plane in field_data["planes"]:
            if plane["grid_shape"] != [n, n]:
                raise ValueError("EMerge near-field grid does not match the requested case.")
            for index, point in enumerate(plane["coordinates_mm"]):
                expected = [xmin+(xmax-xmin)*(index % n)/(n-1),
                            ymin+(ymax-ymin)*(index // n)/(n-1), case["nearfield_z_mm"]]
                if any(not math.isclose(a, b, abs_tol=1e-9, rel_tol=1e-9) for a, b in zip(point, expected)):
                    raise ValueError("EMerge near-field coordinates do not match the requested plane.")
        fields["nearfield"] = field_data
        summary["nearfield"] = field_summary
    for name in ("radiation", "nearfield"):
        if name not in fields:
            continue
        field = fields[name]
        if field.get("excitation_ports") is not None:
            if (field["excitation_ports"] != network_data["ports"]
                    or field["excitation_port"] != network_data["ports"][case["field_excited_port"]-1]):
                raise ValueError("EMerge field excitation does not match the requested port.")
        elif raw.get("generated_script_sha256"):
            raise ValueError("The generated EMerge model returned no field excitation metadata.")
    case_bytes = json.dumps(case, sort_keys=True, separators=(",", ":"),
                            allow_nan=False).encode("utf-8")
    generated = generate_script(case, radiation_requested=contribution == "emerge-radiation")
    if case.get("source_format") == "emerge-gerber":
        issues = [
            {"code": "EMERGE_GERBER_MODEL_UNVALIDATED", "severity": "warning",
             "message": "Native Gerber surface PEC geometry, declared rectangular bounds and the finite absorbing region need mesh convergence and physical correlation."},
            {"code": "EMERGE_GERBER_MANUAL_PORTS", "severity": "warning",
             "message": "Gerber has no source pads or nets; port coordinates, adjacent-layer returns and GerberRF/GerberReturn labels are manual unverified annotations."},
        ]
    else:
        issues = [{"code": "EMERGE_BOARD_MODEL_UNVALIDATED", "severity": "warning",
                   "message": "Surface PEC copper, rectangular board bounds, selected nets and a finite absorbing region need mesh convergence and physical correlation."}]
    if case["loss_tangent_omitted"]:
        issues.append({"code": "EMERGE_DIELECTRIC_LOSS_OMITTED", "severity": "warning",
                       "message": "Imported dielectric loss tangent was not represented; insertion loss is incomplete."})
    if case.get("include_dielectric_loss"):
        issues.append({"code": "EMERGE_CONSTANT_DIELECTRIC_LOSS", "severity": "warning",
                       "message": "Imported constant loss tangent is enabled; frequency-dependent material loss and finite copper conductivity remain unmodeled."})
    if case.get("nearfield_enabled"):
        issues.append({"code": "EMERGE_SAMPLED_NEARFIELD", "severity": "warning",
                       "message": "E/H vectors are interpolated from the solved FEM field at an explicit XY grid. Invalid points remain null; this plane does not describe a full spatial field."})
    if case.get("shorting_vias"):
        issues.append({"code": "EMERGE_SOLID_PEC_SHORTING_VIAS", "severity": "warning",
                       "message": "Explicit return-net shorting vias use solid PEC cylinders; barrels, drills and antipads are not resolved."})
    if case.get("attributed_graphic_polygon_ids"):
        issues.append({"code": "EMERGE_ATTRIBUTED_UNNETTED_COPPER", "severity": "warning",
                       "message": "Selected source copper graphics had no net assignment; their antenna-net attribution is a documented model assumption."})
    if case.get("idealized_reference_plane_ids"):
        issues.append({"code": "EMERGE_IDEALIZED_REFERENCE_PLANE", "severity": "warning",
                       "message": "The reference plane is an idealized rectangle over source ground extents; source voids and detailed return paths are omitted."})
    if case.get("fragment_copper") is False and case.get("source_format") != "emerge-gerber":
        issues.append({"code": "EMERGE_COPPER_FRAGMENTATION_DISABLED", "severity": "warning",
                       "message": "Overlapping same-net copper polygons were sent without planar fragmentation; inspect the resulting mesh for seams or duplicates."})
    if contribution == "emerge-radiation":
        issues.append({"code": "EMERGE_EMI_NOT_COMPLIANCE", "severity": "warning",
                       "message": "Relative far-field pattern is not a calibrated EMI compliance prediction."})
    if case.get("surrounding_geometry"):
        issues.append({"code": "EMERGE_SURROUNDINGS_UNVALIDATED", "severity": "warning",
                       "message": "Dielectric surroundings are explicit ideal boxes without measured dispersion or loss; compare with a bare case and refine the mesh and air domain."})
    result = analysis_result(
        request, analysis_id=f"emerge-{request.get('request_id', 'run')}",
        mode=CONTRIBUTIONS[contribution], model_status="unvalidated",
        solver=f"EMerge/{raw['engine_version']}", summary=summary,
        fields=fields, networks=networks, issues=issues,
        provenance={"board_case_sha256": hashlib.sha256(case_bytes).hexdigest(),
                    "generated_script_sha256": raw.get("generated_script_sha256", generated["script_sha256"]),
                    "case_contract": case["contract"],
                    "geometry_status": case["geometry_status"],
                    "copper_layers": case["copper_layers"],
                    "dielectric_layers": case["dielectric_layers"],
                    "geometry_backend": case["geometry_backend"],
                    "geometry_backend_version": raw.get("geometry_backend_version"),
                    "surrounding_geometry": case.get("surrounding_geometry", []),
                    "modeled_nets": case["modeled_nets"],
                    "port_mapping": case["port_mapping"],
                    "native_gerber_source_sha256": case.get("native_gerber_source_sha256"),
                    "source_assumptions": case.get("source_assumptions", []),
                    "material_assignment_source": case.get("material_assignment_source"),
                    "air_margin_m": raw.get("air_margin_m"),
                    "qualification": "not independently validated"},
    )
    return analysis_envelope(result, title="EMerge " +
                             ("radiation pattern" if contribution == "emerge-radiation" else "SI port sweep"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    write_result(args.result, execute(read_request(args.request)))


if __name__ == "__main__":
    main()
