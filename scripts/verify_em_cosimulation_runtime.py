# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Execute bounded owned AC/circuit-heat routes in a source or frozen worker.

The synthetic one-port and tetrahedron are independently authored packaging
oracles, not measured EM evidence or a fresh EMerge field solve.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def probe_inputs():
    result = {"contract": "spike/v1", "analysis_id": "release-cosim-probe", "status": "completed_with_warnings",
        "mode": "emerge-si", "model_status": "unvalidated", "summary": {}, "fields": {}, "probes": [],
        "networks": {"s_parameters": {"frequencies_hz": [1e6], "ports": ["p0"],
            "reference_impedance_ohm": 50., "values": [[[[0., 0.]]]]}},
        "issues": [{"code": "SYNTHETIC_REFERENCE", "severity": "warning", "message": "Packaging oracle, not field evidence"}],
        "provenance": {"solver": "EMerge/packaging-reference", "design_id": "reference",
            "design_digest_sha256": "a"*64, "board_case_sha256": "b"*64, "generated_script_sha256": "c"*64}}
    return {"result": result, "binding": {"design_id": "reference", "digest_sha256": "a"*64},
        "expected_case_sha256": "b"*64, "expected_script_sha256": "c"*64,
        "port_bindings": {"p0": {"positive_node": "signal", "negative_node": "0", "reference_plane": "declared-reference"}},
        "wave_convention": "rms_power_waves_common_positive_real_reference"}


def verify_em_cosimulation_runtime(executable, request):
    packet = request(executable, "prepare_emerge_cosimulation_source", {"request": probe_inputs()})["result"]
    if (packet.get("model_status") != "unvalidated" or packet.get("production_qualified") is not False
            or packet.get("source_issues") != probe_inputs()["result"]["issues"]):
        raise RuntimeError("Co-simulation preparation dropped source status/diagnostics")
    ac = {"contract": "spike/em-network-ac-request/v1", "source": packet["network_source"],
        "wave_convention": packet["wave_convention"], "boundaries": [{"p0": {
            "voltage_v": [2., 0.], "impedance_ohm": [50., 0.]}}]}
    solved = request(executable, "solve_em_network_ac", {"request": ac})["result"]
    sample = solved["samples"][0]
    for actual, expected in ((sample["voltage_rms_v"][0][0], 1.),
                             (sample["current_into_network_rms_a"][0][0], .02),
                             (sample["series_resistor_power_w"][0], .02)):
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15):
            raise RuntimeError("Packaged AC differs from independent matched-resistor oracle")
    mesh = {"contract": "spike/solver-mesh/v1", "units": "m", "coordinate_system": "right_handed_xyz",
        "vertices": [[0,0,0], [1,0,0], [0,1,0], [0,0,1]],
        "cells": [{"id": "r", "kind": "tetrahedron", "vertices": [0,1,2,3],
                   "material_id": "k", "source_object_ids": ["resistor"]}],
        "counts": {"vertices": 4, "cells": 1}, "object_map": {"resistor": {"kind": "solid"}}}
    heat = {"contract": "spike/assembly-tetra-thermal-request/v1", "mesh": mesh,
        "materials": [{"id": "k", "thermal_conductivity_w_mk": 2.}],
        "boundaries": [{"id": "fixed", "vertices": [0,2,3], "type": "temperature", "temperature_k": 300.}]}
    coupled = request(executable, "run_em_network_resistor_thermal", {"request": {
        "contract": "spike/em-network-resistor-thermal-request/v1", "ac_request": ac,
        "thermal_request": heat, "sample_index": 0, "resistor_cell_weights": {"p0": {"r": 1.}}}})["result"]
    # Vtet=1/6 m3, Kfree=2/6 W/K, free nodal load=P/4=.005 W.
    if not math.isclose(coupled["thermal"]["node_temperatures_k"][1], 300.015, abs_tol=1e-10, rel_tol=0):
        raise RuntimeError("Packaged thermal field differs from independent discrete-element oracle")
    if not math.isclose(coupled["deposited_series_resistor_power_w"], .02, rel_tol=1e-12):
        raise RuntimeError("Packaged resistor heat mapping failed")
    # Reuse the independently authored retained fluid/solid packaging mesh.
    # The circuit resistor is in cell 1 (solid), never the fluid or EM body.
    from scripts.verify_tetra_cht_runtime import probe_request
    cht_request = probe_request()
    cht = request(executable, "run_em_network_resistor_cht", {"request": {
        "contract": "spike/em-network-resistor-cht-request/v1", "ac_request": ac,
        "cht_request": cht_request, "sample_index": 0,
        "resistor_cell_weights": {"p0": {"1": 1.}}}})["result"]
    if (cht.get("production_qualified") is not False or cht["cht"].get("status") != "completed"
            or not math.isclose(cht["deposited_series_resistor_power_w"], .02, rel_tol=1e-12)
            or not math.isclose(cht["unclassified_em_network_power_w"], .02, rel_tol=1e-12)
            or cht["cell_power_w"][0] != 0.
            or not math.isclose(cht["cell_power_w"][1], .02, rel_tol=1e-12)
            or cht["outside_series_resistor_power_w"] != 0.):
        raise RuntimeError("Packaged AC/CHT explicit solid heating or loss classification failed")
    energy = cht["cht"]["diagnostics"]["energy"]
    if (not math.isclose(energy["generated_heat_w"], .02, rel_tol=1e-12)
            or energy["cell_energy_relative_defect"] > 1e-9
            or energy["global_energy_relative_defect"] > 1e-9
            or not max(abs(value) for value in cht["cht"]["fields"]["face_mass_flow_kg_s"]) > 0.
            or max(cht["cht"]["fields"]["energy"]["temperature_k"]) <= 310.):
        raise RuntimeError("Packaged AC/CHT heat, nonzero solved flow or conservation oracle failed")
    spice_request = {"contract": "spike/em-spice-coupling-request/v1",
        "source": packet["network_source"], "wave_convention": packet["wave_convention"],
        "port_bindings": packet["port_bindings"],
        "circuit": {"ground_node": "0", "elements": [
            {"id": "V1", "type": "voltage_source", "positive_node": "src",
             "negative_node": "0", "phasor": [2., 0.]},
            {"id": "R1", "type": "resistor", "positive_node": "src",
             "negative_node": "signal", "value": 25.}]}}
    spice = request(executable, "run_em_spice_coupling", {"request": spice_request})["result"]
    if (not math.isclose(spice["samples"][0]["voltage_rms_v"][0][0], 4/3, rel_tol=1e-11)
            or spice["provenance"]["native_execution_count"] != 1
            or spice["provenance"]["library_origin"] != "release_owned"):
        raise RuntimeError("Packaged owned-SPICE divider execution failed")
    if any(item.get("production_qualified") is not False for item in (packet, solved, coupled, cht, spice)):
        raise RuntimeError("Experimental co-simulation was incorrectly promoted")
    return {"status": "passed", "production_qualified": False,
        "methods": ["prepare_emerge_cosimulation_source", "solve_em_network_ac", "run_em_network_resistor_thermal", "run_em_network_resistor_cht", "run_em_spice_coupling"],
        "cht_resistor_heat_w": cht["deposited_series_resistor_power_w"],
        "cht_cell_energy_relative_defect": energy["cell_energy_relative_defect"],
        "resistor_heat_w": coupled["deposited_series_resistor_power_w"],
        "free_node_temperature_k": coupled["thermal"]["node_temperatures_k"][1],
        "scope": "Synthetic packaging oracles with actual owned linear SPICE; no fresh EMerge or measured EM"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    def request(executable, method, params):
        command = [str(executable)] if executable else [sys.executable, "-m", "python.spike_core.service"]
        run = subprocess.run(command, input=json.dumps({"id": "cosim-probe", "method": method, "params": params})+"\n",
            text=True, capture_output=True, cwd=ROOT, timeout=120, check=True)
        response = json.loads(run.stdout)
        if response.get("ok") is not True:
            raise RuntimeError(str(response))
        return response
    report = verify_em_cosimulation_runtime(args.worker, request)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
