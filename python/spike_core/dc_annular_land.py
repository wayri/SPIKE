# SPDX-License-Identifier: Apache-2.0
"""Axisymmetric conservative annular land reference, with full-azimuth patches.

Four outward integrated face currents per annular cell; Piola RT0 basis in
(r^2,z). Radial mass uses bounded Gauss quadrature, not an exact-mass claim.
Original derivation and primary-law review: docs/DC_ANNULAR_LAND.md.
"""
from __future__ import annotations
from copy import deepcopy
import math

import numpy as np
from numpy.polynomial.legendre import leggauss
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu

from .dc_annular_land_input import prepare, require
from .dc_land_transition import _condition


def radial_mass(radius_m, width_m, height_m, conductivity_s_m, order=16):
    """Quadrature of the two radial flux bases; caller admits positive geometry."""
    x, w = leggauss(order)
    u = (x+1)/2
    radius = radius_m+width_m*u
    s = u*(2*radius_m+width_m*u)/(2*radius_m+width_m)
    basis = np.column_stack((-(1-s), s))
    weights = w*(width_m/2)/radius/(2*math.pi*conductivity_s_m*height_m)
    return np.einsum("q,qi,qj->ij", weights, basis, basis)


def _solve(raw):
    data = prepare(raw)
    count, ids = len(data["cells"]), data["faces"]
    mass = np.zeros((count, 4, 4)); volume = np.empty(count)
    quadrature_error = 0.
    for n, (i, j) in enumerate(data["cells"]):
        radius, dr, dz = data["radius"][i], data["dr"][i], data["dz"][j]
        radial = radial_mass(radius, dr, dz, data["sigma"])
        check = radial_mass(radius, dr, dz, data["sigma"], 32)
        error = float(np.max(np.abs(radial-check))/np.max(np.abs(check)))
        require(math.isfinite(error) and error <= 1e-12, "Annular radial quadrature check failed")
        quadrature_error = max(quadrature_error, error)
        mass[n, :2, :2] = radial
        mass[n, 2:, 2:] = dz/(data["sigma"]*data["annulus"][i])*np.array([[1/3, -1/6], [-1/6, 1/3]])
        volume[n] = data["annulus"][i]*dz
    require(np.isfinite(mass).all() and np.isfinite(volume).all() and np.all(volume > 0), "Invalid annular mass/volume")
    inverse = np.linalg.inv(mass)
    v = inverse.sum(axis=2); d = v.sum(axis=1)
    h = inverse-v[:, :, None]*v[:, None, :]/d[:, None, None]
    rows, cols = np.repeat(ids, 4, axis=1).ravel(), np.tile(ids, (1, 4)).ravel()
    operator = coo_matrix((h.ravel(), (rows, cols)), shape=(data["face_count"],)*2).tocsr()
    free = np.arange(1, data["face_count"])
    selected = operator[free][:, free]
    scaling = 1/np.sqrt(selected.diagonal())
    scaled = (diags(scaling)@selected@diags(scaling)).tocsc()
    require(np.isfinite(scaled.data).all(), "Nonfinite annular trace operator")
    condition = _condition(scaled)
    trace = np.zeros(data["face_count"])
    trace[free] = scaling*splu(scaled).solve(-scaling*data["prescribed"][free])
    flux = -np.einsum("tij,tj->ti", h, trace[ids])
    assembled = np.bincount(ids.ravel(), weights=flux.ravel(), minlength=data["face_count"])
    residual = float(np.max(np.abs(assembled-data["prescribed"])))
    kcl = float(np.max(np.abs(flux.sum(axis=1))))
    scale = data["current_scale"]
    require(np.isfinite(trace).all() and np.isfinite(flux).all() and residual <= 1e-9*scale
            and kcl <= 1e-9*scale, "Annular recovered boundary/interior/gauge KCL failed")
    power = np.einsum("ti,tij,tj->t", flux, mass, flux)
    mean = np.einsum("ti,ti->t", v, trace[ids])/d
    contacts = []
    for p in data["patches"]:
        voltage = float(np.dot(trace[p["face_ids"]], np.array(p["face_areas_m2"])/p["area_m2"]))
        recovered = float(-math.fsum(assembled[p["face_ids"]]))
        contacts.append({key: deepcopy(p[key]) for key in ("id", "attachment_id", "face", "interval_mm")}
                        | {"face_ids": p["face_ids"], "area_m2": p["area_m2"],
                           "inward_current_a": p["current_a"], "recovered_inward_current_a": recovered,
                           "absolute_current_recovery_error_a": abs(recovered-p["current_a"]),
                           "global_face_residual_tolerance_a": 1e-9*scale,
                           "patch_relative_accuracy_certified": False, "mean_potential_v": voltage,
                           "signed_terminal_work_w": p["current_a"]*voltage})
    total_heat = float(math.fsum(power)); work = math.fsum(p["signed_terminal_work_w"] for p in contacts)
    require(np.isfinite(power).all() and np.all(power >= 0) and math.isfinite(work)
            and (scale == 0 or total_heat > 0) and abs(total_heat-work) <= 1e-9*max(total_heat, abs(work)),
            "Annular Joule heat/work failed or underflowed")
    cells = []
    for n, (i, j) in enumerate(data["cells"]):
        q = flux[n]; r0, dr, dz = data["radius"][i], data["dr"][i], data["dz"][j]
        area = data["annulus"][i]
        smid = .5*(2*r0+dr/2)/(2*r0+dr)
        jr = (-q[0]*(1-smid)+q[1]*smid)/(2*math.pi*(r0+dr/2)*dz)
        jz = (-q[2]+q[3])/(2*area)
        cells.append({"id": f"cell:{n}", "face_ids": ids[n].tolist(),
            "radial_bounds_mm": data["rmm"][i:i+2].tolist(), "axial_bounds_mm": data["zmm"][j:j+2].tolist(),
            "outward_face_current_a": q.tolist(), "volume_m3": float(volume[n]),
            "mean_potential_v": float(mean[n]), "joule_heat_w": float(power[n]),
            "mean_joule_density_w_m3": float(power[n]/volume[n]),
            "center_density_rz_a_m2": [float(jr), float(jz)],
            "radial_current_numerator_endpoint_a": [-float(q[0]), float(q[1])],
            "axial_component_endpoint_density_a_m2": [-float(q[2]/area), float(q[3]/area)]})
    return {"contract": "spike/dc-annular-land-result/v1", "model_status": "experimental",
        "production_qualified": False, "complete_board_physical_volume": False,
        "source_request": deepcopy(raw), "input_digest": data["digest"], "contacts": contacts,
        "cells": cells, "face_potential_v": trace.tolist(), "total_volume_m3": float(math.fsum(volume)),
        "joule_heat_w": total_heat, "signed_terminal_work_w": work,
        "diagnostics": {"maximum_face_boundary_gauge_error_a": residual, "maximum_cell_kcl_error_a": kcl,
                        "input_current_balance_a": data["input_current_balance_a"],
                        "scaled_condition_estimate": condition, "radial_mass_16_32_relative_difference": quadrature_error},
        "conventions": {"current": "positive_into_domain", "potential_gauge": "face:0=0",
                        "local_face_order": ["r_min", "r_max", "z_min", "z_max"],
                        "attachment_ids": "labels_only_no_equipotential_or_circuit_weld",
                        "field": "full azimuth axisymmetric Jr,Jz; radial numerator affine in r squared, Jz affine in z"},
        "limitations": ["Explicit full-azimuth annular prism and conforming band patches only; r=0 unsupported.",
            "Radial mass uses 16-point Gauss quadrature checked at32 points; no rigorous quadrature certificate.",
            "Prescribed finite Neumann currents only; external circuit/other regions require a fresh coupled solve.",
            "Global absolute flux recovery bound only; tiny patches have no relative accuracy guarantee.",
            "No angular field/crowding, arbitrary polygon/contact inference, AC, thermal mapping or board qualification."]}


def solve_annular_land(request):
    """Solve actual supplied currents; every call recomputes fields and heat."""
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            return _solve(request)
    except (FloatingPointError, OverflowError, np.linalg.LinAlgError, RuntimeError) as error:
        raise ValueError("Annular land arithmetic/factorization/condition screen failed") from error
