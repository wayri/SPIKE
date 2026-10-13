"""Native switching-level synchronous buck with winding electrothermal feedback.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Yawar B (wayri) and SPIKE contributors.

This adapter orchestrates the existing SPikes MNA kernel; it is not another
circuit solver. Gate commands are ideal, switches have finite conductance,
and only winding Joule heat enters the lumped thermal state.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable

REQUEST = "spike/pwm-electrothermal-request/v1"
RESULT = "spike/pwm-electrothermal-result/v1"
DEFAULTS = {
    "input_voltage_v": 12.0, "target_voltage_v": 5.0,
    "inductance_h": 1e-4, "capacitance_f": 1e-4,
    "load_resistance_ohm": 5.0, "winding_resistance_ohm": 0.2,
    "temperature_coefficient_per_k": 0.02, "ambient_temperature_k": 300.0,
    "thermal_resistance_k_per_w": 10.0, "thermal_capacitance_j_per_k": 0.01,
    "switch_on_resistance_ohm": 0.02, "switch_off_resistance_ohm": 1e6,
    "switching_frequency_hz": 20000.0, "maximum_step_s": 1e-6,
    "cycles": 400, "controller_kp_per_v": 0.04,
    "controller_ki_per_v_s": 10.0,
}


def _request(raw: Any) -> dict[str, float | int]:
    if not isinstance(raw, dict) or set(raw) - {"contract", "parameters", "restart"}:
        raise ValueError("PWM_REQUEST: unknown fields or invalid object")
    if raw.get("contract") != REQUEST or not isinstance(raw.get("parameters"), dict):
        raise ValueError("PWM_REQUEST: contract and parameters required")
    params = raw["parameters"]
    if set(params) - DEFAULTS.keys():
        raise ValueError("PWM_REQUEST: unknown parameter")
    config = dict(DEFAULTS)
    for key, value in params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"PWM_REQUEST: {key} must be numeric")
        try:
            value = float(value)
        except (OverflowError, ValueError) as exc:
            raise ValueError(f"PWM_REQUEST: {key} not representable") from exc
        if not math.isfinite(value):
            raise ValueError(f"PWM_REQUEST: {key} must be finite")
        config[key] = value
    ranges = {
        "input_voltage_v": (1, 100), "target_voltage_v": (0.1, 99),
        "inductance_h": (1e-6, 0.1), "capacitance_f": (1e-7, 0.1),
        "load_resistance_ohm": (0.1, 1000), "winding_resistance_ohm": (1e-4, 10),
        "temperature_coefficient_per_k": (0, 0.1),
        "ambient_temperature_k": (250, 350),
        "thermal_resistance_k_per_w": (0.01, 1000),
        "thermal_capacitance_j_per_k": (1e-5, 100),
        "switch_on_resistance_ohm": (1e-3, 10),
        "switch_off_resistance_ohm": (1e3, 1e8),
        "switching_frequency_hz": (100, 1e6), "maximum_step_s": (1e-9, 1e-3),
        "cycles": (1, 2000), "controller_kp_per_v": (0, 10),
        "controller_ki_per_v_s": (0, 1e5),
    }
    for key, (low, high) in ranges.items():
        if not low <= config[key] <= high:
            raise ValueError(f"PWM_RANGE: {key} outside supported bounds")
    if config["cycles"] != int(config["cycles"]):
        raise ValueError("PWM_REQUEST: cycles must be an integer")
    config["cycles"] = int(config["cycles"])
    if config["target_voltage_v"] >= config["input_voltage_v"]:
        raise ValueError("PWM_RANGE: buck target must be below input")
    period = 1 / config["switching_frequency_hz"]
    if config["maximum_step_s"] > period / 4:
        raise ValueError("PWM_RANGE: maximum step must be at most period/4")
    if config["cycles"] * (math.ceil(period / config["maximum_step_s"]) + 2) > 200000:
        raise ValueError("PWM_RESOURCE: electrical step budget exceeded")
    if "restart" in raw:
        token = raw["restart"]
        if not isinstance(token, dict) or set(token) != {"contract", "completed_cycles", "configuration_sha256", "library_sha256", "state_sha256"}:
            raise ValueError("PWM_CHECKPOINT: malformed restart token")
        if token["contract"] != "spike/pwm-electrothermal-checkpoint/v1":
            raise ValueError("PWM_CHECKPOINT: unsupported checkpoint")
        n = token["completed_cycles"]
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= config["cycles"]:
            raise ValueError("PWM_CHECKPOINT: invalid completed cycle count")
        for key in ("configuration_sha256", "library_sha256", "state_sha256"):
            digest = token[key]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("PWM_CHECKPOINT: invalid digest")
    return config


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_pwm_electrothermal(raw: Any) -> dict:
    """Strict preflight, without loading a native library or allocating a solve."""
    p = _request(raw)
    return {"contract": "spike/pwm-electrothermal-admission/v1", "status": "accepted",
            "parameters": p, "configuration_sha256": _digest(p),
            "maximum_electrical_steps": p["cycles"]*(math.ceil(1/p["switching_frequency_hz"]/p["maximum_step_s"])+2),
            "model_status": "experimental"}


def _circuit(library: Any, p: dict) -> Any:
    c = library.circuit()
    try:
        c.add_voltage_source("Vin", "vin", "0", p["input_voltage_v"])
        c.add_voltage_source("GH", "gh", "0", 0.0)
        c.add_voltage_source("GL", "gl", "0", 0.0)
        for name, a, b, gate in (("SH", "vin", "sw", "gh"), ("SL", "sw", "0", "gl")):
            c.add_voltage_controlled_switch(
                name, a, b, gate, "0",
                on_resistance_ohm=p["switch_on_resistance_ohm"],
                off_resistance_ohm=p["switch_off_resistance_ohm"],
                threshold_voltage_v=0.5, transition_voltage_v=0.01)
        c.add_inductor("L", "sw", "w", p["inductance_h"])
        c.add_electrothermal_resistor(
            "Rw", "w", "out", "tj", resistance_ohm=p["winding_resistance_ohm"],
            temperature_coefficient_per_k=p["temperature_coefficient_per_k"],
            ambient_temperature_k=p["ambient_temperature_k"],
            thermal_resistance_k_per_w=p["thermal_resistance_k_per_w"],
            thermal_capacitance_j_per_k=p["thermal_capacitance_j_per_k"],
            minimum_temperature_k=p["ambient_temperature_k"]-1.0, maximum_temperature_k=450.0)
        c.add_capacitor("C", "out", "0", p["capacitance_f"])
        c.add_resistor("Load", "out", "0", p["load_resistance_ohm"])
        return c
    except BaseException:
        c.close()
        raise


def run_pwm_electrothermal(raw: Any, *, cancel_check: Callable[[], bool] | None = None,
                          progress: Callable[[dict], None] | None = None,
                          library: Any = None) -> dict:
    """Run in an owned worker. Never accept executable/DLL paths in requests.

    ``library`` is an in-process trusted dependency injection, not JSON input.
    Native electrical and thermal states persist throughout all PWM cycles.
    Each returned window is one full PWM cycle, not an averaged solve.
    """
    p = _request(raw)
    def cancelled() -> None:
        if cancel_check and cancel_check():
            raise ValueError("PWM_CANCELLED: operation cancelled")
    cancelled()
    if library is None:
        from .spikes_runtime import _engine
        try:
            library = _engine()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(f"PWM_NATIVE_UNAVAILABLE: {exc}") from exc
    library_hash = hashlib.sha256(library.path.read_bytes()).hexdigest()
    config_hash = _digest(p)
    restart = raw.get("restart")
    if restart and (restart["configuration_sha256"] != config_hash or restart["library_sha256"] != library_hash):
        raise ValueError("PWM_CHECKPOINT: configuration or library identity mismatch")
    period = 1 / p["switching_frequency_hz"]
    total = dict.fromkeys(("source_j", "switch_j", "load_j", "winding_j",
                          "ambient_j", "be_numerical_dissipation_j"), 0.0)
    windows = []
    integral = voltage = current = theta = 0.0
    max_electrical = max_thermal = max_power = 0.0
    interrupted = False
    replay_verified = restart is None
    def checkpoint(n: int) -> dict:
        # Portable restart reconstructs native history by deterministic replay;
        # never installs arbitrary serialized native handles or user state.
        state_hash = _digest({"completed_cycles": n, "voltage_v": voltage,
                              "current_a": current, "rise_k": theta,
                              "controller_integral_v_s": integral, "energy": total})
        return {"contract": "spike/pwm-electrothermal-checkpoint/v1",
                "completed_cycles": n, "configuration_sha256": config_hash,
                "library_sha256": library_hash, "state_sha256": state_hash}
    committed = checkpoint(0)
    if restart and restart["completed_cycles"] == 0:
        if restart != committed:
            raise ValueError("PWM_CHECKPOINT: initial state identity mismatch")
        replay_verified = True
    with _circuit(library, p) as circuit, circuit.transient_session(
            initialize_from_operating_point=False, integration_method="backward_euler",
            absolute_tolerance=1e-12, relative_tolerance=1e-10) as session:
        for cycle in range(p["cycles"]):
            if cancel_check and cancel_check():
                interrupted = True
                break
            saved = (integral, voltage, current, theta, dict(total),
                     max_electrical, max_thermal, max_power)
            cycle_start = session.time_s
            off_edge = cycle_start
            minimum_v = maximum_v = voltage
            minimum_i = maximum_i = current
            error = p["target_voltage_v"] - voltage
            duty = min(0.95, max(0.05, p["target_voltage_v"] / p["input_voltage_v"]
                               + p["controller_kp_per_v"] * error
                               + p["controller_ki_per_v_s"] * integral))
            integral += period * error
            before = dict(total)
            for on, duration in ((True, duty * period), (False, (1-duty) * period)):
                session.set_source_value("GH", float(on))
                session.set_source_value("GL", float(not on))
                steps = math.ceil(duration / p["maximum_step_s"])
                dt = duration / steps
                for _ in range(steps):
                    if cancel_check and cancel_check():
                        interrupted = True
                        break
                    if not session.step(dt):
                        raise ValueError(f"PWM_CONVERGENCE: {session.message}")
                    v = session.node_voltage("out")
                    i = session.element_current("L")
                    th = session.node_voltage("tj")
                    source = -sum(session.element_power(n) for n in ("Vin", "GH", "GL"))
                    switch = sum(session.element_power(n) for n in ("SH", "SL"))
                    load = session.element_power("Load")
                    winding = session.element_power("Rw")
                    ambient = th / p["thermal_resistance_k_per_w"]
                    numerical = 0.5*p["inductance_h"]*(i-current)**2 + 0.5*p["capacitance_f"]*(v-voltage)**2
                    stored = 0.5*p["inductance_h"]*(i*i-current*current) + 0.5*p["capacitance_f"]*(v*v-voltage*voltage)
                    electrical = dt*(source-switch-load-winding)-stored-numerical
                    thermal = dt*(winding-ambient)-p["thermal_capacitance_j_per_k"]*(th-theta)
                    power = source - sum(session.element_power(n) for n in ("SH", "SL", "Load", "Rw", "L", "C"))
                    values = (v, i, th, source, switch, load, winding, ambient, electrical, thermal, power)
                    if not all(math.isfinite(x) for x in values):
                        raise ValueError("PWM_NONFINITE: native output")
                    if th < -1e-8:
                        raise ValueError("PWM_THERMAL: self-heating state below ambient")
                    # Verify both local ledgers, not just cancellation-prone cumulative sums.
                    energy_scale = max(abs(dt*source), abs(stored), abs(numerical), 1e-12)
                    thermal_scale = max(abs(dt*winding), abs(p["thermal_capacitance_j_per_k"]*(th-theta)), 1e-12)
                    if abs(electrical) > 1e-10 + 1e-8*energy_scale or abs(thermal) > 1e-10 + 1e-8*thermal_scale:
                        raise ValueError("PWM_ENERGY: step ledger failed")
                    if abs(power) > 1e-9 + 1e-8*max(abs(source), abs(switch)+abs(load)+abs(winding)):
                        raise ValueError("PWM_ENERGY: element power balance failed")
                    max_electrical = max(max_electrical, abs(electrical))
                    max_thermal = max(max_thermal, abs(thermal))
                    max_power = max(max_power, abs(power))
                    for key, value in (("source_j", source*dt), ("switch_j", switch*dt),
                                       ("load_j", load*dt), ("winding_j", winding*dt),
                                       ("ambient_j", ambient*dt), ("be_numerical_dissipation_j", numerical)):
                        total[key] += value
                    voltage, current, theta = v, i, th
                    minimum_v, maximum_v = min(minimum_v, v), max(maximum_v, v)
                    minimum_i, maximum_i = min(minimum_i, i), max(maximum_i, i)
                if interrupted:
                    break
                if on:
                    off_edge = session.time_s
            if interrupted:
                (integral, voltage, current, theta, total,
                 max_electrical, max_thermal, max_power) = saved
                break
            windows.append({"cycle": cycle+1, "time_s": session.time_s, "duty": duty,
                            "output_voltage_v": voltage, "inductor_current_a": current,
                            "winding_temperature_k": p["ambient_temperature_k"]+theta,
                            "on_start_s": cycle_start, "off_start_s": off_edge,
                            "minimum_output_voltage_v": minimum_v, "maximum_output_voltage_v": maximum_v,
                            "minimum_inductor_current_a": minimum_i, "maximum_inductor_current_a": maximum_i,
                            "energy": {k: total[k]-before[k] for k in total}})
            committed = checkpoint(cycle+1)
            if restart and cycle+1 == restart["completed_cycles"]:
                if restart != committed:
                    raise ValueError("PWM_CHECKPOINT: deterministic replay state mismatch")
                replay_verified = True
            if progress:
                progress({"completed_cycles": cycle+1, "total_cycles": p["cycles"]})
        diagnostics = session.diagnostics()
    if cancel_check and cancel_check():
        interrupted = True
    if not interrupted and not replay_verified:
        raise ValueError("PWM_CHECKPOINT: checkpoint replay was not verified")
    total["electrical_stored_j"] = 0.5*p["inductance_h"]*current**2 + 0.5*p["capacitance_f"]*voltage**2
    total["thermal_stored_j"] = p["thermal_capacitance_j_per_k"]*theta
    total["electrical_balance_j"] = total["source_j"]-sum(total[k] for k in ("switch_j", "load_j", "winding_j", "electrical_stored_j", "be_numerical_dissipation_j"))
    total["thermal_balance_j"] = total["winding_j"]-total["ambient_j"]-total["thermal_stored_j"]
    if abs(total["electrical_balance_j"]) > 1e-9+1e-8*max(abs(total["source_j"]), 1e-12) or abs(total["thermal_balance_j"]) > 1e-9+1e-8*max(abs(total["winding_j"]), 1e-12):
        raise ValueError("PWM_ENERGY: cumulative ledger failed")
    return {"contract": RESULT, "status": "cancelled" if interrupted else "completed", "model_status": "experimental",
            "checkpoint": committed, "restart": {"method": "deterministic_replay",
                "verified": replay_verified, "no_replay_speedup_claim": True},
            "issue_codes": ["PWM_CANCELLED"] if interrupted else [],
            "parameters": p, "windows": windows, "energy": total,
            "request_sha256": _digest(raw), "configuration_sha256": config_hash,
            "runtime": {"engine": "native_spikes_persistent_mna", "integration": "backward_euler",
                        "diagnostics": diagnostics, "library_sha256": library_hash},
            "quality": {"maximum_step_electrical_balance_j": max_electrical,
                        "maximum_step_thermal_balance_j": max_thermal,
                        "maximum_element_power_balance_w": max_power},
            "limits": ["ideal complementary gates; no deadtime or gate charge",
                       "finite-conductance behavioral switches, not vendor transistor models",
                       "winding-only lumped thermal feedback; switch/load heat is external",
                       "no spatial thermal, EMI, measured correlation or release qualification",
                       "sampled PI without anti-windup; arbitrary controller stability not guaranteed"]}
