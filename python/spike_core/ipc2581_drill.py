"""Lossless IPC-2581 physical drill normalization and owner linking."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, Mapping


GeometryIssue = Callable[..., None]


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


def _finite(attributes: Mapping[str, str], *names: str) -> float | None:
    raw = _value(attributes, *names)
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _point_key(point: tuple[float, float]) -> tuple[float, float]:
    return round(point[0], 9), round(point[1], 9)


def normalize_physical_drills(
    root: ET.Element,
    *,
    unit_factor: float,
    layer_lookup: Mapping[str, str],
    net_lookup: Mapping[str, str],
    components: list[Dict[str, Any]],
    pads: list[Dict[str, Any]],
    vias: list[Dict[str, Any]],
    element_indices: Mapping[int, int],
    geometry_issue: GeometryIssue,
) -> tuple[list[Dict[str, Any]], int, int]:
    """Preserve direct physical holes and link exact electrical owners once."""

    component_lookup: Dict[str, str] = {}
    for component in components:
        component_id = str(component.get("id", ""))
        component_lookup[component_id] = component_id
        component_lookup[str(component.get("reference", ""))] = component_id

    owners: Dict[tuple[Any, ...], list[tuple[str, str, list[str]]]] = {}
    for kind, records in (("via", vias), ("pad", pads)):
        for record in records:
            point = record.get("at")
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            drill = record.get("drill")
            try:
                center = (float(point[0]), float(point[1]))
                diameter = float(drill)
            except (TypeError, ValueError):
                continue
            if not all(math.isfinite(value) for value in (*center, diameter)) or diameter <= 0:
                continue
            component_id = str(record.get("component", "")) if kind == "pad" else ""
            key = (
                str(record.get("ipc2581_padstack", "")),
                *_point_key(center), round(diameter, 9),
                str(record.get("net_id", "")), component_id,
            )
            owners.setdefault(key, []).append((kind, str(record.get("id", "")), [str(item) for item in record.get("layers", [])]))

    drills: list[Dict[str, Any]] = []
    normalized = 0
    unresolved_owners = 0
    source_ids: set[str] = set()
    for layer_feature in (item for item in root.iter() if _local_name(item.tag) == "layerfeature"):
        layer_attributes = _attributes(layer_feature)
        layer_ref = _value(layer_attributes, "layerref", "layer")
        source_layer = layer_lookup.get(layer_ref, layer_ref)
        for set_element in (item for item in layer_feature if _local_name(item.tag) == "set"):
            set_attributes = _attributes(set_element)
            net_ref = _value(set_attributes, "netref", "net") or _value(layer_attributes, "netref", "net")
            net_id = net_lookup.get(net_ref, "")
            geometry_ref = _value(set_attributes, "geometry", "padstackdefref", "padstackref")
            component_ref = _value(set_attributes, "componentref", "component")
            component_id = component_lookup.get(component_ref, "")
            for hole in (item for item in set_element if _local_name(item.tag) == "hole"):
                attributes = _attributes(hole)
                source_index = element_indices[id(hole)]
                source_id = _value(attributes, "name", "id") or f"hole:{source_index}"
                x = _finite(attributes, "x")
                y = _finite(attributes, "y")
                diameter = _finite(attributes, "diameter")
                plus_tolerance = _finite(attributes, "plustol")
                minus_tolerance = _finite(attributes, "minustol")
                status_raw = _value(attributes, "platingstatus").upper()
                status = {
                    "VIA": "via", "PLATED": "plated", "UNPLATED": "unplated",
                    "NONPLATED": "unplated", "NON_PLATED": "unplated",
                }.get(status_raw, "unknown")
                malformed = (
                    source_id in source_ids or x is None or y is None or diameter is None or diameter <= 0
                    or (plus_tolerance is not None and plus_tolerance < 0)
                    or (minus_tolerance is not None and minus_tolerance < 0)
                )
                if malformed:
                    geometry_issue(
                        "IMPORT_IPC2581_DRILL_MALFORMED",
                        "Physical Hole records require unique identities, finite coordinates, a positive circular diameter, and non-negative tolerances.",
                        source_id=source_id,
                    )
                    continue
                source_ids.add(source_id)
                center_mm = (x * unit_factor, y * unit_factor)
                diameter_mm = diameter * unit_factor
                owner_key = (
                    geometry_ref, *_point_key(center_mm), round(diameter_mm, 9),
                    net_id, component_id,
                )
                matches = owners.get(owner_key, [])
                owner_kind = "none" if status == "unplated" else "unresolved"
                owner_id = ""
                owner_match = "none"
                span_layers: list[str] = []
                span_provenance = "unresolved"
                if len(matches) == 1:
                    owner_kind, owner_id, span_layers = matches[0]
                    owner_match = "exact_source"
                    span_provenance = "matched_owner"
                elif status != "unplated":
                    unresolved_owners += 1
                drills.append({
                    "id": source_id,
                    "name": source_id,
                    "source_layer_id": source_layer,
                    "at": list(center_mm),
                    "shape": "circle",
                    "diameter_mm": diameter_mm,
                    "size_mm": None,
                    "rotation_deg": None,
                    "plating_status": status,
                    "plated": True if status in {"via", "plated"} else False if status == "unplated" else None,
                    "plus_tolerance_mm": plus_tolerance * unit_factor if plus_tolerance is not None else None,
                    "minus_tolerance_mm": minus_tolerance * unit_factor if minus_tolerance is not None else None,
                    "net_id": net_id,
                    "component_id": component_id,
                    "geometry_ref": geometry_ref,
                    "span_layer_ids": span_layers,
                    "span_provenance": span_provenance,
                    "owner_kind": owner_kind,
                    "owner_id": owner_id,
                    "owner_match": owner_match,
                    "source_index": source_index,
                    "ipc2581_source": {
                        "hole": attributes,
                        "set": set_attributes,
                        "layer_feature": layer_attributes,
                    },
                })
                normalized += 1

    return drills, normalized, unresolved_owners
