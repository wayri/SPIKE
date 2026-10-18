# SPDX-License-Identifier: Apache-2.0
"""Original causal travelling-wave solution of a uniform lossless TEM line.

For zero history, F(t)=alpha_left*Vs_left(t)+Gamma_left*B(t-tau)
and B(t)=alpha_right*Vs_right(t)+Gamma_right*F(t-tau). Iteratively
substituting these equations terminates after floor(t/tau) reflections.
No temporal mesh or rational fit is introduced. Exact rational arithmetic on
admitted binary64 times preserves causal ordering; PWL weights and voltages
use checked binary64 arithmetic. Finite horizon permits full reflections.
"""
from __future__ import annotations

from bisect import bisect_right
from fractions import Fraction
import math

from . import sparameter_sampling as sampling

REQUEST_CONTRACT = "spike/lossless-line-transient-request/v1"
RESULT_CONTRACT = "spike/lossless-line-transient-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024
_MAX_BOUNCE_DEPTH = 4096


class LosslessLineTransientError(ValueError):
    """Invalid distributed line or unsupported precision, without partial output."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "LOSSLESS_LINE_TRANSIENT_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise LosslessLineTransientError(code, message)


def _finite(value, name, nonzero=False):
    _require(math.isfinite(value) and (not nonzero or value != 0), f"Unrepresentable {name}", "numerical_failure")
    return value


def _product(*values):
    """Avoid avoidable intermediate overflow; reject lost nonzero products."""
    if any(value == 0 for value in values): return 0.
    mantissa, exponent = 1., 0
    for value in values:
        part, power = math.frexp(value); mantissa *= part; exponent += power
    return _finite(math.ldexp(mantissa, exponent), "nonzero physical product", True)


def _value(time, waveform):
    times, values = waveform
    if time < 0: return 0.
    index = bisect_right(times, time)-1
    _require(index >= 0 and time <= times[-1], "Wave evaluation outside supplied horizon", "numerical_failure")
    if time == times[index]: return values[index]
    fraction = float((time-times[index])/(times[index+1]-times[index]))
    _require(0 < fraction < 1, "Interior PWL time fraction collapses in supported precision", "numerical_failure")
    if values[index] == values[index+1]: return values[index]
    return _finite(math.fsum((_product(1-fraction, values[index]), _product(fraction, values[index+1]))), "interpolated voltage")


def _prepare(request, size, poll):
    sampling._record(request, {"contract", "length_m", "inductance_h_per_m", "capacitance_f_per_m", "left_boundary", "right_boundary", "probes", "output_times_s"}, "lossless line request")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported lossless line contract")
    length, inductance, capacitance = [sampling._number(request[key], key) for key in ("length_m", "inductance_h_per_m", "capacitance_f_per_m")]
    _require(min(length, inductance, capacitance) > 0, "Length and distributed L/C must be positive")
    root_l, root_c = math.sqrt(inductance), math.sqrt(capacitance)
    impedance = _finite(root_l/root_c, "characteristic impedance", True)
    slowness = _product(root_l, root_c)
    delay = _product(length, slowness)
    speed = _finite(1/slowness, "propagation speed", True)
    time_identity = {}

    def time_number(value):
        converted = sampling._number(value, "time")
        if converted in time_identity:
            _require(time_identity[converted] == value, "Distinct supplied times collapse to one binary64 time", "numerical_failure")
        else: time_identity[converted] = value
        return converted

    waves, resistance, gamma, alpha = [], [], [], []
    for name in ("left_boundary", "right_boundary"):
        poll(); boundary = request[name]
        sampling._record(boundary, {"resistance_ohm", "voltage_points"}, name)
        r = sampling._number(boundary["resistance_ohm"], "boundary resistance")
        _require(r >= 0, "Boundary resistance must be nonnegative")
        points = boundary["voltage_points"]
        _require(isinstance(points, list) and 2 <= len(points) <= 1024, "Provide 2..1024 voltage points per boundary")
        times, values = [], []
        for point in points:
            sampling._record(point, {"time_s", "voltage_v"}, "boundary voltage point")
            times.append(time_number(point["time_s"])); values.append(sampling._number(point["voltage_v"], "source voltage"))
        _require(times[0] == values[0] == 0 and all(b > a for a, b in zip(times, times[1:])),
                 "Sources must start at exact (0,0) with strictly increasing times")
        waves.append(([Fraction(t) for t in times], values)); resistance.append(r)
        scale = max(r, impedance); rr, zz = r/scale, impedance/scale
        _require(zz > 0 and (r == 0 or rr > 0), "Boundary normalization underflows", "numerical_failure")
        denominator = rr+zz
        gamma.append(_finite((rr-zz)/denominator, "reflection coefficient"))
        alpha.append(_finite(zz/denominator, "launch factor", True))
    _require(waves[0][0][-1] == waves[1][0][-1] and waves[0][0][-1] > 0, "Both boundaries must have an identical positive final time")
    outputs = request["output_times_s"]
    _require(isinstance(outputs, list) and 1 <= len(outputs) <= 1024, "Provide 1..1024 observation times")
    observations = [Fraction(time_number(value)) for value in outputs]
    horizon = waves[0][0][-1]
    _require(all(0 <= t <= horizon for t in observations) and all(b > a for a, b in zip(observations, observations[1:])),
             "Observation times must strictly increase within the source horizon")
    probes = request["probes"]
    _require(isinstance(probes, list) and 1 <= len(probes) <= 32, "Provide 1..32 probes")
    ids, positions = set(), []
    for probe in probes:
        sampling._record(probe, {"id", "fractional_position"}, "line probe")
        name = probe["id"]
        _require(isinstance(name, str) and name.strip() and len(name) <= 128 and name not in ids, "Invalid or duplicate probe id")
        ids.add(name)
        position = sampling._number(probe["fractional_position"], "fractional position")
        _require(0 <= position <= 1, "Probe fractional position must lie in [0,1]")
        positions.append(Fraction(position))
    exact_delay = Fraction(delay); depth = horizon//exact_delay
    _require(depth <= _MAX_BOUNCE_DEPTH, "Preflight bounce depth exceeds 4096", "resource_limit")
    queries = 2*(len(probes)+2)*len(observations)
    work = queries*(depth+1)*(32+2*max(len(w[0]).bit_length() for w in waves))
    _require(work <= _MAX_WORK, "Estimated line-reflection work exceeds 100 million", "resource_limit")
    estimate = 2*size+len(observations)*(2048+768*len(probes))+262144
    _require(estimate <= _MAX_RESULT_BYTES, "Estimated full line result exceeds 16 MiB", "resource_limit")
    return impedance, delay, speed, waves, resistance, gamma, alpha, observations, positions, int(depth), work


def run_lossless_line_transient(request, *, cancel_check=None):
    """Evaluate a zero-history distributed TEM line at explicit observations."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try: cancelled = cancel_check()
            except Exception as error: raise LosslessLineTransientError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Lossless line transient cancelled", "cancelled")

    try:
        poll(); frozen, size = sampling._snapshot(request)
        impedance, delay, speed, waves, resistance, gamma, alpha, times, positions, depth, work = _prepare(frozen, size, poll)
        exact_delay = Fraction(delay)

        def launch(time, boundary):
            coefficient, terms = 1., []
            while time >= 0:
                poll(); value = _value(time, waves[boundary])
                if value != 0: terms.append(_product(coefficient, alpha[boundary], value))
                time -= exact_delay
                if time < 0 or gamma[boundary] == 0: break
                coefficient = _product(coefficient, gamma[boundary]); boundary = 1-boundary
            return _finite(math.fsum(terms), "travelling-wave sum")

        maximum_residual, points = 0., []
        for original_time, time in zip(frozen["output_times_s"], times):
            poll(); cache = {}

            def fields(position):
                forward_time, backward_time = time-position*exact_delay, time-(1-position)*exact_delay
                for key in ((forward_time, 0), (backward_time, 1)):
                    if key not in cache: cache[key] = launch(*key)
                forward, backward = cache[(forward_time, 0)], cache[(backward_time, 1)]
                voltage = _finite(math.fsum((forward, backward)), "line voltage")
                difference = _finite(math.fsum((forward, -backward)), "wave voltage difference")
                current = _finite(difference/impedance, "line current", difference != 0)
                return forward, backward, voltage, current

            boundary_values = {}
            for index, name in enumerate(("left", "right")):
                _, _, voltage, current = fields(Fraction(index))
                into = current if index == 0 else -current
                source = _value(time, waves[index]); resistor_voltage = _product(resistance[index], into)
                residual = _finite(math.fsum((source, -voltage, -resistor_voltage)), "boundary KVL residual")
                _require(abs(residual) <= 2e-10+1e-9*max(abs(source), abs(voltage), abs(resistor_voltage)),
                         "Terminal KVL residual exceeds tolerance", "numerical_failure")
                maximum_residual = max(maximum_residual, abs(residual))
                boundary_values[name] = {"source_voltage_v": source, "voltage_v": voltage, "current_into_line_a": into,
                                         "resistor_power_w": _product(resistance[index], into, into), "kvl_residual_v": residual}
            probe_values = []
            for probe, position in zip(frozen["probes"], positions):
                forward, backward, voltage, current = fields(position)
                density = _finite(math.fsum((_product(.5, frozen["capacitance_f_per_m"], voltage, voltage),
                                             _product(.5, frozen["inductance_h_per_m"], current, current))), "line energy density")
                probe_values.append({"id": probe["id"], "fractional_position": probe["fractional_position"],
                    "forward_voltage_v": forward, "backward_voltage_v": backward, "voltage_v": voltage,
                    "current_left_to_right_a": current, "transported_power_w": _product(voltage, current),
                    "energy_density_j_per_m": density})
            points.append({"time_s": original_time, "boundary_values": boundary_values, "probe_values": probe_values})
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": sampling._digest(frozen), "source_request": frozen,
                  "characteristic_impedance_ohm": impedance, "one_way_delay_s": delay, "propagation_speed_m_per_s": speed,
                  "reflection_coefficient_by_boundary": dict(zip(("left", "right"), gamma)), "points": points,
                  "diagnostics": {"sample_count": len(times), "probe_count": len(positions), "maximum_bounce_depth": depth,
                                  "estimated_work": work, "maximum_kvl_residual_v": maximum_residual}}
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Full line result exceeds 16 MiB", "resource_limit")
        poll(); return result
    except LosslessLineTransientError: raise
    except sampling.SParameterSamplingError as error:
        raise LosslessLineTransientError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as error:
        raise LosslessLineTransientError("numerical_failure", f"Lossless line evaluation failed: {error}") from error
