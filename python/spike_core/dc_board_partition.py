# SPDX-License-Identifier: Apache-2.0
"""Localized conforming partition for supplied board-volume copper geometry."""
from __future__ import annotations

import math
import numpy as np

from .dc_triangle_partition import refine_triangles


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _polygons(geometry, label):
    from shapely.geometry import MultiPolygon, Polygon
    _require(isinstance(geometry, (Polygon, MultiPolygon)) and geometry.is_valid
             and not geometry.is_empty and geometry.area > 0, f"{label} must be valid polygonal geometry")
    parts = list(geometry.geoms) if isinstance(geometry, MultiPolygon) else [geometry]
    _require(parts and all(part.area > 0 for part in parts), f"{label} contains an empty component")
    return parts


def _support_audit(source, represented):
    source_parts = _polygons(source, "Source geometry")
    represented_parts = _polygons(represented, "Represented geometry")
    span = max(source.bounds[2]-source.bounds[0], source.bounds[3]-source.bounds[1])
    tolerance = 128*np.finfo(float).eps*max(source.area, span*span)
    symmetric = float(source.symmetric_difference(represented).area)
    topology = (len(source_parts) == len(represented_parts)
                and sum(len(p.interiors) for p in source_parts) ==
                    sum(len(p.interiors) for p in represented_parts))
    components = (all(any(a.intersection(b).area > 0 for b in represented_parts) for a in source_parts)
                  and all(any(a.intersection(b).area > 0 for a in source_parts) for b in represented_parts))
    return {"accepted": bool(topology and components and symmetric <= tolerance),
            "topology_matches": bool(topology), "components_match": bool(components),
            "source_minus_mesh_area_mm2": float(source.difference(represented).area),
            "mesh_minus_source_area_mm2": float(represented.difference(source).area),
            "symmetric_difference_area_mm2": symmetric,
            "admitted_overlay_tolerance_mm2": float(tolerance)}


class _UnionFind:
    def __init__(self, count):
        self.parent = list(range(count))

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, first, second):
        a, b = self.find(first), self.find(second)
        if a != b:
            self.parent[b] = a


def partition_board_volumes(volumes, contacts, *, target_mm, max_cells=5000, scalable=False):
    """Return localized XY triangles and conforming prism rows.

    ``volumes`` require ``geometry``, ``z0``, ``z1`` and ``net``. Contacts
    require ``geometry`` and ``group_index`` naming the owning volume. The
    result is geometry-only; it allocates no solver nodes or materials.
    """
    from shapely import STRtree, constrained_delaunay_triangles, get_parts, node, polygonize, union_all
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    _require(isinstance(volumes, list) and 1 <= len(volumes) <= 4096, "Volume partition budget exceeded")
    _require(isinstance(contacts, list) and len(contacts) <= 4096, "Contact partition budget exceeded")
    _require(type(scalable) is bool, "Explicit scalable profile flag required")
    _require(type(target_mm) in (int, float) and math.isfinite(target_mm) and target_mm > 0,
             "Target size must be a finite positive length")
    cell_limit = 50000 if scalable else 5000
    vertex_limit = 250000 if scalable else 100000
    _require(type(max_cells) is int and 3 <= max_cells <= cell_limit, "Invalid tetrahedron budget")

    fragments, boundary_vertices = [], 0
    for owner, volume in enumerate(volumes):
        _require(isinstance(volume, dict) and {"geometry", "z0", "z1", "net"} <= set(volume),
                 "Volume lacks partition geometry")
        z0, z1 = volume["z0"], volume["z1"]
        _require(type(z0) in (int, float) and type(z1) in (int, float)
                 and math.isfinite(z0) and math.isfinite(z1) and z1 > z0,
                 "Volume span must be finite and positive")
        _require(isinstance(volume["net"], str) and volume["net"], "Volume net is invalid")
        for geometry in _polygons(volume["geometry"], "Volume geometry"):
            boundary_vertices += len(geometry.exterior.coords)+sum(len(r.coords) for r in geometry.interiors)
            fragments.append({"geometry": geometry, "owner": owner, "z0": float(z0),
                              "z1": float(z1), "net": volume["net"]})
    _require(len(fragments) <= 10000 and boundary_vertices <= min(vertex_limit, max_cells*40),
             "Volume component/source-vertex budget exceeded")

    tree = STRtree([row["geometry"] for row in fragments])
    links = _UnionFind(len(fragments)); comparisons = 0
    for index, first in enumerate(fragments):
        for other_index in tree.query(first["geometry"]):
            other_index = int(other_index)
            if other_index <= index:
                continue
            comparisons += 1
            _require(comparisons <= 4_000_000, "Volume interface comparison budget exceeded")
            second = fragments[other_index]
            intersection = first["geometry"].intersection(second["geometry"])
            area = intersection.area
            z_overlap = min(first["z1"], second["z1"])-max(first["z0"], second["z0"])
            horizontal = (first["z0"] in (second["z0"], second["z1"])
                          or first["z1"] in (second["z0"], second["z1"])) and area > 0
            lateral = z_overlap > 0 and area == 0 and intersection.length > 0
            _require(not (z_overlap > 0 and area > 0), "Supplied conductive volumes overlap")
            if horizontal or lateral:
                _require(first["net"] == second["net"],
                         "Different nets share an unmodelled conductive interface")
                links.union(index, other_index)

    clusters = {}
    for index in range(len(fragments)):
        clusters.setdefault(links.find(index), []).append(index)
    contact_parts = {root: [] for root in clusters}
    contact_ids = set()
    for contact in contacts:
        _require(isinstance(contact, dict) and {"id", "geometry", "group_index"} <= set(contact),
                 "Contact lacks localized partition ownership")
        _require(isinstance(contact["id"], str) and contact["id"] and contact["id"] not in contact_ids,
                 "Contact identity is invalid or duplicated")
        contact_ids.add(contact["id"])
        owner = contact["group_index"]
        _require(type(owner) is int and 0 <= owner < len(volumes), "Contact owner is invalid")
        for part in _polygons(contact["geometry"], "Contact geometry"):
            matches = [index for index, fragment in enumerate(fragments)
                       if fragment["owner"] == owner and fragment["geometry"].covers(part)]
            _require(len(matches) == 1, "Contact component lacks one complete owning volume component")
            root = links.find(matches[0]); contact_parts[root].append((contact["id"], part))
            boundary_vertices += len(part.exterior.coords)+sum(len(r.coords) for r in part.interiors)
    _require(boundary_vertices <= min(vertex_limit, max_cells*40), "Contact/source-vertex budget exceeded")

    triangles, signatures, contact_signatures, triangle_clusters = [], [], [], []
    region_count = classification_checks = 0
    cluster_zplanes = {}
    for cluster_number, (root, indices) in enumerate(sorted(clusters.items())):
        local = [fragments[index] for index in indices]
        linework = union_all([row["geometry"].boundary for row in local]
                             + [part.boundary for _, part in contact_parts[root]])
        regions = list(get_parts(polygonize(get_parts(node(linework)))))
        _require(regions, "Localized planar arrangement is empty")
        region_count += len(regions)
        _require(region_count <= max_cells, "Localized planar arrangement exceeds polygon budget")
        local_tree = STRtree([row["geometry"] for row in local])
        local_contacts = contact_parts[root]
        contact_tree = STRtree([part for _, part in local_contacts]) if local_contacts else None
        for region in regions:
            candidate_indices = [int(value) for value in local_tree.query(region)]
            classification_checks += len(candidate_indices)
            _require(classification_checks <= 4_000_000,
                     "Localized planar ownership classification budget exceeded")
            owners = set()
            for candidate in candidate_indices:
                fragment = local[candidate]
                intersection = fragment["geometry"].intersection(region).area
                _require(intersection == 0 or fragment["geometry"].covers(region),
                         "Localized arrangement failed to preserve a source boundary")
                if fragment["geometry"].covers(region):
                    owners.add(fragment["owner"])
            if not owners:
                continue
            signature = tuple(sorted(owners))
            contact_signature = set()
            if contact_tree is not None:
                contact_candidates = [int(value) for value in contact_tree.query(region)]
                classification_checks += len(contact_candidates)
                _require(classification_checks <= 4_000_000,
                         "Localized planar ownership classification budget exceeded")
                for candidate in contact_candidates:
                    contact_id, part = local_contacts[candidate]
                    intersection = part.intersection(region).area
                    # Polygonization may place an interpolated atom vertex one
                    # binary64 ulp on the exterior side of the authored contact
                    # even though the atom interior is wholly in the contact.
                    # Contact flux is an area integral: classify that intended
                    # closed-boundary case only when a strict interior witness
                    # is covered and the positive-area intersection is exactly
                    # the full atom area. This introduces no distance/area
                    # tolerance; a genuinely straddling atom remains rejected.
                    inside = part.covers(region.representative_point())
                    complete_area = region.difference(part).area == 0
                    _require(intersection == 0 or (inside and complete_area),
                             "Localized arrangement failed to preserve a contact boundary")
                    if inside and complete_area:
                        contact_signature.add(contact_id)
            contact_signature = tuple(sorted(contact_signature))
            for triangle in get_parts(constrained_delaunay_triangles(region)):
                points = np.asarray(triangle.exterior.coords[:-1], dtype=float)
                _require(points.shape == (3, 2) and triangle.area > 0 and region.covers(triangle),
                         "Localized constrained triangulation returned an invalid triangle")
                triangles.append(points); signatures.append(signature)
                contact_signatures.append(contact_signature); triangle_clusters.append(cluster_number)
                _require(len(triangles) <= max_cells//3,
                         "Tetrahedron budget exceeded before planar refinement")
        owners = sorted({fragments[index]["owner"] for index in indices})
        planes = set()
        for owner in owners:
            volume = volumes[owner]; z0, z1 = float(volume["z0"]), float(volume["z1"])
            divisions = math.ceil((z1-z0)/target_mm)
            _require(divisions <= max_cells, "Vertical refinement exceeds tetrahedron budget")
            planes.update((z0, z1))
            planes.update(z0+(z1-z0)*step/divisions for step in range(1, divisions))
        cluster_zplanes[cluster_number] = sorted(planes)
    _require(triangles, "No supplied conductive volume was triangulated")

    # Refinement preserves ordering only by emitting children consecutively;
    # carry cluster identity as part of the refinement owner token.
    tokens = [(signatures[index], contact_signatures[index], triangle_clusters[index])
              for index in range(len(triangles))]
    triangles, tokens = refine_triangles(triangles, tokens, float(target_mm), max_cells//3)
    signatures = [token[0] for token in tokens]
    contact_signatures = [token[1] for token in tokens]
    triangle_clusters = [token[2] for token in tokens]
    polygons = [Polygon(points) for points in triangles]
    audits = []
    for owner, volume in enumerate(volumes):
        represented = unary_union([polygon for polygon, signature in zip(polygons, signatures)
                                   if owner in signature])
        audit = _support_audit(volume["geometry"], represented)
        _require(audit["accepted"], "Localized partition changed source footprint topology")
        audits.append(audit)

    prism_rows = []
    for triangle_index, (signature, cluster_number) in enumerate(zip(signatures, triangle_clusters)):
        planes = cluster_zplanes[cluster_number]
        for low, high in zip(planes, planes[1:]):
            middle = (low+high)/2
            active = [owner for owner in signature
                      if float(volumes[owner]["z0"]) < middle < float(volumes[owner]["z1"])]
            _require(len(active) <= 1, "Localized partition found overlapping volume ownership")
            if active:
                prism_rows.append((triangle_index, active[0], low, high))
                _require(3*len(prism_rows) <= max_cells,
                         "Tetrahedron budget exceeded before mesh allocation")
    return {"triangles": triangles, "signatures": signatures,
            "contact_signatures": contact_signatures, "prism_rows": prism_rows,
            "triangle_clusters": triangle_clusters, "coverage_audits": audits,
            "stats": {"volume_count": len(volumes), "component_count": len(fragments),
                "conforming_cluster_count": len(clusters), "arrangement_polygon_count": region_count,
                "base_triangle_count": len(triangles), "prism_count": len(prism_rows),
                "interface_comparisons": comparisons, "ownership_classification_checks": classification_checks}}
