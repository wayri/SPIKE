"""Analytic, deterministic evidence fixtures for thermal solver qualification.

These are verification references, not a general CFD/FEM solver and not a
claim that a candidate engine is field-qualified.  An adapter must execute
and compare its own output against these fixtures before it can cite them.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class Layer:
    thickness_m: float
    conductivity_w_mk: float

    def resistance_k_per_w(self, area_m2: float) -> float:
        if self.thickness_m <= 0 or self.conductivity_w_mk <= 0 or area_m2 <= 0:
            raise ValueError("Layer thickness, conductivity, and cross-sectional area must be positive.")
        return self.thickness_m / (self.conductivity_w_mk * area_m2)


def layered_conduction_reference(
    *,
    layers: Iterable[Layer | Mapping[str, float]],
    area_m2: float,
    contact_resistances_k_per_w: Iterable[float] = (),
    heat_w: float = 1.0,
    cold_temperature_k: float = 293.15,
) -> dict[str, Any]:
    """Closed-form steady 1-D series conduction with explicit contacts."""
    if heat_w < 0 or cold_temperature_k <= 0:
        raise ValueError("Heat must be non-negative and cold boundary temperature positive.")
    parsed = [layer if isinstance(layer, Layer) else Layer(float(layer["thickness_m"]), float(layer["conductivity_w_mk"])) for layer in layers]
    if not parsed:
        raise ValueError("At least one material layer is required.")
    contacts = [float(value) for value in contact_resistances_k_per_w]
    if len(contacts) not in (0, len(parsed) - 1) or any(value < 0 for value in contacts):
        raise ValueError("Contact resistances must be non-negative and occur only between layers.")
    layer_r = [layer.resistance_k_per_w(area_m2) for layer in parsed]
    resistance = sum(layer_r) + sum(contacts)
    interfaces = [cold_temperature_k]
    # Walk from the cold boundary toward the source; each entry is an exact
    # material/interface temperature, without numerical discretization.
    temperature = cold_temperature_k
    for index in range(len(parsed) - 1, -1, -1):
        temperature += heat_w * layer_r[index]
        interfaces.append(temperature)
        if index and contacts:
            temperature += heat_w * contacts[index - 1]
            interfaces.append(temperature)
    hot_temperature_k = cold_temperature_k + heat_w * resistance
    conducted_w = (hot_temperature_k - cold_temperature_k) / resistance if resistance else 0.0
    residual_w = heat_w - conducted_w
    return {
        "contract": "spike/thermal-analytic-layered-conduction/v1",
        "model_status": "analytic_reference_fixture",
        "heat_w": heat_w,
        "area_m2": area_m2,
        "cold_temperature_k": cold_temperature_k,
        "hot_temperature_k": hot_temperature_k,
        "total_resistance_k_per_w": resistance,
        "layer_resistances_k_per_w": layer_r,
        "contact_resistances_k_per_w": contacts,
        "interface_temperatures_cold_to_hot_k": interfaces,
        "conservation": {
            "input_heat_w": heat_w,
            "conducted_heat_w": conducted_w,
            "residual_w": residual_w,
            "relative_residual": abs(residual_w) / max(abs(heat_w), 1e-30),
            "passed": abs(residual_w) <= max(1e-12, abs(heat_w) * 1e-12),
        },
    }


def assess_mesh_convergence(levels: Iterable[Mapping[str, float]], *, metric_key: str = "hot_temperature_k", relative_tolerance: float = 0.002) -> dict[str, Any]:
    """Assess a supplied coarse-to-fine sequence; no solver value is invented."""
    records = [dict(level) for level in levels]
    if len(records) < 3:
        raise ValueError("Thermal mesh convergence requires at least three coarse-to-fine levels.")
    if relative_tolerance <= 0:
        raise ValueError("Relative tolerance must be positive.")
    values = [float(record[metric_key]) for record in records]
    cells = [float(record["cells"]) for record in records]
    if any(value <= 0 for value in cells) or any(right <= left for left, right in zip(cells, cells[1:])):
        raise ValueError("Mesh levels must have strictly increasing positive cell counts.")
    deltas = [abs(right - left) / max(abs(right), 1e-30) for left, right in zip(values, values[1:])]
    return {
        "contract": "spike/thermal-mesh-convergence/v1",
        "metric": metric_key,
        "levels": records,
        "successive_relative_changes": deltas,
        "finest_relative_change": deltas[-1],
        "relative_tolerance": relative_tolerance,
        "passed": deltas[-1] <= relative_tolerance,
        "meaning": "A passed numeric sequence is fixture evidence only; geometry, boundary conditions, and experimental correlation remain separate gates.",
    }


def electrothermal_fixed_point_reference(
    *,
    voltage_v: float,
    resistance_at_ambient_ohm: float,
    temperature_coefficient_per_k: float,
    thermal_resistance_k_per_w: float,
    ambient_temperature_k: float = 293.15,
    relaxation: float = 0.5,
    tolerance_k: float = 1e-8,
    max_iterations: int = 200,
) -> dict[str, Any]:
    """Voltage-driven resistor/thermal fixed-point reference with exact root."""
    if voltage_v < 0 or resistance_at_ambient_ohm <= 0 or thermal_resistance_k_per_w < 0 or ambient_temperature_k <= 0:
        raise ValueError("Voltage, resistance, thermal resistance, and ambient temperature are invalid.")
    if not 0 < relaxation <= 1 or tolerance_k <= 0 or max_iterations < 1:
        raise ValueError("Relaxation, tolerance, or iteration limit is invalid.")
    coupling = thermal_resistance_k_per_w * voltage_v * voltage_v / resistance_at_ambient_ohm
    if temperature_coefficient_per_k < 0:
        raise ValueError("This positive-temperature-coefficient reference does not support negative coefficients.")
    exact_rise = coupling if temperature_coefficient_per_k == 0 else (-1.0 + sqrt(1.0 + 4.0 * temperature_coefficient_per_k * coupling)) / (2.0 * temperature_coefficient_per_k)
    temperature = ambient_temperature_k
    trace: list[dict[str, float]] = []
    converged = False
    for iteration in range(1, max_iterations + 1):
        resistance = resistance_at_ambient_ohm * (1.0 + temperature_coefficient_per_k * (temperature - ambient_temperature_k))
        power = voltage_v * voltage_v / resistance
        target = ambient_temperature_k + thermal_resistance_k_per_w * power
        updated = temperature + relaxation * (target - temperature)
        delta = abs(updated - temperature)
        trace.append({"iteration": iteration, "temperature_k": updated, "power_w": power, "fixed_point_delta_k": delta})
        temperature = updated
        if delta <= tolerance_k:
            converged = True
            break
    final_power = voltage_v * voltage_v / (resistance_at_ambient_ohm * (1.0 + temperature_coefficient_per_k * (temperature - ambient_temperature_k)))
    thermal_balance_w = (temperature - ambient_temperature_k) / thermal_resistance_k_per_w if thermal_resistance_k_per_w else (0.0 if final_power == 0 else float("inf"))
    return {
        "contract": "spike/electrothermal-fixed-point-reference/v1",
        "model_status": "analytic_reference_fixture",
        "status": "converged" if converged else "iteration_limit",
        "iterations": len(trace),
        "temperature_k": temperature,
        "exact_temperature_k": ambient_temperature_k + exact_rise,
        "relative_temperature_error": abs(temperature - ambient_temperature_k - exact_rise) / max(abs(exact_rise), 1e-30),
        "power_w": final_power,
        "electrothermal_balance_residual_w": abs(final_power - thermal_balance_w),
        "trace": trace,
        "qualification": "Reference fixture only. It does not establish semiconductor electrothermal, transient, or field-solver validity.",
    }
