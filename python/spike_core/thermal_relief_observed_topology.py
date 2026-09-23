"""Controlled source-filled thermal attachment topology evidence.

The admitted profile proves four source components have spoke-shaped geometry:
one open-edge pad contact each, nominal width through the relief gap, a
contained centerline, and an outer reservoir.  It does not prove KiCad filler
provenance, perform a refill, or create solver geometry.
"""
from __future__ import annotations

import json
import math
from typing import Any, Callable, Dict, Mapping

from .design_ir_v2 import DesignIRV2
from .design_ir_v2_schema import content_digest
from .thermal_relief_boundary_contact import (
    validate_thermal_relief_boundary_contact_evidence,
)
from .thermal_spoke_observed_geometry import (
    GEOMETRY_TOLERANCE_MM, WIDTH_TOLERANCE_MM, admitted_simple_polygon,
    angle_deg, centered_section, components_disjoint, edge_frame,
    modulo_quadrant_delta, outward_normal, segment_is_contained,
)
from .zone_pad_connection_evidence import validate_zone_pad_connection_evidence


CONTRACT = "spike/thermal-relief-observed-topology/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0020"
PROFILE = "four_cardinal_rectilinear_reservoir_v1"
MAX_RECORDS = 65_536
MAX_ATTACHMENTS = 262_144
MAX_COMPONENT_VERTICES = 4_096
MAX_CROSS_SECTIONS = 1_048_576
MAX_WORK_STEPS = 16_777_216
MAX_SERIALIZED_BYTES = 67_108_864


class ThermalReliefObservedTopologyError(ValueError):
    code = ERROR_CODE


def _fail(message: str) -> None:
    raise ThermalReliefObservedTopologyError(f"{ERROR_CODE}: {message}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ThermalReliefObservedTopologyError(
            f"{ERROR_CODE}: topology inputs must contain finite JSON values"
        ) from error


def _design(value: DesignIRV2 | Mapping[str, Any]) -> tuple[DesignIRV2, Dict[str, Any]]:
    if isinstance(value, DesignIRV2):
        design, payload = value, value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
        try:
            design = DesignIRV2.from_dict(payload)
        except (TypeError, ValueError) as error:
            raise ThermalReliefObservedTopologyError(
                f"{ERROR_CODE}: source geometry is not valid DesignIR v2"
            ) from error
    else:
        _fail("source geometry must be DesignIR v2 or a mapping")
    if payload.get("contract") != "spike/design-ir/v2" or not design.design_id:
        _fail("observed topology requires identified DesignIR v2")
    return design, payload


def _effective_dimensions(pad, component, zones) -> tuple[float, float, float]:
    gaps = set()
    widths = set()
    for zone in zones:
        gap = (
            pad.thermal_gap_override_mm if pad.thermal_gap_override_mm is not None
            else component.thermal_gap_override_mm
            if component is not None and component.thermal_gap_override_mm is not None
            else zone.thermal_gap_mm
        )
        width = (
            pad.thermal_spoke_width_override_mm if pad.thermal_spoke_width_override_mm is not None
            else component.thermal_spoke_width_override_mm
            if component is not None and component.thermal_spoke_width_override_mm is not None
            else zone.thermal_spoke_width_mm
        )
        if gap is None or width is None or gap <= 0 or width <= 0:
            _fail("controlled topology requires positive effective gap and width")
        gaps.add(float(gap))
        widths.add(float(width))
    if len(gaps) != 1 or len(widths) != 1:
        _fail("source-fill group has inconsistent effective thermal dimensions")
    angle = pad.thermal_spoke_angle_deg
    if angle is None or not math.isfinite(angle):
        _fail("controlled topology requires an explicit finite pad spoke angle")
    return gaps.pop(), widths.pop(), float(angle)


def build_thermal_relief_observed_topology(
    source_geometry: DesignIRV2 | Mapping[str, Any],
    connection_evidence: Mapping[str, Any],
    boundary_contact_evidence: Mapping[str, Any],
    cancel_check: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    design, payload = _design(source_geometry)
    input_bytes = sum(len(_canonical_bytes(value)) for value in (
        payload, connection_evidence, boundary_contact_evidence,
    ))
    if input_bytes > MAX_SERIALIZED_BYTES:
        _fail("combined topology input exceeds the 64 MiB limit")
    try:
        connection = validate_zone_pad_connection_evidence(
            connection_evidence, source_geometry=design,
        )
        boundary = validate_thermal_relief_boundary_contact_evidence(
            boundary_contact_evidence, source_geometry=design,
            connection_evidence=connection,
        )
    except ValueError as error:
        raise ThermalReliefObservedTopologyError(
            f"{ERROR_CODE}: prerequisite evidence is invalid"
        ) from error

    work_steps = 0
    cross_section_count = 0

    def charge() -> None:
        nonlocal work_steps
        work_steps += 1
        if work_steps > MAX_WORK_STEPS:
            _fail("observed topology work exceeds the bounded step limit")
        if work_steps % 256 == 0 and cancel_check is not None and bool(cancel_check()):
            _fail("observed topology extraction was cancelled")

    if cancel_check is not None and bool(cancel_check()):
        _fail("observed topology extraction was cancelled")

    pads = {item.id: item for item in design.pads}
    components = {item.id: item for item in design.components}
    zones = {item.id: item for item in design.zones}
    legacy = design.to_v1()
    raw_pads = {str(item.get("id")): item for item in legacy.pads if isinstance(item, Mapping)}
    raw_zones = {str(item.get("id")): item for item in legacy.zones if isinstance(item, Mapping)}
    connection_by_id = {item["record_id"]: item for item in connection["records"]}

    candidates: dict[tuple[str, str, str, str], list[Dict[str, Any]]] = {}
    for boundary_record in boundary["records"]:
        connection_record = connection_by_id.get(boundary_record["connection_evidence_id"])
        zone = zones.get(boundary_record["zone_id"])
        if connection_record is None or zone is None:
            _fail("boundary evidence refers to an unknown prerequisite record")
        if not zone.source_fill_group_id:
            if boundary_record["observation"] == "no_source_filled_contact":
                continue
            _fail("contacting candidate lacks complete source-fill group provenance")
        key = (
            boundary_record["pad_id"], zone.source_zone_id,
            boundary_record["layer_id"], zone.source_fill_group_sha256,
        )
        candidates.setdefault(key, []).append(boundary_record)
    candidates = {
        key: records for key, records in candidates.items()
        if any(item["observation"] == "boundary_contact_extracted" for item in records)
    }
    if len(candidates) > MAX_RECORDS:
        _fail("observed topology record count exceeds the bounded limit")

    from .hybrid_mesh import _pad_boundary_polygon

    records = []
    attachment_total = 0
    for (pad_id, source_zone_id, layer_id, group_sha256), candidate_records in sorted(candidates.items()):
        charge()
        pad = pads.get(pad_id)
        raw_pad = raw_pads.get(pad.source_id or pad.id) if pad is not None else None
        if pad is None or raw_pad is None or str(raw_pad.get("shape", "")).lower() != "rect":
            _fail("controlled topology admits rectangular pads only")
        group_zones = sorted((
            zone for zone in design.zones
            if zone.source_zone_id == source_zone_id
            and zone.source_fill_group_sha256 == group_sha256
            and layer_id in zone.layer_ids
        ), key=lambda value: value.source_fill_component_sha256)
        if not group_zones or len(group_zones) != group_zones[0].source_fill_component_count:
            _fail("source-fill group membership is incomplete")
        if any(
            not zone.source_fill_provenance_complete or zone.fill_mode != "solid"
            or zone.holes_mm or zone.source_fill_representation != "flat_polygon_path"
            for zone in group_zones
        ):
            _fail("source-fill group is not an admitted flat solid component set")
        component = components.get(pad.component_id)
        gap_mm, width_mm, configured_angle = _effective_dimensions(pad, component, group_zones)
        pad_boundary = admitted_simple_polygon(
            _pad_boundary_polygon(dict(raw_pad)), maximum_vertices=64,
        )
        polygons = []
        polygon_by_zone = {}
        for zone in group_zones:
            raw_zone = raw_zones.get(zone.source_id or zone.id)
            if raw_zone is None:
                _fail("source-fill component lacks a solver projection")
            polygon = admitted_simple_polygon(
                raw_zone.get("points", []), maximum_vertices=MAX_COMPONENT_VERTICES,
            )
            polygons.append(polygon)
            polygon_by_zone[zone.id] = polygon
        if not components_disjoint(polygons, charge=charge):
            _fail("source-fill components touch or overlap")

        record_by_zone = {item["zone_id"]: item for item in candidate_records}
        if set(record_by_zone) != {zone.id for zone in group_zones}:
            _fail("boundary evidence does not account for every source-fill component")
        contacts = [
            record_by_zone[zone.id] for zone in group_zones
            if record_by_zone[zone.id]["observation"] == "boundary_contact_extracted"
        ]
        if any(record_by_zone[zone.id]["observation"] == "unsupported" for zone in group_zones):
            _fail("boundary evidence contains an unsupported group component")
        if len(contacts) != 4:
            _fail("controlled topology requires exactly four observed attachments")

        attachments = []
        epsilon = min(1e-6, gap_mm / 1000.0, width_mm / 1000.0)
        for contact in contacts:
            charge()
            if contact["boundary_contact_kind"] != "partial" or len(contact["boundary_intervals"]) != 1:
                _fail("each controlled component must have one partial boundary interval")
            interval = contact["boundary_intervals"][0]
            if not (
                interval["start_fraction"] > GEOMETRY_TOLERANCE_MM
                and interval["end_fraction"] < 1.0 - GEOMETRY_TOLERANCE_MM
            ):
                _fail("controlled attachment touches a pad vertex")
            zone = zones[contact["zone_id"]]
            polygon = polygon_by_zone[zone.id]
            edge_index = int(interval["edge_index"])
            _, _, tangent, _ = edge_frame(pad_boundary, edge_index)
            normal = outward_normal(pad_boundary, edge_index)
            start_mm = tuple(float(value) for value in interval["start_mm"])
            end_mm = tuple(float(value) for value in interval["end_mm"])
            center = ((start_mm[0] + end_mm[0]) / 2, (start_mm[1] + end_mm[1]) / 2)
            observed_width = float(interval["length_mm"])
            if abs(observed_width - width_mm) > WIDTH_TOLERANCE_MM:
                _fail("observed attachment width does not match the effective width")
            sections = []
            for offset in (epsilon, gap_mm / 2.0, gap_mm - epsilon, gap_mm + epsilon):
                left, right = centered_section(
                    polygon, center, tangent, normal, offset, charge=charge,
                )
                cross_section_count += 1
                if cross_section_count > MAX_CROSS_SECTIONS:
                    _fail("observed topology cross-section count exceeds its limit")
                sections.append({
                    "offset_mm": offset, "start_tangent_mm": left,
                    "end_tangent_mm": right, "width_mm": right - left,
                })
            for section in sections[:3]:
                if (
                    abs(section["width_mm"] - width_mm) > WIDTH_TOLERANCE_MM
                    or abs(section["start_tangent_mm"] + section["end_tangent_mm"]) > WIDTH_TOLERANCE_MM
                ):
                    _fail("attachment does not preserve centered nominal width through the relief gap")
            if sections[3]["width_mm"] < width_mm * 1.5:
                _fail("attachment does not widen into an outer source-filled reservoir")
            centerline_start = (
                center[0] + normal[0] * epsilon,
                center[1] + normal[1] * epsilon,
            )
            centerline_end = (
                center[0] + normal[0] * (gap_mm + epsilon),
                center[1] + normal[1] * (gap_mm + epsilon),
            )
            if not segment_is_contained(
                polygon, centerline_start, centerline_end, charge=charge,
            ):
                _fail("attachment centerline is not continuously contained through the relief gap")
            observed_angle = angle_deg(normal)
            angle_delta = modulo_quadrant_delta(observed_angle, configured_angle)
            if angle_delta > 1e-6:
                _fail("observed attachment angle does not match the controlled cardinal profile")
            attachment_id = content_digest([
                CONTRACT, pad.id, zone.source_fill_component_sha256,
                edge_index, interval["start_fraction"], interval["end_fraction"],
            ])
            attachments.append({
                "attachment_id": attachment_id, "zone_id": zone.id,
                "filled_copper_id": zone.filled_copper_id,
                "source_fill_component_sha256": zone.source_fill_component_sha256,
                "pad_edge_index": edge_index,
                "boundary_start_fraction": interval["start_fraction"],
                "boundary_end_fraction": interval["end_fraction"],
                "boundary_center_mm": list(center), "outward_unit": list(normal),
                "observed_normal_angle_deg": observed_angle,
                "configured_angle_delta_deg": angle_delta,
                "observed_boundary_width_mm": observed_width,
                "width_delta_mm": observed_width - width_mm,
                "centerline_start_mm": list(centerline_start),
                "centerline_end_mm": list(centerline_end),
                "cross_sections": sections,
                "topology_state": "fixture_conforming_spoke_shaped_attachment",
            })
        attachments.sort(key=lambda value: (
            value["observed_normal_angle_deg"], value["source_fill_component_sha256"],
        ))
        if len({round(value["observed_normal_angle_deg"], 9) for value in attachments}) != 4:
            _fail("controlled topology does not contain four distinct cardinal directions")
        attachment_total += len(attachments)
        if attachment_total > MAX_ATTACHMENTS:
            _fail("observed topology attachment count exceeds its limit")
        records.append({
            "topology_id": content_digest([
                CONTRACT, design.design_id, pad.id, source_zone_id, layer_id,
                group_sha256, PROFILE,
            ]),
            "profile": PROFILE, "pad_id": pad.id,
            "component_id": pad.component_id, "source_zone_id": source_zone_id,
            "layer_id": layer_id, "net_id": pad.net_id,
            "source_fill_group_id": group_zones[0].source_fill_group_id,
            "source_fill_group_sha256": group_sha256,
            "source_fill_component_count": len(group_zones),
            "effective_gap_mm": gap_mm, "effective_width_mm": width_mm,
            "configured_angle_deg": configured_angle,
            "attachment_count": len(attachments), "attachments": attachments,
            "observation": "controlled_fixture_topology_matched",
        })

    if cancel_check is not None and bool(cancel_check()):
        _fail("observed topology extraction was cancelled")
    records.sort(key=lambda value: (
        value["pad_id"], value["source_zone_id"], value["layer_id"], value["topology_id"],
    ))
    status = "complete" if records else "no_candidates"
    return {
        "contract": CONTRACT,
        "source": {
            "design_contract": "spike/design-ir/v2",
            "design_sha256": content_digest(payload), "design_id": design.design_id,
            "connection_contract": connection["contract"],
            "connection_sha256": content_digest(connection),
            "boundary_contact_contract": boundary["contract"],
            "boundary_contact_sha256": content_digest(boundary),
        },
        "records": records,
        "accounting": {
            "status": status, "topology_record_count": len(records),
            "attachment_count": attachment_total,
            "all_controlled_candidates_accounted": True,
        },
        "resources": {
            "maximum_records": MAX_RECORDS, "maximum_attachments": MAX_ATTACHMENTS,
            "maximum_component_vertices": MAX_COMPONENT_VERTICES,
            "maximum_cross_sections": MAX_CROSS_SECTIONS,
            "maximum_work_steps": MAX_WORK_STEPS,
            "maximum_serialized_bytes": MAX_SERIALIZED_BYTES,
            "actual_records": len(records), "actual_attachments": attachment_total,
            "actual_cross_sections": cross_section_count,
            "actual_work_steps": work_steps, "actual_serialized_bytes": input_bytes,
            "cancellation_supported": True,
        },
        "qualification": {
            "state": "controlled_source_fill_observed_spoke_topology_only",
            "controlled_fixture_observed_spoke_topology": bool(records),
            "general_kicad_thermal_spoke_topology_extracted": False,
            "thermal_spoke_topology_regenerated": False,
            "parametric_zone_refill_performed": False,
            "native_geometric_overlay_verified": False, "mesh_ready": False,
            "field_convergence_performed": False, "physics_ready": False,
            "solver_ready": False,
        },
    }


def validate_thermal_relief_observed_topology(
    report: Mapping[str, Any], *, source_geometry: DesignIRV2 | Mapping[str, Any],
    connection_evidence: Mapping[str, Any],
    boundary_contact_evidence: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(report, Mapping) or report.get("contract") != CONTRACT:
        _fail("observed topology has an unsupported contract")
    rebuilt = build_thermal_relief_observed_topology(
        source_geometry, connection_evidence, boundary_contact_evidence,
    )
    if _canonical_bytes(dict(report)) != _canonical_bytes(rebuilt):
        _fail("observed topology is stale, incomplete, tampered, or promoted")
    return rebuilt
