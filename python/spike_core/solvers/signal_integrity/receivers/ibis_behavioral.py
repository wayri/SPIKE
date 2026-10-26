# SPDX-License-Identifier: Apache-2.0
"""Bounded, inert classic-IBIS behavioral compilation for an external engine."""
from __future__ import annotations

from hashlib import sha256
import json
import math

class UnsupportedIBIS(ValueError):
    """A source or request exceeds the explicitly admitted model subset."""


def exact_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise UnsupportedIBIS(f"{label} requires exactly {', '.join(sorted(fields))}.")


def finite(value, label, lower=0.0, upper=1e100, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UnsupportedIBIS(f"{label} must be a finite number.")
    if not lower <= value <= upper or (positive and value <= lower):
        raise UnsupportedIBIS(f"{label} is outside the admitted range.")
    return float(value)


def _request(request):
    exact_fields(request, {"contract", "driver", "receiver", "stimulus", "interconnect", "analysis"}, "request")
    if request["contract"] != "spike/ibis-behavioral-request/v1":
        raise UnsupportedIBIS("Unsupported IBIS behavioral request contract.")
    exact_fields(request["analysis"], {"time_step_s", "stop_time_s"}, "analysis")
    step = finite(request["analysis"]["time_step_s"], "time_step_s", 0, 1e-3, positive=True)
    stop = finite(request["analysis"]["stop_time_s"], "stop_time_s", 0, 1e-3, positive=True)
    if step > stop or math.ceil(stop / step) + 1 > 20000:
        raise UnsupportedIBIS("Analysis permits at most 20000 requested points and requires step <= stop.")
    interconnect = request["interconnect"]
    if not isinstance(interconnect, dict):
        raise UnsupportedIBIS("interconnect must be an object.")
    if interconnect.get("kind") == "lossless_tline":
        exact_fields(interconnect, {"kind", "impedance_ohm", "delay_s"}, "interconnect")
        finite(interconnect["impedance_ohm"], "impedance_ohm", 0, 1e9, positive=True)
        finite(interconnect["delay_s"], "delay_s", 0, stop, positive=True)
    elif interconnect.get("kind") == "series_resistor":
        exact_fields(interconnect, {"kind", "resistance_ohm"}, "interconnect")
        finite(interconnect["resistance_ohm"], "resistance_ohm", 0, 1e9, positive=True)
    else:
        raise UnsupportedIBIS("Only lossless_tline and series_resistor interconnects are admitted.")
    stimulus = request["stimulus"]
    exact_fields(stimulus, {"initial_state", "transitions"}, "stimulus")
    if stimulus["initial_state"] not in {"low", "high", "z"}:
        raise UnsupportedIBIS("initial_state must be low, high or z.")
    transitions = stimulus["transitions"]
    if not isinstance(transitions, list) or len(transitions) > 128:
        raise UnsupportedIBIS("At most 128 transitions are admitted.")
    previous = -1.0
    state = stimulus["initial_state"]
    for transition in transitions:
        exact_fields(transition, {"time_s", "state", "waveform_indices"}, "transition")
        time = finite(transition["time_s"], "transition time_s", 0, stop)
        indices = transition["waveform_indices"]
        if time <= previous or transition["state"] not in {"low", "high"} or transition["state"] == state:
            raise UnsupportedIBIS("Transition times must increase and states must alternate low/high.")
        if state == "z":
            raise UnsupportedIBIS("Dynamic enable transitions from z have no admitted waveform calibration.")
        if (not isinstance(indices, list) or len(indices) != 2 or any(type(i) is not int or i < 0 for i in indices)
                or indices[0] == indices[1]):
            raise UnsupportedIBIS("Each transition requires two distinct explicit waveform indices.")
        previous, state = time, transition["state"]
    return step, stop


def compile_ibis_behavioral(request: dict) -> dict:
    """Compile inline source data only; never discover or launch an executable."""
    result = {"contract": "spike/ibis-behavioral-compile/v1", "status": "unsupported",
              "model_status": "experimental", "production_qualified": False,
              "diagnostics": [], "endpoints": {}}
    try:
        step, stop = _request(request)
        from .ibis_behavioral_tables import endpoint, generate_netlist
        driver = endpoint(request["driver"], "driver")
        receiver = endpoint(request["receiver"], "receiver")
        result["endpoints"] = {"driver": driver["provenance"], "receiver": receiver["provenance"]}
        netlist, calibration = generate_netlist(driver, receiver, request, step, stop)
        result.update(status="ready", netlist=netlist, netlist_sha256=sha256(netlist.encode("ascii")).hexdigest(),
                      calibration=calibration, request_sha256=sha256(json.dumps(request, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest())
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        result["diagnostics"] = [{"code": "IBIS_BEHAVIORAL_UNSUPPORTED", "severity": "error", "message": str(error)}]
    return result
