# SPDX-License-Identifier: Apache-2.0
"""Lossless source-level preparation of nonconformal two-conductor routes.

This is NOT a channel extractor. Exact rational projected overlaps are candidate
geometry only. Every source and every straight-track parameter interval survives;
no candidate is silently promoted to a physical coupled-line section.
"""
from __future__ import annotations

from dataclasses import asdict
from fractions import Fraction
import json
from math import dist, fsum, isfinite
from typing import Any, Callable, Mapping

from .si_channel import SiChannelError, _selector
from ....spider_v2 import SpiDeRV2
from ....spider_v2_schema import content_digest

MAX_SOURCES = 8192
MAX_PAIR_COMPARISONS = 262144
MAX_PARTITIONS = 65536
MAX_CANDIDATES = 32768
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise SiChannelError("Geometry dimensions must be numeric millimetres.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise SiChannelError("Geometry dimensions must be finite and bounded to 1e6 mm.") from error
    if not isfinite(result) or abs(result) > 1e6:
        raise SiChannelError("Geometry dimensions must be finite and bounded to 1e6 mm.")
    return result


def _point(value: Any) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise SiChannelError("Geometry points require exactly two millimetre coordinates.")
    return tuple(_number(item) for item in value)


def _rpoint(value: Any) -> tuple[Fraction, Fraction]:
    # Exactly preserve admitted binary values. Never snap or limit denominators.
    return tuple(Fraction(item) for item in _point(value))


def _difference(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _fraction(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def _overlap(a: Any, b: Any):
    if a.layer_id != b.layer_id:
        return None
    p, q = _rpoint(a.start_mm), _rpoint(b.start_mm)
    d, e = _difference(_rpoint(a.end_mm), p), _difference(_rpoint(b.end_mm), q)
    if _cross(d, e) != 0:
        return None
    dd, ee = _dot(d, d), _dot(e, e)
    projected = [_dot(_difference(point, p), d) / dd
                 for point in (q, _rpoint(b.end_mm))]
    lo, hi = max(Fraction(0), min(projected)), min(Fraction(1), max(projected))
    if lo >= hi:
        return None
    ends = [(p[0] + u * d[0], p[1] + u * d[1]) for u in (lo, hi)]
    vlo, vhi = sorted(_dot(_difference(point, q), e) / ee for point in ends)
    separation_squared = _cross(_difference(q, p), d) ** 2 / dd
    width = (Fraction(_number(a.width_mm)) + Fraction(_number(b.width_mm))) / 2
    return lo, hi, vlo, vhi, separation_squared, separation_squared <= width * width


def _topology(tracks, vias, layers):
    """Endpoint incidence only; not a copper-contact or native DRC proof."""
    edges = []
    for track in tracks:
        edges.append((track.id, (track.layer_id, *_point(track.start_mm)),
                      (track.layer_id, *_point(track.end_mm))))
    for via in vias:
        first, last = layers[via.start_layer_id], layers[via.end_layer_id]
        lo, hi = sorted((first.order, last.order))
        span = sorted((layer for layer in layers.values()
                       if layer.layer_type == "copper" and lo <= layer.order <= hi),
                      key=lambda layer: (layer.order, layer.id))
        for a, b in zip(span, span[1:]):
            edges.append((via.id, (a.id, *_point(via.center_mm)),
                          (b.id, *_point(via.center_mm))))
    adjacency = {}
    for index, (_, a, b) in enumerate(edges):
        adjacency.setdefault(a, []).append(index)
        adjacency.setdefault(b, []).append(index)
    ends = sorted(point for point, indices in adjacency.items() if len(indices) == 1)
    ordered = []
    used = set()
    if len(ends) == 2 and all(len(indices) <= 2 for indices in adjacency.values()):
        cursor = ends[0]
        while True:
            remaining = [i for i in adjacency[cursor] if i not in used]
            if len(remaining) != 1:
                break
            index = remaining[0]
            used.add(index)
            source, a, b = edges[index]
            following = b if cursor == a else a
            ordered.append({"source_id": source, "start": list(cursor), "end": list(following)})
            cursor = following
    complete = bool(edges) and len(used) == len(edges)
    return {"status": "open_endpoint_chain" if complete else "unresolved_endpoint_topology",
            "ordered_edges": ordered if complete else [],
            "endpoint_count": len(ends),
            "branch_vertex_count": sum(len(indices) > 2 for indices in adjacency.values()),
            "scope": "exact_endpoint_incidence_only_not_copper_connectivity"}


def _transitions(sources):
    regions = [{"kind": name[:-1], "source_ids": [item.id], "status": "retained_unextracted_3d_transition"}
               for name in ("vias", "pads", "arcs", "zones", "drills", "castellations") for item in sources[name]]
    adjacency = {}
    for track in sources["tracks"]:
        for point, other in ((track.start_mm, track.end_mm), (track.end_mm, track.start_mm)):
            adjacency.setdefault((track.layer_id, *_point(point)), []).append((track, other))
    for node, entries in sorted(adjacency.items()):
        kind = None
        if len(entries) == 2:
            (a, p), (b, q) = entries
            d, e = _difference(_rpoint(p), _rpoint(node[1:])), _difference(_rpoint(q), _rpoint(node[1:]))
            if _cross(d, e) or _dot(d, e) >= 0:
                kind = "bend_or_reversal"
            elif a.width_mm != b.width_mm:
                kind = "width_step"
        elif len(entries) > 2:
            kind = "endpoint_branch"
        if kind:
            regions.append({"kind": kind, "source_ids": sorted(item.id for item, _ in entries),
                            "layer_id": node[0], "point_mm": list(node[1:]),
                            "status": "retained_unextracted_3d_transition"})
    return regions


def prepare_pair_geometry(design: SpiDeRV2, request: Mapping[str, Any], *,
                          cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Prepare full selected-net geometry without requiring equal segmentation.

    Selectors: signal_net, victim_net, reference_net, reference_layer. Optional
    terminal_pad_ids maps signal/victim to explicitly ordered two-pad ID lists;
    these are source assignments, never inferred physical reference planes.
    """
    allowed = {"signal_net", "victim_net", "reference_net", "reference_layer", "terminal_pad_ids"}
    if not isinstance(request, Mapping) or set(request) - allowed:
        raise SiChannelError("Unknown pair-geometry request fields.")
    if cancel_check is not None and cancel_check():
        raise SiChannelError("Pair geometry preparation cancelled.")
    if any(not isinstance(request.get(key), str) or not request[key].strip()
           for key in ("signal_net", "victim_net", "reference_net", "reference_layer")):
        raise SiChannelError("Pair geometry selectors require nonempty strings.")
    if design.frame.units != "mm":
        raise SiChannelError("Pair geometry requires millimetre canonical coordinates.")
    selected = {key: _selector(request.get(key, ""), design.nets, key)
                for key in ("signal_net", "victim_net", "reference_net")}
    if len({item.id for item in selected.values()}) != 3:
        raise SiChannelError("Signal, victim and reference nets must be distinct.")
    reference_layer = _selector(request.get("reference_layer", ""), design.layers, "reference_layer")
    if len(design.layers) > 256 or len({layer.id for layer in design.layers}) != len(design.layers):
        raise SiChannelError("Layer inventory must be unique and within the 256-layer budget.")
    layers = {layer.id: layer for layer in design.layers}
    if reference_layer.layer_type != "copper":
        raise SiChannelError("Reference layer must be copper.")
    for layer in layers.values():
        _number(layer.z_mm)
        if isinstance(layer.order, bool) or not isinstance(layer.order, int) or abs(layer.order) > 1000000:
            raise SiChannelError("Layer orders must be bounded integers.")
    terminals = request.get("terminal_pad_ids", {})
    if not isinstance(terminals, Mapping) or set(terminals) - {"signal", "victim"}:
        raise SiChannelError("terminal_pad_ids requires signal/victim ID lists.")
    selected_ids = {selected[key].id for key in ("signal_net", "victim_net")}
    collections = {name: sorted((item for item in getattr(design, name) if item.net_id in selected_ids),
                               key=lambda item: item.id)
                   for name in ("tracks", "arcs", "vias", "pads", "zones", "drills", "castellations")}
    if sum(map(len, collections.values())) > MAX_SOURCES:
        raise SiChannelError("Selected source count exceeds pair geometry budget.")
    ids = [item.id for items in collections.values() for item in items]
    if len(ids) != len(set(ids)):
        raise SiChannelError("Selected source IDs must be unique.")
    routes = {}
    for polarity in ("signal", "victim"):
        net = selected[polarity + "_net"]
        sources = {name: [item for item in items if item.net_id == net.id]
                   for name, items in collections.items()}
        tracks, vias = sources["tracks"], sources["vias"]
        if not tracks and not sources["arcs"]:
            raise SiChannelError("Each selected net must contain retained route geometry.")
        for track in tracks + sources["arcs"]:
            if track.layer_id not in layers or layers[track.layer_id].layer_type != "copper":
                raise SiChannelError("Every route source requires an existing copper layer.")
            if _number(track.width_mm) <= 0 or _point(track.start_mm) == _point(track.end_mm):
                raise SiChannelError("Route width and endpoint length must be positive.")
        for arc in sources["arcs"]:
            _point(arc.mid_mm)
        for via in vias:
            _point(via.center_mm)
            if any(layer not in layers or layers[layer].layer_type != "copper"
                   for layer in (via.start_layer_id, via.end_layer_id)):
                raise SiChannelError("Via span requires existing copper layers.")
            if (via.start_layer_id == via.end_layer_id or
                    layers[via.start_layer_id].z_mm == layers[via.end_layer_id].z_mm or
                    layers[via.start_layer_id].order == layers[via.end_layer_id].order or
                    not 0 < _number(via.drill_mm) < _number(via.diameter_mm)):
                raise SiChannelError("Via requires a nonzero span and positive drill below diameter.")
        pads = {pad.id: pad for pad in sources["pads"]}
        terminal_ids = terminals.get(polarity, [])
        if (not isinstance(terminal_ids, (list, tuple)) or
                any(not isinstance(item, str) for item in terminal_ids) or
                (terminal_ids and (len(terminal_ids) != 2 or len(set(terminal_ids)) != 2 or
                                  any(item not in pads for item in terminal_ids)))):
            raise SiChannelError("Each declared terminal pair must name two distinct pads on its net.")
        topology = _topology(tracks, vias, layers)
        if sources["arcs"]:
            topology.update(status="unresolved_arc_endpoint_topology", ordered_edges=[])
        routes[polarity] = {
            "net_id": net.id, "sources": {name: [asdict(item) for item in items] for name, items in sources.items()},
            "straight_centerline_length_mm": fsum(dist(t.start_mm, t.end_mm) for t in tracks),
            "arc_centerline_length_mm": None if sources["arcs"] else 0.0,
            "via_axial_span_mm": fsum(abs(layers[v.start_layer_id].z_mm - layers[v.end_layer_id].z_mm) for v in vias),
            "terminal_pad_ids": list(terminal_ids),
            "terminal_status": "source_assignment_only" if terminal_ids else "not_bound",
            "topology": topology,
            "transition_regions": _transitions(sources),
        }
    signal = [track for track in collections["tracks"] if track.net_id == selected["signal_net"].id]
    victim = [track for track in collections["tracks"] if track.net_id == selected["victim_net"].id]
    if len(signal) * len(victim) > MAX_PAIR_COMPARISONS:
        raise SiChannelError("Pair comparisons exceed geometry work budget.")
    candidates, memberships = [], {track.id: [] for track in signal + victim}
    for a in signal:
        if cancel_check is not None and cancel_check():
            raise SiChannelError("Pair geometry preparation cancelled.")
        for b in victim:
            overlap = _overlap(a, b)
            if overlap is None:
                continue
            lo, hi, vlo, vhi, separation_squared, touching = overlap
            if len(candidates) >= MAX_CANDIDATES:
                raise SiChannelError("Projected candidates exceed geometry output budget.")
            index = len(candidates)
            candidates.append({"candidate_index": index, "signal_track_id": a.id, "victim_track_id": b.id,
                               "signal_interval": [_fraction(lo), _fraction(hi)],
                               "victim_interval": [_fraction(vlo), _fraction(vhi)],
                               "separation_squared_mm2": _fraction(separation_squared),
                               "strip_touch_or_overlap": touching,
                               "status": "geometric_candidate_not_extracted"})
            memberships[a.id].append((lo, hi, index))
            memberships[b.id].append((vlo, vhi, index))
    partitions, association_count = [], 0
    for track in signal + victim:
        if cancel_check is not None and cancel_check():
            raise SiChannelError("Pair geometry preparation cancelled.")
        membership = memberships[track.id]
        cuts = sorted({Fraction(0), Fraction(1)} | {u for lo, hi, _ in membership for u in (lo, hi)})
        starts, stops = {}, {}
        for lo, hi, index in membership:
            starts.setdefault(lo, []).append(index)
            stops.setdefault(hi, []).append(index)
        active = set()
        for lo, hi in zip(cuts, cuts[1:]):
            if len(partitions) >= MAX_PARTITIONS:
                raise SiChannelError("Source partitions exceed geometry output budget.")
            active.difference_update(stops.get(lo, []))
            active.update(starts.get(lo, []))
            association_count += len(active)
            if association_count > MAX_PAIR_COMPARISONS:
                raise SiChannelError("Partition associations exceed geometry output budget.")
            owners = sorted(active)
            length_mm = dist(track.start_mm, track.end_mm) * float(hi - lo)
            if not isfinite(length_mm) or length_mm <= 0:
                raise SiChannelError("Source partition length is not positively representable in millimetres.")
            partitions.append({"track_id": track.id, "interval": [_fraction(lo), _fraction(hi)],
                               "length_mm": length_mm,
                               "candidate_indices": owners,
                               "status": "unpaired" if not owners else "candidate" if len(owners) == 1 else "ambiguous_candidates"})
    reference = selected["reference_net"]
    result = {
        "preparation_version": 1, "status": "geometry_prepared_channel_unextracted",
        "source": asdict(design.source), "design_id": design.design_id,
        "design_digest_sha256": content_digest(design.to_dict()),
        "coordinate_frame": asdict(design.frame), "routes": routes,
        "layer_stack": [asdict(layer) for layer in design.layers],
        "retained_geometry_context": {
            "incomplete_padstack_groups": [asdict(item) for item in design.retained_padstack_occurrence_groups],
            "nonregular_padstack_geometry": asdict(design.retained_nonregular_padstack_geometry)
            if design.retained_nonregular_padstack_geometry is not None else None,
            "standard_contour_land_geometry": asdict(design.retained_standard_contour_land_geometry)
            if design.retained_standard_contour_land_geometry is not None else None,
            "status": "retained_global_context_not_resolved_or_meshed",
        },
        "reference": {"net_id": reference.id, "layer_id": reference_layer.id,
                      "zone_ids": sorted(z.id for z in design.zones if z.net_id == reference.id and reference_layer.id in z.layer_ids),
                      "status": "identity_only_coverage_and_return_connectivity_unverified"},
        "parallel_overlap_candidates": candidates, "track_partitions": partitions,
        "coverage": {"retained_source_count": len(ids), "retained_source_ids": sorted(ids),
                     "all_straight_source_intervals_retained": True,
                     "arc_geometry_retained_without_tessellation": True},
        "unextracted_requirements": ["all_source_field_extraction", "bends_and_nonparallel_fanin_fanout",
                                     "via_pad_and_layer_transitions", "reference_return_and_antipads",
                                     "terminal_reference_planes", "frequency_dependent_materials"],
        "channel_extracted": False, "production_qualified": False, "compliance_status": "not_evaluated",
    }
    result["preparation_digest_sha256"] = content_digest(result)
    if len(json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise SiChannelError("Retained geometry exceeds serialized output budget.")
    return result
