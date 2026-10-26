# SPDX-License-Identifier: Apache-2.0
"""Explicit fixed-grid polygon arrangement with measured geometry admission.

Uses public GEOS/Shapely operations, not a copied noder implementation.
The grid changes the geometry model; it is never a solver tolerance or a
license to drop thin features. See docs/DC_PRECISION_PARTITION.md.
"""
from __future__ import annotations

from math import isfinite, pi


def _signature(shape):
    polygons = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
    if any(p.geom_type != "Polygon" or p.is_empty for p in polygons):
        raise ValueError("Precision partition requires nonempty polygon support")
    return len(polygons), sorted(len(p.interiors) for p in polygons)


def _audit(original, admitted, grid):
    if not admitted.is_valid or _signature(original) != _signature(admitted):
        raise ValueError("Precision partition changed components or holes")
    # GEOS audit is floating-point, not an outward-rounded geometry proof.
    # A deliberately small admitted tube bounds both boundary motion and area.
    radius = 4*grid
    distance = original.boundary.hausdorff_distance(admitted.boundary)
    difference = original.symmetric_difference(admitted).area
    area_budget = 2*radius*original.length + pi*radius*radius
    if (not all(isfinite(v) for v in (distance, difference, area_budget))
            or distance > radius or difference > area_budget):
        raise ValueError("Precision partition exceeded declared boundary/area uncertainty")
    return {"boundary_displacement_mm": distance, "symmetric_difference_mm2": difference,
            "source_area_mm2": original.area, "admitted_area_mm2": admitted.area,
            "boundary_budget_mm": radius, "area_budget_mm2": area_budget,
            "components": _signature(original)[0], "hole_counts": _signature(original)[1]}


def polygon_regions(copper, contacts, grid, target):
    """Return noded regions and audits, retaining every source/contact owner.

    Zero grid preserves the legacy double-precision path. Positive grid is
    explicit, bounded below the mesh scale, and uses one arrangement operation
    on original linework; vertices are not individually rounded first.
    """
    from shapely import unary_union
    from shapely.ops import polygonize
    boundaries = [copper.boundary] + [c["geometry"].boundary for c in contacts]
    if grid == 0:
        regions = [p for p in polygonize(unary_union(boundaries))
                   if copper.covers(p.representative_point())]
        return regions, None
    if not isfinite(grid) or not 0 < grid <= target*1e-6:
        raise ValueError("Precision grid must be positive and at most one millionth of target size")
    shapes = [copper] + [c["geometry"] for c in contacts]
    for shape in shapes:
        _signature(shape)
        if shape.minimum_clearance <= 32*grid:
            raise ValueError("Precision grid cannot resolve source/contact features")
        if max(abs(v) for v in shape.bounds) > grid*2**50:
            raise ValueError("Precision grid is not representable at the supplied origin")
    for contact in contacts:
        distance = contact["geometry"].distance(copper.boundary)
        if 0 < distance <= 32*grid:
            raise ValueError("Precision grid cannot resolve contact-to-copper boundary clearance")
    regions = [p for p in polygonize(unary_union(boundaries, grid_size=grid))
               if copper.covers(p.representative_point())]
    if not regions:
        raise ValueError("Precision partition lost all copper")
    represented = unary_union(regions)
    audit = {"grid_mm": grid, "method": "explicit_fixed_grid_noded_original_linework",
             "formal_roundoff_certificate": False, "copper": _audit(copper, represented, grid),
             "contacts": []}
    for contact in contacts:
        owned = [p for p in regions if contact["geometry"].covers(p.representative_point())]
        if not owned:
            raise ValueError("Precision partition lost a finite contact")
        admitted = unary_union(owned)
        if contact["geometry"].relate(copper) != admitted.relate(represented):
            raise ValueError("Precision partition changed contact-to-copper topology")
        audit["contacts"].append({"id": contact["id"], **_audit(contact["geometry"], admitted, grid)})
    # Distinct finite contacts may share edges, but no region may acquire two
    # owners. In particular a narrow separating strip cannot silently disappear.
    for region in regions:
        if sum(c["geometry"].covers(region.representative_point()) for c in contacts) > 1:
            raise ValueError("Precision partition has ambiguous finite contact ownership")
    for i, first in enumerate(contacts):
        for second in contacts[:i]:
            distance = first["geometry"].distance(second["geometry"])
            if 0 < distance <= 32*grid:
                raise ValueError("Precision grid cannot resolve separation between contacts")
    return regions, audit
