# SPDX-License-Identifier: Apache-2.0
"""Sampled fixed-polarity crosstalk envelopes from actual linear RLC solves.

For prescribed aggressor deviations d_j=w_j-b_j, linearity gives the victim
voltage v_sigma=v_baseline+sum(sigma_j*v_j). At each requested observation,
independent signs attain v_baseline +/- sum(abs(v_j)). A single sign pattern
need not attain the envelope at every time. The two selected global sampled
extrema are therefore checked by full fixed-pattern solves, including the
common initial state and all nonaggressor sources. This is voltage linearity,
not superposition of quadratic heat/storage or a continuous-time extremum.
"""
from __future__ import annotations

from copy import deepcopy
import math

from . import sparameter_rlc_initial as initialized

rlc = initialized.rlc
sampling = rlc.rational.sampling
REQUEST_CONTRACT = "spike/multi-aggressor-crosstalk-request/v1"
RESULT_CONTRACT = "spike/multi-aggressor-crosstalk-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterMultiAggressorError(ValueError):
    """Invalid family or failed numerical witness, without partial success."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_MULTI_AGGRESSOR_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterMultiAggressorError(code, message)


def _sum(values):
    value = math.fsum(values)
    _require(math.isfinite(value), "Nonfinite bias, envelope or margin arithmetic", "numerical_failure")
    return value


def _admit_transient(source, size, poll):
    sampling._record(source, {"contract", "fit_request", "terminations", "output_times_s", "initial_state"}, "initialized source request")
    _require(source["contract"] == initialized.REQUEST_CONTRACT, "An initialized v2 RLC source request is required")
    old = {key: source[key] for key in ("fit_request", "terminations", "output_times_s")}
    old["contract"] = rlc.REQUEST_CONTRACT
    admitted = rlc._prepare(old, size, poll)
    initialized._state_vector(source["initial_state"], source["fit_request"], admitted[0], admitted[9], admitted[10])
    return admitted


def _family_request(source, bias, *, basis=None, signs=None):
    result = deepcopy(source)
    if basis is not None:
        state = result["initial_state"]
        state["fit_state_sqrt_w"] = [[0. for _ in row] for row in state["fit_state_sqrt_w"]]
        for name in ("inductor_current_a_by_port", "capacitor_voltage_v_by_port"):
            state[name] = {port: 0. for port in state[name]}
    for term in result["terminations"]:
        port = term["port_name"]
        for point in term["voltage_points"]:
            original = sampling._number(point["voltage_v"], "source voltage")
            if basis is not None:
                point["voltage_v"] = _sum((original, -bias[port])) if port == basis else 0.
            elif port in bias:
                if signs is None:
                    point["voltage_v"] = bias[port]
                elif signs[port] == -1:
                    # fsum avoids an unnecessary overflowing intermediate 2*b.
                    point["voltage_v"] = _sum((bias[port], bias[port], -original))
                # Positive polarity retains the exact original sample.
    return result


def _trace(result, source, victim):
    _require(result["contract"] == initialized.RESULT_CONTRACT
             and result["input_digest"] == sampling._digest(source)
             and result["port_names"] == source["fit_request"]["source"]["port_names"]
             and result["output_times_s"] == source["output_times_s"],
             "Actual solver result identity mismatch", "numerical_failure")
    points = result["points"]
    _require(len(points) == len(source["output_times_s"]), "Actual solver sample count mismatch", "numerical_failure")
    trace = []
    for point, time in zip(points, source["output_times_s"]):
        _require(point["time_s"] == time, "Actual solver observation mapping mismatch", "numerical_failure")
        trace.append(sampling._number(point["port_voltage_v_by_port"][victim], "victim voltage"))
    return trace


def run_multi_aggressor_crosstalk(request, *, cancel_check=None):
    """Run N+3 actual fits/trajectories and admit both sampled-extremum witnesses."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try:
                cancelled = cancel_check()
            except Exception as error:
                raise SParameterMultiAggressorError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Multi-aggressor analysis cancelled", "cancelled")

    try:
        poll(); frozen, size = rlc.prescribed._snapshot(request)
        sampling._record(frozen, {"contract", "transient_request", "victim_port", "aggressors", "lower_limit_v", "upper_limit_v"}, "multi-aggressor request")
        _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported multi-aggressor contract")
        source = frozen["transient_request"]
        admitted = _admit_transient(source, size, poll)
        ports, victim = admitted[0], frozen["victim_port"]
        _require(isinstance(victim, str) and victim in ports, "Unknown victim port")
        lower = sampling._number(frozen["lower_limit_v"], "lower voltage limit")
        upper = sampling._number(frozen["upper_limit_v"], "upper voltage limit")
        _require(lower < upper, "Voltage limits must strictly increase")
        aggressors = frozen["aggressors"]
        _require(isinstance(aggressors, list) and 1 <= len(aggressors) <= 6, "Provide 1..6 aggressors")
        supplied = {}
        for record in aggressors:
            sampling._record(record, {"port_name", "reference_voltage_v"}, "aggressor")
            port = record["port_name"]
            _require(isinstance(port, str) and port in ports and port != victim and port not in supplied,
                     "Aggressor ports must be unique, known and different from the victim")
            supplied[port] = sampling._number(record["reference_voltage_v"], "aggressor bias")
        ordered = [port for port in ports if port in supplied]
        bias = {port: supplied[port] for port in ordered}
        count, samples, n = len(ordered)+3, len(source["output_times_s"]), len(ports)
        work = count*admitted[-1]
        _require(work <= _MAX_WORK, "Combined N+3 transient work exceeds 100 million", "resource_limit")
        frequencies = len(source["fit_request"]["source"]["frequencies_hz"])
        estimate = 8*size+96*frequencies*n*n+samples*(2048+3072*n+256*len(ordered))+524288
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated full crosstalk result exceeds 16 MiB", "resource_limit")
        baseline_request = _family_request(source, bias)
        # Validate every deviation and mirrored endpoint before any actual fit,
        # even if its sign is not selected by the later sampled extrema.
        _family_request(source, bias, signs={port: -1 for port in ordered})
        basis_requests = [_family_request(source, bias, basis=port) for port in ordered]
        for derived in [baseline_request, *basis_requests]:
            _admit_transient(derived, len(sampling._json(derived)), poll)
        poll()
        baseline = initialized.run_initialized_rlc_network_transient(baseline_request, cancel_check=cancel_check)
        base = _trace(baseline, baseline_request, victim)
        contributions, traces = [], []
        for port, basis_request in zip(ordered, basis_requests):
            poll()
            solved = initialized.run_initialized_rlc_network_transient(basis_request, cancel_check=cancel_check)
            values = _trace(solved, basis_request, victim)
            traces.append(values)
            contributions.append({"port_name": port, "input_digest": sampling._digest(basis_request), "victim_voltage_v": values})
        envelope = []
        for index, time in enumerate(source["output_times_s"]):
            radius = _sum(abs(values[index]) for values in traces)
            minimum, maximum = _sum((base[index], -radius)), _sum((base[index], radius))
            envelope.append({"time_s": time, "baseline_voltage_v": base[index], "minimum_voltage_v": minimum,
                             "maximum_voltage_v": maximum, "lower_margin_v": _sum((minimum, -lower)),
                             "upper_margin_v": _sum((upper, -maximum))})

        def witness(is_upper):
            field = "maximum_voltage_v" if is_upper else "minimum_voltage_v"
            index = (max if is_upper else min)(range(samples), key=lambda i: envelope[i][field])
            signs = {port: (1 if values[index] >= 0 else -1)*(1 if is_upper else -1)
                     for port, values in zip(ordered, traces)}
            direct_request = _family_request(source, bias, signs=signs)
            poll()
            actual = initialized.run_initialized_rlc_network_transient(direct_request, cancel_check=cancel_check)
            direct = _trace(actual, direct_request, victim)
            maximum_error = 0.
            for i, value in enumerate(direct):
                expected = _sum([base[i]]+[signs[port]*values[i] for port, values in zip(ordered, traces)])
                error = abs(_sum((value, -expected)))
                scale = max(abs(value), abs(expected), abs(base[i]), _sum(abs(values[i]) for values in traces))
                tolerance = _sum((2e-10, 1e-9*scale))
                _require(error <= tolerance, "Direct fixed-pattern trajectory fails superposition tolerance", "superposition_failure")
                maximum_error = max(maximum_error, error)
            return {"sample_time_s": envelope[index]["time_s"], "victim_voltage_v": envelope[index][field],
                    "margin_v": envelope[index]["upper_margin_v" if is_upper else "lower_margin_v"],
                    "polarity_by_port": signs, "verified_input_digest": sampling._digest(direct_request),
                    "verified_victim_voltage_v": direct, "maximum_superposition_error_v": maximum_error}

        worst_upper, worst_lower = witness(True), witness(False)
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": sampling._digest(frozen), "source_request": source, "victim_port": victim,
                  "aggressor_port_names": ordered, "reference_voltage_v_by_port": bias,
                  "lower_limit_v": frozen["lower_limit_v"], "upper_limit_v": frozen["upper_limit_v"],
                  "baseline_result": baseline, "contributions": contributions, "envelope": envelope,
                  "worst_upper_pattern": worst_upper, "worst_lower_pattern": worst_lower,
                  "diagnostics": {"solution_count": count, "estimated_work": work, "sample_count": samples,
                                  "maximum_superposition_error_v": max(worst_upper["maximum_superposition_error_v"], worst_lower["maximum_superposition_error_v"])}}
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Full crosstalk result exceeds 16 MiB", "resource_limit")
        poll(); return result
    except SParameterMultiAggressorError:
        raise
    except (initialized.SParameterRlcInitialError, rlc.SParameterRlcError, rlc.resistive.SParameterTerminatedError,
            rlc.prescribed.SParameterTransientError, rlc.rational.SParameterRationalError, sampling.SParameterSamplingError) as error:
        raise SParameterMultiAggressorError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, KeyError) as error:
        raise SParameterMultiAggressorError("numerical_failure", f"Multi-aggressor analysis failed: {error}") from error
