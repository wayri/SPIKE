# SPDX-License-Identifier: Apache-2.0
"""Supplied fitted/RLC states and stateless continuation of the v1 propagator.

The fit state is the actual real-pole realization x; physical boundary states
map to q=sqrt(Z0)*Isource and v=V/sqrt(Z0), independently in source-port order.
The autonomous state and explicit PWL input determine each local-time segment.
Returning the actual final states enables the exponential semigroup property
when the caller explicitly reslices the same continuous source waveforms.
The fit-request digest binds coordinates to source data, poles and fit options;
it authenticates neither the state values nor a code revision or prior run.
"""
from __future__ import annotations

import math

import numpy as np

from . import sparameter_rlc_terminated as rlc

REQUEST_CONTRACT = "spike/rlc-network-transient-request/v2"
RESULT_CONTRACT = "spike/rlc-network-transient-result/v2"
STATE_CONTRACT = "spike/rlc-initial-state/v1"
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterRlcInitialError(ValueError):
    """Invalid supplied state or failed propagation, without partial success."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_RLC_INITIAL_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterRlcInitialError(code, message)


def _state_vector(state, fit_request, ports, inductive, capacitive):
    sampling = rlc.rational.sampling
    sampling._record(state, {"contract", "fit_request_digest", "fit_state_sqrt_w", "inductor_current_a_by_port", "capacitor_voltage_v_by_port"}, "initial state")
    _require(state["contract"] == STATE_CONTRACT, "Unsupported initial-state contract")
    _require(state["fit_request_digest"] == sampling._digest(fit_request), "Initial-state fit-request binding mismatch")
    k, n = len(fit_request["pole_rates_rad_s"]), len(ports)
    memory = state["fit_state_sqrt_w"]
    _require(isinstance(memory, list) and len(memory) == k and all(isinstance(row, list) and len(row) == n for row in memory), "Fit state must have supplied-pole by source-port dimensions")
    normalized = [sampling._number(value, "fit state") for row in memory for value in row]
    root = math.sqrt(fit_request["source"]["reference_impedance_ohm"])
    for field, subset, multiplier in (("inductor_current_a_by_port", inductive, root), ("capacitor_voltage_v_by_port", capacitive, 1/root)):
        values = state[field]
        _require(isinstance(values, dict) and set(values) == {ports[i] for i in subset}, "Initial physical state must exactly cover the positive-component port subset")
        for index in subset:
            value = sampling._number(values[ports[index]], field)
            mapped = value*multiplier
            _require(math.isfinite(mapped) and (value == 0 or mapped != 0), "Initial physical-state normalization overflows or underflows", "numerical_failure")
            normalized.append(mapped)
    vector = np.array(normalized, dtype=float)
    _require(np.isfinite(vector).all(), "Nonfinite supplied normalized state", "numerical_failure")
    return vector


def run_initialized_rlc_network_transient(request, *, cancel_check=None):
    """Validate a portable supplied state and execute the shared propagator."""
    return _run(request, cancel_check=cancel_check)


def _run(request, *, cancel_check=None, interval_observer=None):
    """Private initialized propagation, optionally observing accepted intervals."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterRlcInitialError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Initialized RLC transient cancelled", "cancelled")

    try:
        poll()
        frozen, size = rlc.prescribed._snapshot(request)
        sampling = rlc.rational.sampling
        sampling._record(frozen, {"contract", "fit_request", "terminations", "output_times_s", "initial_state"}, "initialized RLC request")
        _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported initialized RLC contract")
        old_request = {key: frozen[key] for key in ("fit_request", "terminations", "output_times_s")}
        old_request["contract"] = rlc.REQUEST_CONTRACT
        ports, _, _, _, _, _, _, _, _, inductive, capacitive, _ = rlc._prepare(old_request, size, poll)
        initial = _state_vector(frozen["initial_state"], frozen["fit_request"], ports, inductive, capacitive)
        poll()
        result = rlc._run(old_request, cancel_check=cancel_check, initial_state=initial, interval_observer=interval_observer)
        poll()
        result["contract"] = RESULT_CONTRACT
        result["input_digest"] = sampling._digest(frozen)
        result["initial_state"] = frozen["initial_state"]
        result["restart_state"] = {"contract": STATE_CONTRACT, "fit_request_digest": sampling._digest(frozen["fit_request"]),
                                   "fit_state_sqrt_w": result["final_state_sqrt_w"],
                                   "inductor_current_a_by_port": result["final_inductor_current_a_by_port"],
                                   "capacitor_voltage_v_by_port": result["final_capacitor_voltage_v_by_port"]}
        result["limitations"] = ["Explicit supplied fitted-network, inductor and capacitor states; local-time continuous PWL sources with series R/L and shunt C"]+result["limitations"][1:]
        result["limitations"].extend(["Restart state has no time: every call starts at local zero and the caller must explicitly reslice continuous PWL sources",
                                     "Fit-request digest binds source/poles/options only; supplied/restart values are not authenticated checkpoints or bound to a code revision",
                                     "Arbitrary fitted realization states have no inferred generic physical energy or measurement qualification"])
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Initialized RLC result exceeds 16 MiB", "resource_limit")
        poll()
        return result
    except SParameterRlcInitialError:
        raise
    except (rlc.SParameterRlcError, rlc.resistive.SParameterTerminatedError, rlc.prescribed.SParameterTransientError,
            rlc.rational.SParameterRationalError, rlc.rational.sampling.SParameterSamplingError) as error:
        raise SParameterRlcInitialError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, np.linalg.LinAlgError) as error:
        raise SParameterRlcInitialError("numerical_failure", f"Initialized RLC numerical failure: {error}") from error
