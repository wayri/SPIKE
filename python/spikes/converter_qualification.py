"""Deterministic coupled-reference qualification for converter edge cases.

These fixtures exercise reviewable constitutive models outside the native MNA
kernel.  Passing this suite qualifies the fixtures and their assertions only;
it does not qualify native electrothermal/magnetic coupling, a production
compact model, hard real-time execution, HIL, or competitive superiority.
"""

from __future__ import annotations

import math
import platform
from datetime import datetime, timezone
from typing import Any, Callable

from .dynamic_devices import (
    DynamicDiodeModel,
    DynamicDiodeValidity,
    ReverseRecoveryState,
)


REPORT_CONTRACT = "spikes/converter-coupled-reference-qualification/v1"
CASE_CONTRACT = "spikes/converter-coupled-reference-case/v1"


def _gate(gate_id: str, passed: bool, observed: Any, limit: Any, rule: str) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "passed": bool(passed),
        "observed": observed,
        "limit": limit,
        "rule": rule,
    }


def _case(
    case_id: str,
    title: str,
    model: str,
    runner: Callable[[], tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    try:
        metrics, events, gates = runner()
        status = "passed" if gates and all(item["passed"] for item in gates) else "failed"
        issues: list[dict[str, str]] = [] if status == "passed" else [{
            "code": "SPIKES_CONVERTER_REFERENCE_GATE_FAILED",
            "message": "One or more declared coupled-reference gates failed.",
        }]
    except Exception as exc:  # fail closed and retain a serializable report
        metrics, events, gates, status = {}, [], [], "failed"
        issues = [{
            "code": "SPIKES_CONVERTER_REFERENCE_EXECUTION_FAILED",
            "message": str(exc)[:4096],
        }]
    return {
        "contract": CASE_CONTRACT,
        "case_id": case_id,
        "title": title,
        "status": status,
        "qualification_scope": "deterministic_coupled_reference",
        "model": model,
        "metrics": metrics,
        "events": events,
        "gates": gates,
        "limitations": list(limitations),
        "issues": issues,
    }


def _reverse_recovery() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    dt = 0.5e-9
    transit_time = 30.0e-9
    model = DynamicDiodeModel(
        saturation_current_a=2.0e-10,
        emission_coefficient=1.45,
        zero_bias_capacitance_f=80.0e-12,
        junction_potential_v=0.9,
        grading_coefficient=0.42,
        forward_depletion_coefficient=0.45,
        transit_time_s=transit_time,
        validity=DynamicDiodeValidity(
            minimum_voltage_v=-50.0,
            maximum_voltage_v=0.75,
            maximum_absolute_current_a=1.0e5,
            maximum_timestep_s=2.0e-9,
        ),
    )
    state = ReverseRecoveryState()
    previous_v = 0.49
    for _ in range(600):
        point = model.advance(0.49, previous_v, 300.15, dt, state)
        state = point.state
        previous_v = 0.49
    armed_charge = state.stored_charge_c
    dc = model.evaluate(0.49, 300.15)
    expected_armed_charge = transit_time * dc.current_a

    events = [{
        "sequence": 0,
        "kind": "stored_charge_armed",
        "time_s": 0.0,
        "value_c": armed_charge,
    }]
    negative_transport: list[float] = []
    charges = [armed_charge]
    recovered_charge = 0.0
    recovery_90_time = None
    previous_v = 0.49
    for index in range(1, 601):
        point = model.advance(-20.0, previous_v, 300.15, dt, state)
        previous_v = -20.0
        state = point.state
        charges.append(state.stored_charge_c)
        negative_transport.append(point.transport_current_a)
        recovered_charge += -point.transport_current_a * dt
        if index == 1:
            events.append({
                "sequence": 1,
                "kind": "reverse_current_peak",
                "time_s": index * dt,
                "value_a": point.transport_current_a,
            })
        if recovery_90_time is None and state.stored_charge_c <= 0.1 * armed_charge:
            recovery_90_time = index * dt
            events.append({
                "sequence": 2,
                "kind": "stored_charge_recovered_90pct",
                "time_s": recovery_90_time,
                "remaining_charge_c": state.stored_charge_c,
            })

    exact_recovered = armed_charge - state.stored_charge_c
    charge_balance_error = abs(recovered_charge - exact_recovered)
    monotonic = all(right <= left for left, right in zip(charges, charges[1:]))
    expected_90 = math.log(10.0) / math.log1p(dt / transit_time) * dt
    metrics = {
        "time_step_s": dt,
        "transit_time_s": transit_time,
        "forward_current_a": dc.current_a,
        "armed_charge_c": armed_charge,
        "expected_dc_charge_c": expected_armed_charge,
        "peak_reverse_transport_current_a": min(negative_transport),
        "recovered_charge_c": recovered_charge,
        "remaining_charge_c": state.stored_charge_c,
        "charge_balance_error_c": charge_balance_error,
        "recovery_90_time_s": recovery_90_time,
        "discrete_analytic_recovery_90_time_s": expected_90,
    }
    gates = [
        _gate(
            "reverse.precharge_equilibrium",
            abs(armed_charge - expected_armed_charge) <= expected_armed_charge * 1.0e-4,
            armed_charge,
            expected_armed_charge * 1.0e-4,
            "abs(observed - expected_dc_charge) <= limit",
        ),
        _gate(
            "reverse.negative_tail",
            min(negative_transport) < 0.0,
            min(negative_transport),
            0.0,
            "peak reverse transport current < 0 A",
        ),
        _gate(
            "reverse.monotonic_charge_decay",
            monotonic,
            monotonic,
            True,
            "stored charge is non-increasing after commutation",
        ),
        _gate(
            "reverse.discrete_charge_conservation",
            charge_balance_error <= max(1.0e-24, armed_charge * 1.0e-12),
            charge_balance_error,
            max(1.0e-24, armed_charge * 1.0e-12),
            "integrated recovery tail equals removed state charge",
        ),
        _gate(
            "reverse.recovery_event",
            recovery_90_time is not None and abs(recovery_90_time - expected_90) <= dt,
            recovery_90_time,
            expected_90,
            "90% recovery event is within one step of the discrete analytic time",
        ),
    ]
    return metrics, events, gates


def _electrothermal_feedback() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    ambient = 300.15
    r0 = 0.04
    alpha = 0.004
    thermal_r = 10.0
    thermal_c = 0.05
    current_on = 10.0
    duty = 0.5
    dt = 0.001
    duration = 5.0
    effective_i2 = duty * current_on * current_on
    loop_gain = effective_i2 * r0 * alpha * thermal_r
    expected_rise = effective_i2 * r0 * thermal_r / (1.0 - loop_gain)
    expected_temperature = ambient + expected_rise

    temperature = ambient
    initial_power = effective_i2 * r0
    warning_temperature = ambient + 15.0
    events: list[dict[str, Any]] = []
    peak_power = initial_power
    steps = round(duration / dt)
    for index in range(1, steps + 1):
        resistance = r0 * (1.0 + alpha * (temperature - ambient))
        power = effective_i2 * resistance
        peak_power = max(peak_power, power)
        temperature += dt / thermal_c * (
            power - (temperature - ambient) / thermal_r
        )
        if not events and temperature >= warning_temperature:
            events.append({
                "sequence": 0,
                "kind": "junction_temperature_warning",
                "time_s": index * dt,
                "temperature_k": temperature,
                "limit_k": warning_temperature,
            })

    error = abs(temperature - expected_temperature)
    metrics = {
        "ambient_temperature_k": ambient,
        "final_temperature_k": temperature,
        "closed_form_steady_temperature_k": expected_temperature,
        "absolute_steady_error_k": error,
        "thermal_loop_gain": loop_gain,
        "initial_loss_w": initial_power,
        "peak_loss_w": peak_power,
        "temperature_coefficient_per_k": alpha,
        "duration_s": duration,
        "time_step_s": dt,
    }
    gates = [
        _gate("thermal.stable_feedback", 0.0 < loop_gain < 1.0, loop_gain, 1.0, "0 < loop gain < 1"),
        _gate("thermal.closed_form_correlation", error <= 0.02, error, 0.02, "final temperature error <= 0.02 K"),
        _gate("thermal.positive_feedback_visible", peak_power > initial_power, peak_power, initial_power, "hot loss > ambient loss"),
        _gate("thermal.warning_event", len(events) == 1, len(events), 1, "exactly one threshold-crossing event"),
    ]
    return metrics, events, gates


def _magnetic_saturation() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    nominal_l = 20.0e-6
    minimum_l = 3.0e-6
    saturation_current = 8.0
    exponent = 8
    initial_current = 5.0
    input_voltage = 24.0
    output_voltage = 48.0
    period = 10.0e-6
    duty = 0.5
    dt = 10.0e-9

    def differential_l(current: float) -> float:
        ratio = abs(current) / saturation_current
        return minimum_l + (nominal_l - minimum_l) / (1.0 + ratio ** exponent)

    current = initial_current
    linear_current = initial_current
    peak_current = current
    linear_peak = linear_current
    minimum_observed_l = nominal_l
    events: list[dict[str, Any]] = []
    entered = False
    steps = round(period / dt)
    for index in range(1, steps + 1):
        time_s = index * dt
        on = time_s <= duty * period
        voltage = input_voltage if on else input_voltage - output_voltage
        inductance = differential_l(current)
        minimum_observed_l = min(minimum_observed_l, inductance)
        current = max(0.0, current + voltage / inductance * dt)
        linear_current = max(0.0, linear_current + voltage / nominal_l * dt)
        peak_current = max(peak_current, current)
        linear_peak = max(linear_peak, linear_current)
        if not entered and current >= saturation_current:
            entered = True
            events.append({
                "sequence": 0,
                "kind": "differential_inductance_saturation_enter",
                "time_s": time_s,
                "current_a": current,
                "threshold_a": saturation_current,
            })
        if entered and len(events) == 1 and not on and current <= saturation_current:
            events.append({
                "sequence": 1,
                "kind": "differential_inductance_saturation_exit",
                "time_s": time_s,
                "current_a": current,
                "threshold_a": saturation_current,
            })

    ideal_linear_peak = initial_current + input_voltage * duty * period / nominal_l
    metrics = {
        "nominal_differential_inductance_h": nominal_l,
        "minimum_differential_inductance_h": minimum_observed_l,
        "saturation_current_a": saturation_current,
        "nonlinear_peak_current_a": peak_current,
        "linear_reference_peak_current_a": linear_peak,
        "analytic_linear_peak_current_a": ideal_linear_peak,
        "final_nonlinear_current_a": current,
        "final_linear_current_a": linear_current,
        "period_s": period,
        "time_step_s": dt,
    }
    gates = [
        _gate("magnetic.linear_reference", abs(linear_peak - ideal_linear_peak) <= 0.02, abs(linear_peak - ideal_linear_peak), 0.02, "Euler linear peak agrees with analytic ramp"),
        _gate("magnetic.inductance_collapse", minimum_observed_l <= 0.5 * nominal_l, minimum_observed_l, 0.5 * nominal_l, "minimum Ldiff <= 50% nominal"),
        _gate("magnetic.current_divergence", peak_current >= 1.25 * linear_peak, peak_current / linear_peak, 1.25, "nonlinear peak >= 1.25 times linear peak"),
        _gate("magnetic.event_pair", [item["kind"] for item in events] == ["differential_inductance_saturation_enter", "differential_inductance_saturation_exit"], [item["kind"] for item in events], ["enter", "exit"], "ordered saturation enter/exit events"),
        _gate("magnetic.nonnegative_current", current >= 0.0, current, 0.0, "diode-constrained current remains non-negative"),
    ]
    return metrics, events, gates


def _protection_events() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    input_voltage = 48.0
    inductance = 10.0e-6
    resistance = 0.05
    freewheel_voltage = 12.0
    warning_current = 50.0
    trip_current = 100.0
    shutdown_delay = 0.5e-6
    dt = 10.0e-9
    # Covers the RL rise, comparator latency, and bounded freewheel decay.
    duration = 100.0e-6
    current = 0.0
    peak_current = 0.0
    trip_time = None
    shutdown_time = None
    shutdown = False
    events: list[dict[str, Any]] = []
    for index in range(1, round(duration / dt) + 1):
        time_s = index * dt
        voltage = -freewheel_voltage if shutdown else input_voltage
        current = max(0.0, current + (voltage - resistance * current) / inductance * dt)
        peak_current = max(peak_current, current)
        if not any(item["kind"] == "overcurrent_warning" for item in events) and current >= warning_current:
            events.append({"sequence": len(events), "kind": "overcurrent_warning", "time_s": time_s, "current_a": current, "limit_a": warning_current})
        if trip_time is None and current >= trip_current:
            trip_time = time_s
            events.append({"sequence": len(events), "kind": "overcurrent_trip", "time_s": time_s, "current_a": current, "limit_a": trip_current})
        if trip_time is not None and not shutdown and time_s + 0.5 * dt >= trip_time + shutdown_delay:
            shutdown = True
            shutdown_time = time_s
            events.append({"sequence": len(events), "kind": "gate_shutdown", "time_s": time_s, "current_a": current, "command_delay_s": shutdown_delay})
        if shutdown and current == 0.0:
            events.append({"sequence": len(events), "kind": "current_extinguished", "time_s": time_s, "current_a": 0.0})
            break

    warning_analytic = -inductance / resistance * math.log1p(-warning_current * resistance / input_voltage)
    trip_analytic = -inductance / resistance * math.log1p(-trip_current * resistance / input_voltage)
    kinds = [item["kind"] for item in events]
    observed_warning = events[0]["time_s"] if events else None
    metrics = {
        "warning_current_a": warning_current,
        "trip_current_a": trip_current,
        "peak_current_a": peak_current,
        "warning_time_s": observed_warning,
        "analytic_warning_time_s": warning_analytic,
        "trip_time_s": trip_time,
        "analytic_trip_time_s": trip_analytic,
        "shutdown_time_s": shutdown_time,
        "shutdown_delay_s": shutdown_delay,
        "final_current_a": current,
        "time_step_s": dt,
    }
    gates = [
        _gate("protection.event_order", kinds == ["overcurrent_warning", "overcurrent_trip", "gate_shutdown", "current_extinguished"], kinds, ["warning", "trip", "shutdown", "extinguished"], "events occur exactly once in safety order"),
        _gate("protection.warning_localization", observed_warning is not None and abs(observed_warning - warning_analytic) <= dt, observed_warning, warning_analytic, "warning crossing is within one step of analytic RL crossing"),
        _gate("protection.trip_localization", trip_time is not None and abs(trip_time - trip_analytic) <= dt, trip_time, trip_analytic, "trip crossing is within one step of analytic RL crossing"),
        _gate("protection.command_latency", shutdown_time is not None and trip_time is not None and abs((shutdown_time - trip_time) - shutdown_delay) <= dt, None if shutdown_time is None or trip_time is None else shutdown_time - trip_time, shutdown_delay, "gate shutdown delay is within one step of command latency"),
        _gate("protection.current_extinguished", current == 0.0, current, 0.0, "freewheel path extinguishes current within bounded duration"),
    ]
    return metrics, events, gates


def run_converter_reference_qualification() -> dict[str, Any]:
    """Run all bounded fixtures and return a JSON-safe fail-closed report."""

    cases = [
        _case(
            "converter.reverse_recovery_commutation",
            "Buck freewheel-diode stored-charge commutation",
            "DynamicDiodeModel implicit mobile-charge state",
            _reverse_recovery,
            (
                "Prescribed terminal voltage; no native MNA or package parasitics.",
                "Single-lifetime reverse-recovery reference, not a vendor compact model.",
            ),
        ),
        _case(
            "converter.electrothermal_switch_feedback",
            "PWM switch conduction-loss electrothermal feedback",
            "Lumped temperature-dependent Rds(on) plus one-pole thermal RC",
            _electrothermal_feedback,
            (
                "Cycle-averaged conduction loss; switching and gate losses are omitted.",
                "One junction temperature and fixed ambient; no spatial thermal solution.",
            ),
        ),
        _case(
            "converter.magnetic_saturation",
            "PWM inductor differential-saturation excursion",
            "Bounded current-dependent differential inductance",
            _magnetic_saturation,
            (
                "Prescribed converter voltages; no native magnetic DAE coupling.",
                "No hysteresis, core loss, fringing, temperature, or winding parasitics.",
            ),
        ),
        _case(
            "converter.overcurrent_protection",
            "Short-circuit warning, trip, delayed shutdown and freewheel decay",
            "Piecewise RL fault reference with deterministic comparator events",
            _protection_events,
            (
                "Ideal thresholds and fixed command latency; no noise or metastability.",
                "Prescribed freewheel clamp; no semiconductor avalanche model.",
            ),
        ),
    ]
    passed = all(item["status"] == "passed" for item in cases)
    return {
        "contract": REPORT_CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "qualification_scope": "coupled_reference_only",
        "deterministic": True,
        "case_count": len(cases),
        "passed_case_count": sum(item["status"] == "passed" for item in cases),
        "native_mna_integration_qualified": False,
        "production_compact_models_qualified": False,
        "hard_realtime_qualified": False,
        "hil_claim_eligible": False,
        "competitive_claim_eligible": False,
        "platform": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "cases": cases,
        "claim_guard": (
            "Passing qualifies deterministic coupled-reference fixtures only. "
            "It is not evidence of native MNA/DAE integration, production device "
            "models, hard real-time/HIL behavior, or superiority over another solver."
        ),
    }


__all__ = [
    "CASE_CONTRACT",
    "REPORT_CONTRACT",
    "run_converter_reference_qualification",
]
