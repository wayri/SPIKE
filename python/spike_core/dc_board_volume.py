# SPDX-License-Identifier: Apache-2.0
"""Exact supplied-board copper volumes for the experimental tetrahedral RT0 path."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

import numpy as np

from .dc_triangle_partition import refine_triangles


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identifier(value, label):
    _require(isinstance(value, str) and value.strip() and len(value) <= 200, f"Invalid {label}")
    return value


def _number(value, label, *, positive=False):
    _require(type(value) in (int, float), f"{label} must be a finite number")
    value = float(value)
    _require(math.isfinite(value) and (not positive or value > 0), f"Invalid {label}")
    return value


def _polygons(geometry, label, *, annulus=False):
    from shapely.geometry import MultiPolygon, Polygon
    _require(isinstance(geometry, (Polygon, MultiPolygon)) and not geometry.is_empty
             and geometry.is_valid and geometry.area > 0, f"{label} must be valid positive polygonal geometry")
    parts = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    _require(parts and all(part.area > 0 for part in parts), f"{label} contains an empty component")
    _require(all(math.isfinite(value) and abs(value) <= 1e9 for value in geometry.bounds),
             f"{label} exceeds finite coordinate bounds")
    if annulus:
        _require(all(len(part.interiors) >= 1 for part in parts), f"{label} must retain an explicit bore")
    return parts


def _vertex_count(geometry):
    return sum(len(part.exterior.coords) + sum(len(ring.coords) for ring in part.interiors)
               for part in _polygons(geometry, "Geometry"))


def _geometry_evidence(geometry):
    from shapely.geometry import mapping
    return {"geojson": mapping(geometry), "wkb_sha256": hashlib.sha256(geometry.wkb).hexdigest(),
            "area_mm2": float(geometry.area), "component_count": len(_polygons(geometry, "Geometry")),
            "boundary_vertex_count": _vertex_count(geometry)}


def _polygon_support_audit(source, represented):
    """Return topology and directional binary64 overlay evidence."""
    source_parts = _polygons(source, "Source geometry")
    represented_parts = _polygons(represented, "Represented geometry")
    topology_matches = (len(source_parts) == len(represented_parts)
        and sum(len(part.interiors) for part in source_parts) ==
            sum(len(part.interiors) for part in represented_parts))
    span = max(source.bounds[2]-source.bounds[0], source.bounds[3]-source.bounds[1])
    tolerance = 128 * np.finfo(float).eps * max(source.area, span*span)
    omitted = float(source.difference(represented).area)
    excess = float(represented.difference(source).area)
    symmetric = float(source.symmetric_difference(represented).area)
    # A small component may be below the aggregate roundoff bound; require an
    # actual positive-area counterpart instead of allowing it to disappear.
    components_match = (all(any(a.intersection(b).area > 0 for b in represented_parts)
                            for a in source_parts)
                        and all(any(a.intersection(b).area > 0 for a in source_parts)
                                for b in represented_parts))
    return {"accepted": bool(topology_matches and components_match and symmetric <= tolerance),
            "topology_matches": bool(topology_matches),
            "components_match": bool(components_match),
            "source_minus_mesh_area_mm2": omitted,
            "mesh_minus_source_area_mm2": excess,
            "symmetric_difference_area_mm2": symmetric,
            "admitted_overlay_tolerance_mm2": float(tolerance)}


def _same_polygon_support(source, represented):
    return _polygon_support_audit(source, represented)["accepted"]


def _json_copy(value, label):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        _require(len(encoded.encode()) <= 2 * 1024 * 1024, f"{label} exceeds metadata budget")
        return json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be finite JSON-compatible evidence") from error


def _tetra_volume(points):
    return float(np.linalg.det((points[1:] - points[0]).T) / 6)


def _interval_overlap(a, b):
    return min(a[1], b[1]) - max(a[0], b[0])


def compile_board_volume(groups, barrels, contacts, *, expected_axial_source_ids,
                         target_mm, max_cells=5000, scalable=False):
    """Compile exact supplied slab/barrel geometry and finite current patches.

    No pad, point-terminal, plating, stackup, or electrode geometry is inferred.
    All coordinates are millimetres; conductivity is S/m and contact current A.
    """
    from shapely import constrained_delaunay_triangles, get_parts, node, polygonize, union_all
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    _require(isinstance(groups, dict) and 1 <= len(groups) <= 128, "Board volume group budget exceeded")
    _require(type(scalable) is bool, "Explicit scalable profile flag required")
    _require(isinstance(barrels, list) and len(barrels) <= (1024 if scalable else 512), "Board barrel budget exceeded")
    _require(isinstance(contacts, list) and 2 <= len(contacts) <= 256, "Finite contacts required within budget")
    _require(type(max_cells) is int and 3 <= max_cells <= (50000 if scalable else 5000), "Invalid tetrahedron budget")
    target = _number(target_mm, "target size", positive=True)
    _require(target <= 1e6, "Target size exceeds coordinate budget")
    _require(isinstance(expected_axial_source_ids, (list, tuple, set))
             and not isinstance(expected_axial_source_ids, (str, bytes)), "Expected axial source IDs must be a collection")
    expected = [_identifier(item, "expected axial source ID") for item in expected_axial_source_ids]
    _require(len(expected) == len(set(expected)), "Expected axial source IDs must be unique")

    volumes, group_by_key, object_map = [], {}, {}
    boundary_vertices = 0
    inventory_bytes = 0
    for index, (key, record) in enumerate(sorted(groups.items(), key=lambda item: repr(item[0]))):
        _require(isinstance(key, tuple) and len(key) == 2, "Copper groups require (layer, net) keys")
        layer, net = (_identifier(value, "copper group identity") for value in key)
        _require(key not in group_by_key and isinstance(record, dict), "Duplicate or invalid copper group")
        _require({"geometry", "thickness_mm", "z_mm", "conductivity_s_m", "source_inventory"} <= set(record),
                 "Copper group lacks physical source evidence")
        geometry = record["geometry"]
        _polygons(geometry, f"Copper group {layer}/{net}")
        boundary_vertices += _vertex_count(geometry)
        thickness = _number(record["thickness_mm"], "copper thickness", positive=True)
        center = _number(record["z_mm"], "copper elevation")
        sigma = _number(record["conductivity_s_m"], "conductivity", positive=True)
        _require(1e-6 <= sigma <= 1e12, "Conductivity exceeds supported range")
        inventory = _json_copy(record["source_inventory"], "Source inventory")
        _require(isinstance(inventory, list) and inventory, "Every copper group needs source inventory")
        inventory_bytes += len(json.dumps(inventory, separators=(",", ":"), allow_nan=False).encode())
        _require(inventory_bytes <= 2 * 1024 * 1024, "Aggregate source inventory exceeds metadata budget")
        _require(max(abs(center-thickness/2), abs(center+thickness/2)) <= 1e9,
                 "Copper slab exceeds coordinate bounds")
        source_id = f"board-slab:{index}"
        volume = {"source_object_id": source_id, "kind": "copper_slab", "layer": layer, "net": net,
                  "geometry": geometry, "z0": center-thickness/2, "z1": center+thickness/2,
                  "conductivity_s_m": sigma, "source_inventory": inventory, "input_key": [layer, net]}
        volumes.append(volume); group_by_key[key] = volume
        object_map[source_id] = {"kind": "copper_slab", "net": net, "layer": layer, "body_id": f"net:{net}"}

    barrel_ids, actual_axial = set(), []
    for index, record in enumerate(barrels):
        _require(isinstance(record, dict) and set(record) == {
            "id", "source_id", "net", "geometry", "z_min_mm", "z_max_mm", "conductivity_s_m"},
            "Invalid explicit barrel record")
        identity = _identifier(record["id"], "barrel ID")
        source = _identifier(record["source_id"], "barrel source ID")
        net = _identifier(record["net"], "barrel net")
        _require(identity not in barrel_ids, "Duplicate barrel ID")
        barrel_ids.add(identity); actual_axial.append(source)
        geometry = record["geometry"]
        _polygons(geometry, f"Barrel {identity}", annulus=True)
        boundary_vertices += _vertex_count(geometry)
        z0 = _number(record["z_min_mm"], "barrel lower face")
        z1 = _number(record["z_max_mm"], "barrel upper face")
        sigma = _number(record["conductivity_s_m"], "barrel conductivity", positive=True)
        _require(z1 > z0 and 1e-6 <= sigma <= 1e12, "Barrel span/material is invalid")
        _require(max(abs(z0), abs(z1)) <= 1e9, "Barrel exceeds coordinate bounds")
        source_object_id = f"board-barrel:{index}:{identity}"
        volumes.append({"source_object_id": source_object_id, "kind": "plated_barrel", "id": identity,
                        "source_id": source, "layer": "axial", "net": net, "geometry": geometry,
                        "z0": z0, "z1": z1, "conductivity_s_m": sigma,
                        "source_inventory": [{"id": source, "kind": "axial_source"}]})
        object_map[source_object_id] = {"kind": "plated_barrel", "net": net, "layer": "axial",
                                       "body_id": f"net:{net}"}
    _require(set(actual_axial) == set(expected),
             "Explicit barrels do not exactly cover expected axial sources")
    _require(boundary_vertices <= min(250000 if scalable else 100000, max_cells * 40), "Source boundary vertex budget exceeded")

    # Positive-volume overlap is never resolved by ownership priority. A
    # zero-thickness same-net interface is conformingly welded; different nets
    # may not occupy coincident faces without an explicit interface model.
    comparisons = 0
    for i, first in enumerate(volumes):
        for second in volumes[:i]:
            comparisons += 1
            _require(comparisons <= 250000, "Volume overlap comparison budget exceeded")
            area = first["geometry"].intersection(second["geometry"]).area
            overlap = _interval_overlap((first["z0"], first["z1"]), (second["z0"], second["z1"]))
            _require(not (overlap > 0 and area > 0), "Supplied conductive volumes overlap")
            touching = first["z0"] in (second["z0"], second["z1"]) or first["z1"] in (second["z0"], second["z1"])
            _require(not (touching and area > 0 and first["net"] != second["net"]),
                     "Different nets touch on an unmodelled zero-thickness interface")

    # Every barrel must land over supplied same-net slab copper at both exact
    # endpoints. This proves geometry support without inferring a pad or weld.
    for barrel in (volume for volume in volumes if volume["kind"] == "plated_barrel"):
        landing_layers = []
        for endpoint in (barrel["z0"], barrel["z1"]):
            candidates = [volume for volume in volumes if volume["kind"] == "copper_slab"
                          and volume["net"] == barrel["net"] and endpoint in (volume["z0"], volume["z1"])]
            _require(candidates and unary_union([item["geometry"] for item in candidates]).covers(barrel["geometry"]),
                     "Barrel endpoint lacks complete same-net slab support")
            landing_layers.append(sorted(item["layer"] for item in candidates
                                         if item["geometry"].intersection(barrel["geometry"]).area > 0))
        barrel["landing_layers"] = landing_layers

    contact_rows, contact_ids = [], set()
    for record in contacts:
        _require(isinstance(record, dict) and set(record) == {
            "id", "layer", "net", "side", "geometry", "current_a"}, "Invalid finite contact record")
        identity = _identifier(record["id"], "contact ID")
        _require(len(identity) <= 128, "Contact ID exceeds solver contract")
        key = (_identifier(record["layer"], "contact layer"), _identifier(record["net"], "contact net"))
        _require(identity not in contact_ids and key in group_by_key, "Duplicate contact or missing copper group")
        contact_ids.add(identity)
        side = record["side"]
        _require(side in {"top", "bottom"}, "Contact side must be top or bottom")
        geometry = record["geometry"]
        _polygons(geometry, f"Contact {identity}")
        boundary_vertices += _vertex_count(geometry)
        group = group_by_key[key]
        _require(group["geometry"].covers(geometry), f"Contact {identity} cuts a void or leaves copper")
        current = _number(record["current_a"], "contact current")
        _require(abs(current) <= 1e9, "Contact current exceeds supported range")
        contact_rows.append({"id": identity, "layer": key[0], "net": key[1], "side": side,
                             "geometry": geometry, "current_a": current, "group": group,
                             "group_index": volumes.index(group),
                             "z": group["z1"] if side == "top" else group["z0"]})
    _require(boundary_vertices <= min(250000 if scalable else 100000, max_cells * 40), "Contact boundary vertex budget exceeded")
    for index, first in enumerate(contact_rows):
        for second in contact_rows[:index]:
            if first["z"] == second["z"]:
                _require(first["geometry"].intersection(second["geometry"]).area == 0,
                         "Finite contact footprints overlap")

    partition_stats = {}
    triangle_contacts = None
    if scalable:
        from .dc_board_partition import partition_board_volumes
        partition = partition_board_volumes(volumes, contact_rows, target_mm=target, max_cells=max_cells, scalable=True)
        base = partition["triangles"]; signatures = partition["signatures"]
        base_polygons = [Polygon(points) for points in base]
        footprint_audits = partition["coverage_audits"]
        prism_rows = partition["prism_rows"]; partition_stats = partition["stats"]
        triangle_contacts = partition["contact_signatures"]
        arrangement_count = partition_stats["arrangement_polygon_count"]
        z_plane_count = len({z for _, _, lo, hi in prism_rows for z in (lo, hi)})
    else:
        linework = union_all([volume["geometry"].boundary for volume in volumes]
                             + [contact["geometry"].boundary for contact in contact_rows])
        arrangement = list(get_parts(polygonize(get_parts(node(linework)))))
        _require(arrangement and len(arrangement) <= max_cells, "Global planar arrangement exceeds polygon budget")
        _require(len(arrangement) * len(volumes) <= 4_000_000,
                 "Global planar ownership classification budget exceeded")
        base, signatures = [], []
        for region in arrangement:
            covered = tuple(index for index, volume in enumerate(volumes) if volume["geometry"].covers(region))
            if not covered:
                continue
            # Noding must make each atom wholly inside or outside every source.
            for index, volume in enumerate(volumes):
                intersection = region.intersection(volume["geometry"]).area
                _require(intersection == 0 or volume["geometry"].covers(region),
                         "Global arrangement failed to preserve a source boundary")
            for triangle in get_parts(constrained_delaunay_triangles(region)):
                points = np.asarray(triangle.exterior.coords[:-1], dtype=float)
                _require(points.shape == (3, 2) and Polygon(points).area > 0 and region.covers(triangle),
                         "Constrained triangulation returned a degenerate nontriangle")
                base.append(points); signatures.append(covered)
                _require(len(base) <= max_cells // 3, "Tetrahedron budget exceeded before refinement")
        _require(base, "No supplied conductive volume was triangulated")
        base, signatures = refine_triangles(base, signatures, target, max_cells // 3)
        base_polygons = [Polygon(points) for points in base]

        # Exact topological coverage is required for every component; area-only
        # agreement could hide a swapped sliver or a lost hole.
        footprint_audits = []
        for index, volume in enumerate(volumes):
            represented = unary_union([polygon for polygon, owners in zip(base_polygons, signatures) if index in owners])
            audit = _polygon_support_audit(volume["geometry"], represented)
            _require(audit["accepted"],
                     "Triangulation changed source volume footprint topology")
            footprint_audits.append(audit)

        zplanes = set()
        for volume in volumes:
            divisions = math.ceil((volume["z1"] - volume["z0"]) / target)
            _require(divisions <= max_cells, "Vertical refinement exceeds tetrahedron budget")
            # Preserve supplied endpoints exactly. Recomputing the final point by
            # interpolation can differ by one binary64 ulp and create a spurious
            # near-zero interval where a barrel meets its landing slab.
            zplanes.update((volume["z0"], volume["z1"]))
            zplanes.update(volume["z0"] + (volume["z1"] - volume["z0"]) * step / divisions
                           for step in range(1, divisions))
            _require(len(zplanes) <= max_cells, "Global vertical-plane budget exceeded")
        zplanes = sorted(zplanes)
        intervals = [(low, high) for low, high in zip(zplanes, zplanes[1:]) if high > low]
        prism_rows = []
        for triangle_index, owners in enumerate(signatures):
            for low, high in intervals:
                middle = (low + high) / 2
                active = [index for index in owners if volumes[index]["z0"] < middle < volumes[index]["z1"]]
                _require(len(active) <= 1, "Planar arrangement found overlapping conductive volume ownership")
                if active:
                    prism_rows.append((triangle_index, active[0], low, high))
        _require(3 * len(prism_rows) <= max_cells, "Tetrahedron budget exceeded before mesh allocation")

        arrangement_count = len(arrangement)
        z_plane_count = len(zplanes)

    vertices, vertex_ids, cells, conductivity = [], {}, [], {}
    meshed_volume = [0.0 for _ in volumes]
    triangle_nodes = {}
    def vertex(net, point, z):
        key = (net, float(point[0]), float(point[1]), float(z))
        if key not in vertex_ids:
            _require(len(vertices) < (50000 if scalable else 10000), "Tetra DC vertex budget exceeded")
            vertex_ids[key] = len(vertices)
            vertices.append([key[1], key[2], key[3]])
        return vertex_ids[key]

    for triangle_index, volume_index, low, high in prism_rows:
        volume = volumes[volume_index]
        points = base[triangle_index]
        order = sorted(range(3), key=lambda i: (float(points[i, 0]), float(points[i, 1])))
        low_nodes = [vertex(volume["net"], points[i], low) for i in order]
        high_nodes = [vertex(volume["net"], points[i], high) for i in order]
        triangle_nodes[(triangle_index, volume["net"], low)] = low_nodes
        triangle_nodes[(triangle_index, volume["net"], high)] = high_nodes
        a, b, c = low_nodes; ap, bp, cp = high_nodes
        for raw in ([a, b, c, cp], [a, b, bp, cp], [a, ap, bp, cp]):
            xyz = np.asarray([vertices[node_id] for node_id in raw], dtype=float)
            signed = _tetra_volume(xyz)
            _require(signed != 0 and math.isfinite(signed), "Degenerate tetrahedron generated")
            nodes = list(raw)
            if signed < 0:
                nodes[1], nodes[2] = nodes[2], nodes[1]
                signed = -signed
            cell_id = f"tetra:{len(cells)}"
            cells.append({"id": cell_id, "kind": "tetrahedron", "vertices": nodes,
                          "material_id": f"material:{volume['source_object_id']}",
                          "source_object_ids": [volume["source_object_id"]]})
            conductivity[cell_id] = volume["conductivity_s_m"]
            meshed_volume[volume_index] += signed

    face_counts = {}
    for cell in cells:
        a, b, c, d = cell["vertices"]
        for face in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
            key = tuple(sorted(face)); face_counts[key] = face_counts.get(key, 0) + 1

    output_contacts, contact_coverage = [], []
    used_faces = set()
    for contact in contact_rows:
        chosen, chosen_polygons = [], []
        group_index = contact["group_index"]
        for triangle_index, (polygon, owners) in enumerate(zip(base_polygons, signatures)):
            selected_patch = (contact["id"] in triangle_contacts[triangle_index] if scalable
                              else contact["geometry"].covers(polygon))
            if group_index not in owners or not selected_patch:
                continue
            nodes = triangle_nodes.get((triangle_index, contact["net"], contact["z"]))
            _require(nodes is not None, "Contact face has no retained volume support")
            face = list(nodes)
            xy = np.asarray([vertices[node][:2] for node in face])
            cross = ((xy[1, 0]-xy[0, 0])*(xy[2, 1]-xy[0, 1])
                     - (xy[1, 1]-xy[0, 1])*(xy[2, 0]-xy[0, 0]))
            if (contact["side"] == "top" and cross < 0) or (contact["side"] == "bottom" and cross > 0):
                face[1], face[2] = face[2], face[1]
            key = tuple(sorted(face))
            _require(face_counts.get(key) == 1, "Contact selects an internal or nonmanifold face")
            _require(key not in used_faces, "Contact faces overlap")
            used_faces.add(key); chosen.append(face); chosen_polygons.append(polygon)
        _require(chosen, "Contact has no complete exterior mesh faces")
        represented = unary_union(chosen_polygons)
        audit = _polygon_support_audit(contact["geometry"], represented)
        _require(audit["accepted"],
                 "Contact is only partially represented by exterior faces")
        output_contacts.append({"id": contact["id"], "faces": chosen, "current_a": contact["current_a"]})
        contact_coverage.append({"id": contact["id"], "layer": contact["layer"], "net": contact["net"],
                                 "side": contact["side"], "source_area_mm2": float(contact["geometry"].area),
                                 "mesh_area_mm2": float(sum(polygon.area for polygon in chosen_polygons)),
                                 "face_count": len(chosen), "overlay_audit": audit,
                                 "input_geometry": _geometry_evidence(contact["geometry"])})

    volume_coverage = []
    omitted_volume = 0.0
    excess_volume = 0.0
    symmetric_difference_volume = 0.0
    for index, volume in enumerate(volumes):
        source_volume = float(volume["geometry"].area * (volume["z1"] - volume["z0"]))
        _require(math.isfinite(source_volume) and source_volume > 0,
                 "Supplied source volume is not representable")
        tolerance = 1e-10 * source_volume
        _require(abs(meshed_volume[index] - source_volume) <= tolerance,
                 "Tetrahedra do not conserve supplied source volume")
        height = volume["z1"] - volume["z0"]
        overlay = footprint_audits[index]
        omitted_volume += overlay["source_minus_mesh_area_mm2"] * height
        excess_volume += overlay["mesh_minus_source_area_mm2"] * height
        symmetric_difference_volume += overlay["symmetric_difference_area_mm2"] * height
        row = {"source_object_id": volume["source_object_id"], "kind": volume["kind"],
               "layer": volume["layer"], "net": volume["net"], "z_min_mm": volume["z0"],
               "z_max_mm": volume["z1"], "conductivity_s_m": volume["conductivity_s_m"],
               "source_volume_mm3": source_volume, "mesh_volume_mm3": meshed_volume[index],
               "volume_difference_mm3": meshed_volume[index] - source_volume,
               "volume_conservation_tolerance_mm3": tolerance,
               "footprint_overlay_audit": overlay,
               "source_inventory": deepcopy(volume["source_inventory"]),
               "input_geometry": _geometry_evidence(volume["geometry"])}
        if volume["kind"] == "plated_barrel":
            row.update({"id": volume["id"], "source_id": volume["source_id"],
                        "landing_layers": deepcopy(volume["landing_layers"])})
        volume_coverage.append(row)

    mesh = {"contract": "spike/solver-mesh/v1", "units": "mm",
            "coordinate_system": "right_handed_xyz", "vertices": vertices, "cells": cells,
            "counts": {"vertices": len(vertices), "cells": len(cells)}, "object_map": object_map}
    request = {"contract": "spike/tetra-dc-rt0-scalable-request/v1" if scalable else "spike/tetra-dc-rt0-request/v1", "mesh": mesh,
               "conductivity_s_m": conductivity, "contacts": output_contacts}
    coverage = {"contract": "spike/dc-board-volume-coverage/v1", "model_status": "experimental",
                "production_qualified": False, "complete_selected_geometry": True,
                "all_source_volumes_retained": True, "no_intentional_geometry_omission": True,
                "overlay_omitted_volume_mm3": float(omitted_volume),
                "overlay_excess_volume_mm3": float(excess_volume),
                "overlay_symmetric_difference_volume_mm3": float(symmetric_difference_volume),
                "target_mm": target, "max_cells": max_cells,
                "arrangement_polygon_count": arrangement_count, "base_triangle_count": len(base),
                "z_plane_count": z_plane_count, "partition_stats": partition_stats,
                "volume_comparisons": comparisons, "expected_axial_source_ids": sorted(expected),
                "compiled_axial_source_ids": sorted(set(actual_axial)), "volumes": volume_coverage,
                "contacts": contact_coverage,
                "limitations": ["supplied selected copper only; no board-wide completeness claim",
                                "uniform normal-flux finite contacts, not equipotential electrodes",
                                "no inferred pads, barrels, contacts, stackup, dielectric, AC or thermal ownership"]}
    return {"request": request, "coverage": coverage}
