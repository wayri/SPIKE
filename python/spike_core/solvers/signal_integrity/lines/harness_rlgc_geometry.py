# SPDX-License-Identifier: Apache-2.0
"""Approximate image-line RLGC for explicit, straight solid round conductors.

Independent SPIKE derivation/code; no external implementation was consulted.
With exp(+jwt), radial diffusion gives E(r)=A I0(k r), k^2=jw mu sigma.
Integrating sigma E over the disk gives Zint=k I0(ka)/(2 pi a sigma I1(ka)).
Its DC limits are R=1/(pi a^2 sigma), Lint=mu/(8 pi). The image-line
potential coefficients give Lext=mu0/(2pi) log(Dimage/Ddirect) and
C=mu0 epsilon inv(Lext). These are thin-wire, not exact cylinder arrays.

Method references (equations and public APIs only):
https://web.mit.edu/6.013_book/www/chapter8/8.6.html (line images and thin wires)
https://web.mit.edu/6.013_book/www/chapter14/14.2.html (TEM duality)
https://web.mit.edu/6.013_book/www/chapter10/10.7.html (magnetic diffusion)
https://dlmf.nist.gov/10.25 (modified Bessel equation and series)
https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.ive.html
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np
from scipy.special import ive

MU0 = 4e-7 * math.pi
EPSILON0 = 1 / (MU0 * 299792458.0**2)
CONTRACT = "spike/harness-round-wire-rlgc/v1"
MAX_WIRES = 16
MAX_FREQUENCIES = 257
MAX_SLENDERNESS = 0.05
MAX_TRANSVERSE_WAVELENGTH_RATIO = 0.05
MAX_CONDITION = 1e8
LIMITATIONS = [
    "Approximate thin-wire image model above an explicit ideal infinite grounded plane; not CAD or full-wave extraction.",
    "Straight parallel solid nonmagnetic round wires in one homogeneous dielectric only; no insulation layers, bends, helices, strands or shields.",
    "Internal skin effect is included; proximity current redistribution, plane loss and surface roughness are not included.",
    "Geometry and wavelength admission limits are conservative model gates, not a guaranteed physical error bound.",
    "Constant material properties and loss tangent describe only the supplied sweep; no broadband causality or thermal/material qualification.",
    "No radiation, connector launch, EMI compliance or production qualification; knowledgeable human numerical review is required before release.",
]


def _fields(value, required, optional, label):
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"HARNESS_RLGC_INPUT: {label} must be an object.")
    missing, unknown = required - value.keys(), value.keys() - required - optional
    if missing or unknown:
        raise ValueError(f"HARNESS_RLGC_INPUT: {label} missing {sorted(missing)}, unknown {sorted(unknown)}.")


def _number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HARNESS_RLGC_INPUT: {label} must be a finite number.")
    try:
        admitted = math.isfinite(value) and low <= value <= high
    except OverflowError:
        admitted = False
    if not admitted:
        raise ValueError(f"HARNESS_RLGC_INPUT: {label} must be within [{low}, {high}].")
    return float(value)


def _identity(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"HARNESS_RLGC_INPUT: {label} must be a nonempty string of at most 256 characters.")


def _request(raw):
    _fields(raw, {"contract", "wires", "dielectric", "frequency_hz", "reference_plane", "provenance"},
            {"harness_id", "occurrence_id"}, "request")
    if raw["contract"] != CONTRACT:
        raise ValueError("HARNESS_RLGC_INPUT: unsupported request contract.")
    for key in ("harness_id", "occurrence_id"):
        if key in raw:
            _identity(raw[key], key)
    wires = raw["wires"]
    if not isinstance(wires, list) or not 1 <= len(wires) <= MAX_WIRES:
        raise ValueError("HARNESS_RLGC_INPUT: require 1..16 wires.")
    for wire in wires:
        _fields(wire, {"wire_id", "x_m", "height_m", "radius_m", "conductivity_s_m", "relative_permeability"},
                {"role", "occurrence_id"}, "wire")
        for key in ("wire_id", "role", "occurrence_id"):
            if key in wire:
                _identity(wire[key], key)
        for key, low, high in (("x_m", -100, 100), ("height_m", 1e-6, 100),
                               ("radius_m", 1e-7, 0.1), ("conductivity_s_m", 1e4, 1e9),
                               ("relative_permeability", 1e-3, 1e4)):
            _number(wire[key], low, high, key)
    if len({w["wire_id"] for w in wires}) != len(wires):
        raise ValueError("HARNESS_RLGC_INPUT: wire_id values must be unique.")
    _fields(raw["dielectric"], {"relative_permittivity", "loss_tangent"}, set(), "dielectric")
    _number(raw["dielectric"]["relative_permittivity"], 1, 100, "relative_permittivity")
    _number(raw["dielectric"]["loss_tangent"], 0, 0.1, "loss_tangent")
    _fields(raw["reference_plane"], {"kind"}, set(), "reference_plane")
    _identity(raw["reference_plane"]["kind"], "reference_plane.kind")
    frequency = raw["frequency_hz"]
    if not isinstance(frequency, list) or not 1 <= len(frequency) <= MAX_FREQUENCIES:
        raise ValueError("HARNESS_RLGC_INPUT: require 1..257 frequency samples.")
    for f in frequency:
        _number(f, 0, 1e10, "frequency_hz")
    if any(b <= a for a, b in zip(frequency, frequency[1:])):
        raise ValueError("HARNESS_RLGC_INPUT: frequencies must be strictly increasing; DC is supported.")
    if not isinstance(raw["provenance"], dict) or not raw["provenance"]:
        raise ValueError("HARNESS_RLGC_INPUT: explicit nonempty provenance is required.")
    try:
        encoded = json.dumps(raw, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("HARNESS_RLGC_INPUT: request must contain finite JSON data.") from exc
    if len(encoded.encode("utf-8")) > 128 * 1024:
        raise ValueError("HARNESS_RLGC_INPUT: request exceeds 128 KiB.")
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cancel(cancel_check):
    if cancel_check and cancel_check():
        raise ValueError("HARNESS_RLGC_CANCELLED: extraction cancelled; no partial result.")


def _unsupported(out, code, message):
    return {**out, "status": "unsupported", "model_status": "unsupported",
            "issues": [{"code": code, "severity": "error", "message": message}]}


def _external(wires):
    n = len(wires)
    matrix = np.empty((n, n))
    slenderness = 0.0
    for i, wire in enumerate(wires):
        a, h = wire["radius_m"], wire["height_m"]
        slenderness = max(slenderness, a / h)
        matrix[i, i] = MU0 / (2 * math.pi) * math.log(2 * h / a)
        for j in range(i):
            other = wires[j]
            dx = wire["x_m"] - other["x_m"]
            direct = math.hypot(dx, h - other["height_m"])
            if direct <= a + other["radius_m"]:
                return None, 1.0
            slenderness = max(slenderness, max(a, other["radius_m"]) / direct)
            # log1p avoids loss of all coupling for distant unequal-height wires.
            logarithm = 0.5 * math.log1p(4 * h * other["height_m"] / direct**2)
            matrix[i, j] = matrix[j, i] = MU0 / (2 * math.pi) * logarithm
    return matrix, slenderness


def _internal_impedance(frequency, wire):
    """Return R and Lint with stable small-argument series and exact DC limit."""
    radius, sigma = wire["radius_m"], wire["conductivity_s_m"]
    mu = MU0 * wire["relative_permeability"]
    rdc = 1 / (math.pi * radius**2 * sigma)
    omega = 2 * math.pi * frequency
    t = omega * mu * sigma * radius**2
    # z I0(z)/(2 I1(z)) = 1+z^2/8-z^4/192+z^6/3072+O(z^8).
    # Separate real/imag terms avoid cancellation as omega approaches zero.
    if t <= 1e-4:
        return rdc * (1 + t**2 / 192), mu / (8 * math.pi) * (1 - t**2 / 384)
    z = complex(1, 1) * math.sqrt(t / 2)
    impedance = rdc * z / 2 * (ive(0, z) / ive(1, z))
    return float(impedance.real), float(impedance.imag / omega)


def extract_parallel_round_rlgc(request, *, cancel_check=None):
    """Return geometry-derived sampled RLGC or fail-closed unsupported status.

    All coordinates are meters; height is the center distance from plane y=0.
    Positive currents run in the same axial direction and voltages reference
    the plane. Returned arrays have shape [frequency, wire, wire]. Role and
    occurrence labels are retained, never interpreted as an electrical return.
    """
    _cancel(cancel_check)
    digest = _request(request)
    wires, frequency = request["wires"], request["frequency_hz"]
    out = {"contract": "spike/harness-round-wire-rlgc-result/v1", "status": "completed",
           "model_status": "approximate", "production_qualified": False,
           "field_coupling_executed": False, "geometry_rlgc_executed": False,
           "request_digest": digest, "request_snapshot": copy.deepcopy(request),
           "wire_metadata": [{k: copy.deepcopy(w[k]) for k in ("wire_id", "role", "occurrence_id") if k in w}
                             for w in wires], "provenance": copy.deepcopy(request["provenance"]),
           "limitations": list(LIMITATIONS), "issues": []}
    for key in ("harness_id", "occurrence_id"):
        if key in request:
            out[key] = request[key]
    if request["reference_plane"]["kind"] != "ideal_infinite_ground_plane":
        return _unsupported(out, "HARNESS_RLGC_REFERENCE", "Only an explicit ideal infinite grounded reference plane is supported.")
    if any(w["relative_permeability"] != 1 for w in wires):
        return _unsupported(out, "HARNESS_RLGC_MAGNETIC", "Only relative_permeability=1 is admitted; magnetic material dispersion and field redistribution are unsupported.")
    external, slenderness = _external(wires)
    width = max(w["x_m"] + w["radius_m"] for w in wires) - min(w["x_m"] - w["radius_m"] for w in wires)
    transverse = math.hypot(width, 2 * max(w["height_m"] + w["radius_m"] for w in wires))
    epsilon = EPSILON0 * request["dielectric"]["relative_permittivity"]
    wavelength_ratio = transverse * frequency[-1] * math.sqrt(MU0 * epsilon)
    out["admission"] = {"max_radius_to_height_or_spacing": slenderness,
                        "slenderness_limit": MAX_SLENDERNESS, "transverse_dimension_m": transverse,
                        "max_transverse_to_wavelength": wavelength_ratio,
                        "transverse_to_wavelength_limit": MAX_TRANSVERSE_WAVELENGTH_RATIO}
    if external is None or slenderness > MAX_SLENDERNESS:
        return _unsupported(out, "HARNESS_RLGC_SLENDERNESS", "Require a/h <= 0.05 and max(a_i,a_j)/center_spacing <= 0.05 for all wires.")
    if wavelength_ratio > MAX_TRANSVERSE_WAVELENGTH_RATIO:
        return _unsupported(out, "HARNESS_RLGC_QUASI_TEM", "Cross section including plane images must be at most 0.05 dielectric wavelengths across.")
    condition = float(np.linalg.cond(external))
    out["admission"]["external_inductance_condition"] = condition
    if not math.isfinite(condition) or condition > MAX_CONDITION or np.min(np.linalg.eigvalsh(external)) <= 0:
        return _unsupported(out, "HARNESS_RLGC_CONDITION", "External inductance is not sufficiently well-conditioned positive definite.")
    capacitance = MU0 * epsilon * np.linalg.solve(external, np.eye(len(wires)))
    capacitance = (capacitance + capacitance.T) / 2
    if np.min(np.linalg.eigvalsh(capacitance)) <= 0:
        return _unsupported(out, "HARNESS_RLGC_ENERGY", "Capacitance failed positive energy admission.")
    model = {"wire_ids": [w["wire_id"] for w in wires], "frequency_hz": list(frequency),
             "r_ohm_per_m": [], "l_h_per_m": [], "g_s_per_m": [], "c_f_per_m": [],
             "provenance": {"source": "SPIKE thin-wire image-plane geometry extraction", "request_digest": digest,
                            "model_status": "approximate", "input_provenance": copy.deepcopy(request["provenance"])}}
    for f in frequency:
        _cancel(cancel_check)
        resistance, internal = np.array([_internal_impedance(f, w) for w in wires]).T
        if not np.all(np.isfinite(resistance)) or not np.all(np.isfinite(internal)) or np.min(resistance) <= 0 or np.min(internal) <= 0:
            return _unsupported(out, "HARNESS_RLGC_INTERNAL", "Internal impedance failed finite/passive admission.")
        model["r_ohm_per_m"].append(np.diag(resistance).tolist())
        model["l_h_per_m"].append((external + np.diag(internal)).tolist())
        model["g_s_per_m"].append((2 * math.pi * f * request["dielectric"]["loss_tangent"] * capacitance).tolist())
        model["c_f_per_m"].append(capacitance.tolist())
    _cancel(cancel_check)
    out.update(model=model, geometry_rlgc_executed=True, external_inductance_h_per_m=external.tolist())
    return out
