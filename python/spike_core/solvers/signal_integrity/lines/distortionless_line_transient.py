# SPDX-License-Identifier: Apache-2.0
"""Uniform Heaviside line: R'=kappa*L', G'=kappa*C'.

The telegrapher equations factor into waves travelling at v=1/sqrt(L'C')
and decaying as exp(-kappa*flight_time). Z0 stays sqrt(L'/C'). Each reflection flight
therefore adds the one-way attenuation; each probe leg adds its own decay.
Instantaneous local losses are R'I² and G'V², whose sum is2*kappa*u for
u=(C'V²+L'I²)/2. This effective distributed-circuit model assumes the
explicit distortionless ratio; arbitrary dispersive loss is not inferred.
"""
from __future__ import annotations

from fractions import Fraction
import math

from . import lossless_line_transient as lossless

sampling = lossless.sampling
REQUEST_CONTRACT = "spike/distortionless-line-transient-request/v1"
RESULT_CONTRACT = "spike/distortionless-line-transient-result/v1"
_MAX_WORK = 100_000_000
_MAX_RESULT_BYTES = 16*1024*1024


class DistortionlessLineTransientError(ValueError):
    """Invalid Heaviside line or unsupported precision, without partial output."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = "DISTORTIONLESS_LINE_TRANSIENT_"+code.upper()


def _require(condition, message, code="invalid_request"):
    if not condition:
        raise DistortionlessLineTransientError(code, message)


def _attenuation(rate, travel_time):
    if rate == 0 or travel_time == 0: return 1.
    exponent = float(Fraction(rate)*travel_time)
    _require(math.isfinite(exponent) and exponent > 0, "Attenuation exponent overflows or underflows", "numerical_failure")
    value = math.exp(-exponent)
    _require(0 < value < 1, "Positive flight attenuation underflows or is absorbed at unity", "numerical_failure")
    return value


def run_distortionless_line_transient(request, *, cancel_check=None):
    """Evaluate the explicit finite-horizon distortionless distributed model."""
    _require(cancel_check is None or callable(cancel_check), "cancel_check must be callable")

    def poll():
        if cancel_check is not None:
            try: cancelled = cancel_check()
            except Exception as error: raise DistortionlessLineTransientError("cancel_check_failed", str(error)) from error
            _require(not cancelled, "Distortionless line transient cancelled", "cancelled")

    try:
        poll(); frozen, size = sampling._snapshot(request)
        sampling._record(frozen, {"contract", "line_request", "attenuation_rate_per_s"}, "distortionless line request")
        _require(frozen["contract"] == REQUEST_CONTRACT, "Unsupported distortionless line contract")
        rate = sampling._number(frozen["attenuation_rate_per_s"], "attenuation rate")
        _require(rate >= 0, "Attenuation rate must be nonnegative")
        source = frozen["line_request"]
        impedance, delay, speed, waves, resistance, gamma, alpha, times, positions, depth, base_work = lossless._prepare(source, size, poll)
        product, finite = lossless._product, lossless._finite
        exact_delay = Fraction(delay)
        one_way = _attenuation(rate, exact_delay)
        distributed_r = product(rate, source["inductance_h_per_m"])
        distributed_g = product(rate, source["capacitance_f_per_m"])
        nepers = product(rate, math.sqrt(source["inductance_h_per_m"]), math.sqrt(source["capacitance_f_per_m"]))
        attenuation = {position: (_attenuation(rate, position*exact_delay), _attenuation(rate, (1-position)*exact_delay))
                       for position in set(positions+[Fraction(0), Fraction(1)])}
        work = base_work+2*(len(positions)+2)*len(times)*(depth+1)*8+len(times)*len(positions)*64
        _require(work <= _MAX_WORK, "Combined lossy-line work exceeds 100 million", "resource_limit")
        estimate = 2*size+len(times)*(2048+1024*len(positions))+262144
        _require(estimate <= _MAX_RESULT_BYTES, "Estimated full lossy-line result exceeds 16 MiB", "resource_limit")

        def launch(time, boundary):
            coefficient, terms = 1., []
            while time >= 0:
                poll(); value = lossless._value(time, waves[boundary])
                if value != 0: terms.append(product(coefficient, alpha[boundary], value))
                time -= exact_delay
                if time < 0 or gamma[boundary] == 0: break
                coefficient = product(coefficient, gamma[boundary]) if one_way == 1 else product(coefficient, gamma[boundary], one_way)
                boundary = 1-boundary
            return finite(math.fsum(terms), "attenuated travelling-wave sum")

        maximum_kvl, maximum_loss_residual, points = 0., 0., []
        for original_time, time in zip(source["output_times_s"], times):
            poll(); cache = {}

            def fields(position):
                forward_time, backward_time = time-position*exact_delay, time-(1-position)*exact_delay
                for key in ((forward_time, 0), (backward_time, 1)):
                    if key not in cache: cache[key] = launch(*key)
                forward, backward = cache[(forward_time, 0)], cache[(backward_time, 1)]
                forward_attenuation, backward_attenuation = attenuation[position]
                if forward_attenuation != 1: forward = product(forward, forward_attenuation)
                if backward_attenuation != 1: backward = product(backward, backward_attenuation)
                voltage = finite(math.fsum((forward, backward)), "line voltage")
                difference = finite(math.fsum((forward, -backward)), "wave voltage difference")
                current = finite(difference/impedance, "line current", difference != 0)
                return forward, backward, voltage, current

            boundary_values = {}
            for index, name in enumerate(("left", "right")):
                _, _, voltage, current = fields(Fraction(index))
                into = current if index == 0 else -current
                boundary_source = lossless._value(time, waves[index]); resistor_voltage = product(resistance[index], into)
                residual = finite(math.fsum((boundary_source, -voltage, -resistor_voltage)), "boundary KVL residual")
                _require(abs(residual) <= 2e-10+1e-9*max(abs(boundary_source), abs(voltage), abs(resistor_voltage)),
                         "Terminal KVL residual exceeds tolerance", "numerical_failure")
                maximum_kvl = max(maximum_kvl, abs(residual))
                boundary_values[name] = {"source_voltage_v": boundary_source, "voltage_v": voltage, "current_into_line_a": into,
                                         "resistor_power_w": product(resistance[index], into, into), "kvl_residual_v": residual}
            probe_values = []
            for probe, position in zip(source["probes"], positions):
                forward, backward, voltage, current = fields(position)
                density = finite(math.fsum((product(.5, source["capacitance_f_per_m"], voltage, voltage),
                                           product(.5, source["inductance_h_per_m"], current, current))), "line energy density")
                conductor, dielectric = product(distributed_r, current, current), product(distributed_g, voltage, voltage)
                total = finite(math.fsum((conductor, dielectric)), "total distributed loss")
                expected = product(2., rate, density)
                residual = finite(math.fsum((total, -expected)), "local loss balance residual")
                scale = max(total, expected)
                _require(total >= 0 and (residual == 0 if scale == 0 else abs(residual)/scale <= 1e-10),
                         "Local distributed-loss identity fails tolerance", "numerical_failure")
                maximum_loss_residual = max(maximum_loss_residual, abs(residual))
                probe_values.append({"id": probe["id"], "fractional_position": probe["fractional_position"],
                    "forward_voltage_v": forward, "backward_voltage_v": backward, "voltage_v": voltage,
                    "current_left_to_right_a": current, "transported_power_w": product(voltage, current),
                    "energy_density_j_per_m": density, "conductor_loss_w_per_m": conductor,
                    "dielectric_loss_w_per_m": dielectric, "total_loss_w_per_m": total})
            points.append({"time_s": original_time, "boundary_values": boundary_values, "probe_values": probe_values})
        result = {"contract": RESULT_CONTRACT, "model_status": "experimental", "production_qualified": False,
                  "input_digest": sampling._digest(frozen), "source_request": frozen,
                  "characteristic_impedance_ohm": impedance, "one_way_delay_s": delay, "propagation_speed_m_per_s": speed,
                  "resistance_ohm_per_m": distributed_r, "conductance_s_per_m": distributed_g,
                  "attenuation_neper_per_m": nepers, "one_way_voltage_attenuation": one_way,
                  "reflection_coefficient_by_boundary": dict(zip(("left", "right"), gamma)), "points": points,
                  "diagnostics": {"sample_count": len(times), "probe_count": len(positions), "maximum_bounce_depth": depth,
                    "estimated_work": work, "maximum_kvl_residual_v": maximum_kvl,
                    "maximum_local_loss_balance_residual_w_per_m": maximum_loss_residual}}
        _require(len(sampling._json(result)) <= _MAX_RESULT_BYTES, "Full lossy-line result exceeds 16 MiB", "resource_limit")
        poll(); return result
    except DistortionlessLineTransientError: raise
    except (lossless.LosslessLineTransientError, sampling.SParameterSamplingError) as error:
        raise DistortionlessLineTransientError(error.code.split("_", 2)[2], str(error)) from error
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as error:
        raise DistortionlessLineTransientError("numerical_failure", f"Distortionless line evaluation failed: {error}") from error
