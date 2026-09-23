# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded linear coupled electrical/mechanical voice-coil simulation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


CONTRACT = "spike/voice-coil-drive/v1"
RESULT_CONTRACT = "spike/voice-coil-drive-result/v1"
MAX_STEPS = 100_000
MAX_CONDITION = 1.0e12
MAX_REQUEST_BYTES = 8 * 1024 * 1024

_FIELDS = {
    "contract", "resistance_ohm", "inductance_h", "force_constant_n_per_a",
    "mass_kg", "damping_n_s_per_m", "spring_n_per_m",
    "spring_equilibrium_position_m", "voltage_v", "initial_current_a",
    "initial_position_m", "initial_velocity_m_per_s", "duration_s", "time_step_s",
    "provenance",
}


def _number(request: dict[str, Any], name: str, lower: float, upper: float,
            *, lower_open: bool = False) -> float:
    value = request.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a real number.")
    try:
        value = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite representable real number.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite.")
    admitted = lower < value <= upper if lower_open else lower <= value <= upper
    if not admitted:
        relation = ">" if lower_open else ">="
        raise ValueError(f"{name} must be {relation} {lower:g} and <= {upper:g}.")
    return value


def simulate_voice_coil_drive(request: dict[str, Any]) -> dict[str, Any]:
    """Integrate the admitted linear SI model with implicit midpoint."""
    if not isinstance(request, dict):
        raise ValueError("Request must be an object.")
    unknown = set(request) - _FIELDS
    missing = _FIELDS - set(request)
    if unknown:
        raise ValueError(f"Unknown request fields: {sorted(unknown)}")
    if missing:
        raise ValueError(f"Missing request fields: {sorted(missing)}")
    if request["contract"] != CONTRACT:
        raise ValueError(f"contract must be {CONTRACT!r}.")
    provenance = request["provenance"]
    if not isinstance(provenance, str) or not provenance.strip() or len(provenance) > 512:
        raise ValueError("provenance must be a nonempty string of at most 512 characters.")

    resistance = _number(request, "resistance_ohm", 0.0, 1.0e9)
    inductance = _number(request, "inductance_h", 1.0e-12, 1.0e6)
    coupling = _number(request, "force_constant_n_per_a", -1.0e6, 1.0e6)
    mass = _number(request, "mass_kg", 1.0e-12, 1.0e6)
    damping = _number(request, "damping_n_s_per_m", 0.0, 1.0e12)
    spring = _number(request, "spring_n_per_m", 0.0, 1.0e12)
    equilibrium = _number(request, "spring_equilibrium_position_m", -1.0e9, 1.0e9)
    voltage = _number(request, "voltage_v", -1.0e9, 1.0e9)
    current0 = _number(request, "initial_current_a", -1.0e12, 1.0e12)
    position0 = _number(request, "initial_position_m", -1.0e9, 1.0e9)
    velocity0 = _number(request, "initial_velocity_m_per_s", -1.0e12, 1.0e12)
    duration = _number(request, "duration_s", 0.0, 1.0e9, lower_open=True)
    requested_step = _number(request, "time_step_s", 0.0, 1.0e9, lower_open=True)

    ratio = duration / requested_step
    if not math.isfinite(ratio):
        raise ValueError("duration_s/time_step_s exceeds numerical range.")
    steps = max(1, math.ceil(ratio))
    if steps > MAX_STEPS:
        raise ValueError(f"Simulation requires {steps} steps; limit is {MAX_STEPS}.")
    step = duration / steps
    if not math.isfinite(step) or step <= 0.0:
        raise ValueError("Uniform time step is not representable.")

    # State is [current, displacement from spring equilibrium, velocity].
    system = np.array([
        [-resistance / inductance, 0.0, -coupling / inductance],
        [0.0, 0.0, 1.0],
        [coupling / mass, -spring / mass, -damping / mass],
    ], dtype=np.float64)
    identity = np.eye(3)
    lhs = identity - 0.5 * step * system
    rhs_operator = identity + 0.5 * step * system
    source = np.array([voltage / inductance, 0.0, 0.0], dtype=np.float64)
    if not np.all(np.isfinite(lhs)) or not np.all(np.isfinite(rhs_operator)) or not np.all(np.isfinite(source)):
        raise ValueError("Admitted coefficients exceed numerical range.")
    condition = float(np.linalg.cond(lhs))
    if not math.isfinite(condition) or condition > MAX_CONDITION:
        raise ValueError(f"Implicit midpoint system is ill-conditioned ({condition:.6g}).")
    try:
        # Parameters and step size are fixed, so solve the affine update once.
        solved = np.linalg.solve(lhs, np.column_stack((rhs_operator, step * source)))
    except np.linalg.LinAlgError as exc:
        raise ValueError("Implicit midpoint system is singular.") from exc
    propagator = solved[:, :3]
    forcing = solved[:, 3]

    state = np.array([current0, position0 - equilibrium, velocity0], dtype=np.float64)
    initial_energy = 0.5 * (inductance * current0**2 + mass * velocity0**2
                            + spring * state[1]**2)
    if not math.isfinite(initial_energy):
        raise ValueError("Initial stored energy exceeds numerical range.")
    times = [0.0]
    currents = [current0]
    positions = [position0]
    velocities = [velocity0]
    supplied = resistive_loss = damping_loss = 0.0

    for index in range(1, steps + 1):
        next_state = propagator @ state + forcing
        midpoint = 0.5 * (state + next_state)
        supplied += step * voltage * midpoint[0]
        resistive_loss += step * resistance * midpoint[0] ** 2
        damping_loss += step * damping * midpoint[2] ** 2
        if not (np.all(np.isfinite(next_state)) and all(math.isfinite(value) for value in
                (supplied, resistive_loss, damping_loss))):
            raise ValueError("State or energy accounting exceeds numerical range.")
        state = next_state
        times.append(duration if index == steps else index * step)
        currents.append(float(state[0]))
        positions.append(float(state[1] + equilibrium))
        velocities.append(float(state[2]))

    final_energy = 0.5 * (inductance * state[0] ** 2 + mass * state[2] ** 2
                          + spring * state[1] ** 2)
    residual = final_energy - initial_energy - supplied + resistive_loss + damping_loss
    values = (final_energy, residual, supplied, resistive_loss, damping_loss)
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("Final energy accounting exceeds numerical range.")
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    return {
        "contract": RESULT_CONTRACT, "request_sha256": digest, "status": "completed",
        "model_status": "verification_only", "production_qualified": False,
        "provenance": provenance,
        "time_s": times, "current_a": currents, "position_m": positions,
        "velocity_m_per_s": velocities, "actual_time_step_s": step,
        "step_count": steps, "linear_system_condition": condition,
        "initial_stored_energy_j": initial_energy, "final_stored_energy_j": float(final_energy),
        "supplied_electrical_work_j": supplied, "resistive_dissipation_j": resistive_loss,
        "mechanical_damping_dissipation_j": damping_loss,
        "energy_balance_residual_j": float(residual),
        "limitations": [
            "Linear lumped voice-coil model with constant parameters and constant terminal voltage only.",
            "No solenoid, magnetic geometry, saturation, hysteresis, eddy current, thermal, contact, or control model.",
            "The force and back-EMF constants are the same reciprocal SI coefficient; supplied geometry is not interpreted.",
            "Passing numerical checks is not field, hardware, safety, lifetime, or production validation.",
        ],
    }


def _reject_duplicates(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate key: {key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    with args.request.open("rb") as stream:
        raw = stream.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES:
        parser.error("Request exceeds 8 MiB.")
    request = json.loads(raw, object_pairs_hook=_reject_duplicates)
    result = simulate_voice_coil_drive(request)
    args.result.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
