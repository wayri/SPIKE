# SPDX-License-Identifier: Apache-2.0
"""Execute and independently check explicit RC demonstration thermal models."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
import numpy as np
from scipy.integrate import solve_ivp
from python.spike_core.headless import run_request


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def execute(directory, stem, method, params):
    request = {"method": method, "params": params}
    write(directory / f"{stem}-request.json", request)
    envelope = run_request(request, timeout_seconds=120)
    write(directory / f"{stem}-envelope.json", envelope)
    if not envelope.get("ok"):
        raise RuntimeError(f"{stem}: {envelope}")
    result = envelope["result"]
    write(directory / f"{stem}-result.json", result)
    if result.get("status") != "completed":
        raise RuntimeError(f"{stem}: status {result.get('status')}")
    return result


def build_model(directory):
    assembly = read(directory / "assembly.json")
    scenario = read(directory / "scenario.json")
    designs = {d["design_id"]: d for d in read(directory / "designs.json")["designs"]}
    pi = read(directory / "pi-result.json")
    native = pi if scenario["single_board"] else pi["native_result"]
    if native["status"] != "completed":
        raise ValueError("Thermal deposition requires completed actual PI output.")
    powers = {b["id"]: 0. for b in assembly["boards"]}
    deposition = []
    admitted = set()
    for board in scenario["board_elements"]:
        owner = board["board_id"]
        for element in board["elements"]:
            if element["type"] != "resistor":
                continue
            identifier = element["id"] if scenario["single_board"] else pi["element_map"][owner][element["id"]]
            loss = native["data"]["element_power_w"][identifier]
            current = native["data"]["element_current_a"][identifier]
            if abs(loss-current**2*element["resistance_ohm"]) > 1e-8 or loss < -1e-12:
                raise ValueError(f"Inconsistent resistor loss {identifier}.")
            powers[owner] += max(0., loss)
            admitted.add(identifier)
            deposition.append({"board_id": owner, "electrical_element_id": identifier, "deposited_power_w": max(0., loss), "fraction": 1.})
    endpoints = {("mate", m["id"]): m["data"] for m in assembly.get("connector_mappings", []) if m["kind"] == "connector-mate"}
    endpoints.update({("harness", h["id"]): h for h in assembly.get("harnesses", [])})
    for link in pi.get("links", []):
        ends = endpoints[(link["kind"], link["link_id"])]
        for endpoint in ("endpoint_a", "endpoint_b"):
            owner = ends[endpoint].split("::")[0]
            loss = link["total_loss_w"] / 2
            powers[owner] += loss
            deposition.append({"board_id": owner, "link_id": link["link_id"], "pin": link["source_pin"], "deposited_power_w": loss, "fraction": .5})
        admitted.update(e for e in link["element_ids"] if e.endswith(":resistor"))
    unmatched = {e: p for e, p in native["data"]["element_power_w"].items() if p > 1e-10 and e not in admitted}
    if unmatched:
        raise ValueError(f"Unmapped PI dissipation: {unmatched}")
    positive_power = sum(max(0., p) for p in native["data"]["element_power_w"].values())
    if abs(sum(powers.values())-positive_power) > 1e-8:
        raise ValueError("Total PI dissipation does not equal deposited heat.")
    board_models, areas, dimensions = [], {}, {}
    for board in assembly["boards"]:
        owner = board["id"]
        bounds = designs[board["design_id"]]["metadata"]["board_bounds_mm"]
        dimensions[owner] = {"x": bounds[2]-bounds[0], "y": bounds[3]-bounds[1], "z": 1.6}
        areas[owner] = dimensions[owner]["x"] * dimensions[owner]["y"]
        uno = owner.startswith("uno-")
        board_models.append({"board_id": owner, "elements": [{"id": "board", "power_w": powers[owner],
                             "ambient_resistance_c_per_w": 18. if uno else 22.,
                             "thermal_capacitance_j_per_c": 18. if uno else 12.}], "links": []})
    assumptions = {"model_status": "approximate", "board_power_w": powers, "loss_deposition": deposition,
                   "pi_positive_dissipation_w": positive_power,
                   "deposition_balance_residual_w": sum(powers.values())-positive_power,
                   "board_bounds_rectangle_area_mm2": areas,
                   "notes": ["One uniform temperature node per imported board occurrence; no spatial thermal field.",
                             "UNO ambient resistance18 C/W and capacitance18 J/K; shield22 C/W and12 J/K; assumed constants, not fitted hardware values.",
                             "All actual PI resistor losses deposited; UNO operating-load already represents nominal0.35 W and is not added again.",
                             "All connector and cable loss split equally into endpoint boards; cable temperature and distributed heat leakage are not resolved.",
                             "Fixed25 C ambient; direct stack contact conductance0.025 W/K; no cable thermal conduction or interstack radiation.",
                             "Board bounding rectangles supply radiation area; holes, component occlusion and edge areas omitted; emissivity0.85 assumed.",
                             "Each stack uses one facing surface per board; UNO-to-shield view factor0.55; reverse factor enforces area reciprocity; remainder sees black ambient. Opposite face cooling is within assumed ambient resistance.",
                             "Single-board RC uses ambient resistance only; no explicit radiation. Single element1.6 mm thickness is a contract geometry assumption and does not determine RC properties.",
                             "One-way deposition of nominal-temperature PI losses; no temperature-dependent electrical feedback, FEA, CFD or hardware accuracy qualification."]}
    if scenario["single_board"]:
        model = board_models[0]
        element = dict(model["elements"][0], id=model["board_id"], dimensions_mm=dimensions[model["board_id"]])
        request = {"contract": "spike/thermal/v1", "scenario_id": scenario["id"], "mode": "steady_state",
                   "ambient_temperature_c": 25., "thermal_elements": [element], "thermal_links": [],
                   "heat_sources": [{"id": model["board_id"], "power_w": element["power_w"]}]}
    else:
        contacts = [{"contact_id": c["id"], "from": {"board_id": c["endpoint_a"], "node": "board"},
                     "to": {"board_id": c["endpoint_b"], "node": "board"}, "conductance_w_per_k": .025}
                    for c in assembly["thermal_contacts"]]
        surfaces = []
        for uno, shield in scenario["stack_pairs"]:
            reverse = .55 * areas[uno] / areas[shield]
            for owner, other, factor in [(uno, shield, .55), (shield, uno, reverse)]:
                surfaces.append({"id": owner+"-face", "board_id": owner, "node": "board", "area_mm2": areas[owner],
                                 "emissivity": .85, "view_factors": {other+"-face": factor, "ambient": 1-factor}})
        request = {"contract": "spike/multiboard-thermal-request/v1", "assembly": assembly,
                   "board_models": board_models, "contact_models": contacts, "radiation_surfaces": surfaces,
                   "ambient_temperature_c": 25., "mode": "steady_state"}
    write(directory / "thermal-model-input.json", request)
    write(directory / "thermal-assumptions.json", assumptions)
    return request, assumptions


def independent_oracle(request, result):
    """Build heat balance from supplied coefficients without SPIKE kernels."""
    ids = [node["id"] for node in result["nodes"]]
    count = len(ids)
    index = {identifier: i for i, identifier in enumerate(ids)}
    models = request.get("board_models")
    if models:
        elements = [dict(e, id=json.dumps([m["board_id"], e["id"]], separators=(",", ":")))
                    for m in models for e in m["elements"]]
        links = [{"from_id": json.dumps([c["from"]["board_id"], c["from"]["node"]], separators=(",", ":")),
                  "to_id": json.dumps([c["to"]["board_id"], c["to"]["node"]], separators=(",", ":")),
                  "conductance_w_per_k": c["conductance_w_per_k"]} for c in request["contact_models"]]
        if any(m["links"] for m in models):
            raise ValueError("Demonstration oracle expects one uniform node per board.")
    else:
        elements, links = request["thermal_elements"], list(request["thermal_links"])
    links += [{"from_id": e["id"], "to_id": "ambient", "conductance_w_per_k": 1/e["ambient_resistance_c_per_w"]} for e in elements]
    matrix = np.zeros((count, count))
    for link in links:
        a = index[link["from_id"]]
        g = link["conductance_w_per_k"]
        matrix[a, a] += g
        if link["to_id"] != "ambient":
            b = index[link["to_id"]]
            matrix[b, b] += g
            matrix[a, b] -= g
            matrix[b, a] -= g
    powers = np.asarray([element["power_w"] for element in elements])
    surfaces = request.get("radiation_surfaces", [])
    ambient = request.get("ambient_temperature_c", 25)
    if surfaces:
        surface_ids = [surface["id"] for surface in surfaces]
        owner_indices = [index[json.dumps([s["board_id"], s["node"]], separators=(",", ":"))] for s in surfaces]
        area = np.asarray([s["area_mm2"] * 1e-6 for s in surfaces])
        emissivity = np.asarray([s["emissivity"] for s in surfaces])
        factors = np.asarray([[s["view_factors"].get(other, 0) for other in surface_ids] for s in surfaces])
        exterior = np.asarray([s["view_factors"].get("ambient", 0) for s in surfaces])
        radiosity_matrix = np.eye(len(surfaces)) - (1-emissivity)[:, None] * factors
        black_ambient = 5.670374419e-8 * (ambient + 273.15)**4
        reciprocity = float(np.max(np.abs(area[:, None]*factors - area[None, :]*factors.T)))
        closure = float(np.max(np.abs(factors.sum(axis=1) + exterior - 1)))
    else:
        reciprocity, closure = 0., 0.

    def radiation(temperatures):
        heat = np.zeros(count)
        if not surfaces:
            return heat, 0., 0.
        emitted = 5.670374419e-8 * (temperatures[owner_indices] + 273.15)**4
        radiosity = np.linalg.solve(radiosity_matrix, emissivity*emitted + (1-emissivity)*exterior*black_ambient)
        surface_heat = area * (radiosity - factors @ radiosity - exterior * black_ambient)
        np.add.at(heat, owner_indices, surface_heat)
        ambient_heat = float(np.sum(area*exterior*(radiosity-black_ambient)))
        return heat, ambient_heat, float(sum(surface_heat)-ambient_heat)

    capacitance = np.asarray([element["thermal_capacitance_j_per_c"] for element in elements])
    steady = np.asarray([node["steady_temperature_c"] for node in result["nodes"]])
    rad_heat, rad_ambient, rad_residual = radiation(steady)
    residual = powers - matrix @ (steady-ambient) - rad_heat
    reference = solve_ivp(lambda _, t: (powers-matrix @ (t-ambient)-radiation(t)[0])/capacitance,
                          (0., 600.), np.full(count, ambient), rtol=1e-11, atol=1e-12)
    if not reference.success:
        raise RuntimeError(reference.message)
    return {"ids": ids, "matrix": matrix, "powers": powers, "radiation": radiation,
            "capacitance": capacitance, "reference": reference.y[:, -1],
            "checks": {"independent_steady_max_node_residual_w": float(max(abs(residual))),
                       "independent_steady_energy_balance_residual_w": float(sum(residual)),
                       "independent_radiation_ambient_heat_w": rad_ambient,
                       "independent_radiation_closure_residual_w": rad_residual,
                       "view_factor_row_closure": closure,
                       "area_reciprocity_residual_m2": reciprocity}}


def study(directory, request, assumptions):
    multi = "board_models" in request
    method = "run_multiboard_thermal" if multi else "estimate_thermal"
    param = "request" if multi else "scenario"
    steady = execute(directory, "thermal", method, {param: request})
    oracle = independent_oracle(request, steady)
    checks = oracle["checks"]
    finals = []
    transients = []
    peaks = []
    for dt, stem in [(2., "thermal-transient-dt2"), (1., "thermal-transient"), (.5, "thermal-transient-dt0p5")]:
        transient = copy.deepcopy(request)
        transient["mode"] = "transient"
        if multi:
            transient.update(duration_s=600., time_step_s=dt)
        else:
            transient["run"] = {"end_time_s": 600., "write_interval_s": dt, "max_iterations": 2000, "residual_target": 1e-6}
        result = execute(directory, stem, method, {param: transient})
        transients.append(result)
        peaks.append(max(max(frame["temperatures_c"].values()) for frame in result["transient"]))
        final = np.asarray([result["transient"][-1]["temperatures_c"][i] for i in oracle["ids"]])
        finals.append(final)
    errors = [float(max(abs(final-oracle["reference"]))) for final in finals]
    checks["transient_final_max_error_to_adaptive_ode_c"] = dict(zip(["dt2", "dt1", "dt0p5"], errors))
    checks["dt1_vs_dt0p5_final_max_difference_c"] = float(max(abs(finals[1]-finals[2])))
    checks["dt2_vs_dt1_final_max_difference_c"] = float(max(abs(finals[0]-finals[1])))
    checks["transient_peak_temperatures_c"] = dict(zip(["dt2", "dt1", "dt0p5"], peaks))
    checks["dt1_vs_dt0p5_peak_difference_c"] = abs(peaks[1]-peaks[2])
    main = transients[1]
    max_balance = 0.
    for previous, current in zip(main["transient"], main["transient"][1:]):
        p = np.asarray([previous["temperatures_c"][i] for i in oracle["ids"]])
        t = np.asarray([current["temperatures_c"][i] for i in oracle["ids"]])
        storage = oracle["capacitance"] * (t-p) / (current["time_s"]-previous["time_s"])
        residual = oracle["powers"] - storage - oracle["matrix"] @ (t-25.) - oracle["radiation"](t)[0]
        max_balance = max(max_balance, float(max(abs(residual))))
    checks["independent_transient_max_node_balance_residual_w"] = max_balance
    if multi:
        linear = copy.deepcopy(request)
        linear.pop("radiation_surfaces", None)
        result = execute(directory, "thermal-radiation-off", method, {param: linear})
        expected = 25. + np.linalg.solve(oracle["matrix"], oracle["powers"])
        observed = np.asarray([n["steady_temperature_c"] for n in result["nodes"]])
        checks["radiation_off_numpy_max_difference_c"] = float(max(abs(expected-observed)))
    checks["passed"] = bool(max(abs(checks[k]) for k in ["independent_steady_max_node_residual_w", "independent_steady_energy_balance_residual_w", "independent_radiation_closure_residual_w", "independent_transient_max_node_balance_residual_w"]) < 1e-7
                             and errors[2] < errors[1] < errors[0]
                             and checks["dt1_vs_dt0p5_final_max_difference_c"] <= .1
                             and checks["dt1_vs_dt0p5_peak_difference_c"] <= .1
                             and checks.get("radiation_off_numpy_max_difference_c", 0) < 1e-8
                             and checks["view_factor_row_closure"] < 1e-10
                             and checks["area_reciprocity_residual_m2"] < 1e-12)
    validation = {"model_status": "approximate", "production_qualified": False,
                  "assumptions": assumptions, "validation": checks,
                  "validation_limits": {"energy_balance_w": 1e-7, "peak_and_final_refinement_c": .1,
                                        "radiation_off_linear_solution_c": 1e-8,
                                        "view_factor_row_closure": 1e-10, "area_reciprocity_m2": 1e-12},
                  "steady_temperatures_c": {i: n["steady_temperature_c"] for i, n in zip(oracle["ids"], steady["nodes"])},
                  "final_600s_temperatures_c": dict(zip(oracle["ids"], finals[1].tolist())),
                  "adaptive_ode_final_600s_temperatures_c": dict(zip(oracle["ids"], oracle["reference"].tolist())),
                  "inputs_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.json") if p.name in {"assembly.json", "pi-result.json", "designs.json"}}}
    write(directory / "thermal-validation.json", validation)
    if not checks["passed"]:
        raise RuntimeError(f"Thermal validation failed: {checks}")
    print(json.dumps({"scenario": directory.name, "thermal_status": steady["status"], "validation": checks}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    request, assumptions = build_model(args.directory)
    study(args.directory, request, assumptions)


if __name__ == "__main__":
    main()
