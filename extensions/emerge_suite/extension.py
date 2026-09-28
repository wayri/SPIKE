# SPDX-License-Identifier: Apache-2.0
"""Bridge imported SPIKE boards to the optional EMerge FEM runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from extension_sdk.python.spike_extension_sdk import (
    analysis_envelope, analysis_result, read_request, write_result,
)
from extensions.emerge_suite.board_adapter import compile_board
from extensions.emerge_suite.normalize import network, radiation


CONTRIBUTIONS = {"emerge-radiation": "emi", "emerge-si": "si"}
MAX_ENGINE_BYTES = 8 * 1024 * 1024


def _probe_executable(executable: Path) -> dict:
    if not executable.is_file():
        return {"available": False, "reason": "Python executable does not exist.", "capabilities": []}
    try:
        process = subprocess.run(
            [str(executable), "-I", "-c", "import emerge; print(emerge.__version__)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as error:
        return {"available": False, "reason": str(error), "capabilities": []}
    if process.returncode:
        return {"available": False,
                "reason": process.stderr[-1000:].decode("utf-8", errors="replace"),
                "capabilities": []}
    version_lines = process.stdout.decode("utf-8", errors="replace").splitlines()
    version = version_lines[-1].strip() if version_lines else ""
    if not version:
        return {"available": False, "reason": "EMerge did not report its version.",
                "capabilities": []}
    if not (version.startswith("2.8.") or version == "3.0.0a19"):
        return {"available": False, "version": version,
                "reason": "This adapter supports EMerge 2.8.x and the tested 3.0.0a19 alpha; review other versions before use.",
                "capabilities": []}
    return {"available": True, "version": version,
            "python_executable": str(executable),
            "capabilities": ["si_s_parameters", "radiation_pattern"]}


def probe_engine(python_executable: str | None) -> dict:
    if python_executable:
        return _probe_executable(Path(python_executable).expanduser().resolve())
    project = Path(__file__).resolve().parents[2]
    candidates = [project / ".venv-emerge3" / "Scripts" / "python.exe",
                  Path(sys.executable),
                  project / ".venv-emerge" / "Scripts" / "python.exe"]
    last = None
    for candidate in candidates:
        last = _probe_executable(candidate)
        if last["available"]:
            return last
    return last or {"available": False, "reason": "No EMerge Python interpreter found.", "capabilities": []}


def run_engine(case: dict, *, radiation_requested: bool, python_executable: str | None) -> dict:
    readiness = probe_engine(python_executable)
    if not readiness["available"]:
        raise RuntimeError("EMerge runtime is unavailable: " + readiness["reason"])
    executable = Path(readiness["python_executable"])
    with tempfile.TemporaryDirectory(prefix="spike-emerge-") as directory:
        root = Path(directory)
        case_path, result_path = root / "case.json", root / "result.json"
        case_path.write_text(json.dumps(case, allow_nan=False, separators=(",", ":")), encoding="utf-8")
        command = [str(executable), "-I", "-X", "utf8", str(Path(__file__).with_name("runner.py")),
                   "--case", str(case_path), "--result", str(result_path)]
        if radiation_requested:
            command.append("--radiation")
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
        return json.loads(result_path.read_text(encoding="utf-8"),
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


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
    if contribution not in CONTRIBUTIONS:
        raise ValueError("Unsupported EMerge contribution.")
    context = request.get("context")
    if not isinstance(context, dict) or not isinstance(context.get("design"), dict):
        raise ValueError("Import a board before running EMerge.")
    parameters = context.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Set up EMerge nets, port pads, frequency, and mesh in SPIKE.")
    case = compile_board(context["design"], parameters)
    engine = backend or run_engine
    raw = engine(case, radiation_requested=contribution == "emerge-radiation",
                 python_executable=parameters.get("python_executable"))
    if not isinstance(raw, dict) or not isinstance(raw.get("engine_version"), str) or not raw["engine_version"]:
        raise ValueError("EMerge returned no versioned result.")
    network_data, network_summary = network(raw.get("s_parameters"))
    frequencies = network_data["frequencies_hz"]
    if (len(frequencies) != case["frequency_points"]
            or not math.isclose(frequencies[0], case["frequency_start_hz"], rel_tol=1e-6)
            or not math.isclose(frequencies[-1], case["frequency_stop_hz"], rel_tol=1e-6)
            or network_data["ports"] != [f"P{index}" for index in range(1, len(case["ports"]) + 1)]
            or not math.isclose(network_data["reference_impedance_ohm"], 50.0, rel_tol=1e-12)):
        raise ValueError("EMerge returned a sweep or port set that does not match the board case.")
    networks = {"s_parameters": network_data}
    fields: dict = {}
    summary = {"engine": "EMerge", "engine_version": raw["engine_version"],
               "s_parameters": network_summary, "modeled_nets": case["modeled_nets"],
               "geometry_status": case["geometry_status"],
               "surrounding_geometry": case.get("surrounding_geometry", [])}
    if contribution == "emerge-radiation":
        field_data, field_summary = radiation(raw.get("radiation"))
        if field_data["frequencies_hz"] != frequencies:
            raise ValueError("EMerge far-field frequencies do not match the solved port sweep.")
        fields["radiation"] = field_data
        summary["radiation"] = field_summary
    case_bytes = json.dumps(case, sort_keys=True, separators=(",", ":"),
                            allow_nan=False).encode("utf-8")
    issues = [{"code": "EMERGE_BOARD_MODEL_UNVALIDATED", "severity": "warning",
               "message": "Surface PEC copper, rectangular board bounds, selected nets and a finite absorbing region need mesh convergence and physical correlation."}]
    if case["loss_tangent_omitted"]:
        issues.append({"code": "EMERGE_DIELECTRIC_LOSS_OMITTED", "severity": "warning",
                       "message": "Imported dielectric loss tangent was not represented; insertion loss is incomplete."})
    if case.get("shorting_vias"):
        issues.append({"code": "EMERGE_SOLID_PEC_SHORTING_VIAS", "severity": "warning",
                       "message": "Explicit return-net shorting vias use solid PEC cylinders; barrels, drills and antipads are not resolved."})
    if case.get("attributed_graphic_polygon_ids"):
        issues.append({"code": "EMERGE_ATTRIBUTED_UNNETTED_COPPER", "severity": "warning",
                       "message": "Selected source copper graphics had no net assignment; their antenna-net attribution is a documented model assumption."})
    if case.get("idealized_reference_plane_ids"):
        issues.append({"code": "EMERGE_IDEALIZED_REFERENCE_PLANE", "severity": "warning",
                       "message": "The reference plane is an idealized rectangle over source ground extents; source voids and detailed return paths are omitted."})
    if case.get("fragment_copper") is False:
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
                    "case_contract": case["contract"],
                    "geometry_status": case["geometry_status"],
                    "surrounding_geometry": case.get("surrounding_geometry", []),
                    "modeled_nets": case["modeled_nets"],
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
