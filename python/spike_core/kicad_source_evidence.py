# SPDX-License-Identifier: Apache-2.0
"""Bounded native KiCad evidence for source-authenticated solver adapters.

This auxiliary importer adapter is intentionally narrower than
``kicad_importer``.  Parser objects remain local; callers receive only plain,
canonical data for one UUID-selected pad.
"""
from __future__ import annotations

import hashlib
import math
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


MAX_SOURCE_BYTES = 32 * 1024 * 1024
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
