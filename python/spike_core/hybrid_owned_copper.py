# SPDX-License-Identifier: MIT
"""Opt-in pad-owned copper partition for hybrid DC; no geometry dependency.

Convex half-plane clipping partitions retained zone cells outside convex pad
outlines. Pads own their metal; their enclosed drill voids own no conductor.
All quantities use millimetres. This remains a finite-volume approximation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from math import ceil, hypot, pi, floor

from .contracts import ValidationIssue


def cross(a, b, p):
    return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])


def area(poly):
    if len(poly) < 3:
        return 0.0
    origin = poly[0]
    return abs(sum(cross(origin, a, b) for a, b in zip(poly[1:], poly[2:]))) / 2


def centroid(poly):
    origin = poly[0]
    terms = [(cross(origin, a, b), a, b) for a, b in zip(poly[1:], poly[2:])]
    weight = sum(t[0] for t in terms)
    if abs(weight) <= 1e-18:
        return None
    return tuple(origin[i] + sum(w*((a[i]-origin[i])+(b[i]-origin[i])) for w,a,b in terms)/(3*weight) for i in (0,1))


def hull(points):
    points = sorted(set(points))
    def half(items):
        out = []
        for p in items:
            while len(out) >= 2 and cross(out[-2], out[-1], p) <= 1e-12:
                out.pop()
            out.append(p)
        return out
    return half(points)[:-1] + half(reversed(points))[:-1]


def bounds(poly):
    return min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly), max(p[1] for p in poly)


def boxes_overlap(a, b, tolerance=1e-8):
    return not (a[2] < b[0]-tolerance or b[2] < a[0]-tolerance or a[3] < b[1]-tolerance or b[3] < a[1]-tolerance)


def clip_half_plane(poly, a, b, inside=True):
    """Clip a convex polygon by one oriented line; independently derived."""
    if not poly:
        return []
    result = []
    previous = poly[-1]
    vp = cross(a,b,previous) * (1 if inside else -1)
    for point in poly:
        value = cross(a,b,point) * (1 if inside else -1)
        if (vp >= 0) != (value >= 0):
            ratio = vp/(vp-value)
            result.append(tuple(previous[i]+ratio*(point[i]-previous[i]) for i in (0,1)))
        if value >= 0:
            result.append(point)
        previous, vp = point, value
    cleaned = []
    for point in result:
        if not cleaned or hypot(point[0]-cleaned[-1][0], point[1]-cleaned[-1][1]) > 1e-10:
            cleaned.append(point)
    if len(cleaned)>1 and hypot(cleaned[0][0]-cleaned[-1][0],cleaned[0][1]-cleaned[-1][1]) <= 1e-10:
        cleaned.pop()
    return cleaned if area(cleaned)>1e-12 else []


def difference(subject, cutter):
    """Disjoint convex pieces of subject minus a convex CCW cutter."""
    if not boxes_overlap(bounds(subject), bounds(cutter)):
        return [subject]
    remaining, result = subject, []
    for a,b in zip(cutter,cutter[1:]+cutter[:1]):
        outside = clip_half_plane(remaining,a,b,False)
        if outside:
            result.append(outside)
        remaining = clip_half_plane(remaining,a,b)
        if not remaining:
            break
    return result


def fail(builder, message):
    builder.mesh.branches.clear()
    builder.mesh.issues.append(ValidationIssue("OWNED_COPPER_UNSUPPORTED", "error", message,
        status="unsupported", suggestion="Use admitted convex pads with retained source-filled contact evidence."))


def prepare(builder):
    """Read actual pad cells, validate ownership, and replace pad branch widths."""
    from .hybrid_mesh import (_shared_polygon_face_length, _pad_size, _pad_has_drill,
        _pad_boundary_polygon, _pad_local_to_world, _annular_pad_local_cells,
        _circumscribed_shape_polygon, _pad_drill_shape, _pad_drill_size)
    from .quasistatic_copper_area import _source_polygon
    pads = {str(p.get("id")):p for p in builder.design.pads}
    profiles = defaultdict(dict)
    node_polygons = {}
    for cell in builder.mesh.cells:
        if cell["source_kind"] != "pad" or "node_id" not in cell:
            continue
        poly = [tuple(p[:2]) for p in cell["vertices_mm"]]
        key = cell["layer"], cell["net"]
        profile = profiles[key].setdefault(cell["source_id"], {"id":cell["source_id"],"cells":[]})
        profile["cells"].append((cell["node_id"],poly))
        node_polygons[cell["node_id"]] = poly
    for group in profiles.values():
        for profile in group.values():
            profile["outline"] = hull([p for _,poly in profile["cells"] for p in poly])
            profile["bounds"] = bounds(profile["outline"])
            profile["metal_area_mm2"] = sum(area(poly) for _,poly in profile["cells"])
            profile["void_area_mm2"] = area(profile["outline"])-profile["metal_area_mm2"]
            pad = pads[profile["id"]]
            width,height = _pad_size(pad)
            expected_void = 0.0
            if _pad_has_drill(pad):
                cells,_ = _annular_pad_local_cells(pad,builder.target)
                expected = hull([_pad_local_to_world(pad,*p) for poly in cells for p in poly])
                sides = max(24,min(192,int(ceil(pi*max(width,height)/max(builder.target,.01)))))
                expected_void = area(_circumscribed_shape_polygon(_pad_drill_shape(pad),*_pad_drill_size(pad),sides))
            elif str(pad.get("shape","rect")) in {"circle","oval"}:
                sides = max(24,min(96,int(ceil(pi*max(width,height)/max(builder.target,.01)))))
                expected = _pad_boundary_polygon(pad,sides)
            else:
                expected = _source_polygon("pad",pad)
            outside = sum(area(p) for p in difference(profile["outline"],hull(expected)))
            missing = sum(area(p) for p in difference(hull(expected),profile["outline"]))
            if outside+missing > 1e-8 or abs(profile["void_area_mm2"]-expected_void)>1e-8:
                fail(builder,f"Pad cells do not preserve authoritative outer boundary/drill area: {profile['id']}")
                return False
            profile["void_area_mm2"] = max(0.0,profile["void_area_mm2"])
        prior = []
        for profile in group.values():
            for other in prior:
                if boxes_overlap(profile["bounds"],other["bounds"]):
                    overlap = area(profile["outline"])-sum(area(p) for p in difference(profile["outline"],other["outline"]))
                    if overlap > 1e-8:
                        fail(builder, f"Owned route does not admit overlapping pad outlines: {profile['id']} and {other['id']}")
                        return False
            prior.append(profile)
    updated = []
    for branch in builder.mesh.branches:
        if branch.kind == "pad" and branch.node_p in node_polygons and branch.node_n in node_polygons:
            width = _shared_polygon_face_length(node_polygons[branch.node_p],node_polygons[branch.node_n],builder.containment_tolerance)
            if width <= 1e-7:
                continue
            branch = replace(branch,width_mm=width)
        updated.append(branch)
    builder.mesh.branches = updated
    builder.owned_pad_profiles = profiles
    pad_ids = {p["id"] for g in profiles.values() for p in g.values()}
    builder.owned_pad_nodes = set(node_polygons) | {n for b in builder.mesh.branches if b.source_id in pad_ids for n in (b.node_p,b.node_n)}
    builder.mesh.branch_admission["owned_copper"] = {
        "method":"pad_owned_shared_faces", "input_zone_cell_area_mm2":0.0, "removed_zone_area_mm2":0.0, "contacts":[],
        "pad_metal_area_mm2":sum(p["metal_area_mm2"] for g in profiles.values() for p in g.values()),
        "pad_void_area_mm2":sum(p["void_area_mm2"] for g in profiles.values() for p in g.values()),
        "status":"approximate", "limitations":["Nonorthogonal finite-volume branch distance requires refinement", "Pad barrel retains its existing angular landing approximation", "Track/zone and via/zone overlap are not repartitioned"],
    }
    return True


def subtract(builder, fragments, layer, net):
    from .hybrid_mesh import _triangulate_polygon
    profiles = builder.owned_pad_profiles.get((layer,net),{})
    result = []
    for fragment in fragments:
        builder.mesh.branch_admission["owned_copper"]["input_zone_cell_area_mm2"] += area(fragment)
        orientation = 1 if sum(cross(fragment[0],a,b) for a,b in zip(fragment[1:],fragment[2:])) >= 0 else -1
        convex = all(orientation*cross(fragment[i-1],fragment[i],fragment[(i+1)%len(fragment)]) >= -1e-12 for i in range(len(fragment)))
        pieces = [fragment] if convex else _triangulate_polygon(fragment)
        relevant = [p for p in profiles.values() if boxes_overlap(bounds(fragment),p["bounds"])]
        if not relevant:
            result.extend(pieces)
            continue
        initial = area(fragment)
        # Clipping a concave subject can return disconnected pieces. Convex
        # triangulation makes every half-plane operation unambiguous.
        for profile in relevant:
            pieces = [part for piece in pieces for part in difference(piece,profile["outline"])]
        removed = initial-sum(area(piece) for piece in pieces)
        if removed < -1e-8:
            raise ValueError("Owned copper clipping increased conductor area")
        builder.mesh.branch_admission["owned_copper"]["removed_zone_area_mm2"] += max(0.0,removed)
        result.extend(pieces)
    return result


def bent_zone_link(builder, branch_id, a, b, width, thickness, layer, net, source_id, left, right):
    """Route an otherwise exterior centroid chord through its real shared face."""
    from .hybrid_mesh import _segments, _point_in_polygon
    weighted=[]
    for start,end in _segments(left):
        dx,dy=end[0]-start[0],end[1]-start[1]
        length=hypot(dx,dy)
        if length<=1e-12:continue
        for p,q in _segments(right):
            other_length=hypot(q[0]-p[0],q[1]-p[1])
            if other_length<=1e-12:continue
            tolerance=min(builder.containment_tolerance,1e-10) if min(length,other_length)<=builder.containment_tolerance else builder.containment_tolerance
            if any(abs(cross(start,end,v))/length>tolerance for v in (p,q)):continue
            low,high=sorted(((v[0]-start[0])*dx+(v[1]-start[1])*dy)/length for v in (p,q))
            low,high=max(0,low),min(length,high)
            if high-low>1e-12:
                ratio=(low+high)/(2*length)
                weighted.append((high-low,(start[0]+ratio*dx,start[1]+ratio*dy)))
    total=sum(w for w,p in weighted)
    if total<=1e-7:raise ValueError("Missing positive face for an owned zone link")
    point=tuple(sum(w*p[i] for w,p in weighted)/total for i in (0,1))
    if not all(_point_in_polygon(point,poly,builder.containment_tolerance) for poly in (left,right)):
        raise ValueError("Shared face midpoint is outside its admitted convex cells")
    node=builder.zone_node(point,layer,net)
    builder.owned_face_nodes[node]=(a,b)
    builder.add_branch(branch_id+":half-a","zone",a,node,width,thickness,layer,net,source_id)
    builder.add_branch(branch_id+":half-b","zone",node,b,width,thickness,layer,net,source_id)


def couple(builder):
    from .hybrid_mesh import _shared_polygon_face_length
    audit = builder.mesh.branch_admission["owned_copper"]
    audit["remaining_zone_cell_area_mm2"] = sum(area(poly) for region in builder.zone_regions for poly in region["cell_polygons"].values())
    audit["zone_area_balance_error_mm2"] = audit["input_zone_cell_area_mm2"]-audit["removed_zone_area_mm2"]-audit["remaining_zone_cell_area_mm2"]
    if abs(audit["zone_area_balance_error_mm2"])>1e-8:
        fail(builder,"Owned zone partition does not conserve its admitted input cell area")
        return
    for region in builder.zone_regions:
        for profile in builder.owned_pad_profiles.get((region["layer"],region["net"]),{}).values():
            evidence = builder.zone_pad_attachment_evidence.get((profile["id"],region["source_id"],region["layer"]), "")
            if (profile["id"],region["source_id"],region["layer"]) in builder.zone_pad_declared_none:
                continue
            count = 0
            length = 0.0
            for pn,pp in profile["cells"]:
                pb = bounds(pp)
                # Only grid bins touching this pad cell can share its boundary.
                size = region["cell_mm"]
                x0,x1 = (floor((pb[k]-region["min_x"])/size) for k in (0,2))
                y0,y1 = (floor((pb[k]-region["min_y"])/size) for k in (1,3))
                candidates = {node for x in range(x0-1,x1+2) for y in range(y0-1,y1+2) for node in region["grid"].get((x,y),[])}
                for zn in sorted(candidates):
                    zp = region["cell_polygons"][zn]
                    if not boxes_overlap(pb,bounds(zp)):
                        continue
                    width = _shared_polygon_face_length(pp,zp,builder.containment_tolerance)
                    if width <= 1e-7:
                        continue
                    if builder.zone_pad_evidence_required and not evidence:
                        fail(builder,f"Positive shared pad-zone face has no retained solid/thermal evidence: {profile['id']} / {region['source_id']}")
                        return
                    builder.add_branch(f"{profile['id']}:{region['layer']}:owned-zone:{region['source_id']}:{pn}:{zn}",
                        "pad_zone_attachment",pn,zn,width,builder.thickness[region["layer"]],region["layer"],region["net"],profile["id"],evidence_id=evidence)
                    count += 1
                    length += width
            builder.mesh.branch_admission["owned_copper"]["contacts"].append({
                "pad_id":profile["id"],"zone_id":region["source_id"],"layer":region["layer"],
                "face_count":count,"face_length_mm":length,"face_area_mm2":length*builder.thickness[region["layer"]],
                "pad_metal_area_mm2":profile["metal_area_mm2"],"evidence_id":evidence,
            })
            if evidence and not count:
                fail(builder,f"Retained pad-zone contact has no positive shared face: {profile['id']} / {region['source_id']}")
                return
