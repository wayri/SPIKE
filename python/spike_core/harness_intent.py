# SPDX-License-Identifier: Apache-2.0
"""Explicit conductor intent; labels never establish an electrical model."""
from __future__ import annotations

import copy


def validate_assembly_conductors(harness):
    """Admit retained conductor metadata against its authoritative pin map.

    Metadata stays on the AssemblyIR entity. A temporary canonical harness
    reuses the standalone semantic boundary without inventing electrical data.
    """
    key = "spike.harness-conductors"
    if key not in harness.extensions:
        return
    raw = harness.extensions[key]
    allowed = {"contract", "wires", "pairs", "connectors", "cables", "analysis_extensions"}
    if not isinstance(raw, dict) or set(raw) - allowed or raw.get("contract") != "spike/assembly-harness-conductors/v1":
        raise ValueError("HARNESS_CONDUCTOR_CONTRACT: invalid assembly conductor metadata.")
    wires = raw.get("wires")
    if not isinstance(wires, list) or not 1 <= len(wires) <= 512 or len(wires) != len(harness.pin_map):
        raise ValueError("HARNESS_CONDUCTOR_PIN_MAP: metadata must cover every saved pin pair exactly once.")
    canonical, sources = [], set()
    for wire in wires:
        if not isinstance(wire, dict) or not isinstance(wire.get("from_pin"), str) or not isinstance(wire.get("to_pin"), str):
            raise ValueError("HARNESS_CONDUCTOR_PIN_MAP: each wire requires explicit from_pin and to_pin strings.")
        source, target = wire["from_pin"], wire["to_pin"]
        if source in sources or harness.pin_map.get(source) != target:
            raise ValueError("HARNESS_CONDUCTOR_PIN_MAP: stale or duplicate wire pin mapping.")
        sources.add(source)
        # Reject canonical endpoints/route fields in this extension: the saved
        # assembly owns them, so wire metadata cannot silently override them.
        if set(wire) & {"from", "to", "route_id"}:
            raise ValueError("HARNESS_CONDUCTOR_PIN_MAP: conductor endpoints and routes are assembly-owned.")
        row = {k: copy.deepcopy(v) for k, v in wire.items() if k not in {"from_pin", "to_pin"}}
        row.update({"from": {"connector": harness.endpoint_a, "pin": source},
                    "to": {"connector": harness.endpoint_b, "pin": target}})
        canonical.append(row)
    connectors = raw.get("connectors")
    expected = {harness.endpoint_a: set(harness.pin_map), harness.endpoint_b: set(harness.pin_map.values())}
    if connectors is None:
        connectors = [{"id": key, "pins": [{"id": pin} for pin in sorted(pins)]} for key, pins in expected.items()]
    else:
        if not isinstance(connectors, list) or len(connectors) != 2:
            raise ValueError("HARNESS_CONDUCTOR_CONNECTORS: metadata requires the two saved connectors.")
        seen = set()
        for connector in connectors:
            if not isinstance(connector, dict) or not isinstance(connector.get("id"), str):
                raise ValueError("HARNESS_CONDUCTOR_CONNECTORS: invalid connector metadata.")
            identity = connector["id"]
            pins = connector.get("pins")
            if identity not in expected or identity in seen or not isinstance(pins, list) or any(not isinstance(p, dict) or not isinstance(p.get("id"), str) for p in pins):
                raise ValueError("HARNESS_CONDUCTOR_CONNECTORS: connectors must match the saved endpoints.")
            if {pin["id"] for pin in pins} != expected[identity]:
                raise ValueError("HARNESS_CONDUCTOR_CONNECTORS: connector pins must match the saved pin map.")
            if "board_binding" in connector:
                board, _, ref = identity.partition("::" if "::" in identity else ":")
                if connector["board_binding"] != {"board_id": board, "connector_id": ref}:
                    raise ValueError("HARNESS_CONDUCTOR_CONNECTORS: board binding disagrees with the saved endpoint.")
            seen.add(identity)
    from .harness import validate_harness
    validate_harness({"contract": "spike/harness/v1", "id": harness.id, "name": harness.name or harness.id,
                      "connectors": copy.deepcopy(connectors), "wires": canonical,
                      "pairs": copy.deepcopy(raw.get("pairs", [])), "cables": copy.deepcopy(raw.get("cables", [])),
                      "extensions": copy.deepcopy(raw.get("analysis_extensions", {}))})


def validate_conductor_intent(data):
    """Check role, ordered pair identities, twist, and cable ownership."""
    wires = {wire["id"]: wire for wire in data["wires"]}
    membership = {wire: cable["id"] for cable in data["cables"] for wire in cable["wire_ids"]}
    paired = set()

    def spans(wire):
        # Pair orientation is taken from the first wire's from/to. A reversed
        # second wire is retained; no endpoint or polarity is silently changed.
        ends = [wire["from"], wire["to"]]
        if any("connector" not in end for end in ends):
            raise ValueError("HARNESS_PAIR_ENDPOINTS: pairs require connector-to-connector wires.")
        return frozenset(end["connector"] for end in ends)

    for wire in wires.values():
        if "return_wire_id" in wire:
            reference = wires.get(wire["return_wire_id"])
            if reference is None or reference is wire or reference.get("role") != "return" or wire.get("role") not in {"power", "signal"}:
                raise ValueError("HARNESS_RETURN_REFERENCE: power/signal wires need a distinct explicit return-role wire.")
    for cable in data["cables"]:
        if "twist_pitch_mm" in cable and cable.get("twisted") is not True:
            raise ValueError("HARNESS_TWIST_METADATA: cable pitch requires twisted=true.")
    for pair in data.get("pairs", []):
        ids = pair["wire_ids"]
        if any(key not in wires or key in paired for key in ids):
            raise ValueError("HARNESS_PAIR_MEMBERSHIP: pair wires must exist and belong to only one pair.")
        a, b = (wires[key] for key in ids)
        if spans(a) != spans(b) or len(spans(a)) != 2:
            raise ValueError("HARNESS_PAIR_ENDPOINTS: pair members must span the same two distinct connectors.")
        if any(end_a == end_b for end_a in (a["from"], a["to"]) for end_b in (b["from"], b["to"])):
            raise ValueError("HARNESS_PAIR_ENDPOINTS: pair members must use distinct connector terminals.")
        if membership.get(ids[0]) != membership.get(ids[1]):
            raise ValueError("HARNESS_PAIR_CABLE: pair members must have the same cable assignment.")
        if pair["kind"] == "differential" and any(wire.get("role") != "signal" for wire in (a, b)):
            raise ValueError("HARNESS_PAIR_ROLE: differential members must both declare role=signal.")
        twisted = pair["kind"] == "twisted" or pair.get("twisted") is True
        if pair["kind"] == "twisted" and pair.get("twisted") is False:
            raise ValueError("HARNESS_TWIST_METADATA: twisted pair cannot declare twisted=false.")
        if "twist_pitch_mm" in pair and not twisted:
            raise ValueError("HARNESS_TWIST_METADATA: pair pitch requires an explicit twist declaration.")
        paired.update(ids)
