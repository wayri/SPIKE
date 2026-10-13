# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Yawar B and SPIKE contributors.
"""Bounded frequency-domain branched multiconductor transmission-line networks.

Independently derived telegrapher transfer constraints, stamped into MNA.
Coordinates are explicit conductor potentials relative to one ideal reference;
geometry, causality and board fields are not inferred from supplied RLGC.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np
from scipy.linalg import expm

CONTRACT = "spike/harness-mtl-request/v1"
MAX_UNKNOWNS = 256
MAX_WORK = 100_000_000
MAX_RESPONSE_SAMPLES = 131_072
CURRENT_SCALE_OHM = 50.0


def _object(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("HARNESS_MTL_CONTRACT: missing or unknown fields")
    return value


def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or value != value.strip():
        raise ValueError("HARNESS_MTL_ID: expected bounded nonempty identifier")
    return value


def _number(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("HARNESS_MTL_NUMBER: expected finite real value")
    try:
        value = float(value)
    except OverflowError as exc:
        raise ValueError("HARNESS_MTL_NUMBER: unrepresentable real value") from exc
    if not math.isfinite(value):
        raise ValueError("HARNESS_MTL_NUMBER: expected finite real value")
    if value < 0 or (positive and value == 0):
        raise ValueError("HARNESS_MTL_NUMBER: expected positive/nonnegative value")
    return float(value)


def _rows(value, maximum, label, *, empty=False):
    if not isinstance(value, list) or len(value) > maximum or (not value and not empty):
        raise ValueError("HARNESS_MTL_RESOURCE: invalid " + label + " count")
    return value


def _incidence(positive, negative, indices, reference, count):
    _name(positive)
    _name(negative)
    if positive == negative or positive not in {*indices, reference} or negative not in {*indices, reference}:
        raise ValueError("HARNESS_MTL_ENDPOINT: unknown or shorted terminal pair")
    vector = np.zeros(count)
    if positive != reference:
        vector[indices[positive]] += 1
    if negative != reference:
        vector[indices[negative]] -= 1
    return vector


def _conductor_terminal(node, indices, reference, count):
    """A conductor endpoint may have prescribed zero reference potential."""
    _name(node)
    if node == reference:
        return np.zeros(count)
    return _incidence(node, reference, indices, reference, count)


def _model(raw, wire_ids, frequencies):
    _object(raw, ("wire_ids", "frequency_hz", "r_ohm_per_m", "l_h_per_m",
                  "g_s_per_m", "c_f_per_m", "provenance"))
    for frequency in _rows(raw["frequency_hz"], 257, "model frequency"):
        _number(frequency)
    if raw["wire_ids"] != wire_ids or raw["frequency_hz"] != frequencies or not isinstance(raw["provenance"], dict) or not raw["provenance"]:
        raise ValueError("HARNESS_MTL_MODEL: exact wire order, sweep and provenance required")
    count = len(wire_ids)
    result = {}
    for key in ("r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"):
        raw_array = np.asarray(raw[key], dtype=object)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in raw_array.flat):
            raise ValueError("HARNESS_MTL_MODEL: matrices require real JSON numbers")
        try:
            a = np.asarray(raw_array, dtype=float)
        except (OverflowError, ValueError, TypeError) as exc:
            raise ValueError("HARNESS_MTL_MODEL: unrepresentable matrix values") from exc
        if a.shape != (len(frequencies), count, count) or not np.isfinite(a).all():
            raise ValueError("HARNESS_MTL_MODEL: invalid matrix shape or values")
        scale = np.max(np.abs(a), axis=(1, 2))
        symmetry = np.max(np.abs(a - a.transpose(0, 2, 1)), axis=(1, 2))
        if np.any(symmetry > 1e-12 * scale):
            raise ValueError("HARNESS_MTL_RECIPROCITY: nonsymmetric RLGC")
        # Never repair a negative-energy input by clipping eigenvalues.
        try:
            eigenvalues = np.linalg.eigvalsh(a)
        except np.linalg.LinAlgError as exc:
            raise ValueError("HARNESS_MTL_CONDITION: matrix energy assessment failed") from exc
        if not np.isfinite(eigenvalues).all():
            raise ValueError("HARNESS_MTL_CONDITION: nonfinite matrix energy assessment")
        if np.any(eigenvalues < 0) or (key in {"l_h_per_m", "c_f_per_m"} and np.any(eigenvalues <= 0)):
            raise ValueError("HARNESS_MTL_ENERGY: matrices must be positive (semi)definite")
        result[key] = a
    return result


def run_harness_mtl(raw, *, cancel_check=None):
    """Return power-wave S[receiver,source], with every branch bound explicitly.

    R/L/G/C are exact sampled real symmetric matrices in SI units. All line
    reference conductors share the explicitly named ideal reference node.
    Contact elements are series R-L; termination elements are parallel G-C.
    Ports use positive real power-wave references. No interpolation is done.
    """
    if cancel_check and cancel_check():
        raise ValueError("HARNESS_MTL_CANCELLED: result discarded")
    _object(raw, ("contract", "reference_node", "nodes", "segments", "ports",
                  "frequency_hz", "contacts", "terminations", "provenance"), ("mixed_mode_pairs",))
    if raw["contract"] != CONTRACT:
        raise ValueError("HARNESS_MTL_CONTRACT: unsupported contract")
    if len(json.dumps(raw, allow_nan=False).encode()) > 8 * 1024 * 1024:
        raise ValueError("HARNESS_MTL_RESOURCE: request exceeds 8 MiB")
    if not isinstance(raw["provenance"], dict) or not raw["provenance"]:
        raise ValueError("HARNESS_MTL_PROVENANCE: explicit model origin required")
    frequencies = _rows(raw["frequency_hz"], 257, "frequency")
    values = [_number(f) for f in frequencies]
    if any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError("HARNESS_MTL_FREQUENCY: sweep must strictly increase; DC allowed")
    reference = _name(raw["reference_node"])
    nodes = _rows(raw["nodes"], 128, "node")
    for node in nodes:
        _object(node, ("id",), ("occurrence_id", "terminal_id", "wire_id"))
        for value in node.values():
            _name(value)
    names = [node["id"] for node in nodes]
    if reference in names or len(set(names)) != len(names):
        raise ValueError("HARNESS_MTL_ID: duplicate node or reference included in unknowns")
    indices = {name: i for i, name in enumerate(names)}
    n = len(nodes)
    segments = _rows(raw["segments"], 32, "segment", empty=True)
    contacts = _rows(raw["contacts"], 128, "contact", empty=True)
    terminations = _rows(raw["terminations"], 128, "termination", empty=True)
    ports = _rows(raw["ports"], 32, "port")
    identifiers = []
    compiled = []
    unknowns = n
    for segment in segments:
        _object(segment, ("id", "wire_ids", "from_nodes", "to_nodes", "length_m", "model"))
        identifiers.append(_name(segment["id"]))
        wires = _rows(segment["wire_ids"], 16, "conductor")
        if len(set(map(_name, wires))) != len(wires):
            raise ValueError("HARNESS_MTL_ID: duplicate conductor within segment")
        k = len(wires)
        ends = []
        for key in ("from_nodes", "to_nodes"):
            _rows(segment[key], 16, "terminal")
            for node in segment[key]:
                _name(node)
            if len(segment[key]) != k or len(set(segment[key])) != k:
                raise ValueError("HARNESS_MTL_ENDPOINT: one distinct node per conductor required")
            ends.append(np.array([_conductor_terminal(node, indices, reference, n) for node in segment[key]]).T)
        compiled.append((segment, ends, unknowns, _number(segment["length_m"], positive=True),
                         _model(segment["model"], wires, frequencies)))
        unknowns += 2 * k
    compiled_contacts, compiled_terminations, compiled_ports = [], [], []
    for element in contacts:
        _object(element, ("id", "positive_node", "negative_node", "resistance_ohm", "inductance_h", "provenance"), ("wire_id", "occurrence_id"))
        identifiers.append(_name(element["id"]))
        b = _incidence(element["positive_node"], element["negative_node"], indices, reference, n)
        r, l = _number(element["resistance_ohm"]), _number(element["inductance_h"])
        compiled_contacts.append((b, unknowns, r, l))
        unknowns += 1
    for element in terminations:
        _object(element, ("id", "positive_node", "negative_node", "conductance_s", "capacitance_f", "provenance"), ("wire_id", "occurrence_id"))
        identifiers.append(_name(element["id"]))
        b = _incidence(element["positive_node"], element["negative_node"], indices, reference, n)
        compiled_terminations.append((b, _number(element["conductance_s"]), _number(element["capacitance_f"])))
    port_ids = []
    for port in ports:
        _object(port, ("id", "positive_node", "negative_node", "reference_impedance_ohm"), ("wire_id", "occurrence_id"))
        port_ids.append(_name(port["id"]))
        compiled_ports.append((_incidence(port["positive_node"], port["negative_node"], indices, reference, n),
                               _number(port["reference_impedance_ohm"], positive=True)))
    if len(set(identifiers)) != len(identifiers) or len(set(port_ids)) != len(port_ids):
        raise ValueError("HARNESS_MTL_ID: duplicate element or port identity")
    for element in [*contacts, *terminations]:
        if not isinstance(element["provenance"], dict) or not element["provenance"]:
            raise ValueError("HARNESS_MTL_PROVENANCE: each lumped model requires provenance")
        for key in ("wire_id", "occurrence_id"):
            if key in element:
                _name(element[key])
    for port in ports:
        for key in ("wire_id", "occurrence_id"):
            if key in port:
                _name(port[key])
    conductor_count = sum(len(segment["wire_ids"]) for segment in segments)
    mode_factor = 2 if raw.get("mixed_mode_pairs") else 1
    response_count = len(values) * (mode_factor*len(ports)**2 + 4*conductor_count*len(ports))
    if unknowns > MAX_UNKNOWNS or len(values) * unknowns ** 3 > MAX_WORK or response_count > MAX_RESPONSE_SAMPLES:
        raise ValueError("HARNESS_MTL_RESOURCE: dense work/output budget exceeded")
    transforms = None
    pairs = raw.get("mixed_mode_pairs", [])
    if pairs:
        _rows(pairs, 16, "mixed-mode pair")
        used = []
        for pair in pairs:
            if not isinstance(pair, list) or len(pair) != 2 or any(p not in port_ids for p in pair):
                raise ValueError("HARNESS_MTL_MODES: pair requires two existing ordered ports")
            used.extend(pair)
        if len(used) != len(ports) or len(set(used)) != len(used):
            raise ValueError("HARNESS_MTL_MODES: pairs must partition all ports")
        z = [p[1] for p in compiled_ports]
        if any(v != z[0] for v in z):
            raise ValueError("HARNESS_MTL_MODES: equal real references required")
        order = [port_ids.index(p) for p in used]
        transforms = order
    elif "mixed_mode_pairs" in raw and pairs != []:
        raise ValueError("HARNESS_MTL_MODES: invalid pair list")
    responses, residuals, conditions = [], [], []
    terminal_responses = [[] for _ in compiled]
    for f_index, frequency in enumerate(values):
        if cancel_check and cancel_check():
            raise ValueError("HARNESS_MTL_CANCELLED: result discarded")
        omega = 2 * math.pi * frequency
        if not math.isfinite(omega):
            raise ValueError("HARNESS_MTL_CONDITION: unrepresentable angular frequency")
        matrix = np.zeros((unknowns, unknowns), complex)
        rhs = np.zeros((unknowns, len(ports)), complex)
        for segment, (a, b), offset, length, model in compiled:
            k = a.shape[1]
            with np.errstate(over="ignore", invalid="ignore"):
                z = model["r_ohm_per_m"][f_index] + 1j * omega * model["l_h_per_m"][f_index]
                y = model["g_s_per_m"][f_index] + 1j * omega * model["c_f_per_m"][f_index]
                generator = np.block([[np.zeros((k, k)), -z / CURRENT_SCALE_OHM],
                                      [-CURRENT_SCALE_OHM * y, np.zeros((k, k))]]) * length
                norm = np.linalg.norm(generator, np.inf)
            if not np.isfinite(generator).all() or norm > 50:
                raise ValueError("HARNESS_MTL_CONDITION: electrical segment too long; subdivide explicitly")
            transfer = expm(generator)
            ia, ib = slice(offset, offset+k), slice(offset+k, offset+2*k)
            matrix[:n, ia] += a
            matrix[:n, ib] -= b
            matrix[ia, :n] = b.T - transfer[:k, :k] @ a.T
            matrix[ia, ia] = -transfer[:k, k:]
            matrix[ib, :n] = -transfer[k:, :k] @ a.T
            matrix[ib, ia] = -transfer[k:, k:]
            matrix[ib, ib] = np.eye(k)
        for b, offset, r, l in compiled_contacts:
            matrix[:n, offset] += b
            matrix[offset, :n] = b
            matrix[offset, offset] = -(r + 1j * omega * l) / CURRENT_SCALE_OHM
        for b, g, c in compiled_terminations:
            with np.errstate(over="ignore", invalid="ignore"):
                matrix[:n, :n] += CURRENT_SCALE_OHM * (g + 1j * omega * c) * np.outer(b, b)
        for index, (b, reference_ohm) in enumerate(compiled_ports):
            with np.errstate(over="ignore", invalid="ignore"):
                matrix[:n, :n] += CURRENT_SCALE_OHM / reference_ohm * np.outer(b, b)
            rhs[:n, index] = 2 * CURRENT_SCALE_OHM / math.sqrt(reference_ohm) * b
        if not np.isfinite(matrix).all() or not np.isfinite(rhs).all():
            raise ValueError("HARNESS_MTL_CONDITION: nonfinite assembled system")
        try:
            condition = float(np.linalg.cond(matrix))
        except np.linalg.LinAlgError as exc:
            raise ValueError("HARNESS_MTL_CONDITION: condition assessment failed") from exc
        if not math.isfinite(condition) or condition > 1e12:
            raise ValueError("HARNESS_MTL_CONDITION: singular/ill-conditioned network")
        try:
            solution = np.linalg.solve(matrix, rhs)
        except np.linalg.LinAlgError as exc:
            raise ValueError("HARNESS_MTL_CONDITION: linear solve failed") from exc
        residual = float(np.linalg.norm(matrix @ solution-rhs) / max(np.linalg.norm(rhs), np.finfo(float).tiny))
        s = np.array([b @ solution[:n] / math.sqrt(z0) for b, z0 in compiled_ports]) - np.eye(len(ports))
        if not np.isfinite(s).all() or residual > 1e-10:
            raise ValueError("HARNESS_MTL_RESIDUAL: nonfinite or inaccurate solve")
        if np.linalg.svd(s, compute_uv=False)[0] > 1 + 1e-8 or np.max(np.abs(s-s.T)) > 1e-8:
            raise ValueError("HARNESS_MTL_QUALITY: passivity or reciprocity check failed")
        responses.append(s)
        for i, (segment, (a, b), offset, _, _) in enumerate(compiled):
            k = len(segment["wire_ids"])
            terminal_responses[i].append((a.T @ solution[:n], b.T @ solution[:n],
                                         solution[offset:offset+k] / CURRENT_SCALE_OHM,
                                         -solution[offset+k:offset+2*k] / CURRENT_SCALE_OHM))
        residuals.append(residual)
        conditions.append(condition)
    s = np.asarray(responses)
    output = {"contract": "spike/harness-mtl-result/v1", "status": "completed", "model_status": "experimental",
              "production_qualified": False, "field_coupling_executed": False,
              "request_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
              "frequency_hz": values, "reference_node": reference, "nodes": copy.deepcopy(nodes),
              "ports": copy.deepcopy(ports), "segments": [{k: copy.deepcopy(v) for k, v in segment.items() if k != "model"} for segment in segments],
              "contacts": copy.deepcopy(contacts), "terminations": copy.deepcopy(terminations),
              "s_real": s.real.tolist(), "s_imag": s.imag.tolist(), "provenance": copy.deepcopy(raw["provenance"]),
              "quality": {"relative_residual": residuals, "condition_number": conditions,
                          "maximum_singular_value": np.linalg.svd(s, compute_uv=False)[:, 0].tolist(),
                          "reciprocity_max_abs": float(np.max(np.abs(s-s.transpose(0, 2, 1)))), "causality": "not_qualified"},
              "limitations": ["Common ideal reference node; no physical shield transfer, board copper or radiation solve.",
                              "Sampled RLGC without interpolation; sampled passivity is not broadband causality qualification.",
                              "Lumped contacts are explicit series R-L; loads are explicit parallel G-C.",
                              "Physical routes, twisting, insulation interfaces and proximity effects are not inferred."]}
    for segment, response in zip(output["segments"], terminal_responses):
        original_model = next(s["model"] for s in segments if s["id"] == segment["id"])
        segment["model_provenance"] = copy.deepcopy(original_model["provenance"])
        segment["model_sha256"] = hashlib.sha256(json.dumps(original_model, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        segment["response_order"] = "frequency,wire,incident_port; unit incident power-wave amplitude sqrt(W)"
        segment["current_sign"] = "into segment at each end"
        for i, key in enumerate(("from_voltage_v", "to_voltage_v", "from_current_a", "to_current_a")):
            array = np.asarray(response)[:, i]
            segment[key] = {"real": array.real.tolist(), "imag": array.imag.tolist()}
    if transforms is not None:
        from .sparameters import single_ended_to_mixed_mode
        mixed = single_ended_to_mixed_mode(s[:, transforms][:, :, transforms])
        z0 = compiled_ports[0][1]
        output["mixed_mode"] = {"pairs": copy.deepcopy(pairs), "ordering": "D1..Dn,C1..Cn",
                                "reference_impedance_ohm": [2*z0]*len(pairs)+[z0/2]*len(pairs),
                                "s_real": mixed.real.tolist(), "s_imag": mixed.imag.tolist()}
    if len(json.dumps(output, allow_nan=False).encode()) > 16 * 1024 * 1024:
        raise ValueError("HARNESS_MTL_RESOURCE: result exceeds 16 MiB")
    if cancel_check and cancel_check():
        raise ValueError("HARNESS_MTL_CANCELLED: result discarded")
    return output
