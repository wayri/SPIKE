# SPDX-License-Identifier: Apache-2.0
"""Admit raw land fields by local constitutive, flux and work witnesses."""
from __future__ import annotations
import math
import numpy as np
from .dc_land_transition_input import prepare, require


def close(actual, expected, name):
    actual, expected = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
    require(actual.shape == expected.shape and np.isfinite(actual).all() and np.isfinite(expected).all(),
            "Land result witness differs: "+name)
    scale = max(float(np.max(np.abs(actual))), float(np.max(np.abs(expected))))
    if scale:
        a, b = actual/scale, expected/scale
        require(np.linalg.norm(a-b) <= 1e-9*max(np.linalg.norm(a), np.linalg.norm(b)),
                "Land result witness differs: "+name)


def validate_land_result(result):
    """No second solve; recompute raw support, weak law, KCL and exact heat."""
    require(result.get("contract") == "spike/dc-land-transition-result/v1"
            and result.get("model_status") == "experimental" and result.get("production_qualified") is False
            and result.get("complete_board_physical_volume") is False, "Land result scope differs")
    data = prepare(result["source_request"])
    require(result["input_digest"] == data["digest"], "Land result input digest differs")
    trace = np.asarray(result["face_potential_v"], dtype=float)
    require(trace.shape == (data["face_count"],) and np.isfinite(trace).all() and trace[0] == 0,
            "Land potential/gauge witness differs")
    require(len(result["cells"]) == len(data["cells"]), "Land result cell support differs")
    assembled = np.zeros(data["face_count"]); heat, volume = [], []
    for n, (cell, index) in enumerate(zip(result["cells"], data["cells"])):
        length = data["lengths"][n]; vol = float(np.prod(length)); area = vol/length
        bounds = [[float(data["axes"][a][i]*1000+data["origins_mm"][a]),
                   float(data["axes"][a][i+1]*1000+data["origins_mm"][a])] for a, i in enumerate(index)]
        require(cell["id"] == f"cell:{n}" and cell["face_ids"] == data["faces"][n].tolist()
                and cell["bounds_mm"] == bounds, "Land cell identity/geometry differs")
        q = np.asarray(cell["outward_face_current_a"], dtype=float)
        require(q.shape == (6,) and np.isfinite(q).all(), "Land cell flux shape differs")
        require(abs(float(q.sum())) <= 1e-9*data["current_scale"], "Land cell charge does not conserve")
        np.add.at(assembled, data["faces"][n], q)
        endpoints = q.reshape(3, 2)/area[:, None]; endpoints[:, 0] *= -1
        close(cell["component_endpoint_density_a_m2"], endpoints, "vector endpoints")
        close(cell["center_density_a_m2"], endpoints.mean(axis=1), "vector center")
        close(cell["volume_m3"], vol, "cell volume")
        # Integrate the quadratic affine-component field; opposite face terms
        # retain their cross contribution. No mass lumping or midpoint heat.
        density_integral = np.sum(endpoints[:, 0]**2+endpoints[:, 0]*endpoints[:, 1]+endpoints[:, 1]**2)/3
        power = float(vol*density_integral/data["sigma"])
        close(cell["joule_heat_w"], power, "cell heat")
        close(cell["mean_joule_density_w_m3"], power/vol, "mean heat density")
        p = float(cell["mean_potential_v"])
        require(math.isfinite(p), "Nonfinite mean land potential")
        moment = np.empty(6)
        for a in range(3):
            factor = length[a]/(data["sigma"]*area[a])
            moment[2*a] = factor*(q[2*a]/3-q[2*a+1]/6)
            moment[2*a+1] = factor*(q[2*a+1]/3-q[2*a]/6)
        local_trace = trace[data["faces"][n]]
        require(np.isfinite(moment).all(), "Nonfinite land constitutive moment")
        scale = max(float(np.max(np.abs(moment))), float(np.max(np.abs(local_trace))), abs(p))
        if scale:
            m, t, mean = moment/scale, local_trace/scale, p/scale
            require(np.linalg.norm(m+t-mean) <= 1e-9*max(np.linalg.norm(m), np.linalg.norm(t), abs(mean)),
                    "Land local Ohmic weak law differs")
        heat.append(power); volume.append(vol)
    require(np.max(np.abs(assembled-data["prescribed"])) <= 1e-9*data["current_scale"],
            "Land interior/boundary/gauge flux differs")
    require(len(result["contacts"]) == len(data["patches"]), "Land result contact support differs")
    work = []
    for actual, patch in zip(result["contacts"], data["patches"]):
        for key in ("id", "attachment_id", "face", "rectangle_mm"):
            require(actual[key] == patch[key], "Land contact mapping differs")
        require(actual["face_ids"] == patch["faces"], "Land contact face identity differs")
        require(actual["patch_relative_accuracy_certified"] is False, "Unsupported contact accuracy claim")
        voltage = float(np.dot(trace[patch["faces"]], patch["face_areas_m2"])/patch["area_m2"])
        for key, expected in (("area_m2", patch["area_m2"]), ("inward_current_a", patch["current_a"]),
                              ("recovered_inward_current_a", -assembled[patch["faces"]].sum()),
                              ("absolute_current_recovery_error_a", abs(-assembled[patch["faces"]].sum()-patch["current_a"])),
                              ("global_face_residual_tolerance_a", 1e-9*data["current_scale"]),
                              ("mean_potential_v", voltage), ("signed_terminal_work_w", patch["current_a"]*voltage)):
            close(actual[key], expected, key)
        work.append(patch["current_a"]*voltage)
    close(result["total_volume_m3"], math.fsum(volume), "total volume")
    close(result["joule_heat_w"], math.fsum(heat), "total heat")
    close(result["signed_terminal_work_w"], math.fsum(work), "terminal work")
    close(math.fsum(heat), math.fsum(work), "global work balance")
