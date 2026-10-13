# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SPIKE contributors
"""Original bounded steady CCM converter estimate; see SMPS_CONVERTER_BLOCKS.md.

Each switching interval obeys L di/dt = V - R i. A periodic load-constrained
solution supplies conduction losses. Supplied transition and gate-drive losses
are input-referred overhead, without commutation feedback into the waveform.
No external implementation or device data is incorporated.
"""
from __future__ import annotations

from copy import deepcopy
import math

REQUEST_CONTRACT = "spike/smps-converter-request/v1"
RESULT_CONTRACT = "spike/smps-converter-result/v1"
TOPOLOGIES = ("synchronous_buck", "synchronous_boost", "inverting_buck_boost")
MAX_DEVICES = 64
SCAN_STEPS = 256
MAX_ITERATIONS = 64
MIN_DUTY = 1e-6
MAX_DUTY = 1 - MIN_DUTY


class SmpsConverterError(ValueError):
    """Stable admission/solver code for the worker boundary."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _require(condition, code, message):
    if not condition:
        raise SmpsConverterError(code, message)


def _keys(value, keys, name):
    _require(isinstance(value, dict) and set(value) == set(keys.split()),
             "invalid_fields", f"{name} has unexpected or missing fields.")


def _number(value, name, positive=False):
    _require(type(value) in (int, float), "invalid_number", f"{name} must be numeric.")
    try:
        value = float(value)
    except OverflowError as exc:
        raise SmpsConverterError("invalid_number", f"{name} is not representable.") from exc
    _require(math.isfinite(value) and (value > 0 if positive else value >= 0),
             "invalid_number", f"{name} must be finite and {'positive' if positive else 'nonnegative'}.")
    return value


def _text(value, name):
    _require(isinstance(value, str) and 0 < len(value) <= 256 and value.strip() == value,
             "invalid_binding", f"{name} requires 1..256 characters without surrounding whitespace.")
    return value


def _binding(value):
    return {key: _text(value[key], key) for key in ("occurrence_id", "component_ref")}


def _admit(request):
    _keys(request, "contract block_id topology input_voltage_v output_voltage_v output_current_a "
          "switching_frequency_hz switches inductor", "converter")
    _require(request["contract"] == REQUEST_CONTRACT, "contract", "Unsupported converter contract.")
    _text(request["block_id"], "block_id")
    topology = request["topology"]
    _require(topology in TOPOLOGIES, "unsupported_topology", "Select an admitted synchronous topology.")
    vin = _number(request["input_voltage_v"], "input_voltage_v", True)
    raw_vout = request["output_voltage_v"]
    _require(type(raw_vout) in (int, float), "invalid_number", "output_voltage_v must be numeric.")
    vout = _number(-raw_vout if topology == "inverting_buck_boost" else raw_vout, "output magnitude", True)
    current = _number(request["output_current_a"], "output_current_a", True)
    frequency = _number(request["switching_frequency_hz"], "switching_frequency_hz", True)
    _require(1e-6 <= vin <= 1e6 and 1e-6 <= vout <= 1e6 and 1e-9 <= current <= 1e6
             and 1 <= frequency <= 1e9, "numeric_range", "Operating inputs exceed the bounded SI envelope.")
    _require(topology != "synchronous_buck" or vout < vin, "voltage_ratio", "Buck requires 0 < Vout < Vin.")
    _require(topology != "synchronous_boost" or vout > vin, "voltage_ratio", "Boost requires Vout > Vin.")
    groups = request["switches"]
    _require(isinstance(groups, list) and len(groups) == 2, "switch_groups", "Exactly on and off groups are required.")
    parsed, seen = {}, set()
    for group in groups:
        _keys(group, "role devices series_count parallel_count rds_on_ohm rise_time_s fall_time_s "
              "gate_charge_c gate_drive_v voltage_rating_v current_rating_a", "switch group")
        role = group["role"]
        _require(role in ("on", "off") and role not in parsed, "switch_groups", "Each on/off role must occur once.")
        for key in ("series_count", "parallel_count"):
            _require(type(group[key]) is int and 1 <= group[key] <= MAX_DEVICES,
                     "device_budget", f"{key} requires 1..{MAX_DEVICES}.")
        count = group["series_count"] * group["parallel_count"]
        devices = group["devices"]
        _require(count <= MAX_DEVICES and isinstance(devices, list) and len(devices) == count,
                 "device_budget", "Group device list must match series_count * parallel_count, at most 64.")
        bindings = []
        for device in devices:
            _keys(device, "occurrence_id component_ref", "device binding")
            binding = _binding(device)
            identity = tuple(binding.values())
            _require(identity not in seen, "duplicate_binding", "Each component occurrence may belong to only one role.")
            seen.add(identity)
            bindings.append(binding)
        numeric = {key: _number(group[key], key, key.endswith("rating_v") or key.endswith("rating_a"))
                   for key in ("rds_on_ohm", "rise_time_s", "fall_time_s", "gate_charge_c",
                               "gate_drive_v", "voltage_rating_v", "current_rating_a")}
        _require((numeric["rise_time_s"] + numeric["fall_time_s"]) * frequency <= .1,
                 "transition_duration", "Transition durations must sum to at most 10% of a switching period.")
        parsed[role] = {**numeric, "devices": bindings, "series_count": group["series_count"],
                        "parallel_count": group["parallel_count"],
                        "resistance": numeric["rds_on_ohm"] * group["series_count"] / group["parallel_count"]}
    ind = request["inductor"]
    _keys(ind, "occurrence_id component_ref inductance_h dcr_ohm current_rating_a", "inductor")
    binding = _binding(ind)
    _require(tuple(binding.values()) not in seen, "duplicate_binding", "Inductor binding duplicates a switch.")
    ind = {**binding, **{key: _number(ind[key], key, key != "dcr_ohm")
                       for key in ("inductance_h", "dcr_ohm", "current_rating_a")}}
    _require(1e-12 <= ind["inductance_h"] <= 1e3, "numeric_range", "Inductance must be in [1e-12, 1e3] H.")
    for group in parsed.values():
        _require((group["resistance"] + ind["dcr_ohm"]) / frequency / ind["inductance_h"] <= .5,
                 "rl_envelope", "Each phase R/(f L) must be <= 0.5; this bounded CCM model excludes faster RL decay.")
    return topology, vin, vout, current, frequency, parsed, ind


def _phase(start, voltage, resistance, duration_over_l):
    """Integrate the independently derived exponential Taylor polynomial.

    At |R t/L| <= .5, degree 18 omitted coefficients are below 2e-22 times
    the first increment. Integrating polynomial products avoids subtracting
    nearly equal exponentials in the mean-square current.
    """
    x = resistance * duration_over_l
    coefficients = [start, (voltage - resistance * start) * duration_over_l]
    for degree in range(2, 19):
        coefficients.append(-x * coefficients[-1] / degree)
    delta = math.fsum(coefficients[1:])
    mean = math.fsum(c / (k + 1) for k, c in enumerate(coefficients))
    square = math.fsum(a * b / (i + j + 1) for i, a in enumerate(coefficients)
                       for j, b in enumerate(coefficients))
    return start + delta, mean, square, delta


def _point(duty, topology, vin, vout, current, frequency, groups, ind):
    r_on = groups["on"]["resistance"] + ind["dcr_ohm"]
    r_off = groups["off"]["resistance"] + ind["dcr_ohm"]
    v_on = vin - vout if topology == "synchronous_buck" else vin
    v_off = vin - vout if topology == "synchronous_boost" else -vout
    t_on, t_off = duty / frequency / ind["inductance_h"], (1-duty) / frequency / ind["inductance_h"]
    # Linearity supplies the start current satisfying output charge balance,
    # even when resistance vanishes and a periodic-current formula is singular.
    zero_on = _phase(0, v_on, r_on, t_on)
    zero_off = _phase(zero_on[0], v_off, r_off, t_off)
    gain_on = _phase(1, 0, r_on, t_on)
    gain_off = _phase(gain_on[0], 0, r_off, t_off)
    if topology == "synchronous_buck":
        offset = duty * zero_on[1] + (1-duty) * zero_off[1]
        gain = duty * gain_on[1] + (1-duty) * gain_off[1]
    else:
        offset, gain = (1-duty) * zero_off[1], (1-duty) * gain_off[1]
    start = (current-offset)/gain
    on = _phase(start, v_on, r_on, t_on)
    off = _phase(on[0], v_off, r_off, t_off)
    return {"duty": duty, "start": start, "on": on, "off": off,
            "residual": on[3] + off[3]}


def _solve(args):
    left = _point(MIN_DUTY, *args)
    bracket = None
    for step in range(1, SCAN_STEPS + 1):
        right = _point(MIN_DUTY + (MAX_DUTY-MIN_DUTY)*step/SCAN_STEPS, *args)
        if left["residual"] <= 0 <= right["residual"]:
            bracket = left, right
            break
        left = right
    _require(bracket is not None, "duty_unbracketed",
             "No lower-duty operating root bracketed on the bounded 256-cell scan; reduce load or revise inputs.")
    left, right = bracket
    for iteration in range(MAX_ITERATIONS):
        mid = _point((left["duty"]+right["duty"])/2, *args)
        if mid["residual"] > 0:
            right = mid
        else:
            left = mid
        if right["duty"] - left["duty"] < 2e-15:
            break
    result = _point((left["duty"]+right["duty"])/2, *args)
    scale = max(args[3], abs(result["start"]), abs(result["on"][0]), 1e-9)
    _require(abs(result["residual"]) <= 1e-9*scale, "failed_to_converge", "Periodic-current residual exceeds tolerance.")
    result["iterations"] = iteration + 1
    result["bracket_width"] = right["duty"]-left["duty"]
    return result


def evaluate_smps_converter(request):
    """Evaluate an explicit block; raise a coded error, never return partial success."""
    try:
        return _evaluate(request)
    except (OverflowError, ZeroDivisionError) as exc:
        raise SmpsConverterError("numeric_range", "Intermediate converter arithmetic exceeds the finite envelope.") from exc


def _evaluate(request):
    args = _admit(request)
    topology, vin, vout, current, frequency, groups, ind = args
    point = _solve(args)
    duty, on, off = point["duty"], point["on"], point["off"]
    minimum, peak = min(point["start"], on[0], off[0]), max(point["start"], on[0], off[0])
    _require(minimum > 0, "discontinuous_conduction", "Current reaches zero; DCM and reverse-current operation are unsupported.")
    _require(peak <= ind["current_rating_a"], "inductor_current_rating", "Peak current exceeds the supplied inductor rating.")
    mean = duty*on[1] + (1-duty)*off[1]
    square = duty*on[2] + (1-duty)*off[2]
    blocking = vin if topology == "synchronous_buck" else vout if topology == "synchronous_boost" else vin+vout
    losses, gate_total, switching_total = [], 0., 0.
    for role, phase, fraction in (("on", on, duty), ("off", off, 1-duty)):
        group = groups[role]
        count = len(group["devices"])
        _require(blocking / group["series_count"] <= group["voltage_rating_v"],
                 "switch_voltage_rating", f"{role} per-device blocking voltage exceeds its supplied rating.")
        _require(peak / group["parallel_count"] <= group["current_rating_a"],
                 "switch_current_rating", f"{role} per-device peak current exceeds its supplied rating.")
        conduction = fraction * phase[2] * group["resistance"]
        # Two edge currents; off-role gate events are opposite to on-role events.
        turn_on, turn_off = (point["start"], on[0]) if role == "on" else (on[0], off[0])
        switching = .5 * blocking * frequency * (turn_on*group["rise_time_s"] + turn_off*group["fall_time_s"])
        gate = count * group["gate_charge_c"] * group["gate_drive_v"] * frequency
        switching_total += switching
        gate_total += gate
        for binding in group["devices"]:
            losses.append({**binding, "role": role, "conduction_power_w": conduction/count,
                           "switching_power_w": switching/count, "total_power_w": (conduction+switching)/count})
    copper_loss = ind["dcr_ohm"] * square
    losses.append({**{key: ind[key] for key in ("occurrence_id", "component_ref")}, "role": "inductor",
                   "conduction_power_w": copper_loss, "switching_power_w": 0., "total_power_w": copper_loss})
    total = math.fsum(row["total_power_w"] for row in losses) + gate_total
    output = vout*current
    conduction_input_current = mean if topology == "synchronous_boost" else duty*on[1]
    input_current = conduction_input_current + (switching_total+gate_total)/vin
    input_power = vin*input_current
    balance = input_power-output-total
    _require(all(math.isfinite(v) for v in (total, input_power, square, mean)) and total >= 0,
             "numeric_range", "Nonfinite or negative converter outputs.")
    _require(abs(balance) <= 1e-8*max(input_power, output, 1e-12),
             "energy_balance", "Independent input/output/loss energy balance exceeds relative tolerance 1e-8.")
    return {"contract": RESULT_CONTRACT, "block_id": request["block_id"], "topology": topology,
            "request_snapshot": deepcopy(request),
            "model_status": "approximate", "temporal_scope": "steady_average_only",
            "duty_cycle": duty, "input_current_a": input_current, "input_power_w": input_power,
            "output_power_w": output, "total_loss_w": total, "efficiency": output/input_power,
            "inductor_average_current_a": mean, "inductor_rms_current_a": math.sqrt(square),
            "inductor_peak_current_a": peak, "inductor_minimum_current_a": minimum,
            "inductor_ripple_current_a": peak-minimum, "losses": losses,
            "auxiliary_loss_w": gate_total, "auxiliary_loss_location": "unassigned_gate_drive",
            "solver": {"iterations": point["iterations"], "duty_bracket_width": point["bracket_width"],
                       "periodic_current_residual_a": point["residual"], "energy_balance_residual_w": balance},
            "limitations": [
                "Approximate steady CCM estimate; no switching waveforms, control-loop stability or transient response.",
                "Switch overlap and gate drive are input-supplied overhead; commutation does not alter the duty/current solution.",
                "Identical devices share series voltage and parallel current equally; sharing is a caller assumption.",
                "No dead time, reverse recovery, Coss, magnetic core loss, capacitor ESR, driver quiescent power or PCB loss.",
                "Rds(on) and DCR are supplied operating values; no temperature or thermal parameters are inferred.",
                "Gate-drive dissipation is unlocated; component losses require explicit thermal mapping before deposition.",
                "Ratings are caller inputs; no SOA, avalanche, saturation curve, topology wiring or hardware qualification.",
                "The bounded root scan selects the first negative-to-positive bracket and may miss near-limit narrow roots."]}
