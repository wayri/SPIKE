# SPDX-License-Identifier: Apache-2.0
"""Physical retained tetra DC witnesses, independent of solver factorization."""
from __future__ import annotations
import math
import numpy as np
from .dc_tetra_rt0_input import prepare, require, grouped_sums
from .dc_tetra_density import tetra_density_enclosure
from python.spike_core.dc_land_transition_evidence import close


def validate_tetra_dc(result):
    require(result.get("contract") == "spike/tetra-dc-rt0-result/v1"
            and result.get("model_status") == "experimental" and result.get("production_qualified") is False,
            "Retained tetra DC scope differs")
    data = prepare(result["source_request"])
    require(result["input_digest"] == data["digest"] and len(result["cells"]) == len(data["cells"]), "Retained tetra input/support differs")
    require(result["faces"] == [list(f) for f in data["face_keys"]]
            and result["gauge_face_ids"] == data["gauges"].tolist(), "Retained tetra face/gauge identities differ")
    trace = np.asarray(result["face_potential_v"], dtype=float)
    require(trace.shape == (len(data["face_keys"]),) and np.isfinite(trace).all()
            and np.all(trace[data["gauges"]] == 0), "Retained tetra trace/gauge differs")
    # Independent degree-two tetra cubature, not the kernel's moment matrix.
    barycentric = np.full((4, 4), (5-math.sqrt(5))/20)
    np.fill_diagonal(barycentric, (5+3*math.sqrt(5))/20)
    assembled = np.zeros(len(trace)); powers, vectors = [], []; inactive_volume = 0.
    cell_components = []
    for n, (actual, source) in enumerate(zip(result["cells"], data["cells"])):
        ids = data["face_ids"][n]; vol = data["volumes"][n]; sigma = data["sigma"][n]
        component = int(data["labels"][ids[0]])
        cell_components.append(component)
        current_scale = data["component_drives"][component]
        require(actual["id"] == source["id"] and actual["vertices"] == source["vertices"]
                and actual["source_object_ids"] == source["source_object_ids"] and actual["face_ids"] == ids.tolist()
                and actual["component"] == component, "Retained tetra cell/source ownership differs")
        q = np.asarray(actual["outward_face_current_a"], dtype=float)
        j = np.asarray(actual["vertex_density_a_m2"], dtype=float)
        require(q.shape == (4,) and j.shape == (4, 3) and np.isfinite(q).all() and np.isfinite(j).all(),
                "Retained tetra flux/vector shape differs")
        require(abs(math.fsum(q)) <= 1e-9*current_scale, "Retained tetra cell KCL differs")
        np.add.at(assembled, ids, q)
        points = data["xyz"][source["vertices"]]; relative = points-points[0]
        x = barycentric@relative
        basis = (x[:, None, :]-relative[None, :, :])/(3*vol)
        field = barycentric@j
        close(field, np.einsum("i,qik->qk", q, basis), "tetra reconstructed physical field")
        # Independent boundary current via planar face centroid and outward area vector.
        for opposite in range(4):
            local = [k for k in range(4) if k != opposite]
            a, b, c = relative[local]
            area_normal = np.cross(b-a, c-a)/2
            if np.dot(area_normal, relative[opposite]-a) > 0: area_normal *= -1
            require(abs(float(j[local].mean(axis=0)@area_normal)-q[opposite]) <= 1e-9*current_scale,
                    "Retained tetra signed face integral differs")
        power = float(vol/4*np.sum(field*field)/sigma)
        require(math.isfinite(power) and (not np.any(q) or power >= np.finfo(float).tiny),
                "Retained tetra heat underflowed or has insufficient subnormal resolution")
        moment = vol/4*np.einsum("qik,qk->i", basis, field)/sigma
        mean = float(actual["mean_potential_v"])
        require(math.isfinite(mean), "Retained tetra potential is nonfinite")
        scale = max(float(np.max(np.abs(moment))), float(np.max(np.abs(trace[ids]))), abs(mean))
        if scale:
            require(np.linalg.norm(moment/scale+trace[ids]/scale-mean/scale)
                    <= 1e-9*max(np.linalg.norm(moment/scale), np.linalg.norm(trace[ids]/scale), abs(mean/scale)),
                    "Retained tetra local Ohmic weak law differs")
        for key, value in (("volume_m3", vol), ("joule_heat_w", power), ("mean_joule_density_w_m3", power/vol)):
            close(actual[key], value, "tetra "+key)
        if data["component_drives"][component] == 0:
            require(not np.any(q) and not np.any(j), "Undriven retained component has nonzero field")
            inactive_volume += float(vol)
        powers.append(power); vectors.append(j)
    face_scales = np.asarray(data["component_drives"])[data["labels"]]
    require(np.all(np.abs(assembled-data["prescribed"]) <= 1e-9*face_scales),
            "Retained tetra interior/boundary/gauge flux differs")
    require(len(result["contacts"]) == len(data["patches"]), "Retained tetra contact support differs")
    works = []
    for actual, p in zip(result["contacts"], data["patches"]):
        f = p["face_ids"]
        require(actual["id"] == p["id"] and actual["faces"] == p["faces"] and actual["face_ids"] == f.tolist()
                and actual["patch_relative_accuracy_certified"] is False, "Retained tetra contact identity/accuracy differs")
        voltage = float((data["face_area"][f]/p["area_m2"])@trace[f]); recovered = -math.fsum(assembled[f])
        work = voltage*p["current_a"]
        for key, value in (("area_m2", p["area_m2"]), ("inward_current_a", p["current_a"]),
                           ("recovered_inward_current_a", recovered), ("mean_potential_v", voltage),
                           ("signed_terminal_work_w", work), ("absolute_current_recovery_error_a", abs(recovered-p["current_a"]))):
            close(actual[key], value, "tetra contact "+key)
        works.append(work)
    close(result["joule_heat_w"], math.fsum(powers), "tetra total heat")
    close(result["signed_terminal_work_w"], math.fsum(works), "tetra total work")
    close(math.fsum(powers), math.fsum(works), "tetra physical heat/work")
    component_power = grouped_sums(cell_components, powers, data["components"])
    component_work = grouped_sums(data["labels"], -data["prescribed"]*trace, data["components"])
    for power, terminal, drive in zip(component_power, component_work, data["component_drives"]):
        close(power, terminal, "tetra connected-component heat/work")
        require(drive == 0 or power > 0 and terminal > 0,
                "Driven retained tetra component has zero heat/work")
    require(data["current_scale"] == 0 or math.fsum(powers) > 0 and math.fsum(works) > 0,
            "Nonzero retained tetra drive has zero heat/work")
    observable = result["current_density_observable"]
    require(observable["method"] == "conservative_tetra_RT0_unique_volume"
            and observable["complete_supplied_volume"] is True and observable["complete_board_physical_volume"] is False,
            "Retained tetra coverage/qualification scope differs")
    close(observable["physical_volume_m3"], math.fsum(data["volumes"]), "tetra density physical volume")
    close(observable["undriven_volume_m3"], inactive_volume, "tetra density undriven volume")
    for key, quantile in (("p95", .95), ("p99", .99)):
        expected = tetra_density_enclosure(vectors, data["volumes"], quantile)
        require(observable[key] == expected, "Retained tetra density quantile/support differs")
