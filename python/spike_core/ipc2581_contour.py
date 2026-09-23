"""Strict, lossless IPC-2581 contour normalization.

This module intentionally stops at a typed source-side representation.  It
does not tessellate arcs or claim that curved holes are mesh-ready.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, Mapping


GeometryIssue = Callable[..., None]
_UNIT_FACTORS_MM = {
    "mm": 1.0, "millimeter": 1.0, "millimeters": 1.0,
    "inch": 25.4, "inches": 25.4, "mil": 0.0254, "mils": 0.0254,
}


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
    try:
        value = float(_value(attributes, name))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _same_point(first: tuple[float, float], second: tuple[float, float]) -> bool:
    return math.isclose(first[0], second[0], rel_tol=0.0, abs_tol=1e-10) and math.isclose(
        first[1], second[1], rel_tol=0.0, abs_tol=1e-10
    )


def normalize_contours(
    root: ET.Element,
    *,
    unit_factor: float,
    layer_lookup: Mapping[str, str],
    layer_polarities: Mapping[str, str],
    net_lookup: Mapping[str, str],
    element_indices: Mapping[int, int],
    seen_geometry_ids: set[str],
    geometry_issue: GeometryIssue,
    max_rings_per_contour: int = 10_000,
    max_segments_per_ring: int = 100_000,
) -> tuple[list[Dict[str, Any]], int, list[Dict[str, Any]]]:
    """Return strict v1-style zones and source-only negative contours.

    ``layer_lookup`` and ``net_lookup`` resolve native IPC references to the
    caller's desired v1 identities. ``layer_polarities`` is keyed by either
    the native layer reference or its resolved value and must declare
    ``POSITIVE`` for typed zones. Exact ``NEGATIVE`` contours are retained as
    unresolved source metadata without fill, void, antipad, connectivity, or
    copper semantics. The function scans only the direct
    ``LayerFeature/Set/Features/Contour`` hierarchy and emits each contour
    atomically: a bad child produces no partial record.
    """
    if not math.isfinite(unit_factor) or unit_factor <= 0.0:
        raise ValueError("IPC-2581 contour normalization requires a finite positive unit_factor.")
    if max_rings_per_contour < 1 or max_segments_per_ring < 2:
        raise ValueError("Contour normalization bounds are invalid.")

    # A fill dictionary has a physical unit declaration in IPC-2581C.  A
    # mixed-unit dictionary is rejected, rather than silently converted.
    fills: dict[str, str] = {}
    duplicate_fills: set[str] = set()
    for dictionary in (item for item in root.iter() if _local_name(item.tag) == "dictionaryfilldesc"):
        dictionary_factor = _UNIT_FACTORS_MM.get(_value(_attributes(dictionary), "units", "unit").lower())
        if dictionary_factor is None or not math.isclose(dictionary_factor, unit_factor, rel_tol=0.0, abs_tol=1e-15):
            continue
        for entry in dictionary:
            if _local_name(entry.tag) != "entryfilldesc":
                continue
            fill_id = _value(_attributes(entry), "id", "name")
            descriptions = [child for child in entry if _local_name(child.tag) == "filldesc"]
            property_ = _value(_attributes(descriptions[0]), "fillproperty").upper() if len(descriptions) == 1 else ""
            if not fill_id or not property_:
                continue
            if fill_id in fills:
                duplicate_fills.add(fill_id)
                fills.pop(fill_id, None)
            elif fill_id not in duplicate_fills:
                fills[fill_id] = property_

    def issue(code: str, message: str, source_id: str) -> None:
        geometry_issue(code, message, source_id=source_id)

    def point(element: ET.Element) -> tuple[float, float] | None:
        attributes = _attributes(element)
        x, y = _finite_float(attributes, "x"), _finite_float(attributes, "y")
        return None if x is None or y is None else (x * unit_factor, y * unit_factor)

    def ring(element: ET.Element, *, role: str, fill_mode: str) -> tuple[dict[str, Any] | None, str]:
        if fill_mode not in {"required", "optional", "forbidden"}:
            raise ValueError("Contour fill mode is invalid.")
        children = list(element)
        if not children or _local_name(children[0].tag) != "polybegin":
            return None, "A contour ring must begin with exactly one PolyBegin."
        start = point(children[0])
        if start is None:
            return None, "Contour ring coordinates must be finite."
        current = start
        segments: list[dict[str, Any]] = []
        fill_id = ""
        for child_index, child in enumerate(children[1:], start=1):
            tag = _local_name(child.tag)
            if tag == "filldescref" and fill_mode in {"required", "optional"} and child_index == len(children) - 1:
                fill_id = _value(_attributes(child), "id", "ref", "filldescref")
                if not fill_id:
                    return None, "Contour FillDescRef requires a source identity."
                continue
            if tag not in {"polystepsegment", "polystepcurve"}:
                return None, "Contour rings support only ordered line or circular-arc steps."
            end = point(child)
            if end is None or _same_point(current, end):
                return None, "Contour segments require finite non-zero endpoints."
            if tag == "polystepsegment":
                segments.append({"kind": "line", "end_mm": list(end)})
            else:
                attributes = _attributes(child)
                center_x, center_y = _finite_float(attributes, "centerx"), _finite_float(attributes, "centery")
                clockwise = _value(attributes, "clockwise").lower()
                if center_x is None or center_y is None or clockwise not in {"true", "false"}:
                    return None, "Circular arcs require finite centerX/centerY and an explicit clockwise boolean."
                center = (center_x * unit_factor, center_y * unit_factor)
                start_radius = math.hypot(current[0] - center[0], current[1] - center[1])
                end_radius = math.hypot(end[0] - center[0], end[1] - center[1])
                if start_radius <= 0.0 or not math.isclose(start_radius, end_radius, rel_tol=1e-9, abs_tol=1e-10):
                    return None, "PolyStepCurve must be a non-degenerate circular arc."
                segments.append({"kind": "arc", "end_mm": list(end), "center_mm": list(center), "clockwise": clockwise == "true"})
            current = end
            if len(segments) > max_segments_per_ring:
                return None, "Contour ring exceeds the configured segment bound."
        if not segments or not _same_point(current, start):
            return None, "Contour rings must be explicitly closed without approximation."
        if fill_mode == "required":
            if not fill_id:
                return None, "Positive contour polygons require one trailing FillDescRef."
            if fills.get(fill_id) != "FILL":
                return None, "Contour FillDescRef must resolve uniquely to a SOLID FILL style with matching units."
        return {
            "role": role, "start_mm": list(start), "segments": segments,
            **({"fill_style_id": fill_id} if fill_id else {}),
            **({"observed_fill_property": fills[fill_id]} if fill_id in fills else {}),
        }, ""

    def contour_rings(
        contour: ET.Element, *, outer_fill_mode: str,
    ) -> tuple[list[dict[str, Any]] | None, str]:
        children = list(contour)
        outer = [child for child in children if _local_name(child.tag) == "polygon"]
        cutouts = [child for child in children if _local_name(child.tag) == "cutout"]
        if (
            len(outer) != 1
            or not children
            or _local_name(children[0].tag) != "polygon"
            or any(_local_name(child.tag) != "cutout" for child in children[1:])
            or len(children) != 1 + len(cutouts)
            or len(cutouts) > max_rings_per_contour - 1
        ):
            return None, "Contour requires one direct Polygon followed only by bounded direct Cutout rings."
        boundary, error = ring(outer[0], role="outer", fill_mode=outer_fill_mode)
        rings: list[dict[str, Any]] = [boundary] if boundary is not None else []
        if boundary is not None:
            for cutout in cutouts:
                value, error = ring(cutout, role="cutout", fill_mode="forbidden")
                if value is None:
                    break
                rings.append(value)
        if boundary is None or len(rings) != 1 + len(cutouts):
            return None, error
        return rings, ""

    zones: list[Dict[str, Any]] = []
    retained_negative: list[Dict[str, Any]] = []
    normalized = 0
    for layer_feature in (item for item in root.iter() if _local_name(item.tag) == "layerfeature"):
        layer_attributes = _attributes(layer_feature)
        layer_ref = _value(layer_attributes, "layerref", "layer")
        layer_id = layer_lookup.get(layer_ref, "")
        polarity = str(layer_polarities.get(layer_ref, layer_polarities.get(layer_id, ""))).upper()
        for set_element in (item for item in layer_feature if _local_name(item.tag) == "set"):
            set_attributes = _attributes(set_element)
            net_ref = _value(set_attributes, "netref", "net") or _value(layer_attributes, "netref", "net")
            net_id = net_lookup.get(net_ref, "")
            for features in (item for item in set_element if _local_name(item.tag) == "features"):
                for contour in (item for item in features if _local_name(item.tag) == "contour"):
                    index = element_indices.get(id(contour), -1)
                    source_id = _value(_attributes(contour), "id", "name") or f"contour:{index}"
                    if not layer_id:
                        issue("IMPORT_IPC2581_LAYER_REF_UNRESOLVED", f"Contour references unknown layer {layer_ref!r}.", source_id)
                        continue
                    if polarity not in {"POSITIVE", "NEGATIVE"}:
                        issue("IMPORT_IPC2581_CONTOUR_POLARITY_UNSUPPORTED", "Contour layer semantics must be explicitly POSITIVE or NEGATIVE.", source_id)
                        continue
                    if polarity == "POSITIVE" and not net_id:
                        issue("IMPORT_IPC2581_NET_REF_UNRESOLVED", f"Contour references unknown net {net_ref!r}.", source_id)
                        continue
                    if source_id in seen_geometry_ids:
                        issue("IMPORT_IPC2581_GEOMETRY_ID_DUPLICATE", f"Contour identity {source_id!r} is duplicated.", source_id)
                        continue
                    rings, error = contour_rings(
                        contour,
                        outer_fill_mode="required" if polarity == "POSITIVE" else "optional",
                    )
                    if rings is None:
                        issue("IMPORT_IPC2581_CONTOUR_MALFORMED", error, source_id)
                        continue
                    seen_geometry_ids.add(source_id)
                    if polarity == "NEGATIVE":
                        boundary = rings[0]
                        retained_negative.append({
                            "status": "retained_unresolved",
                            "reason": "negative_layer_contour_semantics_pending",
                            "source_id": source_id, "source_index": index,
                            "layer_ref": layer_ref, "resolved_layer_id": layer_id,
                            "layer_polarity": "NEGATIVE", "raw_net_ref": net_ref,
                            "resolved_net_id": net_id, "boundary_rings": rings,
                            **({"raw_fill_ref": boundary["fill_style_id"]}
                               if "fill_style_id" in boundary else {}),
                            **({"observed_fill_property": boundary["observed_fill_property"]}
                               if "observed_fill_property" in boundary else {}),
                        })
                        continue
                    boundary = rings[0]
                    fill_style_id = str(boundary.pop("fill_style_id"))
                    boundary.pop("observed_fill_property", None)
                    zones.append({
                        "id": source_id, "layer": layer_id, "layers": [layer_id], "net_id": net_id,
                        "boundary_rings": rings, "source_index": index,
                        "fill_style_id": fill_style_id, "fill_property": "FILL",
                        "ipc2581_contour_id": source_id, "ipc2581_layer_ref": layer_ref,
                        "ipc2581_net_ref": net_ref, "ipc2581_fill_style": fill_style_id,
                    })
                    normalized += 1
    return zones, normalized, retained_negative
