# SPDX-License-Identifier: Apache-2.0
"""Bind sampled SI visualizations to current canonical geometry; no field inference."""
import hashlib
import json
import math

from .service_helpers import error_response
from .spider_v2 import SpiDeRV2


def inspect_si_spatial_context(params):
    required = {"design", "occurrence_id", "aggressor_net_id", "victim_net_id", "request_id"}
    if not isinstance(params, dict) or set(params) != required:
        raise ValueError("Spatial context requires exactly design, occurrence and net/request identities")
    for key in required - {"design"}:
        if not isinstance(params[key], str) or not 0 < len(params[key]) <= 512:
            raise ValueError(f"{key} must be a bounded nonempty identity")
    raw = params["design"]
    if not isinstance(raw, dict) or raw.get("contract") != "spike/design-ir/v2":
        raise ValueError("Spatial SI requires retained canonical DesignIR v2")
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf-8")) > 32 * 1024 * 1024:
        raise ValueError("Spatial SI design exceeds 32 MiB")
    design = SpiDeRV2.from_dict(raw)
    if design.frame.frame_id != "board" or design.frame.parent_frame_id or design.frame.transform != (
        1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.
    ):
        raise ValueError("Spatial SI currently requires the identity board coordinate frame")
    aggressor, victim = params["aggressor_net_id"], params["victim_net_id"]
    nets = {net.id for net in design.nets}
    if aggressor == victim or aggressor not in nets or victim not in nets:
        raise ValueError("Select two distinct canonical nets in this board")
    layers = {layer.id: layer for layer in design.layers}
    segments = []
    for track in design.tracks:
        if track.net_id != victim:
            continue
        layer = layers.get(track.layer_id)
        if layer is None or layer.layer_type != "copper":
            raise ValueError("Victim track has no canonical copper layer")
        start, end = list(track.start_mm), list(track.end_mm)
        if len(start) != 2 or len(end) != 2 or any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in [*start, *end, layer.z_mm]
        ):
            raise ValueError("Victim geometry requires finite millimetre coordinates")
        segments.append({"id": track.id, "occurrenceId": params["occurrence_id"],
                         "netId": victim, "startMm": [*start, layer.z_mm],
                         "endMm": [*end, layer.z_mm]})
    if len(segments) > 200000:
        raise ValueError("Spatial SI track inventory exceeds 200000 segments")
    return {"designId": design.design_id,
            "designDigest": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "requestId": params["request_id"], "occurrenceId": params["occurrence_id"],
            "aggressorNetId": aggressor, "victimNetId": victim, "traceSegments": segments}


def handle_si_spatial_request(params):
    try:
        return {"ok": True, "result": inspect_si_spatial_context(params)}
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "Spatial SI context failed admission.",
                              detail=str(exc), context={"method": "inspect_si_spatial_context"},
                              error_type=type(exc).__name__)


def run_si_spatial_pair(params):
    """Map actual uniform coupled-line voltage probes onto two explicitly assigned strokes.

    The line model is supplied, never inferred from the displayed PCB. No E field
    is constructed and no interpolation or radial noise halo is introduced.
    """
    context_keys = {"design", "occurrence_id", "aggressor_net_id", "victim_net_id", "request_id"}
    if not isinstance(params, dict) or set(params) != context_keys | {
        "pair_request", "aggressor_segment_id", "victim_segment_id"
    }:
        raise ValueError("Spatial pair requires context, pair_request and two segment identities")
    context = inspect_si_spatial_context({key: params[key] for key in context_keys})
    design = SpiDeRV2.from_dict(params["design"])
    tracks = {track.id: track for track in design.tracks}
    first, second = (tracks.get(params[key]) for key in ("aggressor_segment_id", "victim_segment_id"))
    if first is None or second is None or first.net_id != params["aggressor_net_id"] or second.net_id != params["victim_net_id"]:
        raise ValueError("Assigned strokes must belong to the selected aggressor and victim nets")
    if first.layer_id != second.layer_id:
        raise ValueError("Spatial pair currently requires two co-directed strokes on the same layer")
    delta = lambda track: [float(b) - float(a) for a, b in zip(track.start_mm, track.end_mm)]
    u, v = delta(first), delta(second)
    length = math.hypot(*u)
    if length <= 0 or not all(math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) for a, b in zip(u, v)):
        raise ValueError("Spatial pair requires equal-length co-directed straight strokes")
    separation = [float(b) - float(a) for a, b in zip(first.start_mm, second.start_mm)]
    if not math.isclose(sum(a*b for a, b in zip(u, separation)), 0., abs_tol=1e-8 * max(1., length)):
        raise ValueError("Spatial pair requires coextensive strokes, without longitudinal offset")
    if math.hypot(*separation) <= 0:
        raise ValueError("Spatial pair requires distinct strokes")
    request = params["pair_request"]
    if not isinstance(request, dict) or request.get("conductor_ids") != [first.net_id, second.net_id]:
        raise ValueError("Pair conductors must explicitly match aggressor then victim canonical identities")
    for mode in ("even", "odd"):
        mode_length = request.get("modes", {}).get(mode, {}).get("length_m")
        if type(mode_length) not in (int, float) or not math.isclose(mode_length, length / 1000., rel_tol=1e-9):
            raise ValueError("Supplied line length must equal the assigned strokes in metres")
    for excitation in request.get("excitations", []):
        waves = excitation.get("incident_waves", [])
        if len(waves) != 4 or any(waves[i] != {"real": 0., "imag": 0.} for i in (1, 3)):
            raise ValueError("Induced victim voltage requires zero incident victim waves at both ports")
    from .solvers.signal_integrity.lines.rlgc_coupled_pair import run_rlgc_coupled_pair
    solved = run_rlgc_coupled_pair(request)
    points = solved["points"]
    samples = []
    for index, probe in enumerate(request["probes"]):
        values = []
        for point in points:
            value = point["probe_values"][index]["conductors"][1]["voltage_v"]
            values.append([value["real"], value["imag"]])
        samples.append({"segmentId": second.id, "fraction": probe["fractional_position"],
                        "inducedVoltageV": values})
    data = {"contract": "spike/si-spatial-noise/v1", "status": "completed_with_warnings",
            "modelStatus": "experimental", "binding": {
                "sourceDesignId": context["designId"], "sourceDesignDigest": context["designDigest"],
                "requestId": context["requestId"], "occurrenceId": context["occurrenceId"],
                "aggressorNetId": first.net_id, "victimNetId": second.net_id},
            "sourceResult": {"contract": solved["contract"], "resultId": solved["network"]["id"],
                "rawPointer": "/points/*/probe_values/*/conductors/1/voltage_v",
                "inputDigest": solved["input_digest"], "modelScope": {
                    "basis": "provided_rlgc", "extracted": False,
                    "limitations": ["Supplied uniform symmetric even/odd line parameters; PCB material extraction was not performed.",
                                    "RMS phasor voltage on the assigned victim stroke; no surrounding electric field, transient or protocol qualification."]}},
            "frequenciesHz": [point["frequency_hz"] for point in points],
            "traceSamples": samples, "issues": solved["limitations"]}
    return {"context": context, "data": data, "sourceResult": solved}


def handle_si_spatial_pair_request(params):
    try:
        return {"ok": True, "result": run_si_spatial_pair(params)}
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, AttributeError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "Spatial pair failed admission or execution.",
                              detail=str(exc), context={"method": "run_si_spatial_pair"},
                              error_type=type(exc).__name__)
