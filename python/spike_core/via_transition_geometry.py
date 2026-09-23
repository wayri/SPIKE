"""Fail-closed circular via-transition geometry shared by PI and SI admission."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Iterable, Mapping, Sequence

from .design_ir_v2 import DesignIRV2


CONTRACT = "spike/pcb-via-transition-geometry/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0003"
MAX_ANTIPADS = 64
MAX_REFINEMENT_LEVELS = 8
MAX_REFERENCE_ZONE_POINTS = 4096
SUPPORTED_VIA_TYPES = {"through", "blind", "buried", "microvia"}


class ViaTransitionGeometryError(ValueError):
    """Raised before unsupported or ambiguous via geometry reaches a mesh."""

    code = ERROR_CODE


@dataclass(frozen=True)
class AntipadSpec:
    layer_id: str
    diameter_mm: float
    reference_net_id: str
    reference_zone_id: str
    reference_patch_outer_diameter_mm: float
    source_id: str

    def __post_init__(self) -> None:
        if not self.layer_id or not self.reference_net_id or not self.reference_zone_id or not self.source_id:
            raise ViaTransitionGeometryError("Antipads require canonical layer/net/zone and source identities.")
        values = (self.diameter_mm, self.reference_patch_outer_diameter_mm)
        if any(isinstance(value, bool) or not math.isfinite(float(value)) or value <= 0 for value in values):
            raise ViaTransitionGeometryError("Antipad and reference-patch diameters must be finite and positive.")
        object.__setattr__(self, "diameter_mm", float(self.diameter_mm))
        object.__setattr__(self, "reference_patch_outer_diameter_mm", float(self.reference_patch_outer_diameter_mm))


def _source_contained_reference_patch(
    design: DesignIRV2, via: Any, antipad: AntipadSpec,
) -> None:
    """Admit a local circular patch only when a convex source zone contains it."""
    matches = [item for item in design.zones if item.id == antipad.reference_zone_id]
    if len(matches) != 1:
        raise ViaTransitionGeometryError("Antipad reference_zone_id must resolve exactly once.")
    zone = matches[0]
    if zone.net_id != antipad.reference_net_id or antipad.layer_id not in zone.layer_ids:
        raise ViaTransitionGeometryError("Antipad reference zone must own the declared reference net and layer.")
    if zone.boundary_rings or zone.holes_mm or len(zone.outlines_mm) != 1:
        raise ViaTransitionGeometryError("Via-transition v1 requires one hole-free straight-edged reference-zone outline.")
    points = list(zone.outlines_mm[0])
    if not 3 <= len(points) <= MAX_REFERENCE_ZONE_POINTS:
        raise ViaTransitionGeometryError("Reference-zone outline is outside the bounded point budget.")
    signs: list[bool] = []
    center_x, center_y = via.center_mm
    radius = antipad.reference_patch_outer_diameter_mm / 2.0
    for index, current in enumerate(points):
        following = points[(index + 1) % len(points)]
        after = points[(index + 2) % len(points)]
        edge_x, edge_y = following[0] - current[0], following[1] - current[1]
        length = math.hypot(edge_x, edge_y)
        if length <= 1e-12:
            raise ViaTransitionGeometryError("Reference-zone outline contains a zero-length edge.")
        turn = edge_x * (after[1] - following[1]) - edge_y * (after[0] - following[0])
        if abs(turn) > 1e-12:
            signs.append(turn > 0)
        signed = edge_x * (center_y - current[1]) - edge_y * (center_x - current[0])
        if abs(signed) / length < radius - 1e-12:
            raise ViaTransitionGeometryError("Reference patch is not fully contained by its source zone.")
        signs.append(signed > 0)
    if not signs or any(value != signs[0] for value in signs):
        raise ViaTransitionGeometryError("Reference-zone outline must be convex and contain the local patch.")


def _copper_layers(design: DesignIRV2) -> list[Any]:
    layers = sorted((item for item in design.layers if item.layer_type == "copper"), key=lambda item: item.order)
    if len(layers) < 2 or len({item.id for item in layers}) != len(layers) or len({item.order for item in layers}) != len(layers):
        raise ViaTransitionGeometryError("Via transitions require uniquely ordered canonical copper layers.")
    previous_end: float | None = None
    for layer in layers:
        if (isinstance(layer.z_mm, bool) or not math.isfinite(float(layer.z_mm))
                or layer.thickness_mm is None or not math.isfinite(float(layer.thickness_mm))
                or layer.thickness_mm <= 0):
            raise ViaTransitionGeometryError("Via transitions require finite positive copper-layer thickness and position.")
        if previous_end is not None and float(layer.z_mm) < previous_end - 1e-12:
            raise ViaTransitionGeometryError("Canonical copper layers must be physically ordered and non-overlapping.")
        previous_end = float(layer.z_mm + layer.thickness_mm)
    return layers


def _span(design: DesignIRV2, via: Any) -> tuple[list[Any], int, int]:
    layers = _copper_layers(design)
    indexes = {item.id: index for index, item in enumerate(layers)}
    if via.start_layer_id not in indexes or via.end_layer_id not in indexes:
        raise ViaTransitionGeometryError("Via span endpoints must reference canonical copper layers.")
    source_start, source_end = indexes[via.start_layer_id], indexes[via.end_layer_id]
    if source_start == source_end:
        raise ViaTransitionGeometryError("Via span endpoints must be distinct.")
    start, end = sorted((source_start, source_end))
    last = len(layers) - 1
    outer_endpoints = sum(index in {0, last} for index in (source_start, source_end))
    valid = {
        "through": {source_start, source_end} == {0, last},
        "blind": outer_endpoints == 1,
        "buried": outer_endpoints == 0,
        "microvia": end == start + 1,
    }
    if via.via_type not in SUPPORTED_VIA_TYPES or not valid.get(via.via_type, False):
        raise ViaTransitionGeometryError(f"Via type {via.via_type!r} is incompatible with its canonical layer span.")
    return layers[start:end + 1], start, end


def _land_records(via: Any, span_layers: Sequence[Any], minimum_outer_diameter_mm: float) -> list[Dict[str, Any]]:
    layer_ids = [item.id for item in span_layers]
    profiles = list(via.land_profiles)
    if profiles and [item.layer_id for item in profiles] != layer_ids:
        raise ViaTransitionGeometryError("Explicit via land profiles must cover every copper layer in the admitted span.")
    if profiles:
        for item in profiles:
            if item.shape != "circle" or item.offset_mm != (0.0, 0.0):
                raise ViaTransitionGeometryError("Via-transition v1 admits only centered circular land profiles.")
        diameters = [(item.layer_id, float(item.size_mm[0]), item.source_primitive_id) for item in profiles]
    else:
        diameters = [(item.id, float(via.diameter_mm), via.source_id or via.id) for item in span_layers]
    result = []
    for layer_id, diameter, source_id in diameters:
        if not math.isfinite(diameter) or diameter < minimum_outer_diameter_mm:
            raise ViaTransitionGeometryError("Every via land must contain the plated barrel outer diameter.")
        result.append({"layer_id": layer_id, "outer_diameter_mm": diameter,
                       "inner_diameter_mm": float(via.drill_mm), "source_profile_id": source_id})
    return result


def _refinement(values: Iterable[float]) -> list[float]:
    raw = list(values)
    if any(isinstance(item, bool) for item in raw):
        raise ViaTransitionGeometryError("Local refinement sizes must be finite, positive, strictly decreasing, and bounded.")
    result = [float(item) for item in raw]
    if (not 1 <= len(result) <= MAX_REFINEMENT_LEVELS
            or any(not math.isfinite(item) or item <= 0 for item in result)
            or any(result[index] <= result[index + 1] for index in range(len(result) - 1))):
        raise ViaTransitionGeometryError("Local refinement sizes must be finite, positive, strictly decreasing, and bounded.")
    return result


def build_via_transition_geometry(
    design: DesignIRV2, *, via_id: str, antipads: Sequence[AntipadSpec | Mapping[str, Any]],
    refinement_sizes_mm: Sequence[float] = (0.2, 0.1, 0.05),
) -> Dict[str, Any]:
    """Build exact analytic circular facts; no capacitance or SI result is inferred."""
    matches = [item for item in design.vias if item.id == via_id]
    if len(matches) != 1:
        raise ViaTransitionGeometryError("Via transition requires one exact canonical via identity.")
    via = matches[0]
    if not via.net_id or via.net_id not in {item.id for item in design.nets} or not via.source_id:
        raise ViaTransitionGeometryError("Via transition requires a canonical signal-net identity.")
    if len(via.center_mm) != 2 or not all(math.isfinite(float(value)) for value in via.center_mm):
        raise ViaTransitionGeometryError("Via transition requires a finite two-dimensional center.")
    if (not math.isfinite(float(via.diameter_mm)) or not math.isfinite(float(via.drill_mm))
            or via.drill_mm <= 0 or via.diameter_mm <= via.drill_mm or via.plating_mm is None
            or not math.isfinite(float(via.plating_mm)) or via.plating_mm <= 0):
        raise ViaTransitionGeometryError("Via transition requires finite drill, land, and explicit positive plating dimensions.")
    outer_barrel_radius = via.drill_mm / 2.0 + via.plating_mm
    if outer_barrel_radius * 2.0 > via.diameter_mm:
        raise ViaTransitionGeometryError("Via plating cannot extend outside the declared land diameter.")
    span_layers, start_index, end_index = _span(design, via)
    lands = _land_records(via, span_layers, outer_barrel_radius * 2.0)
    antipad_items = [item if isinstance(item, AntipadSpec) else AntipadSpec(**dict(item)) for item in antipads]
    if not 1 <= len(antipad_items) <= MAX_ANTIPADS or len({item.layer_id for item in antipad_items}) != len(antipad_items):
        raise ViaTransitionGeometryError("Via transition requires a bounded, unique explicit antipad set.")
    nets = {item.id for item in design.nets}
    land_by_layer = {item["layer_id"]: item for item in lands}
    layer_by_id = {item.id: item for item in span_layers}
    antipad_records = []
    for item in sorted(antipad_items, key=lambda value: layer_by_id.get(value.layer_id, span_layers[0]).order):
        land = land_by_layer.get(item.layer_id)
        if (land is None or item.reference_net_id not in nets or item.reference_net_id == via.net_id
                or item.diameter_mm <= land["outer_diameter_mm"]
                or item.reference_patch_outer_diameter_mm <= item.diameter_mm):
            raise ViaTransitionGeometryError("Antipads must be explicit larger voids on an admitted reference-net layer.")
        _source_contained_reference_patch(design, via, item)
        antipad_records.append({"layer_id": item.layer_id, "diameter_mm": item.diameter_mm,
                                "reference_net_id": item.reference_net_id,
                                "reference_zone_id": item.reference_zone_id,
                                "reference_patch_outer_diameter_mm": item.reference_patch_outer_diameter_mm,
                                "source_id": item.source_id,
                                "clearance_mm": (item.diameter_mm - land["outer_diameter_mm"]) / 2.0})
    interfaces = [{"layer_id": item.id, "z_mm": float(item.z_mm + item.thickness_mm / 2.0),
                   "inner_radius_mm": float(via.drill_mm / 2.0), "outer_radius_mm": float(outer_barrel_radius)}
                  for item in span_layers]
    barrel_segments = [{"id": f"{via.id}:barrel:{index}", "from_layer_id": left["layer_id"],
                        "to_layer_id": right["layer_id"], "z_min_mm": left["z_mm"], "z_max_mm": right["z_mm"],
                        "inner_radius_mm": left["inner_radius_mm"], "outer_radius_mm": left["outer_radius_mm"],
                        "source_via_id": via.id, "net_id": via.net_id}
                       for index, (left, right) in enumerate(zip(interfaces, interfaces[1:]), 1)]
    land_volumes = [{"id": f"{via.id}:land:{item['layer_id']}", **item,
                     "z_min_mm": float(layer_by_id[item["layer_id"]].z_mm),
                     "z_max_mm": float(layer_by_id[item["layer_id"]].z_mm + layer_by_id[item["layer_id"]].thickness_mm),
                     "source_via_id": via.id, "net_id": via.net_id} for item in lands]
    refinement = _refinement(refinement_sizes_mm)
    return {
        "contract": CONTRACT, "design_id": design.design_id, "via_id": via.id, "source_via_id": via.source_id,
        "net_id": via.net_id, "via_type": via.via_type,
        "span": {"start_layer_id": span_layers[0].id, "end_layer_id": span_layers[-1].id,
                 "start_copper_index": start_index, "end_copper_index": end_index,
                 "ordered_layer_ids": [item.id for item in span_layers]},
        "center_mm": list(via.center_mm), "drill_diameter_mm": float(via.drill_mm),
        "plating_mm": float(via.plating_mm), "interfaces": interfaces, "barrel_segments": barrel_segments,
        "lands": land_volumes, "antipads": antipad_records, "refinement_sizes_mm": refinement,
        "topology_audit": {"analytic_csg_profile_validated": True, "duplicate_analytic_surface_ids": 0,
                           "discrete_watertightness_checked": False,
                           "explicit_reference_plane_voids": len(antipad_records)},
        "qualification": {"geometry_state": "admitted_exact_circular", "refinement_state": "refinement_not_convergence_proof",
                          "native_handoff_ready": False, "capacitance_ready": False,
                          "si_ready": False, "solver_ready": False},
    }
