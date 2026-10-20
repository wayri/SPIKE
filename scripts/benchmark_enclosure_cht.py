#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run source-bound enclosure flow/CHT verification benchmarks.

This harness retains every exact request and result in a fresh caller-selected
directory.  It writes receipt.json only after all numerical assertions pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path
import sys

import numpy as np
import scipy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from python.spike_core.enclosure_cht import solve_enclosure_cht
from tests.python.test_enclosure_cht import fixture as cht_fixture
from tests.python.test_enclosure_cht import layered_fixture, material
from tests.python.test_enclosure_cht_advection import manufactured_advection
from tests.python.test_enclosure_laminar import exact_fields, fixture as laminar_fixture
from tests.python.test_enclosure_laminar import manufactured


CONTRACT = "spike/enclosure-cht-benchmark/v1"
SOURCE_PATHS = (
    "scripts/benchmark_enclosure_cht.py",
    "python/spike_core/enclosure_cht.py",
    "python/spike_core/enclosure_energy.py",
    "python/spike_core/enclosure_refinement.py",
    "python/spike_core/enclosure_laminar.py",
    "python/spike_core/enclosure_stokes.py",
    "tests/python/test_enclosure_cht.py",
    "tests/python/test_enclosure_cht_advection.py",
    "tests/python/test_enclosure_laminar.py",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes() -> dict[str, str]:
    return {name: _digest(ROOT / name) for name in SOURCE_PATHS}


def _write_json_new(path: Path, value) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def _retain(output: Path, case_id: str, request: dict, result: dict) -> dict:
    request_path = output / f"{case_id}.request.json"
    result_path = output / f"{case_id}.result.json"
    _write_json_new(request_path, request)
    _write_json_new(result_path, result)
    return {
        "request_file": request_path.name,
        "request_sha256": _digest(request_path),
        "result_file": result_path.name,
        "result_sha256": _digest(result_path),
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _mms_request(n: int) -> dict:
    request = laminar_fixture(n)
    centers = (np.arange(n) + 0.5) / n
    xyz = np.meshgrid(centers, centers, centers, indexing="ij")
    request["body_force_n_m3"] = exact_fields(xyz)[1].tolist()
    return request


def _inertial_mms(output: Path) -> dict:
    rows = []
    for n in (4, 8, 12):
        request = _mms_request(n)
        velocity_error, pressure_error_pa, result = manufactured(n)
        _require(result.get("status") == "completed", f"MMS n={n} did not complete")
        diagnostics = result["diagnostics"]
        _require(diagnostics["momentum_relative_residual"] < 1e-10,
                 f"MMS n={n} momentum residual exceeded 1e-10")
        _require(diagnostics["maximum_divergence_s_inv"] < 1e-10,
                 f"MMS n={n} divergence exceeded 1e-10 /s")
        _require(abs(diagnostics["advective_power_w"]) < 1e-10,
                 f"MMS n={n} advective power defect exceeded 1e-10 W")
        _require(abs(diagnostics["pressure_power_w"]) < 1e-10,
                 f"MMS n={n} pressure power defect exceeded 1e-10 W")
        row = {
            "n": n,
            "velocity_relative_l2_error": float(velocity_error),
            "pressure_gauge_l2_error_pa": float(pressure_error_pa),
            "diagnostics": diagnostics,
            "artifact": _retain(output, f"inertial-mms-{n}", request, result),
        }
        rows.append(row)
    orders = [
        math.log(rows[index]["velocity_relative_l2_error"]
                 / rows[index + 1]["velocity_relative_l2_error"])
        / math.log(rows[index + 1]["n"] / rows[index]["n"])
        for index in range(2)
    ]
    _require(all(order > 1.8 for order in orders),
             f"MMS observed orders must exceed 1.8, got {orders}")
    _require(rows[-1]["velocity_relative_l2_error"] < 0.02,
             "MMS finest velocity error exceeded 0.02")
    _require(rows[-1]["pressure_gauge_l2_error_pa"] < rows[0]["pressure_gauge_l2_error_pa"],
             "MMS pressure error did not improve")
    return {"runs": rows, "observed_velocity_orders": orders, "passed": True}


def _layered_resistance(output: Path) -> dict:
    heat_flux_density = 10.0 / (0.1 / 2.0 + 0.4 / 0.5 + 0.1 / 4.0)
    expected_heat_w = heat_flux_density * 0.04
    rows = []
    for refined in (False, True):
        request = layered_fixture(refined)
        result = solve_enclosure_cht(request)
        label = "refined" if refined else "coarse"
        _require(result.get("status") == "completed", f"layered {label} case did not complete")
        energy = result["energy_diagnostics"]
        heat_in = -float(energy["outward_heat_w"]["x_min"])
        heat_out = float(energy["outward_heat_w"]["x_max"])
        error = max(abs(heat_in - expected_heat_w), abs(heat_out - expected_heat_w))
        _require(error < 1e-12, f"layered {label} resistance error exceeded 1e-12 W")
        _require(energy["maximum_interface_temperature_jump_k"] < 1e-12,
                 f"layered {label} interface jump exceeded 1e-12 K")
        rows.append({
            "grid": label,
            "expected_heat_w": expected_heat_w,
            "heat_in_w": heat_in,
            "heat_out_w": heat_out,
            "maximum_heat_error_w": error,
            "fine_shape": result["grid"]["shape"],
            "artifact": _retain(output, f"layered-{label}", request, result),
        })
    difference = abs(rows[0]["heat_out_w"] - rows[1]["heat_out_w"])
    _require(difference < 1e-12, "coarse/refined layered heat differs by at least 1e-12 W")
    return {"runs": rows, "coarse_refined_heat_difference_w": difference, "passed": True}


def _source_flux(output: Path) -> dict:
    request = cht_fixture((5, 4, 4))
    ids = np.full((5, 4, 4), "fluid", dtype="U8")
    ids[2, 1:3, 1:3] = "heater"
    request["material_ids"] = ids.tolist()
    request["materials"].append(material("heater", "solid", 3.0))
    force = np.zeros((5, 4, 4, 3))
    force[..., 0] = np.arange(4)[None, :, None] * 0.01
    force[ids == "heater"] = 0.0
    request["flow"]["body_force_n_m3"] = force.tolist()
    heat = np.zeros((5, 4, 4))
    heat[ids == "heater"] = 100.0
    request["heat_sources_w_m3"] = heat.tolist()
    request["grid"]["local_refinement"] = [{
        "bounds_m": [[0.2, 0.3], [0.1, 0.3], [0.1, 0.3]],
        "split_factor": 2,
    }]
    result = solve_enclosure_cht(request)
    _require(result.get("status") == "completed", "source/flux CHT case did not complete")
    energy = result["energy_diagnostics"]
    generated = float(energy["generated_heat_w"])
    outward = math.fsum(float(value) for value in energy["outward_heat_w"].values())
    _require(abs(generated - 0.4) < 1e-13, "source/flux generated heat differs from 0.4 W")
    _require(abs(energy["raw_energy_balance_w"]) < 1e-11,
             "source/flux raw energy balance exceeded 1e-11 W")
    _require(abs(outward - generated) < 1e-11,
             "source/flux integrated boundary heat does not equal generated heat")
    _require(result["transfer_diagnostics"]["maximum_fine_divergence_s_inv"] < 1e-10,
             "source/flux prolonged divergence exceeded 1e-10 /s")
    _require(result["flow_diagnostics"]["force_work_w"] > 0.0,
             "source/flux flow did no positive force work")
    return {
        "generated_heat_w": generated,
        "outward_boundary_heat_w": outward,
        "raw_energy_balance_w": energy["raw_energy_balance_w"],
        "maximum_fine_divergence_s_inv": result["transfer_diagnostics"][
            "maximum_fine_divergence_s_inv"],
        "artifact": _retain(output, "source-flux", request, result),
        "passed": True,
    }


def _thermal_spatial_mms(output: Path) -> dict:
    rows = []
    for n in (4, 8, 12):
        request = cht_fixture((n, n, n))
        request["grid"]["spacing_m"] = [1.0 / n] * 3
        centers = (np.arange(n) + 0.5) / n
        xyz = np.meshgrid(centers, centers, centers, indexing="ij")
        mode = np.prod([np.sin(math.pi * coordinate) for coordinate in xyz], axis=0)
        exact = 300.0 + mode
        request["heat_sources_w_m3"] = (3.0 * math.pi**2 * mode).tolist()
        result = solve_enclosure_cht(request)
        _require(result.get("status") == "completed",
                 f"thermal spatial MMS n={n} did not complete")
        actual = np.asarray(result["fields"]["temperature_k"], dtype=float)
        relative_rise_error = float(np.linalg.norm(actual - exact) / np.linalg.norm(mode))
        _require(abs(result["energy_diagnostics"]["raw_energy_balance_w"]) < 1e-10,
                 f"thermal spatial MMS n={n} energy balance exceeded 1e-10 W")
        rows.append({
            "n": n,
            "relative_temperature_rise_l2_error": relative_rise_error,
            "raw_energy_balance_w": result["energy_diagnostics"]["raw_energy_balance_w"],
            "artifact": _retain(output, f"thermal-spatial-mms-{n}", request, result),
        })
    orders = [
        math.log(rows[index]["relative_temperature_rise_l2_error"]
                 / rows[index + 1]["relative_temperature_rise_l2_error"])
        / math.log(rows[index + 1]["n"] / rows[index]["n"])
        for index in range(2)
    ]
    _require(all(order > 1.8 for order in orders),
             f"thermal spatial MMS observed orders must exceed 1.8, got {orders}")
    _require(rows[-1]["relative_temperature_rise_l2_error"] < 0.01,
             "thermal spatial MMS finest relative rise error exceeded 0.01")
    return {
        "field": "T=300+sin(pi*x)*sin(pi*y)*sin(pi*z)",
        "source_w_m3": "q=3*pi^2*sin(pi*x)*sin(pi*y)*sin(pi*z)",
        "scope": "continuous steady conduction oracle; not advective CHT qualification",
        "runs": rows,
        "observed_temperature_orders": orders,
        "passed": True,
    }


def _coupled_advection_mms(output: Path) -> dict:
    rows = []
    for n in (4, 8, 12):
        request, result, metrics = manufactured_advection(n)
        _require(result.get("status") == "completed",
                 f"coupled advection MMS n={n} did not complete")
        flow = result["flow_diagnostics"]
        energy = result["energy_diagnostics"]
        _require(metrics["maximum_analytical_advection_w_m3"] > 1.0,
                 f"coupled advection MMS n={n} has trivial analytical advection")
        _require(flow["reynolds_upper_bound"] > 2.0,
                 f"coupled advection MMS n={n} did not exercise inertia")
        _require(flow["momentum_relative_residual"] <= 1e-10,
                 f"coupled advection MMS n={n} momentum residual exceeded 1e-10")
        _require(flow["relative_energy_defect"] < 1e-9,
                 f"coupled advection MMS n={n} mechanical energy defect exceeded 1e-9")
        _require(result["transfer_diagnostics"]["maximum_fine_divergence_s_inv"] < 1e-10,
                 f"coupled advection MMS n={n} prolonged divergence exceeded 1e-10 /s")
        generated = float(metrics["independent_generated_heat_w"])
        outward = math.fsum(float(value) for value in energy["outward_heat_w"].values())
        _require(abs(float(energy["generated_heat_w"]) - generated) < 1e-12,
                 f"coupled advection MMS n={n} generated heat disagrees with oracle")
        _require(abs(outward - generated) < 1e-10 * max(abs(generated), 1.0),
                 f"coupled advection MMS n={n} global heat balance failed")
        _require(energy["relative_energy_balance"] < 1e-9,
                 f"coupled advection MMS n={n} relative energy balance exceeded 1e-9")
        rows.append({
            **metrics,
            "outward_boundary_heat_w": outward,
            "energy_relative_balance": energy["relative_energy_balance"],
            "flow_reynolds_upper_bound": flow["reynolds_upper_bound"],
            "artifact": _retain(output, f"coupled-advection-mms-{n}", request, result),
        })
    orders = [
        math.log(rows[index]["relative_temperature_rise_l2_error"]
                 / rows[index + 1]["relative_temperature_rise_l2_error"])
        / math.log(rows[index + 1]["n"] / rows[index]["n"])
        for index in range(2)
    ]
    _require(all(order >= 0.7 for order in orders),
             f"coupled advection MMS observed orders must be at least 0.7, got {orders}")
    _require(rows[-1]["relative_temperature_rise_l2_error"] < 0.1,
             "coupled advection MMS finest relative rise error exceeded 0.1")
    return {
        "scope": "nonzero-advection continuous thermal MMS; synthetic coupled verification",
        "runs": rows,
        "observed_temperature_orders": orders,
        "passed": True,
    }


def _embedded_inertial_solid_source(output: Path) -> dict:
    request = cht_fixture((6, 6, 6))
    request["grid"]["spacing_m"] = [0.25, 0.25, 0.25]
    request["grid"]["local_refinement"] = [{
        "bounds_m": [[0.01, 0.2], [0.5, 1.0], [0.5, 1.0]],
        "split_factor": 2,
    }]
    ids = np.full((6, 6, 6), "wall", dtype="U8")
    ids[1:5, 1:5, 1:5] = "fluid"
    request["material_ids"] = ids.tolist()
    request["materials"].append(material("wall", "solid", 2.0))
    local_centers = (np.arange(4) + 0.5) / 4
    _, local_force, _ = exact_fields(
        np.meshgrid(local_centers, local_centers, local_centers, indexing="ij"))
    force = np.zeros((6, 6, 6, 3))
    force[1:5, 1:5, 1:5] = local_force
    request["flow"] = {
        "model": "laminar_inertial",
        "body_force_n_m3": force.tolist(),
        "nonlinear_controls": {
            "max_iterations": 60, "relaxation": 1.0, "relative_tolerance": 1e-10,
        },
    }
    heat = np.zeros((6, 6, 6))
    heat[0, 2:4, 2:4] = 40.0
    request["heat_sources_w_m3"] = heat.tolist()
    result = solve_enclosure_cht(request)
    _require(result.get("status") == "completed",
             "embedded inertial fluid/solid source case did not complete")
    flow = result["flow_diagnostics"]
    transfer = result["transfer_diagnostics"]
    energy = result["energy_diagnostics"]
    velocities = [np.asarray(values) for values in result["fields"]["face_velocity_m_s"]]
    maximum_speed = max(float(np.max(np.abs(values), initial=0.0)) for values in velocities)
    _require(flow["thermal_grid_fluid_box_indices"] == [[1, 1, 1], [5, 5, 5]],
             "embedded inertial fluid box identity changed")
    _require(flow["reynolds_upper_bound"] > 2.0 and flow["iterations"] > 2,
             "embedded case did not exercise nonlinear inertia")
    _require(flow["force_work_w"] > 0.0 and maximum_speed > 0.0,
             "embedded case produced no moving flow")
    _require(flow["momentum_relative_residual"] <= 1e-10,
             "embedded inertial momentum residual exceeded 1e-10")
    _require(flow["maximum_divergence_s_inv"] < 1e-10,
             "embedded inertial mass divergence exceeded 1e-10 /s")
    _require(flow["relative_energy_defect"] < 1e-9,
             "embedded inertial mechanical energy defect exceeded 1e-9")
    _require(transfer["maximum_fine_divergence_s_inv"] < 1e-10,
             "embedded prolonged mass divergence exceeded 1e-10 /s")
    _require(transfer["coarse_face_flux_integral_relative_error"] < 1e-12,
             "embedded coarse/fine face flux transfer error exceeded 1e-12")
    _require(len(result["interfaces"]) > 0,
             "embedded case returned no solid/fluid interface evidence")
    _require(energy["maximum_interface_temperature_jump_k"] < 1e-10,
             "embedded interface temperature jump exceeded 1e-10 K")
    _require(abs(float(energy["generated_heat_w"]) - 2.5) < 1e-12,
             "embedded solid source did not integrate to 2.5 W")
    _require(abs(float(energy["raw_energy_balance_w"])) < 1e-10,
             "embedded global energy balance exceeded 1e-10 W")
    _require(float(energy["maximum_temperature_k"]) > 300.0,
             "embedded solid source produced no temperature rise")
    return {
        "fluid_box_indices": flow["thermal_grid_fluid_box_indices"],
        "maximum_speed_m_s": maximum_speed,
        "reynolds_upper_bound": flow["reynolds_upper_bound"],
        "flow_iterations": flow["iterations"],
        "generated_heat_w": energy["generated_heat_w"],
        "raw_energy_balance_w": energy["raw_energy_balance_w"],
        "maximum_temperature_k": energy["maximum_temperature_k"],
        "maximum_interface_temperature_jump_k": energy[
            "maximum_interface_temperature_jump_k"],
        "interface_records": len(result["interfaces"]),
        "maximum_fine_divergence_s_inv": transfer["maximum_fine_divergence_s_inv"],
        "artifact": _retain(output, "embedded-inertial-solid-source", request, result),
        "passed": True,
    }


def _transient_be(output: Path) -> dict:
    exact_temperature_k = 300.0 + 10.0 * math.exp(-6.0 / (0.5 + 10.0))
    rows = []
    for steps in (8, 16, 32):
        request = cht_fixture((1, 1, 1))
        request["grid"]["spacing_m"] = [1.0, 1.0, 1.0]
        request["boundaries"] = {
            face: {"type": "convection", "ambient_temperature_k": 300.0,
                   "heat_transfer_coefficient_w_m2k": 0.1}
            for face in request["boundaries"]
        }
        request["study"] = {"type": "transient", "time_step_s": 1.0 / steps,
                            "steps": steps, "initial_temperature_k": 310.0,
                            "output_stride": steps}
        result = solve_enclosure_cht(request)
        _require(result.get("status") == "completed", f"BE steps={steps} did not complete")
        actual = float(result["fields"]["temperature_k"][0][0][0])
        rows.append({
            "steps": steps,
            "time_step_s": 1.0 / steps,
            "temperature_k": actual,
            "exact_temperature_k": exact_temperature_k,
            "absolute_error_k": abs(actual - exact_temperature_k),
            "artifact": _retain(output, f"transient-be-{steps}", request, result),
        })
    orders = [math.log(rows[index]["absolute_error_k"]
                       / rows[index + 1]["absolute_error_k"], 2.0)
              for index in range(2)]
    _require(all(order > 0.9 for order in orders),
             f"BE observed orders must exceed 0.9, got {orders}")
    return {"runs": rows, "observed_temperature_orders": orders, "passed": True}


def run(output: Path) -> dict:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite benchmark directory: {output}")
    output.mkdir(parents=True)
    sources_before = _source_hashes()
    cases = {
        "inertial_manufactured_solution": _inertial_mms(output),
        "layered_series_resistance": _layered_resistance(output),
        "conjugate_source_flux": _source_flux(output),
        "thermal_spatial_manufactured_solution": _thermal_spatial_mms(output),
        "coupled_advection_manufactured_solution": _coupled_advection_mms(output),
        "embedded_inertial_solid_source": _embedded_inertial_solid_source(output),
        "transient_backward_euler": _transient_be(output),
    }
    sources_after = _source_hashes()
    _require(sources_before == sources_after, "benchmark source changed during execution")
    receipt = {
        "contract": CONTRACT,
        "passed": True,
        "model_status": "experimental",
        "production_qualified": False,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "source_sha256": sources_before,
        "criteria": {
            "inertial_velocity_order_minimum_exclusive": 1.8,
            "inertial_finest_velocity_relative_l2_error_maximum_exclusive": 0.02,
            "layered_heat_absolute_error_w_maximum_exclusive": 1e-12,
            "source_energy_balance_w_maximum_exclusive": 1e-11,
            "thermal_spatial_temperature_order_minimum_exclusive": 1.8,
            "thermal_spatial_finest_relative_rise_l2_error_maximum_exclusive": 0.01,
            "coupled_advection_temperature_order_minimum_inclusive": 0.7,
            "coupled_advection_finest_relative_rise_l2_error_maximum_exclusive": 0.1,
            "transient_temperature_order_minimum_exclusive": 0.9,
        },
        "cases": cases,
        "limitations": [
            "Synthetic verification only; no measured enclosure or external-solver validation.",
            "Inertial momentum uses a uniform full rectangular fluid box; thermal refinement does not refine momentum or pressure.",
            "The thermal spatial manufactured solution verifies continuous conduction only, not advective CHT spatial accuracy.",
            "The embedded solid-interface case is one bounded rectangular inertial fluid box, not general inertial obstacle flow.",
            "Constant-property Cartesian voxel geometry only; no turbulence, buoyancy, radiation, phase change, rotors, or CAD-fit mesh.",
            "Passing residual, conservation, and refinement checks does not establish production accuracy for arbitrary enclosures.",
        ],
    }
    _write_json_new(output / "receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Fresh directory for exact requests, results, and receipt.json")
    args = parser.parse_args()
    receipt = run(args.output)
    print(json.dumps({"output": str(args.output.resolve()), "passed": receipt["passed"],
                      "contract": receipt["contract"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
