"""Editable passive assumptions for loaded, linear SI studies (SI units).

Grade temperature envelopes are classification limits, not bias curves or
part-specific noise measurements. Numeric parasitics are illustrative defaults.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite, log10, sqrt
from typing import Any, Mapping

import numpy as np

KB = 1.380649e-23
CAPACITOR_GRADES = {
    "C0G": {"temperature_min_c": -55, "temperature_max_c": 125, "temperature_low_fraction": -0.003, "temperature_high_fraction": 0.003},
    "X7R": {"temperature_min_c": -55, "temperature_max_c": 125, "temperature_low_fraction": -0.15, "temperature_high_fraction": 0.15},
    "X5R": {"temperature_min_c": -55, "temperature_max_c": 85, "temperature_low_fraction": -0.15, "temperature_high_fraction": 0.15},
    "Y5V": {"temperature_min_c": -30, "temperature_max_c": 85, "temperature_low_fraction": -0.82, "temperature_high_fraction": 0.22},
    "Z5U": {"temperature_min_c": 10, "temperature_max_c": 85, "temperature_low_fraction": -0.56, "temperature_high_fraction": 0.22},
}
RESISTOR_GRADES = {
    "thick_film": {"tolerance_fraction": 0.01, "tcr_ppm_per_c": 100.0, "noise_index_db": -10.0},
    "thin_film": {"tolerance_fraction": 0.001, "tcr_ppm_per_c": 25.0, "noise_index_db": -30.0},
    "metal_film": {"tolerance_fraction": 0.01, "tcr_ppm_per_c": 50.0, "noise_index_db": -25.0},
    "wirewound": {"tolerance_fraction": 0.01, "tcr_ppm_per_c": 20.0, "noise_index_db": -40.0},
}


def number(value: Any, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    value = float(value)
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{name} is outside [{minimum}, {maximum}].")
    return value


def passive_defaults(kind: str = "resistor", grade: str | None = None) -> dict[str, Any]:
    if kind == "resistor":
        grade = grade or "thick_film"
        if grade not in RESISTOR_GRADES:
            raise ValueError(f"Unknown resistor grade {grade!r}.")
        return {"kind": kind, "grade": grade, "resistance_ohm": 33.0,
                **RESISTOR_GRADES[grade], "inductance_h": 0.5e-9, "capacitance_f": 0.05e-12,
                "dc_voltage_v": 0.0, "temperature_c": 25.0, "corner": "nominal"}
    if kind != "capacitor":
        raise ValueError("Passive kind must be resistor or capacitor.")
    grade = grade or "X7R"
    if grade not in CAPACITOR_GRADES:
        raise ValueError("Choose C0G, X7R, X5R, Y5V or Z5U; Y5 alone is an incomplete grade.")
    return {"kind": kind, "grade": grade, "capacitance_f": 100e-9,
            "tolerance_fraction": 0.1, "esr_ohm": 0.03, "esl_h": 0.5e-9,
            "leakage_ohm": 1e9, "rated_voltage_v": 25.0, "dc_voltage_v": 0.0,
            "bias_factor": 1.0, "aging_percent_per_decade": 0.0, "age_hours": 1000.0,
            "temperature_c": 25.0, "temperature_factor": 1.0, "corner": "nominal"}


def resolve_passive(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Passive model must be an object.")
    base = passive_defaults(raw.get("kind", "resistor"), raw.get("grade"))
    unknown = set(raw) - set(base)
    if unknown:
        raise ValueError(f"Unknown passive fields: {sorted(unknown)}.")
    model = {**base, **raw}
    for key, value in model.items():
        if key not in {"kind", "grade", "corner"}:
            number(value, key)
    corner = model["corner"]
    if corner not in {"nominal", "min", "max"}:
        raise ValueError("corner must be nominal, min or max.")
    t = number(model["temperature_c"], "temperature_c", -273.14, 500)
    tol = number(model["tolerance_fraction"], "tolerance_fraction", 0, 0.99)
    direction = {"nominal": 0, "min": -1, "max": 1}[corner]
    warnings = ["Generic editable assumptions; replace parasitics, bias and noise with manufacturer data."]
    number(model["dc_voltage_v"], "dc_voltage_v", -1e6, 1e6)
    if model["kind"] == "resistor":
        r = number(model["resistance_ohm"], "resistance_ohm", 1e-9, 1e12)
        number(model["inductance_h"], "inductance_h", 0, 1)
        number(model["capacitance_f"], "capacitance_f", 0, 1)
        number(model["noise_index_db"], "noise_index_db", -200, 100)
        r *= (1 + direction * tol) * (1 + model["tcr_ppm_per_c"] * 1e-6 * (t - 25))
        if r <= 0:
            raise ValueError("The TCR/temperature combination produces non-positive resistance.")
        effective = {"resistance_ohm": r}
    else:
        envelope = CAPACITOR_GRADES[model["grade"]]
        if not envelope["temperature_min_c"] <= t <= envelope["temperature_max_c"]:
            raise ValueError("Capacitor temperature is outside its grade envelope.")
        c = number(model["capacitance_f"], "capacitance_f", 1e-18, 1)
        rated = number(model["rated_voltage_v"], "rated_voltage_v", 1e-9, 1e6)
        if abs(model["dc_voltage_v"]) > rated:
            raise ValueError("Capacitor DC bias exceeds its rated voltage.")
        bias = number(model["bias_factor"], "bias_factor", 0.001, 2)
        temp = number(model["temperature_factor"], "temperature_factor", 0.001, 2)
        aging = number(model["aging_percent_per_decade"], "aging_percent_per_decade", 0, 30)
        hours = number(model["age_hours"], "age_hours", 1, 1e9)
        number(model["esr_ohm"], "esr_ohm", 0, 1e9)
        number(model["esl_h"], "esl_h", 0, 1)
        number(model["leakage_ohm"], "leakage_ohm", 1e-6, 1e15)
        # Bounds deliberately use the complete grade envelope, not an invented
        # temperature curve. Nominal uses the explicit temperature factor.
        if direction:
            temp = 1 + envelope["temperature_low_fraction" if direction < 0 else "temperature_high_fraction"]
        c *= (1 + direction * tol) * bias * temp * (1 - aging / 100 * log10(hours))
        if c <= 0:
            raise ValueError("Capacitor aging assumptions produce non-positive capacitance.")
        if model["grade"] != "C0G" and bias == 1 and model["dc_voltage_v"]:
            warnings.append("DC bias is specified but no capacitance derating has been supplied.")
        effective = {"capacitance_f": c, "temperature_envelope": deepcopy(envelope)}
    return {"model": model, "effective": effective, "warnings": warnings}


def passive_admittance(resolved: Mapping[str, Any], frequencies_hz: np.ndarray) -> np.ndarray:
    m, e = resolved["model"], resolved["effective"]
    omega = 2 * np.pi * frequencies_hz
    if m["kind"] == "resistor":
        return 1 / (e["resistance_ohm"] + 1j * omega * m["inductance_h"]) + 1j * omega * m["capacitance_f"]
    jw_c = 1j * omega * e["capacitance_f"]
    return jw_c / (1 + jw_c * (m["esr_ohm"] + 1j * omega * m["esl_h"])) + 1 / m["leakage_ohm"]


def resistor_noise(resolved: Mapping[str, Any], low_hz: float, high_hz: float) -> dict[str, float]:
    m, e = resolved["model"], resolved["effective"]
    if m["kind"] != "resistor":
        raise ValueError("Resistor noise requires a resistor model.")
    number(low_hz, "low_hz", 1e-12)
    number(high_hz, "high_hz", low_hz)
    thermal = 4 * KB * (m["temperature_c"] + 273.15) * e["resistance_ohm"] * (high_hz - low_hz)
    excess = (abs(m["dc_voltage_v"]) * 1e-6 * 10 ** (m["noise_index_db"] / 20)) ** 2 * log10(high_hz / low_hz)
    return {"thermal_rms_v": sqrt(thermal), "excess_rms_v": sqrt(excess), "total_rms_v": sqrt(thermal + excess)}
