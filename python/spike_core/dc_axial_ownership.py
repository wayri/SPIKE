# SPDX-License-Identifier: Apache-2.0
"""Explicit annular gap ownership; not a solved 3-D conductor or board adapter.

One coaxial stack, supplied finite annular face contacts, and exactly one
segment per adjacent slab gap. Land prisms own their whole thickness. Axial
segments own only the open gaps between slab faces. Clipping changes resistance;
make_gap_branches creates fresh branches for a new solve, never mutates a mesh.
Independent derivation and reviewed primary laws: docs/DC_AXIAL_OWNERSHIP.md.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

from .hybrid_mesh import MeshBranch

REQUEST = "spike/dc-axial-ownership-request/v1"
RESULT = "spike/dc-axial-ownership-result/v1"
_MIN_LENGTH = 1e-9
_MAX_LENGTH = 1e6
_MAX_LANDS = 256
_MAX_BYTES = 1024 * 1024


class AxialOwnershipError(ValueError):
    """Unsupported, inconsistent, or unrepresentable supplied ownership."""


def _require(condition, message):
    if not condition:
        raise AxialOwnershipError(message)


def _record(value, keys, name):
    _require(type(value) is dict and set(value) == set(keys.split()),
             name + " requires exactly the declared fields")


def _number(value, name, low=-_MAX_LENGTH, high=_MAX_LENGTH):
    _require(type(value) in (int, float) and low <= value <= high
             and math.isfinite(value), name + " outside finite supported range")
    return float(value)


def _name(value):
    _require(type(value) is str and bool(value.strip()) and len(value) <= 80,
             "IDs, layer, and net must be nonempty strings of at most 80 characters")
    return value


def _positive(value, name):
    _require(math.isfinite(value) and value > 0, name + " overflowed or underflowed")
    return value


def _area(inner, outer):
    _require(outer - inner >= _MIN_LENGTH, "Annular thickness below supported minimum")
    return _positive(math.pi * (outer - inner) * (outer + inner), "Annular area")


def _contact(contact, land, inner, outer, ids):
    _record(contact, "id land_id node inner_radius_mm outer_radius_mm", "Annular face contact")
    name = _name(contact["id"])
    _require(name not in ids, "Duplicate face contact ID")
    ids.add(name)
    _require(type(contact["node"]) is int and contact["node"] == land["node"]
             and contact["land_id"] == land["id"], "Contact land/node incidence differs")
    _require(_number(contact["inner_radius_mm"], "Contact inner radius", _MIN_LENGTH) == inner
             and _number(contact["outer_radius_mm"], "Contact outer radius", _MIN_LENGTH) == outer,
             "Contact must preserve the supplied barrel annulus exactly")


def compile_axial_ownership(request):
    """Audit explicit support and evaluate imposed uniform axial currents.

    Input current_a is signed from source_land to target_land; it is not
    certified as a solution of the coupled land/barrel problem. All lengths
    are mm, conductivity S/m, current A, density A/mm2, volume mm3, loss W.
    Every output has complete_physical_volume=False: transition fields remain
    unresolved, even when the declared geometry has disjoint volume ownership.
    """
    _record(request, "contract center_xy_mm net bore_radius_mm lands segments", "Axial ownership")
    _require(request["contract"] == REQUEST, "Unsupported axial ownership contract")
    center = request["center_xy_mm"]
    _require(type(center) is list and len(center) == 2, "Supply one coaxial XY center")
    x, y = (_number(v, "Center coordinate") for v in center)
    net = _name(request["net"])
    inner = _number(request["bore_radius_mm"], "Bore radius", _MIN_LENGTH)
    supplied_lands, segments = request["lands"], request["segments"]
    _require(type(supplied_lands) is list and 2 <= len(supplied_lands) <= _MAX_LANDS,
             "Supply 2..256 explicit land slabs")
    _require(type(segments) is list and len(segments) == len(supplied_lands) - 1,
             "Supply exactly one barrel segment for every adjacent land gap")
    lands, layer_ids, node_ids = {}, set(), set()
    for land in supplied_lands:
        _record(land, "id layer node z_min_mm z_max_mm outer_radius_mm conductivity_s_m", "Land prism")
        name, layer = _name(land["id"]), _name(land["layer"])
        node = land["node"]
        _require(name not in lands and layer not in layer_ids and type(node) is int
                 and 0 <= node < 2**31 and node not in node_ids, "Duplicate/invalid land, layer, or node identity")
        z0, z1 = (_number(land[k], "Slab face") for k in ("z_min_mm", "z_max_mm"))
        _require(z1 - z0 >= _MIN_LENGTH, "Land slab is reversed or too thin")
        outer = _number(land["outer_radius_mm"], "Land radius", _MIN_LENGTH)
        _number(land["conductivity_s_m"], "Land conductivity", 1e-12, 1e12)
        volume = _positive(_area(inner, outer) * (z1 - z0), "Land volume")
        lands[name] = {**deepcopy(land), "volume_mm3": volume,
                       "center_z_mm": (z0 + z1) / 2, "net_current_to_barrels_a": 0.}
        layer_ids.add(layer); node_ids.add(node)
    ordered = sorted(lands.values(), key=lambda land: land["z_min_mm"])
    adjacent = set()
    for low, high in zip(ordered, ordered[1:]):
        _require(high["z_min_mm"] - low["z_max_mm"] >= _MIN_LENGTH,
                 "Land prisms overlap, touch, or leave an unrepresentable gap")
        adjacent.add(frozenset((low["id"], high["id"])))
    ids, contact_ids, seen, rows, incidence = set(), set(), set(), [], {k: [] for k in lands}
    for segment in segments:
        _record(segment, "id kind source_land target_land start_z_mm end_z_mm outer_radius_mm conductivity_s_m current_a source_contact target_contact", "Barrel segment")
        name = _name(segment["id"])
        _require(name not in ids and segment["kind"] in ("via", "pad_barrel"), "Duplicate segment or unsupported kind")
        ids.add(name)
        source_id, target_id = _name(segment["source_land"]), _name(segment["target_land"])
        _require(source_id in lands and target_id in lands and source_id != target_id,
                 "Barrel endpoint land is missing or identical")
        pair = frozenset((source_id, target_id))
        _require(pair in adjacent and pair not in seen,
                 "Barrel skips a land, duplicates/overlaps a gap, or leaves a gap unassigned")
        seen.add(pair)
        source, target = lands[source_id], lands[target_id]
        z0, z1 = (_number(segment[k], "Supplied barrel endpoint") for k in ("start_z_mm", "end_z_mm"))
        _require(z0 == source["center_z_mm"] and z1 == target["center_z_mm"],
                 "Supplied span must reach both exact land midplanes; gaps/overhangs are unsupported")
        outer = _number(segment["outer_radius_mm"], "Barrel radius", _MIN_LENGTH)
        area = _area(inner, outer)
        _require(outer <= min(source["outer_radius_mm"], target["outer_radius_mm"]),
                 "Barrel face extends beyond its supplied land support")
        sigma = _number(segment["conductivity_s_m"], "Barrel conductivity", 1e-12, 1e12)
        current = _number(segment["current_a"], "Imposed signed current", -1e12, 1e12)
        _contact(segment["source_contact"], source, inner, outer, contact_ids)
        _contact(segment["target_contact"], target, inner, outer, contact_ids)
        direction = 1 if z1 > z0 else -1
        start = source["z_max_mm"] if direction == 1 else source["z_min_mm"]
        end = target["z_min_mm"] if direction == 1 else target["z_max_mm"]
        length, original_length = abs(end - start), abs(z1 - z0)
        _require(original_length > length > 0, "Clipped interval or removed land overlap is unrepresentable")
        volume = _positive(area * length, "Axial volume")
        resistance = _positive(1000. * length / sigma / area, "Gap resistance")
        original_r = _positive(1000. * original_length / sigma / area, "Original span resistance")
        density = direction * current / area
        heat = (current * resistance) * current
        _require(math.isfinite(density) and math.isfinite(heat)
                 and (current == 0 or (density != 0 and heat > 0)), "Axial field or heat overflowed/underflowed")
        incidence[source_id].append(current); incidence[target_id].append(-current)
        rows.append({"id": name, "kind": segment["kind"], "source_land": source_id,
            "target_land": target_id, "node_p": source["node"], "node_n": target["node"],
            "layer": source["layer"] + "->" + target["layer"], "net": net,
            "start_mm": [x, y, start], "end_mm": [x, y, end],
            "inner_radius_mm": inner, "outer_radius_mm": outer, "conductivity_s_m": sigma,
            "face_contact_area_mm2": area, "source_contact": deepcopy(segment["source_contact"]),
            "target_contact": deepcopy(segment["target_contact"]), "length_mm": length,
            "original_center_span_mm": original_length, "removed_land_span_mm": original_length - length,
            "original_center_span_resistance_ohm": original_r, "gap_resistance_ohm": resistance,
            "resistance_change_ohm": resistance - original_r, "volume_mm3": volume,
            "imposed_current_a": current, "current_density_a_mm2": [0., 0., density],
            "imposed_current_joule_heat_w": heat, "requires_resolve": True})
    _require(seen == adjacent, "Unassigned barrel gap")
    for name, land in lands.items():
        land["net_current_to_barrels_a"] = math.fsum(incidence[name])
    rows.sort(key=lambda row: row["id"])
    try:
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as error:
        raise AxialOwnershipError("Request must be finite JSON") from error
    _require(len(encoded) <= _MAX_BYTES, "Axial ownership request exceeds 1 MiB")
    return {"contract": RESULT, "model_status": "experimental", "production_qualified": False,
        "input_digest": hashlib.sha256(encoded).hexdigest(), "source_request": deepcopy(request),
        "geometry_ownership": "disjoint_explicit_coaxial_land_prisms_and_gap_annuli",
        "complete_physical_volume": False, "requires_resolve": True,
        "current_status": "supplied_imposed_values_not_a_coupled_solution",
        "land_transition_fields_status": "unresolved", "land_transition_heat_w": None,
        "lands": ordered, "segments": rows,
        "land_volume_mm3": math.fsum(land["volume_mm3"] for land in ordered),
        "axial_gap_volume_mm3": math.fsum(row["volume_mm3"] for row in rows),
        "axial_imposed_current_heat_w": math.fsum(row["imposed_current_joule_heat_w"] for row in rows),
        "limitations": ["One explicitly supplied coaxial stack; no source/board/electrode inference.",
            "Uniform axial DC current in each gap only; land spreading and through-thickness transition fields remain unresolved.",
            "Clipped gap resistance requires a fresh coupled solve; supplied currents do not establish KCL/work for land fields.",
            "No complete-volume density percentile, planar-field merge, thermal mapping, AC or board qualification."]}


def make_gap_branches(request):
    """Create independent MeshBranch objects for a fresh, explicitly wired solve.

    Node IDs retain supplied contact incidence; positions are the physical slab
    faces, not a mutation of the existing layer-center node coordinates. The
    caller must supply matching finite annular contacts before a new solve.
    """
    report = compile_axial_ownership(request)
    return [MeshBranch(id=row["id"], kind=row["kind"], node_p=row["node_p"], node_n=row["node_n"],
        start_mm=tuple(row["start_mm"]), end_mm=tuple(row["end_mm"]),
        width_mm=math.pi * (row["outer_radius_mm"] + row["inner_radius_mm"]),
        thickness_mm=row["outer_radius_mm"] - row["inner_radius_mm"],
        conductivity_s_m=row["conductivity_s_m"], layer=row["layer"], net=row["net"],
        source_id=row["id"], evidence_id=report["input_digest"]) for row in report["segments"]]
