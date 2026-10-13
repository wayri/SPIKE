# SPDX-License-Identifier: Apache-2.0
"""Original generic lumped passive models; no manufacturer qualification.

See docs/SPIKES_PASSIVE_MODEL_EQUATIONS.md for topology, units and limits.
"""

from __future__ import annotations

import math
import re
from typing import Any


_KINDS = {"resistor": "R", "capacitor": "C", "inductor": "L", "kelvin_shunt": "R"}
_LIMITATIONS = (
    "Generic linear lumped model, not a characterized manufacturer part.",
    "Tolerance and temperature are static compile-time value adjustments only.",
    "No self-heating, bias dependence, saturation, hysteresis, aging or distributed RF effects.",
    "Parasitics are explicit user inputs; zero means absent, not an inferred estimate.",
)


def _finite(label: str, value: Any) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def build_model(
    kind: str, value: float, *, name: str = "SPK_PASSIVE",
    series_resistance_ohm: float = 0, series_inductance_h: float = 0,
    parallel_capacitance_f: float = 0, leakage_resistance_ohm: float | None = None,
    contact_resistance_ohm: float = 0, tolerance_percent: float = 1,
    corner: float = 0, temperature_c: float = 25, reference_temperature_c: float = 25,
    tc1_per_k: float = 0, tc2_per_k2: float = 0,
) -> dict[str, Any]:
    """Compile an explicit two-terminal RLC or four-terminal Kelvin subcircuit.

    Corner is a deterministic fraction in [-1, 1], not a random distribution.
    Kelvin contacts are each contact_resistance_ohm and body R is value.
    """
    if not isinstance(kind, str) or kind not in _KINDS:
        raise ValueError(f"kind must be one of {', '.join(_KINDS)}")
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) is None:
        raise ValueError("name must be a simple ASCII identifier of at most 64 characters")
    raw = {
        "value": value, "series_resistance_ohm": series_resistance_ohm,
        "series_inductance_h": series_inductance_h,
        "parallel_capacitance_f": parallel_capacitance_f,
        "contact_resistance_ohm": contact_resistance_ohm,
        "tolerance_percent": tolerance_percent, "corner": corner,
        "temperature_c": temperature_c, "reference_temperature_c": reference_temperature_c,
        "tc1_per_k": tc1_per_k, "tc2_per_k2": tc2_per_k2,
    }
    params = {key: _finite(key, item) for key, item in raw.items()}
    if params["value"] <= 0:
        raise ValueError("value must be positive")
    for key in ("series_resistance_ohm", "series_inductance_h", "parallel_capacitance_f", "contact_resistance_ohm"):
        if params[key] < 0:
            raise ValueError(f"{key} must be nonnegative")
    if not 0 <= params["tolerance_percent"] < 100 or not -1 <= params["corner"] <= 1:
        raise ValueError("tolerance_percent must be in [0,100); corner must be in [-1,1]")
    if min(params["temperature_c"], params["reference_temperature_c"]) <= -273.15:
        raise ValueError("temperature must exceed absolute zero")
    leakage = None if leakage_resistance_ohm is None else _finite("leakage_resistance_ohm", leakage_resistance_ohm)
    if leakage is not None and leakage <= 0:
        raise ValueError("leakage_resistance_ohm must be positive or None")
    params["leakage_resistance_ohm"] = leakage
    if kind == "kelvin_shunt":
        if any(params[key] for key in ("series_resistance_ohm", "series_inductance_h", "parallel_capacitance_f")) or leakage is not None:
            raise ValueError("Kelvin shunt supports body and contact resistance only")
    elif params["contact_resistance_ohm"]:
        raise ValueError("contact_resistance_ohm is only supported for kelvin_shunt")

    delta = params["temperature_c"] - params["reference_temperature_c"]
    thermal = 1 + params["tc1_per_k"] * delta + params["tc2_per_k2"] * delta * delta
    effective = params["value"] * (1 + params["corner"] * params["tolerance_percent"] / 100) * thermal
    if not math.isfinite(effective) or effective <= 0:
        raise ValueError("effective value must remain positive and finite")
    pins = ["FP", "FN", "SP", "SN"] if kind == "kelvin_shunt" else ["P", "N"]
    lines = ["* Original SPIKE generic linear passive model; not manufacturer data",
             f".subckt {name} {' '.join(pins)}"]
    if kind == "kelvin_shunt":
        contact = params["contact_resistance_ohm"]
        # A 0 V source is an exact ideal connection with a defined branch current.
        # Distinct exposed pins cannot be collapsed by the caller's net naming.
        prefix = "R" if contact else "V"
        lines.extend((f"{prefix}CONTACTP FP SP {contact:.17g}",
                      f"RBODY SP SN {effective:.17g}",
                      f"{prefix}CONTACTN SN FN {contact:.17g}"))
    else:
        chain = []
        if params["series_resistance_ohm"]:
            chain.append(("RSER", params["series_resistance_ohm"]))
        if params["series_inductance_h"]:
            chain.append(("LSER", params["series_inductance_h"]))
        chain.append((_KINDS[kind] + "BODY", effective))
        first = "P"
        for index, (element, amount) in enumerate(chain):
            last = "N" if index == len(chain) - 1 else f"INT{index + 1}"
            lines.append(f"{element} {first} {last} {amount:.17g}")
            first = last
        if params["parallel_capacitance_f"]:
            lines.append(f"CPAR P N {params['parallel_capacitance_f']:.17g}")
        if leakage is not None:
            lines.append(f"RLEAK P N {leakage:.17g}")
    lines.append(f".ends {name}")
    return {"kind": kind, "name": name, "pins": pins, "source": "\n".join(lines) + "\n",
            "effective_value": effective, "parameters": params,
            "limitations": list(_LIMITATIONS)}


def impedance(model: dict[str, Any], frequency_hz: float) -> complex:
    """Return two-terminal impedance in ohms; open circuits return inf+0j.

    Kelvin is deliberately excluded: sense loading requires a four-node solve.
    Raises ValueError for numeric range overflow, rather than an invented result.
    """
    frequency = _finite("frequency_hz", frequency_hz)
    if frequency < 0:
        raise ValueError("frequency_hz must be nonnegative")
    if not isinstance(model, dict) or "kind" not in model or "parameters" not in model:
        raise ValueError("model must be a build_model result")
    checked = build_model(model["kind"], **model["parameters"])
    kind, p = checked["kind"], checked["parameters"]
    if kind == "kelvin_shunt":
        raise ValueError("Kelvin shunt is four-terminal; specify sense loading in a circuit solve")
    value = checked["effective_value"]
    leakage = p["leakage_resistance_ohm"]
    if frequency == 0 and kind == "capacitor":
        return complex(math.inf if leakage is None else leakage, 0)
    omega = 2 * math.pi * frequency
    if not math.isfinite(omega):
        raise ValueError("frequency exceeds floating-point range")

    def frequency_product(amount: float) -> float:
        product = omega * amount
        if not math.isfinite(product) or (omega > 0 and amount > 0 and product == 0):
            raise ValueError("frequency-element product exceeds floating-point range")
        return product

    try:
        body = (complex(value, 0) if kind == "resistor" else
                complex(0, frequency_product(value)) if kind == "inductor" else
                complex(0, -1 / frequency_product(value)))
        series = body + complex(p["series_resistance_ohm"], frequency_product(p["series_inductance_h"]))
        if not math.isfinite(series.real) or not math.isfinite(series.imag):
            raise ValueError("impedance exceeds floating-point range")
        if series == 0:
            return 0j
        shunt = complex(0 if leakage is None else 1 / leakage, frequency_product(p["parallel_capacitance_f"]))
        if shunt == 0:
            return series
        admittance = 1 / series + shunt
        if not math.isfinite(admittance.real) or not math.isfinite(admittance.imag):
            raise ValueError("admittance exceeds floating-point range")
        if admittance == 0:
            return complex(math.inf, 0)
        result = 1 / admittance
        if not math.isfinite(result.real) or not math.isfinite(result.imag):
            raise ValueError("impedance exceeds floating-point range")
        return result
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("impedance exceeds floating-point range") from exc
