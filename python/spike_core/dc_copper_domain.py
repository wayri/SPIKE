# SPDX-License-Identifier: Apache-2.0
"""Source-bound planar copper unions for the experimental RT0 density path.

No branch pseudo-volume, area clipping, disconnected-component removal or
implicit terminal footprint is used. Circular outlines are inscribed and drill
voids circumscribed with 128 sides, independently of the requested mesh size.
Barrels are reported separately: this planar adapter cannot qualify their 3D
landing overlap or determine a source/load electrode footprint.
"""
from __future__ import annotations

from math import cos, isfinite, pi

from .hybrid_mesh import (
    COPPER_CONDUCTIVITY_S_M, _copper_stack, _net, _pad_has_drill, _pad_layers,
    _pad_local_to_world, _pad_drill_size, _pad_drill_shape, _circumscribed_shape_polygon,
)


def _admit_pad_kind(pad, drilled):
    """A bore is not plating evidence; contradictory pad kinds fail closed."""
    raw = str(pad.get("type", "")).strip().lower()
    normalized = str(pad.get("pad_kind", "")).strip().lower()
    if raw and normalized and raw != normalized:
        raise ValueError("Complete copper pad kind metadata is contradictory")
    kind = normalized or raw
    if kind and kind not in {"smd", "connect", "thru_hole", "np_thru_hole"}:
        raise ValueError("Complete copper pad kind is unsupported")
    if drilled and kind not in {"thru_hole", "np_thru_hole"}:
        raise ValueError("Complete copper drilled pad needs an explicit through-hole kind")
    plated = pad.get("plated")
    if plated is not None and (not isinstance(plated, bool) or
            kind == "np_thru_hole" and plated or kind == "thru_hole" and not plated):
        raise ValueError("Complete copper pad plating metadata is contradictory")
    return kind


def explicit_terminal_contacts(spec):
    """Require user-supplied fixed physical footprints, not mesh-sized patches."""
    from shapely.geometry import Point, Polygon
    contacts = []
    for role, items in (("source",spec.sources),("load",spec.loads)):
        for index,item in enumerate(items):
            identity = str(item.get("id",f"{role}-{index+1}"))
            points = item.get("contact_polygon_mm")
            if points is None:
                raise ValueError(f"{identity}: physical contact footprint is unspecified; position-only terminals do not define finite-area RT0 injection")
            if not isinstance(points,(list,tuple)) or not 3 <= len(points) <= 4096:
                raise ValueError(f"{identity}: physical contact footprint vertex budget exceeded")
            try:
                shape = Polygon(points)
            except (TypeError,ValueError) as error:
                raise ValueError(f"{identity}: malformed physical contact footprint") from error
            if not shape.is_valid or shape.is_empty or shape.area <= 0:
                raise ValueError(f"{identity}: invalid physical contact footprint")
            if item.get("position_mm") is not None and not shape.covers(Point(item["position_mm"])):
                raise ValueError(f"{identity}: footprint does not cover its supplied terminal position")
            net = str(item.get("net",spec.net_names[0] if len(spec.net_names)==1 else ""))
            layer = str(item.get("layer",""))
            if not net or not layer:
                raise ValueError(f"{identity}: finite contacts need explicit net and layer")
            contacts.append({"id":identity,"layer":layer,"net":net,"geometry":shape,"role":role})
    return contacts


def source_copper_groups(design, selected_nets):
    """Return complete selected planar unions and explicit axial-source inventory.

    Finite straight tracks, filled polygons, admitted standard/custom SMD pads,
    and centered circular/oval-drill lands are supported. Arcs, ambiguous
    source fills and unsupported pad metadata fail closed.
    """
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    from .quasistatic_copper_area import _source_polygon
    from .hybrid_owned_copper import custom_outline
    if design.units != "mm":
        raise ValueError("Complete copper domain requires millimetres")
    layers,z,thickness = _copper_stack(design)
    records,holes = {},{}
    selected = set(selected_nets)
    axial = []
    if sum(len(getattr(design,name)) for name in ("pads","vias","tracks","zones")) > 100000:
        raise ValueError("Complete copper source-object work budget exceeded")
    # Drills are physical voids, independent of the electrical net selected.
    # In particular NPTH/foreign-net drills must cut selected track envelopes.
    global_holes = {layer:[] for layer in layers}
    for pad in design.pads:
        raw = pad.get("drill_size",pad.get("drill_size_mm"))
        if isinstance(raw,dict):
            raw = (raw.get("x",raw.get("width")),raw.get("y",raw.get("height")))
        if raw is None:
            raw = (pad.get("drill",0),)*2
        try:
            if len(raw)!=2 or any(isinstance(v,bool) for v in raw):
                raise ValueError
            dw,dh = (float(v) for v in raw)
            if not all(isfinite(v) and v >= 0 for v in (dw,dh)) or (min(dw,dh)==0<max(dw,dh)):
                raise ValueError
        except (TypeError,ValueError) as error:
            raise ValueError("Complete copper drill metadata is malformed") from error
        if dw == dh == 0:
            continue
        _admit_pad_kind(pad, True)
        if pad.get("drill_shape") not in (None,"","circle","oval"):
            raise ValueError("Complete copper drill shape is unsupported")
        if pad.get("drill_shape") == "circle" and abs(dw-dh)>1e-12:
            raise ValueError("Complete copper circular drill has unequal dimensions")
        offset = pad.get("drill_offset",pad.get("drill_offset_mm",(0,0)))
        if (not all(isfinite(v) and v > 0 for v in (dw,dh)) or len(offset)!=2
                or any(not isfinite(float(v)) or float(v)!=0 for v in offset)):
            raise ValueError("Complete copper drill metadata is unsupported")
        hole = Polygon([_pad_local_to_world(pad,*p) for p in
            _circumscribed_shape_polygon(_pad_drill_shape(pad),dw,dh,128)])
        # Through-hole pads/NPTH bores pierce the complete PCB stack, not only
        # layers on which their optional annular copper is drawn.
        for layer in layers:
            global_holes[layer].append(hole)
    for via in design.vias:
        drill = float(via.get("drill",0))
        span = via.get("layers",("F.Cu","B.Cu"))
        if not isfinite(drill) or drill <= 0 or len(span)!=2 or any(layer not in layers for layer in span):
            raise ValueError("Complete copper via drill/span metadata is invalid")
        hole = Point(via["at"]).buffer(drill/2/cos(pi/128),quad_segs=32)
        first,last = sorted(layers.index(layer) for layer in span)
        for layer in layers[first:last+1]:
            global_holes[layer].append(hole)

    def add(layer,net,shape,source,kind):
        if layer not in layers:
            raise ValueError(f"{source}: copper layer has no physical stack position")
        if not shape.is_valid or shape.is_empty or shape.area <= 0:
            raise ValueError(f"{source}: invalid source copper")
        records.setdefault((layer,net),[]).append((shape,source,kind))

    for index,track in enumerate(design.tracks):
        net = _net(track)
        if selected and net not in selected:
            continue
        _source_polygon("track",track)  # Existing strict straight-track admission.
        width = float(track["width"])
        shape = LineString([track["start"],track["end"]]).buffer(width/2,quad_segs=32)
        add(track["layer"],net,shape,str(track.get("id",f"track-{index}")),"track")
    for index,zone in enumerate(design.zones):
        net = _net(zone)
        if selected and net not in selected:
            continue
        shape = Polygon(_source_polygon("zone",zone))
        add(zone["layer"],net,shape,str(zone.get("id",f"zone-{index}")),"zone")
    for index,pad in enumerate(design.pads):
        net = _net(pad)
        if selected and net not in selected:
            continue
        source = str(pad.get("id",f"pad-{index}"))
        kind = _admit_pad_kind(pad, _pad_has_drill(pad))
        if kind == "np_thru_hole":
            raise ValueError(f"{source}: selected NPTH copper support is unspecified; no annular land or plated barrel is inferred")
        shape_name = str(pad.get("shape","rect"))
        if shape_name == "custom":
            shape = Polygon([_pad_local_to_world(pad,*p) for p in custom_outline(pad)])
        else:
            outer = dict(pad,drill=0)
            outer.pop("drill_size",None)
            outer.pop("drill_size_mm",None)
            shape = Polygon(_source_polygon("pad",outer))
        drill = None
        if _pad_has_drill(pad):
            dw,dh = _pad_drill_size(pad)
            drill_shape = _pad_drill_shape(pad)
            if drill_shape not in {"circle","oval"}:
                raise ValueError(f"{source}: complete RT0 drill shape is not admitted")
            offset = pad.get("drill_offset",pad.get("drill_offset_mm",(0,0)))
            if len(offset)!=2 or any(not isfinite(float(v)) or float(v)!=0 for v in offset):
                raise ValueError(f"{source}: drill offset is not admitted")
            drill = Polygon([_pad_local_to_world(pad,*p) for p in
                _circumscribed_shape_polygon(drill_shape,dw,dh,128)])
            if not shape.contains(drill):
                raise ValueError(f"{source}: bounded drill leaves no contained annular land")
            axial.append({"source_id":source,"kind":"pad_barrel","drill_size_mm":[dw,dh],
                "status":"axial contact and 3D landing support not compiled"})
        for layer in _pad_layers(pad,layers):
            add(layer,net,shape if drill is None else shape.difference(drill),source,"pad")
            if drill is not None:
                holes.setdefault((layer,net),[]).append(drill)
    for index,via in enumerate(design.vias):
        net = _net(via)
        if selected and net not in selected:
            continue
        source = str(via.get("id",f"via-{index}"))
        drill,size = float(via.get("drill",0)),float(via.get("size",0))
        if not all(isfinite(v) for v in (drill,size)) or not 0<drill<size:
            raise ValueError(f"{source}: invalid circular via land/drill")
        center = via["at"]
        hole = Point(center).buffer(drill/2/cos(pi/128),quad_segs=32)
        land = Point(center).buffer(size/2,quad_segs=32).difference(hole)
        span = via.get("layers",("F.Cu","B.Cu"))
        if len(span)!=2 or any(layer not in layers for layer in span):
            raise ValueError(f"{source}: invalid via layer span")
        first,last = sorted(layers.index(layer) for layer in span)
        for layer in layers[first:last+1]:
            add(layer,net,land,source,"via")
            holes.setdefault((layer,net),[]).append(hole)
        axial.append({"source_id":source,"kind":"via","drill_mm":drill,
            "status":"axial contact and 3D landing support not compiled"})
    groups = {}
    global_voids = {layer:unary_union(items) for layer,items in global_holes.items()}
    for key,items in sorted(records.items()):
        shape = unary_union([item[0] for item in items])
        shape = shape.difference(global_voids[key[0]])
        groups[key] = {"geometry":shape,"thickness_mm":thickness[key[0]],
            "conductivity_s_m":COPPER_CONDUCTIVITY_S_M,"z_mm":z[key[0]],
            "source_inventory":[{"id":source,"kind":kind} for _,source,kind in items],
            "curve_segments":128,"source_union_area_mm2":shape.area,
            "drill_void_area_mm2":global_voids[key[0]].area,
            "scope":"planar copper only; axial support is not compiled"}
    return groups,axial
