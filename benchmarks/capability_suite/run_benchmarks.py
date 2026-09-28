# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Permanent local capability benchmark runner; no release promotion."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import traceback
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
import scipy
from python.spike_core.benchmarks import run_solver_benchmarks
from python.spike_core.native_mna import run_native_mna
from python.spike_core.si_channel import uniform_rlgc_network
from python.spike_core.structured_solid_thermal import solve_structured_solid_thermal
from python.spike_core.structured_electrothermal import solve_structured_electrothermal

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def si_matched_line():
    errors = []
    for z0 in (25., 50., 100.):
        for length in (.001, .1, 1.):
            velocity = 2e8
            f = np.linspace(0., 1e10, 101)
            network = uniform_rlgc_network({"geometry": {"length_m": length}, "rlgc_per_m": {
                "resistance_ohm_per_m": 0., "inductance_h_per_m": z0 / velocity,
                "capacitance_f_per_m": 1 / (z0 * velocity), "loss_tangent": 0.}}, f, z0)
            s = network.parameters
            exact = np.exp(-2j * np.pi * f * length / velocity)
            errors.extend([float(np.max(abs(s[:, 1, 0] - exact))), float(np.max(abs(s[:, 0, 0]))),
                           float(np.max(abs(s[:, 0, 1] - s[:, 1, 0])))])
    require(max(errors) < 1e-12, errors)
    return {"reference": "matched lossless line: S21=exp(-j*omega*l/v), S11=0, S12=S21",
            "parameter_combinations": 9, "frequency_points_each": 101,
            "maximum_absolute_error": max(errors), "tolerance": 1e-12}

def rc_broadband():
    errors = []
    for resistance, capacitance in ((10., 1e-12), (50., 1e-9), (1000., 1e-6)):
        fc = 1 / (2 * math.pi * resistance * capacitance)
        for ratio in (.001, .01, .1, 1., 10., 100., 1000.):
            request = {"contract": "spike/native-mna-request/v1", "request_id": "benchmark",
                       "ground_node": "0", "analysis": {"mode": "ac", "start_hz": fc * ratio,
                       "stop_hz": fc * ratio, "points": 1, "scale": "log"}, "elements": [
                {"id": "V", "type": "voltage_source", "positive_node": "in", "negative_node": "0", "ac_magnitude": 1.},
                {"id": "R", "type": "resistor", "positive_node": "in", "negative_node": "out", "resistance_ohm": resistance},
                {"id": "C", "type": "capacitor", "positive_node": "out", "negative_node": "0", "capacitance_f": capacitance}]}
            result = run_native_mna(request)
            require(result["status"] == "completed", result)
            value = result["data"]["node_voltage_v"]["out"]
            actual = value["magnitude"][0] * np.exp(1j * np.deg2rad(value["phase_deg"][0]))
            exact = 1 / (1 + 1j * ratio)
            errors.append(float(abs(actual - exact) / abs(exact)))
    require(max(errors) < 1e-12, errors)
    return {"reference": "RC transfer H(jw)=1/(1+jwRC), complex magnitude and phase",
            "cases": len(errors), "maximum_relative_error": max(errors), "tolerance": 1e-12}

def thermal_mms():
    errors, balance = [], []
    for n in (3, 6, 12, 24):
        coordinate = (np.arange(n) + .5) / n
        z, y, x = np.meshgrid(coordinate, coordinate, coordinate, indexing="ij")
        mode = np.sin(np.pi*x)*np.sin(np.pi*y)*np.sin(np.pi*z)
        request = {"contract": "spike/structured-solid-thermal-request/v1",
            "grid": {"shape": [n]*3, "spacing_m": 1/n}, "materials": [
                {"id": "solid", "thermal_conductivity_w_mk": [1., 2., 3.]}],
            "material_ids": ["solid"]*n**3, "heat_generation_w_m3": (6*np.pi**2*mode).ravel().tolist(),
            "boundaries": {axis+side: {"type": "temperature", "temperature_k": 300.}
                           for axis in "xyz" for side in ("_min", "_max")}, "study": {"type": "steady"}}
        result = solve_structured_solid_thermal(request)
        require(result["status"] == "completed", result.get("issues"))
        errors.append(float(np.linalg.norm(np.asarray(result["temperature_k"])-(300+mode).ravel())/n**1.5))
        balance.append(result["energy"]["relative_residual"])
    slopes = [math.log2(a/b) for a,b in zip(errors, errors[1:])]
    require(min(slopes) > 1.95 and max(balance) < 1e-8, (slopes, balance))
    return {"reference": "T=300+sin(pi*x)sin(pi*y)sin(pi*z); K=diag(1,2,3); q=6*pi^2*(T-300)",
            "cells_per_axis": [3,6,12,24], "rms_errors_k": errors, "l2_slopes": slopes,
            "minimum_slope": 1.95, "energy_relative_residuals": balance, "energy_tolerance": 1e-8}

def electrothermal():
    request = json.loads((ROOT/"examples/thermal/structured_electrothermal_request.json").read_text())
    errors, balances = [], []
    for voltage in (1., 6., 12., 24.):
        request["circuit"]["elements"][0]["dc_value"] = voltage
        result = solve_structured_electrothermal(request)
        require(result["status"] == "completed", result.get("issues"))
        a = 3 * voltage**2 / 4
        rise = 2*a/(1+math.sqrt(1+4*.004*a))
        errors.append(abs(result["temperature_k"][0] - (300+rise)))
        balances.append(abs(result["coupled_power_residual_w"]))
    require(max(errors) < 1e-6 and max(balances) < 1e-7, (errors, balances))
    return {"reference": "rise*(1+alpha*rise)=Rtheta*V^2/R0; Rtheta=3,R0=4,alpha=.004",
            "voltages_v": [1,6,12,24], "temperature_errors_k": errors,
            "power_residuals_w": balances, "temperature_tolerance_k": 1e-6, "power_tolerance_w": 1e-7}

def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item

def channel_cht_probe():
    from tests.python.test_laminar_channel_cht import fixture
    from python.spike_core.laminar_channel_cht import solve_laminar_channel_cht
    result=solve_laminar_channel_cht(fixture(nf=16,nx=32))
    require(result["status"]=="completed",result)
    exact=.02*.1*.01**3/(12*1.8e-5)
    error=abs(result["flow_m3_s"]-exact)/exact
    require(error<.005 and abs(result["energy"]["residual_w"])<1e-8,result)
    return {"reference":"Plane Poiseuille volumetric flow plus finite-volume thermal energy conservation",
            "relative_flow_error":error,"flow_tolerance":.005,"energy":result["energy"],
            "scope":"Fully developed laminar channel; not enclosure airflow qualification"}

def huygens_probe():
    from tests.python.test_huygens_far_field import dipole_request,K,ETA
    from python.spike_core.huygens_far_field import huygens_far_field
    result=huygens_far_field(**dipole_request(24))
    exact=np.array([0.,0.,-1j*K*ETA/(4*np.pi)])
    error=float(np.linalg.norm(result["electric_amplitude_v"][0]-exact)/np.linalg.norm(exact))
    require(error<.001,error)
    return {"reference":"Closed-box Hertzian dipole complex far amplitude",
            "relative_complex_amplitude_error":error,"tolerance":.001,
            "surface_samples":result["surface_samples"],"scope":"Postprocessor, not fullwave solver"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-build", type=Path)
    args = parser.parse_args()
    output = ROOT / "build" / "capability-benchmarks" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S.%fZ")
    output.mkdir(parents=True)
    modules = {
        "numerical_and_operation": ["native_mna", "peec_multiport", "transient_peec", "si_channel", "si_workflow",
            "sparameters", "structured_solid_thermal", "structured_electrothermal", "transient_diode_field", "thermal_validation", "electrothermal_sharing", "laminar_channel_cht", "huygens_far_field", "enclosure_stokes",
            "local_mesh_controls", "tetra_mesh_refinement", "tetra_mesh_optimization", "mom_surface_basis"],
        "adapter_or_recorded_evidence_not_field_solves": ["openems_benchmarks", "openems_far_field", "openems_far_field_normalization", "openems_geometry_admission", "openems_pad_geometry", "pcb_entity_ports", "emi_workflow", "thermal_field_job", "thermal_qualification"]}
    paths = sorted(set((ROOT/"python/spike_core").rglob("*.py")) | set((ROOT/"examples/thermal").glob("*.json")) | {
        ROOT/f"tests/python/test_{name}.py" for group in modules.values() for name in group})
    before = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    report = {"contract": "spike/local-capability-benchmarks/v1", "created_utc": datetime.now(timezone.utc).isoformat(),
        "production_qualified": False, "runner_sha256": sha(Path(__file__)), "machine": {"platform": platform.platform(), "machine": platform.machine(),
        "processor": platform.processor(), "cpu_count": os.cpu_count(), "python": sys.version,
        "numpy": np.__version__, "scipy": scipy.__version__}, "source_sha256": before,
        "method": "One warm-up and five sequential measured runs per numerical probe/native executable; no performance acceptance baseline. Unit tests run once.",
        "probes": [], "unit_groups": [], "native_tests": [],
        "coverage": {
            "SI": "Matched-line complex transfer; cascades, terminations, transforms, TDR/TDT, waveform and bounded eye component tests",
            "basic_RF_multiport": "RC complex frequency response plus native network, port and waveguide component verification",
            "EMI_EMC": "Native Maxwell, impedance, PML, modal scattering and Hcurl component tests; not an EMC compliance measurement",
            "PI_AC_broadband": "PEEC/shared-reference matrices, loaded PDN, RC/RL/MNA and extraction reference corpus",
            "PI_transient": "MNA RC response and geometry-PEEC transient operation tests",
            "thermal": "3D anisotropic manufactured solution, contacts, radiation surface law, backward-Euler convergence",
            "electrothermal": "Steady resistor-network/thermal-field fixed point and adjoint loss transfer; no general transient coupling",
            "magnetostatics": "Available native planar/axisymmetric, force, inductance and nonlinear component tests",
            "geometry": "Available native topology, predicates, meshing, layout and volume compiler component tests",
            "general_multiphysics": "Not qualified: bounded field/circuit orchestration tests only"},
        "unqualified": ["Independent-solver and measured-hardware correlation not acquired by this run",
            "Linux/MPI and clean-machine/private-CI qualification not exercised",
            "Full CFD/conjugate heat transfer, arbitrary-geometry electrothermal and general multiphysics not covered",
            "Prebuilt native executable tests are bounded component evidence, not a fresh rebuild or end-to-end EMC compliance qualification"]}
    for name, function in [("si_lossless_matched_line", si_matched_line), ("pi_rf_rc_broadband", rc_broadband),
                           ("thermal_3d_anisotropic_mms", thermal_mms), ("electrothermal_dc_fixed_point", electrothermal),
                           ("existing_extraction_pi_corpus", run_solver_benchmarks),
                           ("laminar_channel_cht",channel_cht_probe),("huygens_far_field",huygens_probe)]:
        row = {"name": name, "status": "failed", "samples_s": []}
        try:
            for index in range(6):
                start = time.perf_counter()
                metrics = function()
                elapsed = time.perf_counter()-start
                if metrics.get("status") == "failed" or metrics.get("summary", {}).get("skipped", 0):
                    raise AssertionError(metrics)
                if index:
                    row["samples_s"].append(elapsed)
                row["metrics"] = metrics
            row.update(status="passed", median_s=statistics.median(row["samples_s"]))
        except Exception:
            row["error"] = traceback.format_exc()
        report["probes"].append(row)
        print(name, row["status"], flush=True)
    seen = set()
    for group, names in modules.items():
        suite = unittest.TestSuite()
        for name in names:
            for case in flatten(unittest.defaultTestLoader.loadTestsFromName("tests.python.test_"+name)):
                if case.id() not in seen:
                    seen.add(case.id()); suite.addTest(case)
        stream = io.StringIO()
        start = time.perf_counter()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        (output/(group+".log")).write_text(stream.getvalue(), encoding="utf-8")
        row = {"name": group, "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "status": "passed" if result.wasSuccessful() and not result.skipped else "incomplete",
               "elapsed_s": time.perf_counter()-start}
        report["unit_groups"].append(row)
        print(group, row, flush=True)
    if args.native_build:
        metadata = [args.native_build/name for name in ("CMakeCache.txt", "build.ninja", "compile_commands.json")]
        metadata += sorted(args.native_build.glob("*.dll"))
        report["native_build_file_sha256"] = {str(p): sha(p) for p in metadata if p.is_file()}
        binaries = sorted(args.native_build.glob("*math_vnv_tests.exe"))
        if not binaries:
            report["unqualified"].append("No native mathematical verification executables found")
        for exe in binaries:
            row = {"name": exe.name, "path": str(exe), "sha256": sha(exe), "status": "failed", "samples_s": []}
            try:
                for index in range(6):
                    start = time.perf_counter()
                    run = subprocess.run([str(exe)], cwd=output, capture_output=True, text=True, timeout=30)
                    elapsed = time.perf_counter()-start
                    require(run.returncode == 0, f"exit={run.returncode}\n{run.stdout}\n{run.stderr}")
                    if index:
                        row["samples_s"].append(elapsed)
                require(sha(exe) == row["sha256"], "Executable changed during run")
                row.update(status="passed", median_s=statistics.median(row["samples_s"]), stdout=run.stdout, stderr=run.stderr)
            except Exception:
                row["error"] = traceback.format_exc()
            report["native_tests"].append(row)
            print(exe.name, row["status"], flush=True)
    else:
        report["unqualified"].append("Native Maxwell/EMI mathematical test executables not requested")
    report["source_unchanged_during_run"] = before == {str(p.relative_to(ROOT)): sha(p) for p in paths}
    report["runner_unchanged_during_run"] = report["runner_sha256"] == sha(Path(__file__))
    report["native_build_unchanged_during_run"] = all(sha(Path(p)) == digest for p, digest in report.get("native_build_file_sha256", {}).items())
    rows = report["probes"]+report["unit_groups"]+report["native_tests"]
    stable = all(report[key] for key in ("source_unchanged_during_run", "runner_unchanged_during_run", "native_build_unchanged_during_run"))
    report["executed_checks_status"] = "passed" if all(r["status"] == "passed" for r in rows) and stable else "failed_or_incomplete"
    report["qualification_status"] = "incomplete"
    target = output/"report.json"
    target.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    manifest = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    (output/"SHA256.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print("REPORT", target, flush=True)
    return 0 if report["executed_checks_status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
