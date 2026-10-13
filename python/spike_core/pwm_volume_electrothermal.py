"""Conservative PWM/retained-solid window coupling, without embedded thermal RCs.

SPDX-License-Identifier: Apache-2.0
Copyright 2026 Yawar B (wayri) and SPIKE contributors.

Independently authored partitioned midpoint-temperature coupling. Native MNA
owns electrical history; retained P1 volumes own all thermal capacity.
"""
from __future__ import annotations

import copy
import hashlib
import math
from typing import Any, Callable

import numpy as np

from .pwm_electrothermal import _digest, _request
from .retained_thermal_step import prepare_retained_thermal_step

REQUEST = "spike/pwm-volume-electrothermal-request/v1"
RESULT = "spike/pwm-volume-electrothermal-result/v1"
DEVICES = ("Rw", "SH", "SL", "Load")
RC_PARAMETERS = {"thermal_resistance_k_per_w", "thermal_capacitance_j_per_k"}
COUPLING_DEFAULTS = {"cycles_per_window": 1, "maximum_iterations": 20,
                     "temperature_tolerance_k": 1e-6,
                     "relative_energy_tolerance": 1e-6, "relaxation": 1.0}


def _admit(raw):
    if not isinstance(raw, dict) or set(raw) != {"contract", "parameters", "thermal", "coupling"} or raw.get("contract") != REQUEST:
        raise ValueError("PWM_VOLUME_REQUEST: invalid contract or fields")
    params = raw["parameters"]
    if not isinstance(params, dict) or set(params) & RC_PARAMETERS:
        raise ValueError("PWM_VOLUME_REQUEST: embedded thermal RC parameters forbidden")
    p = _request({"contract": "spike/pwm-electrothermal-request/v1", "parameters": params})
    for key in RC_PARAMETERS:
        del p[key]
    thermal = raw["thermal"]
    if not isinstance(thermal, dict) or set(thermal) != {"request", "material_heat_capacity", "initial_temperature_k", "device_cell_fractions"}:
        raise ValueError("PWM_VOLUME_REQUEST: explicit retained thermal setup required")
    if not isinstance(thermal["device_cell_fractions"], dict) or set(thermal["device_cell_fractions"]) != set(DEVICES):
        raise ValueError("PWM_VOLUME_MAPPING: every dissipative device must be mapped exactly once")
    setup = raw["coupling"]
    if not isinstance(setup, dict) or set(setup) - COUPLING_DEFAULTS.keys():
        raise ValueError("PWM_VOLUME_REQUEST: invalid coupling controls")
    controls = dict(COUPLING_DEFAULTS)
    controls.update(setup)
    for key, value in controls.items():
        try:
            valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("PWM_VOLUME_REQUEST: finite numeric controls required")
        if key in ("cycles_per_window", "maximum_iterations") and (int(value) != value or not 1 <= value <= 100):
            raise ValueError("PWM_VOLUME_RESOURCE: integer coupling controls outside 1..100")
    if not 2 <= controls["maximum_iterations"] <= 100:
        raise ValueError("PWM_VOLUME_REQUEST: at least two coupling iterations required")
    if not 1e-10 <= controls["temperature_tolerance_k"] <= .1 or not 1e-10 <= controls["relative_energy_tolerance"] <= .01 or not .05 <= controls["relaxation"] <= 1:
        raise ValueError("PWM_VOLUME_REQUEST: coupling tolerance or relaxation out of bounds")
    for key in ("cycles_per_window", "maximum_iterations"):
        controls[key] = int(controls[key])
    work = p["cycles"] * (math.ceil(1 / p["switching_frequency_hz"] / p["maximum_step_s"]) + 2) * controls["maximum_iterations"]
    if work > 2000000:
        raise ValueError("PWM_VOLUME_RESOURCE: replay electrical work exceeds two million steps")
    if len(str(raw).encode("utf-8")) > 8 * 1024 * 1024:
        raise ValueError("PWM_VOLUME_RESOURCE: request exceeds 8 MiB")
    return p, controls, thermal


def _prepare(raw, cancel_check=None):
    p, controls, setup = _admit(raw)
    prepared = prepare_retained_thermal_step(setup["request"], setup["material_heat_capacity"],
        setup["device_cell_fractions"], cancel_check=cancel_check)
    initial = setup["initial_temperature_k"]
    if isinstance(initial, bool):
        raise ValueError("PWM_VOLUME_TEMPERATURE: invalid initial temperature")
    if isinstance(initial, (int, float)):
        initial = [initial] * len(setup["request"]["mesh"]["vertices"])
    initial = np.asarray(prepared.validate_temperature(initial), dtype=float)
    frames = math.ceil(p["cycles"] / controls["cycles_per_window"]) + 1
    if frames * initial.size > 200000:
        raise ValueError("PWM_VOLUME_RESOURCE: retained frame budget exceeded")
    return p, controls, prepared, initial


def validate_pwm_volume_electrothermal(raw):
    p, controls, _, initial = _prepare(raw)
    return {"contract": "spike/pwm-volume-electrothermal-admission/v1", "status": "accepted",
            "model_status": "experimental", "parameters": p, "coupling": controls,
            "nodes": int(initial.size), "request_sha256": _digest(raw)}


def _circuit(library, p):
    circuit = library.circuit()
    try:
        for name, node, value in (("Vin", "vin", p["input_voltage_v"]), ("GH", "gh", 0.),
                                  ("GL", "gl", 0.), ("Tw", "tw", p["ambient_temperature_k"])):
            circuit.add_voltage_source(name, node, "0", value)
        for name, a, b, gate in (("SH", "vin", "sw", "gh"), ("SL", "sw", "0", "gl")):
            circuit.add_voltage_controlled_switch(name, a, b, gate, "0",
                on_resistance_ohm=p["switch_on_resistance_ohm"], off_resistance_ohm=p["switch_off_resistance_ohm"],
                threshold_voltage_v=.5, transition_voltage_v=.01)
        circuit.add_inductor("L", "sw", "w", p["inductance_h"])
        # Fixed, generated AST only; request cannot inject an expression or code.
        expression = f"(V(w)-V(out))/({p['winding_resistance_ohm']:.17g}*(1+{p['temperature_coefficient_per_k']:.17g}*(V(tw)-{p['ambient_temperature_k']:.17g})))"
        circuit.add_behavioral_source("Rw", "w", "out", expression, voltage_output=False)
        circuit.add_capacitor("C", "out", "0", p["capacitance_f"])
        circuit.add_resistor("Load", "out", "0", p["load_resistance_ohm"])
        return circuit
    except BaseException:
        circuit.close()
        raise


def _electrical_window(session, p, cycles, state, winding_temperature, cancel):
    integral, voltage, current = state
    period = 1 / p["switching_frequency_hz"]
    resistance = p["winding_resistance_ohm"] * (1 + p["temperature_coefficient_per_k"] * (winding_temperature - p["ambient_temperature_k"]))
    if not 0 < resistance < 1e6 or not 1 <= winding_temperature <= 450:
        raise ValueError("PWM_VOLUME_TEMPERATURE: winding feedback outside supported range")
    session.set_source_value("Tw", winding_temperature)
    energies = dict.fromkeys(DEVICES, 0.)
    source_j = numerical_j = max_balance = 0.
    records = []
    for _ in range(cycles):
        error = p["target_voltage_v"] - voltage
        duty = min(.95, max(.05, p["target_voltage_v"] / p["input_voltage_v"] + p["controller_kp_per_v"] * error + p["controller_ki_per_v_s"] * integral))
        integral += period * error
        for on, duration in ((True, duty * period), (False, (1 - duty) * period)):
            session.set_source_value("GH", float(on))
            session.set_source_value("GL", float(not on))
            steps = math.ceil(duration / p["maximum_step_s"])
            dt = duration / steps
            for _ in range(steps):
                cancel()
                if not session.step(dt):
                    raise ValueError(f"PWM_VOLUME_ELECTRICAL_CONVERGENCE: {session.message}")
                v, i = session.node_voltage("out"), session.element_current("L")
                powers = {name: session.element_power(name) for name in DEVICES}
                source = -sum(session.element_power(name) for name in ("Vin", "GH", "GL", "Tw"))
                stored = .5 * p["inductance_h"] * (i*i-current*current) + .5 * p["capacitance_f"] * (v*v-voltage*voltage)
                numerical = .5 * p["inductance_h"] * (i-current)**2 + .5 * p["capacitance_f"] * (v-voltage)**2
                imbalance = dt * (source-sum(powers.values())) - stored - numerical
                if not all(math.isfinite(x) for x in (v, i, source, imbalance, *powers.values())) or any(x < 0 for x in powers.values()):
                    raise ValueError("PWM_VOLUME_ENERGY: invalid passive-device power")
                if abs(imbalance) > 1e-10 + 1e-8 * max(abs(dt*source), abs(stored), numerical, 1e-12):
                    raise ValueError("PWM_VOLUME_ENERGY: electrical step balance failed")
                for name in DEVICES:
                    energies[name] += dt * powers[name]
                source_j += source * dt
                numerical_j += numerical
                max_balance = max(max_balance, abs(imbalance))
                voltage, current = v, i
        records.append({"time_s": session.time_s, "duty": duty, "output_voltage_v": voltage, "inductor_current_a": current})
    return (integral, voltage, current), energies, source_j, numerical_j, records, max_balance


def run_pwm_volume_electrothermal(raw: Any, *, library=None, cancel_check: Callable[[], bool] | None = None,
                                progress: Callable[[dict], None] | None = None):
    """Advance only committed windows; replay every iterate from a native snapshot.

    Winding R(T) uses the average of start/end mapped temperature; losses of all
    four passive devices become constant energy-equivalent power per window.
    Temporal accuracy therefore needs independent electrical/window refinement.
    """
    def cancel():
        if cancel_check and cancel_check():
            raise ValueError("PWM_VOLUME_CANCELLED: operation cancelled")
    cancel()
    p, controls, prepared, temperature = _prepare(raw, cancel_check)
    if library is None:
        from .spikes_runtime import _engine
        library = _engine()
    state = (0., 0., 0.)
    completed = 0
    windows = []
    frames = [{"time_s": 0., "node_temperatures_k": temperature.tolist()}]
    total = {"source_j": 0., "be_numerical_dissipation_j": 0., **{name: 0. for name in DEVICES}}
    thermal_total = {}
    interrupted = False
    max_balance = 0.
    with _circuit(library, p) as circuit, circuit.transient_session(initialize_from_operating_point=False,
            integration_method="backward_euler", absolute_tolerance=1e-12, relative_tolerance=1e-10) as session:
        while completed < p["cycles"]:
            cycles = min(controls["cycles_per_window"], p["cycles"]-completed)
            dt = cycles / p["switching_frequency_hz"]
            old = temperature.copy()
            guess = old.copy()
            previous_energy = None
            with session.checkpoint() as checkpoint:
                try:
                    for iteration in range(1, controls["maximum_iterations"]+1):
                        cancel()
                        session.restore(checkpoint)
                        feedback = prepared.device_temperatures_k((old+guess)/2)["Rw"]
                        candidate = _electrical_window(session, p, cycles, state, feedback, cancel)
                        new_state, energy, source_j, numerical, records, balance = candidate
                        thermal = prepared.advance(old, dt, energy, cancel_check=cancel_check)
                        endpoint = np.asarray(thermal["node_temperatures_k"])
                        defect = float(np.max(np.abs(endpoint-guess)))
                        energy_defect = math.inf if previous_energy is None else max(abs(energy[name]-previous_energy[name])/max(abs(energy[name]), abs(previous_energy[name]), 1e-12) for name in DEVICES)
                        if previous_energy is not None and defect <= controls["temperature_tolerance_k"] and energy_defect <= controls["relative_energy_tolerance"]:
                            cancel()
                            break
                        guess += controls["relaxation"] * (endpoint-guess)
                        previous_energy = energy
                    else:
                        session.restore(checkpoint)
                        raise ValueError("PWM_VOLUME_COUPLING_CONVERGENCE: unrelaxed temperature/energy defects exceed tolerance")
                except BaseException as exc:
                    session.restore(checkpoint)
                    if isinstance(exc, ValueError) and "CANCELLED" in str(exc):
                        interrupted = True
                        break
                    raise
            # All ledgers and states cross the commit point together.
            state, temperature = new_state, endpoint
            completed += cycles
            total["source_j"] += source_j
            total["be_numerical_dissipation_j"] += numerical
            for name in DEVICES:
                total[name] += energy[name]
            for key, value in thermal["energy_balance"].items():
                thermal_total[key] = thermal_total.get(key, 0.) + value
            max_balance = max(max_balance, balance)
            windows.append({"completed_cycles": completed, "time_s": session.time_s, "electrical_cycles": records,
                            "device_energies_j": energy, "device_temperatures_k": thermal["device_temperatures_k"],
                            "feedback_winding_temperature_k": feedback, "iterations": iteration,
                            "temperature_defect_k": defect, "relative_energy_defect": energy_defect,
                            "thermal_energy_balance": thermal["energy_balance"]})
            frames.append({"time_s": session.time_s, "node_temperatures_k": temperature.tolist()})
            if progress:
                progress(copy.deepcopy({"completed_cycles": completed, "total_cycles": p["cycles"]}))
        diagnostics = session.diagnostics()
    total["electrical_stored_j"] = .5*p["inductance_h"]*state[2]**2 + .5*p["capacitance_f"]*state[1]**2
    total["electrical_balance_j"] = total["source_j"]-sum(total[name] for name in DEVICES)-total["electrical_stored_j"]-total["be_numerical_dissipation_j"]
    if abs(total["electrical_balance_j"]) > 1e-9+1e-8*max(abs(total["source_j"]), 1e-12):
        raise ValueError("PWM_VOLUME_ENERGY: cumulative electrical ledger failed")
    total["combined_balance_j"] = total["source_j"]-total["electrical_stored_j"]-total["be_numerical_dissipation_j"]-sum(
        thermal_total.get(key, 0.) for key in ("stored_energy_change_j", "convection_outward_j", "radiation_outward_j")) + sum(
        thermal_total.get(key, 0.) for key in ("prescribed_flux_inward_j", "temperature_reaction_inward_j"))
    if abs(total["combined_balance_j"]) > thermal_total.get("acceptance_tolerance_j", 0.) + 1e-9 + 1e-8*max(abs(total["source_j"]), 1e-12):
        raise ValueError("PWM_VOLUME_ENERGY: cumulative combined energy ledger failed")
    return {"contract": RESULT, "status": "cancelled" if interrupted else "completed", "model_status": "experimental",
            "completed_cycles": completed, "parameters": p, "coupling": controls, "windows": windows,
            "frames": frames, "energy": total, "thermal_energy_balance": thermal_total,
            "maximum_step_electrical_balance_j": max_balance, "request_sha256": _digest(raw),
            "committed_state_sha256": _digest({"cycles": completed, "electrical": state, "temperature": temperature.tolist(), "energy": total}),
            "runtime": {"engine": "native_spikes_persistent_mna", "library_sha256": hashlib.sha256(library.path.read_bytes()).hexdigest(), "diagnostics": diagnostics},
            "limits": ["retained constant-property P1 solids; no airflow", "only winding R(T) feeds back; ideal finite-conductance switches and resistive load",
                       "cycle sampled PI and ideal complementary gates; no deadtime/gate charge", "window-averaged per-device losses; require time/window/mesh refinement",
                       "no portable native checkpoint or arbitrary semiconductor qualification", "knowledgeable numerical human review required before release"]}
