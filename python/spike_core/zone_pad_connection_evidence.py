"""Digest-bound evidence for KiCad zone-to-pad connection policy.

The report resolves retained source policy and observes contact against the
source-filled polygon.  It never regenerates a thermal spoke or promotes a
mesh, field solution, or physical model.
"""
from __future__ import annotations

import json
import hashlib
from typing import Any, Callable, Dict, Mapping

from .design_ir_v2 import DesignIRV2
from .design_ir_v2_schema import content_digest


CONTRACT = "spike/zone-pad-connection-evidence/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0018"
MAX_PADS = 65_536
MAX_SOURCE_FILLED_ZONES = 65_536
MAX_RECORDS = 262_144
MAX_WORK_STEPS = 16_777_216
# Marble-class boards retain source-filled copper rings which can make a valid
# DesignIR larger than 64 MiB.  This remains a hard admission limit: it is
# deliberately separate from the record and work limits below.
MAX_SERIALIZED_BYTES = 134_217_728


class ZonePadConnectionEvidenceError(ValueError):
    code = ERROR_CODE


def _fail(message: str) -> None:
    raise ZonePadConnectionEvidenceError(f"{ERROR_CODE}: {message}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ZonePadConnectionEvidenceError(f"{ERROR_CODE}: evidence inputs must be finite JSON values") from error


def _canonical_digest_and_size(value: Any) -> tuple[str, int]:
    """Digest canonical DesignIR JSON without allocating a second full copy.

    ``content_digest`` defines the public source binding as compact,
    ASCII-escaped, sorted JSON.  Iterating the encoder preserves those exact
    bytes without constructing a second complete JSON byte string.  The
    resource gate is enforced while encoding, before any over-limit input is
    completely hashed.
    """
    digest = hashlib.sha256()
    serialized_bytes = 0
    try:
        encoder = json.JSONEncoder(
            sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        )
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            digest.update(encoded)
            serialized_bytes += len(encoded)
            if serialized_bytes > MAX_SERIALIZED_BYTES:
                _fail("DesignIR v2 exceeds the 128 MiB connection-evidence input limit")
    except (TypeError, ValueError) as error:
        raise ZonePadConnectionEvidenceError(f"{ERROR_CODE}: evidence inputs must be finite JSON values") from error
    return digest.hexdigest(), serialized_bytes


def _design(value: DesignIRV2 | Mapping[str, Any]) -> tuple[DesignIRV2, Dict[str, Any]]:
    if isinstance(value, DesignIRV2):
        design, payload = value, value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
        try:
            design = DesignIRV2.from_dict(payload)
        except (TypeError, ValueError) as error:
            raise ZonePadConnectionEvidenceError(f"{ERROR_CODE}: source geometry is not valid DesignIR v2") from error
    else:
        _fail("source geometry must be DesignIR v2 or a mapping")
    if payload.get("contract") != "spike/design-ir/v2" or not design.design_id:
        _fail("connection evidence requires an identified spike/design-ir/v2 source")
    return design, payload


def _cancel(cancel_check: Callable[[], Any] | None) -> None:
    if cancel_check is not None and bool(cancel_check()):
        _fail("zone-pad connection evidence generation was cancelled")


def _observes_contact(raw_pad, pad_boundary, pad_bounds, polygon, zone_edges, tolerance: float) -> bool:
    """Boolean-equivalent spatially bounded form of hybrid pad/zone contact."""
    from .hybrid_mesh import (
        _point, _point_in_pad, _point_in_polygon, _segment_intersection_points, _segments,
    )
    center = _point(raw_pad.get("at", (0, 0)))
    if _point_in_pad(center, raw_pad) and _point_in_polygon(center, polygon, tolerance):
        return True
    if any(_point_in_pad(point, raw_pad) and _point_in_polygon(point, polygon, tolerance) for point in pad_boundary):
        return True
    if any(
        pad_bounds[0] - tolerance <= point[0] <= pad_bounds[2] + tolerance
        and pad_bounds[1] - tolerance <= point[1] <= pad_bounds[3] + tolerance
        and _point_in_pad(point, raw_pad) and _point_in_polygon(point, polygon, tolerance)
        for point in polygon
    ):
        return True
    for pad_start, pad_end in _segments(pad_boundary):
        edge_min_x, edge_max_x = sorted((pad_start[0], pad_end[0]))
        edge_min_y, edge_max_y = sorted((pad_start[1], pad_end[1]))
        for zone_start, zone_end, zone_bounds in zone_edges:
            if (edge_max_x < zone_bounds[0] - tolerance or zone_bounds[2] < edge_min_x - tolerance
                    or edge_max_y < zone_bounds[1] - tolerance or zone_bounds[3] < edge_min_y - tolerance):
                continue
            for point in _segment_intersection_points(pad_start, pad_end, zone_start, zone_end, tolerance):
                if _point_in_pad(point, raw_pad) and _point_in_polygon(point, polygon, tolerance):
                    return True
    return False


def _resolve_mode(pad, component, zone, layer_id: str) -> tuple[str, str, str, str, str, str]:
    layer_mode = str(pad.zone_connection_layer_overrides.get(layer_id, "inherit"))
    pad_mode = str(pad.zone_connection_override)
    footprint_mode = str(component.zone_connection_override) if component is not None else "inherit"
    zone_mode = str(zone.zone_connection_default)
    if not zone.thermal_settings_valid or not pad.thermal_settings_valid or (component is not None and not component.thermal_settings_valid):
        _fail("a candidate connection has invalid or unresolved retained thermal settings")
    modes = {"inherit", "none", "thermal", "solid", "tht_thermal"}
    if any(mode not in modes for mode in (layer_mode, pad_mode, footprint_mode)) or zone_mode not in modes - {"inherit"}:
        _fail("a candidate connection contains an unknown retained connection mode")
    if layer_mode != "inherit":
        selected, resolved_by = layer_mode, "pad_layer_override"
    elif pad_mode != "inherit":
        selected, resolved_by = pad_mode, "pad_override"
    elif footprint_mode != "inherit":
        selected, resolved_by = footprint_mode, "footprint_override"
    else:
        selected, resolved_by = zone_mode, "zone_default"
    if selected == "tht_thermal":
        if pad.pad_kind == "thru_hole":
            selected = "thermal"
        elif pad.pad_kind in {"smd", "connect"}:
            selected = "solid"
        else:
            _fail("THT-only policy cannot be resolved for this pad kind")
    if selected not in {"none", "thermal", "solid"}:
        _fail("connection policy did not resolve to a concrete mode")
    return layer_mode, pad_mode, footprint_mode, zone_mode, resolved_by, selected


def build_zone_pad_connection_evidence(
    source_geometry: DesignIRV2 | Mapping[str, Any],
    cancel_check: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    design, payload = _design(source_geometry)
    design_digest, serialized_bytes = _canonical_digest_and_size(payload)
    # Keep this defensive check at the admission boundary as well; the helper
    # normally fails early while streaming.
    if serialized_bytes > MAX_SERIALIZED_BYTES:
        _fail("DesignIR v2 exceeds the 128 MiB connection-evidence input limit")
    pads = list(design.pads)
    if any(item.filled_copper_state == "outline_fallback" for item in design.zones):
        _fail("outline-fallback zones cannot produce source-filled connection evidence")
    zones = [item for item in design.zones if item.filled_copper_state == "source_filled"]
    if len(pads) > MAX_PADS or len(zones) > MAX_SOURCE_FILLED_ZONES:
        _fail("connection-evidence source counts exceed bounded limits")
    legacy = design.to_v1()
    raw_pads = {str(item.get("id")): item for item in legacy.pads if isinstance(item, Mapping)}
    raw_zones = {str(item.get("id")): item for item in legacy.zones if isinstance(item, Mapping)}
    components = {item.id: item for item in design.components}
    records = []
    work_steps = 0
    from .hybrid_mesh import (
        _normalize_filled_zone_polygon, _pad_boundary_polygon, _point, _segments,
    )
    zone_geometry = {}
    for zone in zones:
        raw_zone = raw_zones.get(zone.source_id or zone.id)
        if raw_zone is None or not zone.source_zone_id or not zone.filled_copper_id:
            _fail(f"zone {zone.id!r} lacks source-filled identity or solver projection")
        polygon = _normalize_filled_zone_polygon([_point(value) for value in raw_zone.get("points", [])])
        if len(polygon) < 3:
            _fail(f"zone {zone.id!r} has no observable source-filled polygon")
        zone_geometry[zone.id] = (
            polygon,
            (min(x for x, _ in polygon), min(y for _, y in polygon), max(x for x, _ in polygon), max(y for _, y in polygon)),
            content_digest([[x, y] for x, y in polygon]),
            [
                (start, end, (min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])))
                for start, end in _segments(polygon)
            ],
        )

    for pad in pads:
        raw_pad = raw_pads.get(pad.source_id or pad.id)
        if raw_pad is None:
            _fail(f"pad {pad.id!r} has no solver projection for contact observation")
        raw_layers = {str(value).strip('"') for value in raw_pad.get("layers", [])}
        pad_boundary = None
        try:
            candidate_boundary = _pad_boundary_polygon(dict(raw_pad))
            if len(candidate_boundary) >= 3:
                pad_boundary = candidate_boundary
        except (TypeError, ValueError, ArithmeticError):
            pass
        pad_bounds = (
            (min(x for x, _ in pad_boundary), min(y for _, y in pad_boundary),
             max(x for x, _ in pad_boundary), max(y for _, y in pad_boundary))
            if pad_boundary else None
        )
        for zone in zones:
            work_steps += 1
            if work_steps > MAX_WORK_STEPS:
                _fail("connection-evidence work exceeds the bounded step limit")
            if work_steps % 1024 == 0:
                _cancel(cancel_check)
            if pad.net_id != zone.net_id:
                continue
            shared_layers = [layer for layer in zone.layer_ids if layer in pad.layer_ids or "*.Cu" in raw_layers]
            for layer_id in shared_layers:
                if pad.pad_kind not in {"smd", "thru_hole", "connect"}:
                    _fail("a candidate connection has an unsupported pad kind")
                if len(records) >= MAX_RECORDS:
                    _fail("connection-evidence record count exceeds the bounded limit")
                polygon, zone_bounds, geometry_digest, zone_edges = zone_geometry[zone.id]
                component = components.get(pad.component_id)
                layer_mode, pad_mode, footprint_mode, zone_mode, resolved_by, resolved_mode = _resolve_mode(
                    pad, component, zone, layer_id,
                )
                observation = "unsupported"
                reason = "pad_geometry_unsupported"
                custom = raw_pad.get("custom_geometry")
                custom_unsupported = (
                    str(raw_pad.get("shape", "")).lower() == "custom"
                    and isinstance(custom, Mapping) and custom.get("status") != "supported"
                )
                if pad_bounds is not None and not custom_unsupported:
                    observation, reason = "no_source_filled_copper_contact", "filled_polygon_disjoint_observed"
                    boxes_overlap = not (
                        pad_bounds[2] < zone_bounds[0] - 1e-6 or zone_bounds[2] < pad_bounds[0] - 1e-6
                        or pad_bounds[3] < zone_bounds[1] - 1e-6 or zone_bounds[3] < pad_bounds[1] - 1e-6
                    )
                    if boxes_overlap:
                        try:
                            overlap = _observes_contact(dict(raw_pad), pad_boundary, pad_bounds, polygon, zone_edges, 1e-6)
                            observation = "source_filled_copper_contact" if overlap else "no_source_filled_copper_contact"
                            reason = "filled_polygon_intersection_observed" if overlap else "filled_polygon_disjoint_observed"
                        except (TypeError, ValueError, ArithmeticError):
                            observation, reason = "unsupported", "exact_intersection_indeterminate"
                record_key = [design.design_id, pad.id, zone.id, layer_id, zone.filled_copper_id]
                records.append({
                    "record_id": content_digest(record_key), "pad_id": pad.id,
                    "component_id": pad.component_id, "pad_kind": pad.pad_kind,
                    "zone_id": zone.id, "source_zone_id": zone.source_zone_id,
                    "filled_copper_id": zone.filled_copper_id, "zone_geometry_state": "source_filled",
                    "layer_id": layer_id, "net_id": pad.net_id, "pad_layer_mode": layer_mode,
                    "pad_mode": pad_mode, "footprint_mode": footprint_mode, "zone_mode": zone_mode,
                    "resolved_by": resolved_by, "resolved_mode": resolved_mode,
                    "through_hole_expansion": "expanded_on_canonical_copper_layer" if pad.pad_kind == "thru_hole" else "not_applicable",
                    "filled_copper_geometry_sha256": geometry_digest,
                    "observation": observation, "reason_code": reason, "topology_state": "not_regenerated",
                })
    _cancel(cancel_check)
    records.sort(key=lambda item: (item["pad_id"], item["zone_id"], item["layer_id"], item["record_id"]))
    counts = {name: sum(item["observation"] == state for item in records) for name, state in (
        ("contact", "source_filled_copper_contact"), ("no_contact", "no_source_filled_copper_contact"), ("unsupported", "unsupported"),
    )}
    unsupported = counts["unsupported"]
    return {
        "contract": CONTRACT,
        "source": {"design_contract": "spike/design-ir/v2", "design_sha256": design_digest, "design_id": design.design_id},
        "records": records,
        "accounting": {
            "status": "unsupported" if unsupported else "complete", "candidate_record_count": len(records),
            "contact_record_count": counts["contact"], "no_contact_record_count": counts["no_contact"],
            "unsupported_record_count": unsupported, "all_candidate_connections_accounted": True,
        },
        "resources": {
            "maximum_pads": MAX_PADS, "maximum_source_filled_zones": MAX_SOURCE_FILLED_ZONES,
            "maximum_records": MAX_RECORDS, "maximum_work_steps": MAX_WORK_STEPS,
            "maximum_serialized_bytes": MAX_SERIALIZED_BYTES, "actual_pads": len(pads),
            "actual_source_filled_zones": len(zones), "actual_records": len(records),
            "actual_work_steps": work_steps, "actual_serialized_bytes": serialized_bytes,
            "cancellation_supported": True,
        },
        "qualification": {
            "state": "source_filled_connection_evidence_only",
            "source_filled_copper_evidence_complete": unsupported == 0,
            "thermal_spoke_topology_regenerated": False, "parametric_zone_refill_performed": False,
            "native_geometric_overlay_verified": False, "field_convergence_performed": False,
            "physics_ready": False, "solver_ready": False,
        },
    }


def validate_zone_pad_connection_evidence(
    report: Mapping[str, Any], *, source_geometry: DesignIRV2 | Mapping[str, Any]
) -> Dict[str, Any]:
    if not isinstance(report, Mapping) or report.get("contract") != CONTRACT:
        _fail("connection evidence has an unsupported contract")
    rebuilt = build_zone_pad_connection_evidence(source_geometry)
    if _canonical_bytes(dict(report)) != _canonical_bytes(rebuilt):
        _fail("connection evidence is stale, incomplete, tampered, or promoted")
    return rebuilt
