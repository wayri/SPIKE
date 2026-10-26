# SPDX-License-Identifier: Apache-2.0
"""Explicit full-pad electrodes and barrel-gap models from authenticated boards."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import math
from pathlib import Path

from .dc_board_filled import prepare_board_copper_groups
from ...geometry_meshing.preparation.hybrid_mesh import _copper_stack, _net, _pad_has_drill, _pad_drill_size, _pad_drill_shape, _pad_layers, _pad_local_to_world, _circumscribed_shape_polygon


def require(condition, message):
    if not condition: raise ValueError(message)


def pad_surface(pad):
    """Same bounded source perimeter convention as complete planar copper."""
    from shapely.geometry import Polygon
    from ..pdn.quasistatic_copper_area import _source_polygon
    from .hybrid_owned_copper import custom_outline
    if pad.get("shape") == "custom":
        shape = Polygon([_pad_local_to_world(pad, *p) for p in custom_outline(pad)])
    else:
        outer = dict(pad, drill=0)
        outer.pop("drill_size", None); outer.pop("drill_size_mm", None)
        shape = Polygon(_source_polygon("pad", outer))
    if _pad_has_drill(pad):
        dw, dh = _pad_drill_size(pad)
        hole = Polygon([_pad_local_to_world(pad, *p) for p in
                        _circumscribed_shape_polygon(_pad_drill_shape(pad), dw, dh, 128)])
        require(shape.contains(hole), "Full-pad electrode has no contained drill void")
        shape = shape.difference(hole)
    require(shape.is_valid and not shape.is_empty and shape.area > 0, "Full-pad electrode geometry is invalid")
    return shape


def prepare_board_sources(design, *, net_names, electrodes, plating_thickness_mm, conductivity_s_m):
    """Prepare inert geometry; source-file authentication belongs to the wrapper."""
    from shapely.geometry import Point, Polygon
    require(type(net_names) is list and bool(net_names) and len(net_names) == len(set(net_names))
            and all(type(n) is str and n for n in net_names), "Select explicit distinct source nets")
    for value, low, high in ((plating_thickness_mm, 1e-6, 1.), (conductivity_s_m, 1e-6, 1e12)):
        require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
                "Explicit finite barrel plating and conductivity required")
    require(type(electrodes) is list and 2 <= len(electrodes) <= 4096, "Explicit full-pad electrodes required")
    groups, axial, fill_evidence = prepare_board_copper_groups(design, net_names)
    layers, heights, thickness = _copper_stack(design)
    for group in groups.values(): group["conductivity_s_m"] = conductivity_s_m
    pads = {p["id"]: p for p in design.pads}
    require(len(pads) == len(design.pads), "Source pad identities are ambiguous")
    contacts, contact_evidence, names = [], [], set()
    for electrode in electrodes:
        require(type(electrode) is dict and set(electrode) == {"id", "pad_id", "layer", "side", "current_a"},
                "Full-pad electrode needs explicit identity, source pad, layer, side and inward current")
        identity, pid, layer = electrode["id"], electrode["pad_id"], electrode["layer"]
        require(type(identity) is str and 0 < len(identity) <= 128 and identity not in names and pid in pads,
                "Duplicate electrode or missing exact source pad ID")
        require(electrode["side"] in ("top", "bottom")
                and type(electrode["current_a"]) in (int, float) and math.isfinite(electrode["current_a"])
                and abs(electrode["current_a"]) <= 1e9, "Finite electrode side/current is invalid")
        names.add(identity); pad = pads[pid]; net = _net(pad)
        require(net in net_names and layer in _pad_layers(pad, layers), "Full-pad electrode net/layer differs")
        shape = pad_surface(pad)
        require((layer, net) in groups and groups[(layer, net)]["geometry"].covers(shape),
                "Full-pad electrode leaves selected physical copper")
        contacts.append({"id": identity, "layer": layer, "net": net, "side": electrode["side"],
                         "geometry": shape, "current_a": electrode["current_a"]})
        contact_evidence.append({"id": identity, "pad_id": pid, "component_pad": pad.get("component_pad"),
            "net": net, "layer": layer, "side": electrode["side"], "area_mm2": shape.area,
            "geometry_wkb_sha256": hashlib.sha256(shape.wkb).hexdigest(),
            "hole_count": sum(len(p.interiors) for p in (shape.geoms if shape.geom_type == "MultiPolygon" else [shape])),
            "model": "explicit_full_imported_pad_copper_including_drill_void"})
    records = {str(p["id"]): ("pad", p) for p in design.pads}
    records.update({str(v["id"]): ("via", v) for v in design.vias})
    require(len(records) == len(design.pads)+len(design.vias), "Pad/via source IDs collide")
    barrels = []
    for source in axial:
        sid = source["source_id"]; kind, item = records[sid]; net = _net(item)
        if kind == "pad":
            require(item.get("type") == "thru_hole", "Axial pad is not explicitly plated")
            dw, dh = _pad_drill_size(item)
            hole = Polygon([_pad_local_to_world(item, *p) for p in
                            _circumscribed_shape_polygon(_pad_drill_shape(item), dw, dh, 128)])
            require(dw == dh and _pad_drill_shape(item) == "circle", "Only centered circular barrel walls are admitted")
            outer = Point(item["at"]).buffer(dw/2+plating_thickness_mm, quad_segs=32)
            span = _pad_layers(item, layers)
        else:
            drill = float(item["drill"])
            hole = Point(item["at"]).buffer(drill/2/math.cos(math.pi/128), quad_segs=32)
            outer = Point(item["at"]).buffer(drill/2+plating_thickness_mm, quad_segs=32)
            pair = item["layers"]; a, b = sorted(layers.index(name) for name in pair)
            span = layers[a:b+1]
        require(outer.contains(hole), "Explicit barrel wall collapses under curve approximation")
        ring = outer.difference(hole)
        selected_layers = sorted(span, key=lambda layer: heights[layer])
        require(len(selected_layers) >= 2, "A barrel needs at least two supported copper layers")
        # Do not bridge missing layer evidence or overlap a land slab.
        for low, high in zip(selected_layers, selected_layers[1:]):
            require((low, net) in groups and (high, net) in groups, "Barrel lacks selected same-net landing layers")
            z0 = heights[low]+thickness[low]/2; z1 = heights[high]-thickness[high]/2
            require(z1 > z0, "Barrel gap has nonpositive length")
            barrels.append({"id": sid+":"+low+":"+high, "source_id": sid, "net": net,
                            "geometry": ring, "z_min_mm": z0, "z_max_mm": z1,
                            "conductivity_s_m": conductivity_s_m})
    return {"groups": groups, "barrels": barrels, "contacts": contacts,
            "expected_axial_source_ids": [row["source_id"] for row in axial],
            "electrode_evidence": contact_evidence,
            "source_fill_evidence": fill_evidence,
            "model_assumptions": {"plating_thickness_mm": plating_thickness_mm,
                "conductivity_s_m": conductivity_s_m, "curve_segments": 128,
                "layer_geometry": "source profile through existing copper_stack_profile; inspect its provenance",
                "electrodes": "explicit_full_pad_neumann_flux_not_point_or_equipotential",
                "scope": "selected conductor model; not original study or full-board qualification"}}


def authenticate_board_pads(design, inventory):
    """Verify normalized geometry has not hidden native offset/padstack policies."""
    native = inventory["pads"]; selected = {}
    for pad in design.pads:
        uid = pad.get("source_native_uuid", pad.get("uuid"))
        require(uid in native and uid not in selected, "Normalized source pad UUID is missing or ambiguous")
        selected[uid] = pad; record = native[uid]
        require(record["drill_offset_mm"] == [0., 0.]
                and record["padstack_geometry"] == "uniform_implicit"
                and record["remove_unused_layers"] in ("absent", "no")
                and record["keep_end_layers"] in ("absent", "no"), "Native offset/padstack/layer policy is unsupported")
        require(record["pad_kind"] == pad.get("type") == pad.get("pad_kind")
                and record["shape"] == pad.get("shape")
                and record["size_mm"] == list(pad["size"])
                and record["layers"] == list(pad["layers"])
                and record["net_name"] == (pad.get("net_name") or ""), "Native/normalized board pad geometry differs")
        if _pad_has_drill(pad):
            require(record["drill_size_mm"] == list(_pad_drill_size(pad))
                    and record["drill_shape"] == _pad_drill_shape(pad), "Native/normalized bore differs")
        else: require(record["drill_size_mm"] == [0., 0.], "Native drill was omitted by normalization")
        for field in ("roundrect_rratio", "chamfer_ratio", "chamfer"):
            if field in record:
                require(record[field] == pad.get(field), "Native pad shape parameters differ from normalization")
        require(not any(record.get("rect_delta_mm", [0., 0.])), "Native trapezoid pad geometry is unsupported")
    require(set(selected) == set(native), "Native pad inventory is incomplete in normalized board")
    via_inventory = inventory["vias"]; seen = set()
    for via in design.vias:
        uid = via.get("source_native_uuid", via.get("uuid"))
        require(uid in via_inventory and uid not in seen, "Normalized native via UUID is missing or ambiguous")
        seen.add(uid); record = via_inventory[uid]
        require(record.get("drill_offset_mm", [0., 0.]) == [0., 0.]
                and record.get("padstack_geometry", "uniform_implicit") == "uniform_implicit"
                and record.get("remove_unused_layers", "absent") in ("absent", "no")
                and record.get("keep_end_layers", "absent") in ("absent", "no"),
                "Native via offset/padstack/layer policy is unsupported")
        require(record["via_kind"] == "through" and via.get("type") == "through",
                "Native blind/microvia volume authentication is unsupported")
        require(record["at_mm"] == list(via["at"]) and record["size_mm"] == via["size"]
                and record["drill_mm"] == via["drill"] and record["layers"] == list(via["layers"])
                and record["net_code"] == str(via["net_id"]), "Native/normalized via geometry differs")
    require(seen == set(via_inventory), "Native via inventory is incomplete in normalized board")


def prepare_source_board(path, expected_sha256, *, net_names, electrodes,
                         plating_thickness_mm, conductivity_s_m):
    from ....kicad_importer import import_kicad_design
    from ....kicad_source_evidence import read_kicad_board_pad_inventory
    source = Path(path).resolve()
    require(source.is_file() and source.stat().st_size <= 64*1024*1024, "Source board exceeds64 MiB or is missing")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    require(before == expected_sha256, "Source board hash differs")
    inventory = read_kicad_board_pad_inventory(source, before)
    design = import_kicad_design(str(source)); authenticate_board_pads(design, inventory)
    prepared = prepare_board_sources(design, net_names=net_names, electrodes=deepcopy(electrodes),
        plating_thickness_mm=plating_thickness_mm, conductivity_s_m=conductivity_s_m)
    require(hashlib.sha256(source.read_bytes()).hexdigest() == before, "Source changed during board preparation")
    prepared["source_evidence"] = {"source_path": str(source), "source_sha256": before,
        "native_pad_count": inventory["pad_count"], "native_via_count": inventory["via_count"], "net_names": deepcopy(net_names),
        "electrodes": deepcopy(electrodes), "plating_thickness_mm": plating_thickness_mm,
        "conductivity_s_m": conductivity_s_m, "native_pad_inventory_authenticated": True,
        "native_via_inventory_authenticated": True}
    return prepared
