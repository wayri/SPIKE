# SPDX-License-Identifier: Apache-2.0
"""Process extension for one-way EMerge-driven Optycal structure studies."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from extension_sdk.python.spike_extension_sdk import analysis_envelope, analysis_result, read_request, write_result
from extensions.emerge_suite.normalize import radiation
from extensions.optycal_suite.study import prepare_case, generate_script
from extensions.engine_runtime import existing_engine_interpreter


def probe_engine(python_executable=None):
    root = Path(__file__).resolve().parents[2]
    executable = existing_engine_interpreter("optycal", root, python_executable)
    if not executable.is_file():
        return {"available": False, "reason": "Selected Optycal Python executable is missing.", "capabilities": []}
    # Disable import-time compilation only for discovery. Actual simulations
    # use Optycal's normal execution; signatures are checked without source reads.
    code = ("import os; os.environ['NUMBA_DISABLE_JIT']='1'; import optycal,gmsh,json; "
            "from importlib.metadata import version; "
            "print(json.dumps({'version':version('optycal'),'gmsh_version':version('gmsh')}))")
    try:
        process = subprocess.run([str(executable), "-I", "-c", code], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode:
            raise ValueError(process.stderr[-2000:].decode("utf-8", errors="replace"))
        metadata = json.loads(process.stdout.decode("utf-8").splitlines()[-1])
        if metadata["version"] != "0.2.0":
            raise ValueError("Only the reviewed Optycal 0.2.0 public API is supported.")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return {"available": False, "reason": str(error), "capabilities": []}
    return {"available": True, **metadata, "python_executable": str(executable),
            "capabilities": ["emerge_complex_angular_source", "step_pec_surface", "one_way_physical_optics", "coherent_interference", "script_preview"],
            "model_status": "unvalidated", "source_model": "explicitly assumed far-zone coefficient", "engine_license": "MIT"}


def run_engine(case, *, python_executable=None, expected_script_sha256=None):
    runtime = probe_engine(python_executable)
    if not runtime["available"]:
        raise RuntimeError("Optycal runtime unavailable: " + runtime["reason"])
    generated = generate_script(case)
    if expected_script_sha256 is not None and generated["script_sha256"] != expected_script_sha256:
        raise ValueError("Optycal source or structure changed since the displayed preview.")
    with tempfile.TemporaryDirectory(prefix="spike-optycal-") as directory:
        root = Path(directory)
        script, result, log = root/"study.py", root/"result.json", root/"engine.log"
        script.write_bytes(generated["script"].encode("utf-8"))
        try:
            with log.open("wb") as output:
                process = subprocess.run([runtime["python_executable"], "-I", "-X", "utf8", str(script), "--result", str(result)],
                    cwd=root, stdout=output, stderr=subprocess.STDOUT, timeout=1800,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Optycal study exceeded its 1800-second bound.") from error
        if process.returncode:
            with log.open("rb") as output:
                size = output.seek(0, 2)
                output.seek(max(0, size-4000))
                diagnostic = output.read().decode("utf-8", errors="replace")
            raise RuntimeError("Optycal study failed: " + diagnostic)
        if not result.is_file() or result.stat().st_size > 8*1024*1024:
            raise ValueError("Optycal returned no bounded result.")
        raw = json.loads(result.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    raw["generated_script_sha256"] = generated["script_sha256"]
    return raw


def _validate_comparison(raw, case):
    import numpy as np
    if not isinstance(raw, dict) or raw.get("contract") != "spike/optycal-pattern-comparison/v1" or raw.get("frequency_hz") != case["frequency_hz"]:
        raise ValueError("Optycal comparison does not match the selected source frequency.")
    theta = list(range(0, 181, case["theta_step_deg"]))
    phi = list(range(0, 361, case["phi_step_deg"]))
    size = len(theta)*len(phi)
    if raw.get("theta_deg") != theta or raw.get("phi_deg") != phi:
        raise ValueError("Optycal comparison angular grids do not match setup.")
    for key in ("bare_relative_db", "structure_relative_db", "delta_db", "interference_cross_term"):
        values = raw.get(key)
        if not isinstance(values, list) or len(values) != size or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError("Optycal comparison scalar samples are malformed.")
    for key in ("direct_e_xyz", "scattered_e_xyz", "total_e_xyz"):
        values = raw.get(key)
        if not isinstance(values, list) or len(values) != size:
            raise ValueError("Optycal comparison field samples are malformed.")
        for row in values:
            if not isinstance(row, list) or len(row) != 3 or any(not isinstance(p, list) or len(p) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in p) for p in row):
                raise ValueError("Optycal comparison needs three finite complex field components.")
    for direct, scattered, total in zip(raw["direct_e_xyz"], raw["scattered_e_xyz"], raw["total_e_xyz"]):
        if any(not math.isclose(d+s, t, abs_tol=1e-12, rel_tol=1e-10) for dv, sv, tv in zip(direct, scattered, total) for d, s, t in zip(dv, sv, tv)):
            raise ValueError("Optycal total field is not the coherent direct plus scattered field.")
    field = {}
    for key in ("direct_e_xyz", "scattered_e_xyz", "total_e_xyz"):
        pairs = np.asarray(raw[key], dtype=float)
        field[key] = pairs[:, :, 0]+1j*pairs[:, :, 1]
    direct, scattered, total = (field[key] for key in ("direct_e_xyz", "scattered_e_xyz", "total_e_xyz"))
    peak = float(np.max(np.sum(abs(direct)**2, axis=1)))
    if not math.isfinite(peak) or peak <= 0:
        raise ValueError("Optycal direct source has no finite nonzero reference peak.")
    db = lambda power: np.maximum(-300., 10*np.log10(np.maximum(power/peak, 1e-30)))
    bare_db, total_db = db(np.sum(abs(direct)**2, axis=1)), db(np.sum(abs(total)**2, axis=1))
    calculated = {"bare_relative_db": bare_db, "structure_relative_db": total_db,
                  "delta_db": total_db-bare_db, "interference_cross_term": 2*np.real(np.sum(direct*np.conj(scattered), axis=1))/peak}
    for key, expected in calculated.items():
        if not np.allclose(raw[key], expected, atol=1e-9, rtol=1e-9):
            raise ValueError(f"Optycal {key} does not match its complex field samples.")
    return raw


def execute(request, *, backend=None, mesher=None):
    contribution = request.get("contribution_id")
    parameters = request.get("context", {}).get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("Optycal parameters must be an object.")
    if contribution == "optycal-probe":
        return {"contract": "spike/extension-result/v1", "status": "completed", "title": "Optycal runtime", "data": probe_engine(parameters.get("python_executable"))}
    if contribution not in ("optycal-preview", "optycal-radiation"):
        raise ValueError("Unknown Optycal contribution.")
    binding = request.get("context", {}).get("design_binding")
    case = prepare_case(parameters, binding, mesher=mesher)
    generated = generate_script(case)
    if contribution == "optycal-preview":
        return {"contract": "spike/extension-result/v1", "status": "completed", "title": "Optycal study preview",
                "data": {**generated, "solved": False, "model_status": "unvalidated", "setup": {k: v for k, v in case.items() if k not in ("source_pattern", "structure_mesh")},
                         "structure_source_sha256": case["structure_mesh"]["source_sha256"]}}
    expected = parameters.get("expected_generated_script_sha256")
    if expected is not None and expected != generated["script_sha256"]:
        raise ValueError("Optycal inputs changed after script preview; prepare the current study again.")
    raw = (backend or run_engine)(case, python_executable=parameters.get("python_executable"), expected_script_sha256=expected)
    if raw.get("engine_version") != "0.2.0":
        raise ValueError("Optycal result has an unsupported engine version.")
    normalized, summary = radiation(raw.get("radiation"))
    comparison = _validate_comparison(raw.get("comparison"), case)
    if normalized["frequencies_hz"] != [case["frequency_hz"]] or len(normalized["patterns_3d"]) != 1:
        raise ValueError("Optycal radiation does not match the selected source.")
    _validate_projection(normalized, comparison)
    normalized["field_units"] = "arbitrary coherent units; no absolute V/m calibration"
    issues = [{"code": "OPTYCAL_ONE_WAY_PO_UNVALIDATED", "severity": "warning", "message": "One-way PEC physical optics is unvalidated: no antenna loading/S11 feedback, edge diffraction, multiple scattering or geometric shadowing."},
              {"code": "OPTYCAL_FARZONE_SOURCE_ASSUMPTION", "severity": "warning", "message": "EMerge complex angular samples are explicitly assumed to be outgoing far-zone coefficients with e^(+j omega t), phase origin at the placed antenna origin. No absolute voltage, power, gain or compliance calibration is claimed."}]
    mesh = case["structure_mesh"]
    setup = {k: v for k, v in case.items() if k not in ("source_pattern", "structure_mesh")}
    result = analysis_result(request, analysis_id=f"optycal-{request.get('request_id', 'run')}", mode="emi", model_status="unvalidated", solver="Optycal/0.2.0",
        summary={"engine": "Optycal", "engine_version": "0.2.0", "setup": setup, "radiation": summary,
                 "illuminated_triangle_count": raw.get("illuminated_triangle_count"),
                 "structure": {k: v for k, v in mesh.items() if k not in ("vertices_mm", "triangles")}},
        fields={"radiation": normalized, "comparison": comparison, "structure_mesh": mesh}, issues=issues,
        provenance={"source_analysis_id": case["source_analysis_id"], "source_result_sha256": case["source_sha256"],
                    "structure_source_sha256": mesh["source_sha256"], "generated_script_sha256": raw.get("generated_script_sha256", generated["script_sha256"]),
                    "case_sha256": generated["case_sha256"], "source_phase_assumption": case["source_phase_assumption"], "qualification": "not independently validated"})
    return analysis_envelope(result, title="Optycal structure radiation and coherent interference")


def _validate_projection(radiation_data, comparison):
    """Bind the existing spherical visualization to the coherent XYZ samples."""
    import numpy as np
    pattern = radiation_data["patterns_3d"][0]
    if pattern["theta_deg"] != comparison["theta_deg"] or pattern["phi_deg"] != comparison["phi_deg"]:
        raise ValueError("Optycal radiation and comparison grids differ.")
    t = np.deg2rad(np.repeat(comparison["theta_deg"], len(comparison["phi_deg"])))
    p = np.deg2rad(np.tile(comparison["phi_deg"], len(comparison["theta_deg"])))
    pairs = np.asarray(comparison["total_e_xyz"], dtype=float)
    xyz = pairs[:, :, 0]+1j*pairs[:, :, 1]
    expected = {"e_theta_v_m": np.sum(xyz*np.stack((np.cos(t)*np.cos(p), np.cos(t)*np.sin(p), -np.sin(t)), axis=1), axis=1),
                "e_phi_v_m": np.sum(xyz*np.stack((-np.sin(p), np.cos(p), np.zeros_like(p)), axis=1), axis=1)}
    for key, values in expected.items():
        actual = np.asarray(pattern[key], dtype=float)
        if not np.allclose(actual[:, 0]+1j*actual[:, 1], values, atol=1e-12, rtol=1e-9):
            raise ValueError("Optycal spherical field does not match its total Cartesian field.")
    cut = radiation_data["cuts"][0]
    if len(radiation_data["cuts"]) != 1 or cut["angles_deg"] != comparison["theta_deg"] or cut["phi_deg"] != 0:
        raise ValueError("Optycal cut grid does not match its comparison.")
    for key in expected:
        actual = np.asarray(cut[key], dtype=float)
        wanted = expected[key][::len(comparison["phi_deg"])]
        if not np.allclose(actual[:, 0]+1j*actual[:, 1], wanted, atol=1e-12, rtol=1e-9):
            raise ValueError("Optycal cut does not match its spherical samples.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    write_result(args.result, execute(read_request(args.request)))


if __name__ == "__main__":
    main()
