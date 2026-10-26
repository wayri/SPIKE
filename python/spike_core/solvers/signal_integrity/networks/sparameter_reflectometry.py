# SPDX-License-Identifier: Apache-2.0
"""Loaded apparent port reflectometry from one actual initialized trajectory.

With a,b in sqrt(W) and real Z0, V+=sqrt(Z0)*a, V-=sqrt(Z0)*b,
V=V++V- and I=(V+-V-)/Z0, positive into the fitted network. Resolved
ratios are V-/V+ and V/I, without inversion through (1-Gamma). Common
states, other driven ports and boundary loading remain present. These are
instantaneous apparent ratios, not isolated S11 or a spatial reconstruction.
"""
from __future__ import annotations

import math

from . import sparameter_rlc_initial as initialized

rlc = initialized.rlc
sampling = rlc.rational.sampling
REQUEST_CONTRACT = "spike/network-reflectometry-request/v1"
RESULT_CONTRACT = "spike/network-reflectometry-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterReflectometryError(ValueError):
    """Invalid request or failed derived evidence, without partial success."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_REFLECTOMETRY_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterReflectometryError(code, message)


def _finite(value, name, nonzero=False):
    _require(math.isfinite(value) and (not nonzero or value != 0), f"Unrepresentable {name}", "numerical_failure")
    return value


def _admit(source, size, poll):
    sampling._record(source, {"contract", "fit_request", "terminations", "output_times_s", "initial_state"}, "initialized transient request")
    _require(source["contract"] == initialized.REQUEST_CONTRACT, "An initialized v2 transient is required")
    old = {key: source[key] for key in ("fit_request", "terminations", "output_times_s")}
    old["contract"] = rlc.REQUEST_CONTRACT
    admitted = rlc._prepare(old, size, poll)
    initialized._state_vector(source["initial_state"], source["fit_request"], admitted[0], admitted[9], admitted[10])
    return admitted


def run_network_reflectometry(request, *, cancel_check=None):
    """Retain one actual solve and report only explicitly resolved port ratios."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try: cancelled = cancel_check()
            except Exception as error: raise SParameterReflectometryError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Network reflectometry cancelled", "cancelled")

    try:
        poll(); frozen, size = rlc.prescribed._snapshot(request)
        sampling._record(frozen, {"contract", "transient_request", "probe_port", "minimum_incident_voltage_v", "minimum_current_a"}, "reflectometry request")
        _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported reflectometry contract")
        source = frozen["transient_request"]
        admitted = _admit(source, size, poll)
        ports, probe = admitted[0], frozen["probe_port"]
        _require(isinstance(probe, str) and probe in ports, "Unknown fitted-network probe port")
        incident_floor = sampling._number(frozen["minimum_incident_voltage_v"], "incident voltage floor")
        current_floor = sampling._number(frozen["minimum_current_a"], "network current floor")
        _require(incident_floor > 0 and current_floor > 0, "Resolution floors must be positive")
        samples, n = len(source["output_times_s"]), len(ports)
        _require(admitted[-1]+64*samples <= _MAX_WORK, "Aggregate reflectometry work exceeds 100 million", "resource_limit")
        frequencies = len(source["fit_request"]["source"]["frequencies_hz"])
        estimate = 8*size+96*frequencies*n*n+samples*(2048+3072*n)+524288
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated full reflectometry result exceeds 16 MiB", "resource_limit")
        poll(); transient = initialized.run_initialized_rlc_network_transient(source, cancel_check=cancel_check)
        _require(transient["contract"] == initialized.RESULT_CONTRACT and transient["input_digest"] == sampling._digest(source)
                 and transient["port_names"] == ports and transient["output_times_s"] == source["output_times_s"]
                 and len(transient["points"]) == samples, "Actual transient identity or sample count mismatch", "numerical_failure")
        reference = source["fit_request"]["source"]["reference_impedance_ohm"]
        root = math.sqrt(reference)
        points, reflection_count, impedance_count = [], 0, 0
        maximum_voltage_error, maximum_current_error = 0., 0.
        for time, point in zip(source["output_times_s"], transient["points"]):
            poll(); _require(point["time_s"] == time, "Actual transient observation mapping mismatch", "numerical_failure")
            incident = sampling._number(point["incident_wave_sqrt_w_by_port"][probe], "incident wave")
            reflected = sampling._number(point["outgoing_wave_sqrt_w_by_port"][probe], "outgoing wave")
            voltage = sampling._number(point["port_voltage_v_by_port"][probe], "network voltage")
            current = sampling._number(point["port_current_a_by_port"][probe], "network current")
            plus = _finite(root*incident, "incident voltage", incident != 0)
            minus = _finite(root*reflected, "reflected voltage", reflected != 0)
            reconstructed_v = _finite(math.fsum((plus, minus)), "reconstructed voltage")
            difference = _finite(math.fsum((plus, -minus)), "wave voltage difference")
            reconstructed_i = _finite(difference/reference, "reconstructed current", difference != 0)
            voltage_error = abs(_finite(math.fsum((voltage, -reconstructed_v)), "voltage residual"))
            current_error = abs(_finite(math.fsum((current, -reconstructed_i)), "current residual"))
            _require(voltage_error <= 2e-10+1e-9*max(abs(voltage), abs(plus), abs(minus), abs(reconstructed_v)),
                     "Wave voltage reconstruction fails tolerance", "numerical_failure")
            _require(current_error <= 2e-10+1e-9*max(abs(current), abs(reconstructed_i)),
                     "Wave current reconstruction fails tolerance", "numerical_failure")
            maximum_voltage_error, maximum_current_error = max(maximum_voltage_error, voltage_error), max(maximum_current_error, current_error)
            power = _finite(voltage*current, "instantaneous network power", voltage != 0 and current != 0)
            gamma, impedance = None, None
            reflection_status = impedance_status = "incident_below_floor"
            if abs(plus) > incident_floor:
                gamma = _finite(minus/plus, "reflection coefficient", minus != 0)
                reflection_status = "resolved"; reflection_count += 1
                impedance_status = "current_below_floor"
                if abs(current) > current_floor:
                    impedance = _finite(voltage/current, "apparent impedance", voltage != 0)
                    impedance_status = "resolved"; impedance_count += 1
            points.append({"time_s": time, "incident_voltage_v": plus, "reflected_voltage_v": minus,
                           "network_voltage_v": voltage, "network_current_a": current, "instantaneous_network_power_w": power,
                           "reflection_coefficient": gamma, "reflection_status": reflection_status,
                           "apparent_impedance_ohm": impedance, "impedance_status": impedance_status})
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": sampling._digest(frozen), "probe_port": probe, "reference_impedance_ohm": reference,
                  "minimum_incident_voltage_v": frozen["minimum_incident_voltage_v"], "minimum_current_a": frozen["minimum_current_a"],
                  "transient_result": transient, "points": points, "diagnostics": {"solution_count": 1, "sample_count": samples,
                    "resolved_reflection_count": reflection_count, "resolved_impedance_count": impedance_count,
                    "maximum_voltage_reconstruction_error_v": maximum_voltage_error, "maximum_current_reconstruction_error_a": maximum_current_error}}
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Full reflectometry result exceeds 16 MiB", "resource_limit")
        poll(); return result
    except SParameterReflectometryError: raise
    except (initialized.SParameterRlcInitialError, rlc.SParameterRlcError, rlc.resistive.SParameterTerminatedError,
            rlc.prescribed.SParameterTransientError, rlc.rational.SParameterRationalError, sampling.SParameterSamplingError) as error:
        raise SParameterReflectometryError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, KeyError, ZeroDivisionError) as error:
        raise SParameterReflectometryError("numerical_failure", f"Reflectometry analysis failed: {error}") from error
