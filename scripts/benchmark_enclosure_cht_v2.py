#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproducible source-bound acceptance benchmark for enclosure CHT v2.

This is synthetic mathematical verification, not measured validation or a
production qualification. The rectilinear momentum MMS is intentionally owned
by its kernel benchmark and is not duplicated here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.enclosure_cht_v2 import REQUEST, solve_enclosure_cht_v2


CONTRACT = "spike/enclosure-cht-v2-benchmark/v1"
FACES = ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max")
SOURCES = (
    "python/spike_core/enclosure_cht_v2.py",
    "python/spike_core/enclosure_cht.py",
    "python/spike_core/enclosure_rectilinear_momentum.py",
    "python/spike_core/enclosure_stokes.py",
    "python/spike_core/enclosure_energy.py",
    "python/spike_core/enclosure_refinement.py",
    "schemas/enclosure-cht-request-v2.schema.json",
    "schemas/enclosure-cht-result-v2.schema.json",
    "scripts/benchmark_enclosure_cht_v2.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes() -> dict[str, str]:
    return {name: _digest(ROOT / name) for name in SOURCES}


def _write_json_new(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _retain(output: Path, case_id: str, request: dict, result: dict) -> dict:
    request_path = output / f"{case_id}-request.json"
    result_path = output / f"{case_id}-result.json"
    _write_json_new(request_path, request)
    _write_json_new(result_path, result)
    return {
        "request": request_path.name,
        "request_sha256": _digest(request_path),
        "result": result_path.name,
        "result_sha256": _digest(result_path),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _material(name="fluid", phase="fluid", conductivity=1.0, capacity=1.0):
    value = {"id": name, "phase": phase, "density_kg_m3": 1.0,
             "specific_heat_j_kgk": capacity, "conductivity_w_mk": conductivity}
    if phase == "fluid":
        value["dynamic_viscosity_pa_s"] = 1.0
    return value


def _fixture(shape=(4, 4, 4), *, obstacle=True, refined=False):
    ids = np.full(shape, "fluid", dtype="U8")
    materials = [_material()]
    if obstacle:
        ids[1:3, 1:3, 1:3] = "solid"
        materials.append(_material("solid", "solid", 3.0, 2.0))
    force = np.zeros((*shape, 3))
    force[..., 0] = np.arange(shape[1])[None, :, None] * 0.01
    force[ids != "fluid"] = 0.0
    heat = np.zeros(shape)
    heat[ids != "fluid"] = 100.0
    request = {
        "contract": REQUEST,
        "grid": {"shape": list(shape), "spacing_m": [0.1] * 3,
                 "origin_m": [0.0] * 3, "local_refinement": []},
        "materials": materials,
        "material_ids": ids.tolist(),
        "flow": {"model": "rectilinear_laminar", "body_force_n_m3": force.tolist(),
                 "nonlinear_controls": {"max_iterations": 60, "relaxation": 1.0,
                                        "relative_tolerance": 1e-10}},
        "heat_sources_w_m3": heat.tolist(),
        "boundaries": {face: {"type": "temperature", "temperature_k": 300.0}
                       for face in FACES},
        "study": {"type": "steady"},
    }
    if refined:
        request["grid"]["local_refinement"] = [{
            "bounds_m": [[0.08, 0.32], [0.08, 0.32], [0.08, 0.32]],
            "split_factor": 2,
        }]
    return request


def _check_completed(result, label):
    _require(result.get("status") == "completed", f"{label} did not complete: {result}")
    flow = result["flow_diagnostics"]
    mass = result["independent_mass_diagnostics"]
    energy = result["energy_diagnostics"]
    _require(flow["momentum_relative_residual"] <= 1e-10,
             f"{label} momentum residual exceeded 1e-10")
    _require(flow["relative_energy_defect"] <= 1e-9,
             f"{label} kinetic-energy defect exceeded 1e-9")
    _require(mass["independent_maximum_divergence_s_inv"]
             <= mass["independent_divergence_budget_s_inv"],
             f"{label} physical mass exceeded 1e-9 velocity/length scale")
    _require(energy["relative_energy_balance"] <= 1e-7,
             f"{label} relative heat balance exceeded 1e-7")


def _obstacle_refinement(output: Path) -> dict:
    rows = []
    for refined in (False, True):
        label = "refined" if refined else "coarse"
        request = _fixture(refined=refined)
        # Synthetic high-density reference fluid: raises inertia without making
        # omitted viscous heating material to the passive-scalar heat balance.
        request["materials"][0]["density_kg_m3"] = 200000.0
        result = solve_enclosure_cht_v2(request)
        _check_completed(result, f"obstacle {label}")
        flow, energy = result["flow_diagnostics"], result["energy_diagnostics"]
        _require(0.0 < flow["force_work_w"] < 1e-3,
                 f"obstacle {label} did not exercise bounded positive drive work")
        _require(1.0 < flow["reynolds_upper_bound"] <= 20.0,
                 f"obstacle {label} did not exercise admitted inertia")
        _require(flow["iterations"] >= 3,
                 f"obstacle {label} did not exercise nonlinear iteration")
        _require(flow["momentum_residual_history"][0] > 1e-4
                 and flow["momentum_residual_history"][-1] <= 1e-10,
                 f"obstacle {label} lacks converged nonzero-convection iteration evidence")
        _require(abs(float(energy["generated_heat_w"]) - 0.8) <= 1e-12,
                 f"obstacle {label} generated heat differs from 0.8 W")
        _require(len(result["interfaces"]) > 0,
                 f"obstacle {label} returned no fluid-solid interface evidence")
        rows.append({
            "grid": label,
            "fine_shape": result["grid"]["shape"],
            "velocity_unknowns": flow["velocity_unknowns"],
            "force_work_w": flow["force_work_w"],
            "reynolds_upper_bound": flow["reynolds_upper_bound"],
            "nonlinear_iterations": flow["iterations"],
            "initial_nonlinear_residual": flow["momentum_residual_history"][0],
            "maximum_divergence_s_inv": result["independent_mass_diagnostics"][
                "independent_maximum_divergence_s_inv"],
            "divergence_budget_s_inv": result["independent_mass_diagnostics"][
                "independent_divergence_budget_s_inv"],
            "relative_heat_balance": energy["relative_energy_balance"],
            "artifact": _retain(output, f"obstacle-{label}", request, result),
        })
    _require(rows[1]["velocity_unknowns"] > rows[0]["velocity_unknowns"],
             "manual cuts did not add actual momentum unknowns")
    work_difference = abs(rows[1]["force_work_w"] - rows[0]["force_work_w"])
    _require(work_difference > 1e-12,
             "manual cuts left momentum work unchanged; possible interpolation-only implementation")
    return {"runs": rows, "force_work_difference_w": work_difference, "passed": True}


def _disconnected_hydrostatic(output: Path) -> dict:
    request = _fixture((5, 3, 3), obstacle=False)
    ids = np.full((5, 3, 3), "fluid", dtype="U8")
    ids[2, :, :] = "wall"
    request["materials"].append(_material("wall", "solid", 2.0))
    request["material_ids"] = ids.tolist()
    force = np.broadcast_to([1.0, -0.5, 0.25], (5, 3, 3, 3)).copy()
    force[ids == "wall"] = 0.0
    request["flow"]["body_force_n_m3"] = force.tolist()
    request["heat_sources_w_m3"] = np.zeros((5, 3, 3)).tolist()
    result = solve_enclosure_cht_v2(request)
    _check_completed(result, "disconnected hydrostatic")
    _require(result["flow_diagnostics"]["fluid_components"] == 2,
             "hydrostatic fixture did not retain two fluid components")
    maximum_speed = max(float(np.max(np.abs(values), initial=0.0))
                        for values in result["fields"]["face_velocity_m_s"])
    _require(maximum_speed < 1e-14, "hydrostatic force produced nonzero flow")
    temperature_error = float(np.max(np.abs(
        np.asarray(result["fields"]["temperature_k"]) - 300.0), initial=0.0))
    _require(temperature_error < 1e-12, "hydrostatic fixture lost uniform temperature")
    pressure = np.asarray(result["fields"]["gauge_pressure_pa"])
    pressure_error = 0.0
    for slab in (pressure[:2], pressure[3:]):
        pressure_error = max(pressure_error,
            float(np.max(np.abs(np.diff(slab, axis=0) - 0.1), initial=0.0)),
            float(np.max(np.abs(np.diff(slab, axis=1) + 0.05), initial=0.0)),
            float(np.max(np.abs(np.diff(slab, axis=2) - 0.025), initial=0.0)))
    _require(pressure_error < 1e-12, "hydrostatic pressure gradient error exceeded 1e-12 Pa")
    return {"fluid_components": 2, "maximum_speed_m_s": maximum_speed,
            "maximum_pressure_step_error_pa": pressure_error,
            "maximum_temperature_error_k": temperature_error,
            "artifact": _retain(output, "disconnected-hydrostatic", request, result),
            "passed": True}


def _transient_startup(output: Path) -> dict:
    request = _fixture(refined=True)
    ids = np.asarray(request["material_ids"])
    capacities = {entry["id"]: entry["density_kg_m3"] * entry["specific_heat_j_kgk"]
                  for entry in request["materials"]}
    rate = 0.2
    request["flow"]["body_force_n_m3"] = np.zeros((4, 4, 4, 3)).tolist()
    request["heat_sources_w_m3"] = np.vectorize(lambda mid: rate * capacities[mid])(ids).tolist()
    request["boundaries"] = {face: {"type": "adiabatic"} for face in FACES}
    request["study"] = {"type": "transient", "time_step_s": 0.1, "steps": 4,
                        "initial_temperature_k": 300.0, "output_stride": 2}
    result = solve_enclosure_cht_v2(request)
    _check_completed(result, "transient startup")
    maximum_error = 0.0
    for frame in result["temperature_frames"]:
        exact = 300.0 + rate * frame["time_s"]
        maximum_error = max(maximum_error, float(np.max(np.abs(
            np.asarray(frame["temperature_k"]) - exact), initial=0.0)))
    _require(maximum_error <= 2e-12, "transient startup exact temperature error exceeded 2e-12 K")
    integrated = abs(float(result["energy_diagnostics"]["raw_integrated_energy_balance_j"]))
    _require(integrated <= 1e-12, "transient startup integrated energy error exceeded 1e-12 J")
    return {"uniform_temperature_rate_k_s": rate,
            "maximum_temperature_error_k": maximum_error,
            "raw_integrated_energy_balance_j": integrated,
            "artifact": _retain(output, "transient-startup", request, result),
            "passed": True}


def run(output: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True)
    sources_before = _source_hashes()
    cases = {
        "obstacle_refined_momentum_and_heat": _obstacle_refinement(output),
        "disconnected_hydrostatic_components": _disconnected_hydrostatic(output),
        "multimaterial_transient_startup": _transient_startup(output),
    }
    sources_after = _source_hashes()
    _require(sources_before == sources_after, "benchmark sources changed during execution")
    receipt = {
        "contract": CONTRACT,
        "passed": True,
        "model_status": "experimental",
        "production_qualified": False,
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "numpy": np.__version__, "scipy": scipy.__version__},
        "source_sha256": sources_before,
        "criteria": {
            "momentum_relative_residual_maximum_inclusive": 1e-10,
            "kinetic_energy_relative_defect_maximum_inclusive": 1e-9,
            "physical_mass_relative_velocity_length_scale_maximum_inclusive": 1e-9,
            "heat_relative_balance_maximum_inclusive": 1e-7,
            "obstacle_force_work_w_range_exclusive": [0.0, 1e-3],
            "obstacle_reynolds_upper_bound_range": [1.0, 20.0],
            "obstacle_nonlinear_iterations_minimum_inclusive": 3,
            "obstacle_initial_nonlinear_residual_minimum_exclusive": 1e-4,
            "manual_cut_force_work_difference_w_minimum_exclusive": 1e-12,
            "hydrostatic_maximum_speed_m_s_maximum_exclusive": 1e-14,
            "transient_integrated_energy_error_j_maximum_inclusive": 1e-12,
        },
        "cases": cases,
        "limitations": [
            "Synthetic mathematical verification only; no measured enclosure or external-solver validation.",
            "Selected cuts propagate tensor planes through the domain; they are not confined octree AMR.",
            "Supplied Cartesian voxel solids only; no curved CAD or conforming cut cells.",
            "Constant-property steady laminar momentum; no turbulence, rotors, buoyancy feedback or FSI.",
            "The inertial obstacle case uses a synthetic high-density reference fluid, not air or a material recommendation.",
            "The kernel-owned momentum manufactured-solution convergence benchmark is not duplicated here.",
            "Passing conservation and refinement checks does not establish production accuracy for arbitrary enclosures.",
        ],
    }
    _write_json_new(output / "receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh directory for exact requests, results and receipt.json")
    args = parser.parse_args()
    receipt = run(args.output)
    print(json.dumps({"output": str(args.output.resolve()), "passed": receipt["passed"],
                      "contract": receipt["contract"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
