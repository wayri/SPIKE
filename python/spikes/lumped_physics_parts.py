# SPDX-License-Identifier: Apache-2.0
"""Original, unqualified multi-terminal lumped subcircuit templates.

No solver selection or numerical kernel lives here. See
docs/SPIKES_LUMPED_PHYSICS_PARTS.md for topology and validity boundaries.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .passive_models import build_model


_COMMON = [
    "Original generic lumped model; not manufacturer-characterized or qualified.",
    "Defaults are illustrative inputs, not inferred physical part properties.",
    "No process, geometry, distributed-field, TCAD, self-heating or breakdown model.",
    "All terminals must have an appropriate external bias or return path.",
]
_SYMBOLS = {"nmos4": "mosfet.n_channel.4_terminal", "npn4": "bjt.npn.4_terminal",
            "resistor3": "resistor.substrate.3_terminal",
            "feedthrough_capacitor3": "capacitor.feedthrough.3_terminal",
            "kelvin_shunt4": "resistor.kelvin.4_terminal"}
_CATALOG = {
    "nmos4": {
        "name": "NMOS with explicit bulk junctions",
        "pins": ["D", "G", "S", "B"],
        "defaults": {"threshold_voltage_v": 1., "transconductance_a_per_v2": .001,
                     "channel_length_modulation_per_v": .01, "body_effect_sqrt_v": .4,
                     "surface_potential_v": .6, "width_over_length": 1.,
                     "junction_saturation_current_a": 1e-14, "junction_emission_coefficient": 1.,
                     "cgs_f": 1e-12, "cgd_f": 1e-12, "cds_f": 0.,
                     "cgb_f": 1e-12, "cbd_f": 1e-12, "cbs_f": 1e-12},
        "limitations": ["NMOS Level-1 core plus explicit B-to-D and B-to-S Shockley diodes.",
                        "Constant capacitances; no depletion-capacitance law, reverse recovery or avalanche.",
                        "Core body threshold clamps forward body bias; added junctions do not repair that approximation."],
    },
    "npn4": {
        "name": "NPN with explicit collector-substrate junction",
        "pins": ["C", "B", "E", "SUB"],
        "defaults": {"saturation_current_a": 1e-15, "forward_beta": 99., "reverse_beta": 1.,
                     "emission_coefficient": 1., "cbe_f": 1e-12, "cbc_f": 1e-12,
                     "forward_transit_time_s": 0., "reverse_transit_time_s": 0.,
                     "junction_saturation_current_a": 1e-14, "junction_emission_coefficient": 1.,
                     "csub_f": 1e-12},
        "limitations": ["Three-terminal NPN Ebers-Moll core plus SUB-anode/C-cathode diode and constant capacitor.",
                        "Not a production four-terminal BJT or BiCMOS process model; no substrate transport or latch-up.",
                        "No Early effect, high injection, avalanche, voltage-dependent capacitance or thermal feedback."],
    },
    "resistor3": {
        "name": "Resistor with substrate coupling",
        "pins": ["P", "N", "SUB"],
        "defaults": {"resistance_ohm": 1000., "substrate_capacitance_f": 1e-12,
                     "substrate_leakage_resistance_ohm": 1e12},
        "limitations": ["Two equal body resistors; one midpoint capacitance and leakage resistance to SUB.",
                        "Not a distributed resistor or a semiconductor substrate model."],
    },
    "feedthrough_capacitor3": {
        "name": "Feedthrough capacitor",
        "pins": ["IN", "OUT", "GND"],
        "defaults": {"series_resistance_ohm": .01, "series_inductance_h": 1e-9,
                     "capacitance_f": 1e-9},
        "limitations": ["Series R then L from IN to OUT, with capacitance from their midpoint to GND.",
                        "Asymmetric lumped approximation; no package resonance, distributed geometry or EMI qualification."],
    },
    "kelvin_shunt4": {
        "name": "Four-terminal Kelvin shunt",
        "pins": ["FP", "FN", "SP", "SN"],
        "defaults": {"resistance_ohm": .01, "contact_resistance_ohm": .001},
        "limitations": ["Reuses the original passive model: contact resistors and a sense-node body resistor.",
                        "Sense current loading is modeled, but thermoelectric offset and self-heating are absent."],
    },
}


def catalog() -> list[dict[str, Any]]:
    """Return independent, JSON-compatible descriptors and SI defaults."""
    return [dict(deepcopy(value), id=kind, symbol_id=_SYMBOLS[kind], backend="native",
                 supported_analyses=["op", "transient_be", "transient_bdf2"],
                 model_status="generic_unqualified",
                 limitations=[*_COMMON, *value["limitations"]])
            for kind, value in _CATALOG.items()]


def _bounds(key: str) -> tuple[float, float]:
    if key.endswith("_f"):
        return (1e-18 if key == "capacitance_f" else 0.), 1.
    if key.endswith("_h"):
        return 0., 1000.
    if key.endswith("_ohm"):
        return (0. if key == "contact_resistance_ohm" else 1e-9), 1e15
    if key.endswith("_time_s"):
        return 0., 1.
    if key.endswith("saturation_current_a"):
        return 1e-30, 1.
    if key.endswith("emission_coefficient"):
        return .1, 10.
    if key.endswith("_beta"):
        return .01, 1e6
    return {"threshold_voltage_v": (-100., 100.),
            "transconductance_a_per_v2": (1e-12, 1e6),
            "channel_length_modulation_per_v": (0., 100.),
            "body_effect_sqrt_v": (0., 100.),
            "surface_potential_v": (1e-6, 100.),
            "width_over_length": (1e-6, 1e6)}[key]


def build(kind: str, parameters: Mapping[str, float] | None = None,
          name: str = "SPK_LUMPED") -> dict[str, Any]:
    """Build inert native-ready .subckt source, never execute or switch backend.

    Parameters use SI units. Unknown keys, booleans, strings, nonfinite values
    and values outside bounded numerical admission ranges fail closed.
    """
    if not isinstance(kind, str) or kind not in _CATALOG:
        raise ValueError("Unknown lumped physics part kind")
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) is None:
        raise ValueError("name must be an ASCII identifier of at most 64 characters")
    if parameters is not None and not isinstance(parameters, Mapping):
        raise ValueError("parameters must be a mapping")
    descriptor = next(item for item in catalog() if item["id"] == kind)
    p = dict(descriptor["defaults"])
    supplied = {} if parameters is None else parameters
    if any(key not in p for key in supplied):
        raise ValueError("Unknown parameters for " + kind)
    p.update(supplied)
    for key, value in p.items():
        if isinstance(value, (bool, str, bytes)):
            raise ValueError(key + " must be a finite SI number")
        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(key + " must be a finite SI number") from exc
        low, high = _bounds(key)
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"{key} must lie in [{low:g}, {high:g}] SI")
        p[key] = number
    lines = ["* Original SPIKE generic unqualified lumped model",
             f".subckt {name} {' '.join(descriptor['pins'])}"]

    def element(label: str, nodes: str, key: str) -> None:
        if p[key] != 0:
            lines.append(f"{label} {nodes} {p[key]:.17g}")

    def model(label: str, family: str, bindings: dict[str, str]) -> None:
        fields = " ".join(f"{spice}={p[key]:.17g}" for spice, key in bindings.items())
        lines.append(f".model {label} {family}({fields})")

    if kind in {"nmos4", "npn4"}:
        model("JUNCTION", "D", {"IS": "junction_saturation_current_a", "N": "junction_emission_coefficient"})
    if kind == "nmos4":
        model("CORE", "NMOS", {"VTO": "threshold_voltage_v", "KP": "transconductance_a_per_v2",
              "LAMBDA": "channel_length_modulation_per_v", "GAMMA": "body_effect_sqrt_v",
              "PHI": "surface_potential_v", "CGS": "cgs_f", "CGD": "cgd_f", "CDS": "cds_f"})
        # Exact zero-volt port link keeps primitive endpoints distinct even
        # when the caller ties bulk to source. It adds no invented resistance.
        lines.extend(("VBULK BULK B 0", f"MCORE D G S BULK CORE W={p['width_over_length']:.17g} L=1",
                      "DBD BULK D JUNCTION", "DBS BULK S JUNCTION"))
        for label, nodes, key in (("CGB", "G BULK", "cgb_f"), ("CBD", "BULK D", "cbd_f"), ("CBS", "BULK S", "cbs_f")):
            element(label, nodes, key)
    elif kind == "npn4":
        model("CORE", "NPN", {"IS": "saturation_current_a", "BF": "forward_beta",
              "BR": "reverse_beta", "NF": "emission_coefficient", "CBE": "cbe_f", "CBC": "cbc_f",
              "TF": "forward_transit_time_s", "TR": "reverse_transit_time_s"})
        lines.extend(("VSUB SUBSTRATE SUB 0", "QCORE C B E CORE", "DSUB SUBSTRATE C JUNCTION"))
        element("CSUB", "SUBSTRATE C", "csub_f")
    elif kind == "resistor3":
        lines.extend((f"RLEFT P MID {p['resistance_ohm']/2:.17g}",
                      f"RRIGHT MID N {p['resistance_ohm']/2:.17g}"))
        element("CSUB", "MID SUB", "substrate_capacitance_f")
        element("RLEAK", "MID SUB", "substrate_leakage_resistance_ohm")
    elif kind == "feedthrough_capacitor3":
        element("RSER", "IN MID", "series_resistance_ohm")
        if p["series_inductance_h"]:
            element("LSER", "MID OUT", "series_inductance_h")
        else:
            lines.append("VLINK MID OUT 0")
        element("CBODY", "MID GND", "capacitance_f")
    else:
        lines = build_model("kelvin_shunt", p["resistance_ohm"], name=name,
                            contact_resistance_ohm=p["contact_resistance_ohm"])["source"].rstrip().splitlines()[:-1]
    lines.append(f".ends {name}")
    return dict(descriptor, kind=kind, name=name, parameters=p, source="\n".join(lines) + "\n")
