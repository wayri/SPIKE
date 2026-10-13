# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded supplied-data electrical heat models, independently authored.

For piecewise-linear v and i, their product is quadratic. Simpson's three
point expression integrates it exactly in real arithmetic, unlike trapezoidal
integration of endpoint powers. Admission checks endpoints and the quadratic
stationary point for negative power; energy-storage terminal current must be
separately de-embedded before declaring dissipative_terminal_power.

Spectral data are orthogonal, distinct frequency RMS components, including DC
as its own RMS value: average P = sum(I_rms**2 R). They do not resolve transient
power. Supplied semiconductor tables interpolate conduction W and explicitly
nonoverlapping event energies J at the feedback temperature K. P = Pcond +
fsw*(Eon + Eoff + Err); Eon must exclude any separately supplied recovery loss.
No SPICE dialect, device equations, measured applicability or provenance is
verified. No third-party code, data, or test oracle is incorporated.
"""
from __future__ import annotations

import bisect
import math
import re

CONTRACT = "spike/electrical-heat-source/v1"
MAX_SAMPLES = 100000
MAX_DISTRIBUTION = 5000
WEIGHT_SUM_TOLERANCE = 1e-12


class ElectricalHeatSourceError(ValueError):
    """Stable code plus diagnostic for invalid or unsupported supplied data."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _require(condition, code, message):
    if not condition:
        raise ElectricalHeatSourceError(code, message)


def _keys(value, required, label):
    _require(isinstance(value, dict) and set(value) == set(required),
             "invalid_fields", f"{label} has unexpected or missing fields.")


def _number(value, label, nonnegative=False):
    _require(type(value) in (int, float), "invalid_number", f"{label} must be a finite number.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ElectricalHeatSourceError("invalid_number", f"{label} is not representable.") from exc
    _require(math.isfinite(result) and (not nonnegative or result >= 0),
             "invalid_number", f"{label} must be finite" + (" and nonnegative." if nonnegative else "."))
    return result


def _text(value, label, maximum=256):
    _require(isinstance(value, str) and 0 < len(value) <= maximum and value.strip(),
             "invalid_text", f"{label} must be a nonblank string of at most {maximum} characters.")
    return value


def _array(value, label, minimum=1, nonnegative=False):
    _require(isinstance(value, list) and minimum <= len(value) <= MAX_SAMPLES,
             "array_budget", f"{label} requires {minimum}..{MAX_SAMPLES} samples.")
    return [_number(item, label, nonnegative) for item in value]


def _ascending(values, label):
    _require(all(right > left for left, right in zip(values, values[1:])),
             "invalid_grid", f"{label} must be strictly increasing.")


def _finite(value, label):
    _require(math.isfinite(value) and value >= 0, "numeric_range", f"{label} is outside the finite nonnegative range.")
    return value


def _sum(values, label):
    try:
        return _finite(math.fsum(values), label)
    except OverflowError as exc:
        raise ElectricalHeatSourceError("numeric_range", f"{label} overflowed.") from exc


def _distribution(value):
    _require(isinstance(value, list) and 1 <= len(value) <= MAX_DISTRIBUTION,
             "distribution_budget", f"distribution requires 1..{MAX_DISTRIBUTION} rows.")
    result, seen = [], set()
    for item in value:
        _keys(item, ("occurrence_id", "cell_id", "weight"), "distribution row")
        occurrence = _text(item["occurrence_id"], "occurrence_id")
        cell = _text(item["cell_id"], "cell_id")
        _require((occurrence, cell) not in seen, "duplicate_target", "Duplicate occurrence/cell distribution target.")
        seen.add((occurrence, cell))
        result.append({"occurrence_id": occurrence, "cell_id": cell,
                       "weight": _number(item["weight"], "weight", True)})
    total = _sum((item["weight"] for item in result), "distribution weight sum")
    _require(abs(total - 1) <= WEIGHT_SUM_TOLERANCE, "weight_sum",
             "Distribution weights must sum to 1 within absolute 1e-12; no normalization is performed.")
    return result


def _same_sign_or_zero(left, right):
    # Sign checks must not disappear when multiplying subnormal numbers.
    return left == 0 or right == 0 or (left > 0) == (right > 0)


def _coincident_zero_crossings(v0, v1, i0, i1):
    """Compare roots exactly for supplied binary floats, without cancellation.

    Unequal interior roots create a negative-power interval, however narrow.
    Cross multiplication of integer ratios avoids rounded-root coincidence.
    """
    n0, d0 = v0.as_integer_ratio()
    n1, d1 = v1.as_integer_ratio()
    n2, d2 = i0.as_integer_ratio()
    n3, d3 = i1.as_integer_ratio()
    return n0 * n3 * d1 * d2 == n1 * n2 * d0 * d3


def _waveform(model, temperature):
    _keys(model, ("kind", "time_s", "voltage_v", "current_a", "energy_policy"), "waveform model")
    _require(model["energy_policy"] == "dissipative_terminal_power", "energy_policy",
             "Only de-embedded dissipative terminal power is admitted; stored-energy current is unsupported.")
    times = _array(model["time_s"], "time_s", 2, True)
    voltage = _array(model["voltage_v"], "voltage_v", 2)
    current = _array(model["current_a"], "current_a", 2)
    _require(len(times) == len(voltage) == len(current), "array_length", "Waveform arrays must align.")
    _ascending(times, "time_s")
    energies = []
    for t0, t1, v0, v1, i0, i1 in zip(times, times[1:], voltage, voltage[1:], current, current[1:]):
        _require(_same_sign_or_zero(v0, i0) and _same_sign_or_zero(v1, i1),
                 "nondissipative_power", "Terminal power is negative at a waveform endpoint.")
        # Normalize only for polynomial sign admission, never the physical data.
        vs, cs = max(abs(v0), abs(v1)), max(abs(i0), abs(i1))
        if vs and cs:
            v_crosses = not _same_sign_or_zero(v0, v1)
            i_crosses = not _same_sign_or_zero(i0, i1)
            if v_crosses or i_crosses:
                _require(v_crosses and i_crosses and _coincident_zero_crossings(v0, v1, i0, i1),
                         "nondissipative_power", "Unequal zero crossings create negative terminal power.")
            a, b, c, d = v0 / vs, v1 / vs, i0 / cs, i1 / cs
            dv, di = b - a, d - c
            quadratic = dv * di
            linear = a * di + c * dv
            if quadratic > 0:
                stationary = -0.5 * linear / quadratic
                if 0 < stationary < 1:
                    _require(_same_sign_or_zero(a + stationary * dv, c + stationary * di),
                             "nondissipative_power", "Terminal power is negative inside a waveform interval.")
        p0, p1 = _finite(v0 * i0, "endpoint power"), _finite(v1 * i1, "endpoint power")
        pm = _finite((v0 / 2 + v1 / 2) * (i0 / 2 + i1 / 2), "midpoint power")
        average = _sum((p0 / 6, (pm / 3) * 2, p1 / 6), "interval average power")
        energies.append(_finite(average * (t1 - t0), "interval energy"))
    duration = _finite(times[-1] - times[0], "duration")
    total = _sum(energies, "total energy")
    return {"average_power_w": _finite(total / duration, "average power"),
            "time_s": times, "duration_s": duration, "interval_energy_j": energies,
            "total_energy_j": total, "temporal_scope": "supplied_interval_average",
            "temperature_dependence": "none_supplied",
            "ledger": {"dissipated_energy_j": total},
            "limitations": ["Piecewise-linear terminal data only; no unsampled switching events.",
                            "Caller declares storage current de-embedded; no stored-energy model is verified."]}


def _spectral(model, temperature):
    _keys(model, ("kind", "frequency_hz", "rms_current_a", "resistance_ohm"), "spectral model")
    frequencies = _array(model["frequency_hz"], "frequency_hz", nonnegative=True)
    currents = _array(model["rms_current_a"], "rms_current_a", nonnegative=True)
    resistances = _array(model["resistance_ohm"], "resistance_ohm", nonnegative=True)
    _require(len(frequencies) == len(currents) == len(resistances), "array_length", "Spectral arrays must align.")
    _ascending(frequencies, "frequency_hz")
    powers = [_finite(current * (current * resistance), "spectral power")
              for current, resistance in zip(currents, resistances)]
    return {"average_power_w": _sum(powers, "spectral total power"),
            "temporal_scope": "steady_average_only", "temperature_dependence": "none_supplied",
            "ledger": {"frequency_hz": frequencies, "power_w": powers},
            "limitations": ["Distinct orthogonal RMS frequency components; DC RMS equals its absolute DC value.",
                            "No peak-to-RMS conversion, phase reconstruction, or unresolved transient power."]}


_TABLE_COLUMNS = ("conduction_power_w", "turn_on_energy_j", "turn_off_energy_j", "reverse_recovery_energy_j")


def _semiconductor(model, temperature):
    _keys(model, ("kind", "temperature_k", *_TABLE_COLUMNS, "switching_frequency_hz",
                  "conditions", "energy_terms_nonoverlapping"), "semiconductor model")
    conditions = _text(model["conditions"], "conditions", 4096)
    _require(model["energy_terms_nonoverlapping"] is True, "overlapping_energy_terms",
             "Explicit nonoverlapping energy terms are required; Eon must exclude separately supplied Err.")
    temperatures = _array(model["temperature_k"], "table temperature_k", 2, True)
    _ascending(temperatures, "table temperature_k")
    columns = {name: _array(model[name], name, 2, True) for name in _TABLE_COLUMNS}
    _require(all(len(values) == len(temperatures) for values in columns.values()),
             "array_length", "Loss table columns must align with temperature nodes.")
    frequency = _number(model["switching_frequency_hz"], "switching_frequency_hz", True)
    _require(temperatures[0] <= temperature <= temperatures[-1], "temperature_out_of_bounds",
             "Feedback temperature is outside supplied loss-table coverage; extrapolation is unsupported.")
    index = min(bisect.bisect_right(temperatures, temperature) - 1, len(temperatures) - 2)
    fraction = (temperature - temperatures[index]) / (temperatures[index + 1] - temperatures[index])
    values = {name: _sum(((1 - fraction) * column[index], fraction * column[index + 1]), name)
              for name, column in columns.items()}
    loss_powers = {name.replace("energy_j", "power_w"): _finite(frequency * values[name], name)
                   for name in _TABLE_COLUMNS[1:]}
    power = _sum((values["conduction_power_w"], *loss_powers.values()), "semiconductor total power")
    return {"average_power_w": power, "temporal_scope": "steady_average_only",
            "temperature_dependence": "supplied_piecewise_linear_table", "conditions": conditions,
            "ledger": {**values, **loss_powers, "switching_frequency_hz": frequency,
                       "temperature_bracket_k": temperatures[index:index + 2],
                       "interpolation_fraction": fraction, "energy_terms_nonoverlapping": True},
            "limitations": ["Caller-declared conditions and nonoverlapping event energies, not device-model validation.",
                            "No extrapolation, arbitrary SPICE dialect, switching waveform, or thermal transient model."]}


def _energy_balanced(model, temperature):
    from .energy_balanced_heat import evaluate_energy_balanced_heat
    return evaluate_energy_balanced_heat(model, temperature)


def _operating_semiconductor(model, temperature):
    from .semiconductor_operating_losses import (
        evaluate_semiconductor_operating_loss, SemiconductorOperatingLossError,
    )
    try:
        return evaluate_semiconductor_operating_loss(model, temperature)
    except SemiconductorOperatingLossError as exc:
        raise ElectricalHeatSourceError(exc.code, str(exc)) from exc


_MODELS = {"terminal_waveform": _waveform, "spectral_resistive": _spectral,
           "semiconductor_loss_table": _semiconductor,
           "energy_balanced_terminal_waveform": _energy_balanced,
           "semiconductor_operating_loss_table": _operating_semiconductor}


def evaluate_electrical_heat_source(request, temperature_k):
    """Return a new JSON-compatible average-power ledger or a coded ValueError.

    All temperatures are kelvin. Distribution weights are preserved within an
    absolute 1e-12 sum tolerance; no geometric coverage or source hash is verified
    here. The assembly binding owns cell identity and conservative W-to-W/m3
    conversion. Resource use is linear in at most 100000 samples and 5000 rows.
    """
    _keys(request, ("contract", "id", "model", "distribution", "provenance"), "electrical heat source")
    _require(request["contract"] == CONTRACT, "invalid_contract", "Unsupported electrical heat source contract.")
    source_id = _text(request["id"], "id")
    temperature = _number(temperature_k, "temperature_k", True)
    distribution = _distribution(request["distribution"])
    provenance = request["provenance"]
    _keys(provenance, ("source_sha256", "description"), "provenance")
    digest = provenance["source_sha256"]
    _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
             "invalid_provenance", "source_sha256 must be a lowercase SHA-256 declaration.")
    description = _text(provenance["description"], "provenance description", 4096)
    model = request["model"]
    _require(isinstance(model, dict) and isinstance(model.get("kind"), str) and model["kind"] in _MODELS,
             "unsupported_model", "Unsupported or missing electrical heat model kind.")
    result = _MODELS[model["kind"]](model, temperature)
    return {"contract": "spike/electrical-heat-evaluation/v1", "id": source_id,
            "model_kind": model["kind"], "model_status": "experimental", "temperature_k": temperature,
            "distribution": distribution, "provenance": {"source_sha256": digest, "description": description},
            "provenance_status": "caller_declared_not_verified", **result}
