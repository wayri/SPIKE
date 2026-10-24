# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Actual one-way AC/heat/stress slab ladder; synthetic, not board qualification."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from examples.pdn_dielectric_thermal.run_slab import setup as electrothermal_setup
from python.spike_core.pdn_dielectric_thermomechanical import REQUEST_CONTRACT, run_pdn_dielectric_thermomechanical

SOURCES = ["python/spike_core/"+name+".py" for name in (
    "pdn_dielectric_thermomechanical", "pdn_dielectric_thermal", "pdn_dielectric_ac",
    "assembly_tetra_thermal", "assembly_tetra_thermal_validation", "assembly_tetra_radiation",
    "assembly_tetra_structural")]+[
        "examples/pdn_dielectric_thermal/run_slab.py", "examples/pdn_dielectric_thermomechanical/run_slab.py"]


def hashes():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}


def setup(n):
    electrothermal = electrothermal_setup(n)
    mesh = deepcopy(electrothermal["electrical_request"]["mesh"])
    structural = {
        "contract": "spike/assembly-tetra-structural-request/v1", "mesh": mesh,
        "context_digest": electrothermal["electrical_request"]["context_digest"],
        "materials": [{"id": "bulk", "young_modulus_pa": 2e9, "poisson_ratio": .25,
                       "thermal_expansion_per_k": 1e-5, "reference_temperature_k": 300.}],
        "nodal_temperatures_k": None, "nodal_forces_n": {},
        "dirichlet": [{"node_id": i, "component": axis, "displacement_m": 0.}
                      for i in range(len(mesh["vertices"])) for axis in "xyz"],
    }
    return {"contract": REQUEST_CONTRACT, "electrothermal_request": electrothermal,
            "structural_request": structural}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"build/dielectric-thermomechanical-20261023")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    before, rows = hashes(), []
    for n in (1, 2, 4):
        request = setup(n)
        result = run_pdn_dielectric_thermomechanical(request)
        electric = request["electrothermal_request"]["electrical_request"]
        # Independent one-metre slab: E_rms=10 V/m, q=(sigma+w*epsilon*tan_delta)*E².
        q = (.5+2*math.pi*1000*1e-6*.05)*100
        actual_power = result["electrothermal"]["total_dielectric_power_w"]
        if abs(actual_power-q) > 1e-9*q:
            raise RuntimeError("Independent plate power gate failed")
        xyz = np.asarray(electric["mesh"]["vertices"])
        temperatures = np.asarray(result["electrothermal"]["thermal_result"]["node_temperatures_k"])
        error, exact_energy = 0., 0.
        for cell, stress in zip(electric["mesh"]["cells"], result["structural"]["cells"]):
            ids = cell["vertices"]; points = xyz[ids]
            volume = abs(np.linalg.det((points[1:]-points[0]).T))/6
            x = points[:, 0].mean()
            error += volume*(temperatures[ids].mean()-(300+q*x*(1-x)/2))**2
            eigenstrain = 1e-5*(temperatures[ids].mean()-300)
            expected_pressure = -4e9*eigenstrain
            np.testing.assert_allclose(stress["stress_pa"], [expected_pressure]*3+[0.]*3, atol=1e-7)
            exact_energy += -1.5*volume*expected_pressure*eigenstrain
        np.testing.assert_allclose(result["structural"]["elastic_energy_j"], exact_energy, rtol=1e-10, atol=1e-14)
        prefix = args.output/f"n{n}"
        write(prefix.with_suffix(".request.json"), request)
        write(prefix.with_suffix(".result.json"), result)
        rows.append({"n": n, "cells": len(electric["mesh"]["cells"]), "power_w": actual_power,
                     "peak_temperature_k": float(temperatures.max()), "temperature_centroid_l2_k": math.sqrt(error),
                     "elastic_energy_j": result["structural"]["elastic_energy_j"]})
    slopes = [math.log(a["temperature_centroid_l2_k"]/b["temperature_centroid_l2_k"], 2)
              for a, b in zip(rows, rows[1:])]
    if min(slopes) < 1.7 or hashes() != before:
        raise RuntimeError("Refinement or source-stability gate failed")
    artifacts = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(args.output.glob("*.json"))}
    report = {"status": "passed", "production_qualified": False, "source_sha256": before,
              "artifact_sha256": artifacts, "temperature_refinement_slopes": slopes, "runs": rows,
              "scope": "Synthetic fully clamped slab; no measured-board, general SI or deformation feedback qualification"}
    write(args.output/"report.json", report)
    print(json.dumps({"report": str(args.output/"report.json"), "slopes": slopes, "runs": rows}))


if __name__ == "__main__":
    main()
