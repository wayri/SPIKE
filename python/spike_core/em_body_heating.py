# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Power-calibrated one-port volume loss on an explicit shared linear tetra mesh.

Independent RMS Poynting formulation; see docs/validation/EM_BODY_HEATING_20261023.md.
Raw E and H must share a single amplitude convention. No port deficit is heat.
"""
from copy import deepcopy
import itertools
import json
import math

import numpy as np

from .assembly_tetra_thermal import run_assembly_tetra_thermal
from .assembly_tetra_thermal_validation import validate_request
from .em_network_ac import _digest, solve_em_network_ac

CONTRACT = "spike/em-body-heating-request/v1"
TOLERANCE = 1e-8
MAX_CELLS = 512


def _require(value, message):
    if not value:
        raise ValueError("EM_BODY_HEATING: " + message)


def field_quadrature(thermal_request):
    """Positive 4^3 volume / 4^2 face Duffy-Gauss rules, explicit SI points.

    Exact for quadratic E/H polynomial products on straight tetrahedra.
    Sampling accuracy of a nonpolynomial/curved field is not inferred.
    """
    _require(isinstance(thermal_request, dict) and isinstance(thermal_request.get("mesh"), dict), "Thermal mesh required")
    _require(1 <= len(thermal_request["mesh"].get("cells", [])) <= MAX_CELLS, "At most 512 shared tetrahedra")
    data = validate_request(thermal_request)
    xyz, cells = data["xyz"], thermal_request["mesh"]["cells"]
    roots, weights = np.polynomial.legendre.leggauss(4)
    roots, weights = (roots+1)/2, weights/2
    volumes, faces = {}, {}
    for cell, (volume, _) in zip(cells, data["geometry"]):
        vertices = xyz[cell["vertices"]]
        points, factors = [], []
        for i, j, k in itertools.product(range(4), repeat=3):
            u, v, w = roots[i], roots[j], roots[k]
            bary = np.array([(1-u)*(1-v)*(1-w), u, (1-u)*v, (1-u)*(1-v)*w])
            points.append((bary@vertices).tolist())
            factors.append(float(6*volume*weights[i]*weights[j]*weights[k]*(1-u)**2*(1-v)))
        volumes[cell["id"]] = {"points_m": points, "weights_m3": factors}
        for face in itertools.combinations(cell["vertices"], 3):
            key = ":".join(map(str, sorted(face)))
            if key in faces:
                faces[key]["owners"] += 1
                continue
            p = xyz[list(face)]
            cross = np.cross(p[1]-p[0], p[2]-p[0])
            opposite = next(n for n in cell["vertices"] if n not in face)
            if np.dot(cross, xyz[opposite]-p[0]) > 0:
                cross = -cross
            normal, jacobian = cross/np.linalg.norm(cross), np.linalg.norm(cross)
            points, factors = [], []
            for i, j in itertools.product(range(4), repeat=2):
                u, v = roots[i], roots[j]
                points.append((np.array([(1-u)*(1-v), u, (1-u)*v])@p).tolist())
                factors.append(float(jacobian*weights[i]*weights[j]*(1-u)))
            faces[key] = {"owners": 1, "points_m": points, "weights_m2": factors, "outward_normal": normal.tolist()}
    return {"cells": volumes, "boundary_faces": {key: value for key, value in faces.items() if value["owners"] == 1}}


def _vectors(raw, count):
    array = np.asarray(raw)
    _require(array.shape == (count, 3, 2) and array.dtype.kind in "iuf" and np.isfinite(array).all(),
             "Finite [sample][xyz][real,imag] vectors required")
    return array[:, :, 0]+1j*array[:, :, 1]


def run_em_body_heating(request, *, cancel_check=None):
    _require(cancel_check is None or callable(cancel_check), "Invalid cancellation callback")
    def poll():
        _require(cancel_check is None or not cancel_check(), "CANCELLED")
    poll()
    encoded = json.dumps(request, allow_nan=False)
    _require(len(encoded.encode()) <= 8*1024**2, "Request exceeds 8 MiB")
    raw = json.loads(encoded)
    _require(isinstance(raw, dict) and set(raw) == {"contract", "ac_request", "thermal_request", "loss_materials",
             "field_samples", "port_faces", "source_binding"} and raw["contract"] == CONTRACT, "Exact request fields required")
    thermal, ac_request = raw["thermal_request"], raw["ac_request"]
    _require(isinstance(thermal, dict) and not thermal.get("heat_sources_w_m3"), "Pre-existing heat would double count")
    geometry = field_quadrature(thermal)
    binding = raw["source_binding"]
    _require(isinstance(binding, dict) and set(binding) == {"mesh_digest", "ac_request_digest", "solver_run_digest", "field_samples_digest"}
             and binding["mesh_digest"] == _digest(thermal["mesh"]) and binding["ac_request_digest"] == _digest(ac_request)
             and isinstance(binding["solver_run_digest"], str) and len(binding["solver_run_digest"]) == 64
             and all(c in "0123456789abcdef" for c in binding["solver_run_digest"]), "Stale/missing source binding")
    ac = solve_em_network_ac(ac_request, cancel_check=cancel_check)
    _require(len(ac["ports"]) == 1 and len(ac["samples"]) == 1, "One source port and one exact frequency required")
    accepted = ac["samples"][0]["port_real_power_w"][0]
    _require(accepted > 0, "Positive accepted physical port power needed for calibration")
    omega = 2*math.pi*ac["samples"][0]["frequency_hz"]
    cells = thermal["mesh"]["cells"]
    loss = raw["loss_materials"]
    _require(isinstance(loss, dict) and set(loss) == {c["material_id"] for c in cells}, "Exact electromagnetic material coverage required")
    gamma = {}
    for name, item in loss.items():
        _require(isinstance(item, dict) and set(item) == {"conductivity_s_m", "permittivity_f_m", "loss_tangent"}, "Exact isotropic loss properties required")
        _require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in item.values())
                 and item["permittivity_f_m"] > 0, "Invalid passive loss properties")
        gamma[name] = item["conductivity_s_m"] + omega*item["permittivity_f_m"]*item["loss_tangent"]
    fields = raw["field_samples"]
    _require(isinstance(fields, dict) and _digest(fields) == binding["field_samples_digest"], "Retained field packet digest mismatch")
    _require(isinstance(fields, dict) and set(fields) == {"context", "cells", "boundary_faces"}
             and set(fields["cells"]) == set(geometry["cells"])
             and set(fields["boundary_faces"]) == set(geometry["boundary_faces"]), "Complete deterministic volume/boundary samples required")
    port_faces = raw["port_faces"]
    _require(isinstance(port_faces, list) and port_faces and len(set(port_faces)) == len(port_faces)
             and set(port_faces) <= set(geometry["boundary_faces"]), "Port must cover explicit exterior faces; internal lumped ports unsupported")
    expected_context = {"frequency_hz": ac["samples"][0]["frequency_hz"],
        "mesh_digest": binding["mesh_digest"], "loss_materials_digest": _digest(loss),
        "ac_source_digest": _digest(ac_request["source"]), "port_faces_digest": _digest(sorted(port_faces)),
        "solver_run_digest": binding["solver_run_digest"]}
    _require(fields["context"] == expected_context, "Field frequency/material/network/port/mesh/run context mismatch")
    powers = {}
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for cell in cells:
            poll()
            rule = geometry["cells"][cell["id"]]
            e = _vectors(fields["cells"][cell["id"]], len(rule["points_m"]))
            powers[cell["id"]] = float(np.dot(rule["weights_m3"], gamma[cell["material_id"]]*np.sum(abs(e)**2, axis=1)))
        flux = {}
        for key, rule in geometry["boundary_faces"].items():
            item = fields["boundary_faces"][key]
            _require(isinstance(item, dict) and set(item) == {"e", "h"}, "Boundary E and H required")
            e, h = _vectors(item["e"], 16), _vectors(item["h"], 16)
            poynting = np.cross(e, h.conjugate()).real@np.array(rule["outward_normal"])
            flux[key] = float(np.dot(rule["weights_m2"], poynting))
    incoming = -math.fsum(flux[key] for key in port_faces)
    outward = math.fsum(value for key, value in flux.items() if key not in port_faces)
    body = math.fsum(powers.values())
    scale = max(abs(incoming), abs(outward)+body, np.finfo(float).tiny)
    _require(all(math.isfinite(v) for v in (incoming, outward, body, scale)) and incoming > 0 and body >= 0,
             "Invalid raw volume/port power")
    _require(outward >= -TOLERANCE*scale and abs(incoming-outward-body) <= TOLERANCE*scale,
             "Raw Poynting/volume-loss closure failed; cannot calibrate")
    power_scale = accepted/incoming
    _require(math.isfinite(power_scale) and power_scale > 0, "Invalid field power scale")
    data = validate_request(thermal)
    density = {cell["id"]: powers[cell["id"]]*power_scale/volume
               for cell, (volume, _) in zip(cells, data["geometry"])}
    poll()
    heat = run_assembly_tetra_thermal({**deepcopy(thermal), "heat_sources_w_m3": density})
    deposited = body*power_scale
    _require(abs(heat["heat_balance"]["source_w"]-deposited) <= TOLERANCE*max(deposited, np.finfo(float).tiny), "Conservative thermal source transfer failed")
    result = {"contract": "spike/em-body-heating-result/v1", "model_status": "experimental", "production_qualified": False,
        "input_digest": _digest(raw), "source_binding": binding, "ac": ac, "thermal": heat,
        "source_authenticity_verified": False, "shared_solver_mesh_verified": False,
        "field_power_scale": power_scale, "field_amplitude_scale_to_rms": math.sqrt(power_scale),
        "raw_balance_error": abs(incoming-outward-body)/scale,
        "accepted_port_power_w": accepted, "deposited_body_power_w": deposited,
        "nonport_outward_power_w": outward*power_scale, "cell_heat_sources_w_m3": density,
        "limitations": ["Single exterior source port, supplied same-state E/H and isotropic electric volume loss only",
            "No PEC heating, magnetic/surface losses, internal lumped-port calibration, radiation-to-heat or remeshing",
            "Sampling mesh identity is checked; equality to an interpolator's FE mesh is not verified",
            "Retained packet binding prevents accidental stale use; it is not an authenticated solver attestation",
            "Power calibration/closure does not establish material accuracy, Maxwell convergence or measured correlation"]}
    _require(len(json.dumps(result, allow_nan=False).encode()) <= 16*1024**2, "Result exceeds 16 MiB")
    poll()
    return result
