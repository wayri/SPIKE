# SPDX-License-Identifier: Apache-2.0
"""Fresh coupled annular-land/barrel/current-driven passive DC solve."""
from __future__ import annotations
from copy import deepcopy
import math
import numpy as np

from .dc_annular_land import solve_annular_land
from .dc_annular_stack_input import prepare
from .dc_port_circuit import solve_port_circuit, require


def _currents(request, values):
    request = deepcopy(request)
    for patch, current in zip(request["contacts"], values):
        patch["current_a"] = float(current)
    return request


def solve_annular_stack(request, *, cancelled=None):
    """Source bindings are digest/geometry checked here; use source wrapper for IO authentication."""
    data = prepare(request)
    require(cancelled is None or callable(cancelled), "Cancellation must be callable")

    def check():
        require(cancelled is None or not cancelled(), "Annular stack cancelled between bounded field solves")

    responses, response_fields = [], []
    for land in data["lands"]:
        n = len(land["contacts"]); columns, unit_fields = [], []
        for p in range(n-1):
            check(); currents = np.zeros(n); currents[p] = 1.; currents[-1] = -1.
            result = solve_annular_land(_currents(land, currents))
            voltage = np.array([c["mean_potential_v"] for c in result["contacts"]])
            columns.append(voltage[:-1]-voltage[-1])
            unit_fields.append(result)
        responses.append(np.column_stack(columns))
        response_fields.append(unit_fields)
    check()
    network = solve_port_circuit(responses, data["edges"], data["external"])
    results, potentials = [], []
    for b, land in enumerate(data["lands"]):
        check()
        result = solve_annular_land(_currents(land, network["body_currents_a"][b]))
        v = np.array([c["mean_potential_v"] for c in result["contacts"]])
        predicted = np.asarray(network["body_port_potentials_v"][b])
        actual_difference, expected_difference = v-v[-1], predicted-predicted[-1]
        scale = max(np.linalg.norm(actual_difference), np.linalg.norm(expected_difference))
        require(np.linalg.norm(actual_difference-expected_difference) <= 1e-8*scale, "Fresh field voltage differs from reduced response")
        shift = float(predicted[-1]-v[-1]); global_v = v+shift
        potentials.append(global_v)
        results.append({"land_id": data["names"][b], "gauge_shift_v": shift,
                        "global_port_potentials_v": global_v.tolist(), "field_result": result})
    edge_rows = []
    for k, (edge, meta) in enumerate(zip(data["edges"], data["metadata"])):
        p, n = edge["p"], edge["n"]
        drop = float(potentials[p[0]][p[1]]-potentials[n[0]][n[1]])
        current = network["edge_current_a"][k]; expected = current*edge["resistance_ohm"]
        operands = abs(potentials[p[0]][p[1]])+abs(potentials[n[0]][n[1]])+abs(expected)
        require(abs(drop-expected) <= 1e-8*operands, "Fresh field/barrel KVL failed")
        row = {**deepcopy(meta), "p": list(p), "n": list(n), "resistance_ohm": edge["resistance_ohm"],
            "current_a": current, "heat_w": network["edge_heat_w"][k], "voltage_drop_v": drop}
        if meta["kind"] == "physical_barrel":
            geometry = meta["geometry"]
            direction = 1 if geometry["end_mm"][2] > geometry["start_mm"][2] else -1
            volume = geometry["volume_mm3"]*1e-9
            density = direction*current/(geometry["face_contact_area_mm2"]*1e-6)
            heat_density = row["heat_w"]/volume
            require(math.isfinite(density) and math.isfinite(heat_density), "Actual barrel field overflowed")
            row.update({"current_density_a_m2": [0., 0., density], "volume_m3": volume,
                        "mean_joule_density_w_m3": heat_density})
        edge_rows.append(row)
    land_heat = math.fsum(r["field_result"]["joule_heat_w"] for r in results)
    barrel_heat = math.fsum(e["heat_w"] for e in edge_rows if e["kind"] == "physical_barrel")
    resistor_heat = math.fsum(e["heat_w"] for e in edge_rows if e["kind"] == "supplied_resistor")
    work = math.fsum(float(np.asarray(s)@v) for s, v in zip(data["external"], potentials))
    total = land_heat+barrel_heat+resistor_heat
    require(math.isfinite(work) and abs(work-total) <= 1e-8*max(abs(work), total), "Fresh field/circuit source-work balance failed")
    check()
    return {"contract": "spike/dc-annular-stack-result/v1", "model_status": "experimental",
        "production_qualified": False, "complete_board_physical_volume": False,
        "source_request": deepcopy(request), "input_digest": data["digest"], "lands": results, "edges": edge_rows,
        "reduced_responses_ohm": [r.tolist() for r in responses], "response_field_results": response_fields, "circuit": network,
        "land_heat_w": land_heat, "barrel_heat_w": barrel_heat, "resistor_heat_w": resistor_heat,
        "total_heat_w": total, "source_work_w": work, "ownership_currents_reused": False,
        "source_binding_status": "supplied_digest_and_geometry_checked_use_source_wrapper_for_file_authentication",
        "limitations": ["One explicitly supplied coaxial stack and full-azimuth annular bands only.",
            "Finite current-driven Neumann patches, not equipotential electrodes; current recovery uses global absolute bounds.",
            "Native source binding authenticates isolated pad dimensions, not surrounding board copper or electrode choice.",
            "DC only; no full-board density/AC, angular crowding, nonlinear circuit, inferred thermal mapping or release qualification."]}
