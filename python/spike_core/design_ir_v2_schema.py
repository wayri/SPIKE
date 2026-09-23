"""Canonical DesignIR v2 schema types and identity utilities.

These definitions are intentionally separate from the v1 migration adapter so
new consumers can depend on the typed schema without importing migration code.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .design_ir_land_profiles import (
    LandProfile, hydrate_land_profiles, land_profiles_from_v1,
    project_land_profiles_to_v1, validate_land_profiles,
)
from .design_ir_thermal_connections import validate_component_policy, validate_pad_policy, validate_zone_policy
from .design_ir_zone_boundaries import ZoneBoundaryRing, ZoneBoundarySegment


DESIGN_IR_V2_CONTRACT = "spike/design-ir/v2"
ASSEMBLY_IR_V1_CONTRACT = "spike/assembly-ir/v1"
_SPIKE_OBJECT_NAMESPACE = uuid.UUID("b5d2350a-5d97-4d14-a47d-bdd779d33ce9")


def canonical_uuid(source_format: str, source_digest: str, object_kind: str, source_id: str) -> str:
    """Return a stable UUID for one source-native object identity."""

    identity = "\x1f".join((source_format.strip().lower(), source_digest.lower(), object_kind, str(source_id)))
    return str(uuid.uuid5(_SPIKE_OBJECT_NAMESPACE, identity))


def content_digest(value: bytes | str | Mapping[str, Any] | Sequence[Any]) -> str:
    """Return a SHA-256 digest for bytes or canonical JSON-compatible data."""

    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SourceIdentity:
    source_format: str
    source_digest: str
    native_id: str = ""
    artifact_path: str = ""


@dataclass(frozen=True)
class CoordinateFrame:
    frame_id: str = "board"
    parent_frame_id: str = ""
    units: str = "mm"
    handedness: str = "right"
    transform: tuple[float, ...] = (
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0,
        0.0, 0.0, 0.0, 1.0,
    )

    def __post_init__(self) -> None:
        if self.units != "mm" or self.handedness != "right":
            raise ValueError("SPIKE canonical frames must be right-handed and expressed in millimetres.")
        if len(self.transform) != 16:
            raise ValueError("Coordinate-frame transforms must contain 16 values.")
        try:
            normalized = tuple(float(value) for value in self.transform)
        except (TypeError, ValueError) as exc:
            raise ValueError("Coordinate-frame transforms must contain numeric values.") from exc
        if not all(math.isfinite(value) for value in normalized):
            raise ValueError("Coordinate-frame transforms must contain finite values.")
        object.__setattr__(self, "transform", normalized)


@dataclass
class CanonicalEntity:
    id: str
    source_id: str = ""
    name: str = ""
    extensions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Material(CanonicalEntity):
    material_class: str = "unspecified"
    conductivity_s_per_m: Optional[float] = None
    relative_permittivity: Optional[float] = None
    loss_tangent: Optional[float] = None
    thermal_conductivity_w_per_mk: Optional[float] = None
    density_kg_per_m3: Optional[float] = None
    heat_capacity_j_per_kgk: Optional[float] = None


@dataclass
class Layer(CanonicalEntity):
    layer_type: str = "documentation"
    order: int = 0
    z_mm: float = 0.0
    thickness_mm: Optional[float] = None
    material_id: str = ""
    region_ids: List[str] = field(default_factory=list)


@dataclass
class Net(CanonicalEntity):
    net_class: str = "signal"
    aliases: List[str] = field(default_factory=list)


@dataclass
class TrackPath:
    """Ordered straight-stroke membership for one canonical conductor path.

    Wave 1 deliberately admits only round-ended, round-joined paths.  Other
    cap/join policies stay outside the contract until every geometry consumer
    can reproduce them without approximation.
    """

    path_id: str
    step_index: int
    step_count: int
    end_cap: str = "round"
    join_style: str = "round"

    def __post_init__(self) -> None:
        if not isinstance(self.path_id, str) or not self.path_id.strip():
            raise ValueError("Track paths require a non-empty path_id.")
        if isinstance(self.step_index, bool) or not isinstance(self.step_index, int) or self.step_index < 0:
            raise ValueError("Track path step_index must be a non-negative integer.")
        if isinstance(self.step_count, bool) or not isinstance(self.step_count, int) or self.step_count < 1:
            raise ValueError("Track path step_count must be a positive integer.")
        if self.step_index >= self.step_count:
            raise ValueError("Track path step_index must be smaller than step_count.")
        if self.end_cap != "round" or self.join_style != "round":
            raise ValueError("Only round-ended, round-joined conductor paths are currently lossless.")


@dataclass
class Track(CanonicalEntity):
    net_id: str = ""
    layer_id: str = ""
    start_mm: tuple[float, float] = (0.0, 0.0)
    end_mm: tuple[float, float] = (0.0, 0.0)
    width_mm: float = 0.0
    path: Optional[TrackPath] = None


def validate_track_paths(tracks: Sequence[Track]) -> None:
    paths: Dict[str, List[Track]] = {}
    for track in tracks:
        if track.path is not None:
            paths.setdefault(track.path.path_id, []).append(track)
    for path_id, steps in paths.items():
        expected_count = steps[0].path.step_count  # type: ignore[union-attr]
        if len(steps) != expected_count or any(
            step.path is None or step.path.step_count != expected_count for step in steps
        ):
            raise ValueError(f"Track path {path_id!r} does not contain its declared number of steps.")
        ordered = sorted(steps, key=lambda item: item.path.step_index)  # type: ignore[union-attr]
        if [item.path.step_index for item in ordered] != list(range(expected_count)):  # type: ignore[union-attr]
            raise ValueError(f"Track path {path_id!r} step indices must be unique and contiguous.")
        first = ordered[0]
        if any(
            item.net_id != first.net_id
            or item.layer_id != first.layer_id
            or not math.isclose(item.width_mm, first.width_mm, rel_tol=0.0, abs_tol=1e-12)
            for item in ordered[1:]
        ):
            raise ValueError(f"Track path {path_id!r} must keep one net, layer, and width.")
        if any(ordered[index].end_mm != ordered[index + 1].start_mm for index in range(len(ordered) - 1)):
            raise ValueError(f"Track path {path_id!r} steps must be contiguous in source order.")


def track_path_from_v1(raw: Mapping[str, Any]) -> Optional[TrackPath]:
    nested = raw.get("path")
    if isinstance(nested, Mapping):
        return TrackPath(**dict(nested))
    path_id = text(raw.get("path_id"))
    if not path_id:
        return None
    return TrackPath(
        path_id=path_id,
        step_index=int(raw.get("path_step_index", raw.get("step_index", 0))),
        step_count=int(raw.get("path_step_count", raw.get("step_count", 1))),
        end_cap=text(raw.get("path_end_cap", raw.get("end_cap")), "round").lower(),
        join_style=text(raw.get("path_join_style", raw.get("join_style")), "round").lower(),
    )


def hydrate_track_path(values: Dict[str, Any]) -> Dict[str, Any]:
    if values.get("path") is not None and not isinstance(values["path"], TrackPath):
        values["path"] = TrackPath(**dict(values["path"]))
    return values


def strip_null_track_paths(payload: Dict[str, Any]) -> Dict[str, Any]:
    for track in payload.get("tracks", []):
        if track.get("path") is None:
            track.pop("path", None)
    for zone in payload.get("zones", []):
        if not zone.get("boundary_rings"):
            zone.pop("boundary_rings", None)
            zone.pop("fill_style_id", None)
            zone.pop("fill_property", None)
        else:
            for ring in zone["boundary_rings"]:
                for segment in ring.get("segments", []):
                    if segment.get("kind") == "line":
                        segment.pop("center_mm", None)
                        segment.pop("clockwise", None)
    for key in ("pads", "vias"):
        for entity in payload.get(key, []):
            if not entity.get("land_profiles"):
                entity.pop("land_profiles", None)
            if key == "pads" and not entity.get("custom_geometry"):
                entity.pop("custom_geometry", None)
    if not payload.get("retained_padstack_occurrence_groups"):
        payload.pop("retained_padstack_occurrence_groups", None)
    if payload.get("retained_nonregular_padstack_geometry") is None:
        payload.pop("retained_nonregular_padstack_geometry", None)
    else:
        for primitive in payload["retained_nonregular_padstack_geometry"].get("user_primitives", []):
            for contour in primitive.get("contours", []):
                for ring in contour.get("boundary_rings", []):
                    for segment in ring.get("segments", []):
                        if segment.get("kind") == "line":
                            segment.pop("center_mm", None)
                            segment.pop("clockwise", None)
    if payload.get("retained_standard_contour_land_geometry") is None:
        payload.pop("retained_standard_contour_land_geometry", None)
    return payload


def apply_track_path_to_v1(raw: Dict[str, Any], track: Track) -> Dict[str, Any]:
    if track.path is not None:
        raw.update({
            "path_id": track.path.path_id,
            "path_step_index": track.path.step_index,
            "path_step_count": track.path.step_count,
            "path_end_cap": track.path.end_cap,
            "path_join_style": track.path.join_style,
        })
    return raw


def project_track_to_v1(track: Track, net_names: Mapping[str, str], layer_names: Mapping[str, str]) -> Dict[str, Any]:
    preserved = track.extensions.get("spike.v1")
    raw = dict(preserved) if isinstance(preserved, dict) else {
        "id": track.source_id or track.id,
        "net_name": net_names.get(track.net_id, track.net_id),
        "layer": layer_names.get(track.layer_id, track.layer_id),
        "start": list(track.start_mm),
        "end": list(track.end_mm),
        "width": track.width_mm,
    }
    return apply_track_path_to_v1(raw, track)


def project_pad_to_v1(pad: "Pad", net_names: Mapping[str, str], layer_names: Mapping[str, str]) -> Dict[str, Any]:
    preserved = pad.extensions.get("spike.v1")
    raw = dict(preserved) if isinstance(preserved, dict) else {}
    drill_width, drill_height = pad.drill_size_mm
    raw.update({
        "id": pad.source_id or pad.id,
        "net_name": net_names.get(pad.net_id, pad.net_id),
        "at": list(pad.center_mm), "size": list(pad.size_mm), "shape": pad.shape,
        "layers": [layer_names.get(layer, layer) for layer in pad.layer_ids],
        "drill": min(drill_width, drill_height) if drill_width > 0 and drill_height > 0 else 0.0,
        "drill_size": [drill_width, drill_height], "drill_shape": pad.drill_shape,
        "plated": pad.plated,
        "pad_kind": pad.pad_kind,
        "zone_connection_override": pad.zone_connection_override,
        "zone_connection_declared": pad.zone_connection_declared,
        "zone_connection_layer_overrides": {
            layer_names.get(layer, layer): mode for layer, mode in pad.zone_connection_layer_overrides.items()
        },
        "thermal_gap_override_mm": pad.thermal_gap_override_mm,
        "thermal_spoke_width_override_mm": pad.thermal_spoke_width_override_mm,
        "thermal_spoke_angle_deg": pad.thermal_spoke_angle_deg,
        "thermal_settings_valid": pad.thermal_settings_valid,
    })
    if pad.custom_geometry:
        raw["custom_geometry"] = dict(pad.custom_geometry)
    if pad.land_profiles:
        raw["land_profiles"] = project_land_profiles_to_v1(pad.land_profiles, layer_names)
    return raw


def project_via_to_v1(via: "Via", net_names: Mapping[str, str], layer_names: Mapping[str, str]) -> Dict[str, Any]:
    preserved = via.extensions.get("spike.v1")
    raw = dict(preserved) if isinstance(preserved, dict) else {}
    raw.update({
        "id": via.source_id or via.id,
        "net_name": net_names.get(via.net_id, via.net_id),
        "at": list(via.center_mm), "diameter": via.diameter_mm, "drill": via.drill_mm,
        "layers": [layer_names.get(via.start_layer_id, via.start_layer_id), layer_names.get(via.end_layer_id, via.end_layer_id)],
        "type": via.via_type, "plating_mm": via.plating_mm,
    })
    if via.land_profiles:
        raw["land_profiles"] = project_land_profiles_to_v1(via.land_profiles, layer_names)
    return raw


def drill_from_v1(
    raw: Mapping[str, Any], index: int, source_format: str, digest: str,
    layer_ids: Mapping[str, str], net_ids: Mapping[str, str],
    component_ids: Mapping[str, str], owner_ids: Mapping[tuple[str, str], str],
) -> "Drill":
    owner_kind = text(raw.get("owner_kind"), "unresolved")
    owner_source_id = text(raw.get("owner_id"))
    layer_source = text(raw.get("source_layer_id", raw.get("layer")))
    net_source = text(raw.get("net_id", raw.get("net")))
    component_source = text(raw.get("component_id", raw.get("component")))
    return Drill(
        id=entity_id(source_format, digest, "drill", raw, index),
        source_id=source_id(raw, index), name=text(raw.get("name")),
        source_layer_id=layer_ids.get(layer_source, layer_source),
        center_mm=point(raw.get("center_mm", raw.get("at"))),
        shape=text(raw.get("shape"), "circle"),
        diameter_mm=number(raw.get("diameter_mm", raw.get("diameter"))) if raw.get("diameter_mm", raw.get("diameter")) is not None else None,
        size_mm=point(raw.get("size_mm", raw.get("size"))) if raw.get("size_mm", raw.get("size")) is not None else None,
        rotation_deg=number(raw.get("rotation_deg", raw.get("rotation"))) if raw.get("rotation_deg", raw.get("rotation")) is not None else None,
        plating_status=text(raw.get("plating_status"), "unknown"),
        plated=raw.get("plated") if isinstance(raw.get("plated"), bool) else None,
        plus_tolerance_mm=number(raw.get("plus_tolerance_mm")) if raw.get("plus_tolerance_mm") is not None else None,
        minus_tolerance_mm=number(raw.get("minus_tolerance_mm")) if raw.get("minus_tolerance_mm") is not None else None,
        net_id=net_ids.get(net_source, net_source), component_id=component_ids.get(component_source, component_source),
        geometry_ref=text(raw.get("geometry_ref")),
        span_layer_ids=[layer_ids.get(text(item), text(item)) for item in raw.get("span_layer_ids", raw.get("layers", []))],
        span_provenance=text(raw.get("span_provenance"), "unresolved"), owner_kind=owner_kind,
        owner_id=owner_ids.get((owner_kind, owner_source_id), owner_source_id), owner_match=text(raw.get("owner_match"), "none"),
        extensions={"spike.v1": dict(raw)},
    )


def project_drill_to_v1(
    drill: "Drill", layer_names: Mapping[str, str], net_names: Mapping[str, str],
    component_names: Mapping[str, str], owner_names: Mapping[str, str],
) -> Dict[str, Any]:
    preserved = drill.extensions.get("spike.v1")
    raw = dict(preserved) if isinstance(preserved, dict) else {}
    raw.update({
        "id": drill.source_id or drill.id, "name": drill.name,
        "source_layer_id": layer_names.get(drill.source_layer_id, drill.source_layer_id), "at": list(drill.center_mm),
        "shape": drill.shape, "diameter_mm": drill.diameter_mm,
        "size_mm": list(drill.size_mm) if drill.size_mm is not None else None, "rotation_deg": drill.rotation_deg,
        "plating_status": drill.plating_status, "plated": drill.plated,
        "plus_tolerance_mm": drill.plus_tolerance_mm, "minus_tolerance_mm": drill.minus_tolerance_mm,
        "net_id": net_names.get(drill.net_id, drill.net_id), "component_id": component_names.get(drill.component_id, drill.component_id),
        "geometry_ref": drill.geometry_ref, "span_layer_ids": [layer_names.get(item, item) for item in drill.span_layer_ids],
        "span_provenance": drill.span_provenance, "owner_kind": drill.owner_kind,
        "owner_id": owner_names.get(drill.owner_id, drill.owner_id), "owner_match": drill.owner_match,
    })
    return raw


@dataclass
class Arc(CanonicalEntity):
    net_id: str = ""
    layer_id: str = ""
    start_mm: tuple[float, float] = (0.0, 0.0)
    mid_mm: tuple[float, float] = (0.0, 0.0)
    end_mm: tuple[float, float] = (0.0, 0.0)
    width_mm: float = 0.0


@dataclass
class Zone(CanonicalEntity):
    net_id: str = ""
    layer_ids: List[str] = field(default_factory=list)
    outlines_mm: List[List[tuple[float, float]]] = field(default_factory=list)
    holes_mm: List[List[tuple[float, float]]] = field(default_factory=list)
    boundary_rings: List[ZoneBoundaryRing] = field(default_factory=list)
    fill_style_id: str = ""
    fill_property: str = ""
    source_zone_id: str = ""
    filled_copper_id: str = ""
    source_zone_outline_id: str = ""
    source_zone_outline_sha256: str = ""
    source_zone_outline_paths_mm: List[List[tuple[float, float]]] = field(default_factory=list)
    source_zone_outline_path_count: int = 0
    source_zone_outline_vertex_count: int = 0
    source_zone_outline_representation: str = "none"
    source_zone_outline_provenance_complete: bool = False
    parametric_refill_eligible: bool = False
    source_fill_group_id: str = ""
    source_fill_group_sha256: str = ""
    source_fill_component_ordinal: int = 0
    source_fill_component_count: int = 0
    source_fill_component_sha256: str = ""
    source_fill_representation: str = "none"
    source_fill_provenance_complete: bool = False
    thermal_topology_eligible: bool = False
    zone_kind: str = "copper"
    filled_copper_state: str = "unknown"
    zone_connection_default: str = "unknown"
    zone_connection_declared: bool = False
    clearance_mm: Optional[float] = None
    thermal_gap_mm: Optional[float] = None
    thermal_spoke_width_mm: Optional[float] = None
    fill_mode: str = "unknown"
    thermal_settings_valid: bool = False

    def __post_init__(self) -> None:
        self.boundary_rings = [
            item if isinstance(item, ZoneBoundaryRing) else ZoneBoundaryRing(**dict(item))
            for item in self.boundary_rings
        ]
        validate_zone_policy(self)
        if not self.boundary_rings:
            return
        if self.outlines_mm or self.holes_mm:
            raise ValueError("Exact zone boundaries cannot coexist with point-only polygons.")
        if self.boundary_rings[0].role != "outer" or any(item.role != "cutout" for item in self.boundary_rings[1:]):
            raise ValueError("Exact zones require one outer boundary followed by cutouts.")
        if not self.fill_style_id or self.fill_property != "FILL":
            raise ValueError("Exact zones require a resolved solid fill style.")


def hydrate_zone_boundaries(values: Dict[str, Any]) -> Dict[str, Any]:
    values["boundary_rings"] = [
        item if isinstance(item, ZoneBoundaryRing) else ZoneBoundaryRing(**dict(item))
        for item in values.get("boundary_rings", [])
    ]
    return values


def zone_from_v1(
    raw: Mapping[str, Any], index: int, source_format: str, digest: str,
    layer_ids: Mapping[str, str], net_ids: Mapping[str, str],
) -> Zone:
    net_source = text(raw.get("net_id", raw.get("net_name", raw.get("net"))))
    layer_sources = [text(item) for item in raw.get("layers", [raw.get("layer")]) if item]
    return Zone(
        id=entity_id(source_format, digest, "zone", raw, index), source_id=source_id(raw, index),
        name=text(raw.get("name")), net_id=net_ids.get(net_source, net_source),
        layer_ids=[layer_ids.get(item, item) for item in layer_sources],
        outlines_mm=[[point(item) for item in polygon] for polygon in raw.get("polygons", [raw.get("points", [])]) if polygon],
        holes_mm=[[point(item) for item in polygon] for polygon in raw.get("holes", [])],
        boundary_rings=hydrate_zone_boundaries({"boundary_rings": raw.get("boundary_rings", [])})["boundary_rings"],
        fill_style_id=text(raw.get("fill_style_id")), fill_property=text(raw.get("fill_property")),
        source_zone_id=text(raw.get("source_zone_id", raw.get("zone_uuid"))),
        filled_copper_id=text(raw.get("filled_copper_id")),
        source_zone_outline_id=text(raw.get("source_zone_outline_id")), source_zone_outline_sha256=text(raw.get("source_zone_outline_sha256")),
        source_zone_outline_paths_mm=[[point(item) for item in path] for path in raw.get("source_zone_outline_paths_mm", [])],
        source_zone_outline_path_count=int(raw.get("source_zone_outline_path_count", 0)), source_zone_outline_vertex_count=int(raw.get("source_zone_outline_vertex_count", 0)),
        source_zone_outline_representation=text(raw.get("source_zone_outline_representation"), "none"), source_zone_outline_provenance_complete=bool(raw.get("source_zone_outline_provenance_complete", False)), parametric_refill_eligible=bool(raw.get("parametric_refill_eligible", False)),
        source_fill_group_id=text(raw.get("source_fill_group_id")), source_fill_group_sha256=text(raw.get("source_fill_group_sha256")),
        source_fill_component_ordinal=int(raw.get("source_fill_component_ordinal", 0)), source_fill_component_count=int(raw.get("source_fill_component_count", 0)),
        source_fill_component_sha256=text(raw.get("source_fill_component_sha256")), source_fill_representation=text(raw.get("source_fill_representation"), "none"),
        source_fill_provenance_complete=bool(raw.get("source_fill_provenance_complete", False)),
        thermal_topology_eligible=bool(raw.get("thermal_topology_eligible", False)),
        zone_kind=text(raw.get("zone_kind"), "copper"),
        filled_copper_state=text(raw.get("filled_copper_state"), "unknown"),
        zone_connection_default=text(raw.get("zone_connection_default"), "unknown"),
        zone_connection_declared=bool(raw.get("zone_connection_declared", False)),
        clearance_mm=number(raw.get("clearance_mm")) if raw.get("clearance_mm") is not None else None,
        thermal_gap_mm=number(raw.get("thermal_gap_mm")) if raw.get("thermal_gap_mm") is not None else None,
        thermal_spoke_width_mm=number(raw.get("thermal_spoke_width_mm")) if raw.get("thermal_spoke_width_mm") is not None else None,
        fill_mode=text(raw.get("fill_mode"), "unknown"),
        thermal_settings_valid=bool(raw.get("thermal_settings_valid", False)),
        extensions={"spike.v1": dict(raw)},
    )


def _zone_boundary_payload(ring: ZoneBoundaryRing) -> Dict[str, Any]:
    return {
        "role": ring.role, "start_mm": list(ring.start_mm),
        "segments": [
            {"kind": item.kind, "end_mm": list(item.end_mm),
             **({"center_mm": list(item.center_mm), "clockwise": item.clockwise} if item.kind == "arc" else {})}
            for item in ring.segments
        ],
    }


def project_zone_to_v1(zone: Zone, net_names: Mapping[str, str], layer_names: Mapping[str, str]) -> Dict[str, Any]:
    preserved = zone.extensions.get("spike.v1")
    raw = dict(preserved) if isinstance(preserved, dict) else {
        "id": zone.source_id or zone.id, "net_name": net_names.get(zone.net_id, zone.net_id),
        "layers": [layer_names.get(item, item) for item in zone.layer_ids],
        "polygons": [[list(point_value) for point_value in polygon] for polygon in zone.outlines_mm],
        "holes": [[list(point_value) for point_value in polygon] for polygon in zone.holes_mm],
    }
    if zone.boundary_rings:
        raw.update({"boundary_rings": [_zone_boundary_payload(item) for item in zone.boundary_rings],
                    "fill_style_id": zone.fill_style_id, "fill_property": zone.fill_property})
    raw.update({
        "source_zone_id": zone.source_zone_id, "filled_copper_id": zone.filled_copper_id,
        "source_zone_outline_id": zone.source_zone_outline_id, "source_zone_outline_sha256": zone.source_zone_outline_sha256,
        "source_zone_outline_paths_mm": [[list(item) for item in path] for path in zone.source_zone_outline_paths_mm],
        "source_zone_outline_path_count": zone.source_zone_outline_path_count, "source_zone_outline_vertex_count": zone.source_zone_outline_vertex_count,
        "source_zone_outline_representation": zone.source_zone_outline_representation, "source_zone_outline_provenance_complete": zone.source_zone_outline_provenance_complete, "parametric_refill_eligible": zone.parametric_refill_eligible,
        "source_fill_group_id": zone.source_fill_group_id, "source_fill_group_sha256": zone.source_fill_group_sha256,
        "source_fill_component_ordinal": zone.source_fill_component_ordinal, "source_fill_component_count": zone.source_fill_component_count,
        "source_fill_component_sha256": zone.source_fill_component_sha256, "source_fill_representation": zone.source_fill_representation,
        "source_fill_provenance_complete": zone.source_fill_provenance_complete,
        "thermal_topology_eligible": zone.thermal_topology_eligible,
        "zone_kind": zone.zone_kind, "filled_copper_state": zone.filled_copper_state,
        "zone_connection_default": zone.zone_connection_default,
        "zone_connection_declared": zone.zone_connection_declared,
        "clearance_mm": zone.clearance_mm, "thermal_gap_mm": zone.thermal_gap_mm,
        "thermal_spoke_width_mm": zone.thermal_spoke_width_mm, "fill_mode": zone.fill_mode,
        "thermal_settings_valid": zone.thermal_settings_valid,
    })
    return raw


@dataclass
class Pad(CanonicalEntity):
    net_id: str = ""
    component_id: str = ""
    pin_id: str = ""
    layer_ids: List[str] = field(default_factory=list)
    center_mm: tuple[float, float] = (0.0, 0.0)
    size_mm: tuple[float, float] = (0.0, 0.0)
    shape: str = "custom"
    drill_size_mm: tuple[float, float] = (0.0, 0.0)
    drill_shape: str = "none"
    plated: bool = False
    land_profiles: List[LandProfile] = field(default_factory=list)
    custom_geometry: Dict[str, Any] = field(default_factory=dict)
    pad_kind: str = "unknown"
    zone_connection_override: str = "inherit"
    zone_connection_declared: bool = False
    zone_connection_layer_overrides: Dict[str, str] = field(default_factory=dict)
    thermal_gap_override_mm: Optional[float] = None
    thermal_spoke_width_override_mm: Optional[float] = None
    thermal_spoke_angle_deg: Optional[float] = None
    thermal_settings_valid: bool = False

    def __post_init__(self) -> None:
        validate_pad_policy(self)


@dataclass
class Via(CanonicalEntity):
    net_id: str = ""
    center_mm: tuple[float, float] = (0.0, 0.0)
    diameter_mm: float = 0.0
    drill_mm: float = 0.0
    start_layer_id: str = ""
    end_layer_id: str = ""
    plating_mm: Optional[float] = None
    via_type: str = "through"
    land_profiles: List[LandProfile] = field(default_factory=list)


@dataclass
class Drill(CanonicalEntity):
    """Physical/manufacturing drill record, independent of electrical ownership."""

    source_layer_id: str = ""
    center_mm: tuple[float, float] = (0.0, 0.0)
    shape: str = "circle"
    diameter_mm: Optional[float] = None
    size_mm: Optional[tuple[float, float]] = None
    rotation_deg: Optional[float] = None
    plating_status: str = "unknown"
    plated: Optional[bool] = None
    plus_tolerance_mm: Optional[float] = None
    minus_tolerance_mm: Optional[float] = None
    net_id: str = ""
    component_id: str = ""
    geometry_ref: str = ""
    span_layer_ids: List[str] = field(default_factory=list)
    span_provenance: str = "unresolved"
    owner_kind: str = "unresolved"
    owner_id: str = ""
    owner_match: str = "none"

    def __post_init__(self) -> None:
        self.center_mm = point(self.center_mm)
        self.size_mm = point(self.size_mm) if self.size_mm is not None else None
        if not all(math.isfinite(value) for value in self.center_mm):
            raise ValueError("Drill centers must be finite.")
        if self.shape not in {"circle", "slot", "polygon", "custom"}:
            raise ValueError("Drill shape is unsupported.")
        if self.shape == "circle" and (self.diameter_mm is None or not math.isfinite(self.diameter_mm) or self.diameter_mm <= 0):
            raise ValueError("Circular drills require a finite positive diameter.")
        if self.plating_status not in {"plated", "unplated", "via", "unknown"}:
            raise ValueError("Drill plating_status is unsupported.")
        for value in (self.plus_tolerance_mm, self.minus_tolerance_mm):
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError("Drill tolerances must be finite and non-negative.")
        if self.span_provenance not in {"explicit", "matched_owner", "unresolved"}:
            raise ValueError("Drill span_provenance is unsupported.")
        if self.owner_kind not in {"via", "pad", "none", "unresolved"} or self.owner_match not in {"exact_source", "geometric", "none"}:
            raise ValueError("Drill ownership metadata is unsupported.")
        if (self.owner_kind in {"via", "pad"}) != bool(self.owner_id):
            raise ValueError("Owned drills require exactly one owner identity.")


def validate_drill_references(
    drills: Sequence[Drill], *, layers: Sequence[Layer], nets: Sequence[Net],
    components: Sequence["Component"], pads: Sequence[Pad], vias: Sequence[Via],
) -> None:
    """Ensure typed drill links resolve to the canonical entities they name.

    Empty electrical and layer links deliberately remain valid: a manufacturing
    drill can be unresolved, but any link that is supplied is a canonical ID
    and must be resolvable.
    """

    known_ids = {
        "layer": {item.id for item in layers},
        "net": {item.id for item in nets},
        "component": {item.id for item in components},
        "pad": {item.id for item in pads},
        "via": {item.id for item in vias},
    }
    for drill in drills:
        references = (
            ("source_layer_id", drill.source_layer_id, "layer"),
            ("net_id", drill.net_id, "net"),
            ("component_id", drill.component_id, "component"),
        )
        for field_name, reference_id, kind in references:
            if reference_id and reference_id not in known_ids[kind]:
                raise ValueError(
                    f"Drill {drill.id!r} {field_name} references unknown {kind} {reference_id!r}."
                )
        for layer_id in drill.span_layer_ids:
            if layer_id not in known_ids["layer"]:
                raise ValueError(
                    f"Drill {drill.id!r} span_layer_ids references unknown layer {layer_id!r}."
                )
        if drill.owner_kind in {"pad", "via"} and drill.owner_id not in known_ids[drill.owner_kind]:
            raise ValueError(
                f"Drill {drill.id!r} owner_id references unknown {drill.owner_kind} {drill.owner_id!r}."
            )


@dataclass
class Castellation(CanonicalEntity):
    net_id: str = ""
    via_id: str = ""
    boundary_region_id: str = ""
    retained_fraction: float = 0.5


@dataclass
class Pin(CanonicalEntity):
    component_id: str = ""
    number: str = ""
    net_id: str = ""
    pad_ids: List[str] = field(default_factory=list)


@dataclass
class ModelReference(CanonicalEntity):
    model_type: str = "3d"
    uri: str = ""
    digest: str = ""
    transform: List[float] = field(default_factory=list)


@dataclass
class Component(CanonicalEntity):
    reference: str = ""
    value: str = ""
    footprint: str = ""
    side: str = "top"
    position_mm: tuple[float, float] = (0.0, 0.0)
    rotation_deg: float = 0.0
    pin_ids: List[str] = field(default_factory=list)
    model_ids: List[str] = field(default_factory=list)
    zone_connection_override: str = "inherit"
    zone_connection_declared: bool = False
    thermal_gap_override_mm: Optional[float] = None
    thermal_spoke_width_override_mm: Optional[float] = None
    thermal_settings_valid: bool = False

    def __post_init__(self) -> None:
        validate_component_policy(self)


@dataclass
class ComponentBond(CanonicalEntity):
    component_id: str = ""
    pin_id: str = ""
    pad_id: str = ""
    electrical_material_id: str = ""
    thermal_material_id: str = ""
    contact_area_mm2: Optional[float] = None
    thickness_mm: Optional[float] = None


@dataclass
class Connector(CanonicalEntity):
    component_id: str = ""
    pin_ids: List[str] = field(default_factory=list)
    mating_connector_id: str = ""


@dataclass
class Region(CanonicalEntity):
    region_type: str = "rigid"
    outlines_mm: List[List[tuple[float, float]]] = field(default_factory=list)
    layer_ids: List[str] = field(default_factory=list)


@dataclass
class Bend(CanonicalEntity):
    region_id: str = ""
    line_start_mm: tuple[float, float] = (0.0, 0.0)
    line_end_mm: tuple[float, float] = (0.0, 0.0)
    angle_deg: float = 0.0
    radius_mm: Optional[float] = None


@dataclass
class NamedRecord(CanonicalEntity):
    """Typed identity envelope for constraints, variants, and model semantics."""

    kind: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


def point(raw: Any, fallback: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            return float(raw[0]), float(raw[1])
        except (TypeError, ValueError):
            return fallback
    return fallback


def text(value: Any, fallback: str = "") -> str:
    """Return a non-empty stable text value without treating numeric zero as absent."""

    if value is None:
        return fallback
    result = str(value).strip()
    return result or fallback


def number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def native_identity(raw: Mapping[str, Any]) -> str:
    """Return the strongest native identity carried by a v1 object."""

    for key in ("source_id", "uuid", "id"):
        value = text(raw.get(key))
        if value:
            return value
    return ""


def semantic_identity(kind: str, raw: Mapping[str, Any]) -> str:
    """Create a deterministic fallback for anonymous records."""

    ignored = {"source_digest", "source_sha256", "file_digest", "timestamp", "updated_at"}
    stable = {key: value for key, value in raw.items() if key not in ignored}
    return f"{kind}:{content_digest(stable)}"


def entity_identity(kind: str, raw: Mapping[str, Any], index: int) -> tuple[str, str]:
    native = native_identity(raw)
    if native:
        return native, "native"
    return semantic_identity(kind, raw), "semantic"


def entity_id(source_format: str, digest: str, kind: str, raw: Mapping[str, Any], index: int) -> str:
    identity, identity_kind = entity_identity(kind, raw, index)
    scope = "native" if identity_kind == "native" else "semantic"
    return canonical_uuid(source_format, scope, kind, identity)


def source_id(raw: Mapping[str, Any], index: int) -> str:
    native = native_identity(raw)
    return native or semantic_identity("source", raw)


def net_lookup(nets: Iterable[Net]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for net in nets:
        lookup[net.id] = net.id
        if net.source_id:
            lookup[net.source_id] = net.id
        if net.name:
            lookup[net.name] = net.id
    return lookup
