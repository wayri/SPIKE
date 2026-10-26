# SPDX-License-Identifier: Apache-2.0
"""Bounded native KiCad evidence for source-authenticated solver adapters.

This auxiliary importer adapter is intentionally narrower than
``kicad_importer``.  Parser objects remain local; callers receive only plain,
canonical data for one UUID-selected pad or a complete native pad inventory.
"""
from __future__ import annotations

import hashlib
import math
from contextlib import redirect_stdout
from io import StringIO
from itertools import chain
from pathlib import Path


MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_BOARD_INVENTORY_BYTES = 64 * 1024 * 1024
MAX_SEXP_NODES = 2_000_000


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _atom(value):
    return str(value).strip('"')


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Native {label} must be finite") from error
    _require(math.isfinite(result), f"Native {label} must be finite")
    return result


def _children(node, key):
    return [item for item in node if isinstance(item, list) and item and item[0] == key]


def _one(node, key, required=True):
    matches = _children(node, key)
    _require(len(matches) <= 1, f"Ambiguous native {key} declaration")
    if required:
        _require(len(matches) == 1, f"Native {key} declaration required")
    return matches[0] if matches else None


def _pad_identity(node):
    identities = []
    for key in ("uuid", "tstamp"):
        identities.extend(_children(node, key))
    values = [_atom(item[1]).strip() for item in identities if len(item) == 2]
    _require(len(values) == len(identities), "Malformed native pad identity")
    _require(len(values) <= 1, "Ambiguous native pad identity")
    return values[0] if values else ""


def read_kicad_pad_source_evidence(path, expected_sha256, native_uuid):
    """Return plain evidence for exactly one UUID-selected native KiCad pad."""
    source = Path(path).resolve()
    _require(source.is_file() and source.stat().st_size <= MAX_SOURCE_BYTES,
             "Source file missing or exceeds budget")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    _require(type(expected_sha256) is str and expected_sha256 == before, "Source file hash differs")
    _require(type(native_uuid) is str and native_uuid.strip(), "Native pad UUID required")

    # This module is a registered importer-owned boundary.  The parser and its
    # S-expression nodes do not escape this function.
    from python.core.board_parser import KicadParser
    with redirect_stdout(StringIO()):
        parser = KicadParser(source)
    root = parser.parse_sexp(parser.tokenize(parser.content))
    selected = []
    pending = [root]
    visited = 0
    while pending:
        node = pending.pop()
        if not isinstance(node, list) or not node:
            continue
        visited += 1
        _require(visited <= MAX_SEXP_NODES, "Native source S-expression exceeds node budget")
        if node[0] == "pad" and _pad_identity(node) == native_uuid:
            selected.append(node)
        pending.extend(item for item in node if isinstance(item, list))
    _require(len(selected) == 1, "Native source pad UUID is missing or ambiguous")
    pad = selected[0]
    _require(len(pad) >= 4, "Malformed native pad declaration")

    padstack = _one(pad, "padstack", required=False)
    _require(padstack is None, "Per-layer native padstack geometry is unsupported")
    removal = _one(pad, "remove_unused_layers", required=False)
    removal_value = "absent"
    if removal is not None:
        _require(len(removal) == 2 and _atom(removal[1]).lower() == "no",
                 "Unused-layer removal is unsupported for source annuli")
        removal_value = "no"
    _require(_one(pad, "keep_end_layers", required=False) is None,
             "End-layer retention policy is unsupported for source annuli")

    at = _one(pad, "at")
    size = _one(pad, "size")
    layers = _one(pad, "layers")
    drill = _one(pad, "drill")
    net = _one(pad, "net")
    _require(len(at) in (3, 4) and len(size) == 3 and len(layers) >= 2,
             "Incomplete native pad geometry")
    _require(len(drill) >= 2 and _atom(drill[1]).lower() != "oval",
             "Only a circular native drill is supported")
    _require(not any(not isinstance(item, list) and _atom(item).lower() == "oval" for item in drill[1:]),
             "Only a circular native drill is supported")
    offset = _one(drill, "offset", required=False)
    drill_atoms = [item for item in drill if not isinstance(item, list)]
    drill_nodes = [item for item in drill if isinstance(item, list)]
    _require(len(drill_atoms) == 2 and all(item and item[0] == "offset" for item in drill_nodes),
             "Unsupported native drill declaration")
    offset_xy = [0.0, 0.0]
    if offset is not None:
        _require(len(offset) == 3, "Malformed native drill offset")
        offset_xy = [_number(offset[1], "drill offset"), _number(offset[2], "drill offset")]
    _require(offset_xy == [0.0, 0.0], "Native offset drills are not coaxial annuli")
    _require(len(net) in (2, 3), "Malformed native pad net")
    net_code = None if len(net) == 2 else _atom(net[1])
    net_name = _atom(net[-1])
    _require(bool(net_name), "Native source net must be explicit")

    size_xy = [_number(size[1], "pad size"), _number(size[2], "pad size")]
    drill_diameter = _number(drill[1], "drill diameter")
    _require(drill_diameter > 0, "Native drill diameter must be positive")
    evidence = {
        "contract": "spike/kicad-pad-source-evidence/v1",
        "source_sha256": before,
        "native_uuid": native_uuid,
        "pad_number": _atom(pad[1]),
        "pad_kind": _atom(pad[2]).lower(),
        "shape": _atom(pad[3]).lower(),
        "at_local_mm": [_number(at[1], "pad position"), _number(at[2], "pad position")],
        "rotation_deg": _number(at[3], "pad rotation") if len(at) == 4 else 0.0,
        "size_mm": size_xy,
        "drill_shape": "circle",
        "drill_size_mm": [drill_diameter, drill_diameter],
        "drill_offset_mm": offset_xy,
        "layers": [_atom(value) for value in layers[1:]],
        "net_code": net_code,
        "net_name": net_name,
        "remove_unused_layers": removal_value,
        "padstack_geometry": "uniform_implicit",
    }
    _require(hashlib.sha256(source.read_bytes()).hexdigest() == before, "Source changed during native inspection")
    return evidence


def _inventory_drill(pad, kind):
    drill = _one(pad, "drill", required=False)
    if drill is None:
        _require(kind in {"smd", "connect"}, "Native through-hole pad requires a drill")
        return "none", [0.0, 0.0], [0.0, 0.0]
    _require(kind in {"thru_hole", "np_thru_hole"}, "Native surface pad cannot declare a drill")
    atoms = [item for item in drill[1:] if not isinstance(item, list)]
    nodes = [item for item in drill[1:] if isinstance(item, list)]
    _require(all(item and item[0] == "offset" for item in nodes), "Unsupported native drill declaration")
    oval = bool(atoms) and atoms[0] == "oval"
    _require(len(atoms) == (3 if oval else 1), "Malformed native circular/oval drill grammar")
    _require(drill[1:1 + len(atoms)] == atoms, "Malformed native drill attribute order")
    dimensions = atoms[1:] if oval else atoms * 2
    dimensions = [_number(value, "drill size") for value in dimensions]
    _require(all(value > 0 for value in dimensions), "Native drill dimensions must be positive")
    offset = _one(drill, "offset", required=False)
    xy = [0.0, 0.0]
    if offset is not None:
        _require(len(offset) == 3, "Malformed native drill offset")
        xy = [_number(value, "drill offset") for value in offset[1:]]
    _require(xy == [0.0, 0.0], "Native offset drills are unsupported")
    return "oval" if oval else "circle", dimensions, xy


def _inventory_pad(pad, identity, source_hash):
    _require(len(pad) >= 4 and all(isinstance(value, str) for value in pad[1:4]),
             "Malformed native pad declaration")
    known = {"at", "size", "layers", "drill", "net", "uuid", "tstamp", "locked", "property",
             "padstack", "remove_unused_layers", "remove_unused_layer", "keep_end_layers",
             "roundrect_rratio", "chamfer_ratio", "chamfer", "rect_delta", "options", "primitives",
             "pinfunction", "pintype", "die_length", "solder_mask_margin", "solder_paste_margin",
             "solder_paste_margin_ratio", "clearance", "zone_connect", "thermal_width", "thermal_gap",
             "thermal_bridge_width", "thermal_bridge_angle", "zone_layer_connections", "teardrops"}
    seen = set()
    for item in pad[4:]:
        if not isinstance(item, list):
            _require(item == "locked" and item not in seen, "Unsupported native pad flag")
            seen.add(item)
            continue
        _require(item and isinstance(item[0], str) and item[0] in known,
                 "Unsupported native pad geometry metadata")
        _require(item[0] not in seen, f"Ambiguous native {item[0]} declaration")
        seen.add(item[0])
    _require(_one(pad, "padstack", required=False) is None, "Per-layer native padstack geometry is unsupported")
    policies = {}
    for name in ("remove_unused_layers", "remove_unused_layer", "keep_end_layers"):
        value = _one(pad, name, required=False)
        _require(value is None or len(value) == 2 and value[1] == "no",
                 "Enabled native layer removal/retention is unsupported")
        policies[name] = "absent" if value is None else "no"
    _require(not {"remove_unused_layer", "remove_unused_layers"}.issubset(seen),
             "Ambiguous native layer removal declaration")
    kind, shape = _atom(pad[2]).lower(), _atom(pad[3]).lower()
    _require(kind in {"smd", "connect", "thru_hole", "np_thru_hole"}, "Unsupported native pad type")
    _require(shape in {"circle", "rect", "oval", "trapezoid", "roundrect", "custom"},
             "Unsupported native pad shape")
    at, size, layers = (_one(pad, name) for name in ("at", "size", "layers"))
    _require(len(at) in (3, 4) and len(size) == 3 and len(layers) >= 2
             and all(isinstance(item, str) and _atom(item) for item in layers[1:]),
             "Incomplete native pad geometry")
    layer_names = [_atom(item) for item in layers[1:]]
    _require(len(set(layer_names)) == len(layer_names), "Duplicate native pad layers")
    sizes = [_number(value, "pad size") for value in size[1:]]
    _require(all(value > 0 for value in sizes), "Native pad size must be positive")
    drill_shape, drill_size, offset = _inventory_drill(pad, kind)
    net = _one(pad, "net", required=False)
    _require(net is None or len(net) in (2, 3) and all(isinstance(v, str) for v in net[1:]),
             "Malformed native pad net")
    net_code = _atom(net[1]) if net is not None and len(net) == 3 else None
    _require(net_code is None or net_code.isascii() and net_code.isdigit(), "Malformed native pad net code")
    result = {"native_uuid": identity, "source_sha256": source_hash, "pad_number": _atom(pad[1]),
              "pad_kind": kind, "shape": shape,
              "at_local_mm": [_number(value, "pad position") for value in at[1:3]],
              "rotation_deg": _number(at[3], "pad rotation") if len(at) == 4 else 0.0,
              "size_mm": sizes, "drill_shape": drill_shape, "drill_size_mm": drill_size,
              "drill_offset_mm": offset, "layers": layer_names, "net_code": net_code,
              "net_name": _atom(net[-1]) if net is not None else "",
              "remove_unused_layers": policies["remove_unused_layers"],
              "keep_end_layers": policies["keep_end_layers"], "padstack_geometry": "uniform_implicit"}
    for name in ("roundrect_rratio", "chamfer_ratio"):
        value = _one(pad, name, required=False)
        if value is not None:
            _require(len(value) == 2, "Malformed native shape ratio")
            ratio = _number(value[1], name)
            _require(0 <= ratio <= 1, "Invalid native shape ratio")
            result[name] = ratio
    chamfer = _one(pad, "chamfer", required=False)
    if chamfer is not None:
        corners = chamfer[1:]
        _require(corners and all(isinstance(c, str) and c in {"top_left", "top_right", "bottom_left", "bottom_right"}
                                for c in corners) and len(set(corners)) == len(corners), "Invalid native chamfer")
        result["chamfer"] = list(corners)
    delta = _one(pad, "rect_delta", required=False)
    if delta is not None:
        _require(len(delta) == 3, "Malformed native trapezoid delta")
        result["rect_delta_mm"] = [_number(v, "trapezoid delta") for v in delta[1:]]
    return result


def _inventory_via(via, identity, source_hash):
    # Official KiCad Board File Format, Track Via (reviewed 2026-10-23):
    # https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/index.html
    known = {"at", "size", "drill", "layers", "net", "uuid", "tstamp", "locked", "free",
             "remove_unused_layers", "keep_end_layers"}
    seen, declared_type = set(), None
    flags = {"locked": False, "free": False}
    for index, item in enumerate(via[1:], 1):
        if not isinstance(item, list):
            _require(index == 1 and item in {"blind", "micro"}, "Unsupported native via type or flag")
            declared_type = item
            continue
        _require(item and isinstance(item[0], str) and item[0] in known,
                 "Unsupported native via geometry metadata")
        name = item[0]
        _require(name not in seen, f"Ambiguous native via {name} declaration")
        seen.add(name)
        if name in {"locked", "free"}:
            _require(len(item) == 1 or len(item) == 2 and item[1] in {"yes", "no"},
                     "Malformed native via flag")
            flags[name] = len(item) == 1 or item[1] == "yes"
        if name in {"remove_unused_layers", "keep_end_layers"}:
            _require(len(item) == 2 and item[1] == "no", "Enabled native via layer removal/retention is unsupported")
    at, size, drill, layers, net = (_one(via, key) for key in ("at", "size", "drill", "layers", "net"))
    _require(len(at) == 3 and len(size) == 2 and len(drill) == 2 and len(layers) == 3
             and len(net) == 2, "Malformed native via position, dimensions, span or net")
    position = [_number(value, "via position") for value in at[1:]]
    diameter, bore = _number(size[1], "via size"), _number(drill[1], "via drill")
    _require(0 < bore < diameter, "Native cylindrical via requires positive drill smaller than size")
    _require(all(isinstance(value, str) and _atom(value).endswith(".Cu") and "*" not in value
                 for value in layers[1:]), "Native via needs two explicit copper layers")
    span = [_atom(value) for value in layers[1:]]
    _require(span[0] != span[1], "Native via needs two distinct copper layers")
    _require(isinstance(net[1], str), "Malformed native via net code")
    net_code = _atom(net[1])
    _require(net_code.isascii() and net_code.isdigit(), "Malformed native via net code")
    return {"native_uuid": identity, "source_sha256": source_hash, "at_mm": position,
            "size_mm": diameter, "drill_mm": bore, "layers": span,
            "via_kind": declared_type or "through", "net_code": net_code, **flags}


def read_kicad_board_pad_inventory(path, expected_sha256):
    """One bounded parse; all UUID-keyed pads and cylindrical native vias.

    Custom primitive geometry remains owned by the ordinary importer. The
    inventory authenticates pad/via metadata, not complete copper geometry.
    Native grammar: KiCad official S-expression format, Footprint Pad and Pad
    Drill Definition (reviewed 2026-10-23); independently authored adapter.
    https://dev-docs.kicad.org/en/file-formats/sexpr-intro/index.html
    """
    source = Path(path).resolve()
    _require(source.is_file() and source.stat().st_size <= MAX_BOARD_INVENTORY_BYTES,
             "Source file missing or exceeds board inventory byte budget")
    content = source.read_bytes()
    _require(len(content) <= MAX_BOARD_INVENTORY_BYTES, "Source exceeds board inventory byte budget")
    before = hashlib.sha256(content).hexdigest()
    _require(type(expected_sha256) is str and expected_sha256 == before, "Source file hash differs")
    from python.core.board_parser import KicadParser
    # Tokenizer/parser methods are stateless. Bypass __init__, which runs a full
    # normalized import; never parse once per pad or reread unauthenticated text.
    parser = object.__new__(KicadParser)
    tokens = parser.tokenize(content.decode("utf-8"))
    root = parser.parse_sexp(chain(("(",), tokens, (")",)))
    _require(len(root) == 1 and isinstance(root[0], list) and root[0] and root[0][0] == "kicad_pcb",
             "Native inventory requires exactly one KiCad board root")
    pads, vias, pending, visited = {}, {}, [root[0]], 0
    while pending:
        node = pending.pop()
        visited += 1
        _require(visited <= MAX_SEXP_NODES, "Native source S-expression exceeds node budget")
        if not node:
            continue
        if node[0] == "pad" or node[0] == "via":
            identity = _pad_identity(node)
            _require(identity and identity not in pads and identity not in vias,
                     "Native source pad/via UUID is missing or ambiguous")
            if node[0] == "pad":
                pads[identity] = _inventory_pad(node, identity, before)
            else:
                vias[identity] = _inventory_via(node, identity, before)
        pending.extend(item for item in node if isinstance(item, list))
    _require(hashlib.sha256(source.read_bytes()).hexdigest() == before, "Source changed during native inspection")
    return {"contract": "spike/kicad-board-pad-inventory/v1", "source_sha256": before,
            "pads": pads, "pad_count": len(pads), "vias": vias, "via_count": len(vias)}
