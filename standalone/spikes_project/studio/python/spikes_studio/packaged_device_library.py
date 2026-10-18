# SPDX-License-Identifier: Apache-2.0
"""Studio adapter for established lumped cores with explicit package parasitics."""

from __future__ import annotations

from copy import deepcopy
import re

from python.spikes.device_parasitics import compose_device_parasitics
from python.spikes.lumped_physics_parts import build as build_core
from python.spikes.lumped_physics_parts import catalog as core_catalog


MODEL_TYPE = "packaged_lumped_device_v1"
CATEGORY = "Physics models"
ORIGIN = (
    "python.spikes.lumped_physics_parts + "
    "python.spikes.device_parasitics established composition"
)
PACKAGE_PARAMETERS = {
    "series_resistance_ohm": 0.01,
    "series_inductance_h": 1e-9,
    "parallel_capacitance_f": 0.0,
}
_PROFILES = {
    "nmos4": {
        "id": "physics.packaged.nmos4",
        "family": "packaged_nmos4",
        "name": "Packaged generic NMOS · uniform active-lead R/L",
        "primary_parameter": "series_inductance_h",
        "parameter_unit": "H",
        "active_pins": ("D", "G", "S"),
        "shunt_pair": ("G", "S"),
        "fourth_pin": "B",
        "roles": ("terminal", "control", "terminal", "bulk"),
        "sides": ("east", "west", "east", "east"),
    },
    "npn4": {
        "id": "physics.packaged.npn4",
        "family": "packaged_npn4",
        "name": "Packaged generic NPN · uniform active-lead R/L",
        "primary_parameter": "series_inductance_h",
        "parameter_unit": "H",
        "active_pins": ("C", "B", "E"),
        "shunt_pair": ("B", "E"),
        "fourth_pin": "SUB",
        "roles": ("terminal", "control", "terminal", "substrate"),
        "sides": ("east", "west", "east", "east"),
    },
}


def _cores():
    return {descriptor["id"]: descriptor for descriptor in core_catalog()}


def records():
    """Return two independent records composed only from established builders."""
    result = []
    cores = _cores()
    for core_kind, profile in _PROFILES.items():
        core = cores[core_kind]
        parameters = deepcopy(core["defaults"])
        parameters.update(PACKAGE_PARAMETERS)
        topology = (
            f"Package R/L is applied uniformly to {', '.join(profile['active_pins'])}; "
            f"{profile['fourth_pin']} uses an exact zero-volt link. Optional package capacitance "
            f"is placed across {'-'.join(profile['shunt_pair'])}."
        )
        result.append({
            "id": profile["id"],
            "category": CATEGORY,
            "family": profile["family"],
            "name": profile["name"],
            "parameters": parameters,
            "primary_parameter": profile["primary_parameter"],
            "parameter_unit": profile["parameter_unit"],
            "model_type": MODEL_TYPE,
            "builder_kind": profile["family"],
            "core_builder_kind": core_kind,
            "package_builder": "device_parasitics",
            "pins": deepcopy(core["pins"]),
            "symbol_id": core["symbol_id"],
            "status": "native_subcircuit",
            "model_status": "generic_unqualified",
            "backend": "native",
            "supported_analyses": deepcopy(core["supported_analyses"]),
            "manufacturer": None,
            "fidelity": "generic_reduced_order",
            "license": "Apache-2.0 original SPIKES contribution",
            "qualification": "generic_unqualified",
            "origin": ORIGIN,
            "limitations": (
                "Model status: generic_unqualified. Defaults are illustrative inputs, not inferred "
                "package properties. " + topology + " " + " ".join(core["limitations"]) +
                " Avoid double counting capacitance already present in the core. Mutual coupling, "
                "self-heating, distributed package behavior, and vendor qualification are absent."
            ),
        })
    return result


def _model_name(record):
    name = "SPK_" + re.sub(r"[^A-Za-z0-9_]", "_", record.get("id", ""))
    if len(name) > 59:
        raise ValueError("Packaged device model identity is too long")
    return name


def validate_record(record):
    """Validate metadata, then delegate numeric admission to both source builders."""
    if not isinstance(record, dict) or record.get("model_type") != MODEL_TYPE:
        raise ValueError("Invalid packaged device library record")
    core_kind = record.get("core_builder_kind")
    profile = _PROFILES.get(core_kind)
    core = _cores().get(core_kind)
    if profile is None or core is None:
        raise ValueError("Unknown packaged device core builder")
    exact = {
        "id": profile["id"], "category": CATEGORY, "family": profile["family"],
        "builder_kind": profile["family"], "core_builder_kind": core_kind,
        "package_builder": "device_parasitics", "primary_parameter": profile["primary_parameter"],
        "parameter_unit": profile["parameter_unit"], "pins": core["pins"],
        "symbol_id": core["symbol_id"], "status": "native_subcircuit",
        "model_status": "generic_unqualified", "backend": "native",
        "supported_analyses": core["supported_analyses"], "manufacturer": None,
        "fidelity": "generic_reduced_order", "qualification": "generic_unqualified",
        "origin": ORIGIN,
    }
    if any(record.get(key) != value for key, value in exact.items()):
        raise ValueError("Packaged device metadata does not match its established builders")
    if not isinstance(record.get("name"), str) or not 1 <= len(record["name"]) <= 160:
        raise ValueError("Invalid packaged device display name")
    if not isinstance(record.get("limitations"), str) or "unqualified" not in record["limitations"].casefold():
        raise ValueError("Packaged device limitations must retain unqualified status")
    parameters = record.get("parameters")
    expected = set(core["defaults"]) | set(PACKAGE_PARAMETERS)
    if not isinstance(parameters, dict) or set(parameters) != expected:
        raise ValueError("Packaged device parameters must exactly match the core and package contract")
    core_parameters = {key: parameters[key] for key in core["defaults"]}
    build_core(core_kind, core_parameters, name=_model_name(record) + "_CORE")
    _compose(record, profile, core_parameters)


def _compose(record, profile, core_parameters):
    name = _model_name(record)
    core_name = name + "_CORE"
    core = build_core(record["core_builder_kind"], core_parameters, name=core_name)
    resistance = record["parameters"]["series_resistance_ohm"]
    inductance = record["parameters"]["series_inductance_h"]
    capacitance = record["parameters"]["parallel_capacitance_f"]
    pin_parasitics = {
        pin: {"resistance_ohm": resistance, "inductance_h": inductance}
        for pin in profile["active_pins"]
    }
    between = [{"pins": list(profile["shunt_pair"]), "capacitance_f": capacitance}]
    package = compose_device_parasitics(
        core_name, core["pins"], name=name, pin_parasitics=pin_parasitics,
        between_pin_parasitics=between,
    )
    package["source"] = core["source"] + package["source"]
    package["core"] = core
    return package


def model(record):
    validate_record(record)
    core = _cores()[record["core_builder_kind"]]
    core_parameters = {key: record["parameters"][key] for key in core["defaults"]}
    return _compose(record, _PROFILES[record["core_builder_kind"]], core_parameters)


def primary_value(record):
    validate_record(record)
    return record["parameters"][record["primary_parameter"]]


def pin_contract(record):
    validate_record(record)
    profile = _PROFILES[record["core_builder_kind"]]
    return {
        "pins": [
            {"number": str(index + 1), "name": name,
             "role": profile["roles"][index], "side": profile["sides"][index]}
            for index, name in enumerate(record["pins"])
        ],
        "numbering": "Established core terminal order; NOT a manufacturer package pinout",
        "execution": record["status"],
        "power_behavior": (
            "Native generic_unqualified core plus explicit uniform active-lead package R/L; "
            "the fourth terminal is exact-linked."
        ),
    }


def evaluate(record, inputs=None, state=None, dt=1e-4):
    validate_record(record)
    raise ValueError("Packaged devices execute only after native circuit placement; Equation bench is unavailable")


__all__ = ["CATEGORY", "MODEL_TYPE", "ORIGIN", "model", "pin_contract", "primary_value", "records", "validate_record"]
