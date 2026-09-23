# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Bounded interior rectangular copper partition for experimental volume PEEC.

One potential unknown belongs to each control rectangle. A shared-face current
has width equal to the actual face overlap and length equal to the sum of the
two normal half-cell distances. Its rectangular support stays in those two
cells. The incidence matrix conserves integrated face flux exactly; the
piecewise-constant potential/current approximation still needs convergence.
No clipping, width repair, or nearest-node attachment is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite, pi, sqrt
from typing import Any

from .contracts import AnalysisSpec, DesignIR, ValidationIssue
from .hybrid_mesh import (
    COPPER_CONDUCTIVITY_S_M, HybridMesh, MeshBranch, MeshNode, _Builder,
    _net, _pad_has_drill, _pad_layers, _pad_size, _point,
)


@dataclass(frozen=True)
class _Cell:
    bounds: tuple[float, float, float, float]
    node: int
    source: str
    kind: str


def _coalesce_rectangles(rectangles: list[tuple[float, float, float, float]],
                         target: float) -> list[tuple[float, float, float, float]]:
    """Remove redundant subdivision while preserving the exact rectangle union.

    Only identical complete opposing faces merge. No bounds move, no gap is
    filled, and no cell exceeds the requested target in either dimension.
    Fixed contacts are excluded by the caller. Eight alternating passes bound
    work; stopping early merely leaves more cells and cannot alter copper.
    """
    result = list(rectangles)
    for _ in range(8):
        before = len(result)
        for axis in (0, 1):
            tangent = 1-axis
            groups: dict[tuple[float, float], list[tuple[float, float, float, float]]] = {}
            for rectangle in result:
                groups.setdefault((rectangle[tangent], rectangle[tangent+2]), []).append(rectangle)
            merged = []
            for key in sorted(groups):
                ordered = sorted(groups[key], key=lambda bounds: bounds[axis])
                current = ordered[0]
                for following in ordered[1:]:
                    if (current[axis+2] == following[axis]
                            and following[axis+2]-current[axis] <= target*(1+1e-12)):
                        extended = list(current)
                        extended[axis+2] = following[axis+2]
                        current = tuple(extended)
                    else:
                        merged.append(current)
                        current = following
                merged.append(current)
            result = merged
        if len(result) == before:
            break
    return result


def _failure(mesh: HybridMesh, message: str) -> HybridMesh:
    mesh.truncated = True
    mesh.issues.append(ValidationIssue(
        "PEEC_CONFORMING_PARTITION_UNQUALIFIED", "error", message,
        suggestion="Refine the bounded partition or increase its explicit resource budget; do not use the legacy nonconforming bases.",
        status="unsupported",
    ))
    return mesh


def _subdivide_interior_rectangles(rectangles: list[tuple[float, float, float, float]],
                                  maximum_edge_mm: float, remaining_cells: int
                                  ) -> list[tuple[float, float, float, float]]:
    """Split complete rectangles; retain endpoints, union, and excluded contacts.

    Uniform subdivisions in each coordinate use ceil(length/maximum_edge).
    The caller excludes fixed contact rectangles. Budget each parent before
    allocating its children, including near-zero requested edge lengths.
    """
    result = []
    for x0, y0, x1, y1 in rectangles:
        width, height = x1-x0, y1-y0
        # This precheck also avoids overflow in ceil for a subnormal limit.
        if width > remaining_cells*maximum_edge_mm or height > remaining_cells*maximum_edge_mm:
            raise ValueError("Conforming interior subdivision exceeds the control-cell budget")
        nx, ny = max(1, ceil(width/maximum_edge_mm)), max(1, ceil(height/maximum_edge_mm))
        if len(result)+nx*ny > remaining_cells:
            raise ValueError("Conforming interior subdivision exceeds the control-cell budget")
        xs = [x0] + [x0+width*i/nx for i in range(1,nx)] + [x1]
        ys = [y0] + [y0+height*i/ny for i in range(1,ny)] + [y1]
        result.extend((xa,ya,xb,yb) for xa,xb in zip(xs,xs[1:]) for ya,yb in zip(ys,ys[1:]))
    return result


def build_conforming_mesh(design: DesignIR, spec: AnalysisSpec) -> HybridMesh:
    """Build an admitted approximation or an explicitly failed partial mesh.

    Shapely is an optional geometry prerequisite for this experimental route.
    The maximum omitted area is a geometry bound, never an R/L error estimate.
    Fixed terminal footprints are subdivided at the effective requested mesh
    size while retaining one terminal identity and their exact physical area.
    Optional mesh.conforming_interior_max_edge_mm subdivides retained
    noncontact rectangles after geometry partition/coalescing. Neither changes
    copper boundaries or finite terminal support.
    """
    builder = _Builder(design, spec)
    mesh = builder.mesh
    try:
        from shapely.geometry import LineString, Point, Polygon, box
        from shapely.ops import unary_union
        from shapely.prepared import prep
    except ImportError:
        return _failure(mesh, "Conforming volume copper requires the optional Shapely geometry backend.")
    if design.units != "mm":
        return _failure(mesh, "Conforming copper partition requires DesignIR units=mm.")
    max_cells = int(spec.mesh.get("max_conforming_cells", 20000))
    max_depth = int(spec.mesh.get("conforming_boundary_depth", 7))
    area_limit = float(spec.mesh.get("conforming_max_omitted_area_fraction", 0.01))
    if not 1 <= max_depth <= 12 or not 0 < area_limit <= 0.02 or not 4 <= max_cells <= 100000:
        return _failure(mesh, "Invalid conforming partition limits (depth 1..12, omitted area <=2%, cells >=4).")
    interior_max_edge = spec.mesh.get("conforming_interior_max_edge_mm")
    if interior_max_edge is not None:
        try:
            if isinstance(interior_max_edge, bool):
                raise ValueError
            interior_max_edge = float(interior_max_edge)
            if not isfinite(interior_max_edge) or interior_max_edge <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return _failure(mesh, "Conforming interior maximum edge must be finite and positive in mm.")
    try:
        requested_target = min(float(spec.mesh.get("target_size_mm", 1.0)),
            float(spec.mesh.get("zone_cell_mm", spec.mesh.get("target_size_mm", 1.0))))
    except (TypeError, ValueError):
        return _failure(mesh, "Conforming requested mesh size must be finite and positive in mm.")
    if not isfinite(requested_target) or requested_target < 0.05:
        return _failure(mesh, "Conforming requested mesh size below 0.05 mm is not admitted; the base builder would silently clamp it.")
    target = min(builder.target, builder.zone_target)
    groups: dict[tuple[str, str], list[tuple[Any, str, str]]] = {}
    holes: dict[tuple[str, str], list[Any]] = {}
    contacts: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def add(layer: str, net: str, geometry: Any, source: str, kind: str) -> None:
        if (not net or layer not in builder.copper_layers
                or builder.requested and net not in builder.requested):
            return
        if not geometry.is_valid or geometry.is_empty or geometry.area <= 0:
            raise ValueError(f"{source} has invalid or empty authoritative copper")
        groups.setdefault((layer, net), []).append((geometry, source, kind))

    try:
        for index, track in enumerate(design.tracks):
            if (builder.requested and _net(track) not in builder.requested
                    or str(track.get("layer", "")) not in builder.copper_layers):
                continue
            source = str(track.get("id", f"track-{index + 1}"))
            start, end = _point(track.get("start", (0, 0))), _point(track.get("end", (0, 0)))
            width = float(track.get("width", 0))
            if width <= 0 or start == end or track.get("mid") is not None:
                raise ValueError(f"{source}: conforming partition currently requires straight positive-width tracks")
            add(str(track.get("layer", "")), _net(track),
                LineString([start, end]).buffer(width / 2, quad_segs=32), source, "track")
        for index, zone in enumerate(design.zones):
            if (builder.requested and _net(zone) not in builder.requested
                    or str(zone.get("layer", "")) not in builder.copper_layers):
                continue
            from .hybrid_mesh import _normalize_filled_zone_polygon
            polygon = _normalize_filled_zone_polygon([_point(p) for p in zone.get("points", [])])
            add(str(zone.get("layer", "")), _net(zone), Polygon(polygon),
                str(zone.get("id", f"zone-{index + 1}")), "zone")
        for index, pad in enumerate(design.pads):
            if builder.requested and _net(pad) not in builder.requested:
                continue
            layers = _pad_layers(pad, builder.copper_layers)
            if not layers:
                continue
            source = str(pad.get("id") or pad.get("component_pad") or f"pad-{index + 1}")
            net = _net(pad)
            from .quasistatic_copper_area import _source_polygon
            polygon = Polygon(_source_polygon("pad", pad))
            center = _point(pad.get("at", (0, 0)))
            width, height = _pad_size(pad)
            if _pad_has_drill(pad):
                raise ValueError(f"{source}: plated/slot pad contact requires an annular conforming contact model")
            # A fixed interior control volume defines the original pad terminal.
            # It is a copper cell, with finite half-cell loss to every face;
            # no finite attachment resistor is deleted or made ideal.
            size = min(width, height) / 4
            contact = box(center[0] - size / 2, center[1] - size / 2,
                          center[0] + size / 2, center[1] + size / 2)
            if not polygon.covers(contact):
                raise ValueError(f"{source}: fixed terminal contact is not fully supported by pad copper")
            for layer in layers:
                add(layer, net, polygon, source, "pad")
                contacts.setdefault((layer, net), []).append({"shape": contact,
                    "source": source, "kind": "pad", "center": center})
        builder.vias()
        if mesh.truncated:
            return _failure(mesh, "Vertical bases already exceed the branch resource budget")
        for index, via in enumerate(design.vias):
            net = _net(via)
            if builder.requested and net not in builder.requested:
                continue
            source = str(via.get("id", f"via-{index + 1}"))
            center = _point(via.get("at", (0, 0)))
            drill = float(via.get("drill", 0.3))
            plating = float(via.get("plating_thickness", via.get("plating_thickness_mm", spec.mesh.get("via_plating_thickness_mm", 0.025))))
            outer = drill / 2 + plating
            # Circumscribe drill void; inscribe the outer land/contact. This
            # excludes actual void copper rather than filling the drill.
            from math import cos
            hole = Point(center).buffer(drill / 2 / cos(pi / 128), quad_segs=32)
            ring = Point(center).buffer(outer, quad_segs=32).difference(hole)
            land = Point(center).buffer(max(float(via.get("size", 2*outer))/2, outer), quad_segs=32)
            via_nodes = {node_id for branch in mesh.branches if branch.source_id == source
                         for node_id in (branch.node_p, branch.node_n)}
            for node_id in sorted(via_nodes):
                layer = mesh.nodes[node_id].layer
                add(layer, net, land.difference(hole), source, "via")
                holes.setdefault((layer, net), []).append(hole)
                radial_low, radial_high = drill/2+plating/4, drill/2+3*plating/4
                half_tangent = sqrt(max(0.0, outer*outer-radial_high*radial_high))/2
                # Four fixed, finite copper contacts around the annular
                # terminal. Each is wholly in plated copper. The axial basis
                # retains its full source annulus normalization; unresolved
                # within-barrel redistribution remains an explicit uniform
                # axial-current approximation, never a fictitious planar link.
                for axis in (0, 1):
                    for sign in (-1, 1):
                        low, high = sorted((sign*radial_low, sign*radial_high))
                        bounds = (center[0]+low,center[1]-half_tangent,center[0]+high,center[1]+half_tangent) if axis == 0 else (center[0]-half_tangent,center[1]+low,center[0]+half_tangent,center[1]+high)
                        contact = box(*bounds)
                        if not ring.covers(contact):
                            raise ValueError(f"{source}: finite landing contact leaves annular copper")
                        contacts.setdefault((layer, net), []).append({"shape": contact,
                            "source": source, "kind": "via", "center": center,
                            "node": node_id, "physical_area_mm2": pi*plating*(drill+plating)})
    except (ValueError, TypeError, KeyError) as error:
        return _failure(mesh, str(error))

    group_reports = []
    terminal_support = []
    quality = {"method": "interior_rectangles_shared_face_flux",
        "outside_area_tolerance_mm2": 1e-8, "support_outside_area_max_mm2": 0.0,
        "maximum_omitted_area_fraction": area_limit, "boundary_depth": max_depth,
        "requested_target_mm": requested_target, "effective_target_mm": target,
        "interior_max_edge_mm": interior_max_edge, "interior_subdivision_added_cells": 0,
        "contact_max_edge_mm": target, "contact_subdivision_added_cells": 0,
        "groups": group_reports, "terminal_contacts": terminal_support,
        "potential_approximation": "cellwise_constant; nonorthogonal/adaptive-face accuracy requires refinement",
        "via_contact_approximation": "four fixed finite annular landing contacts per axial terminal; uniform axial barrel current",
        "area_bound_is_not_port_error_bound": True}
    mesh.branch_admission["conforming_partition"] = quality
    all_cells: list[_Cell] = []
    visited_boxes = 0
    for (layer, net), records in sorted(groups.items()):
        copper = unary_union([record[0] for record in records])
        if holes.get((layer, net)):
            copper = copper.difference(unary_union(holes[(layer, net)]))
        if not copper.is_valid:
            return _failure(mesh, f"{layer}/{net}: copper union is invalid")
        z = builder.layer_z[layer]
        thickness = builder.thickness[layer]
        layer_cells: list[_Cell] = []
        bounded_records = [(geometry.bounds, geometry, source, kind) for geometry, source, kind in records]

        def accept(bounds: tuple[float, float, float, float], owner: str = "", kind: str = "", contact_node: int | None = None) -> None:
            if len(all_cells) >= max_cells:
                raise ValueError(f"Conforming copper exceeded {max_cells} control cells")
            x0, y0, x1, y1 = bounds
            center = ((x0 + x1) / 2, (y0 + y1) / 2)
            if not owner:
                point = Point(center)
                matches = [(geometry,source,kind) for bounds, geometry,source,kind in bounded_records
                    if bounds[0] <= center[0] <= bounds[2] and bounds[1] <= center[1] <= bounds[3] and geometry.covers(point)]
                # Give pads stable anchor ownership over coincident zones.
                matches.sort(key=lambda item: (item[2] != "pad", item[2] != "track", item[1]))
                _, owner, kind = matches[0]
            node = len(mesh.nodes) if contact_node is None else contact_node
            if contact_node is None:
                mesh.nodes.append(MeshNode(node, *center, z, layer, net))
            cell = _Cell(bounds, node, owner, kind)
            layer_cells.append(cell)
            all_cells.append(cell)
            mesh.cells.append({"id": f"conforming:{layer}:{net}:{len(all_cells)}",
                "kind": "surface", "source_kind": kind, "source_id": owner,
                "layer": layer, "net": net, "vertices_mm": [
                    [x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]],
                "control_node": node})

        fixed = contacts.get((layer, net), [])
        try:
            for index, contact in enumerate(fixed):
                if any(contact["shape"].intersection(other["shape"]).area > 1e-12 for other in fixed[:index]):
                    raise ValueError("Overlapping fixed terminal contacts are not admitted")
                subcells = _subdivide_interior_rectangles(
                    [tuple(contact["shape"].bounds)], target, max_cells-len(all_cells))
                quality["contact_subdivision_added_cells"] += len(subcells)-1
                terminal_node = contact.get("node")
                for bounds in subcells:
                    accept(bounds, contact["source"], contact["kind"], terminal_node)
                    if terminal_node is None:
                        terminal_node = layer_cells[-1].node
                        # A shared terminal label is a physical footprint,
                        # not the first subcell's representative point.
                        center = contact["shape"].centroid
                        mesh.nodes[terminal_node].x_mm = center.x
                        mesh.nodes[terminal_node].y_mm = center.y
                contact["node"] = terminal_node
                terminal_support.append({"source_id": contact["source"], "layer": layer,
                    "node": contact["node"], "kind": contact["kind"], "area_mm2": contact["shape"].area,
                    "physical_area_mm2": contact.get("physical_area_mm2", contact["shape"].area),
                    "bounds_mm": list(contact["shape"].bounds)})
            fixed_shapes = [contact["shape"] for contact in fixed]
            active = copper.difference(unary_union(fixed_shapes)) if fixed_shapes else copper
            prepared = prep(active)
            xmin, ymin, xmax, ymax = copper.bounds
            # Include contact edges in the initial Cartesian partition, so no
            # omitted sliver is introduced around a fixed terminal support.
            xs = sorted(set([xmin, xmax] + [min(xmax, xmin + i * target) for i in range(1, int(ceil((xmax-xmin)/target)))]
                + [value for contact in fixed for value in (contact["shape"].bounds[0], contact["shape"].bounds[2])]))
            ys = sorted(set([ymin, ymax] + [min(ymax, ymin + i * target) for i in range(1, int(ceil((ymax-ymin)/target)))]
                + [value for contact in fixed for value in (contact["shape"].bounds[1], contact["shape"].bounds[3])]))
            if len(xs) * len(ys) > max_cells * 8:
                raise ValueError("Conforming initial partition exceeds the geometry work budget")
            interior_rectangles: list[tuple[float, float, float, float]] = []

            def partition(bounds: tuple[float, float, float, float], depth: int) -> None:
                nonlocal visited_boxes
                visited_boxes += 1
                quality["visited_box_count"] = visited_boxes
                if visited_boxes > max_cells * 8:
                    raise ValueError(f"Conforming partition exceeded its {max_cells*8} visited-box work budget")
                rect = box(*bounds)
                if prepared.covers(rect):
                    interior_rectangles.append(bounds)
                    return
                if depth == max_depth or not prepared.intersects(rect):
                    return
                x0, y0, x1, y1 = bounds
                xm, ym = (x0+x1)/2, (y0+y1)/2
                if x1-x0 >= 2*(y1-y0):
                    children = ((x0,y0,xm,y1), (xm,y0,x1,y1))
                elif y1-y0 >= 2*(x1-x0):
                    children = ((x0,y0,x1,ym), (x0,ym,x1,y1))
                else:
                    children = ((x0,y0,xm,ym), (xm,y0,x1,ym), (x0,ym,xm,y1), (xm,ym,x1,y1))
                for child in children:
                    partition(child, depth+1)

            for x0, x1 in zip(xs, xs[1:]):
                for y0, y1 in zip(ys, ys[1:]):
                    if x1-x0 > 1e-12 and y1-y0 > 1e-12:
                        partition((x0,y0,x1,y1), 0)
            coalesced = _coalesce_rectangles(interior_rectangles, target)
            quality["raw_interior_rectangle_count"] = quality.get("raw_interior_rectangle_count", 0)+len(interior_rectangles)
            quality["coalesced_interior_rectangle_count"] = quality.get("coalesced_interior_rectangle_count", 0)+len(coalesced)
            if interior_max_edge is not None:
                subdivided = _subdivide_interior_rectangles(coalesced, interior_max_edge, max_cells-len(all_cells))
                quality["interior_subdivision_added_cells"] += len(subdivided)-len(coalesced)
                coalesced = subdivided
            for bounds in coalesced:
                accept(bounds)
        except ValueError as error:
            return _failure(mesh, str(error))
        represented = sum((c.bounds[2]-c.bounds[0])*(c.bounds[3]-c.bounds[1]) for c in layer_cells)
        omitted = max(0.0, copper.area - represented)
        report = {"layer": layer, "net": net, "copper_area_mm2": copper.area,
            "represented_area_mm2": represented, "omitted_area_mm2": omitted,
            "omitted_area_fraction": omitted/copper.area, "cell_count": len(layer_cells)}
        group_reports.append(report)
        if omitted/copper.area > area_limit:
            return _failure(mesh, f"{layer}/{net}: omitted copper area {omitted/copper.area:.6g} exceeds {area_limit:.6g}")
        # Index opposing faces; overlaps are genuine positive-area contacts.
        left: dict[float, list[_Cell]] = {}
        right: dict[float, list[_Cell]] = {}
        bottom: dict[float, list[_Cell]] = {}
        top: dict[float, list[_Cell]] = {}
        for cell in layer_cells:
            x0,y0,x1,y1 = cell.bounds
            for index, coordinate in ((left,x0),(right,x1),(bottom,y0),(top,y1)):
                index.setdefault(round(coordinate, 12), []).append(cell)
        for first_faces, second_faces, axis in ((right,left,0),(top,bottom,1)):
            for coordinate, first_cells in first_faces.items():
                tangent = 1-axis
                first_sorted = sorted(first_cells, key=lambda cell: cell.bounds[tangent])
                second_sorted = sorted(second_faces.get(coordinate, []), key=lambda cell: cell.bounds[tangent])
                cursor = 0
                for first in first_sorted:
                    while cursor < len(second_sorted) and second_sorted[cursor].bounds[tangent+2] <= first.bounds[tangent]+1e-12:
                        cursor += 1
                    for second in second_sorted[cursor:]:
                        if second.bounds[tangent] >= first.bounds[tangent+2]-1e-12:
                            break
                        low = max(first.bounds[tangent], second.bounds[tangent])
                        high = min(first.bounds[tangent+2], second.bounds[tangent+2])
                        if high-low <= 1e-12:
                            continue
                        if first.node == second.node:
                            continue
                        if len(mesh.branches) >= builder.max_branches:
                            return _failure(mesh, f"Conforming face currents exceed {builder.max_branches} branch budget")
                        midpoint = (low+high)/2
                        a = (first.bounds[axis]+first.bounds[axis+2])/2
                        b = (second.bounds[axis]+second.bounds[axis+2])/2
                        start = (a,midpoint,z) if axis == 0 else (midpoint,a,z)
                        end = (b,midpoint,z) if axis == 0 else (midpoint,b,z)
                        chosen = min((first,second), key=lambda cell: ({"pad":0,"zone":1,"track":2,"via":3}[cell.kind], cell.source))
                        # A lateral via-land face is not source zone copper and
                        # must not be looked up as a zone for capacitance.
                        owner, kind = chosen.source, chosen.kind if chosen.kind != "via" else "via_landing"
                        branch = MeshBranch(f"conforming:{len(mesh.branches)}:{first.node}:{second.node}", kind,
                            first.node, second.node, start, end, high-low, thickness,
                            COPPER_CONDUCTIVITY_S_M, layer, net, owner)
                        support = box(a,low,b,high) if axis == 0 else box(low,a,high,b)
                        outside = support.difference(copper).area
                        quality["support_outside_area_max_mm2"] = max(quality["support_outside_area_max_mm2"], outside)
                        if outside > 1e-8:
                            return _failure(mesh, f"{branch.id}: rectangular support leaves copper by {outside:.9g} mm2")
                        mesh.branches.append(branch)
        # A small omitted-area fraction must never excuse severing a thin
        # conductor. Check every retained rectangle in each source component.
        parent = {cell.node: cell.node for cell in layer_cells}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for branch in mesh.branches:
            if branch.layer == layer and branch.net == net:
                parent[find(branch.node_p)] = find(branch.node_n)
        components = list(copper.geoms) if copper.geom_type == "MultiPolygon" else [copper]
        for component in components:
            roots = {find(cell.node) for cell in layer_cells
                if component.covers(Point((cell.bounds[0]+cell.bounds[2])/2,
                                          (cell.bounds[1]+cell.bounds[3])/2))}
            if len(roots) != 1:
                return _failure(mesh, f"{layer}/{net}: interior partition disconnected or omitted a source copper component ({len(roots)} retained components)")
        for kind in mesh.geometry_counts:
            mesh.geometry_counts[kind] += sum(record[2] == kind for record in records)
    mesh.issues.append(ValidationIssue("PEEC_CONFORMING_PARTITION_APPROXIMATE", "warning",
        "Interior rectangular copper partition passed its area gate; port R/L convergence remains required.",
        status="approximate"))
    return mesh
