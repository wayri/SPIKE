# SPDX-License-Identifier: Apache-2.0
"""Experimental conservative scalar DC on complete supplied tetrahedral solids."""
from __future__ import annotations
from copy import deepcopy
import math
import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu
from python.spike_core.dc_land_transition import _condition
from .dc_tetra_rt0_input import prepare, require, DCTetraRT0Error, grouped_sums
from .dc_tetra_density import tetra_density_enclosure


def local_masses(data):
    result = []
    for n, cell in enumerate(data["cells"]):
        vertices = data["xyz"][cell["vertices"]]
        r = vertices-vertices[0]; centered = r-r.mean(axis=0)
        m = ((centered@centered.T)+np.sum(centered*centered)/20)/(9*data["volumes"][n]*data["sigma"][n])
        require(np.isfinite(m).all() and np.linalg.eigvalsh(m)[0] > 0, "Invalid tetrahedral Ohmic mass")
        result.append(m)
    return np.array(result)


def solve_tetra_dc(request, *, cancelled=None):
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _solve(request, cancelled)
    except DCTetraRT0Error:
        raise
    except (ValueError, TypeError, KeyError, FloatingPointError, OverflowError, np.linalg.LinAlgError, RuntimeError) as error:
        raise DCTetraRT0Error("Tetra DC arithmetic/factorization/condition screen failed") from error


def _solve(request, cancelled):
    data = prepare(request)
    require(cancelled is None or callable(cancelled), "Cancellation must be callable")
    def check(): require(cancelled is None or not cancelled(), "Tetra DC cancelled between bounded operations")
    check()
    if data['scalable']:
        from .dc_tetra_sparse import local_hybrid
        h, normals = local_hybrid(data)
    else:
        mass = local_masses(data); inverse = np.linalg.inv(mass)
        a = inverse.sum(axis=2); d = a.sum(axis=1)
        h = inverse-a[:, :, None]*a[:, None, :]/d[:, None, None]
    ids = data["face_ids"]; count = len(data["face_keys"])
    operator = coo_matrix((h.ravel(), (np.repeat(ids, 4, axis=1).ravel(), np.tile(ids, (1, 4)).ravel())),
                          shape=(count, count)).tocsr()
    free = np.setdiff1d(np.arange(count), data["gauges"])
    selected = operator[free][:, free]; scaling = 1/np.sqrt(selected.diagonal())
    scaled = (diags(scaling)@selected@diags(scaling)).tocsc()
    require(np.isfinite(scaled.data).all(), "Nonfinite scaled tetra trace operator")
    check(); linear_diagnostics = {}
    if data["scalable"]:
        from .dc_tetra_sparse import solve_trace
        solution, linear_diagnostics = solve_trace(scaled, -scaling*data["prescribed"][free], check)
        condition = linear_diagnostics["scaled_condition_estimate"]
    else:
        condition = _condition(scaled)
        solution = splu(scaled).solve(-scaling*data["prescribed"][free])
    trace = np.zeros(count); trace[free] = scaling*solution
    if data['scalable']:
        relative_trace = trace[ids]-trace[ids[:, :1]]
        constant_fields = -(data['sigma']/data['volumes'])[:, None]*np.einsum('ti,tij->tj', relative_trace, normals)
        q = np.einsum('tij,tj->ti', normals, constant_fields)
    else:
        q = -np.einsum("tij,tj->ti", h, trace[ids])
    assembled = np.bincount(ids.ravel(), weights=q.ravel(), minlength=count)
    face_error = float(np.max(np.abs(assembled-data["prescribed"]))); cell_error = float(np.max(np.abs(q.sum(axis=1))))
    component_scale = np.asarray(data["component_drives"])
    cell_component = data["labels"][ids[:, 0]]
    require(np.isfinite(trace).all() and np.isfinite(q).all()
            and np.all(np.abs(assembled-data["prescribed"]) <= 1e-9*component_scale[data["labels"]])
            and np.all(np.abs(q.sum(axis=1)) <= 1e-9*component_scale[cell_component]),
            "Tetra recovered boundary/interior/gauge or cell KCL failed")
    if data['scalable']:
        heat = (data['volumes']/data['sigma'])*np.einsum('ti,ti->t', constant_fields, constant_fields)
        mean = trace[ids].mean(axis=1)
    else:
        heat = np.einsum("ti,tij,tj->t", q, mass, q); mean = np.einsum("ti,ti->t", a, trace[ids])/d
    require(np.isfinite(heat).all() and np.all(heat >= 0)
            and np.all((np.any(q != 0, axis=1)) == (heat > 0))
            and np.all((heat == 0) | (heat >= np.finfo(float).tiny)),
            "Tetra field heat overflowed, underflowed or has insufficient subnormal resolution")
    fields = []; vectors = []; inactive_volume = 0.
    for n, cell in enumerate(data["cells"]):
        vertices = data["xyz"][cell["vertices"]]; r = vertices-vertices[0]
        values = (np.tile(constant_fields[n], (4, 1)) if data['scalable'] else
                  (q[n].sum()*r-np.einsum("i,ik->k", q[n], r))/(3*data["volumes"][n]))
        require(np.isfinite(values).all(), "Tetra vector field overflowed")
        vectors.append(values)
        component = int(data["labels"][ids[n, 0]])
        if data["component_drives"][component] == 0: inactive_volume += float(data["volumes"][n])
        fields.append({"id": cell["id"], "vertices": deepcopy(cell["vertices"]), "face_ids": ids[n].tolist(),
                       "outward_face_current_a": q[n].tolist(), "vertex_density_a_m2": values.tolist(),
                       "volume_m3": float(data["volumes"][n]), "joule_heat_w": float(heat[n]),
                       "mean_joule_density_w_m3": float(heat[n]/data["volumes"][n]), "mean_potential_v": float(mean[n]),
                       "component": component, "source_object_ids": deepcopy(cell["source_object_ids"])})
    patches = []; works = []
    for p in data["patches"]:
        f = p["face_ids"]; weights = data["face_area"][f]/p["area_m2"]
        voltage = float(weights@trace[f]); recovered = -math.fsum(assembled[f]); work = p["current_a"]*voltage
        patches.append({"id": p["id"], "faces": deepcopy(p["faces"]), "face_ids": f.tolist(), "area_m2": p["area_m2"],
                        "inward_current_a": p["current_a"], "recovered_inward_current_a": recovered,
                        "mean_potential_v": voltage, "signed_terminal_work_w": work,
                        "absolute_current_recovery_error_a": abs(recovered-p["current_a"]),
                        "patch_relative_accuracy_certified": False})
        works.append(work)
    total = math.fsum(heat); work = math.fsum(works)
    component_power = grouped_sums(cell_component, heat, data["components"])
    component_work = grouped_sums(data["labels"], -data["prescribed"]*trace, data["components"])
    for power, terminal, drive in zip(component_power, component_work, data["component_drives"]):
        require(math.isfinite(terminal) and (drive == 0 or power > 0 and terminal > 0)
                and abs(power-terminal) <= 1e-9*max(power, abs(terminal)),
                "Tetra connected-component heat/work failed")
    require(math.isfinite(work) and (data["current_scale"] == 0 or total > 0 and work > 0)
            and abs(total-work) <= 1e-9*max(total, abs(work)), "Tetra Joule/terminal work failed")
    check(); density = {"method": "conservative_tetra_RT0_unique_volume", "p95": tetra_density_enclosure(vectors, data["volumes"]),
        "p99": tetra_density_enclosure(vectors, data["volumes"], .99), "physical_volume_m3": math.fsum(data["volumes"]),
        "undriven_volume_m3": inactive_volume, "complete_supplied_volume": True, "complete_board_physical_volume": False}
    return {"contract": "spike/tetra-dc-rt0-result/v1", "source_request": deepcopy(request), "input_digest": data["digest"],
            "model_status": "experimental", "production_qualified": False, "cells": fields, "contacts": patches,
            "faces": [list(f) for f in data["face_keys"]], "face_potential_v": trace.tolist(),
            "gauge_face_ids": data["gauges"].tolist(), "joule_heat_w": total, "signed_terminal_work_w": work,
            "current_density_observable": density, "diagnostics": {"maximum_cell_kcl_error_a": cell_error,
                "maximum_face_boundary_gauge_error_a": face_error, "scaled_condition_estimate": condition,
                "connected_components": data["components"], "volume_coverage": "all supplied retained tetrahedra",
                **linear_diagnostics},
            "limitations": ["Uniform finite Neumann patches and scalar steady conductivity, not equipotential electrodes.",
                "Source-board completeness requires a separate geometry/source coverage proof.",
                "All flux and density are discrete reconstructed fields; mesh/model error remains separate.",
                "No AC/SI, production dispatch, installed qualification or human release review is inferred."]}
