# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Unique copper-area capacitance surrogate; no electrostatic qualification."""

from __future__ import annotations

from math import cos, hypot, pi, sin
from typing import Any, Dict, List, Sequence, Tuple
import numpy as np

from .contracts import AnalysisSpec, DesignIR
from .hybrid_mesh import (
    TOPOLOGY_ONLY_BRANCH_KINDS, _pad_boundary_polygon, _pad_has_drill,
    _normalize_filled_zone_polygon, _polygon_is_simple, _pad_local_to_world, _pad_size,
)
from .quasistatic_capacitance import (
    EPSILON_0_F_M, stackup_profile, dielectric_between,
    estimate_line_capacitance_per_m,
)


def _xy(value: Any) -> Tuple[float, float]:
    if isinstance(value, dict):
        return float(value.get("x", 0.0)), float(value.get("y", 0.0))
    return float(value[0]), float(value[1])


def _source_polygon(kind: str, item: Dict[str, Any]) -> list:
    """Admit source geometry, never the rectangles of internal current links."""
    if kind == "zone":
        if (item.get("filled_copper_state") not in (None, "source_filled")
                or item.get("source_fill_provenance_complete") is False):
            raise ValueError("zone is not authoritative filled copper")
        if item.get("holes"):
            raise ValueError("zone holes require a resolved filled polygon")
        if len(item.get("points", item.get("polygon", []))) > 2000:
            raise ValueError("source polygon exceeds 2000 vertices")
        polygon = _normalize_filled_zone_polygon(
            [_xy(point) for point in item.get("points", item.get("polygon", []))]
        )
    elif kind == "pad":
        # These shapes share the mesher's authoritative perimeter convention.
        # Drilled/custom pads need an exact surface-domain adapter;
        # do not silently replace them with their bounding rectangle.
        shape = str(item.get("shape", "rect")).lower()
        if item.get("chamfer"):
            raise ValueError("chamfered pads require an authoritative clipped surface")
        if _pad_has_drill(item) or shape not in {"rect", "circle", "oval", "roundrect"}:
            raise ValueError("unsupported pad surface geometry")
        if shape in {"oval", "roundrect"}:
            width, height = _pad_size(item)
            ratio = item.get("roundrect_rratio", item.get("rratio"))
            if shape == "roundrect" and (ratio is None or not 0 <= float(ratio) <= 0.5):
                raise ValueError("roundrect requires imported radius ratio in [0, 0.5]")
            radius = min(width, height) * (0.5 if shape == "oval" else float(ratio))
            if radius == 0:
                polygon = _pad_boundary_polygon(dict(item, shape="rect"))
            else:
                # 32 chords per quarter circle: exact straight edges, bounded
                # inscribed arc area. Independent of current mesh refinement.
                polygon = []
                for sx, sy, quarter in ((1, 1, 0), (-1, 1, 1), (-1, -1, 2), (1, -1, 3)):
                    cx, cy = sx * (width / 2 - radius), sy * (height / 2 - radius)
                    for i in range(33):
                        angle = (quarter + i / 32) * pi / 2
                        point = _pad_local_to_world(item, cx + radius * cos(angle), cy + radius * sin(angle))
                        if not polygon or hypot(point[0] - polygon[-1][0], point[1] - polygon[-1][1]) > 1e-12:
                            polygon.append(point)
                if hypot(polygon[-1][0] - polygon[0][0], polygon[-1][1] - polygon[0][1]) < 1e-12:
                    polygon.pop()
        else:
            polygon = _pad_boundary_polygon(item, curve_segments=128)
    else:
        if item.get("mid") is not None or str(item.get("type", "")).lower() == "arc":
            raise ValueError("arc tracks need an authoritative curved copper surface")
        start, end = _xy(item["start"]), _xy(item["end"])
        length = hypot(end[0] - start[0], end[1] - start[1])
        width = float(item.get("width", 0))
        if length <= 0 or width <= 0:
            raise ValueError("invalid track geometry")
        nx, ny = -(end[1] - start[1]) * width / (2 * length), (end[0] - start[0]) * width / (2 * length)
        polygon = [(start[0] - nx, start[1] - ny), (end[0] - nx, end[1] - ny),
                   (end[0] + nx, end[1] + ny), (start[0] + nx, start[1] + ny)]
    if len(polygon) < 3 or not all(np.isfinite(v) for point in polygon for v in point):
        raise ValueError("invalid source polygon")
    if not _polygon_is_simple(polygon):
        raise ValueError("non-simple source polygon")
    return polygon


def _complete_dielectric_path(design: DesignIR, layer: str, reference: str) -> bool:
    names = [str(item.get("name", "")) for item in design.stackup]
    low, high = sorted((names.index(layer), names.index(reference)))
    for item in design.stackup[low + 1:high]:
        if str(item.get("name", "")).endswith(".Cu"):
            # An intervening conductor requires a multiconductor model.
            return False
        thickness = float(item.get("thickness") or item.get("thickness_mm") or 0)
        epsilon = float(item.get("epsilon_r", item.get("epsilonR", 0)) or 0)
        if not np.isfinite(thickness) or not np.isfinite(epsilon) or thickness <= 0 or epsilon < 1:
            return False
    return high > low + 1


def _partition_area(polygons: Sequence[list], source_count: int,
                    reference_labels: Sequence[str]) -> dict[tuple[int, str], float]:
    """Exact polygonal union allocation by a bounded vertical-strip sweep.

    Edges are linear. Their order can change only at a vertex or an edge
    intersection. Between those X cuts every selected vertical interval is
    linear, so its midpoint height times strip width integrates area exactly.
    Earlier sources own overlap; reference polygons are ordered nearest first.
    Coordinates/areas are mm/mm^2. No mesh length or width enters this integral.
    """
    edges = []
    cuts = set()
    for owner, polygon in enumerate(polygons):
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            cuts.update((a[0], b[0]))
            if a[0] != b[0]:
                left, right = (a, b) if a[0] < b[0] else (b, a)
                edges.append((left, right, owner))
    if len(edges) > 2000:
        raise ValueError("capacitance polygon sweep exceeds 2000 nonvertical edges")
    for i, (a, b, _) in enumerate(edges):
        slope = (b[1] - a[1]) / (b[0] - a[0])
        for c, d, _ in edges[:i]:
            low, high = max(a[0], c[0]), min(b[0], d[0])
            if high <= low:
                continue
            other = (d[1] - c[1]) / (d[0] - c[0])
            if slope == other:
                continue
            # Compute relative to the overlap start to avoid large-origin cancellation.
            delta = (c[1] + other * (low - c[0])) - (a[1] + slope * (low - a[0]))
            x = low + delta / (slope - other)
            if low < x < high:
                cuts.add(x)
    if len(cuts) * len(edges) > 4_000_000:
        raise ValueError("capacitance polygon sweep exceeds 4000000 edge-strip checks")
    areas: dict[tuple[int, str], float] = {}
    xs = sorted(cuts)
    for left, right in zip(xs, xs[1:]):
        x = left + (right - left) / 2
        crossings = sorted((a[1] + (b[1] - a[1]) * ((x - a[0]) / (b[0] - a[0])), owner)
                           for a, b, owner in edges if a[0] < x < b[0])
        active: set[int] = set()
        for i, (y, owner) in enumerate(crossings[:-1]):
            if owner in active:
                active.remove(owner)
            else:
                active.add(owner)
            height = crossings[i + 1][0] - y
            sources = [value for value in active if value < source_count]
            refs = [value for value in active if value >= source_count]
            if height <= 0 or not sources or (reference_labels and not refs):
                continue
            reference = reference_labels[min(refs) - source_count] if reference_labels else ""
            key = (min(sources), reference)
            areas[key] = areas.get(key, 0.0) + (right - left) * height
    return areas


def estimate_branch_capacitance(
    design: DesignIR,
    spec: AnalysisSpec,
    branches: Sequence[Any],
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """Allocate a unique-source-area surrogate to physical current branches.

    C_total depends on source copper, not internal link count. Distribution is
    length weighted within each owner; it is an unqualified nodal surrogate.
    """
    capacitance = np.zeros(len(branches), dtype=float)
    loss_tangent = np.zeros(len(branches), dtype=float)
    branch_references = [""] * len(branches)
    copper_centers, dielectrics = stackup_profile(design)
    return_mode = str(spec.return_path.get("mode", "implicit"))
    return_net = str(spec.return_path.get("net", "")) if return_mode in {"explicit", "isolated_secondary"} else ""
    info: Dict[str, Any] = {
        "contract": "spike/distributed-capacitance/v1",
        "model": "unique_copper_area_single_reference",
        "status": "unsupported", "total_capacitance_f": 0.0,
        "reference_mode": "explicit_return_conductor" if return_net else "implicit_nearest_copper",
        "reference_net": return_net, "reference_layers": [],
        "branch_reference_layers": branch_references,
        "estimated_branch_count": 0, "skipped_via_branch_count": 0,
        "skipped_topology_branch_count": 0, "skipped_geometry_branch_count": 0,
        "skipped_reference_branch_count": 0, "skipped_reference_geometry_branch_count": 0,
        "skipped_overlap_branch_count": 0, "skipped_return_conductor_branch_count": 0,
        "unique_estimated_area_mm2": 0.0, "area_by_owner": [], "geometry_failures": [],
        "unrepresented_source_ids": [],
        "validity": [
            "approximate single-reference surrogate, not an electrostatic qualification",
            "pads/zones: epsilon_0*A/sum(d_i/epsilon_i); no fringing correction",
            "tracks: zero-thickness microstrip density times unique uncovered rectangular area",
            "source geometry allocation is independent of current-branch tessellation",
            "length-weighted nodal distribution is not an electrostatic charge solution",
            "explicit return requires projected copper overlap; implicit mode assumes a full plane",
            "no via/antipad, drilled/custom pad, arc-track, or multiconductor capacitance",
            "circle/oval/roundrect perimeters use 128 fixed arc chords; no track end-cap area",
        ],
    }
    def finish(reason: str = ""):
        total = float(np.sum(capacitance))
        estimated = int(np.count_nonzero(capacitance))
        info.update(total_capacitance_f=total, estimated_branch_count=estimated,
                    status="approximate" if estimated else "unsupported",
                    branch_coverage=estimated / max(len(branches), 1),
                    effective_loss_tangent=float(np.dot(capacitance, loss_tangent) / total) if total else 0.0,
                    skipped_branch_count=len(branches) - estimated,
                    reference_layers=sorted({v for v in branch_references if v}))
        info["complete_source_coverage"] = bool(estimated) and not (info["geometry_failures"] or info["unrepresented_source_ids"]
            or info["skipped_reference_branch_count"] or info["skipped_geometry_branch_count"]
            or info["skipped_via_branch_count"])
        if reason:
            info["reason"] = reason
        return capacitance, loss_tangent, info

    if str(spec.options.get("capacitance_model", "auto")).lower() == "none" or spec.options.get("include_dielectric") is False:
        info["model"] = "none"
        return finish("Capacitance extraction was disabled by the analysis request.")
    if len(copper_centers) < 2 or not dielectrics:
        return finish("At least two copper layers and dielectric epsilon/thickness are required.")
    if return_mode in {"explicit", "isolated_secondary"} and not return_net:
        return finish("Explicit reference mode requires a return net.")

    inventory = {}
    references: dict[str, list] = {}
    for kind, collection in (("zone", design.zones), ("pad", design.pads), ("track", design.tracks)):
        for index, item in enumerate(collection):
            owner = str(item.get("id") or (item.get("component_pad") if kind == "pad" else "") or f"{kind}-{index + 1}")
            inventory[(kind, owner)] = item
            if return_net and str(item.get("net_name") or item.get("net") or "") == return_net:
                try:
                    polygon = _source_polygon(kind, item)
                except (ValueError, KeyError, TypeError) as error:
                    info["geometry_failures"].append({"source_id": owner, "reason": str(error)})
                    continue
                layers = list(item.get("layers", [])) or [item.get("layer", "")]
                if "*.Cu" in layers:
                    layers = list(copper_centers)
                for layer in layers:
                    if layer in copper_centers:
                        references.setdefault(layer, []).append(polygon)

    groups: dict[tuple[str, str], dict] = {}
    for index, branch in enumerate(branches):
        kind = str(branch.kind)
        if kind in TOPOLOGY_ONLY_BRANCH_KINDS:
            info["skipped_topology_branch_count"] += 1
        elif "via" in kind or "barrel" in kind:
            info["skipped_via_branch_count"] += 1
        elif return_net and str(branch.net) == return_net:
            info["skipped_return_conductor_branch_count"] += 1
        elif kind not in {"track", "pad", "zone"} or not np.isfinite(branch.length_mm) or branch.length_mm <= 0:
            info["skipped_geometry_branch_count"] += 1
        else:
            groups.setdefault((str(branch.net), str(branch.layer)), {}).setdefault(
                (kind, str(branch.source_id)), []).append(index)

    loss_known = 0
    for (net, layer), owners in groups.items():
        for key, item in inventory.items():
            layers = list(item.get("layers", [])) or [item.get("layer", "")]
            if (key not in owners and (layer in layers or "*.Cu" in layers)
                    and str(item.get("net_name") or item.get("net") or "") == net):
                info["unrepresented_source_ids"].append({"source_id": key[1], "kind": key[0], "layer": layer})
        source_keys, source_polygons, source_branches = [], [], []
        for key in sorted(owners, key=lambda key: ({"zone": 0, "pad": 1, "track": 2}[key[0]], key[1])):
            try:
                item = inventory[key]
                if str(item.get("net_name") or item.get("net") or "") != net:
                    raise ValueError("source net differs from branch net")
                layers = list(item.get("layers", [])) or [item.get("layer", "")]
                if layer not in layers and "*.Cu" not in layers:
                    raise ValueError("source layer differs from branch layer")
                polygon = _source_polygon(key[0], item)
            except (ValueError, KeyError, TypeError) as error:
                info["skipped_geometry_branch_count"] += len(owners[key])
                info["geometry_failures"].append({"source_id": key[1], "reason": str(error)})
                continue
            source_keys.append(key)
            source_polygons.append(polygon)
            source_branches.append(owners[key])
        count = len(source_keys)
        if not count:
            continue
        candidates = sorted((name for name in copper_centers if name != layer),
                            key=lambda name: (abs(copper_centers[name] - copper_centers.get(layer, 0)), name))
        if layer not in copper_centers or not candidates:
            info["skipped_reference_branch_count"] += sum(map(len, source_branches))
            continue
        ref_polygons, ref_labels = [], []
        if return_net:
            for name in candidates:
                for polygon in references.get(name, []):
                    ref_polygons.append(polygon)
                    ref_labels.append(name)
            if not ref_labels:
                skipped = sum(map(len, source_branches))
                info["skipped_reference_branch_count"] += skipped
                info["skipped_reference_geometry_branch_count"] += skipped
                continue
        try:
            areas = _partition_area(source_polygons + ref_polygons, count, ref_labels)
        except ValueError as error:
            info["skipped_geometry_branch_count"] += sum(map(len, source_branches))
            info["geometry_failures"].append({"net": net, "layer": layer, "reason": str(error)})
            continue
        for source, key in enumerate(source_keys):
            selected = [(ref or candidates[0], area) for (owner, ref), area in areas.items() if owner == source]
            indices = source_branches[source]
            if not selected:
                category = "skipped_reference_branch_count" if return_net else "skipped_overlap_branch_count"
                info[category] += len(indices)
                if return_net:
                    info["skipped_reference_geometry_branch_count"] += len(indices)
                continue
            # One branch shunt can carry only one reference in the v1 contract.
            # Multiple overlapping reference layers require a capacitance matrix.
            if len({ref for ref, _ in selected}) != 1:
                info["skipped_reference_branch_count"] += len(indices)
                info["geometry_failures"].append({"source_id": key[1], "reason": "surface requires multiple reference layers"})
                continue
            reference, area = selected[0]
            if not _complete_dielectric_path(design, layer, reference):
                info["skipped_reference_branch_count"] += len(indices)
                info["geometry_failures"].append({"source_id": key[1], "reason": "incomplete dielectric or intervening copper layer"})
                continue
            dielectric = dielectric_between(copper_centers[layer], copper_centers[reference], dielectrics)
            if dielectric is None:
                info["skipped_reference_branch_count"] += len(indices)
                continue
            epsilon_r, height, tan_delta = dielectric
            if key[0] == "track":
                width = float(inventory[key]["width"])
                value = estimate_line_capacitance_per_m(width, height, epsilon_r) * area / width * 1e-3
            else:
                low, high = sorted((copper_centers[layer], copper_centers[reference]))
                electrical_height = sum(max(0.0, min(high, top) - max(low, bottom)) / epsilon
                                        for bottom, top, epsilon, _ in dielectrics)
                value = EPSILON_0_F_M * area * 1e-3 / electrical_height
                paths = [(max(0.0, min(high, top) - max(low, bottom)) / epsilon, loss)
                         for bottom, top, epsilon, loss in dielectrics
                         if min(high, top) > max(low, bottom)]
                tan_delta = (sum(weight * loss for weight, loss in paths) / electrical_height
                             if all(loss is not None for _, loss in paths) else None)
            if not np.isfinite(value) or value <= 0:
                info["skipped_geometry_branch_count"] += len(indices)
                continue
            weights = np.array([branches[i].length_mm for i in indices], dtype=float)
            weights /= weights.sum()
            for i, weight in zip(indices, weights):
                capacitance[i] = value * weight
                branch_references[i] = reference
                if tan_delta is not None:
                    loss_tangent[i] = tan_delta
                    loss_known += 1
            info["unique_estimated_area_mm2"] += area
            info["area_by_owner"].append({"source_id": key[1], "kind": key[0], "layer": layer,
                                         "reference_layer": reference, "area_mm2": area, "capacitance_f": value})
    info["loss_tangent_branch_coverage"] = loss_known / max(int(np.count_nonzero(capacitance)), 1)
    return finish()
