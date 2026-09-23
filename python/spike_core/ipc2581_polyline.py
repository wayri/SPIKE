"""Strict IPC-2581 line-style and straight-polyline normalization."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, Mapping


GeometryIssue = Callable[..., None]
_UNIT_FACTORS_MM = {"mm": 1.0, "millimeter": 1.0, "millimeters": 1.0, "inch": 25.4, "inches": 25.4, "mil": 0.0254, "mils": 0.0254}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _attributes(element: ET.Element) -> Dict[str, str]:
    return {_local_name(key): str(value) for key, value in element.attrib.items()}


def _value(attributes: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(attributes.get(name.lower(), "")).strip()
        if value:
            return value
    return ""


def _finite_float(attributes: Mapping[str, str], name: str) -> float | None:
    value = _value(attributes, name)
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def normalize_straight_polylines(
    root: ET.Element,
    *,
    unit_factor: float,
    layer_lookup: Mapping[str, str],
    net_lookup: Mapping[str, str],
    copper_layers: list[str],
    element_indices: Mapping[int, int],
    seen_geometry_ids: set[str],
    geometry_issue: GeometryIssue,
) -> tuple[list[Dict[str, Any]], int]:
    """Normalize straight ROUND polylines as ordered, lossless conductor paths."""

    line_widths: Dict[str, float] = {}
    duplicate_styles: set[str] = set()
    for dictionary in (item for item in root.iter() if _local_name(item.tag) == "dictionarylinedesc"):
        dictionary_unit = _value(_attributes(dictionary), "units", "unit").lower()
        dictionary_factor = _UNIT_FACTORS_MM.get(dictionary_unit)
        # IPC-2581C requires referenced line dictionaries to use the Ecad
        # section's units.  Converting a non-conforming mixed-unit file would
        # hide a standards error, so the strict path rejects it.
        if dictionary_factor is None or not math.isclose(dictionary_factor, unit_factor, rel_tol=0.0, abs_tol=1e-15):
            continue
        for entry in (item for item in dictionary if _local_name(item.tag) == "entrylinedesc"):
            entry_id = _value(_attributes(entry), "id", "name")
            descriptions = [child for child in entry if _local_name(child.tag) == "linedesc"]
            width: float | None = None
            if len(descriptions) == 1:
                attributes = _attributes(descriptions[0])
                raw_width = _finite_float(attributes, "linewidth")
                line_end = _value(attributes, "lineend").upper()
                if raw_width is not None and raw_width > 0.0 and line_end == "ROUND":
                    width = raw_width * dictionary_factor
            if not entry_id or width is None:
                continue
            if entry_id in line_widths:
                duplicate_styles.add(entry_id)
                line_widths.pop(entry_id, None)
            elif entry_id not in duplicate_styles:
                line_widths[entry_id] = width

    tracks: list[Dict[str, Any]] = []
    normalized_records = 0
    for layer_feature in (item for item in root.iter() if _local_name(item.tag) == "layerfeature"):
        feature_attributes = _attributes(layer_feature)
        layer_ref = _value(feature_attributes, "layerref", "layer")
        layer_name = layer_lookup.get(layer_ref, "")
        if layer_name and layer_name not in copper_layers:
            continue
        for set_element in (item for item in layer_feature if _local_name(item.tag) == "set"):
            set_attributes = _attributes(set_element)
            net_ref = _value(set_attributes, "netref", "net") or _value(feature_attributes, "netref", "net")
            net_id = net_lookup.get(net_ref, "")
            features = [item for item in set_element if _local_name(item.tag) == "features"]
            for polyline in (
                item for feature in features for item in feature if _local_name(item.tag) == "polyline"
            ):
                source_index = element_indices[id(polyline)]
                attributes = _attributes(polyline)
                source_id = _value(attributes, "id", "name") or f"polyline:{source_index}"
                begins = [child for child in polyline if _local_name(child.tag) == "polybegin"]
                segments = [child for child in polyline if _local_name(child.tag) == "polystepsegment"]
                curves = [child for child in polyline if _local_name(child.tag) == "polystepcurve"]
                style_refs = [child for child in polyline if _local_name(child.tag) == "linedescref"]
                if not layer_name:
                    geometry_issue(
                        "IMPORT_IPC2581_LAYER_REF_UNRESOLVED",
                        f"Polyline references unknown layer {layer_ref!r}.",
                        source_id=source_id,
                    )
                    continue
                if not net_id:
                    geometry_issue(
                        "IMPORT_IPC2581_NET_REF_UNRESOLVED",
                        f"Polyline references unknown net {net_ref!r}.",
                        source_id=source_id,
                    )
                    continue
                child_tags = [_local_name(child.tag) for child in polyline]
                expected_tags = ["polybegin", *(["polystepsegment"] * len(segments)), "linedescref"]
                if (
                    len(begins) != 1
                    or not segments
                    or curves
                    or len(style_refs) != 1
                    or child_tags != expected_tags
                ):
                    geometry_issue(
                        "IMPORT_IPC2581_POLYLINE_UNSUPPORTED",
                        (
                            "Lossless polyline normalization requires one PolyBegin, one or more ordered straight "
                            "segments, no curves or unknown children, and one trailing LineDescRef."
                        ),
                        source_id=source_id,
                    )
                    continue
                style_id = _value(_attributes(style_refs[0]), "id", "ref", "linedescref")
                width_mm = line_widths.get(style_id)
                if width_mm is None:
                    geometry_issue(
                        "IMPORT_IPC2581_LINE_STYLE_UNRESOLVED",
                        f"Polyline references an unsupported, duplicate, zero-width, or unknown line style {style_id!r}.",
                        source_id=source_id,
                    )
                    continue
                point_elements = [begins[0], *segments]
                points: list[tuple[float, float]] = []
                malformed = False
                for point_element in point_elements:
                    point_attributes = _attributes(point_element)
                    x = _finite_float(point_attributes, "x")
                    y = _finite_float(point_attributes, "y")
                    if x is None or y is None:
                        malformed = True
                        break
                    point = (x * unit_factor, y * unit_factor)
                    if points and point == points[-1]:
                        malformed = True
                        break
                    points.append(point)
                segment_ids = [source_id] if len(segments) == 1 else [
                    f"{source_id}:segment:{index + 1}" for index in range(len(segments))
                ]
                if malformed or len(points) != len(segments) + 1 or any(
                    candidate in seen_geometry_ids for candidate in segment_ids
                ):
                    geometry_issue(
                        "IMPORT_IPC2581_POLYLINE_MALFORMED",
                        "Polyline coordinates and deterministic segment identities must be finite, non-zero, and unique.",
                        source_id=source_id,
                    )
                    continue
                seen_geometry_ids.update(segment_ids)
                for step_index, segment_id in enumerate(segment_ids):
                    track = {
                        "id": segment_id,
                        "layer": layer_name,
                        "net_id": net_id,
                        "start": list(points[step_index]),
                        "end": list(points[step_index + 1]),
                        "width_mm": width_mm,
                        "source_index": source_index,
                        "ipc2581_polyline_id": source_id,
                        "ipc2581_line_style": style_id,
                        "ipc2581_line_end": "ROUND",
                    }
                    if len(segment_ids) > 1:
                        track.update({
                            "path_id": source_id,
                            "path_step_index": step_index,
                            "path_step_count": len(segment_ids),
                            "path_end_cap": "round",
                            "path_join_style": "round",
                        })
                    tracks.append(track)
                normalized_records += 1

    return tracks, normalized_records
