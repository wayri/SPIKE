"""IBIS inventory and explicit small-signal endpoint reduction.

This is not an IBIS transient or AMI engine. It retains I/V, waveform, pin,
selector and package data and reports unsupported keywords. Only a selected
I/V operating point is reduced; switching tables are never silently simulated.
"""
from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Mapping

import numpy as np

from .si_passives import number

_VALUE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([TGMkmunpf]?)(?:[a-zA-Z]*)$")
_SCALE = {"": 1, "T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}
_TABLES = {"pullup", "pulldown", "gnd clamp", "power clamp", "rising waveform", "falling waveform"}


def ibis_number(token: str) -> float | None:
    if token.upper() == "NA":
        return None
    match = _VALUE.fullmatch(token)
    if not match:
        raise ValueError(f"Invalid IBIS numeric value {token!r}.")
    return number(float(match[1]) * _SCALE[match[2]], "IBIS number")


def parse_ibis(text: str, name: str = "model.ibs") -> dict[str, Any]:
    if not isinstance(text, str) or len(text) > 8_000_000:
        raise ValueError("IBIS text must be at most 8 MB.")
    models: dict[str, Any] = {}
    components: dict[str, Any] = {}
    selectors: dict[str, Any] = {}
    model = component = waveform = None
    section = selector = ""
    version = ""
    unsupported: set[str] = set()
    comment = "|"
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(comment, 1)[0].strip()
        if not line:
            continue
        keyword = re.match(r"^\[([^]]+)\]\s*(.*)$", line)
        try:
            if keyword:
                section = keyword[1].strip().lower().replace("_", " ")
                value = keyword[2].strip()
                if section == "comment char":
                    comment = value[0]
                elif section == "ibis ver":
                    version = value
                elif section == "component":
                    if value in components:
                        raise ValueError("Duplicate component name.")
                    component = {"name": value, "pins": [], "package": {}}
                    components[value] = component
                    model = None
                elif section == "model":
                    if value in models:
                        raise ValueError("Duplicate model name.")
                    model = {"name": value, "model_type": "", "parameters": {}, "tables": {}, "waveforms": [], "ramp": {}}
                    models[value] = model
                elif section == "model selector":
                    selector = value
                    selectors[selector] = []
                elif section in {"voltage range", "temperature range"} and model is not None:
                    model["parameters"][section.replace(" ", "_")] = [ibis_number(t) for t in value.split()]
                elif section in _TABLES and model is not None:
                    if "waveform" in section:
                        waveform = {"kind": section, "fixture": {}, "values": []}
                        model["waveforms"].append(waveform)
                    else:
                        model["tables"][section] = []
                elif section not in {"file name", "file rev", "date", "source", "notes", "disclaimer", "copyright", "manufacturer", "package", "pin", "ramp", "end"}:
                    unsupported.add(section)
                continue
            tokens = line.replace("=", " ").split()
            if section == "pin" and component is not None:
                if len(tokens) < 3:
                    raise ValueError("Pin row requires pin, signal and model.")
                component["pins"].append({"pin": tokens[0], "signal": tokens[1], "model": tokens[2],
                                          "rlc": [ibis_number(t) for t in tokens[3:6]]})
            elif section == "package" and component is not None:
                component["package"][tokens[0].lower()] = [ibis_number(t) for t in tokens[1:4]]
            elif section == "model selector":
                selectors[selector].append({"model": tokens[0], "description": " ".join(tokens[1:])})
            elif section in _TABLES and model is not None:
                if re.match(r"^[+\-.\d]", tokens[0]):
                    row = [ibis_number(t) for t in tokens]
                    if len(row) != 4 or row[0] is None or row[1] is None:
                        raise ValueError("IBIS table rows require axis, typ, min, max (NA allowed for corners).")
                    (waveform["values"] if "waveform" in section else model["tables"][section]).append(row)
                elif "waveform" in section:
                    waveform["fixture"][tokens[0].lower()] = [ibis_number(t) for t in tokens[1:]]
            elif section == "ramp" and model is not None:
                if tokens[0].lower() in {"dv/dt_r", "dv/dt_f"}:
                    ratios = []
                    for token in tokens[1:]:
                        if token.upper() == "NA":
                            ratios.append(None)
                        else:
                            v, t = token.split("/")
                            ratios.append([ibis_number(v), ibis_number(t)])
                    model["ramp"][tokens[0].lower()] = ratios
                elif tokens[0].lower() == "r_load":
                    model["ramp"]["r_load"] = ibis_number(tokens[1])
            elif section == "model" and model is not None:
                key = tokens[0].lower()
                if key in {"model_type", "polarity", "enable"}:
                    model[key] = tokens[1]
                elif key in {"c_comp", "vinl", "vinh", "vref", "rref", "cref", "vmeas"}:
                    model["parameters"][key] = [ibis_number(t) for t in tokens[1:]]
                else:
                    unsupported.add(f"model:{key}")
        except (ValueError, IndexError, TypeError) as exc:
            raise ValueError(f"IBIS line {line_number}: {exc}") from exc
    if not version or not models:
        raise ValueError("IBIS requires [IBIS Ver] and at least one [Model].")
    for item in models.values():
        for table in item["tables"].values():
            axis = [row[0] for row in table]
            if len(axis) < 2 or len(set(axis)) != len(axis):
                raise ValueError("I/V tables need at least two distinct voltages without duplicate rows.")
            table.sort(key=lambda row: row[0])
    return {"contract": "spike/si-ibis-inventory/v1", "name": name, "version": version,
            "sha256": sha256(text.encode("utf-8")).hexdigest(), "models": models,
            "components": components, "selectors": selectors, "unsupported_keywords": sorted(unsupported),
            "limitations": ["Inventory and selected DC operating-point linearization only; no nonlinear switching, IBIS-AMI or power-aware simulation."]}


def reduce_ibis(inventory: Mapping[str, Any], binding: Mapping[str, Any], role: str) -> dict[str, Any]:
    allowed = {"text", "name", "model", "component", "pin", "corner", "state", "operating_voltage_v"}
    if set(binding) - allowed:
        raise ValueError("Unknown IBIS binding fields.")
    model_name = binding.get("model")
    if model_name not in inventory["models"]:
        raise ValueError("Select an IBIS model explicitly.")
    model = inventory["models"][model_name]
    model_type = model["model_type"].lower()
    if model_type not in ({"output", "i/o", "3-state"} if role == "source" else {"input", "i/o"}):
        raise ValueError(f"IBIS {model_type!r} cannot be reduced as {role}.")
    # Unrecognized electrical extensions must not silently disappear in a model.
    electrical = [k for k in inventory["unsupported_keywords"] if k not in {"revision history"}]
    if electrical:
        raise ValueError(f"IBIS reduction does not support these keywords: {electrical}; inventory remains inspectable.")
    corner = binding.get("corner", "typ")
    if corner not in {"typ", "min", "max"}:
        raise ValueError("IBIS corner must be typ, min or max.")
    index = {"typ": 0, "min": 1, "max": 2}[corner]

    def selected(values, label, default=None):
        if values is None:
            if default is not None:
                return default
            raise ValueError(f"IBIS {label} is required.")
        if index >= len(values) or values[index] is None:
            raise ValueError(f"IBIS {label} has no {corner} value; choose another corner explicitly.")
        return values[index]

    params = model["parameters"]
    c = selected(params.get("c_comp"), "C_comp")
    number(c, "C_comp", 0)
    package = {"package_r_ohm": 0.0, "package_l_h": 0.0, "package_c_f": 0.0}
    component_name, pin_name = binding.get("component"), binding.get("pin")
    if bool(component_name) != bool(pin_name):
        raise ValueError("IBIS package binding requires both component and pin.")
    if component_name:
        comp = inventory["components"].get(component_name)
        if comp is None:
            raise ValueError("Unknown IBIS component.")
        matches = [p for p in comp["pins"] if p["pin"] == pin_name]
        if len(matches) != 1:
            raise ValueError("IBIS pin must resolve exactly once.")
        pin = matches[0]
        candidates = [s["model"] for s in inventory["selectors"].get(pin["model"], [])] or [pin["model"]]
        if model_name not in candidates:
            raise ValueError("Selected IBIS model is not assigned to that pin/model selector.")
        for i, (key, source) in enumerate(zip(package, ["r_pkg", "l_pkg", "c_pkg"])):
            pin_value = pin["rlc"][i] if i < len(pin["rlc"]) else None
            value = pin_value if pin_value is not None else selected(comp["package"].get(source), source)
            package[key] = number(value, source, 0)
    output = {"capacitance_f": c, **package}
    if role == "source":
        state = binding.get("state", "low")
        if state not in {"low", "high"}:
            raise ValueError("IBIS state must be low or high for linearization.")
        supply = selected(params.get("voltage_range"), "Voltage Range")
        number(supply, "IBIS supply", 1e-9)
        voltage = number(binding.get("operating_voltage_v", supply / 2), "operating_voltage_v", 0, supply)
        table = model["tables"].get("pulldown" if state == "low" else "pullup", [])
        x = voltage if state == "low" else supply - voltage
        if len(table) < 2 or not table[0][0] <= x <= table[-1][0]:
            raise ValueError("Selected operating point is outside the required IBIS I/V table.")
        i = min(max(int(np.searchsorted([row[0] for row in table], x)) - 1, 0), len(table) - 2)
        a, b = table[i:i + 2]
        ia, ib = selected(a[1:], "I/V"), selected(b[1:], "I/V")
        slope = (ib - ia) / (b[0] - a[0])
        # Pullup table current uses the opposite sign to pulldown current.
        conductance = slope if state == "low" else -slope
        if conductance <= 0:
            raise ValueError("IBIS operating point has no positive incremental output conductance.")
        output.update(resistance_ohm=1 / conductance, low_v=0.0, high_v=supply)
        for key, target in [("dv/dt_r", "rise_time_s"), ("dv/dt_f", "fall_time_s")]:
            v, t = selected(model["ramp"].get(key), key)
            number(v, "ramp voltage", 1e-12)
            number(t, "ramp time", 1e-15)
            output[target] = 0.8 * supply * t / v
    else:
        # Vinl/Vinh are scalar subparameters, not typ/min/max columns.
        output["vil_v"] = params.get("vinl", [0.8])[0]
        output["vih_v"] = params.get("vinh", [2.0])[0]
    return {"values": output, "model": model_name, "corner": corner,
            "sha256": inventory["sha256"], "binding": {k: v for k, v in binding.items() if k != "text"},
            "limitations": inventory["limitations"] + ["One fixed I/V slope and ramp-derived edge time approximate the endpoint across the swing; clamp and waveform tables are retained for inspection only."]}
