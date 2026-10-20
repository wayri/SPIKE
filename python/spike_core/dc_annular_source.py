# SPDX-License-Identifier: Apache-2.0
"""Pinned native circular-pad geometry, never an inferred terminal footprint."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .kicad_importer import import_kicad_design
from .kicad_source_evidence import read_kicad_pad_source_evidence


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "Finite explicit source model value required")
    return float(value)


def bind_annular_pad_source(path, expected_sha256, pad_id, layer, slab_faces_mm, conductivity_s_m):
    """Bind an isolated pad annulus; slab/material are supplied assumptions."""
    path = Path(path).resolve()
    require(path.is_file() and path.stat().st_size <= 32*1024*1024, "Source file missing or exceeds budget")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    require(type(expected_sha256) is str and expected_sha256 == before, "Source file hash differs")
    design = import_kicad_design(str(path))
    require(design.units == "mm", "Source geometry must use mm")
    selected = [p for p in design.pads if p.get("id") == pad_id]
    require(len(selected) == 1, "Select one exact source pad ID")
    pad = selected[0]
    native_id = pad.get("source_native_uuid", pad.get("uuid"))
    require(type(native_id) is str and bool(native_id), "Native pad identity required")
    native = read_kicad_pad_source_evidence(path, before, native_id)
    require(pad.get("type") == "thru_hole" and pad.get("pad_kind", "thru_hole") == "thru_hole"
            and pad.get("plated", True) is True, "Source must explicitly denote plated through-hole copper")
    require(pad.get("shape") == "circle" and pad.get("drill_shape") == "circle", "Only circular land and bore are admitted")
    size, drill = pad.get("size"), pad.get("drill_size")
    require(type(size) in (tuple, list) and len(size) == 2 and type(drill) in (tuple, list) and len(drill) == 2,
            "Source needs complete land/drill dimensions")
    sx, sy = [number(v) for v in size]; dx, dy = [number(v) for v in drill]
    require(sx == sy and dx == dy and 0 < dx < sx, "Source annulus dimensions differ or collapse")
    offset = pad.get("drill_offset", pad.get("drill_offset_mm", (0., 0.)))
    require(type(offset) in (tuple, list) and len(offset) == 2 and all(number(v) == 0 for v in offset),
            "Offset drills are not coaxial annuli")
    copper = [p["name"] for p in design.layers if str(p.get("name", "")).endswith(".Cu")]
    source_layers = pad.get("layers", [])
    require(layer in copper and (layer in source_layers or "*.Cu" in source_layers
            or "F&B.Cu" in source_layers and layer in ("F.Cu", "B.Cu")),
            "Source pad has no requested copper layer")
    require(native["pad_number"] == pad.get("name")
            and native["pad_kind"] == pad.get("pad_kind") == pad.get("type")
            and native["shape"] == pad.get("shape"), "Native and normalized pad type/shape differ")
    require(native["size_mm"] == [sx, sy] and native["drill_size_mm"] == [dx, dy],
            "Native and normalized pad dimensions differ")
    require(native["layers"] == list(source_layers), "Native and normalized pad layers differ")
    require(type(slab_faces_mm) is list and len(slab_faces_mm) == 2, "Explicit slab faces required")
    z0, z1 = [number(v) for v in slab_faces_mm]
    sigma = number(conductivity_s_m)
    require(z1 > z0 and 1e-6 <= sigma <= 1e12, "Invalid explicit slab/material")
    center = pad.get("at")
    require(type(center) in (tuple, list) and len(center) == 2, "Missing source center")
    center = [number(v) for v in center]
    net = pad.get("net_name")
    require(type(net) is str and bool(net), "Source net must be explicit")
    require(native["net_name"] == net, "Native and normalized source nets differ")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == before, "Source changed during import")
    payload = {"contract": "spike/source-annular-pad/v1", "source_path": str(path), "source_sha256": before,
        "pad_id": pad_id, "pad_snapshot": json.loads(json.dumps(pad)), "native_pad_evidence": native,
        "layer": layer, "net": net,
        "center_xy_mm": center, "bore_radius_mm": dx/2, "outer_radius_mm": sx/2,
        "slab_faces_mm": [z0, z1], "conductivity_s_m": sigma,
        "model_assumptions": {"slab_material": "explicit_supplied_not_inferred_stackup",
                              "surrounding_copper": "not_compiled_isolated_pad_only",
                              "electrode": "not_inferred_supply_finite_contact_separately"}}
    return {**payload, "binding_digest": digest(payload)}


def verify_annular_pad_binding(binding):
    require(type(binding) is dict and "binding_digest" in binding, "Source binding required")
    original = {k: v for k, v in binding.items() if k != "binding_digest"}
    require(digest(original) == binding["binding_digest"], "Source binding digest differs")
    actual = bind_annular_pad_source(binding["source_path"], binding["source_sha256"], binding["pad_id"],
        binding["layer"], binding["slab_faces_mm"], binding["conductivity_s_m"])
    require(actual == binding, "Imported source annulus identity differs")


def solve_source_annular_stack(request):
    """Authenticate explicit source bindings before/after a fresh physical solve."""
    from .dc_annular_stack import solve_annular_stack
    bindings = [land["source_binding"] for land in request["lands"]]
    require(all(binding is not None for binding in bindings), "Every source-backed land needs a native binding")
    for binding in bindings:
        verify_annular_pad_binding(binding)
    result = solve_annular_stack(deepcopy(request))
    for binding in bindings:
        verify_annular_pad_binding(binding)
    return {"contract": "spike/source-annular-stack-run/v1", "source_files_revalidated": True,
            "production_qualified": False, "result": result}
