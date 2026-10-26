# SPDX-License-Identifier: Apache-2.0
"""Bounded constant-parameter electromechanical and magnetic-circuit models.

Original implementation of reciprocal SI power conversion and linear magnetic
reluctance. These reduced models do not solve spatial electromagnetic fields.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np

CONTRACT = "spike/em-machine-result/v1"
MAX_STEPS = 20_000
_COMMON = {
    "model", "resistance_ohm", "inductance_h", "coupling_constant",
    "inertia_kg_m2", "damping_n_m_s_per_rad", "shaft_torque_n_m",
    "initial_current_a", "initial_speed_rad_s", "initial_angle_rad",
    "duration_s", "time_step_s",
}
_MAGNET = {
    "model", "turns", "current_a", "resistance_ohm", "core_length_m",
    "core_area_m2", "core_relative_permeability", "gap_length_m", "gap_area_m2",
}
MU0 = 4.0e-7 * math.pi  # Declared engineering approximation, H/m.


def _number(request: dict, key: str, lower: float, upper: float) -> float:
    value = request[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a real number.")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{key} is outside representable range.") from exc
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"{key} must be finite and between {lower:g} and {upper:g}.")
    return value


def run_machine(parameters: dict) -> dict:
    """Run an explicit SI parameter model; reject unknown or missing fields."""
    if not isinstance(parameters, dict) or any(not isinstance(k, str) for k in parameters):
        raise ValueError("Machine parameters must be an object with string keys.")
    model = parameters.get("model")
    if not isinstance(model, str) or model not in {"pm_dc_motor", "pm_dc_generator", "electromagnet"}:
        raise ValueError("model must be pm_dc_motor, pm_dc_generator or electromagnet.")
    required = (_MAGNET if model == "electromagnet" else
                _COMMON | ({"voltage_v"} if model == "pm_dc_motor" else {"load_resistance_ohm"}))
    missing, unknown = required - parameters.keys(), parameters.keys() - required - {"provenance"}
    if missing or unknown:
        raise ValueError(f"Missing machine fields: {sorted(missing)}; unknown fields: {sorted(unknown)}")
    provenance = parameters.get("provenance", "Explicit user-supplied SI model parameters")
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 512:
        raise ValueError("provenance must be a nonempty string of at most 512 characters.")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            payload = _electromagnet(parameters) if model == "electromagnet" else _rotating(parameters)
        canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"), allow_nan=False)
        result = {
            "contract": CONTRACT, "model": model, "status": "completed",
            "model_status": "experimental", "production_qualified": False,
            "request_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "provenance": provenance, **payload,
        }
        # Result admission also covers scalar overflow in derived quantities.
        json.dumps(result, allow_nan=False)
        return result
    except (OverflowError, FloatingPointError, np.linalg.LinAlgError) as exc:
        raise ValueError("Machine model exceeded its finite numerical range.") from exc


def _rotating(p: dict) -> dict[str, Any]:
    generator = p["model"] == "pm_dc_generator"
    resistance = _number(p, "resistance_ohm", 0, 1e9)
    inductance = _number(p, "inductance_h", 1e-9, 1e6)
    coupling = _number(p, "coupling_constant", -1e6, 1e6)
    inertia = _number(p, "inertia_kg_m2", 1e-9, 1e6)
    damping = _number(p, "damping_n_m_s_per_rad", 0, 1e9)
    shaft_torque = _number(p, "shaft_torque_n_m", -1e9, 1e9)
    current = _number(p, "initial_current_a", -1e9, 1e9)
    speed = _number(p, "initial_speed_rad_s", -1e9, 1e9)
    angle = _number(p, "initial_angle_rad", -1e12, 1e12)
    duration = _number(p, "duration_s", 1e-9, 1e6)
    requested_step = _number(p, "time_step_s", 1e-9, 1e6)
    voltage = 0.0 if generator else _number(p, "voltage_v", -1e9, 1e9)
    load = _number(p, "load_resistance_ohm", 0, 1e9) if generator else 0.0
    steps = max(1, math.ceil(duration / requested_step))
    if steps > MAX_STEPS:
        raise ValueError(f"Machine history exceeds {MAX_STEPS} steps; increase time_step_s.")
    step = duration / steps
    sqrt_l, sqrt_j = math.sqrt(inductance), math.sqrt(inertia)
    # Energy coordinates avoid conditioning dependent on unlike current/speed units.
    system = np.array([
        [-(resistance + load) / inductance, -coupling / (sqrt_l * sqrt_j)],
        [coupling / (sqrt_l * sqrt_j), -damping / inertia],
    ])
    lhs = np.eye(2) - 0.5 * step * system
    rhs = np.eye(2) + 0.5 * step * system
    condition = float(np.linalg.cond(lhs))
    if not math.isfinite(condition) or condition > 1e12:
        raise ValueError("Machine midpoint system is ill-conditioned; reduce the step or parameter spread.")
    source = np.array([voltage / sqrt_l, shaft_torque / sqrt_j])
    affine = np.linalg.solve(lhs, np.column_stack((rhs, step * source)))
    state = np.array([sqrt_l * current, sqrt_j * speed])
    initial_energy = float(0.5 * np.dot(state, state))
    history = {key: [] for key in (
        "time_s", "current_a", "speed_rad_s", "angle_rad", "torque_n_m",
        "back_emf_v", "terminal_voltage_v", "terminal_power_w", "shaft_power_w",
    )}

    def record(time: float, amps: float, omega: float, theta: float) -> None:
        terminal_voltage = -load * amps if generator else voltage
        values = (time, amps, omega, theta, coupling * amps, coupling * omega,
                  terminal_voltage, terminal_voltage * amps, shaft_torque * omega)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Machine history exceeded finite numerical range.")
        for key, value in zip(history, values):
            history[key].append(float(value))

    record(0, current, speed, angle)
    electrical = mechanical = copper = friction = load_heat = 0.0
    for index in range(1, steps + 1):
        next_state = affine[:, :2] @ state + affine[:, 2]
        midpoint = 0.5 * (state + next_state)
        amps_mid, speed_mid = midpoint[0] / sqrt_l, midpoint[1] / sqrt_j
        electrical += step * voltage * amps_mid
        mechanical += step * shaft_torque * speed_mid
        copper += step * resistance * amps_mid**2
        friction += step * damping * speed_mid**2
        load_heat += step * load * amps_mid**2
        angle += step * speed_mid
        state = next_state
        record(duration if index == steps else index * step,
               state[0] / sqrt_l, state[1] / sqrt_j, angle)
    final_energy = float(0.5 * np.dot(state, state))
    residual = final_energy - initial_energy - electrical - mechanical + copper + friction + load_heat
    ledger = {
        "initial_stored_energy_j": initial_energy, "final_stored_energy_j": final_energy,
        "supplied_electrical_work_j": electrical, "supplied_shaft_work_j": mechanical,
        "terminal_electrical_work_j": electrical - load_heat,
        "copper_loss_j": copper, "damping_loss_j": friction, "load_energy_j": load_heat,
        "balance_residual_j": residual,
    }
    ledger = {key: float(value) for key, value in ledger.items()}
    scale = max(initial_energy, final_energy, abs(electrical), abs(mechanical), copper + friction + load_heat, 1e-30)
    ledger["relative_balance_residual"] = float(abs(residual) / scale)
    return {
        "histories": history, "energy": ledger, "step_count": steps,
        "actual_time_step_s": step, "linear_system_condition": condition,
        "summary": {key: values[-1] for key, values in history.items()},
        "sign_convention": "Positive current enters the machine; positive shaft torque drives positive rotation. Negative terminal power is electrical generation.",
        "limitations": [
            "Constant reciprocal SI coupling K: torque=K*i and back_emf=K*omega; supplied parameters, no spatial field solve.",
            "Constant voltage and shaft torque; generator is connected only to the specified resistor.",
            "No saturation, hysteresis, eddy currents, commutation, inverter, thermal feedback, friction beyond viscous damping, or geometry inference.",
            "Implicit midpoint is second order; energy closure alone does not establish time resolution. Refine the time step for the intended transient.",
            "Numerical verification does not establish hardware or production qualification.",
        ],
    }


def _electromagnet(p: dict) -> dict:
    turns = _number(p, "turns", 1, 1e6)
    if not turns.is_integer():
        raise ValueError("turns must be an integer.")
    current = _number(p, "current_a", -1e6, 1e6)
    resistance = _number(p, "resistance_ohm", 0, 1e9)
    core_length = _number(p, "core_length_m", 1e-9, 1e3)
    core_area = _number(p, "core_area_m2", 1e-12, 1e3)
    permeability = _number(p, "core_relative_permeability", 1, 1e7)
    gap = _number(p, "gap_length_m", 1e-9, 1e3)
    gap_area = _number(p, "gap_area_m2", 1e-12, 1e3)
    reluctance = core_length / (MU0 * permeability * core_area) + gap / (MU0 * gap_area)
    flux = turns * current / reluctance
    inductance = turns**2 / reluctance
    energy = 0.5 * inductance * current**2
    return {
        "summary": {
            "reluctance_a_turn_per_wb": reluctance, "flux_wb": flux,
            "flux_linkage_wb_turn": turns * flux, "inductance_h": inductance,
            "core_flux_density_t": flux / core_area, "gap_flux_density_t": flux / gap_area,
            "gap_closing_force_n": flux**2 / (2 * MU0 * gap_area),
            "stored_energy_j": energy, "coenergy_j": energy,
            "copper_loss_w": resistance * current**2,
        },
        "permeability_of_free_space_h_per_m": MU0,
        "limitations": [
            "Linear single-path core with exactly one uniform moving air gap; core length and areas stay fixed as the gap closes.",
            "Force is the fixed-current coenergy derivative in the gap-closing direction; no moving actuator dynamics.",
            "No fringing, leakage, saturation, hysteresis, eddy currents, permanent magnets, spatial field solve, or geometry inference.",
            "Supplied constant permeability must be appropriate to the operating point; saturation is not checked.",
            "Numerical verification does not establish hardware or production qualification.",
        ],
    }
