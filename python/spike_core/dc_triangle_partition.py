# SPDX-License-Identifier: Apache-2.0
"""Experimental complete polygon partition for conservative DC fields.

This is a geometry-only adapter. No copper component is discarded. Contacts
must be supplied as finite physical polygons; a coordinate is not a footprint.
Public Shapely operations are used, not external mesher implementation code.
"""
from __future__ import annotations

from math import isfinite

import numpy as np

from .hybrid_mesh import HybridMesh, MeshBranch, MeshNode


def refine_triangles(triangles, owners, target, budget):
    """Conforming edge-midpoint refinement; common edges get common splits.

    Mark every overlength edge simultaneously. A triangle with two marked
    edges has a corner triangle and a quadrilateral; use its shorter diagonal.
    The subdivision preserves the exact parent union and every boundary.
    """
    triangles = np.asarray(triangles, dtype=float)
    owners = list(owners)
    for _ in range(32):
        result, next_owners = [], []
        marked = 0
        for vertices, owner in zip(triangles, owners):
            a, b, c = vertices
            mids = [(a+b)/2, (b+c)/2, (c+a)/2]
            flags = [np.linalg.norm(vertices[(i+1)%3]-vertices[i]) > target*(1+1e-12)
                     for i in range(3)]
            count = sum(flags)
            marked += count
            if count == 0:
                children = [(a,b,c)]
            elif count == 3:
                ab, bc, ca = mids
                children = [(a,ab,ca), (ab,b,bc), (ca,bc,c), (ab,bc,ca)]
            elif count == 1:
                i = flags.index(True)
                a,b,c = (vertices[(i+j)%3] for j in range(3))
                m = mids[i]
                children = [(a,m,c),(m,b,c)]
            else:
                # Rotate so AB and BC are marked, CA is not.
                i = (flags.index(False)+1)%3
                a,b,c = (vertices[(i+j)%3] for j in range(3))
                ab,bc = (a+b)/2,(b+c)/2
                children = [(ab,b,bc)]
                if np.linalg.norm(a-bc) <= np.linalg.norm(ab-c):
                    children += [(a,ab,bc),(a,bc,c)]
                else:
                    children += [(a,ab,c),(ab,bc,c)]
            result.extend(children)
            next_owners.extend([owner]*len(children))
            if len(result) > budget:
                raise ValueError("Complete triangle partition exceeds triangle budget")
        triangles, owners = np.asarray(result), next_owners
        if not marked:
            return triangles, owners
    raise ValueError("Complete triangle refinement exceeds 32 subdivision rounds")


def partition_polygon_groups(groups, contacts, *, target_mm, max_triangles=100000,
                             mesh=None, geometry_grid_mm=0.0):
    """Compile nonoverlapping triangles from full copper unions and contacts.

    groups: (layer, net) -> {geometry, thickness_mm, conductivity_s_m, z_mm}.
    contacts: records {layer, net, id, geometry, node(optional)}. Each contact
    injects uniformly per physical area, with power-conjugate average voltage.
    Existing mesh branches, if any, must be actual axial barrels only.
    Positive geometry_grid_mm explicitly admits a bounded fixed-grid geometry
    model with topology/contact/uncertainty audits; zero keeps legacy noding.
    """
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from .dc_precision_partition import polygon_regions
    if (isinstance(geometry_grid_mm, bool) or not isinstance(geometry_grid_mm, (int, float))
            or not isfinite(geometry_grid_mm) or geometry_grid_mm < 0):
        raise ValueError("Precision grid must be a finite nonnegative length")
    if (not isfinite(target_mm) or target_mm <= 0 or isinstance(max_triangles, bool)
            or not isinstance(max_triangles, int) or not 4 <= max_triangles <= 250000):
        raise ValueError("Invalid complete triangle partition size/budget")
    mesh = HybridMesh() if mesh is None else mesh
    contacts = [dict(contact) for contact in contacts]
    if not groups or len(groups) > 1024 or len(contacts) > 4096:
        raise ValueError("Complete partition group/contact work budget exceeded")
    if mesh.cells or any(b.kind not in {"via", "pad_barrel"} for b in mesh.branches):
        raise ValueError("Complete partition accepts only axial barrel seed branches")
    quality = {"method":"complete_polygon_RT0_triangles", "groups":[],
               "terminal_contacts":[], "omitted_polygon_area_mm2":0.0,
               "all_copper_components_retained":True,
               "contact_model":"prescribed uniform area injection; conjugate mean potential"}
    mesh.branch_admission["conforming_partition"] = quality
    mesh.branch_admission["complete_triangle_partition"] = True
    mesh.target_size_mm = target_mm
    contact_ids = set()
    for contact in contacts:
        if contact["id"] in contact_ids:
            raise ValueError("Finite contact identities must be unique")
        contact_ids.add(contact["id"])
        if (contact["layer"], contact["net"]) not in groups:
            raise ValueError("Finite contact has no selected copper group")
    prior = []
    vertex_count = 0
    for group in groups.values():
        geometry = group["geometry"]
        polygons = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        if any(p.geom_type != "Polygon" for p in polygons):
            raise ValueError("Complete partition requires polygonal copper")
        vertex_count += sum(len(p.exterior.coords)+sum(len(r.coords) for r in p.interiors) for p in polygons)
        if vertex_count > min(100000,3*max_triangles):
            raise ValueError("Complete partition source-vertex work budget exceeded")
        z,thickness = float(group["z_mm"]),float(group["thickness_mm"])
        if not isfinite(z) or not isfinite(thickness) or thickness <= 0:
            raise ValueError("Complete partition requires finite positive physical layer support")
        for other,other_z,other_t in prior:
            overlap_z = min(z+thickness/2,other_z+other_t/2)-max(z-thickness/2,other_z-other_t/2)
            if overlap_z > 0 and geometry.intersection(other).area > 1e-12:
                raise ValueError("Complete partition copper prisms overlap across layer/net groups")
            if overlap_z > 0 and geometry_grid_mm:
                distance = geometry.distance(other)
                if 0 < distance <= 32*geometry_grid_mm:
                    raise ValueError("Precision grid cannot resolve separation between copper groups")
        prior.append((geometry,z,thickness))
    admitted_prior = []
    for key, group in sorted(groups.items()):
        copper = group["geometry"]
        thickness = float(group["thickness_mm"])
        conductivity = float(group["conductivity_s_m"])
        if (copper.is_empty or not copper.is_valid or copper.area <= 0
                or not all(isfinite(v) and v > 0 for v in (thickness,conductivity))):
            raise ValueError("Complete partition requires valid positive copper/material")
        fixed = [c for c in contacts if (c["layer"], c["net"]) == key]
        for i, contact in enumerate(fixed):
            shape = contact["geometry"]
            polygons = list(shape.geoms) if shape.geom_type == "MultiPolygon" else [shape]
            if any(p.geom_type != "Polygon" for p in polygons):
                raise ValueError("Finite contact must be polygonal")
            vertex_count += sum(len(p.exterior.coords)+sum(len(r.coords) for r in p.interiors) for p in polygons)
            if vertex_count > min(100000,3*max_triangles):
                raise ValueError("Complete partition contact-vertex work budget exceeded")
            if (shape.is_empty or not shape.is_valid or shape.area <= 0
                    or not copper.covers(shape)):
                raise ValueError(f"Finite contact {contact['id']} leaves actual copper")
            if any(shape.intersection(other["geometry"]).area > 1e-12 for other in fixed[:i]):
                raise ValueError("Overlapping finite contacts require a separate contact model")
            if "node" not in contact:
                node = len(mesh.nodes)
                center = shape.centroid
                mesh.nodes.append(MeshNode(node,center.x,center.y,group["z_mm"],*key))
                contact["node"] = node
            elif (isinstance(contact["node"],bool) or not isinstance(contact["node"],int) or not 0 <= contact["node"] < len(mesh.nodes)
                    or (mesh.nodes[contact["node"]].layer,mesh.nodes[contact["node"]].net) != key):
                raise ValueError("Finite contact has invalid pre-existing node support")
            quality["terminal_contacts"].append({"id":contact["id"], "node":contact["node"],
                "layer":key[0], "net":key[1], "area_mm2":shape.area})
        regions, precision = polygon_regions(copper, fixed, geometry_grid_mm, target_mm)
        triangles, owners = [], []
        for region in regions:
            matching = [c for c in fixed if c["geometry"].covers(region.representative_point())]
            owner = matching[0]["node"] if matching else -1
            for triangle in constrained_delaunay_triangles(region).geoms:
                points = np.asarray(triangle.exterior.coords[:-1])
                if points.shape != (3,2):
                    raise ValueError("Constrained triangulation did not return a triangle")
                delta = points[1:]-points[0]
                if delta[0,0]*delta[1,1]-delta[0,1]*delta[1,0] < 0:
                    points = points[[0,2,1]]
                triangles.append(points)
                owners.append(owner)
                if len(triangles)+len(mesh.cells) > max_triangles:
                    raise ValueError("Complete triangle partition exceeds triangle budget")
        triangles, owners = refine_triangles(triangles,owners,target_mm,max_triangles-len(mesh.cells))
        polygons = [Polygon(t) for t in triangles]
        represented = unary_union(polygons)
        outside = represented.difference(copper).area
        missing = copper.difference(represented).area
        overlap = sum(p.area for p in polygons)-represented.area
        tolerance = max(1e-11, copper.area*1e-11)
        if max(outside,missing,overlap) > tolerance:
            raise ValueError("Complete triangles fail source union/ownership conservation")
        if geometry_grid_mm:
            for original, admitted, other_z, other_t in admitted_prior:
                if min(group["z_mm"]+thickness/2, other_z+other_t/2) > max(group["z_mm"]-thickness/2, other_z-other_t/2):
                    if copper.relate(original) != represented.relate(admitted):
                        raise ValueError("Precision partition changed copper-group topology")
            admitted_prior.append((copper, represented, group["z_mm"], thickness))
        quality["groups"].append({"layer":key[0],"net":key[1],"source_area_mm2":copper.area,
            "represented_area_mm2":represented.area,"omitted_area_mm2":missing,
            "outside_area_mm2":outside,"overlap_area_mm2":max(0.,overlap),
            "triangle_count":len(triangles)})
        if precision is not None:
            quality["groups"][-1]["precision_geometry"] = precision
        quality["omitted_polygon_area_mm2"] += missing
        for vertices,owner in zip(triangles,owners):
            if owner == -1:
                owner = len(mesh.nodes)
                center = vertices.mean(axis=0)
                mesh.nodes.append(MeshNode(owner,*center,group["z_mm"],*key))
            mesh.cells.append({"id":f"triangle:{len(mesh.cells)}", "kind":"surface",
                "source_kind":"copper_union", "source_id":f"{key[0]}/{key[1]}",
                "control_node":owner,"layer":key[0],"net":key[1],
                "vertices_mm":[[float(x),float(y),group["z_mm"]] for x,y in vertices],
                "thickness_mm":thickness,"conductivity_s_m":conductivity})
    return mesh
