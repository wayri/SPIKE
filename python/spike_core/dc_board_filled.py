# SPDX-License-Identifier: Apache-2.0
"""Source-faithful retraced filled zones for the experimental board DC path."""
from __future__ import annotations

from copy import copy, deepcopy
import hashlib
import json
import math

import numpy as np

from .dc_copper_domain import source_copper_groups
from .filled_copper_path import FilledPathError, prepare_filled_path
from .hybrid_mesh import _net


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value, label):
    _require(isinstance(value, str) and value.strip() and len(value) <= 300, f"Invalid {label}")
    return value


def _source_digest(points):
    try:
        encoded = json.dumps(points, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as error:
        raise ValueError("Filled zone source points must be finite JSON coordinates") from error
    _require(len(encoded) <= 8 * 1024 * 1024, "Filled zone source-point evidence exceeds budget")
    return hashlib.sha256(encoded).hexdigest()


def _overlay_audit(source, represented):
    span = max(source.bounds[2] - source.bounds[0], source.bounds[3] - source.bounds[1])
    tolerance = 128 * np.finfo(float).eps * max(source.area, span * span)
    omitted = float(source.difference(represented).area)
    excess = float(represented.difference(source).area)
    symmetric = float(source.symmetric_difference(represented).area)
    return {"source_minus_triangles_area_mm2": omitted,
            "triangles_minus_source_area_mm2": excess,
            "symmetric_difference_area_mm2": symmetric,
            "admitted_overlay_tolerance_mm2": float(tolerance),
            "accepted": bool(symmetric <= tolerance)}


def _filled_provenance(zone):
    required = ("source_zone_id", "filled_copper_id", "source_fill_group_sha256",
                "source_fill_component_sha256")
    _require(zone.get("source_kind") == "filled_zone"
             and zone.get("source_fill_provenance_complete") is True
             and zone.get("filled_copper_state") == "source_filled"
             and zone.get("source_fill_representation") == "flat_polygon_path",
             "Retraced zone lacks authoritative native filled-copper provenance")
    evidence = {name: _identifier(zone.get(name), name) for name in required}
    for name in ("source_fill_group_sha256", "source_fill_component_sha256"):
        _require(len(evidence[name]) == 64
                 and all(character in "0123456789abcdefABCDEF" for character in evidence[name]),
                 "Retraced zone fill digest is invalid")
    return evidence


def _legacy_simple_pieces(triangles):
    """Coalesce only CDT slivers below the unchanged legacy area admission."""
    from shapely.geometry import Polygon
    from .quasistatic_copper_area import _source_polygon

    pieces = list(triangles)
    coalesced = 0
    while True:
        rejected = None
        for index, piece in enumerate(pieces):
            points = [[float(x), float(y)] for x, y in piece.exterior.coords[:-1]]
            try:
                _source_polygon("zone", {"points": points})
            except ValueError:
                rejected = index
                break
        if rejected is None:
            return pieces, coalesced
        source = pieces[rejected]
        candidates = [(source.boundary.intersection(other.boundary).length, index)
                      for index, other in enumerate(pieces) if index != rejected]
        length, neighbor = max(candidates, default=(0.0, -1))
        _require(length > 0 and neighbor >= 0,
                 "A faithful filled-zone sliver has no adjacent legacy-admissible piece")
        merged = source.union(pieces[neighbor])
        _require(isinstance(merged, Polygon) and merged.is_valid and not merged.interiors,
                 "Filled-zone sliver coalescence changed source topology")
        for index in sorted((rejected, neighbor), reverse=True):
            pieces.pop(index)
        pieces.append(merged)
        coalesced += 1
        _require(coalesced <= len(triangles), "Filled-zone coalescence budget exceeded")


def prepare_board_copper_groups(design, selected_nets):
    """Compile retraced holed fills to exact simple pieces before legacy union.

    Ordinary valid simple zones retain the existing ``source_copper_groups``
    path. Only authoritative retraced filled paths are expanded locally.
    """
    from shapely import constrained_delaunay_triangles, get_parts
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    _require(hasattr(design, "zones") and isinstance(design.zones, list), "Board zones are unavailable")
    _require(isinstance(selected_nets, (list, tuple)) and selected_nets
             and len(selected_nets) == len(set(selected_nets))
             and all(isinstance(net, str) and net for net in selected_nets),
             "Selected nets must be explicit and unique")
    selected = set(selected_nets)
    zones = []
    piece_sources = {}
    fill_evidence = []
    source_vertices = 0
    piece_count = 0
    selected_zone_ids = set()
    reserved_ids = {str(item.get("id")) for name in ("zones", "tracks", "pads", "vias")
                    for item in getattr(design, name, []) if item.get("id") is not None}

    for zone in design.zones:
        _require(isinstance(zone, dict), "Board zone record is malformed")
        points = zone.get("points")
        if _net(zone) not in selected:
            zones.append(zone)
            continue
        _require(isinstance(points, (list, tuple)) and 3 <= len(points) <= 100000,
                 "Selected filled zone source-point budget exceeded")
        source_vertices += len(points)
        _require(source_vertices <= 100000, "Selected filled-zone aggregate vertex budget exceeded")
        try:
            domain = prepare_filled_path(points)
        except FilledPathError as error:
            raise ValueError("Selected filled zone has unsupported physical topology") from error
        if domain is None:
            # Exercise the unchanged strict simple-zone admission now, so a
            # bowtie cannot be mistaken for an ordinary source fill.
            polygon = Polygon(points)
            _require(polygon.is_valid and not polygon.is_empty and polygon.area > 0,
                     "Selected filled zone is neither simple nor a valid retraced fill")
            zones.append(zone)
            continue

        source_id = _identifier(str(zone.get("id", "")), "filled zone ID")
        _require(source_id not in selected_zone_ids, "Selected filled zone identity is ambiguous")
        selected_zone_ids.add(source_id)
        provenance = _filled_provenance(zone)
        source = Polygon(domain.outer, domain.holes)
        _require(source.is_valid and not source.is_empty and source.area > 0,
                 "Recovered filled zone domain is invalid")
        triangles = []
        for triangle in get_parts(constrained_delaunay_triangles(source)):
            _require(triangle.geom_type == "Polygon" and len(triangle.exterior.coords) == 4
                     and triangle.area > 0 and source.covers(triangle),
                     "Filled zone triangulation returned an invalid piece")
            triangles.append(triangle)
        _require(triangles, "Filled zone triangulation returned no physical copper")
        piece_count += len(triangles)
        _require(piece_count <= 100000, "Filled zone simple-piece budget exceeded")
        represented = unary_union(triangles)
        audit = _overlay_audit(source, represented)
        _require(audit["accepted"], "Filled zone triangulation changed physical copper support")
        pieces, coalesced = _legacy_simple_pieces(triangles)
        piece_audit = _overlay_audit(source, unary_union(pieces))
        _require(piece_audit["accepted"], "Filled zone simple pieces changed physical copper support")
        for index, triangle in enumerate(pieces):
            piece_id = f"{source_id}:dc-filled:{index}"
            _require(piece_id not in reserved_ids and piece_id not in piece_sources,
                     "Internal filled-zone piece identity collides with source geometry")
            piece = dict(zone)
            piece["id"] = piece_id
            piece["points"] = [[float(x), float(y)] for x, y in triangle.exterior.coords[:-1]]
            zones.append(piece)
            piece_sources[piece_id] = source_id
        fill_evidence.append({"source_record_id": source_id,
            "source_zone_id": provenance["source_zone_id"],
            "source_point_sha256": _source_digest(points),
            "source_point_count": len(points), "ring_count": len(domain.rings),
            "hole_count": len(domain.holes), "ring_vertex_counts": [len(ring) for ring in domain.rings],
            "source_area_mm2": float(source.area), "triangle_count": len(triangles),
            "emitted_simple_piece_count": len(pieces), "coalesced_sliver_count": coalesced,
            "triangulated_area_mm2": float(sum(triangle.area for triangle in triangles)),
            "overlay_audit": audit, "emitted_piece_overlay_audit": piece_audit,
            "native_fill_provenance": provenance,
            "conversion": "exact_retraced_bridges_cancelled_then_constrained_delaunay_with_exact_adjacent_sliver_union"})

    proxy = copy(design)
    proxy.zones = zones
    groups, axial = source_copper_groups(proxy, list(selected_nets))
    # Internal triangle IDs are not source identities. Restore each original
    # zone ID and deduplicate the union inventory without hiding other objects.
    for group in groups.values():
        inventory = []
        seen = set()
        for row in group["source_inventory"]:
            restored = deepcopy(row)
            restored["id"] = piece_sources.get(str(restored["id"]), restored["id"])
            key = (restored["id"], restored["kind"])
            if key not in seen:
                seen.add(key)
                inventory.append(restored)
        group["source_inventory"] = inventory
    return groups, axial, fill_evidence
