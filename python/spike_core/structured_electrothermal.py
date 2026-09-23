# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Steady DC resistor-network/structured-field electrothermal coupling.

Every resistor has an explicit normalized cell distribution. The transpose
of that distribution samples its temperature, and the distribution deposits
its Joule power. No geometric ownership or device law is inferred.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Callable, Mapping

import numpy as np

from .native_mna import run_native_mna, validate_native_mna_request
from .structured_solid_thermal import (
    StructuredThermalError, _number, _parse_request, _positive_int,
    _strict_keys, solve_structured_solid_thermal,
)

CONTRACT = "spike/structured-electrothermal-dc/v1"
RESULT_CONTRACT = "spike/structured-electrothermal-dc-result/v1"


def _prepare(request: Any):
    if not isinstance(request, Mapping) or request.get("contract") != CONTRACT:
        raise StructuredThermalError(f"Expected {CONTRACT}.")
    _strict_keys(request, {"contract", "circuit", "thermal", "bindings", "iteration"}, "electrothermal")
    thermal = deepcopy(request.get("thermal"))
    model = _parse_request(thermal)
    if model.mode != "steady" or model.cell_count > 2048:
        raise StructuredThermalError("DC coupling requires a steady thermal grid of at most 2048 cells.")
    circuit = deepcopy(request.get("circuit"))
    if not isinstance(circuit, dict):
        raise StructuredThermalError("circuit must be an object.")
    validation = validate_native_mna_request(circuit)
    if not validation.get("valid"):
        raise StructuredThermalError(f"Circuit validation failed: {validation.get('issues')}.")
    if circuit["analysis"] != {"mode": "operating_point"} or len(circuit["elements"]) > 128:
        raise StructuredThermalError("DC coupling admits at most 128 elements and an operating-point study.")
    resistors = {}
    for element in circuit["elements"]:
        kind = element["type"]
        if kind not in {"resistor", "voltage_source", "current_source"} or "waveform" in element:
            raise StructuredThermalError("DC coupling supports resistors and constant independent sources only.")
        if kind == "resistor":
            resistors[element["id"]] = element
    raw = request.get("bindings")
    if not isinstance(raw, list) or len(raw) != len(resistors) or not raw:
        raise StructuredThermalError("Exactly one loss/temperature binding per resistor is required.")
    bindings = []
    seen = set()
    for binding in raw:
        if not isinstance(binding, Mapping):
            raise StructuredThermalError("Every binding must be an object.")
        _strict_keys(binding, {"element_id", "cells", "weights", "reference_temperature_k", "temperature_coefficient_per_k"}, "binding")
        identifier = binding.get("element_id")
        if not isinstance(identifier, str) or identifier not in resistors or identifier in seen:
            raise StructuredThermalError("Resistor binding IDs must be known and unique.")
        seen.add(identifier)
        cells, weights = binding.get("cells"), binding.get("weights")
        if not isinstance(cells, list) or not cells or len(cells) > model.cell_count:
            raise StructuredThermalError("Binding cells must be a nonempty bounded array.")
        if any(type(c) is not int or c < 0 or c >= model.cell_count for c in cells) or len(set(cells)) != len(cells):
            raise StructuredThermalError("Binding cells must be unique valid cell indices.")
        if not isinstance(weights, list) or len(weights) != len(cells):
            raise StructuredThermalError("Every bound cell needs one weight.")
        parsed_weights = np.array([_number(w, "weight", minimum=0) for w in weights])
        if abs(math.fsum(parsed_weights) - 1.0) > 1e-12:
            raise StructuredThermalError("Loss mapping weights must sum to one; automatic normalization is forbidden.")
        bindings.append((identifier, np.asarray(cells), parsed_weights,
                         _number(binding.get("reference_temperature_k"), "reference_temperature_k", minimum=0),
                         _number(binding.get("temperature_coefficient_per_k"), "temperature_coefficient_per_k"),
                         _number(resistors[identifier]["resistance_ohm"], "resistance_ohm", minimum=1e-30)))
    options = request.get("iteration", {})
    if not isinstance(options, Mapping):
        raise StructuredThermalError("iteration must be an object.")
    _strict_keys(options, {"max_iterations", "relaxation", "temperature_tolerance_k", "power_relative_tolerance"}, "iteration")
    maximum = _positive_int(options.get("max_iterations", 100), "max_iterations", maximum=200)
    relaxation = _number(options.get("relaxation", 0.5), "relaxation", minimum=1e-6)
    if relaxation > 1:
        raise StructuredThermalError("relaxation must not exceed one.")
    tolerance = _number(options.get("temperature_tolerance_k", 1e-7), "temperature_tolerance_k", minimum=1e-12)
    power_tolerance = _number(options.get("power_relative_tolerance", 1e-9), "power_relative_tolerance", minimum=1e-14)
    return thermal, model, circuit, resistors, bindings, maximum, relaxation, tolerance, power_tolerance


def solve_structured_electrothermal(request: Any, *, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Iterate a declared resistive circuit against a steady thermal field."""
    def cancel():
        if cancel_check is not None and cancel_check():
            raise StructuredThermalError("Electrothermal solve cancelled.")

    try:
        thermal, model, circuit, resistors, bindings, maximum, relaxation, tolerance, power_tolerance = _prepare(request)
        cancel()
        references = [float(b.get("temperature_k", b.get("ambient_temperature_k")))
                      for b in model.boundaries.values() if b["type"] in {"temperature", "convection", "radiation"}]
        temperatures = np.full(model.cell_count, float(np.mean(references)) if references else 300.0)
        history = []
        for iteration in range(maximum):
            cancel()
            for identifier, cells, weights, reference, alpha, r0 in bindings:
                temperature = float(np.dot(weights, temperatures[cells]))
                resistance = r0 * (1 + alpha * (temperature - reference))
                if not math.isfinite(resistance) or resistance <= 0:
                    raise StructuredThermalError("Temperature-dependent resistance is nonpositive or non-finite.")
                resistors[identifier]["resistance_ohm"] = resistance
            electrical = run_native_mna(circuit)
            cancel()
            if electrical["status"] != "completed":
                raise StructuredThermalError("Electrical operating-point solve failed.")
            powers = electrical["data"]["element_power_w"]
            balance = abs(math.fsum(powers.values()))
            electrical_scale = max(math.fsum(abs(v) for v in powers.values()), 1e-30)
            if not math.isfinite(electrical_scale) or balance > 1e-10 * electrical_scale:
                raise StructuredThermalError("Electrical power balance failed.")
            deposited = np.zeros(model.cell_count)
            for identifier, cells, weights, *_ in bindings:
                power = powers[identifier]
                if not math.isfinite(power) or power < 0:
                    raise StructuredThermalError("Resistor loss must be finite and nonnegative.")
                deposited[cells] += weights * power
            total_loss = math.fsum(powers[b[0]] for b in bindings)
            mapping_residual = abs(float(np.sum(deposited)) - total_loss)
            if mapping_residual > 1e-11 * max(total_loss, 1e-30):
                raise StructuredThermalError("Electrical-to-thermal loss mapping is not conservative.")
            thermal["heat_generation_w_m3"] = (model.heat + deposited / model.volume).tolist()
            field = solve_structured_solid_thermal(thermal, cancel_check=cancel_check)
            cancel()
            if field["status"] != "completed":
                raise StructuredThermalError(f"Thermal iteration rejected: {field['issues']}.")
            target = np.asarray(field["temperature_k"])
            defect = float(np.max(np.abs(target - temperatures)))
            # Estimate the electrical constitutive defect at the returned field,
            # so a small relaxation cannot masquerade as convergence.
            constitutive_defect = 0.0
            for identifier, cells, weights, reference, alpha, r0 in bindings:
                next_r = r0 * (1 + alpha * (float(np.dot(weights, target[cells])) - reference))
                if not math.isfinite(next_r) or next_r <= 0:
                    raise StructuredThermalError("Thermal update leaves the admitted resistance law.")
                constitutive_defect = max(constitutive_defect, abs(next_r / resistors[identifier]["resistance_ohm"] - 1))
                resistors[identifier]["resistance_ohm"] = next_r
            # Re-evaluate the circuit at the actual returned field. A small
            # resistance change alone does not bound branch power changes.
            corrected = run_native_mna(circuit)
            cancel()
            if corrected["status"] != "completed":
                raise StructuredThermalError("Electrical solve at the updated field failed.")
            final_powers = corrected["data"]["element_power_w"]
            final_loss = math.fsum(final_powers[b[0]] for b in bindings)
            power_scale = max(total_loss, final_loss, 1e-30)
            power_defect = math.fsum(abs(final_powers[b[0]] - powers[b[0]]) for b in bindings) / power_scale
            final_balance = abs(math.fsum(final_powers.values()))
            if not math.isfinite(power_defect) or final_balance > 1e-10 * max(math.fsum(abs(p) for p in final_powers.values()), 1e-30):
                raise StructuredThermalError("Updated electrical power balance failed.")
            history.append({"iteration": iteration + 1, "temperature_defect_k": defect,
                            "constitutive_relative_defect": constitutive_defect,
                            "power_relative_defect": power_defect, "joule_power_w": final_loss,
                            "mapping_residual_w": mapping_residual, "electrical_balance_w": balance})
            if defect <= tolerance and power_defect <= power_tolerance:
                return {"contract": RESULT_CONTRACT, "status": "completed", "model_status": "experimental",
                        "temperature_k": target.tolist(), "electrical": corrected, "thermal": field,
                        "coupled_power_residual_w": final_loss + float(np.sum(model.heat) * model.volume) - field["energy"]["outward_boundary_power_w"],
                        "history": history, "issues": [],
                        "qualification": {"production_qualified": False, "scope": "steady_dc_resistors_and_structured_solid_field"}}
            temperatures += relaxation * (target - temperatures)
        raise StructuredThermalError("Electrothermal iteration limit reached without satisfying coupled residuals.")
    except (StructuredThermalError, OverflowError, FloatingPointError) as exc:
        return {"contract": RESULT_CONTRACT, "status": "cancelled" if "cancelled" in str(exc).lower() else "blocked",
                "temperature_k": [], "history": [], "issues": [{"code": "ELECTROTHERMAL_REJECTED", "message": str(exc)}],
                "qualification": {"production_qualified": False}}
