# SPDX-License-Identifier: Apache-2.0
"""Compact canvas projections of source-authoritative reusable subcircuits.

The records in this module never replace native flattened components.  A block
pin is wireable only when it can be bound to an existing native terminal on the
same parsed hierarchy node.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math


SELECTION_PREFIX = "component-instance:"
PROJECTION_KEYS = {"x", "y", "rotation", "mirror_x", "mirror_y"}


def selection_id(ref):
    if not isinstance(ref, str) or not ref:
        raise ValueError("Reusable block reference must be nonempty text")
    return SELECTION_PREFIX + ref


def selected_ref(ident):
    return ident[len(SELECTION_PREFIX):] if isinstance(ident, str) and ident.startswith(SELECTION_PREFIX) else None


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def validate_projection(value):
    """Validate optional inert canvas geometry without accepting extra fields."""
    if not isinstance(value, dict) or set(value) != PROJECTION_KEYS:
        raise ValueError("Reusable block projection needs x, y, rotation and mirror flags")
    if any(type(value[key]) not in (int, float) or not math.isfinite(value[key]) or abs(value[key]) > 1e6
           for key in ("x", "y")):
        raise ValueError("Reusable block coordinates must be finite and bounded")
    if type(value["rotation"]) is not int or value["rotation"] not in (0, 90, 180, 270):
        raise ValueError("Reusable block rotation must be 0, 90, 180 or 270 degrees")
    if type(value["mirror_x"]) is not bool or type(value["mirror_y"]) is not bool:
        raise ValueError("Reusable block mirror flags must be boolean")
    return value


def _geometry(record, members):
    value = record.get("projection")
    if value is not None:
        return deepcopy(validate_projection(value))
    # Legacy packages predate projection geometry.  Their flattened placement
    # is deterministic, so its centroid is a stable migration fallback.
    if not members:
        raise ValueError("Reusable block has no native flattened components")
    return {"x": sum(part["x"] for part in members) / len(members),
            "y": sum(part["y"] for part in members) / len(members),
            "rotation": 0, "mirror_x": False, "mirror_y": False}


def projected_blocks(data):
    """Return checked top-level block projections from native hierarchy facts."""
    metadata = data.get("metadata", {})
    packages = metadata.get("component_packages", {})
    records = metadata.get("component_instances", [])
    if not isinstance(packages, dict) or not isinstance(records, list) or len(records) > 10000:
        raise ValueError("Invalid reusable component metadata")
    if not records:
        return []

    from .component_package import validate as validate_package
    from .part_properties import parse
    hierarchy = {row.path.casefold(): row for row in parse(data["source"]).hierarchy
                 if not row.parent_path}
    parts = data.get("components", [])
    result = []
    seen = set()
    for record in records:
        allowed = {"ref", "package_sha256", "pins", "projection"}
        if not isinstance(record, dict) or set(record) - allowed or not {"ref", "package_sha256", "pins"} <= set(record):
            raise ValueError("Invalid reusable component instance record")
        ref = record["ref"]
        if not isinstance(ref, str) or not ref or ref.casefold() in seen:
            raise ValueError("Reusable component references must be unique nonempty text")
        seen.add(ref.casefold())
        key = record["package_sha256"]
        package = packages.get(key)
        if not isinstance(key, str) or len(key) != 64 or package is None:
            raise ValueError("Reusable component package reference is missing")
        validate_package(package)
        if _digest(package) != key:
            raise ValueError("Reusable component package digest does not match its content")
        implementation = package["implementation"]
        # Primitive MODEL packages already use their native custom symbol.  A
        # compact hierarchy projection applies only to actual X/SUBCKT rows.
        if implementation["language"] != "SPICE" or implementation["prefix"] != "X":
            if "projection" in record:
                validate_projection(record["projection"])
            continue
        if implementation["source"].strip() not in data["source"]:
            raise ValueError("Reusable block package source differs from the native hierarchy definition")
        instance = hierarchy.get(ref.casefold())
        if instance is None or instance.definition.casefold() != implementation["entry"].casefold():
            raise ValueError("Reusable block no longer matches an actual top-level hierarchy instance")
        terminals = package["symbol"]["terminals"]
        mapping = record["pins"]
        terminal_ids = [terminal["id"] for terminal in terminals]
        if not isinstance(mapping, dict) or set(mapping) != set(terminal_ids) or any(not isinstance(value, str) or not value for value in mapping.values()):
            raise ValueError("Reusable block must map every declared public pin")
        if [terminal["name"].casefold() for terminal in terminals] != [pin.casefold() for pin in instance.pins]:
            raise ValueError("Reusable block symbol pins differ from the native hierarchy declaration")
        nodes = [mapping[ident] for ident in terminal_ids]
        if [node.casefold() for node in nodes] != [node.casefold() for node in instance.nodes]:
            raise ValueError("Reusable block pin metadata differs from native hierarchy node mapping")
        if len({node.casefold() for node in nodes}) != len(nodes):
            raise ValueError("Reusable block maps multiple public pins to one node; compact pin anchors would be ambiguous")
        members = [part for part in parts if part.get("ref", "").casefold().startswith(ref.casefold() + ":")]
        if not members:
            raise ValueError("Reusable block has no native flattened components")
        geometry = _geometry(record, members)
        bindings = [];aliases=[]
        ordered_members = sorted(members, key=lambda part: (part["ref"].casefold(), part["ref"], part["id"]))
        for node in nodes:
            candidates = [(part["id"], index) for part in ordered_members
                          for index, actual in enumerate(part["nodes"])
                          if actual.casefold() == node.casefold()]
            aliases.append([list(endpoint) for endpoint in candidates])
            bindings.append(list(candidates[0]) if candidates else None)
        symbol = deepcopy(package["symbol"])
        result.append({"id": selection_id(ref), "ref": ref, "kind": "reusable_block",
                       "value": package["name"], "nodes": nodes,
                       "x": geometry["x"], "y": geometry["y"],
                       "rotation": geometry["rotation"], "mirror_x": geometry["mirror_x"],
                       "mirror_y": geometry["mirror_y"], "package": "", "variant": "native hierarchy",
                       "temperature_k": 300.15, "limits": {}, "model_source": "", "evidence": "",
                       "parameters": {"component_symbol": symbol}, "pin_bindings": bindings,
                       "pin_aliases": aliases,
                       "member_ids": [part["id"] for part in members],
                       "package_sha256": key, "_reusable_block": True})
    junctions = {item["id"]: item for item in data.get("junctions", [])}
    owner_by_part = {ident: block["id"] for block in result for ident in block["member_ids"]}
    public = {tuple(endpoint): block["id"] for block in result
              for aliases in block["pin_aliases"] for endpoint in aliases}
    for wire in data.get("wires", []):
        endpoints = [_terminal_endpoint(wire[key], junctions) for key in ("a", "b")]
        owners = [owner_by_part.get(endpoint[0]) if endpoint else None for endpoint in endpoints]
        if owners[0] == owners[1]:
            continue
        for endpoint, owner in zip(endpoints, owners):
            if owner is not None and public.get(endpoint) != owner:
                raise ValueError("Reusable block has a cross-boundary wire on a private native node; compact projection is unsafe")
    return result


def projection_report(data):
    """Return a fail-safe projection result suitable for the live canvas.

    Invalid or stale metadata reveals all native flattened components instead
    of guessing a hierarchy mapping or interrupting painting.
    """
    try:
        return {"blocks": projected_blocks(data), "diagnostics": []}
    except (KeyError, TypeError, ValueError) as error:
        return {"blocks": [], "diagnostics": [str(error)]}


def hidden_member_ids(data):
    return {ident for block in projected_blocks(data) for ident in block["member_ids"]}


def resolve_selection(data, selected):
    """Expand projection IDs to the exact native flattened component IDs."""
    blocks = {block["id"]: block for block in projected_blocks(data)}
    native = {part["id"] for part in data.get("components", [])}
    if not isinstance(selected, (set, list, tuple)) or not selected:
        raise ValueError("Selection is empty")
    unknown = set(selected) - native - set(blocks)
    if unknown:
        raise ValueError("Reusable block selection is stale")
    result = {ident for ident in selected if ident in native}
    for ident in selected:
        if ident in blocks:
            result.update(blocks[ident]["member_ids"])
    return result


def pin_overrides(blocks):
    """Map real native endpoints to their compact presentation positions."""
    from .editor_geometry import transform
    from .pin_geometry import pins
    result = {}
    for block in blocks:
        for pin, aliases in zip(pins(block), block["pin_aliases"]):
            for endpoint in aliases:
                result[tuple(endpoint)] = transform(block, *pin.anchor)
    return result


def _terminal_endpoint(endpoint, junctions):
    if not isinstance(endpoint, (list, tuple)):
        return None
    if len(endpoint) == 2:
        return tuple(endpoint)
    if len(endpoint) == 1:
        junction = junctions.get(endpoint[0])
        source = junction.get("source_terminal") if junction else None
        return tuple(source) if isinstance(source, (list, tuple)) and len(source) == 2 else None
    return None


def internal_block_wire(wire, blocks, junctions):
    """True only when both real endpoints belong to the same projected block."""
    owner = {ident: block["id"] for block in blocks for ident in block["member_ids"]}
    endpoints = [_terminal_endpoint(wire[key], junctions) for key in ("a", "b")]
    owners = [owner.get(endpoint[0]) if endpoint else None for endpoint in endpoints]
    return owners[0] is not None and owners[0] == owners[1]


def projected_route(parts, wire, junctions, overrides):
    """Draw real wire identity at projected public pins without changing topology."""
    from .editor_geometry import endpoint_position, orthogonal_path, route
    a, b = tuple(wire["a"]), tuple(wire["b"])
    if a not in overrides and b not in overrides:
        return route(parts, wire, junctions)
    start = overrides.get(a, endpoint_position(parts, junctions, wire["a"]))
    end = overrides.get(b, endpoint_position(parts, junctions, wire["b"]))
    return orthogonal_path(start, [*wire.get("waypoints", []), end], wire.get("bend", "horizontal"))


def _records_by_ref(data):
    return {record["ref"].casefold(): record
            for record in data.get("metadata", {}).get("component_instances", [])}


def move_selected(document, selected, delta, preserve_routes=True):
    """Move block projections and their native members in one undo transaction."""
    if type(preserve_routes) is not bool:
        raise ValueError("preserve_routes must be boolean")
    refs = [selected_ref(ident) for ident in selected if selected_ref(ident) is not None]
    native_ids = {ident for ident in selected if selected_ref(ident) is None}
    if not refs:
        raise ValueError("Select a reusable block")
    dx, dy = map(float, delta)
    if not math.isfinite(dx) or not math.isfinite(dy):
        raise ValueError("Reusable block movement must be finite")
    blocks = {block["ref"].casefold(): block for block in projected_blocks(document.data)}
    component_ids = {part["id"] for part in document.data["components"]}
    if any(ref.casefold() not in blocks for ref in refs) or not native_ids <= component_ids:
        raise ValueError("Reusable block selection is stale")
    records = _records_by_ref(document.data)
    member_ids = {ident for ref in refs for ident in blocks[ref.casefold()]["member_ids"]} | native_ids
    by_id = {part["id"]: part for part in document.data["components"]}
    deltas = {ident: (dx, dy) for ident in member_ids}
    from .editor_geometry import dragged_waypoints
    routed = {}
    junctions = {item["id"]: item for item in document.data["junctions"]}
    for wire in document.data["wires"]:
        if wire["a"][0] in deltas or wire["b"][0] in deltas:
            routed[wire["id"]] = dragged_waypoints(by_id, wire, deltas, junctions) if preserve_routes else []

    def mutate(data):
        for part in data["components"]:
            if part["id"] in member_ids:
                part["x"] += dx; part["y"] += dy
        mutable_records = _records_by_ref(data)
        for ref in refs:
            block = blocks[ref.casefold()]
            mutable_records[ref.casefold()]["projection"] = {
                "x": block["x"] + dx, "y": block["y"] + dy,
                "rotation": block["rotation"], "mirror_x": block["mirror_x"],
                "mirror_y": block["mirror_y"]}
        for wire in data["wires"]:
            if wire["id"] in routed:
                wire["waypoints"] = routed[wire["id"]]
    document.commit(mutate)


def rotate_selected(document, selected):
    """Rotate block drawings and ordinary selected symbols atomically."""
    refs = [selected_ref(ident) for ident in selected if selected_ref(ident) is not None]
    native_ids = {ident for ident in selected if selected_ref(ident) is None}
    blocks = {block["ref"].casefold(): block for block in projected_blocks(document.data)}
    component_ids = {part["id"] for part in document.data["components"]}
    if not selected or any(ref.casefold() not in blocks for ref in refs) or not native_ids <= component_ids:
        raise ValueError("Selection is empty or stale")

    def mutate(data):
        records = _records_by_ref(data)
        for ref in refs:
            block = blocks[ref.casefold()]
            records[ref.casefold()]["projection"] = {
                "x": block["x"], "y": block["y"],
                "rotation": (block["rotation"] + 90) % 360,
                "mirror_x": block["mirror_x"], "mirror_y": block["mirror_y"]}
        for part in data["components"]:
            if part["id"] in native_ids:
                part["rotation"] = (part["rotation"] + 90) % 360
    document.commit(mutate)
