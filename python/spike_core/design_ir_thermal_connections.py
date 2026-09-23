"""Validation and source normalization for retained PCB zone-connection policy."""
from __future__ import annotations

import math
from typing import Any, Mapping


CONNECTION_MODES = {"none", "thermal", "solid", "tht_thermal", "unknown"}
CONNECTION_OVERRIDES = {"inherit", *CONNECTION_MODES}
PAD_KINDS = {"smd", "thru_hole", "np_thru_hole", "connect", "unknown"}


def normalize_pad_kind(raw: Mapping[str, Any]) -> str:
    declared = str(raw.get("pad_kind", raw.get("type", "unknown"))).strip().lower()
    normalized = {"through_hole": "thru_hole", "connector": "connect"}.get(declared, declared)
    return normalized if normalized in PAD_KINDS else "unknown"


def _dimensions(values, label: str) -> None:
    if any(value is not None and (not math.isfinite(value) or value < 0) for value in values):
        raise ValueError(f"{label} thermal dimensions must be finite and non-negative.")


def validate_zone_policy(zone: Any) -> None:
    if zone.zone_kind not in {"copper", "keepout", "unknown"}:
        raise ValueError("Zone kind is unsupported.")
    if zone.filled_copper_state not in {"source_filled", "outline_fallback", "none", "unknown"}:
        raise ValueError("Zone filled-copper state is unsupported.")
    if zone.zone_connection_default not in CONNECTION_MODES:
        raise ValueError("Zone connection default is unsupported.")
    if zone.fill_mode not in {"solid", "hatched", "unknown"}:
        raise ValueError("Zone fill mode is unsupported.")
    if not isinstance(zone.zone_connection_declared, bool) or not isinstance(zone.thermal_settings_valid, bool):
        raise ValueError("Zone thermal declaration flags must be boolean.")
    _dimensions((zone.clearance_mm, zone.thermal_gap_mm, zone.thermal_spoke_width_mm), "Zone")
    if zone.zone_connection_default == "unknown" and zone.thermal_settings_valid:
        raise ValueError("Unknown zone connection defaults cannot be marked valid.")
    if zone.filled_copper_state == "source_filled" and not zone.filled_copper_id:
        raise ValueError("Source-filled zones require a filled-copper identity.")
    if zone.source_zone_outline_representation not in {"none", "flat_polygon_paths", "unknown"}:
        raise ValueError("Zone source-outline representation is unsupported.")
    if not isinstance(zone.source_zone_outline_provenance_complete, bool) or not isinstance(zone.parametric_refill_eligible, bool):
        raise ValueError("Zone source-outline qualification flags must be boolean.")
    outline_digest = zone.source_zone_outline_sha256
    if outline_digest and (len(outline_digest) != 64 or any(char not in "0123456789abcdef" for char in outline_digest)):
        raise ValueError("Zone source-outline digest must be a lowercase SHA-256 value.")
    paths = zone.source_zone_outline_paths_mm
    vertex_count = sum(len(path) for path in paths)
    if zone.source_zone_outline_path_count < 0 or zone.source_zone_outline_vertex_count < 0:
        raise ValueError("Zone source-outline counts must be non-negative.")
    if zone.source_zone_outline_provenance_complete:
        if (not zone.source_zone_outline_id or not outline_digest
                or zone.source_zone_outline_representation != "flat_polygon_paths"):
            raise ValueError("Complete source-outline provenance requires identities and flat polygon paths.")
        if not paths or len(paths) != zone.source_zone_outline_path_count or vertex_count != zone.source_zone_outline_vertex_count:
            raise ValueError("Complete source-outline counts must match retained paths.")
        if len(paths) > 256 or any(not 3 <= len(path) <= 65_536 for path in paths) or vertex_count > 1_048_576:
            raise ValueError("Zone source-outline geometry exceeds bounded limits.")
        if any(not math.isfinite(value) for path in paths for point in path for value in point):
            raise ValueError("Zone source-outline coordinates must be finite.")
    elif any((zone.source_zone_outline_id, outline_digest, paths,
              zone.source_zone_outline_path_count, zone.source_zone_outline_vertex_count)) or zone.source_zone_outline_representation != "none":
        raise ValueError("Incomplete source-outline provenance cannot retain qualified metadata.")
    if zone.parametric_refill_eligible:
        raise ValueError("Retained source outlines are not independently sufficient for parametric refill.")
    if zone.source_fill_representation not in {"none", "flat_polygon_path", "unknown"}:
        raise ValueError("Zone source-fill representation is unsupported.")
    if not isinstance(zone.source_fill_provenance_complete, bool) or not isinstance(zone.thermal_topology_eligible, bool):
        raise ValueError("Zone source-fill qualification flags must be boolean.")
    digest_fields = (zone.source_fill_group_sha256, zone.source_fill_component_sha256)
    if any(value and (len(value) != 64 or any(char not in "0123456789abcdef" for char in value)) for value in digest_fields):
        raise ValueError("Zone source-fill digests must be lowercase SHA-256 values.")
    if zone.source_fill_component_ordinal < 0 or zone.source_fill_component_count < 0:
        raise ValueError("Zone source-fill component counts must be non-negative.")
    if zone.source_fill_component_ordinal > 65_536 or zone.source_fill_component_count > 65_536:
        raise ValueError("Zone source-fill component counts exceed bounded limits.")
    if zone.source_fill_component_ordinal > zone.source_fill_component_count:
        raise ValueError("Zone source-fill component ordinal exceeds its group count.")
    if zone.source_fill_provenance_complete:
        if zone.filled_copper_state != "source_filled" or zone.source_fill_representation != "flat_polygon_path":
            raise ValueError("Complete source-fill provenance requires a retained flat filled-polygon path.")
        if not zone.source_fill_group_id or not all(digest_fields):
            raise ValueError("Complete source-fill provenance requires group and component identities.")
        if zone.source_fill_component_ordinal < 1 or zone.source_fill_component_count < 1:
            raise ValueError("Complete source-fill provenance requires positive component membership.")
    elif any((zone.source_fill_group_id, *digest_fields, zone.source_fill_component_ordinal,
              zone.source_fill_component_count)) or zone.source_fill_representation != "none":
        raise ValueError("Incomplete source-fill provenance cannot retain qualified group metadata.")
    if zone.thermal_topology_eligible:
        raise ValueError("Flat source-filled polygon paths are not yet eligible for thermal-topology extraction.")


def validate_pad_policy(pad: Any) -> None:
    if pad.pad_kind not in PAD_KINDS:
        raise ValueError("Pad kind is unsupported.")
    if pad.zone_connection_override not in CONNECTION_OVERRIDES:
        raise ValueError("Pad zone connection override is unsupported.")
    if not isinstance(pad.zone_connection_declared, bool) or not isinstance(pad.thermal_settings_valid, bool):
        raise ValueError("Pad thermal declaration flags must be boolean.")
    if not isinstance(pad.zone_connection_layer_overrides, dict):
        raise ValueError("Pad layer connection overrides must be an object.")
    if any(not str(layer) or mode not in CONNECTION_MODES for layer, mode in pad.zone_connection_layer_overrides.items()):
        raise ValueError("Pad layer connection overrides are invalid.")
    _dimensions((pad.thermal_gap_override_mm, pad.thermal_spoke_width_override_mm), "Pad")
    angle = pad.thermal_spoke_angle_deg
    if angle is not None and (not math.isfinite(angle) or not 0 <= angle < 360):
        raise ValueError("Pad thermal spoke angle must be in [0, 360).")
    if pad.zone_connection_override == "unknown" and pad.thermal_settings_valid:
        raise ValueError("Unknown pad connection overrides cannot be marked valid.")


def validate_component_policy(component: Any) -> None:
    if component.zone_connection_override not in CONNECTION_OVERRIDES:
        raise ValueError("Component zone connection override is unsupported.")
    if not isinstance(component.zone_connection_declared, bool) or not isinstance(component.thermal_settings_valid, bool):
        raise ValueError("Component thermal declaration flags must be boolean.")
    _dimensions((component.thermal_gap_override_mm, component.thermal_spoke_width_override_mm), "Component")
    if component.zone_connection_override == "unknown" and component.thermal_settings_valid:
        raise ValueError("Unknown component connection overrides cannot be marked valid.")
