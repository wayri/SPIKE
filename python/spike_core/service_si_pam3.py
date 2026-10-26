# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Strict JSON admission for generic PAM3; not a protocol compliance route."""
from hashlib import sha256
import json

from .service_helpers import error_response

REQUEST_CONTRACT = "spike/si-pam3-request/v1"
_REQUIRED = {"contract", "symbols", "levels_v", "channel_impulse", "symbol_rate_hz", "samples_per_ui"}
_OPTIONAL = {"sampling_phase_ui", "channel_cursor_samples", "decision_thresholds_v",
             "voltage_noise_rms_v", "noise_seed"}


def simulate_pam3_request(request):
    """Validate a finite bounded JSON envelope and execute the numerical owner."""
    if not isinstance(request, dict) or set(request) - (_REQUIRED | _OPTIONAL) or _REQUIRED - set(request):
        raise ValueError("PAM3 request has missing or unknown fields")
    if request["contract"] != REQUEST_CONTRACT:
        raise ValueError(f"Expected {REQUEST_CONTRACT}")
    from .solvers.signal_integrity.receivers.si_pam3 import pam3_eye, MAX_SYMBOLS, MAX_CHANNEL_TAPS
    for name, maximum in (("symbols", MAX_SYMBOLS), ("channel_impulse", MAX_CHANNEL_TAPS), ("levels_v", 3)):
        value = request[name]
        if not isinstance(value, list) or not 1 <= len(value) <= maximum:
            raise ValueError(f"{name} must be a bounded JSON array")
        if any(type(item) not in {int, float} for item in value):
            raise ValueError(f"{name} must contain numbers only")
    if len(request["levels_v"]) != 3:
        raise ValueError("levels_v requires exactly three voltages")
    if any(type(item) is not int or item not in {0, 1, 2} for item in request["symbols"]):
        raise ValueError("symbols must contain only integer indices 0, 1, 2")
    if request["levels_v"] != sorted(request["levels_v"]) or len(set(request["levels_v"])) != 3:
        raise ValueError("levels_v must be strictly increasing")
    for key in (_OPTIONAL - {"decision_thresholds_v"}) | {"symbol_rate_hz", "samples_per_ui"}:
        if key in request and type(request[key]) not in {int, float}:
            raise ValueError(f"{key} must be numeric")
    if "decision_thresholds_v" in request:
        thresholds = request["decision_thresholds_v"]
        if not isinstance(thresholds, list) or len(thresholds) != 2 or any(type(x) not in {int, float} for x in thresholds):
            raise ValueError("decision_thresholds_v requires exactly two numeric voltages")
    payload = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("PAM3 control exceeds 8 MiB")
    result = pam3_eye(request["symbols"],
        symbol_to_level_v=dict(enumerate(request["levels_v"])),
        channel_impulse=request["channel_impulse"], symbol_rate_hz=request["symbol_rate_hz"],
        samples_per_ui=request["samples_per_ui"],
        **{key: request[key] for key in _OPTIONAL if key in request})
    result["request_sha256"] = sha256(payload).hexdigest()
    return result


def handle_pam3_request(params):
    try:
        if not isinstance(params, dict) or set(params) != {"request"}:
            raise ValueError("Exactly one request is required")
        return {"ok": True, "result": simulate_pam3_request(params["request"])}
    except (ValueError, TypeError, KeyError, ArithmeticError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "PAM3 request failed admission or execution.",
                              detail=str(exc), context={"method": "simulate_si_pam3"},
                              error_type=type(exc).__name__)
