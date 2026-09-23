"""Regenerate published SI setup schemas and the UI default snapshot."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.si_workflow import SOURCE, RECEIVER, workflow_catalog
from python.spike_core.si_passives import passive_defaults, CAPACITOR_GRADES, RESISTOR_GRADES


def obj(properties, required=()):
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(required)}


def numeric_defaults(defaults):
    return {k: {"type": "number", "default": v} for k, v in defaults.items() if isinstance(v, (float, int))}


def build_schema():
    port = {"type": "integer", "minimum": 0, "maximum": 15}
    ibis = obj({"text": {"type": "string", "maxLength": 8_000_000}, "name": {"type": "string"},
                "model": {"type": "string", "minLength": 1}, "component": {"type": "string"}, "pin": {"type": "string"},
                "corner": {"enum": ["typ", "min", "max"]}, "state": {"enum": ["low", "high"]},
                "operating_voltage_v": {"type": "number"}}, ["text", "model"])
    source = obj({**numeric_defaults(SOURCE), "port": port, "ibis": ibis}, ["port"])
    receiver = obj({**numeric_defaults(RECEIVER), "port": port, "ibis": ibis}, ["port"])
    for endpoint in (source, receiver):
        endpoint["properties"]["resistance_ohm"].update(minimum=1e-6, maximum=1e12)
        for key in ["capacitance_f", "package_r_ohm", "package_l_h", "package_c_f"]:
            endpoint["properties"][key]["minimum"] = 0
    source["properties"]["pattern_shift_bits"].update(type="integer", minimum=0, maximum=126)
    passive_models = []
    for kind, grades in [("resistor", RESISTOR_GRADES), ("capacitor", CAPACITOR_GRADES)]:
        properties = numeric_defaults(passive_defaults(kind))
        properties.update(kind={"const": kind}, grade={"enum": list(grades)}, corner={"enum": ["nominal", "min", "max"]})
        properties["tolerance_fraction"].update(minimum=0, maximum=0.99)
        passive_models.append(obj(properties, ["kind"] if kind == "capacitor" else []))
    line = obj({**numeric_defaults(workflow_catalog()["defaults"]["channel"]),
                "kind": {"const": "rlgc"}, "coupled": {"type": "boolean", "default": True}})
    line["properties"]["frequency_points"].update(type="integer", minimum=3, maximum=8193)
    for key in ["length_m", "inductance_h_per_m", "capacitance_f_per_m", "reference_impedance_ohm", "frequency_stop_hz"]:
        line["properties"][key]["exclusiveMinimum"] = 0
    touchstone = obj({"kind": {"const": "touchstone"}, "name": {"type": "string", "pattern": "\\.s[0-9]+p$"},
                      "text": {"type": "string", "maxLength": 32_000_000}}, ["kind", "text"])
    geometry = obj({"kind": {"const": "geometry"}, "request": {"$ref": "si-uniform-channel-request-v1.schema.json"}}, ["kind", "request"])
    edits = [obj({"kind": {"const": "renormalize"}, "reference_impedance_ohm": {"type": "number", "minimum": 0.01, "maximum": 1e6}}, ["kind", "reference_impedance_ohm"]),
             obj({"kind": {"const": "reorder"}, "ports": {"type": "array", "items": port, "minItems": 2, "maxItems": 16, "uniqueItems": True}}, ["kind", "ports"]),
             obj({"kind": {"const": "port_extension"}, "delay_s": {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1e-3}, "minItems": 2, "maxItems": 16}}, ["kind", "delay_s"]),
             obj({"kind": {"const": "cascade"}, "channel": {"oneOf": [line, touchstone]}}, ["kind", "channel"])]
    return {"$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://spike.local/schemas/si-workflow-request-v1.schema.json",
            "title": "SPIKE experimental source-to-receiver SI workflow",
            **obj({"contract": {"const": "spike/si-workflow-request/v1"}, "channel": {"oneOf": [line, touchstone, geometry]},
                   "sources": {"type": "array", "items": source, "minItems": 1, "maxItems": 16},
                   "receivers": {"type": "array", "items": receiver, "minItems": 1, "maxItems": 16},
                   "passives": {"type": "array", "maxItems": 64, "items": obj({"id": {"type": "string"}, "port": port,
                      "connection": {"enum": ["series", "shunt"]}, "model": {"oneOf": passive_models}}, ["port"])},
                   "edits": {"type": "array", "maxItems": 32, "items": {"oneOf": edits}},
                   "temperature_c": {"type": "number", "minimum": -273.14, "maximum": 500},
                   "bit_rate_hz": {"type": "number", "minimum": 1, "maximum": 1e14},
                   "bit_count": {"type": "integer", "minimum": 128, "maximum": 2048},
                   "run_time_domain": {"type": "boolean"}, "export_format": {"enum": ["RI", "MA", "DB"]}}, ["contract"])}


if __name__ == "__main__":
    outputs = {"schemas/si-workflow-request-v1.schema.json": build_schema(), "app/src/siWorkflowCatalog.json": workflow_catalog()}
    for path, value in outputs.items():
        (ROOT / path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
