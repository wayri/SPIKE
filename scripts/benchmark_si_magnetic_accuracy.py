# SPDX-License-Identifier: Apache-2.0
"""Generate bounded SI and planar magnetic-thermal accuracy evidence.

The analytical oracles in this file were independently derived from the
stated governing equations. No third-party implementation or example data is
used. Results remain experimental and are not product qualification evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from python.spike_core.magnetic_fem import MU0, solve_magnetostatic
from python.spike_core.magnetic_thermal import simulate_magnetic_thermal
from python.spike_core.si_channel import time_domain_report, uniform_rlgc_network
from python.spike_core.si_workflow import _loaded_response


def timed(callable_):
    start = time.perf_counter()
    value = callable_()
    return value, time.perf_counter() - start


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def grid(n: int):
    nodes = [[i / n, j / n] for j in range(n + 1) for i in range(n + 1)]
    triangles = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            triangles.extend([[a, a + 1, a + n + 2], [a, a + n + 2, a + n + 1]])
    return nodes, triangles


def si_evidence():
    length = 0.37
    inductance = 250e-9
    capacitance = 100e-12
    delay = length * math.sqrt(inductance * capacitance)
    frequencies = np.linspace(0.0, 5.0e9, 2049)
    extraction = {
        "geometry": {"design_id": "analytic-lossless-line", "length_m": length},
        "geometry_digest": "0" * 64,
        "rlgc_per_m": {
            "resistance_ohm_per_m": 0.0,
            "inductance_h_per_m": inductance,
            "capacitance_f_per_m": capacitance,
            "loss_tangent": 0.0,
        },
    }
    network, solve_s = timed(lambda: uniform_rlgc_network(extraction, frequencies, 50.0))
    s = network.s_parameters()
    expected_s21 = np.exp(-2j * np.pi * frequencies * delay)
    complex_error = np.abs(s[:, 1, 0] - expected_s21)

    # A 1 A Norton source in parallel with 50 ohm has a 50 V Thevenin voltage.
    # With 50 ohm source/load and a matched line, Vload/Vthevenin = exp(-jwt)/2.
    y = np.full((len(frequencies), 2), 1 / 50.0, dtype=complex)
    drive = np.zeros((len(frequencies), 2, 1), dtype=complex)
    drive[:, 0, 0] = 1.0
    transfer, loaded_s = timed(
        lambda: _loaded_response(network, y, drive, 25.0, np.zeros_like(y.real))[0]
    )
    expected_loaded_v = 25.0 * expected_s21
    loaded_error = np.abs(transfer[:, 1, 0] - expected_loaded_v)

    tdr, tdr_s = timed(lambda: time_domain_report(network))
    tdr_impedance = np.asarray([row["impedance_ohm"] for row in tdr["tdr"]], dtype=float)
    return {
        "status": "pass" if max(complex_error.max(), loaded_error.max()) < 1e-10 else "fail",
        "case": "lossless 50 ohm uniform line, matched source and load",
        "settings": {"length_m": length, "L_h_per_m": inductance, "C_f_per_m": capacitance,
                     "frequency_points": len(frequencies), "frequency_stop_hz": frequencies[-1]},
        "oracle": {"delay_s": delay, "s21": "exp(-j*2*pi*f*delay)",
                   "loaded_v_per_1a_norton_v": "25*exp(-j*2*pi*f*delay)"},
        "metrics": {
            "maximum_complex_s21_absolute_error": float(complex_error.max()),
            "maximum_s11_magnitude": float(np.abs(s[:, 0, 0]).max()),
            "maximum_s21_magnitude_error": float(np.abs(np.abs(s[:, 1, 0]) - 1).max()),
            "maximum_loaded_voltage_absolute_error_v": float(loaded_error.max()),
            "maximum_tdr_impedance_error_ohm": float(np.max(np.abs(tdr_impedance - 50.0))),
        },
        "gates": {"maximum_complex_s21_absolute_error": 1e-10,
                  "maximum_loaded_voltage_absolute_error_v": 1e-10},
        "timing_s": {"network": solve_s, "loaded_response": loaded_s, "time_domain": tdr_s},
    }


def magnetostatic_request(n: int):
    nodes, triangles = grid(n)
    boundary = [i for i, (x, y) in enumerate(nodes) if x in (0.0, 1.0) or y in (0.0, 1.0)]
    exact = [x * (1 - x) + y * (1 - y) for x, y in nodes]
    return {
        "nodes_m": nodes, "triangles": triangles, "region_ids": ["solid"] * len(triangles),
        "materials": {"solid": {"mu_r": 1 / MU0}}, "stack_depth_m": 0.3,
        "dirichlet_a_wb_per_m": {i: exact[i] for i in boundary},
        "current_density_a_per_m2": {"solid": 4.0},
    }, np.asarray(exact)


def magnetostatic_evidence():
    rows = []
    for n in (4, 8, 16):
        request, exact_a = magnetostatic_request(n)
        result, elapsed = timed(lambda: solve_magnetostatic(**request))
        energy_error = abs(result["magnetic_energy_j"] - 0.1)
        rows.append({
            "n": n, "nodes": len(request["nodes_m"]), "triangles": len(request["triangles"]),
            "maximum_nodal_potential_error_wb_per_m": float(np.max(np.abs(np.asarray(result["potential_a_wb_per_m"]) - exact_a))),
            "magnetic_energy_j": result["magnetic_energy_j"],
            "magnetic_energy_absolute_error_j": energy_error,
            "elapsed_s": elapsed,
        })
    ratios = [rows[i]["magnetic_energy_absolute_error_j"] / rows[i + 1]["magnetic_energy_absolute_error_j"]
              for i in range(len(rows) - 1)]
    return {
        "status": "pass" if rows[-1]["maximum_nodal_potential_error_wb_per_m"] < 1e-10
                 and min(ratios) > 3.9 else "fail",
        "case": "manufactured Poisson Az field on a unit square with permeability 1 H/m",
        "oracle": {"potential_a_wb_per_m": "x(1-x)+y(1-y)",
                   "current_density_a_per_m2": 4.0, "exact_magnetic_energy_j": 0.1},
        "refinement": rows, "energy_error_ratios": ratios,
        "gates": {"maximum_finest_nodal_potential_error_wb_per_m": 1e-10,
                  "minimum_energy_error_ratio": 3.9},
    }


def coupled_request(steps: int, duration_s: float = 0.02, *, winding_only: bool = False):
    nodes, triangles = grid(4)
    p = np.asarray(nodes)
    boundary = {i: 0.0 for i, (x, y) in enumerate(nodes) if x in (0.0, 1.0) or y in (0.0, 1.0)}
    initial_a = np.zeros(len(nodes)) if winding_only else np.sin(2 * np.pi * p[:, 0]) * np.sin(np.pi * p[:, 1])
    request = {
        "nodes_m": nodes, "triangles": triangles, "region_ids": ["solid"] * len(triangles),
        "magnetic_materials": {"solid": {"mu_r": 1 / MU0, "conductivity_s_m": 1.0}},
        "thermal_materials": {"solid": {"k_w_m_k": 2.0, "rho_kg_m3": 3.0, "cp_j_kg_k": 4.0}},
        "stack_depth_m": 0.3, "dirichlet_a_wb_per_m": boundary,
        "initial_a_wb_per_m": initial_a.tolist(), "initial_temperature_k": [300.0] * len(nodes),
        "time_step_s": duration_s / steps, "steps": steps, "snapshot_stride": steps,
        "conductivity_temperature_coefficients": {"solid": {"alpha_per_k": 0.1, "reference_temperature_k": 300.0}},
    }
    if winding_only:
        request["winding_element_loss_w"] = [3.6 / len(triangles)] * len(triangles)
    return request


def coupling_evidence(case_dir: Path):
    winding_request = coupled_request(3, 0.3, winding_only=True)
    winding_request["snapshot_stride"] = 1
    winding, winding_s = timed(lambda: simulate_magnetic_thermal(**winding_request))
    expected_temperature = [300.0 + 0.1 * i for i in range(4)]
    temperature_frames = [np.asarray(frame["temperature_k"], dtype=float) for frame in winding["history"]]
    actual_temperature = [float(frame[0]) for frame in temperature_frames]
    max_nodal_temperature_error = max(
        float(np.max(np.abs(frame - expected)))
        for frame, expected in zip(temperature_frames, expected_temperature)
    )
    expected_sigma = [1 / (1 + 0.1 * (expected_temperature[i] - 300.0)) for i in range(3)]
    actual_sigma = [row["conductivity_s_m"]["solid"] for row in winding["step_audits"]]
    write_json(case_dir / "winding-input.json", winding_request)
    write_json(case_dir / "winding-result.json", winding)

    runs = []
    vectors = []
    for steps in (4, 8, 16, 64):
        request = coupled_request(steps)
        result, elapsed = timed(lambda request=request: simulate_magnetic_thermal(**request))
        # Explicit reference scales make the mixed-field norm dimensionless.
        # It is a convergence indicator for this fixture, not a universal error metric.
        vector = np.r_[np.asarray(result["final_magnetic_result"]["potential_a_wb_per_m"]) / 1.0,
                       (np.asarray(result["final_thermal_result"]["temperature_k"]) - 300.0) / 1.0]
        vectors.append(vector)
        write_json(case_dir / f"coupling-{steps:03d}-steps-input.json", request)
        write_json(case_dir / f"coupling-{steps:03d}-steps-result.json", result)
        magnetic_residual = max(abs(row["magnetic"]["balance_residual_j"]) for row in result["step_audits"])
        thermal_residual = max(abs(row["thermal"]["balance_residual_j"]) for row in result["step_audits"])
        cumulative_joule = sum(row["eddy_joule_energy_j"] for row in result["step_audits"])
        capacity = np.asarray(result["final_thermal_result"]["nodal_heat_capacity_j_per_k"])
        stored = float(capacity @ (np.asarray(result["final_thermal_result"]["temperature_k"]) - 300.0))
        runs.append({"steps": steps, "time_step_s": 0.02 / steps, "elapsed_s": elapsed,
                     "maximum_magnetic_balance_residual_j": magnetic_residual,
                     "maximum_thermal_balance_residual_j": thermal_residual,
                     "cumulative_eddy_joule_energy_j": cumulative_joule,
                     "thermal_stored_energy_j": stored,
                     "joule_to_storage_absolute_error_j": abs(cumulative_joule - stored),
                     "final_conductivity_s_m": result["step_audits"][-1]["conductivity_s_m"]["solid"]})
    errors = [float(np.linalg.norm(value - vectors[-1])) for value in vectors[:-1]]
    ratios = [errors[i] / errors[i + 1] for i in range(len(errors) - 1)]
    max_winding_temperature_error = max_nodal_temperature_error
    max_sigma_error = max(abs(a - b) for a, b in zip(actual_sigma, expected_sigma))
    status = (max_winding_temperature_error < 1e-10 and max_sigma_error < 1e-12
              and min(ratios) > 1.7 and max(r["joule_to_storage_absolute_error_j"] for r in runs) < 1e-10)
    return {
        "status": "pass" if status else "fail",
        "winding_heat_closed_form": {
            "expected_temperature_k": expected_temperature, "observed_temperature_k": actual_temperature,
            "maximum_temperature_error_k": max_winding_temperature_error,
            "maximum_nodal_temperature_field_error_k": max_nodal_temperature_error,
            "observed_temperature_source": "history[*].temperature_k returned by simulate_magnetic_thermal",
            "expected_conductivity_s_m": expected_sigma, "observed_conductivity_s_m": actual_sigma,
            "maximum_conductivity_error_s_m": max_sigma_error, "elapsed_s": winding_s,
        },
        "eddy_thermal_refinement": runs,
        "fine_reference_vector_l2_errors": errors,
        "successive_error_ratios": ratios,
        "mixed_field_norm": {"potential_scale_wb_per_m": 1.0, "temperature_scale_k": 1.0,
                             "norm": "L2 of concatenated dimensionless scaled fields",
                             "scope": "fixture convergence indicator; not a universal accuracy metric"},
        "gates": {"maximum_closed_form_temperature_error_k": 1e-10,
                  "maximum_conductivity_error_s_m": 1e-12,
                  "minimum_successive_refinement_ratio": 1.7,
                  "maximum_joule_to_storage_absolute_error_j": 1e-10},
        "reference_note": "64-step same-model run is a refinement reference, not external truth.",
    }


def markdown(result):
    si = result["si"]
    mag = result["magnetostatic"]
    coupled = result["magnetic_thermal"]
    lines = [
        "# SI and stationary magnetic-thermal accuracy evidence", "",
        f"Overall status: **{result['status'].upper()}**.", "",
        "This evidence was generated from actual SPIKE solver calls. Analytical oracles are independently derived in the benchmark script. All evaluated solvers report experimental/non-production-qualified status.", "",
        "## SI", "",
        f"Status: **{si['status']}**. Lossless line delay = {si['oracle']['delay_s']:.12g} s; maximum complex S21 error = {si['metrics']['maximum_complex_s21_absolute_error']:.3e}; maximum matched-load voltage error = {si['metrics']['maximum_loaded_voltage_absolute_error_v']:.3e} V; maximum TDR impedance error = {si['metrics']['maximum_tdr_impedance_error_ohm']:.3e} ohm.", "",
        "## Stationary magnetic field", "",
        f"Status: **{mag['status']}**. Manufactured-solution magnetic-energy errors for 4/8/16 cells per axis: " + ", ".join(f"{row['magnetic_energy_absolute_error_j']:.3e} J" for row in mag["refinement"]) + f"; ratios: {', '.join(f'{v:.3f}' for v in mag['energy_error_ratios'])}.", "",
        "## Magnetic-thermal coupling", "",
        f"Status: **{coupled['status']}**. Closed-form maximum nodal temperature-field error = {coupled['winding_heat_closed_form']['maximum_nodal_temperature_field_error_k']:.3e} K; conductivity error = {coupled['winding_heat_closed_form']['maximum_conductivity_error_s_m']:.3e} S/m. Coupling refinement ratios against the 64-step run: {', '.join(f'{v:.3f}' for v in coupled['successive_error_ratios'])}.", "",
        "The coupling comparison uses a dimensionless L2 norm after scaling Az by 1 Wb/m and temperature rise by 1 K. It is a convergence indicator for this fixture, not a universal cross-physics accuracy measure.", "",
        "## Qualification boundary", "",
        "No external magnetics solver or measured magnetic/thermal dataset was available or invoked. The 64-step coupling result is only an internal refinement reference. These checks establish analytical consistency and convergence for bounded planar fixtures; they do not establish 3D end effects, hysteresis, motion, radiation, CFD, material measurement accuracy, protocol compliance, or production qualification.", "",
        "Reproduce from the repository root:", "",
        "```powershell", result["reproduction_command"], "```", "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("output/solver-comprehensive-20261012/si-magnetic-final"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "spike/si-magnetic-accuracy-evidence/v1",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__},
        "provenance": {"implementation": "SPIKE production Python solvers",
                       "oracle": "independently derived analytical formulas in this Apache-2.0 script",
                       "external_magnetics": "absent_not_run",
                       "source_sha256": {
                           "scripts/benchmark_si_magnetic_accuracy.py": sha256_file(Path(__file__)),
                           "python/spike_core/si_channel.py": sha256_file(REPOSITORY_ROOT / "python/spike_core/si_channel.py"),
                           "python/spike_core/si_workflow.py": sha256_file(REPOSITORY_ROOT / "python/spike_core/si_workflow.py"),
                           "python/spike_core/magnetic_fem.py": sha256_file(REPOSITORY_ROOT / "python/spike_core/magnetic_fem.py"),
                           "python/spike_core/magnetic_thermal.py": sha256_file(REPOSITORY_ROOT / "python/spike_core/magnetic_thermal.py"),
                       }},
        "reproduction_command": "build\\qualification-py311\\Scripts\\python.exe scripts\\benchmark_si_magnetic_accuracy.py",
    }
    result["si"] = si_evidence()
    result["magnetostatic"] = magnetostatic_evidence()
    case_dir = args.output_dir / "cases"
    result["magnetic_thermal"] = coupling_evidence(case_dir)
    result["status"] = "pass" if all(result[key]["status"] == "pass" for key in ("si", "magnetostatic", "magnetic_thermal")) else "fail"
    results_path = args.output_dir / "results.json"
    readme_path = args.output_dir / "README.md"
    write_json(results_path, result)
    readme_path.write_text(markdown(result), encoding="utf-8")
    artifact_paths = [results_path, readme_path, *sorted(case_dir.glob("*.json"))]
    manifest = {"schema": "spike/accuracy-artifact-manifest/v1", "artifacts": [
        {"path": str(path).replace("\\", "/"), "sha256": sha256_file(path)} for path in artifact_paths
    ]}
    write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir)}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
