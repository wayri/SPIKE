"""Connector discovery and deterministic, reviewable multi-board harness proposals."""
from __future__ import annotations

import math
import re
from collections import defaultdict

from .assembly_frames import resolve_world
from .design_ir_v2 import AssemblyIRV1
from .design_ir_v2_schema import canonical_uuid, content_digest
from .harness_routing import point, route_cable


def validate_harness_connections(assembly):
    """Validate wiring references while retaining older endpoint-only mappings."""
    boards = {b.id for b in assembly.boards}
    mappings, occupied = {}, set()
    for mapping in assembly.connector_mappings:
        data = mapping.data
        if not isinstance(data, dict):
            raise ValueError(f"Connector mapping {mapping.id} data must be an object.")
        if data.get("board_id") and data.get("connector_id"):
            if data["board_id"] not in boards:
                raise ValueError("Connector mapping references an unknown board.")
            key = f"{data['board_id']}::{data['connector_id']}"
            if key in mappings: raise ValueError(f"Duplicate connector mapping: {key}")
            point(data.get("position_mm"), key)
            mappings[key] = data
    for h in assembly.harnesses:
        endpoints = []
        for value in (h.endpoint_a, h.endpoint_b):
            board, separator, connector = value.partition("::" if "::" in value else ":")
            if not separator or not connector or board not in boards:
                raise ValueError(f"Harness {h.id} has an unresolved endpoint.")
            endpoints.append((board, f"{board}::{connector}"))
        if endpoints[0][0] == endpoints[1][0]: raise ValueError("Harnesses must connect distinct boards.")
        if len(set(h.pin_map.values())) != len(h.pin_map): raise ValueError("Harness destination pins must be unique.")
        for a, b in h.pin_map.items():
            for (_, key), pin in zip(endpoints, (a, b)):
                if not isinstance(pin, str) or not pin.strip(): raise ValueError("Harness pins must be non-empty strings.")
                if (key, pin) in occupied: raise ValueError(f"Connector pin already assigned: {key}:{pin}")
                occupied.add((key, pin))
                mapping = mappings.get(key)
                if mapping and "pins" in mapping and pin not in mapping["pins"]:
                    raise ValueError(f"Unknown connector pin: {key}:{pin}")
                if "spike.harness-routing" in h.extensions and mapping is None:
                    raise ValueError("Routed harnesses require retained connector mappings.")
    for mate in assembly.connector_mappings:
        if mate.kind != "connector-mate":
            continue
        data = mate.data
        if not isinstance(data, dict) or set(data) != {"endpoint_a", "endpoint_b", "pin_map"}:
            raise ValueError(f"Connector mate {mate.id} requires two endpoints and an explicit pin_map only.")
        endpoints = []
        for field in ("endpoint_a", "endpoint_b"):
            value = data.get(field)
            if not isinstance(value, str):
                raise ValueError(f"Connector mate {mate.id} requires {field} as board::connector.")
            board, separator, connector = value.partition("::")
            if not separator or not board or not connector or board not in boards:
                raise ValueError(f"Connector mate {mate.id} has an unresolved {field}.")
            endpoints.append((board, value))
        if endpoints[0][0] == endpoints[1][0]:
            raise ValueError(f"Connector mate {mate.id} must join distinct board instances.")
        pin_map = data.get("pin_map")
        if not isinstance(pin_map, dict) or not pin_map or len(pin_map) > 512:
            raise ValueError(f"Connector mate {mate.id} needs 1 through 512 explicit pin pairs.")
        if any(not isinstance(a, str) or not a.strip() or not isinstance(b, str) or not b.strip()
               for a, b in pin_map.items()) or len(set(pin_map.values())) != len(pin_map):
            raise ValueError(f"Connector mate {mate.id} has invalid or duplicate pin identities.")
        for a, b in pin_map.items():
            for (_, endpoint), pin in zip(endpoints, (a, b)):
                if (endpoint, pin) in occupied:
                    raise ValueError(f"Connector pin already assigned: {endpoint}:{pin}")
                occupied.add((endpoint, pin))
                mapping = mappings.get(endpoint)
                if mapping and "pins" in mapping and pin not in mapping["pins"]:
                    raise ValueError(f"Unknown connector pin: {endpoint}:{pin}")


def discover_connectors(assembly, designs):
    """Discover connector candidates by reference; retain explicit mappings as authority."""
    result = {}
    for board in assembly.boards:
        design = designs.get(board.design_id, {})
        nets = {n["id"]: n.get("name", "") for n in design.get("nets", [])}
        pin_numbers = {p["id"]: p.get("number", "") for p in design.get("pins", [])}
        pads = defaultdict(list)
        for pad in design.get("pads", []):
            pads[pad.get("component_id")].append(pad)
        for component in design.get("components", []):
            reference = component.get("reference", "")
            if not re.match(r"^(J|P|CN)\d", reference, re.I):
                continue
            pins = {}
            for pad in pads[component["id"]]:
                pin = str(pin_numbers.get(pad.get("pin_id"), pad.get("name") or pad.get("pin_id", "")))
                if pin:
                    net = nets.get(pad.get("net_id"), "")
                    if pin in pins and pins[pin] != net:
                        raise ValueError(f"Connector {reference} pin {pin} has conflicting pad nets.")
                    pins[pin] = net
            xy = component.get("position_mm", [0, 0])
            result[f"{board.id}::{reference}"] = {"board_id": board.id, "connector_id": reference,
                "position_mm": [*xy, 0], "pins": pins, "discovered": True}
    for mapping in assembly.connector_mappings:
        data = mapping.data
        if data.get("board_id") and data.get("connector_id"):
            key = f"{data['board_id']}::{data['connector_id']}"
            result[key] = {**result.get(key, {}), **data, "discovered": False}
    boards = {b.id: b for b in assembly.boards}
    for key, data in result.items():
        if data["board_id"] not in boards:
            raise ValueError(f"Connector {key} references an unknown board instance.")
        xyz = point(data.get("position_mm"), f"Connector {key}")
        transform = resolve_world(assembly, boards[data["board_id"]].frame)
        data["assembly_position_mm"] = [sum(transform[r * 4 + c] * xyz[c] for c in range(3)) + transform[r * 4 + 3] for r in range(3)]
        if not isinstance(data.get("pins", {}), dict):
            raise ValueError(f"Connector {key} pins must map pin numbers to net names.")
    return result


def plan_harnesses(request):
    assembly = AssemblyIRV1.from_dict(request["assembly"])
    validate_harness_connections(assembly)
    connectors = discover_connectors(assembly, request.get("designs", {}))
    if len(connectors) > 2000:
        raise ValueError("Harness authoring supports at most 2000 connectors.")
    slack = float(request.get("slack_percent", 10))
    allowance = float(request.get("termination_allowance_mm", 10))
    gauge = float(request.get("gauge_awg", 24))
    if not all(math.isfinite(v) for v in (slack, allowance, gauge)) or not (0 <= slack <= 100 and 0 <= allowance <= 1000 and 0 <= gauge <= 40):
        raise ValueError("Use 0–100% slack, 0–1000 mm termination allowance and 0–40 AWG.")
    diagnostics, proposals = [], []
    occupied = set()
    for harness in assembly.harnesses:
        for a, b in harness.pin_map.items():
            occupied.update(((harness.endpoint_a if "::" in harness.endpoint_a else harness.endpoint_a.replace(":", "::", 1), a),
                             (harness.endpoint_b if "::" in harness.endpoint_b else harness.endpoint_b.replace(":", "::", 1), b)))
    pairs = request.get("pairs")
    if pairs is None:
        # Automatic proposals require a net to resolve to exactly two free pins
        # globally. Shared power/ground or multi-drop nets need explicit pairing.
        occurrences = defaultdict(list)
        for key, data in sorted(connectors.items()):
            for pin, net in data.get("pins", {}).items():
                if net and (key, pin) not in occupied:
                    occurrences[str(net)].append((key, pin))
        grouped = defaultdict(dict)
        for net, ends in sorted(occurrences.items()):
            if len(ends) == 2 and ends[0][0] != ends[1][0] and connectors[ends[0][0]]["board_id"] != connectors[ends[1][0]]["board_id"]:
                grouped[(ends[0][0], ends[1][0])][ends[0][1]] = ends[1][1]
            elif len(ends) > 1:
                diagnostics.append({"code": "ambiguous_net", "message": f"Net {net} has {len(ends)} candidate pins; choose connector pairs explicitly."})
        pairs = [{"endpoint_a": a, "endpoint_b": b, "pin_map": pins} for (a, b), pins in sorted(grouped.items())]
    if not isinstance(pairs, list) or len(pairs) > 1000:
        raise ValueError("Harness planning requires an array of at most 1000 connector pairs.")
    for pair in pairs:
        a, b = pair["endpoint_a"], pair["endpoint_b"]
        if a not in connectors or b not in connectors:
            raise ValueError("Harness endpoints must resolve to discovered or explicitly mapped connectors.")
        ca, cb = connectors[a], connectors[b]
        if ca["board_id"] == cb["board_id"]:
            raise ValueError("Harness endpoints must belong to distinct board instances.")
        pins = pair.get("pin_map")
        if pins is None:
            by_net_a, by_net_b = defaultdict(list), defaultdict(list)
            for pin, net in ca.get("pins", {}).items():
                if net: by_net_a[net].append(pin)
            for pin, net in cb.get("pins", {}).items():
                if net: by_net_b[net].append(pin)
            pins = {}
            for net in sorted(by_net_a.keys() & by_net_b.keys()):
                if len(by_net_a[net]) == len(by_net_b[net]) == 1:
                    pins[by_net_a[net][0]] = by_net_b[net][0]
                else:
                    diagnostics.append({"code": "ambiguous_pin", "message": f"{a} to {b}: net {net} needs an explicit pin map."})
        if not isinstance(pins, dict) or not all(isinstance(p, str) and isinstance(q, str) for p, q in pins.items()):
            raise ValueError("Pin maps must map string pin numbers to string pin numbers.")
        if not pins:
            diagnostics.append({"code": "no_matching_pins", "message": f"No unambiguous matching nets between {a} and {b}."})
            continue
        if len(set(pins.values())) != len(pins):
            raise ValueError("A harness cannot assign multiple conductors to the same destination pin.")
        for p, q in pins.items():
            if p not in ca.get("pins", {}) or q not in cb.get("pins", {}):
                raise ValueError(f"Unknown connector pin in {a}:{p} to {b}:{q}.")
            if (a, p) in occupied or (b, q) in occupied:
                raise ValueError(f"Connector pin already assigned: {a}:{p} or {b}:{q}.")
            occupied.update(((a, p), (b, q)))
        route = route_cable(ca["assembly_position_mm"], cb["assembly_position_mm"], request.get("keepouts", []), request.get("clearance_mm", 2), pair.get("waypoints_mm", []))
        length = route["routed_length_mm"] * (1 + slack / 100) + 2 * allowance
        identifier = canonical_uuid("harness-plan", content_digest([a, b, pins]), "harness", a + b)
        proposals.append({"id": identifier, "name": f"{a} → {b}", "endpoint_a": a, "endpoint_b": b,
            "pin_map": pins, "length_mm": length, "gauge_awg": gauge, "conductor_material_id": "",
            "extensions": {"spike.harness-routing": {**route, "endpoint_a_mm": ca["assembly_position_mm"], "endpoint_b_mm": cb["assembly_position_mm"], "slack_percent": slack,
                "termination_allowance_mm": allowance, "clearance_mm": request.get("clearance_mm", 2), "bend_radius_qualified": False}}})
    mappings = [{"id": canonical_uuid("connector", "", "mapping", key), "name": key, "kind": "connector", "data": data} for key, data in sorted(connectors.items())]
    wire_list = [{"harness_id": h["id"], "from": h["endpoint_a"], "from_pin": p, "to": h["endpoint_b"], "to_pin": q,
                  "cut_length_mm": h["length_mm"], "gauge_awg": gauge} for h in proposals for p, q in h["pin_map"].items()]
    return {"contract": "spike/harness-plan/v1", "harnesses": proposals, "connector_mappings": mappings,
            "connectors": connectors, "wire_list": wire_list, "diagnostics": diagnostics, "requires_review": True,
            "total_wire_length_mm": sum(w["cut_length_mm"] for w in wire_list), "solver_ready": False}
