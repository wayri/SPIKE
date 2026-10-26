# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Source-development AC resistor/solid/fluid analytical refinement benchmark.

Uses independently authored test mesh generators; not a packaged application.
Predeclared: each refinement order >=0.8 and finest relative rise L2 <=0.05,
plus all unchanged AC, mass, mixed-residual and cell/global energy gates.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from python.spike_core.solvers.execution.coupling.em_network_resistor_cht import run_em_network_resistor_cht
from tests.python.test_em_network_resistor_cht import request

OWNERS = (
    "scripts/benchmark_em_network_cht.py", "python/spike_core/solvers/execution/coupling/em_network_resistor_cht.py",
    "python/spike_core/solvers/execution/coupling/em_network_ac.py", "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_cht.py",
    "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_mesh.py", "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_stokes.py",
    "python/spike_core/solvers/thermal_fluid/flow/cfd_tetra_energy.py", "tests/python/test_em_network_resistor_cht.py",
    "tests/python/test_cfd_tetra_cht.py", "tests/python/test_em_network_cosimulation.py",
)


def run_level(n, *, flowing=False):
    raw, geometry = request(n, flowing=flowing)
    # Independent source and continuum interface solution, not generated from
    # the discrete operator. The optional exact shear is tangent to grad(T).
    power = 50.*(20./100.)**2
    q, a, ks, kf = power/.5, .5, 2., 1.
    slope = q*(a*a/(2*ks) + a*(1-a)/kf)/(a+ks*(1-a)/kf)
    right_slope = (ks*slope-q*a)/kf
    boundaries = raw["cht_request"]["energy"]["boundaries"]
    for name in boundaries:
        boundaries[name] = ({"type": "temperature", "temperature_k": 300.}
                            if name in ("xmin", "xmax") else
                            {"type": "heat_flux", "outward_heat_flux_w_m2": 0.})
        if flowing and name not in ("xmin", "xmax"):
            x = geometry["vertices"][np.asarray(raw["cht_request"]["mesh"]["boundary_patches"][name]), 0]
            mean = np.mean(x, axis=1)
            second = (np.sum(x*x, axis=1)+np.sum(x, axis=1)**2)/12.
            rise = np.where(mean < a, slope*mean-q*second/(2*ks), right_slope*(mean-1.))
            boundaries[name]["inflow_temperature_k"] = (300.+rise).tolist()
    started = time.perf_counter()
    result = run_em_network_resistor_cht(raw)
    elapsed = time.perf_counter()-started
    # Independently: source 20 V RMS, external 50 ohm, matched 50 ohm
    # network. Only the external resistor's 2 W enters the half-volume solid.
    x = geometry["vertices"][geometry["cells"], 0]
    mean = np.mean(x, axis=1)
    second_moment = (np.sum(x*x, axis=1)+np.sum(x, axis=1)**2)/20.
    exact_rise = np.where(mean < a, slope*mean-q*second_moment/(2*ks), right_slope*(mean-1.))
    actual = np.asarray(result["cht"]["fields"]["energy"]["temperature_rise_k"])
    volumes = geometry["cell_volumes"]
    relative = math.sqrt(float(np.sum(volumes*(actual-exact_rise)**2)/np.sum(volumes*exact_rise**2)))
    maximum_mass_flow = max(abs(v) for v in result["cht"]["fields"]["face_mass_flow_kg_s"])
    if flowing and maximum_mass_flow <= 0.:
        raise RuntimeError("Flowing analytical case requires actual nonzero solved mass flux")
    return raw, result, {"n": n, "cells": len(volumes), "relative_rise_l2_error": relative,
                         "maximum_face_mass_flow_kg_s": maximum_mass_flow,
                         "elapsed_seconds": elapsed, "expected_deposited_w": power,
                         "actual_deposited_w": result["deposited_series_resistor_power_w"],
                         "energy": result["cht"]["diagnostics"]["energy"]}


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False)+"\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    hashes = {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in OWNERS}
    families = {}
    for name, flowing in (("conduction_limit", False), ("tangential_shear", True)):
        rows = []
        for level in (1, 2, 4):
            raw, result, row = run_level(level, flowing=flowing)
            write_json(args.output/f"request-{name}-n{level}.json", raw)
            write_json(args.output/f"result-{name}-n{level}.json", result)
            rows.append(row)
        orders = [math.log(a["relative_rise_l2_error"]/b["relative_rise_l2_error"], 2.)
                  for a, b in zip(rows, rows[1:])]
        families[name] = {"levels": rows, "observed_orders": orders,
                          "passed": min(orders) >= .8 and rows[-1]["relative_rise_l2_error"] <= .05}
    unchanged = hashes == {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in OWNERS}
    passed = unchanged and all(family["passed"] for family in families.values())
    artifacts = {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(args.output.iterdir())}
    report = {"status": "passed" if passed else "failed", "source_sha256": hashes,
              "sources_unchanged": unchanged, "artifacts_sha256": artifacts,
              "families": families,
              "gates": {"minimum_order": .8, "maximum_finest_relative_rise_l2": .05},
              "production_qualified": False,
              "scope": "Synthetic AC resistor -> layered steady conduction and analytically tangent creeping shear"}
    write_json(args.output/"report.json", report)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
