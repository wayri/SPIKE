# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded implicit, current-driven diode/solid-field verification increment.

Reuses SPIKE's diode reference law, not the general SPICE engine. Every drive
sample is the prescribed current over one backward-Euler time interval. There
is no junction charge, reverse breakdown, transistor or switching-loss model.
"""
from copy import deepcopy
from dataclasses import replace
import math
from typing import Mapping
import numpy as np

from python.spike_core.electrothermal_sharing import DiodeParameters, _voltage_for_current
from python.spike_core.structured_solid_thermal import (
    StructuredThermalError, _number, _positive_int, _strict_keys,
    _parse_request, _solve_step, _energy,
)

CONTRACT = "spike/transient-diode-field/v1"
RESULT_CONTRACT = "spike/transient-diode-field-result/v1"


def _prepare(request):
    if not isinstance(request, Mapping) or request.get("contract") != CONTRACT:
        raise StructuredThermalError(f"Expected {CONTRACT}.")
    _strict_keys(request, {"contract", "thermal", "devices", "iteration"}, "coupling")
    model = _parse_request(deepcopy(request.get("thermal")))
    if model.mode != "transient" or model.cell_count > 512 or model.steps > 1000:
        raise StructuredThermalError("Requires transient thermal study, <=512 cells and <=1000 steps.")
    if not math.isfinite(model.time_step * model.steps):
        raise StructuredThermalError("Total transient duration must be finite.")
    if not 1 <= model.initial_temperature <= 2000:
        raise StructuredThermalError("Initial device temperature must be within 1..2000 K.")
    raw = request.get("devices")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
        raise StructuredThermalError("Requires 1..32 explicitly bound diode devices.")
    devices, seen = [], set()
    keys = {"id", "model", "cells", "weights", "current_a"}
    model_keys = {"saturation_current_a", "ideality_factor", "series_resistance_ohm",
                  "reference_temperature_k", "bandgap_ev", "saturation_temperature_exponent"}
    for device in raw:
        if not isinstance(device, Mapping):
            raise StructuredThermalError("Device must be an object.")
        _strict_keys(device, keys, "device")
        name = device.get("id")
        if not isinstance(name, str) or not 1 <= len(name) <= 128 or name in seen:
            raise StructuredThermalError("Device IDs must be unique nonempty bounded strings.")
        seen.add(name)
        parameters = device.get("model")
        if not isinstance(parameters, Mapping) or set(parameters) != model_keys:
            raise StructuredThermalError("Each diode requires the exact explicit reference-model parameters.")
        values = {key: _number(value, key, minimum=0) for key, value in parameters.items()}
        if not (1e-300 <= values["saturation_current_a"] <= 1e3 and .5 <= values["ideality_factor"] <= 10
                and 1 <= values["reference_temperature_k"] <= 2000 and values["bandgap_ev"] <= 10
                and values["saturation_temperature_exponent"] <= 10):
            raise StructuredThermalError("Diode parameters exceed the reference admission envelope.")
        cells, weights = device.get("cells"), device.get("weights")
        if (not isinstance(cells, list) or not 1 <= len(cells) <= model.cell_count
                or any(type(c) is not int or not 0 <= c < model.cell_count for c in cells)
                or len(set(cells)) != len(cells)):
            raise StructuredThermalError("Binding cells must be unique admitted cell indices.")
        if not isinstance(weights, list) or len(weights) != len(cells):
            raise StructuredThermalError("One weight per bound cell is required.")
        weights = np.array([_number(w, "weight", minimum=0) for w in weights])
        if abs(math.fsum(weights)-1) > 1e-12:
            raise StructuredThermalError("Weights must sum to one; normalization is not inferred.")
        currents = device.get("current_a")
        if not isinstance(currents, list) or len(currents) != model.steps:
            raise StructuredThermalError("Exactly one prescribed current per time interval is required.")
        currents = [_number(i, "current_a", minimum=0) for i in currents]
        if max(currents) > 1e6:
            raise StructuredThermalError("Current exceeds the reference admission limit.")
        devices.append((DiodeParameters(name=name, **values), np.array(cells), weights, currents))
    options = request.get("iteration", {})
    if not isinstance(options, Mapping):
        raise StructuredThermalError("iteration must be an object.")
    _strict_keys(options, {"max_iterations", "relaxation"}, "iteration")
    maximum = _positive_int(options.get("max_iterations", 100), "max_iterations", maximum=200)
    relaxation = _number(options.get("relaxation", .5), "relaxation", minimum=1e-6)
    if relaxation > 1 or model.cell_count * model.steps * maximum > 2_000_000:
        raise StructuredThermalError("Coupled work budget exceeded or relaxation >1.")
    return model, devices, maximum, relaxation


def _losses(devices, field, step, volume):
    heat = np.zeros(len(field))
    records = []
    for parameters, cells, weights, currents in devices:
        temperature = float(np.dot(weights, field[cells]))
        if not 1 <= temperature <= 2000:
            raise StructuredThermalError("Device temperature left the 1..2000 K admission envelope.")
        # Reject the reference law's overflow-clipping region instead of silently
        # accepting a clipped physical model as a converged device evaluation.
        exponent = parameters.bandgap_ev / 8.617333262145e-5 * (
            1/parameters.reference_temperature_k - 1/temperature)
        log_is = (math.log(parameters.saturation_current_a)
                  + parameters.saturation_temperature_exponent * math.log(temperature/parameters.reference_temperature_k)
                  + exponent)
        if abs(exponent) > 600 or not -690 < log_is < 690:
            raise StructuredThermalError("Diode saturation law exceeds its safe exponential range.")
        current = currents[step]
        voltage = _voltage_for_current(parameters, temperature, current)
        power = current * voltage
        if not math.isfinite(power) or power < 0:
            raise StructuredThermalError("Device evaluated non-finite or negative dissipated power.")
        heat[cells] += weights * power / volume
        records.append({"id": parameters.name, "temperature_k": temperature, "current_a": current,
                        "voltage_v": voltage, "power_w": power})
    total = math.fsum(r["power_w"] for r in records)
    mismatch = abs(float(np.sum(heat)*volume)-total)
    if mismatch > 1e-12*max(total, 1e-30):
        raise StructuredThermalError("Device-to-cell mapping failed conservation.")
    return heat, records, total, mismatch


def solve_transient_diode_field(request, *, cancel_check=None):
    """Publish complete results only after all implicit steps pass acceptance."""
    try:
        model, devices, maximum, relaxation = _prepare(request)
        current = np.full(model.cell_count, model.initial_temperature)
        frames, history = [], []
        totals = {key: 0. for key in ("device_heat_j", "background_heat_j", "boundary_heat_j", "stored_energy_j")}
        for step in range(model.steps):
            prior, guess = current.copy(), current.copy()
            for iteration in range(maximum):
                if cancel_check is not None and cancel_check():
                    raise StructuredThermalError("Coupled solve cancelled.")
                heat, records, power, _ = _losses(devices, guess, step, model.volume)
                working = replace(model, heat=model.heat+heat)
                target, _, _, _ = _solve_step(working, prior, guess, cancel_check)
                final_heat, final_records, final_power, mapping = _losses(devices, target, step, model.volume)
                temperature_defect = float(np.max(abs(target-guess)))
                power_defect = math.fsum(abs(a["power_w"]-b["power_w"]) for a,b in zip(records, final_records))
                final_model = replace(model, heat=model.heat+final_heat)
                energy = _energy(final_model, target, prior)
                # Check residual in each control volume using the *updated*
                # device power, not only global cancellation of source errors.
                cell_source_defect = float(np.max(abs((final_heat-heat)*model.volume)))
                tolerance = 1e-10*max(power, final_power, 1e-20)
                if (temperature_defect <= 1e-8 and power_defect <= tolerance
                        and cell_source_defect <= tolerance and energy["passed"]):
                    current = target
                    break
                guess = (1-relaxation)*guess+relaxation*target
            else:
                raise StructuredThermalError("Implicit semiconductor/field coupling did not converge.")
            if cancel_check is not None and cancel_check():
                raise StructuredThermalError("Coupled solve cancelled.")
            entry = {"step": step+1, "time_s": (step+1)*model.time_step, "iterations": iteration+1,
                     "temperature_defect_k": temperature_defect, "power_defect_w": power_defect,
                     "mapping_residual_w": mapping, "energy": energy}
            history.append(entry)
            totals["device_heat_j"] += final_power*model.time_step
            totals["background_heat_j"] += float(np.sum(model.heat)*model.volume)*model.time_step
            totals["boundary_heat_j"] += energy["outward_boundary_power_w"]*model.time_step
            totals["stored_energy_j"] += energy["storage_rate_w"]*model.time_step
            if not all(math.isfinite(value) for value in totals.values()):
                raise StructuredThermalError("Integrated thermal energy exceeded finite representable values.")
            if (step+1) % model.output_stride == 0 or step+1 == model.steps:
                frames.append({"time_s": entry["time_s"], "temperature_k": current.tolist(), "devices": final_records})
        totals["residual_j"] = totals["device_heat_j"]+totals["background_heat_j"]-totals["boundary_heat_j"]-totals["stored_energy_j"]
        if not math.isfinite(totals["residual_j"]):
            raise StructuredThermalError("Integrated energy residual is not finite.")
        return {"contract": RESULT_CONTRACT, "status": "completed", "temperature_k": current.tolist(),
                "frames": frames, "history": history, "integrated_energy": totals, "issues": [],
                "qualification": {"production_qualified": False, "state": "verification_reference",
                    "limitations": ["Prescribed forward-current diode reference only; not a general SPICE coupling.",
                        "No junction charge, switching loss, breakdown, transistor or airflow model.",
                        "No restart, OS-enforced memory, MPI or measured-correlation qualification."]}}
    except (StructuredThermalError, ValueError, OverflowError, FloatingPointError, ZeroDivisionError) as exc:
        return {"contract": RESULT_CONTRACT, "status": "cancelled" if "cancelled" in str(exc).lower() else "blocked",
                "temperature_k": [], "frames": [], "history": [], "issues": [{"code": "TRANSIENT_DIODE_FIELD_REJECTED", "message": str(exc)}],
                "qualification": {"production_qualified": False, "state": "not_qualified"}}
