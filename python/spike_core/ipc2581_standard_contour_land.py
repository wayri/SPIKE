"""Exact source-only retention for a narrow IPC-2581 contour-land subset."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any, Dict, Mapping


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


def _value(attributes: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(attributes.get(name.lower(), "")).strip()
        if value:
            return value
    return ""


def _finite_float(attributes: Mapping[str, str], *names: str) -> float | None:
    value = _value(attributes, *names)
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _direct_children(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == tag]


def source_xform(element: ET.Element, *, factor: float) -> Dict[str, Any] | None:
    """Retain a bounded source transform without applying it."""

    xforms = _direct_children(element, "xform")
    if len(xforms) > 1:
        return None
    if not xforms:
        return {"rotation_deg": 0.0, "mirror": False, "raw_attributes": {}}
    raw = _attributes(xforms[0])
    if set(raw) - {"xoffset", "yoffset", "rotation", "mirror", "faceup", "scale"}:
        return None
    rotation = _finite_float(raw, "rotation")
    if _value(raw, "rotation") and rotation is None:
        return None
    offsets = [_finite_float(raw, "xoffset"), _finite_float(raw, "yoffset")]
    if any(_value(raw, name) and value is None for name, value in zip(("xoffset", "yoffset"), offsets)):
        return None
    scale = _finite_float(raw, "scale")
    if _value(raw, "scale") and scale is None:
        return None
    booleans = {name: _value(raw, name).lower() for name in ("mirror", "faceup")}
    if any(value and value not in {"true", "false"} for value in booleans.values()):
        return None
    normalized: Dict[str, Any] = {
        "rotation_deg": 0.0 if rotation is None else rotation,
        "mirror": booleans["mirror"] == "true",
        "raw_attributes": dict(sorted(raw.items())),
    }
    if _value(raw, "xoffset"):
        normalized["x_offset_mm"] = offsets[0] * factor  # type: ignore[operator]
    if _value(raw, "yoffset"):
        normalized["y_offset_mm"] = offsets[1] * factor  # type: ignore[operator]
    if booleans["faceup"]:
        normalized["face_up"] = booleans["faceup"] == "true"
    if _value(raw, "scale"):
        normalized["scale"] = scale
    return normalized


def _zero_location(element: ET.Element, factor: float) -> Dict[str, Any] | None:
    locations = _direct_children(element, "location")
    if len(locations) != 1:
        return None
    raw = _attributes(locations[0])
    if set(raw) - {"x", "y"}:
        return None
    x = _finite_float(raw, "x")
    y = _finite_float(raw, "y")
    if x is None or y is None or not math.isclose(x, 0.0, abs_tol=1e-12) or not math.isclose(y, 0.0, abs_tol=1e-12):
        return None
    return {"at_mm": [x * factor, y * factor], "raw_attributes": dict(sorted(raw.items()))}


def _fill_descriptors(root: ET.Element) -> Dict[str, Dict[str, Any]]:
    candidates: Dict[str, list[Dict[str, Any]]] = {}
    for dictionary in (item for item in root.iter() if _local_name(item.tag) == "dictionaryfilldesc"):
        source_units = _value(_attributes(dictionary), "units", "unit")
        if source_units.lower() not in _UNIT_FACTORS_MM:
            continue
        for entry in _direct_children(dictionary, "entryfilldesc"):
            entry_id = _value(_attributes(entry), "id", "name")
            children = list(entry)
            if not entry_id or len(children) != 1 or _local_name(children[0].tag) != "filldesc":
                continue
            raw = _attributes(children[0])
            fill_property = _value(raw, "fillproperty")
            if not fill_property:
                continue
            candidates.setdefault(entry_id, []).append({
                "id": entry_id,
                "source_units": source_units,
                "declared_fill_property": fill_property,
                "raw_attributes": dict(sorted(raw.items())),
            })
    return {key: values[0] for key, values in candidates.items() if len(values) == 1}


def _line_ring(polygon: ET.Element, factor: float) -> Dict[str, Any] | None:
    children = list(polygon)
    if len(children) < 3 or _local_name(children[0].tag) != "polybegin" or _local_name(children[-1].tag) != "filldescref":
        return None
    start_raw = _attributes(children[0])
    if set(start_raw) - {"x", "y"}:
        return None
    start_x = _finite_float(start_raw, "x")
    start_y = _finite_float(start_raw, "y")
    if start_x is None or start_y is None:
        return None
    points = [[start_x * factor, start_y * factor]]
    raw_steps: list[Dict[str, str]] = []
    for child in children[1:-1]:
        if _local_name(child.tag) != "polystepsegment":
            return None
        raw = _attributes(child)
        if set(raw) - {"x", "y"}:
            return None
        x = _finite_float(raw, "x")
        y = _finite_float(raw, "y")
        if x is None or y is None:
            return None
        point = [x * factor, y * factor]
        if math.isclose(points[-1][0], point[0], abs_tol=1e-12) and math.isclose(points[-1][1], point[1], abs_tol=1e-12):
            return None
        points.append(point)
        raw_steps.append(dict(sorted(raw.items())))
    if len(raw_steps) < 3 or not (
        math.isclose(points[-1][0], points[0][0], abs_tol=1e-10)
        and math.isclose(points[-1][1], points[0][1], abs_tol=1e-10)
    ):
        return None
    fill_raw = _attributes(children[-1])
    if set(fill_raw) - {"id", "ref", "filldescref"}:
        return None
    fill_ref = _value(fill_raw, "id", "ref", "filldescref")
    if not fill_ref:
        return None
    return {
        "kind": "closed_line_ring",
        "points_mm": points,
        "fill_style_ref": fill_ref,
        "raw_poly_begin_attributes": dict(sorted(start_raw.items())),
        "raw_poly_step_attributes": raw_steps,
        "raw_fill_ref_attributes": dict(sorted(fill_raw.items())),
    }


def find_standard_contour_land_sources(
    root: ET.Element,
    *,
    layer_lookup: Mapping[str, str],
    copper_layers: list[str],
    element_indices: Mapping[int, int],
    unit_factor: float,
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Return only uniquely declared, line-only contour definitions and stacks.

    The result is provenance, not typed copper geometry. In particular, the
    declared fill, pad layer, transforms, and net/PinRef fields are not given
    electrical or meshing semantics here.
    """

    fill_descriptors = _fill_descriptors(root)
    definition_candidates: Dict[str, list[Dict[str, Any]]] = {}
    for dictionary in (item for item in root.iter() if _local_name(item.tag) == "dictionarystandard"):
        source_units = _value(_attributes(dictionary), "units", "unit")
        factor = _UNIT_FACTORS_MM.get(source_units.lower())
        if factor is None:
            continue
        for entry in _direct_children(dictionary, "entrystandard"):
            entry_id = _value(_attributes(entry), "id", "name")
            children = list(entry)
            if not entry_id or len(children) != 1 or _local_name(children[0].tag) != "contour":
                continue
            contour_children = list(children[0])
            if len(contour_children) != 1 or _local_name(contour_children[0].tag) != "polygon":
                continue
            ring = _line_ring(contour_children[0], factor)
            if ring is None:
                continue
            fill = fill_descriptors.get(str(ring["fill_style_ref"]))
            if fill is None or str(fill["declared_fill_property"]).upper() != "FILL":
                continue
            definition_candidates.setdefault(entry_id, []).append({
                "id": entry_id,
                "kind": "standard_contour_land_definition",
                "status": "retained_unresolved",
                "reason": "contour_land_layer_transform_semantics_pending",
                "source_index": element_indices[id(entry)],
                "source_units": source_units,
                "raw_entry_attributes": dict(sorted(_attributes(entry).items())),
                "contour": ring,
                "fill_descriptor": fill,
            })
    definitions = {key: values[0] for key, values in definition_candidates.items() if len(values) == 1}

    stack_candidates: Dict[str, list[Dict[str, Any]]] = {}
    for stack in (item for item in root.iter() if _local_name(item.tag) == "padstackdef"):
        raw_stack = _attributes(stack)
        stack_name = _value(raw_stack, "name", "id")
        children = list(stack)
        profiles = _direct_children(stack, "padstackpaddef")
        holes = _direct_children(stack, "padstackholedef")
        if not stack_name or len(children) != 1 or len(profiles) != 1 or holes:
            continue
        profile = profiles[0]
        raw_profile = _attributes(profile)
        raw_layer_ref = _value(raw_profile, "layerref", "layer")
        declared_layer = layer_lookup.get(raw_layer_ref, "")
        refs = _direct_children(profile, "standardprimitiveref")
        location = _zero_location(profile, unit_factor)
        profile_xform = source_xform(profile, factor=unit_factor)
        child_tags = [_local_name(child.tag) for child in profile]
        if (
            _value(raw_profile, "paduse").upper() != "REGULAR"
            or not declared_layer
            or declared_layer not in copper_layers
            or profile_xform is None
            or any(tag not in {"location", "xform", "standardprimitiveref"} for tag in child_tags)
            or child_tags.count("location") != 1 or child_tags.count("xform") > 1
            or child_tags.count("standardprimitiveref") != 1
            or len(refs) != 1
            or location is None
        ):
            continue
        raw_ref = _attributes(refs[0])
        primitive_ref = _value(raw_ref, "id", "primitiveref", "ref")
        if primitive_ref not in definitions:
            continue
        stack_candidates.setdefault(stack_name, []).append({
            "name": stack_name,
            "source_index": element_indices[id(stack)],
            "raw_attributes": dict(sorted(raw_stack.items())),
            "declared_regular_layer_id": declared_layer,
            "raw_declared_regular_layer_ref": raw_layer_ref,
            "raw_profile_attributes": dict(sorted(raw_profile.items())),
            "profile_location": location,
            "profile_xform": profile_xform,
            "primitive_ref": primitive_ref,
            "raw_primitive_ref_attributes": dict(sorted(raw_ref.items())),
        })
    stacks = {key: values[0] for key, values in stack_candidates.items() if len(values) == 1}
    return definitions, stacks


def retain_standard_contour_land_occurrence(
    pad: ET.Element,
    *,
    source_index: int,
    source_id: str,
    stack_name: str,
    definitions: Mapping[str, Mapping[str, Any]],
    stacks: Mapping[str, Mapping[str, Any]],
    layer_name: str,
    layer_ref: str,
    layer_polarity: str,
    copper_layers: list[str],
    net_ref: str,
    net_id: str,
    location: tuple[float, float] | None,
    component_lookup: Mapping[str, str],
    component_layer_lookup: Mapping[str, str],
    unit_factor: float,
    set_element: ET.Element,
    layer_feature: ET.Element,
) -> tuple[bool, Dict[str, Any] | None]:
    """Return whether an occurrence was safely handled and its retained row."""

    stack = stacks.get(stack_name)
    if stack is None:
        return False, None
    if layer_name and layer_name not in copper_layers:
        return True, None
    refs = _direct_children(pad, "standardprimitiveref")
    raw_ref = _attributes(refs[0]) if len(refs) == 1 else {}
    primitive_ref = _value(raw_ref, "id", "primitiveref", "ref")
    pin_refs = _direct_children(pad, "pinref")
    pin_attributes = _attributes(pin_refs[0]) if len(pin_refs) == 1 else {}
    raw_component_ref = _value(pin_attributes, "componentref", "component")
    pin_number = _value(pin_attributes, "pin", "number")
    resolved_component_id = component_lookup.get(raw_component_ref, "")
    xform = source_xform(pad, factor=unit_factor)
    child_tags = [_local_name(child.tag) for child in pad]
    expected_tags = {"location", "standardprimitiveref", "pinref", "xform"}
    if not (
        layer_name in copper_layers and layer_polarity == "positive" and net_id and net_ref
        and location is not None and xform is not None and len(pin_refs) == 1
        and raw_component_ref and pin_number and resolved_component_id
        and len(refs) == 1 and set(raw_ref) <= {"id", "primitiveref", "ref"}
        and primitive_ref == stack["primitive_ref"] and primitive_ref in definitions
        and all(tag in expected_tags for tag in child_tags)
        and child_tags.count("location") == 1
        and child_tags.count("standardprimitiveref") == 1
        and child_tags.count("pinref") == 1 and child_tags.count("xform") <= 1
    ):
        return False, None
    return True, {
        "source_index": source_index,
        "source_id": source_id,
        "kind": "standard_contour_land_occurrence",
        "status": "retained_unresolved",
        "reason": "contour_land_layer_transform_semantics_pending",
        "padstack_ref": stack_name,
        "primitive_ref": primitive_ref,
        "declared_regular_layer_id": stack["declared_regular_layer_id"],
        "observed_layer_id": layer_name,
        "declared_layer_matches_observed": stack["declared_regular_layer_id"] == layer_name,
        "raw_observed_layer_ref": layer_ref,
        "observed_layer_polarity": layer_polarity,
        "raw_net_ref": net_ref,
        "resolved_net_id": net_id,
        "pin_provenance": {
            "raw_component_ref": raw_component_ref,
            "resolved_component_id": resolved_component_id,
            "component_layer_id": component_layer_lookup.get(raw_component_ref, ""),
            "pin": pin_number,
            "raw_attributes": dict(sorted(pin_attributes.items())),
        },
        "at_mm": list(location),
        "xform": xform,
        "raw_primitive_ref_attributes": dict(sorted(raw_ref.items())),
        "raw_pad_attributes": dict(sorted(_attributes(pad).items())),
        "raw_set_attributes": dict(sorted(_attributes(set_element).items())),
        "raw_layer_feature_attributes": dict(sorted(_attributes(layer_feature).items())),
    }


def retained_standard_contour_land_geometry(
    definitions: Mapping[str, Dict[str, Any]],
    stacks: Mapping[str, Dict[str, Any]],
    occurrences: list[Dict[str, Any]],
) -> Dict[str, Any]:
    primitive_ids = sorted({str(row["primitive_ref"]) for row in occurrences})
    stack_names = sorted({str(row["padstack_ref"]) for row in occurrences})
    return {
        "contract": "spike/retained-standard-contour-land-geometry/v2",
        # These are retention observations, not an IPC-2581 conformance claim.
        # No consumer may compose either source Xform or project this envelope.
        "semantic_state": "unapplied_normative_semantics_missing",
        "projection": "forbidden",
        "definitions": [definitions[item] for item in primitive_ids],
        "padstacks": [stacks[item] for item in stack_names],
        "occurrences": occurrences,
    }


def retained_standard_contour_land_summary(
    geometry: Mapping[str, Any],
) -> tuple[int, int, int, Dict[str, str], Dict[str, Any]]:
    """Summarize retained source facts without assigning geometry semantics."""

    occurrences = geometry.get("occurrences") if isinstance(geometry.get("occurrences"), list) else []
    count = len(occurrences)
    matches = sum(isinstance(item, Mapping) and item.get("declared_layer_matches_observed") is True for item in occurrences)
    mismatches = count - matches
    return count, matches, mismatches, {
        "code": "IMPORT_IPC2581_STANDARD_CONTOUR_LAND_SEMANTICS_PENDING",
        "severity": "warning",
        "message": (f"{count} exact DictionaryStandard contour-land occurrences are retained as source metadata only "
                    f"({matches} declared-layer matches, {mismatches} mismatches); profile and occurrence transforms remain unapplied."),
        "suggestion": "Review layer/profile and transform semantics before creating pads, connectivity, Arrow rows, meshes, or solver geometry.",
    }, {
        "severity": "warning", "code": "IMPORT_IPC2581_STANDARD_CONTOUR_LAND_SEMANTICS_PENDING",
        "count": count, "declared_layer_matches": matches, "declared_layer_mismatches": mismatches,
    }


def retained_standard_contour_land_empirical_distribution(geometry: Mapping[str, Any]) -> Dict[str, Any]:
    """Return auditable fixture observations, explicitly not conformance claims."""

    padstacks = geometry.get("padstacks") if isinstance(geometry.get("padstacks"), list) else []
    profiles = {
        (item.get("name"),
         item.get("profile_xform", {}).get("rotation_deg"),
         item.get("profile_xform", {}).get("mirror"))
        for item in padstacks if isinstance(item, Mapping) and isinstance(item.get("profile_xform"), Mapping)
    }
    occurrences = geometry.get("occurrences") if isinstance(geometry.get("occurrences"), list) else []
    counts: Dict[tuple[Any, ...], int] = {}
    for item in occurrences:
        if not isinstance(item, Mapping) or not isinstance(item.get("xform"), Mapping):
            continue
        xform = item["xform"]
        key = (
            item.get("declared_regular_layer_id"), item.get("observed_layer_id"),
            xform.get("rotation_deg"), xform.get("mirror"),
        )
        counts[key] = counts.get(key, 0) + 1
    return {
        "label": "empirical_source_observation_not_conformance",
        "profile_xforms": [
            {"padstack_ref": name, "rotation_deg": rotation, "mirror": mirror}
            for name, rotation, mirror in sorted(profiles, key=lambda item: str(item[0]))
        ],
        "occurrences": [
            {"declared_regular_layer_id": declared, "observed_layer_id": observed,
             "rotation_deg": rotation, "mirror": mirror, "count": count}
            for (declared, observed, rotation, mirror), count in sorted(counts.items(), key=lambda item: tuple(str(part) for part in item[0]))
        ],
    }
