"""Security-conscious IPC-2581 metadata and topology importer.

The adapter deliberately fails closed on XML declarations that can introduce
entities and reports geometry it cannot normalize. It does not invent copper,
stackup, material, or connectivity details that are absent from the source.
"""

from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .contracts import DesignIR, ValidationIssue
from .ipc2581_contour import normalize_contours
from .ipc2581_drill import normalize_physical_drills
from .ipc2581_padstack import normalize_pad_via_geometry
from .ipc2581_polyline import normalize_straight_polylines
from .ipc2581_standard_contour_land import (
    retained_standard_contour_land_empirical_distribution, retained_standard_contour_land_summary,
)
_UNSAFE_XML = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_COPPER_TOKENS = {"conductor", "copper", "signal", "power", "plane", "mixed"}
MAX_IPC2581_SOURCE_BYTES = 2 * 1024 * 1024 * 1024
MAX_IPC2581_XML_ELEMENTS = 1_000_000
MAX_IPC2581_XML_DEPTH = 256
MAX_IPC2581_ATTRIBUTES_PER_ELEMENT = 256
MAX_IPC2581_ATTRIBUTE_CHARS = 1_048_576
MAX_IPC2581_GEOMETRY_PRIMITIVES = 500_000
MAX_IPC2581_GEOMETRY_DIAGNOSTICS = 10_000
_PARSE_CHUNK_BYTES = 1024 * 1024
_UNIT_FACTORS_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "inch": 25.4,
    "inches": 25.4,
    "mil": 0.0254,
    "mils": 0.0254,
}
def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _attributes(element: ET.Element) -> Dict[str, str]:
    return {_local_name(key): str(value) for key, value in element.attrib.items()}


def _value(attributes: Dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = attributes.get(name.lower(), "").strip()
        if value:
            return value
    return default


def _float(attributes: Dict[str, str], *names: str) -> float | None:
    value = _value(attributes, *names)
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _unique(records: Iterable[Dict[str, Any]], key: str) -> list[Dict[str, Any]]:
    result: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        identity = str(record.get(key, ""))
        if identity and identity not in seen:
            seen.add(identity)
            result.append(record)
    return result


def _parse_bounded_xml(payload: bytes) -> ET.Element:
    parser = ET.XMLPullParser(events=("start", "end"))
    root: ET.Element | None = None
    element_count = 0
    depth = 0

    def consume_events() -> None:
        nonlocal root, element_count, depth
        for event, element in parser.read_events():
            if event == "start":
                if root is None:
                    root = element
                element_count += 1
                depth += 1
                if element_count > MAX_IPC2581_XML_ELEMENTS:
                    raise ValueError(
                        f"IPC-2581 XML exceeds the {MAX_IPC2581_XML_ELEMENTS}-element resource limit."
                    )
                if depth > MAX_IPC2581_XML_DEPTH:
                    raise ValueError(
                        f"IPC-2581 XML exceeds the {MAX_IPC2581_XML_DEPTH}-level depth limit."
                    )
                if len(element.attrib) > MAX_IPC2581_ATTRIBUTES_PER_ELEMENT:
                    raise ValueError("IPC-2581 XML element exceeds the attribute-count resource limit.")
                if any(len(str(key)) + len(str(value)) > MAX_IPC2581_ATTRIBUTE_CHARS for key, value in element.attrib.items()):
                    raise ValueError("IPC-2581 XML attribute exceeds the character resource limit.")
            else:
                depth -= 1

    try:
        for offset in range(0, len(payload), _PARSE_CHUNK_BYTES):
            parser.feed(payload[offset:offset + _PARSE_CHUNK_BYTES])
            consume_events()
        parser.close()
        consume_events()
    except ET.ParseError as exc:
        raise ValueError(f"IPC-2581 XML is malformed: {exc}") from exc
    if root is None:
        raise ValueError("IPC-2581 XML is empty.")
    return root


def _unit_factor(root: ET.Element) -> tuple[float | None, str]:
    declarations: list[str] = []
    for element in root.iter():
        tag = _local_name(element.tag)
        attributes = _attributes(element)
        if tag in {"ipc-2581", "logisticheader", "cadheader", "caddata", "step"}:
            declared = _value(attributes, "unit", "units")
            if declared:
                declarations.append(declared)
        if tag == "unit" and element.text and element.text.strip():
            declarations.append(element.text.strip())
    normalized = {item.strip().lower() for item in declarations if item.strip()}
    known = {_UNIT_FACTORS_MM[item] for item in normalized if item in _UNIT_FACTORS_MM}
    unknown = sorted(item for item in normalized if item not in _UNIT_FACTORS_MM)
    if unknown or len(known) != 1:
        return None, ", ".join(sorted(normalized)) or "missing"
    unit = next(item for item in sorted(normalized) if item in _UNIT_FACTORS_MM)
    return next(iter(known)), unit


def _finite_float(attributes: Mapping[str, str], *names: str) -> float | None:
    value = _float(dict(attributes), *names)
    return value if value is not None and math.isfinite(value) else None


def _arc_midpoint(
    start: tuple[float, float], end: tuple[float, float], center: tuple[float, float], clockwise: bool
) -> tuple[float, float] | None:
    start_radius = math.dist(start, center)
    end_radius = math.dist(end, center)
    if start_radius <= 0.0 or end_radius <= 0.0:
        return None
    if not math.isclose(start_radius, end_radius, rel_tol=1e-7, abs_tol=1e-9):
        return None
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    end_angle = math.atan2(end[1] - center[1], end[0] - center[0])
    if clockwise:
        sweep = (start_angle - end_angle) % (2.0 * math.pi)
        mid_angle = start_angle - sweep / 2.0
    else:
        sweep = (end_angle - start_angle) % (2.0 * math.pi)
        mid_angle = start_angle + sweep / 2.0
    if math.isclose(sweep, 0.0, abs_tol=1e-12):
        return None
    return (center[0] + start_radius * math.cos(mid_angle), center[1] + start_radius * math.sin(mid_angle))


def import_ipc2581_design(path: str) -> DesignIR:
    """Import auditable IPC-2581 topology without accepting unsafe XML."""

    source = Path(path)
    source_size = source.stat().st_size
    if source_size > MAX_IPC2581_SOURCE_BYTES:
        raise ValueError(
            f"IPC-2581 source is {source_size} bytes; parser limit is {MAX_IPC2581_SOURCE_BYTES}."
        )
    payload = source.read_bytes()
    if _UNSAFE_XML.search(payload):
        raise ValueError("IPC-2581 input contains a prohibited DOCTYPE or ENTITY declaration.")
    root = _parse_bounded_xml(payload)

    digest = hashlib.sha256(payload).hexdigest()
    root_attributes = _attributes(root)
    revision = _value(root_attributes, "revision", "rev", default="unknown")
    layer_rows: list[Dict[str, Any]] = []
    stackup_rows: list[Dict[str, Any]] = []
    net_rows: list[Dict[str, Any]] = []
    component_rows: list[Dict[str, Any]] = []
    tracks: list[Dict[str, Any]] = []
    arcs: list[Dict[str, Any]] = []
    pads: list[Dict[str, Any]] = []
    vias: list[Dict[str, Any]] = []
    drills: list[Dict[str, Any]] = []
    zones: list[Dict[str, Any]] = []
    diagnostics: list[Dict[str, Any]] = []
    feature_counts: Dict[str, int] = {}
    element_indices: Dict[int, int] = {}

    for index, element in enumerate(root.iter()):
        element_indices[id(element)] = index
        tag = _local_name(element.tag)
        attributes = _attributes(element)
        feature_counts[tag] = feature_counts.get(tag, 0) + 1

        if tag == "layer":
            name = _value(attributes, "name", "layerref", "id", "layer")
            if not name:
                continue
            layer_type = _value(
                attributes, "layertype", "layerfunction", "type", "function", default="documentation"
            )
            layer_rows.append({
                "id": _value(attributes, "id", default=name),
                "name": name,
                "type": layer_type,
                "polarity": _value(attributes, "polarity"),
                "source_index": index,
            })
        elif tag in {"stackuplayer", "stackuplayerref"}:
            name = _value(attributes, "name", "layerref", "layerorgroupref", "layer", "id")
            if not name:
                continue
            thickness = _float(attributes, "thickness", "thicknessvalue")
            row: Dict[str, Any] = {
                "name": name,
                "type": _value(attributes, "type", "layertype", default="unspecified"),
                "material": _value(attributes, "spec", "material", "materialref"),
            }
            if thickness is not None:
                row["source_thickness"] = thickness
            stackup_rows.append(row)
        elif tag in {"logicalnet", "phynet", "net"}:
            name = _value(attributes, "name", "net", "id")
            if name:
                net_rows.append({"id": _value(attributes, "id", default=name), "name": name})
        elif tag == "component":
            reference = _value(attributes, "refdes", "reference", "name", "id")
            if reference:
                component_rows.append({
                    "id": _value(attributes, "id", default=reference),
                    "reference": reference,
                    "value": _value(attributes, "part", "partref", "value"),
                    "package": _value(attributes, "package", "packageref", "footprint"),
                    "layer": _value(attributes, "layerref", "layer"),
                    "rotation": _float(attributes, "rotation") or 0.0,
                    "source_attributes": attributes,
                })

    layers = _unique(layer_rows, "name")
    stackup = _unique(stackup_rows, "name")
    nets = _unique(net_rows, "name")
    components = _unique(component_rows, "reference")
    copper_layers = [
        row["name"] for row in layers
        if any(token in str(row.get("type", "")).lower() for token in _COPPER_TOKENS)
    ]

    layer_lookup: Dict[str, str] = {}
    for row in layers:
        layer_lookup[str(row.get("id", ""))] = str(row["name"])
        layer_lookup[str(row["name"])] = str(row["name"])
    layer_polarities: Dict[str, str] = {}
    for row in layers:
        layer_polarities[str(row.get("id", ""))] = str(row.get("polarity", ""))
        layer_polarities[str(row["name"])] = str(row.get("polarity", ""))
    net_lookup: Dict[str, str] = {}
    for row in nets:
        net_lookup[str(row.get("id", ""))] = str(row.get("id", row["name"]))
        net_lookup[str(row["name"])] = str(row.get("id", row["name"]))

    issues: list[ValidationIssue] = []
    omitted_geometry_diagnostics = 0

    def geometry_issue(code: str, message: str, *, source_id: str = "") -> None:
        nonlocal omitted_geometry_diagnostics
        if len(diagnostics) >= MAX_IPC2581_GEOMETRY_DIAGNOSTICS:
            omitted_geometry_diagnostics += 1
            return
        issues.append(ValidationIssue(
            code=code,
            severity="error",
            message=message,
            path=source_id,
            suggestion="Correct the source reference or primitive; SPIKE does not invent missing conductor semantics.",
        ))
        diagnostics.append({"severity": "error", "code": code, "source_id": source_id, "message": message})

    unit_factor, declared_unit = _unit_factor(root)
    primitive_count = sum(feature_counts.get(tag, 0) for tag in {"line", "arc", "polygon", "polyline", "pad", "hole"})
    if primitive_count > MAX_IPC2581_GEOMETRY_PRIMITIVES:
        raise ValueError(
            f"IPC-2581 source contains {primitive_count} geometry primitives; parser limit is "
            f"{MAX_IPC2581_GEOMETRY_PRIMITIVES}."
        )
    has_physical_dimensions = (
        primitive_count > 0
        or feature_counts.get("padstackpaddef", 0) > 0
        or feature_counts.get("padstackholedef", 0) > 0
        or any("source_thickness" in row for row in stackup)
    )
    if has_physical_dimensions and unit_factor is None:
        geometry_issue(
            "IMPORT_IPC2581_UNITS_UNRESOLVED",
            f"Physical geometry declares unsupported, ambiguous, or missing units ({declared_unit}).",
        )
    if unit_factor is not None:
        for row in stackup:
            if "source_thickness" in row:
                row["thickness_mm"] = float(row["source_thickness"]) * unit_factor

    seen_geometry_ids: set[str] = set()
    normalized_conductor_records = 0
    if unit_factor is not None:
        for layer_feature in (item for item in root.iter() if _local_name(item.tag) == "layerfeature"):
            feature_attributes = _attributes(layer_feature)
            layer_ref = _value(feature_attributes, "layerref", "layer")
            layer_name = layer_lookup.get(layer_ref, "")
            for set_element in (item for item in layer_feature if _local_name(item.tag) == "set"):
                set_attributes = _attributes(set_element)
                net_ref = _value(set_attributes, "netref", "net") or _value(feature_attributes, "netref", "net")
                net_id = net_lookup.get(net_ref, "")
                feature_elements = [item for item in set_element if _local_name(item.tag) == "features"]
                for primitive in (
                    item for features in feature_elements for item in features
                    if _local_name(item.tag) in {"line", "arc"}
                ):
                    primitive_tag = _local_name(primitive.tag)
                    primitive_attributes = _attributes(primitive)
                    source_index = element_indices[id(primitive)]
                    source_id = _value(primitive_attributes, "id", "name", default=f"{primitive_tag}:{source_index}")
                    if source_id in seen_geometry_ids:
                        geometry_issue(
                            "IMPORT_IPC2581_GEOMETRY_ID_DUPLICATE",
                            f"Conductor primitive identity {source_id!r} is duplicated.",
                            source_id=source_id,
                        )
                        continue
                    seen_geometry_ids.add(source_id)
                    if not layer_name:
                        geometry_issue(
                            "IMPORT_IPC2581_LAYER_REF_UNRESOLVED",
                            f"Conductor primitive references unknown layer {layer_ref!r}.",
                            source_id=source_id,
                        )
                        continue
                    if not net_id:
                        geometry_issue(
                            "IMPORT_IPC2581_NET_REF_UNRESOLVED",
                            f"Conductor primitive references unknown net {net_ref!r}.",
                            source_id=source_id,
                        )
                        continue
                    width = _finite_float(primitive_attributes, "width", "linewidth")
                    if width is None or width <= 0.0:
                        geometry_issue(
                            "IMPORT_IPC2581_WIDTH_UNRESOLVED",
                            "Conductor primitive requires an explicit finite positive width.",
                            source_id=source_id,
                        )
                        continue
                    begins = [item for item in primitive if _local_name(item.tag) == "polybegin"]
                    segments = [item for item in primitive if _local_name(item.tag) == "polystepsegment"]
                    curves = [item for item in primitive if _local_name(item.tag) == "polystepcurve"]
                    if len(begins) != 1:
                        geometry_issue(
                            "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                            "Conductor primitive requires exactly one PolyBegin child.",
                            source_id=source_id,
                        )
                        continue
                    begin_attributes = _attributes(begins[0])
                    start = (
                        _finite_float(begin_attributes, "x"),
                        _finite_float(begin_attributes, "y"),
                    )
                    if None in start:
                        geometry_issue(
                            "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                            "PolyBegin coordinates must be explicit finite numbers.",
                            source_id=source_id,
                        )
                        continue
                    start_mm = (float(start[0]) * unit_factor, float(start[1]) * unit_factor)
                    width_mm = width * unit_factor
                    if primitive_tag == "line":
                        if len(segments) != 1 or curves:
                            geometry_issue(
                                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                                "Line requires exactly one PolyStepSegment and no PolyStepCurve.",
                                source_id=source_id,
                            )
                            continue
                        end_attributes = _attributes(segments[0])
                        end = (_finite_float(end_attributes, "x"), _finite_float(end_attributes, "y"))
                        if None in end:
                            geometry_issue(
                                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                                "PolyStepSegment coordinates must be explicit finite numbers.",
                                source_id=source_id,
                            )
                            continue
                        end_mm = (float(end[0]) * unit_factor, float(end[1]) * unit_factor)
                        if start_mm == end_mm:
                            geometry_issue(
                                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                                "Zero-length conductor lines are not normalized.",
                                source_id=source_id,
                            )
                            continue
                        tracks.append({
                            "id": source_id,
                            "layer": layer_name,
                            "net_id": net_id,
                            "start": list(start_mm),
                            "end": list(end_mm),
                            "width_mm": width_mm,
                            "source_index": source_index,
                        })
                        normalized_conductor_records += 1
                    else:
                        if len(curves) != 1 or segments:
                            geometry_issue(
                                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                                "Arc requires exactly one PolyStepCurve and no PolyStepSegment.",
                                source_id=source_id,
                            )
                            continue
                        curve_attributes = _attributes(curves[0])
                        end = (_finite_float(curve_attributes, "x"), _finite_float(curve_attributes, "y"))
                        center = (
                            _finite_float(curve_attributes, "centerx"),
                            _finite_float(curve_attributes, "centery"),
                        )
                        direction = _value(curve_attributes, "clockwise")
                        if None in end or None in center or direction.lower() not in {"true", "false"}:
                            geometry_issue(
                                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                                "PolyStepCurve requires finite end/center coordinates and clockwise=true|false.",
                                source_id=source_id,
                            )
                            continue
                        end_mm = (float(end[0]) * unit_factor, float(end[1]) * unit_factor)
                        center_mm = (float(center[0]) * unit_factor, float(center[1]) * unit_factor)
                        mid_mm = _arc_midpoint(start_mm, end_mm, center_mm, direction.lower() == "true")
                        if mid_mm is None:
                            geometry_issue(
                                "IMPORT_IPC2581_PRIMITIVE_MALFORMED",
                                "Arc endpoints must lie on one non-zero circle and define a non-zero sweep.",
                                source_id=source_id,
                            )
                            continue
                        arcs.append({
                            "id": source_id,
                            "layer": layer_name,
                            "net_id": net_id,
                            "start": list(start_mm),
                            "mid": list(mid_mm),
                            "end": list(end_mm),
                            "width_mm": width_mm,
                            "source_index": source_index,
                        })
                        normalized_conductor_records += 1

    if unit_factor is not None and feature_counts.get("polyline", 0):
        polyline_tracks, normalized_polyline_records = normalize_straight_polylines(
            root,
            unit_factor=unit_factor,
            layer_lookup=layer_lookup,
            net_lookup=net_lookup,
            copper_layers=copper_layers,
            element_indices=element_indices,
            seen_geometry_ids=seen_geometry_ids,
            geometry_issue=geometry_issue,
        )
        tracks.extend(polyline_tracks)
        normalized_conductor_records += normalized_polyline_records

    normalized_contour_records = 0
    retained_negative_contours: list[Dict[str, Any]] = []
    if unit_factor is not None and feature_counts.get("contour", 0):
        zones, normalized_contour_records, retained_negative_contours = normalize_contours(
            root, unit_factor=unit_factor, layer_lookup=layer_lookup,
            layer_polarities=layer_polarities, net_lookup=net_lookup,
            element_indices=element_indices, seen_geometry_ids=seen_geometry_ids,
            geometry_issue=geometry_issue,
        )
        if zones:
            issues.append(ValidationIssue(
                code="IMPORT_IPC2581_ZONE_CURVE_MESHING_PENDING", severity="warning",
                message=f"{len(zones)} exact curved contour zones are retained, but curve-aware solver meshing and ownership are not qualified.",
                suggestion="Keep solver readiness blocked until exact line/arc rings and cutouts pass mesh ownership validation.",
            ))
            diagnostics.append({"severity": "warning", "code": "IMPORT_IPC2581_ZONE_CURVE_MESHING_PENDING", "count": len(zones)})
        if retained_negative_contours:
            issues.append(ValidationIssue(
                code="IMPORT_IPC2581_NEGATIVE_CONTOUR_SEMANTICS_PENDING", severity="warning",
                message=(f"{len(retained_negative_contours)} exact negative-layer contours are retained as source metadata; "
                         "their fill, void, antipad, connectivity, and copper semantics are unresolved."),
                suggestion="Review the negative-layer fabrication semantics before creating topology or solver geometry.",
            ))
            diagnostics.append({
                "severity": "warning", "code": "IMPORT_IPC2581_NEGATIVE_CONTOUR_SEMANTICS_PENDING",
                "count": len(retained_negative_contours),
            })

    normalized_pad_occurrences = 0
    incomplete_padstack_occurrence_groups: list[Dict[str, Any]] = []
    retained_unnetted_padstack_occurrence_groups: list[Dict[str, Any]] = []
    retained_nonregular_padstack_geometry: Dict[str, Any] = {
        "contract": "spike/retained-padstack-geometry/v1", "user_primitives": [], "occurrences": [],
    }
    retained_standard_contour_land_geometry: Dict[str, Any] = {
        "contract": "spike/retained-standard-contour-land-geometry/v2",
        "semantic_state": "unapplied_normative_semantics_missing", "projection": "forbidden",
        "definitions": [], "padstacks": [], "occurrences": [],
    }
    if unit_factor is not None and feature_counts.get("pad", 0):
        (
            pads, vias, normalized_pad_occurrences, incomplete_padstack_occurrence_groups,
            retained_unnetted_padstack_occurrence_groups, retained_nonregular_padstack_geometry,
            retained_standard_contour_land_geometry,
        ) = normalize_pad_via_geometry(
            root,
            unit_factor=unit_factor,
            layer_lookup=layer_lookup,
            net_lookup=net_lookup,
            components=components,
            copper_layers=copper_layers,
            layer_polarities=layer_polarities,
            element_indices=element_indices,
            geometry_issue=geometry_issue,
        )
    normalized_retained_unnetted_pad_occurrences = sum(
        int(item.get("occurrence_count", 0))
        for item in retained_unnetted_padstack_occurrence_groups
    )
    if retained_unnetted_padstack_occurrence_groups:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_UNNETTED_PADSTACK_SEMANTICS_PENDING", severity="warning",
            message=(f"{normalized_retained_unnetted_pad_occurrences} exact padstack occurrences in "
                     f"{len(retained_unnetted_padstack_occurrence_groups)} complete groups have no native net identity "
                     "and are retained as source metadata only."),
            suggestion="Assign reviewed native net and ownership semantics before creating pads, vias, barrels, connectivity, or solver geometry.",
        ))
        diagnostics.append({
            "severity": "warning", "code": "IMPORT_IPC2581_UNNETTED_PADSTACK_SEMANTICS_PENDING",
            "groups": len(retained_unnetted_padstack_occurrence_groups),
            "count": normalized_retained_unnetted_pad_occurrences,
        })
    normalized_retained_nonregular_padstack_occurrences = len(retained_nonregular_padstack_geometry["occurrences"])
    (normalized_retained_standard_contour_land_occurrences,
     normalized_retained_standard_contour_land_declared_layer_matches,
     normalized_retained_standard_contour_land_declared_layer_mismatches,
     contour_land_issue, contour_land_diagnostic) = retained_standard_contour_land_summary(retained_standard_contour_land_geometry)
    contour_land_empirical_distribution = retained_standard_contour_land_empirical_distribution(
        retained_standard_contour_land_geometry,
    )
    if normalized_retained_standard_contour_land_occurrences:
        issues.append(ValidationIssue(**contour_land_issue))
        diagnostics.append(contour_land_diagnostic)
    heterogeneous_land_profile_records = 0
    for entity in [*pads, *vias]:
        profiles = entity.get("land_profiles", [])
        signatures = {
            (str(item.get("shape", "")), tuple(item.get("size_mm", [])), tuple(item.get("offset_mm", [0.0, 0.0])))
            for item in profiles if isinstance(item, Mapping)
        }
        if len(signatures) > 1:
            heterogeneous_land_profile_records += len(profiles)
    if heterogeneous_land_profile_records:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_LAND_PROFILE_MESHING_PENDING", severity="warning",
            message=(f"{heterogeneous_land_profile_records} exact per-layer heterogeneous copper-land profiles are retained, "
                     "but layer-profile-aware meshing and ownership are not qualified."),
            suggestion="Keep solver readiness blocked until every layer profile passes mesh ownership validation.",
        ))
        diagnostics.append({"severity": "warning", "code": "IMPORT_IPC2581_LAND_PROFILE_MESHING_PENDING",
                            "count": heterogeneous_land_profile_records})

    normalized_drill_records = 0
    unresolved_drill_owners = 0
    if unit_factor is not None and feature_counts.get("hole", 0):
        drills, normalized_drill_records, unresolved_drill_owners = normalize_physical_drills(
            root, unit_factor=unit_factor, layer_lookup=layer_lookup, net_lookup=net_lookup,
            components=components, pads=pads, vias=vias, element_indices=element_indices,
            geometry_issue=geometry_issue,
        )
        if unresolved_drill_owners:
            issues.append(ValidationIssue(
                code="IMPORT_IPC2581_DRILL_OWNER_UNRESOLVED", severity="warning",
                message=f"{unresolved_drill_owners} physical drill records have no exact typed pad/via owner; they are retained as manufacturing geometry only.",
                suggestion="Resolve the corresponding padstack occurrences before using these drills in electrical or void meshing.",
            ))
            diagnostics.append({"severity": "warning", "code": "IMPORT_IPC2581_DRILL_OWNER_UNRESOLVED", "count": unresolved_drill_owners})

    if omitted_geometry_diagnostics:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_DIAGNOSTICS_TRUNCATED",
            severity="error",
            message=(
                f"{omitted_geometry_diagnostics} additional geometry diagnostics were omitted after the "
                f"{MAX_IPC2581_GEOMETRY_DIAGNOSTICS}-record safety limit."
            ),
            suggestion="Resolve the first reported source errors before importing the file again.",
        ))
        diagnostics.append({
            "severity": "error",
            "code": "IMPORT_IPC2581_DIAGNOSTICS_TRUNCATED",
            "omitted": omitted_geometry_diagnostics,
        })

    if not layers:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_NO_LAYERS",
            severity="error",
            message="No IPC-2581 layer declarations were normalized.",
            suggestion="Export an IPC-2581 design containing layer and stackup sections.",
        ))
    if not copper_layers:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_COPPER_UNRESOLVED",
            severity="error",
            message="The imported layer declarations do not identify conductor layers.",
            suggestion="Verify that the IPC-2581 export includes conductor layer functions.",
        ))
    if not nets:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_NETS_MISSING",
            severity="warning",
            message="No logical or physical nets were normalized.",
            suggestion="Include logical-net or physical-net data in the IPC-2581 export.",
        ))

    geometry_tags = {"line", "arc", "polygon", "polyline", "pad", "hole"}
    source_geometry_count = sum(feature_counts.get(tag, 0) for tag in geometry_tags)

    # ``feature_counts`` intentionally remains a whole-document inventory for
    # parser bounds and diagnostics.  It is not, however, an honest solver
    # coverage denominator: IPC files commonly carry Pad artwork on solder
    # mask/paste layers and Polygon constructs in dictionaries and packages.
    # Count only copper-layer Pad/Polyline occurrences and direct copper feature
    # Contours as candidate conductor records.  A Contour is one record even
    # though it contains a Polygon child; all other Polygon nodes are outside
    # the importer traversal and are reported separately rather than called
    # unsupported copper geometry.
    non_copper_pad_occurrences = 0
    non_copper_polyline_records = 0
    scoped_copper_polylines = 0
    scoped_contours = 0
    for layer_feature in (item for item in root.iter() if _local_name(item.tag) == "layerfeature"):
        layer_ref = _value(_attributes(layer_feature), "layerref", "layer")
        is_copper_layer = layer_lookup.get(layer_ref, "") in copper_layers
        for set_element in (item for item in layer_feature if _local_name(item.tag) == "set"):
            if not is_copper_layer:
                non_copper_pad_occurrences += sum(
                    1 for item in set_element.iter() if _local_name(item.tag) == "pad"
                )
                for features in (item for item in set_element if _local_name(item.tag) == "features"):
                    non_copper_polyline_records += sum(
                        1 for item in features if _local_name(item.tag) == "polyline"
                    )
                continue
            for features in (item for item in set_element if _local_name(item.tag) == "features"):
                scoped_copper_polylines += sum(
                    1 for item in features if _local_name(item.tag) == "polyline"
                )
                scoped_contours += sum(
                    1 for item in features if _local_name(item.tag) == "contour"
                )
    out_of_scope_polygon_constructs = max(0, feature_counts.get("polygon", 0) - scoped_contours)
    out_of_scope_polyline_constructs = max(
        0, feature_counts.get("polyline", 0) - non_copper_polyline_records - scoped_copper_polylines,
    )
    geometry_count = (
        source_geometry_count
        - non_copper_pad_occurrences
        - non_copper_polyline_records
        - out_of_scope_polyline_constructs
        - feature_counts.get("polygon", 0)
        + scoped_contours
    )
    normalized_retained_negative_contours = len(retained_negative_contours)
    normalized_geometry_count = (
        len(tracks) + len(arcs) + len(zones) + len(pads) + len(vias) + len(drills)
        + normalized_retained_nonregular_padstack_occurrences
        + normalized_retained_unnetted_pad_occurrences + normalized_retained_negative_contours
    )
    normalized_geometry_records = (
        normalized_conductor_records + normalized_contour_records + normalized_pad_occurrences + normalized_drill_records
        + normalized_retained_nonregular_padstack_occurrences + normalized_retained_negative_contours
    )
    unsupported_geometry_count = max(0, geometry_count - normalized_geometry_records)
    if unsupported_geometry_count:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_GEOMETRY_PENDING",
            severity="warning",
            message=(
                f"The source contains {unsupported_geometry_count} unsupported or unresolved geometry records. "
                "This adapter revision normalizes explicit line/arc conductors, straight one-or-more-step "
                "ROUND positive-width LineDescRef paths, lossless solid positive contour rings, and a strict standard padstack subset."
            ),
            suggestion="Do not run geometry solvers until the import report marks conductor geometry ready.",
        ))
        diagnostics.append({
            "severity": "warning",
            "code": "IMPORT_IPC2581_GEOMETRY_PENDING",
            "count": unsupported_geometry_count,
        })

    stackup_names = {str(row.get("name", "")) for row in stackup}
    missing_stackup = [name for name in copper_layers if name not in stackup_names]
    if missing_stackup:
        issues.append(ValidationIssue(
            code="IMPORT_IPC2581_STACKUP_INCOMPLETE",
            severity="warning",
            message=f"No stackup row was found for: {', '.join(missing_stackup)}.",
            suggestion="Provide conductor thickness and dielectric material data before AC, SI, or EMI analysis.",
        ))

    return DesignIR(
        design_id=f"ipc2581-{digest[:24]}",
        name=_value(root_attributes, "name", "job", default=source.stem),
        source_format="ipc-2581",
        source_path=str(source.resolve()),
        units="mm",
        layers=layers,
        nets=nets,
        tracks=tracks,
        vias=vias,
        pads=pads,
        zones=zones,
        components=components,
        stackup=stackup,
        issues=issues,
        metadata={
            "source_sha256": digest,
            "ipc2581_revision": revision,
            "parser_revision": "ipc2581-conductor-primitives-v13",
            "parser_diagnostics": diagnostics,
            "omitted_geometry_diagnostics": omitted_geometry_diagnostics,
            "feature_counts": feature_counts,
            "ipc2581_incomplete_pad_occurrence_groups": incomplete_padstack_occurrence_groups,
            **({"ipc2581_retained_unnetted_padstack_occurrence_groups": {
                "contract": "spike/retained-unnetted-padstack-groups/v1",
                "groups": retained_unnetted_padstack_occurrence_groups,
            }} if retained_unnetted_padstack_occurrence_groups else {}),
            **({"ipc2581_retained_nonregular_padstack_geometry": retained_nonregular_padstack_geometry}
               if normalized_retained_nonregular_padstack_occurrences else {}),
            **({"ipc2581_retained_standard_contour_land_geometry": retained_standard_contour_land_geometry}
               if normalized_retained_standard_contour_land_occurrences else {}),
            **({"ipc2581_retained_negative_contours": {
                "contract": "spike/retained-negative-contours/v1",
                "records": retained_negative_contours,
            }} if retained_negative_contours else {}),
            "geometry_normalized": bool(normalized_geometry_count) and not unsupported_geometry_count,
            "geometry_solver_ready": (
                not zones and not heterogeneous_land_profile_records and not incomplete_padstack_occurrence_groups
                and not normalized_retained_nonregular_padstack_occurrences
                and not normalized_retained_unnetted_pad_occurrences
                and not normalized_retained_standard_contour_land_occurrences
                and not normalized_retained_negative_contours
            ),
            "geometry_coverage": {
                "declared": geometry_count,
                "source_geometry_total": source_geometry_count,
                "excluded_non_copper_pad_occurrences": non_copper_pad_occurrences,
                "excluded_non_copper_polyline_records": non_copper_polyline_records,
                "excluded_out_of_scope_polyline_constructs": out_of_scope_polyline_constructs,
                "excluded_out_of_scope_polygon_constructs": out_of_scope_polygon_constructs,
                "scoped_contours": scoped_contours,
                "normalized_tracks": len(tracks),
                "normalized_arcs": len(arcs),
                "normalized_zones": len(zones),
                "normalized_pads": len(pads),
                "normalized_vias": len(vias),
                "normalized_drills": len(drills),
                "normalized_heterogeneous_land_profiles": heterogeneous_land_profile_records,
                "normalized_retained_incomplete_pad_occurrences": sum(
                    int(item.get("occurrence_count", 0)) for item in incomplete_padstack_occurrence_groups
                ),
                "normalized_retained_unnetted_pad_occurrences": normalized_retained_unnetted_pad_occurrences,
                "normalized_retained_nonregular_padstack_occurrences": normalized_retained_nonregular_padstack_occurrences,
                "normalized_retained_standard_contour_land_occurrences": normalized_retained_standard_contour_land_occurrences,
                "normalized_retained_standard_contour_land_declared_layer_matches": normalized_retained_standard_contour_land_declared_layer_matches,
                "normalized_retained_standard_contour_land_declared_layer_mismatches": normalized_retained_standard_contour_land_declared_layer_mismatches,
                "retained_standard_contour_land_empirical_distribution": contour_land_empirical_distribution,
                "normalized_retained_negative_contours": normalized_retained_negative_contours,
                "normalized_source_records": normalized_geometry_records,
                "unsupported_or_unresolved": unsupported_geometry_count,
            },
            "arcs": arcs,
            "manufacturing_drills": drills,
            "source_units": declared_unit,
            "physical_units_resolved": unit_factor is not None or not has_physical_dimensions,
            "stackup_missing_copper_layers": missing_stackup,
        },
    )
