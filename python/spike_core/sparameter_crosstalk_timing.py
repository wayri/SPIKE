# SPDX-License-Identifier: Apache-2.0
"""Finite supplied timing corners over sampled fixed-polarity SI envelopes.

An aggressor becomes w(t-delay), with endpoint holds outside its source
horizon. Initial states remain supplied at local zero; shifting the source
does not infer a prehistory. Each corner executes the actual parent analysis.
Sample extrema and overall witnesses are selected over this finite family;
equal values favor declared corner order, then earliest sample in that corner.
"""
from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
import math

from . import sparameter_multi_aggressor as multi

sampling = multi.sampling
REQUEST_CONTRACT = "spike/crosstalk-timing-corners-request/v1"
RESULT_CONTRACT = "spike/crosstalk-timing-corners-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class SParameterCrosstalkTimingError(ValueError):
    """Invalid supplied timing family or failed corner, without partial output."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "SPARAMETER_CROSSTALK_TIMING_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise SParameterCrosstalkTimingError(code, message)


def _shift_points(points, delay, horizon):
    if delay == 0:
        return deepcopy(points)
    if delay >= horizon:
        return [{"time_s": 0., "voltage_v": points[0]["voltage_v"]},
                {"time_s": points[-1]["time_s"], "voltage_v": points[0]["voltage_v"]}]
    if delay <= -horizon:
        return [{"time_s": 0., "voltage_v": points[-1]["voltage_v"]},
                {"time_s": points[-1]["time_s"], "voltage_v": points[-1]["voltage_v"]}]
    times = [float(p["time_s"]) for p in points]

    def interpolate(query):
        if query <= 0: return points[0]["voltage_v"]
        if query >= horizon: return points[-1]["voltage_v"]
        index = bisect_right(times, query)-1
        if query == times[index]: return points[index]["voltage_v"]
        fraction = (query-times[index])/(times[index+1]-times[index])
        _require(math.isfinite(fraction) and 0 < fraction < 1, "Unrepresentable clipped endpoint fraction", "numerical_failure")
        left, right = (float(points[index+j]["voltage_v"]) for j in (0, 1))
        if left == right: return left
        a, b = (1-fraction)*left, fraction*right
        _require((left == 0 or a != 0) and (right == 0 or b != 0), "Endpoint interpolation product underflows", "numerical_failure")
        value = math.fsum((a, b))
        _require(math.isfinite(value), "Nonfinite interpolated endpoint", "numerical_failure")
        return value

    first = points[0]["voltage_v"] if delay > 0 else interpolate(-delay)
    if delay > 0:
        query = horizon-delay
        _require(0 < query < horizon, "Clipped endpoint time loses the supplied delay", "numerical_failure")
        last = interpolate(query)
    else:
        last = points[-1]["voltage_v"]
    shifted = [{"time_s": 0., "voltage_v": first}]
    for point, time in zip(points, times):
        # Compare before adding: unused far-outside knots need not overflow.
        interior = time < horizon-delay if delay > 0 else time > -delay
        if not interior: continue
        shifted_time = math.fsum((time, delay))
        _require(math.isfinite(shifted_time) and 0 < shifted_time < horizon
                 and shifted_time > shifted[-1]["time_s"] and shifted_time != time,
                 "Shifted interior knot collapses or collides in floating-point time", "numerical_failure")
        shifted.append({"time_s": shifted_time, "voltage_v": point["voltage_v"]})
    shifted.append({"time_s": points[-1]["time_s"], "voltage_v": last})
    return shifted


def _preflight(source, poll):
    """Mirror parent contract admission, reusing its numerical admission helpers."""
    sampling._record(source, {"contract", "transient_request", "victim_port", "aggressors", "lower_limit_v", "upper_limit_v"}, "source crosstalk request")
    _require(source["contract"] == multi.REQUEST_CONTRACT, "An S08 crosstalk source request is required")
    size = len(sampling._json(source)); transient = source["transient_request"]
    admitted = multi._admit_transient(transient, size, poll)
    ports = admitted[0]
    _require(isinstance(source["victim_port"], str) and source["victim_port"] in ports, "Unknown victim port")
    lower, upper = [sampling._number(source[key], key) for key in ("lower_limit_v", "upper_limit_v")]
    _require(lower < upper, "Voltage limits must strictly increase")
    aggressors = source["aggressors"]
    _require(isinstance(aggressors, list) and 1 <= len(aggressors) <= 6, "Provide 1..6 aggressors")
    bias = {}
    for record in aggressors:
        sampling._record(record, {"port_name", "reference_voltage_v"}, "aggressor")
        port = record["port_name"]
        _require(isinstance(port, str) and port in ports and port != source["victim_port"] and port not in bias,
                 "Aggressor ports must be unique, known and different from the victim")
        bias[port] = sampling._number(record["reference_voltage_v"], "aggressor bias")
    ordered = [port for port in ports if port in bias]
    variants = [multi._family_request(transient, bias),
                multi._family_request(transient, bias, signs={port: -1 for port in ordered})]
    variants.extend(multi._family_request(transient, bias, basis=port) for port in ordered)
    for variant in variants:
        poll(); multi._admit_transient(variant, len(sampling._json(variant)), poll)
    n, count, samples = len(ports), len(ordered)+3, len(transient["output_times_s"])
    frequencies = len(transient["fit_request"]["source"]["frequencies_hz"])
    estimate = 8*size+96*frequencies*n*n+samples*(2048+3072*n+256*len(ordered))+524288
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated corner result exceeds 16 MiB", "resource_limit")
    return ordered, admitted[3][-1], count*admitted[-1], count, estimate


def run_crosstalk_timing_corners(request, *, cancel_check=None):
    """Evaluate only the explicit timing corners and requested observations."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try: cancelled = cancel_check()
            except Exception as error: raise SParameterCrosstalkTimingError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Crosstalk timing analysis cancelled", "cancelled")

    try:
        poll(); frozen, size = multi.rlc.prescribed._snapshot(request)
        sampling._record(frozen, {"contract", "crosstalk_request", "timing_corners"}, "timing-corners request")
        _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported timing-corners contract")
        source = frozen["crosstalk_request"]
        ports, horizon, _, _, _ = _preflight(source, poll)
        corners = frozen["timing_corners"]
        _require(isinstance(corners, list) and 1 <= len(corners) <= 8, "Provide 1..8 timing corners")
        ids, prepared, work, solution_count = set(), [], 0, 0
        estimate = 2*size+524288
        for corner in corners:
            poll(); sampling._record(corner, {"id", "delay_s_by_port"}, "timing corner")
            _require(isinstance(corner["id"], str) and corner["id"].strip() and len(corner["id"]) <= 128,
                     "Invalid bounded timing corner id")
            _require(corner["id"] not in ids, "Duplicate timing corner id"); ids.add(corner["id"])
            delays = corner["delay_s_by_port"]
            _require(isinstance(delays, dict) and set(delays) == set(ports), "Timing delays must exactly cover aggressor ports")
            values = {port: sampling._number(delays[port], "aggressor delay") for port in ports}
            derived = deepcopy(source)
            for term in derived["transient_request"]["terminations"]:
                if term["port_name"] in values:
                    term["voltage_points"] = _shift_points(term["voltage_points"], values[term["port_name"]], horizon)
            _, _, corner_work, count, corner_estimate = _preflight(derived, poll)
            work += corner_work; solution_count += count; estimate += corner_estimate
            _require(work <= _MAX_WORK, "Aggregate timing-corner work exceeds 100 million", "resource_limit")
            _require(estimate <= _MAX_RESULT_BYTES, "Estimated full timing-corner result exceeds 16 MiB", "resource_limit")
            prepared.append((corner, derived))
        results = []
        for corner, derived in prepared:
            poll(); solved = multi.run_multi_aggressor_crosstalk(derived, cancel_check=cancel_check)
            _require(solved["input_digest"] == sampling._digest(derived), "Corner result identity mismatch", "numerical_failure")
            results.append({"id": corner["id"], "delay_s_by_port": {port: corner["delay_s_by_port"][port] for port in ports}, "result": solved})
        samples = source["transient_request"]["output_times_s"]
        envelope = []
        for index, time in enumerate(samples):
            low = min(results, key=lambda c: c["result"]["envelope"][index]["minimum_voltage_v"])
            high = max(results, key=lambda c: c["result"]["envelope"][index]["maximum_voltage_v"])
            a, b = low["result"]["envelope"][index], high["result"]["envelope"][index]
            envelope.append({"time_s": time, "minimum_voltage_v": a["minimum_voltage_v"], "maximum_voltage_v": b["maximum_voltage_v"],
                             "lower_margin_v": a["lower_margin_v"], "upper_margin_v": b["upper_margin_v"],
                             "minimum_corner_id": low["id"], "maximum_corner_id": high["id"]})
        witnesses = {}
        for name, selection in (("worst_upper_pattern", max), ("worst_lower_pattern", min)):
            winner = selection(results, key=lambda c: c["result"][name]["victim_voltage_v"])
            witnesses[name] = {**deepcopy(winner["result"][name]), "corner_id": winner["id"]}
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": sampling._digest(frozen), "source_crosstalk_request": source, "corners": results,
                  "envelope": envelope, **witnesses, "diagnostics": {"solution_count": solution_count,
                    "estimated_work": work, "corner_count": len(results), "sample_count": len(samples)}}
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Full timing-corner result exceeds 16 MiB", "resource_limit")
        poll(); return result
    except SParameterCrosstalkTimingError: raise
    except (multi.SParameterMultiAggressorError, multi.initialized.SParameterRlcInitialError,
            multi.rlc.SParameterRlcError, multi.rlc.resistive.SParameterTerminatedError,
            multi.rlc.prescribed.SParameterTransientError, multi.rlc.rational.SParameterRationalError,
            sampling.SParameterSamplingError) as error:
        raise SParameterCrosstalkTimingError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, FloatingPointError, KeyError) as error:
        raise SParameterCrosstalkTimingError("numerical_failure", f"Timing-corner analysis failed: {error}") from error
