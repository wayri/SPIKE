# SPDX-License-Identifier: Apache-2.0
"""Original conservative 3-D Cartesian RT0 land reference; not board qualification.

Exact face-flux mass, gauge equation and terminal work: docs/DC_LAND_TRANSITION.md.
"""
from __future__ import annotations
from copy import deepcopy
import math

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import eigsh, splu

from .dc_land_transition_input import prepare, require


def _condition(matrix):
    if matrix.shape[0] <= 128:
        eigenvalues = np.linalg.eigvalsh(matrix.toarray())
        lower, upper = eigenvalues[0], eigenvalues[-1]
    else:
        initial = np.random.default_rng(173).normal(size=matrix.shape[0])
        lower = eigsh(matrix, k=1, which="SA", v0=initial, return_eigenvectors=False, tol=1e-7, maxiter=5000)[0]
        upper = eigsh(matrix, k=1, which="LA", v0=initial, return_eigenvectors=False, tol=1e-7, maxiter=5000)[0]
    require(math.isfinite(lower) and math.isfinite(upper) and lower > 0 and upper/lower <= 1e12,
            "Land trace operator exceeds conditioning budget")
    return float(upper/lower)


def _solve(raw):
    data = prepare(raw)
    lengths, ids = data["lengths"], data["faces"]
    volumes = np.prod(lengths, axis=1)
    areas = volumes[:, None]/lengths
    masses = np.zeros((len(lengths), 6, 6))
    block = np.array([[1/3, -1/6], [-1/6, 1/3]])
    for a in range(3):
        masses[:, 2*a:2*a+2, 2*a:2*a+2] = (lengths[:, a]/(data["sigma"]*areas[:, a]))[:, None, None]*block
    inverse = np.linalg.inv(masses)
    v = inverse.sum(axis=2); denominator = v.sum(axis=1)
    h = inverse-v[:, :, None]*v[:, None, :]/denominator[:, None, None]
    rows = np.repeat(ids, 6, axis=1).ravel()
    cols = np.tile(ids, (1, 6)).ravel()
    operator = coo_matrix((h.ravel(), (rows, cols)), shape=(data["face_count"],)*2).tocsr()
    # Fix one trace only. The recovered residual must include this gauge row.
    free = np.arange(1, data["face_count"])
    selected = operator[free][:, free]
    scaling = 1/np.sqrt(selected.diagonal())
    scaled = (diags(scaling)@selected@diags(scaling)).tocsc()
    require(np.isfinite(scaled.data).all(), "Nonfinite scaled land operator")
    condition = _condition(scaled)
    trace = np.zeros(data["face_count"])
    trace[free] = scaling*splu(scaled).solve(-scaling*data["prescribed"][free])
    flux = -np.einsum("tij,tj->ti", h, trace[ids])
    assembled = np.bincount(ids.ravel(), weights=flux.ravel(), minlength=data["face_count"])
    error = float(np.max(np.abs(assembled-data["prescribed"])))
    cell_error = float(np.max(np.abs(flux.sum(axis=1))))
    scale = data["current_scale"]
    require(np.isfinite(trace).all() and np.isfinite(flux).all() and error <= 1e-9*scale
            and cell_error <= 1e-9*scale, "Recovered land KCL/boundary/gauge equation failed")
    power = np.einsum("ti,tij,tj->t", flux, masses, flux)
    endpoints = flux.reshape(-1, 3, 2)/areas[:, :, None]
    endpoints[:, :, 0] *= -1
    patches = []
    for patch in data["patches"]:
        voltage = float(np.dot(trace[patch["faces"]], patch["face_areas_m2"])/patch["area_m2"])
        patches.append({"id": patch["id"], "attachment_id": patch["attachment_id"], "face": patch["face"],
            "rectangle_mm": deepcopy(patch["rectangle_mm"]), "face_ids": patch["faces"],
            "area_m2": patch["area_m2"], "inward_current_a": patch["current_a"],
            "recovered_inward_current_a": float(-assembled[patch["faces"]].sum()),
            "absolute_current_recovery_error_a": float(abs(-assembled[patch["faces"]].sum()-patch["current_a"])),
            "global_face_residual_tolerance_a": 1e-9*scale,
            "patch_relative_accuracy_certified": False,
            "mean_potential_v": voltage, "signed_terminal_work_w": patch["current_a"]*voltage})
    heat = float(power.sum()); work = math.fsum(p["signed_terminal_work_w"] for p in patches)
    require(np.isfinite(power).all() and np.all(power >= 0) and math.isfinite(work)
            and (scale == 0 or heat > 0) and abs(heat-work) <= 1e-9*max(heat, abs(work)),
            "Land Joule heat and terminal work differ or underflow")
    cells = []
    mean_potential = np.einsum("ti,ti->t", v, trace[ids])/denominator
    for n, index in enumerate(data["cells"]):
        bounds = [[float(data["axes"][a][i]*1000+data["origins_mm"][a]),
                   float(data["axes"][a][i+1]*1000+data["origins_mm"][a])] for a, i in enumerate(index)]
        cells.append({"id": f"cell:{n}", "bounds_mm": bounds, "face_ids": ids[n].tolist(),
            "outward_face_current_a": flux[n].tolist(), "volume_m3": float(volumes[n]),
            "mean_potential_v": float(mean_potential[n]),
            "component_endpoint_density_a_m2": endpoints[n].tolist(),
            "center_density_a_m2": endpoints[n].mean(axis=1).tolist(),
            "joule_heat_w": float(power[n]), "mean_joule_density_w_m3": float(power[n]/volumes[n])})
    return {"contract": "spike/dc-land-transition-result/v1", "model_status": "experimental",
        "production_qualified": False, "complete_board_physical_volume": False,
        "input_digest": data["digest"], "source_request": deepcopy(raw), "contacts": patches, "cells": cells,
        "face_potential_v": trace.tolist(),
        "total_volume_m3": float(volumes.sum()), "joule_heat_w": heat, "signed_terminal_work_w": work,
        "diagnostics": {"maximum_face_boundary_gauge_error_a": error, "maximum_cell_kcl_error_a": cell_error,
            "input_current_balance_a": data["input_current_balance_a"], "scaled_condition_estimate": condition},
        "conventions": {"current": "positive_into_domain", "potential_gauge": "face:0=0",
            "field": "RT0 component affine in its own coordinate; endpoint entries are Cartesian components",
            "thermal_transfer": "cell integrated W or mean W/m3; no energy J or inferred thermal mapping",
            "attachment_ids": "labels_only_no_equipotential_or_circuit_weld"},
        "limitations": ["Uniform scalar DC rectangular prism only; explicit conforming rectangular face patches.",
            "Finite Neumann injection patches, not equipotential electrodes or solved external circuit currents.",
            "Global absolute flux recovery bound only; tiny contacts have no per-patch relative accuracy guarantee.",
            "No automatic annular/board geometry, complete-board density, AC, material feedback or release qualification."]}


def solve_land_transition(request):
    """Solve explicit 3-D land fields; reject unsupported or failed numerics."""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _solve(request)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError, RuntimeError) as error:
        raise ValueError("Land transition arithmetic, factorization or condition screen failed") from error
