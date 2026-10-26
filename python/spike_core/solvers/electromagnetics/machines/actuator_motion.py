# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded fixed-excitation, quasi-static 1DOF actuator motion review."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .actuator_force_map import analyze_force_map

CONTRACT = "spike/actuator-motion/v1"
RESULT_CONTRACT = "spike/actuator-motion-result/v1"
MAX_STEPS = 100_000


def _number(value, label, minimum=None, maximum=None):
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number.")
    try:
        value = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{label} outside bounds.")
    return value


def simulate_actuator_motion(request: dict) -> dict:
    fields = {"contract", "force_map", "mass_kg", "damping_n_s_per_m", "spring_n_per_m",
              "spring_equilibrium_position_m", "initial_position_m", "initial_velocity_m_per_s",
              "duration_s", "time_step_s"}
    if not isinstance(request, dict) or set(request) != fields:
        raise ValueError("Motion request has missing or unknown fields.")
    if request["contract"] != CONTRACT:
        raise ValueError("Unsupported actuator-motion contract.")
    force_review = analyze_force_map(request["force_map"])
    if force_review["status"] != "consistent":
        raise ValueError("Motion requires a consistent admitted force map.")

    mass = _number(request["mass_kg"], "mass_kg", 1e-12)
    damping = _number(request["damping_n_s_per_m"], "damping_n_s_per_m", 0)
    spring = _number(request["spring_n_per_m"], "spring_n_per_m", 0)
    equilibrium = _number(request["spring_equilibrium_position_m"], "spring_equilibrium_position_m")
    position = _number(request["initial_position_m"], "initial_position_m")
    velocity = _number(request["initial_velocity_m_per_s"], "initial_velocity_m_per_s")
    duration = _number(request["duration_s"], "duration_s", 1e-15)
    step = _number(request["time_step_s"], "time_step_s", 1e-15)
    step_ratio = duration / step
    if not math.isfinite(step_ratio):
        raise ValueError("duration_s/time_step_s exceeds numerical range.")
    nearest_steps = round(step_ratio)
    if abs(step_ratio - nearest_steps) <= 8 * math.ulp(step_ratio):
        step_ratio = float(nearest_steps)
    required_steps = math.ceil(step_ratio)
    if required_steps > MAX_STEPS:
        raise ValueError(f"Motion request exceeds {MAX_STEPS} time steps.")

    x_map = np.asarray(request["force_map"]["position_m"], dtype=float)
    f_map = np.asarray(request["force_map"]["force_n"], dtype=float)
    xmin, xmax = float(x_map[0]), float(x_map[-1])
    if not xmin <= position <= xmax:
        raise ValueError("initial_position_m is outside the force-map stroke.")
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        try:
            slopes = np.diff(f_map) / np.diff(x_map)
        except FloatingPointError as exc:
            raise ValueError("Force-map slope exceeds numerical range.") from exc
    # The eliminated midpoint equation is strictly increasing under this bound,
    # so its piecewise-linear root is unique without nonlinear iteration guesses.
    try:
        inertial_slope = (2 * mass / step) / step
        minimum_slope = inertial_slope + damping / step + 0.5 * (spring - float(np.max(slopes)))
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("time_step_s produces an unrepresentable midpoint system.") from exc
    if not math.isfinite(minimum_slope) or minimum_slope <= 0:
        raise ValueError("time_step_s does not guarantee a unique implicit-midpoint solve.")

    def force(x):
        if x < xmin or x > xmax:
            raise ValueError("Force evaluation outside the declared stroke.")
        return float(np.interp(x, x_map, f_map))

    def residual(x1, x0, v0, h):
        midpoint_x = 0.5 * (x0 + x1)
        midpoint_v = (x1 - x0) / h
        try:
            value = (2 * mass * (x1 - x0 - h * v0) / h**2 - force(midpoint_x)
                     + damping * midpoint_v + spring * (midpoint_x - equilibrium))
        except (OverflowError, ZeroDivisionError) as exc:
            raise ValueError("Implicit-midpoint residual exceeds numerical range.") from exc
        if not math.isfinite(value):
            raise ValueError("Implicit-midpoint residual exceeds numerical range.")
        return value

    def endpoint(x0, v0, h):
        lo, hi = xmin, xmax
        glo, ghi = residual(lo, x0, v0, h), residual(hi, x0, v0, h)
        if glo > 0:
            return None, xmin
        if ghi < 0:
            return None, xmax
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if residual(mid, x0, v0, h) < 0:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi), None

    times, positions, velocities = [0.0], [position], [velocity]
    midpoint_work = map_work = damping_loss = 0.0
    try:
        initial_energy = (0.5 * mass * velocity**2
                          + 0.5 * spring * (position - equilibrium)**2)
    except OverflowError as exc:
        raise ValueError("Initial mechanical energy exceeds numerical range.") from exc
    if not math.isfinite(initial_energy):
        raise ValueError("Initial mechanical energy exceeds numerical range.")
    termination = "duration_reached"
    boundary = None
    time = 0.0
    initial_acceleration = (force(position) - damping * velocity
                            - spring * (position - equilibrium)) / mass
    if not math.isfinite(initial_acceleration):
        raise ValueError("Initial acceleration exceeds numerical range.")
    if ((position == xmax and (velocity > 0 or (velocity == 0 and initial_acceleration > 0))) or
            (position == xmin and (velocity < 0 or (velocity == 0 and initial_acceleration < 0)))):
        termination = "stroke_boundary_reached"
        boundary = "maximum" if position == xmax else "minimum"
    def boundary_event(hit, upper_h, x0, v0):
        low, high = 0.0, upper_h
        for _ in range(60):
            trial = 0.5 * (low + high)
            value = residual(hit, x0, v0, trial)
            if (hit == xmax and value > 0) or (hit == xmin and value < 0):
                low = trial
            else:
                high = trial
        return high

    def first_boundary_event(x0, v0, upper_h):
        events = []
        for boundary_position in (xmin, xmax):
            dx = boundary_position - x0
            midpoint_x = 0.5 * (x0 + boundary_position)
            a = spring * (midpoint_x - equilibrium) - force(midpoint_x)
            b = damping * dx - 2 * mass * v0
            c_term = 2 * mass * dx
            if not all(math.isfinite(value) for value in (a, b, c_term)):
                raise ValueError("Stroke-event equation exceeds numerical range.")
            roots = []
            if a == 0:
                if b != 0:
                    roots = [-c_term / b]
            else:
                discriminant = b * b - 4 * a * c_term
                if not math.isfinite(discriminant):
                    raise ValueError("Stroke-event discriminant exceeds numerical range.")
                if discriminant >= 0:
                    root_discriminant = math.sqrt(discriminant)
                    q = -0.5 * (b + math.copysign(root_discriminant, b))
                    roots = ([q / a, c_term / q] if q != 0 else [-b / a])
            threshold = 64 * math.ulp(upper_h)
            for root in roots:
                if math.isfinite(root) and threshold < root <= upper_h + threshold:
                    events.append((min(root, upper_h), boundary_position))
        return min(events, default=None, key=lambda item: item[0])

    for step_index in range(required_steps):
        if time >= duration:
            break
        if termination != "duration_reached":
            break
        target_time = min(duration, (step_index + 1) * step)
        h = target_time - time
        if h <= max(math.ulp(duration), math.ulp(time)):
            time = duration
            break
        event = first_boundary_event(position, velocity, h)
        if event is not None:
            h, candidate = event
            termination = "stroke_boundary_reached"
            boundary = "maximum" if candidate == xmax else "minimum"
        else:
            candidate, hit = endpoint(position, velocity, h)
            if hit is not None:
                # Defensive fallback for roundoff around the analytical event roots.
                h = boundary_event(hit, h, position, velocity)
                candidate = hit
                termination = "stroke_boundary_reached"
                boundary = "maximum" if hit == xmax else "minimum"
        midpoint_x = 0.5 * (position + candidate)
        midpoint_v = (candidate - position) / h
        new_velocity = 2 * midpoint_v - velocity
        dx = candidate - position
        midpoint_increment = force(midpoint_x) * dx
        # Exact integral of the continuous piecewise-linear admitted map. Split
        # at map knots so this remains distinct from midpoint quadrature.
        cuts = [position] + [float(x) for x in x_map if min(position, candidate) < x < max(position, candidate)] + [candidate]
        if candidate < position:
            cuts = [position] + sorted(cuts[1:-1], reverse=True) + [candidate]
        map_increment = sum(0.5 * (force(a) + force(b)) * (b - a)
                            for a, b in zip(cuts, cuts[1:]))
        loss_increment = damping * midpoint_v**2 * h
        if not all(math.isfinite(v) for v in (new_velocity, midpoint_increment,
                                               map_increment, loss_increment)):
            raise ValueError("Motion state or work exceeds numerical range.")
        midpoint_work += midpoint_increment
        map_work += map_increment
        damping_loss += loss_increment
        time = time + h if termination != "duration_reached" else target_time
        position, velocity = candidate, new_velocity
        times.append(time); positions.append(position); velocities.append(velocity)
        if termination != "duration_reached":
            break

    try:
        final_energy = (0.5 * mass * velocity**2
                        + 0.5 * spring * (position - equilibrium)**2)
    except OverflowError as exc:
        raise ValueError("Final mechanical energy exceeds numerical range.") from exc
    balance = final_energy - initial_energy - midpoint_work + damping_loss
    values = (final_energy, midpoint_work, map_work, damping_loss, balance,
              map_work - midpoint_work, time, position, velocity)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Final motion accounting exceeds numerical range.")
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
                                       allow_nan=False).encode()).hexdigest()
    return {"contract": RESULT_CONTRACT, "request_sha256": digest, "status": "completed",
            "production_qualified": False, "termination": termination, "boundary": boundary,
            "time_s": times, "position_m": positions, "velocity_m_per_s": velocities,
            "midpoint_actuator_work_j": midpoint_work, "force_map_work_j": map_work,
            "force_quadrature_error_j": map_work - midpoint_work,
            "damping_dissipation_j": damping_loss,
            "initial_mechanical_energy_j": initial_energy, "final_mechanical_energy_j": final_energy,
            "energy_balance_residual_j": balance, "force_map_review": force_review,
            "limitations": ["Quasi-static supplied force map at one fixed excitation; no current or voltage dynamics.",
                            "One translational degree of freedom with linear viscous damping and linear spring only.",
                            "A stroke boundary terminates motion; force is never extrapolated and impact/contact is not modeled.",
                            "Passing numerical checks is not field, hardware, lifetime, safety, or production validation."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    with args.request.open("rb") as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        parser.error("Request exceeds 8 MiB.")
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"Duplicate key: {key}")
            value[key] = item
        return value
    result = simulate_actuator_motion(json.loads(raw, object_pairs_hook=pairs))
    args.result.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
