# SPDX-License-Identifier: Apache-2.0
"""Validated, inert board-circuit handoff into SPIKES Studio."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .document import Document
from .schematic_layout import source_routes

CONTRACT = "spikes/studio-board-circuit-handoff/v1"
MAX_BYTES = 16 * 1024 * 1024
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_+./:{}()-]{1,256}$")
_PRIMITIVES = {"resistor": ("R", "resistor"), "capacitor": ("C", "capacitor"),
               "inductor": ("L", "inductor"), "voltage_source": ("V", "voltage_source"),
               "current_source": ("I", "current_source")}


def cross_selection_id(digest, occurrence_id, ref):
    return f"{digest}:{occurrence_id}:{ref}"


def default_handoff_roots():
    roots = [Path.cwd()/".local"/"studio-handoff", Path(tempfile.gettempdir())/"spikes-studio-handoff"]
    if os.environ.get("SPIKE_STUDIO_HANDOFF_ROOT"): roots.insert(0, Path(os.environ["SPIKE_STUDIO_HANDOFF_ROOT"]))
    return tuple(path.resolve() for path in roots)


def admit_handoff_path(path, roots=None):
    path = Path(path).resolve(strict=True)
    if not any(path.is_relative_to(Path(root).resolve()) for root in (roots or default_handoff_roots())):
        raise ValueError("Studio handoff must be inside a dedicated local handoff directory")
    if path.suffix.lower() != ".json" or path.stat().st_size > MAX_BYTES:
        raise ValueError("Studio handoff must be JSON no larger than 16 MiB")
    return path


def _text(value, label, limit=256):
    if not isinstance(value, str) or not value or len(value) > limit: raise ValueError(f"Invalid {label}")
    return value


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e7: raise ValueError(f"Invalid {label}")
    return float(value)


def validate_handoff(value):
    if not isinstance(value, dict) or value.get("contract") != CONTRACT: raise ValueError("Unsupported Studio handoff contract")
    source = value.get("source_design", {})
    digest = _text(source.get("digest"), "digest", 64).lower()
    occurrence = _text(source.get("occurrence_id"), "occurrence id")
    if not _DIGEST.fullmatch(digest) or not _TOKEN.fullmatch(occurrence): raise ValueError("Invalid source identity")
    components, nets = value.get("components"), value.get("nets")
    if not isinstance(components, list) or len(components) > 100000: raise ValueError("Invalid component list")
    if not isinstance(nets, list) or len(nets) > 100000: raise ValueError("Invalid net list")
    component_ids, refs, pin_ids, normalized = set(), set(), set(), []
    for item in components:
        ident, ref = _text(item.get("id"), "component id"), _text(item.get("ref"), "ref", 128)
        if ident in component_ids or ref in refs or not _REF.fullmatch(ref): raise ValueError("Duplicate or invalid component identity")
        component_ids.add(ident); refs.add(ref)
        placement = item.get("placement", {})
        if placement.get("side") not in ("top", "bottom"): raise ValueError("Invalid board side")
        placed = {"x_mm": _number(placement.get("x_mm"), "x_mm"), "y_mm": _number(placement.get("y_mm"), "y_mm"),
                  "rotation_deg": _number(placement.get("rotation_deg"), "rotation"), "side": placement["side"]}
        pins = []
        for pin in item.get("pins", []):
            pin_id = _text(pin.get("id"), "pin id")
            if pin_id in pin_ids: raise ValueError("Duplicate pin id")
            pin_ids.add(pin_id)
            pins.append({"id": pin_id, "pin": _text(str(pin.get("pin", "")), "pin"),
                         "net_id": _text(pin.get("net_id"), "net id"), "net_name": _text(pin.get("net_name"), "net name"),
                         "x_mm": _number(pin.get("x_mm"), "pin x"), "y_mm": _number(pin.get("y_mm"), "pin y")})
        binding = deepcopy(item.get("model_binding", {}))
        if binding.get("status") not in ("reviewed", "unavailable") or binding.get("source_kind") != "spike-workspace": raise ValueError("Invalid model binding")
        if set(binding)-{"status","source_kind","model_id","model_type","primitive","value","pin_bindings","parameters","evidence","model_pins"}: raise ValueError("Unsupported model binding field")
        if not pins and binding["status"] != "unavailable": raise ValueError("Reviewed components require explicit pins")
        cross_id = cross_selection_id(digest, occurrence, ref)
        if item.get("cross_selection_id", cross_id) != cross_id: raise ValueError("cross_selection_id does not match source identity")
        normalized.append({"id": ident, "ref": ref, "value": str(item.get("value", ""))[:1024], "placement": placed,
                           "pins": pins, "model_binding": binding, "cross_selection_id": cross_id})
    net_ids = set(); pin_owner={pin["id"]:(item["id"],pin["net_id"]) for item in normalized for pin in item["pins"]}
    for net in nets:
        net_id = _text(net.get("id"), "net id")
        if net_id in net_ids: raise ValueError("Duplicate net id")
        net_ids.add(net_id); _text(net.get("name"), "net name")
        for member in net.get("pins", []):
            if pin_owner.get(member.get("pin_id")) != (member.get("component_id"),net_id): raise ValueError("Invalid net member ownership")
    if any(pin["net_id"] not in net_ids for item in normalized for pin in item["pins"]): raise ValueError("Pin references unknown net")
    wires = value.get("wires", value.get("display_wires", []))
    if not isinstance(wires, list) or len(wires) > 200000: raise ValueError("Invalid display wires")
    for wire in wires:
        if wire.get("net_id") not in net_ids or wire.get("style") not in ("wire", "label"): raise ValueError("Invalid display wire")
        for point in wire.get("points_mm", []):
            if not isinstance(point, list) or len(point) != 2: raise ValueError("Invalid display wire point")
            _number(point[0], "wire x"); _number(point[1], "wire y")
    diagnostics = value.get("diagnostics", [])
    if not isinstance(diagnostics, list) or any(not isinstance(item, str) or len(item)>4096 for item in diagnostics): raise ValueError("Invalid diagnostics")
    ground=source.get("ground_node")
    if ground is not None: ground=_text(ground,"ground node",512)
    return {"contract": CONTRACT, "source_design": {"digest": digest, "occurrence_id": occurrence,
            "title": _text(source.get("title", "SPIKE board circuit"), "title", 512),"ground_node":ground},
            "components": normalized, "nets": deepcopy(nets), "wires": deepcopy(wires), "diagnostics": deepcopy(diagnostics)}


def _record(component,ground_node=None):
    binding = component["model_binding"]
    if binding["status"] != "reviewed" or binding.get("model_type") != "primitive": return None, "binding is not a reviewed primitive"
    if binding.get("primitive") not in _PRIMITIVES: return None, "primitive is unsupported by Studio"
    if len(component["pins"]) != 2: return None, "primitive requires two pins"
    mappings=binding.get("pin_bindings")
    if not isinstance(mappings,list) or len(mappings)!=2: return None,"primitive pin mapping is incomplete"
    model_pins=binding.get("model_pins")
    if model_pins is not None:
        if not isinstance(model_pins,list) or len(model_pins)!=2 or len(set(model_pins))!=2: return None,"primitive model pin order is invalid"
        by_model={row.get("model_pin"):row for row in mappings if isinstance(row,dict)}
        if set(by_model)!=set(model_pins): return None,"primitive model pin coverage is incomplete"
        mappings=[by_model[pin] for pin in model_pins]
    pins={pin["id"]:pin for pin in component["pins"]}; nodes=[]; seen=set()
    for row in mappings:
        if not isinstance(row,dict) or set(row)-{"model_pin","pad_id","circuit_node","board_net"}: return None,"primitive pin mapping is invalid"
        if row.get("pad_id") not in pins or row.get("model_pin") in seen: return None,"primitive pin mapping does not own its board pad"
        node=row.get("circuit_node");seen.add(row.get("model_pin"))
        if not isinstance(node,str) or not node or len(node)>512 or any(c in node for c in "\r\n"): return None,"primitive circuit node is invalid"
        nodes.append("0" if ground_node is not None and node==ground_node else node if _TOKEN.fullmatch(node) else "N_"+hashlib.sha256(node.encode("utf-8")).hexdigest()[:16])
    prefix, kind = _PRIMITIVES[binding["primitive"]]; value = binding.get("value")
    if not isinstance(value,str) or not value or len(value)>256 or any(c in value for c in "\r\n"): return None,"primitive value is invalid"
    source_ref=component["ref"] if component["ref"].upper().startswith(prefix) else prefix+hashlib.sha256(component["cross_selection_id"].encode()).hexdigest()[:12].upper()
    record=f"{source_ref} {nodes[0]} {nodes[1]} {value}"
    check_ground="" if "0" in nodes else f"\nR_HANDOFF_GROUND {nodes[0]} 0 1T"
    try: Document.from_netlist("Board handoff\n"+record+check_ground+"\n.op\n.end\n")
    except Exception: return None,"reviewed primitive is not accepted by the Studio parser"
    return {"record":record,"kind":kind,"source_ref":source_ref}, "reviewed primitive"


def document_from_handoff(value):
    handoff = validate_handoff(value); records, states = [], {}
    for item in handoff["components"]:
        record, detail = _record(item,handoff["source_design"].get("ground_node")); states[item["id"]] = {"available": bool(record), "reason": detail}
        if record: records.append(record["record"]); states[item["id"]]["source_ref"]=record["source_ref"]
    title = handoff["source_design"]["title"].replace("\n", " ").replace("\r", " ")
    source="\n".join([title,*records,*([".op"] if records else []),".end",""])
    if records: document=Document.from_netlist(source)
    else:
        document=Document.from_netlist("Board handoff seed\nV_HANDOFF __handoff 0 0\n.op\n.end\n")
        document.data.update(source=source,components=[],directives=[])
    by_ref = {p["ref"].upper(): p for p in document.data["components"]}
    min_x = min((p["placement"]["x_mm"] for p in handoff["components"]), default=0); min_y = min((p["placement"]["y_mm"] for p in handoff["components"]), default=0)
    inert, positions = [], {}
    for item in handoff["components"]:
        x, y = 140+(item["placement"]["x_mm"]-min_x)*40, 140+(item["placement"]["y_mm"]-min_y)*40
        extra = {"cross_selection_id": item["cross_selection_id"], "source_component_id": item["id"], "board_placement": deepcopy(item["placement"]),
                 "board_pins": deepcopy(item["pins"]), "model_binding": deepcopy(item["model_binding"]), "execution": deepcopy(states[item["id"]])}
        source_ref=states[item["id"]].get("source_ref",item["ref"])
        if source_ref.upper() in by_ref:
            part=by_ref[source_ref.upper()];part.update(extra,source_ref=source_ref,ref=item["ref"]);positions[part["id"]] = (x,y)
        else: inert.append({"id": hashlib.sha256(item["cross_selection_id"].encode()).hexdigest()[:32], "ref": item["ref"], "kind": "board_component_unavailable",
             "value": item["value"] or "unavailable", "nodes": [p["net_name"] for p in item["pins"]], "x": x, "y": y, "rotation": 0,
             "mirror_x": item["placement"]["side"]=="bottom", "mirror_y": False, "package": "", "variant": "unavailable", "temperature_k": 300.15,
             "limits": {}, "model_source": "", "evidence": "", "parameters": {}, **extra})
    if positions: document.move(positions, preserve_routes=False)
    if inert: document.commit(lambda data: data["components"].extend(inert))
    document.data["metadata"]["board_circuit_handoff"] = handoff; document.data["metadata"]["board_circuit_execution"] = states
    source_routes(document); document.saved_data = deepcopy(document.data); document.validate(); return document


def import_handoff_file(path, roots=None):
    path = admit_handoff_path(path, roots)
    return document_from_handoff(json.loads(path.read_text(encoding="utf-8")))
