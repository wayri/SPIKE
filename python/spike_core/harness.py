"""Portable harness authoring, connection-list ingestion and circuit compilation.

All lengths are mm, areas mm² and electrical quantities SI. Connectivity is
topological; a circuit is emitted only from explicit or dimensionally complete
material data. A graph edge never implies a return path, shield or coupling.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
from pathlib import Path

CONTRACT = "spike/harness/v1"
MAX_BYTES = 64 * 1024 * 1024
MAX_OBJECTS = 100_000


def _finite(value, label, *, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{label} must be a finite number >= {minimum}.")
    return float(value)


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be a nonempty printable string.")
    return value


def validate_harness(raw):
    """Return an independent canonical document, rejecting dangling references."""
    if not isinstance(raw, dict) or raw.get("contract") != CONTRACT:
        raise ValueError(f"Harness contract must be {CONTRACT}.")
    allowed = {"contract", "id", "name", "connectors", "splices", "wires", "cables", "routes", "properties", "provenance", "extensions"}
    if set(raw) - allowed:
        raise ValueError("Unknown harness fields; retain vendor data under properties or extensions.")
    data = copy.deepcopy(raw)
    _identifier(data.get("id"), "harness.id")
    _identifier(data.get("name"), "harness.name")
    # Schema validates shapes; semantic checks below enforce unique identities
    # and graph relationships JSON Schema cannot express.
    from jsonschema import Draft202012Validator
    schema_path = Path(__file__).resolve().parents[2] / "schemas/harness-v1.schema.json"
    errors = sorted(Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).iter_errors(data), key=lambda e: str(e.path))
    if errors:
        raise ValueError(f"Invalid harness at {list(errors[0].path)}: {errors[0].message}")
    json.dumps(data, allow_nan=False)
    tables = {}
    for kind in ("connectors", "splices", "wires", "cables", "routes"):
        rows = data.setdefault(kind, [])
        if len(rows) > MAX_OBJECTS:
            raise ValueError("Harness object count limit exceeded.")
        table = {}
        for row in rows:
            key = _identifier(row.get("id"), kind + ".id")
            if key in table:
                raise ValueError(f"Duplicate {kind} ID: {key}")
            table[key] = row
        tables[kind] = table
    for connector in data["connectors"]:
        pins = [p["id"] for p in connector["pins"]]
        if len(pins) != len(set(pins)):
            raise ValueError(f"Duplicate pin in connector {connector['id']}.")
    def endpoint(end):
        if "splice" in end:
            if end["splice"] not in tables["splices"]:
                raise ValueError("Wire references unknown splice.")
        else:
            connector = tables["connectors"].get(end["connector"])
            if connector is None or end["pin"] not in {p["id"] for p in connector["pins"]}:
                raise ValueError("Wire references unknown connector or pin.")
    for wire in data["wires"]:
        endpoint(wire["from"]); endpoint(wire["to"])
        if terminal_key(wire["from"]) == terminal_key(wire["to"]):
            raise ValueError(f"Wire {wire['id']} connects a terminal to itself.")
        for key in ("length_mm", "area_mm2"):
            if key in wire: _finite(wire[key], key, minimum=1e-12)
        model = wire.get("electrical", {})
        for key, value in model.items():
            if key not in {"reference", "provenance", "extensions"}: _finite(value, key)
        if "reference" in model: endpoint(model["reference"])
        material = wire.get("material", {})
        if "resistivity_ohm_m" in material: _finite(material["resistivity_ohm_m"], "resistivity", minimum=1e-30)
        if "route_id" in wire and wire["route_id"] not in tables["routes"]:
            raise ValueError("Wire references unknown route.")
    memberships = set()
    for cable in data["cables"]:
        for wire in cable["wire_ids"]:
            if wire not in tables["wires"] or wire in memberships:
                raise ValueError("Cable has unknown or multiply assigned wire.")
            memberships.add(wire)
        shield = cable.get("shield")
        if shield:
            for end in shield.get("terminations", []): endpoint(end)
    for route in data["routes"]:
        for point in route["points_mm"]:
            for coordinate in point:
                _finite(coordinate, "route coordinate", minimum=-1e9)
    return data


def terminal_key(end):
    # JSON tuple encoding is collision-free even when IDs contain punctuation.
    return json.dumps(["splice", end["splice"]] if "splice" in end else ["connector", end["connector"], end["pin"]], separators=(",", ":"))


def analyze_harness(raw):
    data = validate_harness(raw)
    parent, wires_at = {}, {}
    labels = {}
    def find(key):
        parent.setdefault(key, key)
        root = key
        while parent[root] != root: root = parent[root]
        while parent[key] != key:
            key, parent[key] = parent[key], root
        return root
    for connector in data["connectors"]:
        for pin in connector["pins"]:
            key = terminal_key({"connector": connector["id"], "pin": pin["id"]})
            find(key)
            if pin.get("net"): labels.setdefault(key, set()).add(pin["net"])
    for splice in data["splices"]: find(terminal_key({"splice": splice["id"]}))
    issues = []
    total_length = 0
    unknown_lengths = []
    routes = {r["id"]: r for r in data["routes"]}
    for wire in data["wires"]:
        a, b = terminal_key(wire["from"]), terminal_key(wire["to"])
        parent[find(a)] = find(b)
        for end in (a, b):
            wires_at.setdefault(end, []).append(wire["id"])
            if wire.get("net"): labels.setdefault(end, set()).add(wire["net"])
        if "length_mm" in wire: total_length += wire["length_mm"]
        else: unknown_lengths.append(wire["id"])
        if "route_id" in wire and "length_mm" in wire:
            points = routes[wire["route_id"]]["points_mm"]
            route_length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            if wire["length_mm"] + 1e-6 < route_length:
                issues.append({"code": "HARNESS_LENGTH_TOO_SHORT", "severity": "error", "id": wire["id"], "message": "Cut length is shorter than the assigned route."})
    groups = {}
    for key in parent:
        group = groups.setdefault(find(key), {"terminals": [], "nets": set(), "wire_ids": set()})
        group["terminals"].append(json.loads(key))
        group["nets"].update(labels.get(key, set()))
        group["wire_ids"].update(wires_at.get(key, []))
    networks = []
    for root, group in sorted(groups.items()):
        nets = sorted(group["nets"])
        if len(nets) > 1:
            issues.append({"code": "HARNESS_NET_SHORT", "severity": "error", "id": root, "message": "Connected terminals declare different nets: " + ", ".join(nets)})
        networks.append({"terminals": sorted(group["terminals"]), "nets": nets, "wire_ids": sorted(group["wire_ids"])})
    for connector in data["connectors"]:
        for pin in connector["pins"]:
            key = terminal_key({"connector": connector["id"], "pin": pin["id"]})
            count = len(wires_at.get(key, []))
            if count > pin.get("max_connections", 1):
                issues.append({"code": "HARNESS_TERMINAL_CAPACITY", "severity": "error", "id": key, "message": "Terminal connection capacity exceeded; use an explicit splice."})
            if pin.get("required", False) and count == 0:
                issues.append({"code": "HARNESS_OPEN_TERMINAL", "severity": "error", "id": key, "message": "Required connector terminal is unconnected."})
    for splice in data["splices"]:
        key = terminal_key({"splice": splice["id"]})
        if len(wires_at.get(key, [])) < 2:
            issues.append({"code": "HARNESS_DANGLING_SPLICE", "severity": "error", "id": key, "message": "Splice needs at least two wires."})
    return {"contract": "spike/harness-analysis/v1", "status": "invalid" if issues else "valid", "networks": networks,
            "issues": issues, "bom": {"wires": len(data["wires"]), "connectors": len(data["connectors"]),
            "splices": len(data["splices"]), "known_cut_length_mm": total_length, "unknown_length_wire_ids": unknown_lengths},
            "harness_digest": hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def compile_harness(raw):
    data = validate_harness(raw)
    report = analyze_harness(data)
    if report["status"] != "valid":
        raise ValueError("Harness connectivity validation failed: " + "; ".join(i["message"] for i in report["issues"]))
    elements, unresolved = [], []
    for wire in data["wires"]:
        model = wire.get("electrical", {})
        resistance = model.get("resistance_ohm")
        provenance = "explicit"
        if resistance is None:
            material = wire.get("material", {})
            if all(k in wire for k in ("length_mm", "area_mm2")) and "resistivity_ohm_m" in material:
                resistance = material["resistivity_ohm_m"] * wire["length_mm"] * 1000 / wire["area_mm2"]
                provenance = "rho_length_over_area_at_material_reference_temperature"
        if resistance is None:
            unresolved.append(wire["id"])
            continue
        if not math.isfinite(resistance) or resistance <= 0:
            raise ValueError(f"Wire {wire['id']} resistance is outside the finite positive numerical range.")
        a, b = terminal_key(wire["from"]), terminal_key(wire["to"])
        wire_id = json.dumps(["wire", wire["id"]], separators=(",", ":"))
        series = wire_id if model.get("inductance_h", 0) > 0 else b
        elements.append({"id": wire_id + ":R", "type": "resistor", "positive_node": a, "negative_node": series,
                         "resistance_ohm": resistance, "wire_id": wire["id"], "provenance": provenance})
        if series != b:
            elements.append({"id": wire_id + ":L", "type": "inductor", "positive_node": series, "negative_node": b, "inductance_h": model["inductance_h"]})
        for key, kind in (("capacitance_to_reference_f", "capacitor"), ("conductance_to_reference_s", "conductance")):
            if model.get(key, 0) > 0:
                if "reference" not in model: raise ValueError(f"Wire {wire['id']} requires an explicit shunt reference.")
                reference = terminal_key(model["reference"])
                if reference in {a, b}: raise ValueError("Shunt reference cannot be a signal terminal.")
                elements.append({"id": wire_id + ":" + kind, "type": kind, "positive_node": series, "negative_node": reference, key: model[key]})
    if unresolved:
        raise ValueError("Electrical resistance is unresolved for wires: " + ", ".join(unresolved))
    return {"contract": "spike/harness-circuit/v1", "status": "compiled", "harness_digest": report["harness_digest"],
            "elements": elements, "model_status": "lumped_circuit_fragment", "production_qualified": False,
            "limitations": ["Return paths, connector contacts, shield impedance, mutual coupling and board ports require explicit models.",
                            "Material-derived resistance is at the supplied material reference temperature; no temperature correction is inferred."]}


CSV_REQUIRED = ("wire_id", "from_connector", "from_pin", "to_connector", "to_pin")
CSV_NUMERIC = ("length_mm", "area_mm2", "resistance_ohm", "inductance_h")


def import_harness(path, *, column_map=None, delimiter=None):
    source = Path(path)
    if source.stat().st_size > MAX_BYTES: raise ValueError("Harness source exceeds byte limit.")
    payload = source.read_bytes()
    text = payload.decode("utf-8-sig")
    if source.suffix.lower() == ".json" or text.lstrip().startswith("{"):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result: raise ValueError(f"Duplicate harness JSON key: {key}")
                result[key] = value
            return result
        return validate_harness(json.loads(text, object_pairs_hook=unique))
    delimiter = delimiter or ("\t" if source.suffix.lower() == ".tsv" else ",")
    if delimiter not in {",", ";", "\t", "|"}: raise ValueError("Unsupported connection-list delimiter.")
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)): raise ValueError("Duplicate connection-list columns.")
    mapping = column_map or {h: h for h in headers}
    if not isinstance(mapping, dict) or len(set(mapping.values())) != len(mapping): raise ValueError("Column map must be one-to-one.")
    if set(mapping.values()) - set(headers) or not set(CSV_REQUIRED).issubset(mapping):
        raise ValueError("Connection list needs explicit from/to connector and pin columns and a wire ID.")
    connectors, wires = {}, []
    for line, raw in enumerate(reader, 2):
        if len(wires) >= MAX_OBJECTS or None in raw or any(v is None for v in raw.values()):
            raise ValueError(f"Malformed or oversized connection list at row {line}.")
        row = {key: raw[column].strip() for key, column in mapping.items()}
        for key in CSV_REQUIRED: _identifier(row[key], f"row {line} {key}")
        wire = {"id": row["wire_id"], "from": {"connector": row["from_connector"], "pin": row["from_pin"]},
                "to": {"connector": row["to_connector"], "pin": row["to_pin"]}, "properties": {"source_row": raw, "line": line}}
        for end in (wire["from"], wire["to"]):
            pins = connectors.setdefault(end["connector"], {})
            pins.setdefault(end["pin"], {"id": end["pin"]})
        for key in CSV_NUMERIC:
            if row.get(key):
                value = float(row[key])
                if key in {"resistance_ohm", "inductance_h"}: wire.setdefault("electrical", {})[key] = value
                else: wire[key] = value
        for key in ("net", "color", "part_number"):
            if row.get(key): wire[key] = row[key]
        wires.append(wire)
    if not wires: raise ValueError("Connection list has no wires.")
    return validate_harness({"contract": CONTRACT, "id": "harness-" + hashlib.sha256(payload).hexdigest()[:24], "name": source.stem,
                             "connectors": [{"id": key, "pins": list(pins.values())} for key, pins in connectors.items()], "wires": wires,
                             "provenance": {"source_name": source.name, "sha256": hashlib.sha256(payload).hexdigest(), "column_map": mapping, "delimiter": delimiter}})


def export_harness(raw):
    return json.dumps(validate_harness(raw), indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def compile_multiboard_harness(raw, multiboard_request):
    """Bind a point-to-point harness to the existing assembly circuit compiler.

    Connector board bindings and the assembly harness pin map must agree exactly.
    Branch/splice networks remain standalone until the assembly model can express
    them; they must never be flattened into an invented pin-to-pin connection.
    """
    from .multiboard_analysis import plan_multiboard_analysis
    from .multiboard_execution import compile_harness_electrical_network
    data = validate_harness(raw)
    circuit = compile_harness(data)
    if data["splices"]:
        raise ValueError("Assembly harness binding currently requires point-to-point wires without splices.")
    plan = plan_multiboard_analysis(multiboard_request)
    connectors = {c["id"]: c for c in data["connectors"]}
    resistances = {e["wire_id"]: e["resistance_ohm"] for e in circuit["elements"] if e["type"] == "resistor"}
    models = []
    used = set()
    for cable in plan["graph"]["harnesses"]:
        conductors = []
        for source_pin, target_pin in cable["pin_map"].items():
            matches = []
            for wire in data["wires"]:
                for a, b in ((wire["from"], wire["to"]), (wire["to"], wire["from"])):
                    ca, cb = connectors[a["connector"]], connectors[b["connector"]]
                    endpoint_a = {key: cable["endpoint_a"][key] for key in ("board_id", "connector_id")}
                    endpoint_b = {key: cable["endpoint_b"][key] for key in ("board_id", "connector_id")}
                    if ca.get("board_binding") == endpoint_a and cb.get("board_binding") == endpoint_b and a["pin"] == source_pin and b["pin"] == target_pin:
                        matches.append(wire)
            if len(matches) != 1 or matches[0]["id"] in used:
                raise ValueError("Harness document does not uniquely cover the assembly pin map.")
            wire = matches[0]
            model = wire.get("electrical", {})
            if model.get("inductance_h", 0) <= 0 or any(model.get(key, 0) > 0 for key in ("capacitance_to_reference_f", "conductance_to_reference_s")):
                raise ValueError("Assembly bridge requires explicit positive inductance and no unbound shunt models.")
            if wire.get("length_mm") != cable["length_mm"]:
                raise ValueError("Wire and assembly harness lengths disagree.")
            conductors.append({"source_pin": source_pin, "target_pin": target_pin, "resistance_ohm": resistances[wire["id"]], "inductance_h": model["inductance_h"]})
            used.add(wire["id"])
        models.append({"harness_id": cable["harness_id"], "conductors": conductors})
    if used != {w["id"] for w in data["wires"]}:
        raise ValueError("Harness document contains wires outside the selected assembly harnesses.")
    return compile_harness_electrical_network({"contract": "spike/multiboard-harness-compile-request/v1", "multiboard_request": multiboard_request, "conductor_models": models})
