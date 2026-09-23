"""Bounded source-filled contact observations on polygonal pad boundaries.

This evidence is a prerequisite to thermal-spoke topology extraction.  It
observes boundary intervals in retained source copper and never labels an
interval as a spoke, refills a zone, changes a mesh, or promotes physics.
"""
from __future__ import annotations

import json
import math
from typing import Any, Callable, Dict, Mapping

from .design_ir_v2 import DesignIRV2
from .design_ir_v2_schema import content_digest
from .zone_pad_connection_evidence import validate_zone_pad_connection_evidence


CONTRACT = "spike/thermal-relief-boundary-contact-evidence/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0019"
MAX_RECORDS = 262_144
MAX_INTERVALS = 1_048_576
MAX_WORK_STEPS = 16_777_216
MAX_SERIALIZED_BYTES = 67_108_864
TOLERANCE_MM = 1e-9


class ThermalReliefBoundaryContactError(ValueError):
    code = ERROR_CODE


def _fail(message: str) -> None:
    raise ThermalReliefBoundaryContactError(f"{ERROR_CODE}: {message}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ThermalReliefBoundaryContactError(
            f"{ERROR_CODE}: inputs must contain finite JSON values"
        ) from error


def _design(value: DesignIRV2 | Mapping[str, Any]) -> tuple[DesignIRV2, Dict[str, Any]]:
    if isinstance(value, DesignIRV2):
        design, payload = value, value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
        try:
            design = DesignIRV2.from_dict(payload)
        except (TypeError, ValueError) as error:
            raise ThermalReliefBoundaryContactError(
                f"{ERROR_CODE}: source geometry is not valid DesignIR v2"
            ) from error
    else:
        _fail("source geometry must be DesignIR v2 or a mapping")
    if payload.get("contract") != "spike/design-ir/v2" or not design.design_id:
        _fail("boundary contact evidence requires identified DesignIR v2")
    return design, payload


def _cancel(cancel_check: Callable[[], Any] | None) -> None:
    if cancel_check is not None and bool(cancel_check()):
        _fail("thermal boundary-contact observation was cancelled")


def _fraction(point, start, end) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    denominator = dx * dx + dy * dy
    if denominator <= 0:
        _fail("pad boundary contains a zero-length edge")
    return max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / denominator))


def _boundary_intervals(
    pad_boundary, polygon, *, charge: Callable[[], None],
) -> list[Dict[str, Any]]:
    from .hybrid_mesh import _point_in_polygon, _segment_intersection_points, _segments

    zone_edges = list(_segments(polygon))
    intervals = []
    for edge_index, (start, end) in enumerate(_segments(pad_boundary)):
        cuts = [0.0, 1.0]
        for zone_start, zone_end in zone_edges:
            charge()
            for point in _segment_intersection_points(
                start, end, zone_start, zone_end, TOLERANCE_MM,
            ):
                cuts.append(_fraction(point, start, end))
        ordered = []
        for value in sorted(cuts):
            if not ordered or abs(value - ordered[-1]) > 1e-10:
                ordered.append(value)
        edge_length = math.hypot(end[0] - start[0], end[1] - start[1])
        for left, right in zip(ordered, ordered[1:]):
            if right - left <= 1e-10:
                continue
            middle = (left + right) / 2.0
            midpoint = (
                start[0] + (end[0] - start[0]) * middle,
                start[1] + (end[1] - start[1]) * middle,
            )
            charge()
            if not _point_in_polygon(midpoint, polygon, TOLERANCE_MM):
                continue
            interval_start = (
                start[0] + (end[0] - start[0]) * left,
                start[1] + (end[1] - start[1]) * left,
            )
            interval_end = (
                start[0] + (end[0] - start[0]) * right,
                start[1] + (end[1] - start[1]) * right,
            )
            intervals.append({
                "edge_index": edge_index, "start_fraction": left,
                "end_fraction": right, "start_mm": list(interval_start),
                "end_mm": list(interval_end), "length_mm": edge_length * (right - left),
            })
    return intervals


def build_thermal_relief_boundary_contact_evidence(
    source_geometry: DesignIRV2 | Mapping[str, Any],
    connection_evidence: Mapping[str, Any],
    cancel_check: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    design, payload = _design(source_geometry)
    input_bytes = len(_canonical_bytes(payload)) + len(_canonical_bytes(connection_evidence))
    if input_bytes > MAX_SERIALIZED_BYTES:
        _fail("combined evidence input exceeds the 64 MiB limit")
    try:
        connection = validate_zone_pad_connection_evidence(
            connection_evidence, source_geometry=design,
        )
    except ValueError as error:
        raise ThermalReliefBoundaryContactError(
            f"{ERROR_CODE}: connection evidence is invalid"
        ) from error
    if connection["source"]["design_sha256"] != content_digest(payload):
        _fail("connection evidence is not bound to the supplied design")

    pads = {item.id: item for item in design.pads}
    zones = {item.id: item for item in design.zones}
    legacy = design.to_v1()
    raw_pads = {str(item.get("id")): item for item in legacy.pads if isinstance(item, Mapping)}
    raw_zones = {str(item.get("id")): item for item in legacy.zones if isinstance(item, Mapping)}
    records = []
    interval_count = 0
    work_steps = 0

    def charge() -> None:
        nonlocal work_steps
        work_steps += 1
        if work_steps > MAX_WORK_STEPS:
            _fail("thermal boundary-contact work exceeds the bounded step limit")
        if work_steps % 256 == 0:
            _cancel(cancel_check)

    from .hybrid_mesh import _normalize_filled_zone_polygon, _pad_boundary_polygon, _point

    thermal_records = [item for item in connection["records"] if item["resolved_mode"] == "thermal"]
    if len(thermal_records) > MAX_RECORDS:
        _fail("thermal boundary-contact record count exceeds the bounded limit")
    for item in thermal_records:
        charge()
        pad = pads.get(item["pad_id"])
        zone = zones.get(item["zone_id"])
        if pad is None or zone is None:
            _fail("connection evidence refers to an unknown pad or zone")
        raw_pad = raw_pads.get(pad.source_id or pad.id)
        raw_zone = raw_zones.get(zone.source_id or zone.id)
        if raw_pad is None or raw_zone is None:
            _fail("connection evidence lacks a solver projection")

        observation = "unsupported"
        reason = "source_fill_provenance_incomplete"
        contact_kind = "unsupported"
        intervals = []
        if item["observation"] == "no_source_filled_copper_contact":
            observation, reason, contact_kind = (
                "no_source_filled_contact", "source_filled_disjoint", "none",
            )
        elif item["observation"] == "source_filled_copper_contact":
            if zone.source_fill_provenance_complete:
                try:
                    pad_boundary = _pad_boundary_polygon(dict(raw_pad))
                    polygon = _normalize_filled_zone_polygon([
                        _point(value) for value in raw_zone.get("points", [])
                    ])
                    if len(pad_boundary) < 3 or len(polygon) < 3:
                        reason = "pad_boundary_unsupported"
                    else:
                        intervals = _boundary_intervals(pad_boundary, polygon, charge=charge)
                        if intervals:
                            interval_count += len(intervals)
                            if interval_count > MAX_INTERVALS:
                                _fail("thermal boundary-contact interval count exceeds its limit")
                            perimeter = sum(math.hypot(
                                pad_boundary[(index + 1) % len(pad_boundary)][0] - point[0],
                                pad_boundary[(index + 1) % len(pad_boundary)][1] - point[1],
                            ) for index, point in enumerate(pad_boundary))
                            covered = sum(value["length_mm"] for value in intervals)
                            observation, reason = "boundary_contact_extracted", "polygonal_pad_boundary_observed"
                            contact_kind = "full" if math.isclose(covered, perimeter, rel_tol=0.0, abs_tol=1e-7) else "partial"
                        else:
                            reason = "interior_contact_without_boundary_crossing"
                except (TypeError, ValueError, ArithmeticError):
                    reason = "pad_boundary_unsupported"
        records.append({
            "record_id": content_digest([CONTRACT, item["record_id"]]),
            "connection_evidence_id": item["record_id"], "pad_id": pad.id,
            "zone_id": zone.id, "filled_copper_id": zone.filled_copper_id,
            "layer_id": item["layer_id"], "net_id": item["net_id"],
            "resolved_mode": "thermal", "source_fill_group_id": zone.source_fill_group_id,
            "source_fill_group_sha256": zone.source_fill_group_sha256,
            "source_fill_component_sha256": zone.source_fill_component_sha256,
            "observation": observation, "reason_code": reason,
            "boundary_contact_kind": contact_kind, "boundary_intervals": intervals,
        })
    _cancel(cancel_check)
    records.sort(key=lambda value: (value["pad_id"], value["zone_id"], value["layer_id"], value["record_id"]))
    counts = {
        name: sum(item["observation"] == state for item in records)
        for name, state in (
            ("extracted", "boundary_contact_extracted"),
            ("no_contact", "no_source_filled_contact"), ("unsupported", "unsupported"),
        )
    }
    return {
        "contract": CONTRACT,
        "source": {
            "design_contract": "spike/design-ir/v2", "design_sha256": content_digest(payload),
            "design_id": design.design_id,
            "connection_contract": connection["contract"],
            "connection_sha256": content_digest(connection),
        },
        "records": records,
        "accounting": {
            "status": "unsupported" if counts["unsupported"] else "complete",
            "record_count": len(records), "extracted_record_count": counts["extracted"],
            "no_contact_record_count": counts["no_contact"],
            "unsupported_record_count": counts["unsupported"],
            "all_thermal_candidates_accounted": True,
        },
        "resources": {
            "maximum_records": MAX_RECORDS, "maximum_intervals": MAX_INTERVALS,
            "maximum_work_steps": MAX_WORK_STEPS,
            "maximum_serialized_bytes": MAX_SERIALIZED_BYTES,
            "actual_records": len(records), "actual_intervals": interval_count,
            "actual_work_steps": work_steps, "actual_serialized_bytes": input_bytes,
            "cancellation_supported": True,
        },
        "qualification": {
            "state": "source_filled_pad_boundary_contact_only",
            "boundary_contact_evidence_complete": counts["unsupported"] == 0,
            "thermal_spoke_topology_extracted": False,
            "thermal_spoke_topology_regenerated": False,
            "parametric_zone_refill_performed": False, "mesh_ready": False,
            "field_convergence_performed": False, "physics_ready": False,
            "solver_ready": False,
        },
    }


def validate_thermal_relief_boundary_contact_evidence(
    report: Mapping[str, Any], *, source_geometry: DesignIRV2 | Mapping[str, Any],
    connection_evidence: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(report, Mapping) or report.get("contract") != CONTRACT:
        _fail("thermal boundary-contact evidence has an unsupported contract")
    rebuilt = build_thermal_relief_boundary_contact_evidence(
        source_geometry, connection_evidence,
    )
    if _canonical_bytes(dict(report)) != _canonical_bytes(rebuilt):
        _fail("thermal boundary-contact evidence is stale, incomplete, tampered, or promoted")
    return rebuilt
