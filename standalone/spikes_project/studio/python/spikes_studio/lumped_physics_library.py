# SPDX-License-Identifier: Apache-2.0
"""Studio catalog adapter for the established generic lumped-part builders."""

from __future__ import annotations

from copy import deepcopy
import re

from python.spikes.lumped_physics_parts import build, catalog as source_catalog


MODEL_TYPE = "lumped_physics_part_v1"
CATEGORY = "Physics models"
_PRIMARY = {
    "nmos4": ("threshold_voltage_v", "V"),
    "npn4": ("forward_beta", "1"),
    "resistor3": ("resistance_ohm", "ohm"),
    "feedthrough_capacitor3": ("capacitance_f", "F"),
    "kelvin_shunt4": ("resistance_ohm", "ohm"),
}
_SIDES = {
    "nmos4": ("east", "west", "east", "east"),
    "npn4": ("east", "west", "east", "east"),
    "resistor3": ("west", "east", "east"),
    "feedthrough_capacitor3": ("west", "east", "east"),
    "kelvin_shunt4": ("west", "east", "west", "east"),
}
_ROLES = {
    "nmos4": ("terminal", "control", "terminal", "bulk"),
    "npn4": ("terminal", "control", "terminal", "substrate"),
    "resistor3": ("terminal", "terminal", "substrate"),
    "feedthrough_capacitor3": ("terminal", "terminal", "reference"),
    "kelvin_shunt4": ("force", "force", "sense", "sense"),
}


def _source_by_kind():
    return {descriptor["id"]: descriptor for descriptor in source_catalog()}


def records():
    """Return five independent Studio records backed by existing builders."""
    result = []
    for descriptor in source_catalog():
        kind = descriptor["id"]
        primary, unit = _PRIMARY[kind]
        limitations = "Model status: generic_unqualified. " + " ".join(descriptor["limitations"])
        result.append({
            "id": "physics.lumped." + kind,
            "category": CATEGORY,
            "family": kind,
            "name": descriptor["name"],
            "parameters": deepcopy(descriptor["defaults"]),
            "primary_parameter": primary,
            "parameter_unit": unit,
            "model_type": MODEL_TYPE,
            "builder_kind": kind,
            "pins": deepcopy(descriptor["pins"]),
            "symbol_id": descriptor["symbol_id"],
            "status": "native_subcircuit",
            "model_status": descriptor["model_status"],
            "backend": descriptor["backend"],
            "supported_analyses": deepcopy(descriptor["supported_analyses"]),
            "manufacturer": None,
            "fidelity": "generic_reduced_order",
            "license": "Apache-2.0 original SPIKE contribution",
            "qualification": "generic_unqualified",
            "origin": "python.spikes.lumped_physics_parts established builder",
            "limitations": limitations,
        })
    return result


def validate_record(record):
    """Validate Studio metadata and delegate every numerical bound to build()."""
    if not isinstance(record, dict) or record.get("model_type") != MODEL_TYPE:
        raise ValueError("Invalid lumped physics library record")
    kind = record.get("builder_kind")
    descriptor = _source_by_kind().get(kind)
    if descriptor is None:
        raise ValueError("Unknown lumped physics builder")
    expected_id = "physics.lumped." + kind
    primary, unit = _PRIMARY[kind]
    exact = {
        "id": expected_id,
        "category": CATEGORY,
        "family": kind,
        "primary_parameter": primary,
        "parameter_unit": unit,
        "symbol_id": descriptor["symbol_id"],
        "status": "native_subcircuit",
        "model_status": "generic_unqualified",
        "backend": "native",
        "qualification": "generic_unqualified",
        "fidelity": "generic_reduced_order",
        "manufacturer": None,
    }
    if any(record.get(key) != value for key, value in exact.items()):
        raise ValueError("Lumped physics catalog metadata does not match its established builder")
    if record.get("supported_analyses") != descriptor["supported_analyses"]:
        raise ValueError("Lumped physics analysis claims do not match the established builder")
    if record.get("pins") != descriptor["pins"]:
        raise ValueError("Lumped physics published pins do not match the established builder")
    if not isinstance(record.get("name"), str) or not 1 <= len(record["name"]) <= 160:
        raise ValueError("Invalid lumped physics display name")
    if not isinstance(record.get("limitations"), str) or "unqualified" not in record["limitations"].casefold():
        raise ValueError("Lumped physics limitations must retain unqualified status")
    parameters = record.get("parameters")
    if not isinstance(parameters, dict) or primary not in parameters:
        raise ValueError("Lumped physics primary parameter is missing")
    built = build(kind, parameters, name=_model_name(record))
    if tuple(built["pins"]) != tuple(descriptor["pins"]):
        raise ValueError("Lumped physics pin order drifted from its established builder")


def _model_name(record):
    ident = record.get("id", "")
    name = "SPK_" + re.sub(r"[^A-Za-z0-9_]", "_", ident)
    if len(name) > 64:
        raise ValueError("Lumped physics model identity is too long")
    return name


def model(record):
    validate_record(record)
    return build(record["builder_kind"], record["parameters"], name=_model_name(record))


def primary_value(record):
    validate_record(record)
    return record["parameters"][record["primary_parameter"]]


def pin_contract(record):
    """Return ordered logical terminals for preview; never package pin numbers."""
    validate_record(record)
    built = model(record)
    kind = record["builder_kind"]
    pins = [
        {"number": str(index + 1), "name": name, "role": _ROLES[kind][index], "side": _SIDES[kind][index]}
        for index, name in enumerate(built["pins"])
    ]
    return {
        "pins": pins,
        "numbering": "Established builder terminal order; NOT a manufacturer package pinout",
        "execution": record["status"],
        "power_behavior": "Native generic lumped subcircuit; generic_unqualified and without self-heating.",
    }


def evaluate(record, inputs=None, state=None, dt=1e-4):
    validate_record(record)
    raise ValueError("Lumped physics parts execute only after native circuit placement; Equation bench is unavailable")
