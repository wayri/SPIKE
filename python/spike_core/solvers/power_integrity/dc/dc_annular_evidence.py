# SPDX-License-Identifier: Apache-2.0
"""Independent retained-field witnesses; no second field or circuit solve."""
from __future__ import annotations
from copy import deepcopy
import math
import numpy as np
from numpy.polynomial.legendre import leggauss
from .dc_annular_land_input import prepare, require
from .dc_land_transition_evidence import close


def validate_annular_result(result):
    require(result.get("contract") == "spike/dc-annular-land-result/v1"
            and result.get("model_status") == "experimental"
            and result.get("production_qualified") is False
            and result.get("complete_board_physical_volume") is False, "Annular field scope differs")
    data = prepare(result["source_request"])
    require(result["input_digest"] == data["digest"], "Annular input identity differs")
    trace = np.asarray(result["face_potential_v"], dtype=float)
    require(trace.shape == (data["face_count"],) and np.isfinite(trace).all() and trace[0] == 0,
            "Annular trace/gauge differs")
    require(len(result["cells"]) == len(data["cells"]), "Annular cell support differs")
    assembled = np.zeros(data["face_count"]); powers, volumes = [], []
    nodes, weights = leggauss(32)
    for n, (cell, (i, j)) in enumerate(zip(result["cells"], data["cells"])):
        require(cell["id"] == f"cell:{n}" and cell["face_ids"] == data["faces"][n].tolist()
                and cell["radial_bounds_mm"] == data["rmm"][i:i+2].tolist()
                and cell["axial_bounds_mm"] == data["zmm"][j:j+2].tolist(), "Annular cell identity differs")
        q = np.asarray(cell["outward_face_current_a"], dtype=float)
        require(q.shape == (4,) and np.isfinite(q).all(), "Annular flux shape differs")
        require(abs(math.fsum(q)) <= 1e-9*data["current_scale"], "Annular cell KCL differs")
        np.add.at(assembled, data["faces"][n], q)
        r0, dr, dz = data["radius"][i], data["dr"][i], data["dz"][j]
        area = math.pi*dr*(2*r0+dr); volume = area*dz
        # Integrate the physical vector field and each test flux basis directly.
        # This uses 32 radial nodes, independent of the kernel's 16-node mass.
        r = r0+dr*(nodes+1)/2
        s = (r-r0)*(r+r0)/(dr*(2*r0+dr))
        basis = np.column_stack((-(1-s), s))/(2*math.pi*r[:, None]*dz)
        jr = basis@q[:2]
        dv = weights*(dr/2)*2*math.pi*r*dz
        moment = np.empty(4)
        moment[:2] = np.einsum("q,qi,q->i", dv, basis, jr)/data["sigma"]
        z = (nodes+1)/2
        axial_basis = np.column_stack((-(1-z), z))/area
        jz = axial_basis@q[2:]
        dvz = weights*volume/2
        moment[2:] = np.einsum("q,qi,q->i", dvz, axial_basis, jz)/data["sigma"]
        power = float((dv@(jr*jr)+dvz@(jz*jz))/data["sigma"])
        require(math.isfinite(power) and (not np.any(q) or power > 0), "Annular retained heat underflowed")
        local = trace[data["faces"][n]]; mean = float(cell["mean_potential_v"])
        require(math.isfinite(mean), "Annular mean potential differs")
        scale = max(float(np.max(np.abs(moment))), float(np.max(np.abs(local))), abs(mean))
        if scale:
            require(np.linalg.norm(moment/scale+local/scale-mean/scale)
                    <= 1e-9*max(np.linalg.norm(moment/scale), np.linalg.norm(local/scale), abs(mean/scale)),
                    "Annular local Ohmic weak law differs")
        rc = r0+dr/2; sc = (rc-r0)*(rc+r0)/(dr*(2*r0+dr))
        center = [(-q[0]*(1-sc)+q[1]*sc)/(2*math.pi*rc*dz), (-q[2]+q[3])/(2*area)]
        for key, value in (("volume_m3", volume), ("joule_heat_w", power),
                           ("mean_joule_density_w_m3", power/volume), ("center_density_rz_a_m2", center),
                           ("radial_current_numerator_endpoint_a", [-q[0], q[1]]),
                           ("axial_component_endpoint_density_a_m2", [-q[2]/area, q[3]/area])):
            close(cell[key], value, "annular "+key)
        powers.append(power); volumes.append(volume)
    require(np.max(np.abs(assembled-data["prescribed"])) <= 1e-9*data["current_scale"],
            "Annular shared/boundary/gauge flux differs")
    require(len(result["contacts"]) == len(data["patches"]), "Annular patch count differs")
    works = []
    for contact, patch in zip(result["contacts"], data["patches"]):
        for key in ("id", "attachment_id", "face", "interval_mm", "face_ids"):
            require(contact[key] == patch[key], "Annular patch identity differs")
        require(contact["patch_relative_accuracy_certified"] is False, "Unsupported annular accuracy claim")
        voltage = float(np.dot(trace[patch["face_ids"]], np.asarray(patch["face_areas_m2"])/patch["area_m2"]))
        recovered = -math.fsum(assembled[patch["face_ids"]])
        for key, value in (("area_m2", patch["area_m2"]), ("inward_current_a", patch["current_a"]),
                           ("recovered_inward_current_a", recovered),
                           ("absolute_current_recovery_error_a", abs(recovered-patch["current_a"])),
                           ("global_face_residual_tolerance_a", 1e-9*data["current_scale"]),
                           ("mean_potential_v", voltage), ("signed_terminal_work_w", patch["current_a"]*voltage)):
            close(contact[key], value, "annular "+key)
        works.append(patch["current_a"]*voltage)
    close(result["total_volume_m3"], math.fsum(volumes), "annular total volume")
    close(result["joule_heat_w"], math.fsum(powers), "annular total heat")
    close(result["signed_terminal_work_w"], math.fsum(works), "annular work")
    require(data["current_scale"] == 0 or math.fsum(powers) > 0 and math.fsum(works) > 0,
            "Nonzero annular drive has zero retained work")
    close(math.fsum(powers), math.fsum(works), "annular field work balance")


def validate_annular_stack(result):
    from .dc_annular_stack_input import prepare as prepare_stack
    require(result.get("contract") == "spike/dc-annular-stack-result/v1"
            and result.get("model_status") == "experimental" and result.get("production_qualified") is False
            and result.get("complete_board_physical_volume") is False
            and result.get("ownership_currents_reused") is False, "Annular stack scope differs")
    data = prepare_stack(result["source_request"])
    require(result["input_digest"] == data["digest"] and len(result["lands"]) == len(data["lands"])
            and len(result["edges"]) == len(data["edges"]), "Annular stack support differs")
    require(len(result["response_field_results"]) == len(data["lands"])
            and len(result["reduced_responses_ohm"]) == len(data["lands"]), "Annular response support differs")
    currents, potentials = [], []
    for b, (record, master) in enumerate(zip(result["lands"], data["lands"])):
        n = len(master["contacts"]); columns = []
        require(len(result["response_field_results"][b]) == n-1, "Annular response column count differs")
        for p, unit in enumerate(result["response_field_results"][b]):
            expected_unit = deepcopy(master)
            for k, c in enumerate(expected_unit["contacts"]):
                c["current_a"] = 1. if k == p else -1. if k == n-1 else 0.
            require(unit["source_request"] == expected_unit, "Annular unit response detached")
            validate_annular_result(unit)
            v = np.array([c["mean_potential_v"] for c in unit["contacts"]])
            columns.append(v[:-1]-v[-1])
        z = np.column_stack(columns)
        close(result["reduced_responses_ohm"][b], z, "annular reduced response")
        require(record["land_id"] == data["names"][b], "Annular stack land identity differs")
        field = record["field_result"]; validate_annular_result(field)
        actual = [c["inward_current_a"] for c in field["contacts"]]
        expected_request = deepcopy(master)
        for c, current in zip(expected_request["contacts"], actual):
            c["current_a"] = current
        require(field["source_request"] == expected_request, "Annular stack child input detached")
        shift = float(record["gauge_shift_v"]); require(math.isfinite(shift), "Nonfinite stack gauge")
        voltage = np.array([c["mean_potential_v"] for c in field["contacts"]])+shift
        close(record["global_port_potentials_v"], voltage, "global annular potentials")
        close(voltage[:-1]-voltage[-1], z@np.asarray(actual[:-1]), "annular current response")
        currents.append(np.asarray(actual)); potentials.append(voltage)
    residuals = [np.array(s, dtype=float)-c for s, c in zip(data["external"], currents)]
    heat_by_kind = {"physical_barrel": [], "supplied_resistor": []}
    for edge, model, meta in zip(result["edges"], data["edges"], data["metadata"]):
        for key, value in {**model, **meta}.items():
            require(edge[key] == value, "Annular edge source/geometry differs")
        p, n = model["p"], model["n"]; current = float(edge["current_a"])
        require(math.isfinite(current), "Nonfinite annular edge current")
        residuals[p[0]][p[1]] -= current; residuals[n[0]][n[1]] += current
        voltage = float(potentials[p[0]][p[1]]-potentials[n[0]][n[1]])
        scale = abs(potentials[p[0]][p[1]])+abs(potentials[n[0]][n[1]])+abs(current*model["resistance_ohm"])
        require(abs(voltage-current*model["resistance_ohm"]) <= 1e-8*scale, "Annular physical edge KVL differs")
        close(edge["voltage_drop_v"], voltage, "annular edge voltage")
        heat = current*current*model["resistance_ohm"]
        require(current == 0 or heat > 0, "Annular retained edge heat underflowed")
        close(edge["heat_w"], heat, "annular edge heat"); heat_by_kind[meta["kind"]].append(heat)
        if meta["kind"] == "physical_barrel":
            geometry = meta["geometry"]
            ri, ro = geometry["inner_radius_mm"]*1e-3, geometry["outer_radius_mm"]*1e-3
            area = math.pi*(ro-ri)*(ro+ri)
            length = abs(geometry["end_mm"][2]-geometry["start_mm"][2])*1e-3
            direction = 1 if geometry["end_mm"][2] > geometry["start_mm"][2] else -1
            close(model["resistance_ohm"], length/(geometry["conductivity_s_m"]*area), "barrel physical resistance")
            close(edge["volume_m3"], area*length, "barrel owned volume")
            close(edge["current_density_a_m2"], [0., 0., direction*current/area], "actual barrel vector field")
            close(edge["mean_joule_density_w_m3"], heat/(area*length), "actual barrel heat density")
    scale = math.fsum(abs(v) for s in data["external"] for v in s)+math.fsum(abs(e["current_a"]) for e in result["edges"])
    require(max(float(np.max(np.abs(r))) for r in residuals) <= 1e-8*scale, "Annular per-port KCL differs")
    land_heat = math.fsum(r["field_result"]["joule_heat_w"] for r in result["lands"])
    barrel_heat = math.fsum(heat_by_kind["physical_barrel"]); resistor_heat = math.fsum(heat_by_kind["supplied_resistor"])
    work = math.fsum(float(np.asarray(s)@v) for s, v in zip(data["external"], potentials))
    for key, value in (("land_heat_w", land_heat), ("barrel_heat_w", barrel_heat), ("resistor_heat_w", resistor_heat),
                       ("source_work_w", work), ("total_heat_w", land_heat+barrel_heat+resistor_heat)):
        close(result[key], value, "stack "+key)
    close(work, land_heat+barrel_heat+resistor_heat, "stack physical work")
    circuit = result["circuit"]
    for b, (current, voltage) in enumerate(zip(currents, potentials)):
        close(circuit["body_currents_a"][b], current, "circuit currents")
        close(circuit["body_port_potentials_v"][b], voltage, "circuit potentials")
        close(circuit["body_heat_w"][b], result["lands"][b]["field_result"]["joule_heat_w"], "circuit land heat")
        close(circuit["body_gauge_v"][b], voltage[-1], "circuit body gauge")
    close(circuit["edge_current_a"], [e["current_a"] for e in result["edges"]], "circuit edge currents")
    close(circuit["edge_heat_w"], [e["heat_w"] for e in result["edges"]], "circuit edge heat")
    close(circuit["source_work_w"], work, "circuit work")
    close(circuit["total_heat_w"], result["total_heat_w"], "circuit heat")
