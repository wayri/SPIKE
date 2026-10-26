# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original bounded interpolation of caller-supplied semiconductor loss data.

The rectangular tensor order is [temperature K][blocking voltage V][current A].
Voltage and current are nonnegative operating magnitudes, not terminal waveforms.
Conduction W is the full-cycle averaged loss at the stated duty/waveform; event
energies J are for one turn-on, turn-off and recovery event per switching cycle.
The caller must exclude recovery already included in Eon and declare the fixed
gate drive, duty cycle, topology and other measurement conditions in conditions.

Linear interpolation in each of three coordinates gives eight nonnegative
weights whose sum is one: it reproduces any multi-affine polynomial exactly in
real arithmetic. Nested convex interpolation avoids overflowing an unnecessary
sum of large samples. No extrapolation or physical semiconductor law is inferred.
The synthetic regression oracle and implementation are independently authored;
no vendor device data, external implementation, or external test data is used.
"""
from __future__ import annotations

import bisect
import math

MODEL_KIND = "semiconductor_operating_loss_table"
MAX_AXIS_NODES = 64
MAX_GRID_POINTS = 32768
AXES = ("temperature_k", "voltage_v", "current_a")
LOSS_COLUMNS = ("conduction_power_w", "turn_on_energy_j", "turn_off_energy_j",
                "reverse_recovery_energy_j")


class SemiconductorOperatingLossError(ValueError):
    """Coded admission/range failure, translated by the heat-source adapter."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def _require(condition, code, message):
    if not condition:
        raise SemiconductorOperatingLossError(code, message)


def _number(value, label):
    _require(type(value) in (int, float), "invalid_number", f"{label} must be a finite nonnegative number.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise SemiconductorOperatingLossError("invalid_number", f"{label} is not representable.") from exc
    _require(math.isfinite(result) and result >= 0, "invalid_number",
             f"{label} must be a finite nonnegative number.")
    return result


def _finite(value, label):
    _require(math.isfinite(value) and value >= 0, "numeric_range", f"{label} is outside the finite nonnegative range.")
    return value


def _axis(raw, name):
    _require(isinstance(raw, list) and 2 <= len(raw) <= MAX_AXIS_NODES,
             "axis_budget", f"{name} requires 2..{MAX_AXIS_NODES} nodes.")
    values = [_number(value, name) for value in raw]
    _require(all(right > left for left, right in zip(values, values[1:])),
             "invalid_grid", f"{name} must be strictly increasing.")
    if name == "temperature_k":
        _require(values[0] > 0, "invalid_grid", "Temperature nodes must be above absolute zero.")
    return values


def _tensor(raw, sizes, name):
    nt, nv, ni = sizes
    _require(isinstance(raw, list) and len(raw) == nt, "array_length",
             f"{name} must have tensor order [temperature][voltage][current].")
    result = []
    for plane in raw:
        _require(isinstance(plane, list) and len(plane) == nv, "array_length",
                 f"{name} voltage dimension does not match its axis.")
        decoded_plane = []
        for row in plane:
            _require(isinstance(row, list) and len(row) == ni, "array_length",
                     f"{name} current dimension does not match its axis.")
            decoded_plane.append([_number(value, name) for value in row])
        result.append(decoded_plane)
    return result


def _bracket(axis, value, name):
    _require(axis[0] <= value <= axis[-1], f"{name.rsplit('_', 1)[0]}_out_of_bounds",
             f"Operating {name} is outside supplied coverage; extrapolation is unsupported.")
    index = min(bisect.bisect_right(axis, value) - 1, len(axis) - 2)
    return index, (value - axis[index]) / (axis[index + 1] - axis[index])


def _lerp(left, right, fraction):
    # Preserve endpoints exactly and never sum two near-maximum samples.
    if fraction == 0:
        return left
    if fraction == 1:
        return right
    if left <= right:
        return left + fraction * (right - left)
    return right + (1 - fraction) * (left - right)


def _interpolate(tensor, brackets):
    (t, ft), (v, fv), (i, fi) = brackets
    planes = []
    for ti in (t, t + 1):
        rows = [_lerp(tensor[ti][vi][i], tensor[ti][vi][i + 1], fi) for vi in (v, v + 1)]
        planes.append(_lerp(rows[0], rows[1], fv))
    return _finite(_lerp(planes[0], planes[1], ft), "interpolated loss")


def evaluate_semiconductor_operating_loss(model, temperature_k):
    """Return an average-power partial heat evaluation; no input is modified.

    Every field and every tensor element is checked, including samples outside
    the selected cell. Storage and admission work are O(4*N), N <= 32768; the
    interpolation itself uses eight corners per column. Coordinates outside any
    declared axis fail, with no clipping, extrapolation or unit conversions.
    """
    fields = {"kind", *AXES, *LOSS_COLUMNS, "operating_voltage_v", "operating_current_a",
              "switching_frequency_hz", "conditions", "energy_terms_nonoverlapping"}
    _require(isinstance(model, dict) and set(model) == fields, "invalid_fields",
             "Operating loss model has unexpected or missing fields.")
    _require(model["kind"] == MODEL_KIND, "unsupported_model", "Unsupported operating loss model kind.")
    conditions = model["conditions"]
    _require(isinstance(conditions, str) and 0 < len(conditions) <= 4096 and conditions.strip(),
             "invalid_text", "conditions must be a nonblank string of at most 4096 characters.")
    _require(model["energy_terms_nonoverlapping"] is True, "overlapping_energy_terms",
             "Explicit nonoverlap is required: Eon must exclude separately supplied recovery energy.")
    axes = [_axis(model[name], name) for name in AXES]
    sizes = [len(axis) for axis in axes]
    _require(math.prod(sizes) <= MAX_GRID_POINTS, "grid_budget",
             f"The Cartesian grid may have at most {MAX_GRID_POINTS} points.")
    tensors = {name: _tensor(model[name], sizes, name) for name in LOSS_COLUMNS}
    coordinates = [_number(temperature_k, "temperature_k"),
                   _number(model["operating_voltage_v"], "operating_voltage_v"),
                   _number(model["operating_current_a"], "operating_current_a")]
    frequency = _number(model["switching_frequency_hz"], "switching_frequency_hz")
    brackets = [_bracket(axis, coordinate, name) for axis, coordinate, name in zip(axes, coordinates, AXES)]
    values = {name: _interpolate(tensor, brackets) for name, tensor in tensors.items()}
    powers = {name.replace("energy_j", "power_w"): _finite(frequency * values[name], name)
              for name in LOSS_COLUMNS[1:]}
    try:
        total = _finite(math.fsum([values["conduction_power_w"], *powers.values()]), "total loss")
    except OverflowError as exc:
        raise SemiconductorOperatingLossError("numeric_range", "Total loss overflowed.") from exc
    return {"average_power_w": total, "temporal_scope": "steady_average_only",
            "temperature_dependence": "supplied_trilinear_operating_table", "conditions": conditions,
            "ledger": {**values, **powers, "switching_frequency_hz": frequency,
                       "operating_voltage_v": coordinates[1], "operating_current_a": coordinates[2],
                       "temperature_k": coordinates[0], "energy_terms_nonoverlapping": True,
                       "axis_brackets": {name: axis[index:index + 2]
                                         for name, axis, (index, _) in zip(AXES, axes, brackets)},
                       "interpolation_fractions": {name: fraction
                                                   for name, (_, fraction) in zip(AXES, brackets)}},
            "limitations": [
                "Supplied rectangular operating table; no device equations, SPICE subcircuits or switching waveforms.",
                "One event of each declared type per switching cycle; conduction is already cycle-averaged.",
                "Fixed gate drive, duty, topology and other conditions are caller-declared, not verified.",
                "Recovery energy must not overlap Eon; no extrapolation or thermal transient model."]}
