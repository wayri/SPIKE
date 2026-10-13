# SPDX-License-Identifier: Apache-2.0
"""Bound explicit harness modes to the existing uniform RLGC network kernel.

The caller supplies a complete loop/modal model. Harness routes and twist
metadata are provenance only: no field extraction or common mode is inferred.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator

from .harness import analyze_harness, terminal_key, validate_harness

MAX_EM_GEOMETRY_POINTS = 100_000
MAX_EM_HANDOFF_BYTES = 16 * 1024 * 1024


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _request(raw, name):
    if len(json.dumps(raw, allow_nan=False).encode()) > 8 * 1024 * 1024:
        raise ValueError("Harness analysis request exceeds 8 MiB.")
    path = Path(__file__).resolve().parents[2] / f"schemas/{name}-request-v1.schema.json"
    error = next(Draft202012Validator(json.loads(path.read_text(encoding="utf-8"))).iter_errors(raw), None)
    if error:
        raise ValueError(f"Invalid harness analysis at {list(error.path)}: {error.message}")
    data = validate_harness(raw["harness"])
    report = analyze_harness(data)
    if report["status"] != "valid":
        raise ValueError("HARNESS_ANALYSIS_CONNECTIVITY: " + "; ".join(i["message"] for i in report["issues"]))
    return data, report


def compile_harness_si(raw):
    """Admit a single explicit two-conductor mode, without hidden RLGC defaults."""
    data, report = _request(raw, "harness-si")
    wires = {wire["id"]: wire for wire in data["wires"]}
    selection = raw["selection"]
    if "pair_id" in selection:
        pair = next((p for p in data.get("pairs", []) if p["id"] == selection["pair_id"]), None)
        if pair is None or pair["kind"] != "differential":
            raise ValueError("HARNESS_SI_PAIR: select an explicit differential pair.")
        ids, mode = pair["wire_ids"], "differential"
    else:
        ids = [selection["signal_wire_id"], selection["return_wire_id"]]
        mode = "single_ended"
        if any(key not in wires for key in ids) or wires[ids[0]].get("role") != "signal" or wires[ids[1]].get("role") != "return":
            raise ValueError("HARNESS_SI_RETURN: select explicit signal and return role wires.")
        if wires[ids[0]].get("return_wire_id", ids[1]) != ids[1]:
            raise ValueError("HARNESS_SI_RETURN: selected return conflicts with the retained reference.")
    selected = [wires[key] for key in ids]
    ends = [{terminal_key(w["from"]), terminal_key(w["to"])} for w in selected]
    if ends[0] & ends[1]:
        raise ValueError("HARNESS_SI_SHORT: signal and return/pair legs must be separate terminals.")
    spans = [{end.get("connector") for end in (w["from"], w["to"])} for w in selected]
    if spans[0] != spans[1] or None in spans[0] or len(spans[0]) != 2:
        raise ValueError("HARNESS_SI_ENDPOINTS: both conductors must span the same two connectors.")
    for network in report["networks"]:
        if set(network["wire_ids"]) & set(ids) and len(network["wire_ids"]) != 1:
            raise ValueError("HARNESS_SI_BRANCH: uniform two-port models exclude shorts, splices and parallel/stub branches.")
    length = raw["model"]["length_m"]
    if any("length_mm" not in w or not math.isclose(w["length_mm"] * .001, length, rel_tol=1e-9, abs_tol=1e-12) for w in selected):
        raise ValueError("HARNESS_SI_LENGTH: both conductor cut lengths must match the supplied uniform model length.")
    return {"harness_digest": report["harness_digest"], "request_digest": _digest(raw),
            "mode": mode, "wire_ids": list(ids), "model": copy.deepcopy(raw["model"]),
            "port_bindings": [{"positive": copy.deepcopy(selected[0][end]),
                               "negative": copy.deepcopy(next(e for e in (selected[1]["from"], selected[1]["to"])
                                                        if e["connector"] == selected[0][end]["connector"]))}
                              for end in ("from", "to")]}


def run_harness_si(raw, *, cancel_check=None):
    """Compute the supplied loop/modal RLGC network; preserve its limited scope."""
    if cancel_check and cancel_check():
        raise ValueError("Harness SI execution cancelled.")
    compiled = compile_harness_si(raw)
    from .si_network_workflow import acquire_network
    network, _ = acquire_network(compiled["model"])
    if cancel_check and cancel_check():
        raise ValueError("Harness SI execution cancelled; result discarded.")
    s = network.s_parameters()
    return {"contract": "spike/harness-si-result/v1", "status": "completed", "model_status": "experimental",
            "production_qualified": False, "field_coupling_executed": False,
            **{key: value for key, value in compiled.items() if key != "model"},
            "frequency_hz": network.frequencies_hz.tolist(), "s_real": s.real.tolist(), "s_imag": s.imag.tolist(),
            "reference_impedance_ohm": network.reference_impedance_ohm.tolist(),
            "provenance": copy.deepcopy(raw["provenance"]),
            "request_snapshot": copy.deepcopy(raw),
            "limitations": ["Explicit uniform two-port loop/modal RLGC only; differential mode has no common-mode conversion or crosstalk.",
                            "Both conductors and their return loss/coupling must already be included in the supplied model.",
                            "Twist pitch, shield, route geometry and connector contacts are not extracted or added to the supplied model.",
                            "No full-wave radiation or EMI compliance result."]}


def prepare_harness_em(raw):
    """Retain explicit route geometry with fail-closed EM solver admission."""
    data, report = _request(raw, "harness-em")
    wires = {wire["id"]: wire for wire in data["wires"]}
    routes = {route["id"]: route for route in data["routes"]}
    ids = raw["wire_ids"]
    if any(key not in wires for key in ids):
        raise ValueError("HARNESS_EM_WIRE: selected wire does not exist.")
    # The input byte limit does not bound output: thousands of wires can share
    # one long route, which the compatibility handoff embeds once per wire.
    # Check point copies and a conservative serialized-output budget before
    # deepcopy. Include route properties/extensions as well as point arrays.
    points = 0
    route_sizes = {}
    output_bytes = len(json.dumps(data, allow_nan=False).encode()) + 4096
    for key in ids:
        wire = wires[key]
        route = routes.get(wire.get("route_id"))
        # wire_id appears in the wrapper and up to two diagnostics in addition
        # to the wire record already counted in data. JSON escaping matters.
        output_bytes += 1024 + 3 * len(json.dumps(key).encode())
        if route is not None:
            points += len(route["points_mm"])
            if points > MAX_EM_GEOMETRY_POINTS:
                raise ValueError("HARNESS_EM_OUTPUT_LIMIT: repeated conductor geometry exceeds 100000 route points.")
            if route["id"] not in route_sizes:
                route_sizes[route["id"]] = len(json.dumps(route, allow_nan=False).encode())
            output_bytes += route_sizes[route["id"]]
        if output_bytes > MAX_EM_HANDOFF_BYTES:
            raise ValueError("HARNESS_EM_OUTPUT_LIMIT: projected geometry handoff exceeds 16 MiB.")
    issues = [{"code": "HARNESS_EM_SOLVER_UNAVAILABLE", "severity": "error",
               "message": "No qualified harness conductor/twist field translator is available; routes are not an EM solve."}]
    issues.extend({"code": code, "severity": "error", "message": message} for code, message in (
        ("HARNESS_EM_EXCITATION_REQUIRED", "A future field solver must bind frequency-dependent conductor currents or explicit ports and returns."),
        ("HARNESS_EM_MATERIAL_REQUIRED", "A future field solver must bind conductor, insulation, shield and surrounding material models."),
        ("HARNESS_EM_BOUNDARY_REQUIRED", "A future field solver must bind the domain, field boundaries and return/termination conditions.")))
    geometry = []
    for key in ids:
        wire = wires[key]
        route = routes.get(wire.get("route_id"))
        if route is None or not route.get("frame_id"):
            issues.append({"code": "HARNESS_EM_GEOMETRY_REQUIRED", "severity": "error", "id": key,
                           "message": "An explicit conductor route and coordinate frame are required."})
        if not wire.get("area_mm2"):
            issues.append({"code": "HARNESS_EM_SECTION_REQUIRED", "severity": "error", "id": key,
                           "message": "Conductor cross section is missing; no radius is inferred."})
        geometry.append({"wire_id": key, "wire": copy.deepcopy(wire), "route": copy.deepcopy(route)})
    return {"contract": "spike/harness-em-handoff/v1", "status": "unsupported", "model_status": "unsupported",
            "production_qualified": False, "field_coupling_executed": False,
            "harness_digest": report["harness_digest"], "request_digest": _digest(raw), "geometry": geometry,
            "pairs": copy.deepcopy(data.get("pairs", [])), "cables": copy.deepcopy(data["cables"]), "issues": issues,
            "limitations": ["Route polylines can be bundle centerlines; they do not establish individual conductor or helical geometry.",
                            "Excitation, material, shield, dielectric, termination and field boundary models require an explicit future solver contract."]}
