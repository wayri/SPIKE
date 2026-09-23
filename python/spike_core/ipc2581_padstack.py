"""Strict IPC-2581 padstack, component-pad, and through-via normalization."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, Mapping

from . import ipc2581_standard_contour_land as contour_land
from .ipc2581_unnetted_padstack import finalize_unnetted_padstack_groups


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


def _finite_float(attributes: Mapping[str, str], *names: str) -> float | None:
    value = _value(attributes, *names)
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def normalize_pad_via_geometry(
    root: ET.Element,
    *,
    unit_factor: float,
    layer_lookup: Mapping[str, str],
    net_lookup: Mapping[str, str],
    components: list[Dict[str, Any]],
    copper_layers: list[str],
    layer_polarities: Mapping[str, str],
    element_indices: Mapping[int, int],
    geometry_issue: GeometryIssue,
) -> tuple[
    list[Dict[str, Any]], list[Dict[str, Any]], int, list[Dict[str, Any]],
    list[Dict[str, Any]], Dict[str, Any], Dict[str, Any],
]:
    """Normalize the supported lossless padstack subset and reject ambiguity."""

    def direct_children(element: ET.Element, tag: str) -> list[ET.Element]:
        return [child for child in element if _local_name(child.tag) == tag]

    def one_location(element: ET.Element, *, allow_attributes: bool = False) -> tuple[float, float] | None:
        locations = direct_children(element, "location")
        if allow_attributes and not locations:
            attributes = _attributes(element)
            x = _finite_float(attributes, "x")
            y = _finite_float(attributes, "y")
        elif len(locations) == 1:
            attributes = _attributes(locations[0])
            x = _finite_float(attributes, "x")
            y = _finite_float(attributes, "y")
        else:
            return None
        return None if x is None or y is None else (x * unit_factor, y * unit_factor)

    # UserSpecial primitives on negative planes are deliberately retained as
    # source geometry only.  Their boolean/void semantics are not projected
    # into Pad, Via, connectivity, arrows, or a solver mesh.
    def user_primitive_ref(element: ET.Element) -> tuple[str, Dict[str, Any]] | None:
        refs = direct_children(element, "userprimitiveref")
        if len(refs) != 1:
            return None
        reference = refs[0]
        primitive_id = _value(_attributes(reference), "id", "primitiveref", "ref")
        children = list(reference)
        parent_xforms = direct_children(element, "xform")
        if (
            not primitive_id or any(_local_name(child.tag) != "xform" for child in children)
            or len(children) > 1 or len(parent_xforms) > 1 or len(children) + len(parent_xforms) > 1
        ):
            return None
        xform = {"rotation_deg": 0.0, "mirror": False}
        xform_elements = [*children, *parent_xforms]
        if xform_elements:
            attributes = _attributes(xform_elements[0])
            if set(attributes) - {"rotation", "mirror"}:
                return None
            rotation = _finite_float(attributes, "rotation")
            if _value(attributes, "rotation") and rotation is None:
                return None
            mirror = _value(attributes, "mirror").lower()
            if mirror and mirror not in {"true", "false"}:
                return None
            xform = {"rotation_deg": 0.0 if rotation is None else rotation, "mirror": mirror == "true"}
        return primitive_id, xform

    def contour_ring(element: ET.Element, *, role: str, factor: float) -> Dict[str, Any] | None:
        children = list(element)
        if len(children) < 2 or _local_name(children[0].tag) != "polybegin":
            return None

        def point(item: ET.Element) -> tuple[float, float] | None:
            attributes = _attributes(item)
            x, y = _finite_float(attributes, "x"), _finite_float(attributes, "y")
            return None if x is None or y is None else (x * factor, y * factor)

        start = point(children[0])
        if start is None:
            return None
        current = start
        segments: list[Dict[str, Any]] = []
        fill_style_id = ""
        for index, child in enumerate(children[1:], start=1):
            tag = _local_name(child.tag)
            if tag == "filldescref" and index == len(children) - 1 and not fill_style_id:
                fill_style_id = _value(_attributes(child), "id", "ref", "filldescref")
                if not fill_style_id:
                    return None
                continue
            if tag not in {"polystepsegment", "polystepcurve"}:
                return None
            end = point(child)
            if end is None or math.isclose(current[0], end[0], abs_tol=1e-12) and math.isclose(current[1], end[1], abs_tol=1e-12):
                return None
            if tag == "polystepsegment":
                segments.append({"kind": "line", "end_mm": list(end)})
            else:
                attributes = _attributes(child)
                center_x, center_y = _finite_float(attributes, "centerx"), _finite_float(attributes, "centery")
                clockwise = _value(attributes, "clockwise").lower()
                if center_x is None or center_y is None or clockwise not in {"true", "false"}:
                    return None
                center = (center_x * factor, center_y * factor)
                start_radius = math.dist(current, center)
                end_radius = math.dist(end, center)
                if start_radius <= 0.0 or not math.isclose(start_radius, end_radius, rel_tol=1e-9, abs_tol=1e-10):
                    return None
                segments.append({"kind": "arc", "end_mm": list(end), "center_mm": list(center), "clockwise": clockwise == "true"})
            current = end
            if len(segments) > 100_000:
                return None
        if not segments or not math.isclose(current[0], start[0], abs_tol=1e-10) or not math.isclose(current[1], start[1], abs_tol=1e-10):
            return None
        return {"role": role, "start_mm": list(start), "segments": segments, "fill_style_id": fill_style_id}

    def user_special_definition(
        element: ET.Element, *, primitive_id: str, source_index: int, source_units: str, factor: float,
    ) -> Dict[str, Any] | None:
        contours = direct_children(element, "contour")
        if not primitive_id or not contours or len(contours) > 10_000 or any(_local_name(child.tag) != "contour" for child in element):
            return None
        normalized_contours: list[Dict[str, Any]] = []
        for contour in contours:
            children = list(contour)
            polygons = [child for child in children if _local_name(child.tag) == "polygon"]
            cutouts = [child for child in children if _local_name(child.tag) == "cutout"]
            if (
                len(polygons) != 1 or not children or _local_name(children[0].tag) != "polygon"
                or any(_local_name(child.tag) != "cutout" for child in children[1:])
                or len(cutouts) > 9_999
            ):
                return None
            outer = contour_ring(polygons[0], role="outer", factor=factor)
            rings: list[Dict[str, Any]] = [outer] if outer is not None else []
            for cutout in cutouts:
                ring = contour_ring(cutout, role="cutout", factor=factor)
                if ring is None:
                    return None
                rings.append(ring)
            if outer is None:
                return None
            if not outer["fill_style_id"]:
                return None
            normalized_contours.append({"boundary_rings": rings})
        return {
            "id": primitive_id,
            "kind": "user_special",
            "source_index": source_index,
            "source_units": source_units,
            "contours": normalized_contours,
        }

    user_special_elements: Dict[str, list[tuple[ET.Element, str, int, str, float]]] = {}
    seen_user_special_elements: set[int] = set()
    for dictionary in (item for item in root.iter() if _local_name(item.tag) == "dictionaryuser"):
        source_units = _value(_attributes(dictionary), "units", "unit")
        factor = _UNIT_FACTORS_MM.get(source_units.lower())
        if factor is None:
            continue
        for entry in direct_children(dictionary, "entryuser"):
            primitive_id = _value(_attributes(entry), "id", "name")
            specials = direct_children(entry, "userspecial")
            if primitive_id and len(specials) == 1:
                special = specials[0]
                user_special_elements.setdefault(primitive_id, []).append(
                    (special, primitive_id, element_indices[id(special)], source_units, factor)
                )
                seen_user_special_elements.add(id(special))
        for element in (item for item in dictionary.iter() if _local_name(item.tag) == "userspecial" and id(item) not in seen_user_special_elements):
            primitive_id = _value(_attributes(element), "id", "name")
            if primitive_id:
                user_special_elements.setdefault(primitive_id, []).append(
                    (element, primitive_id, element_indices[id(element)], source_units, factor)
                )
                seen_user_special_elements.add(id(element))
    # A few generators omit DictionaryUser while using the document unit.
    # Retain that unambiguous subset without guessing an unsupported unit.
    root_units = _value(_attributes(root), "units", "unit")
    for element in (item for item in root.iter() if _local_name(item.tag) == "userspecial" and id(item) not in seen_user_special_elements):
        primitive_id = _value(_attributes(element), "id", "name")
        if primitive_id:
            user_special_elements.setdefault(primitive_id, []).append(
                (element, primitive_id, element_indices[id(element)], root_units, unit_factor)
            )
    parsed_user_specials: Dict[str, Dict[str, Any] | None] = {}

    # Dictionary primitives are the only source format which carries a stable
    # per-layer primitive identity.  Retain that identity beside the resolved
    # dimensions so heterogeneous padstacks can be represented losslessly.
    standard_shapes: Dict[str, tuple[str, float, float, str]] = {}
    duplicate_standard_shapes: set[str] = set()
    for dictionary in (item for item in root.iter() if _local_name(item.tag) == "dictionarystandard"):
        dictionary_unit = _value(_attributes(dictionary), "units", "unit").lower()
        dictionary_factor = _UNIT_FACTORS_MM.get(dictionary_unit)
        if dictionary_factor is None:
            continue
        for entry in (item for item in dictionary if _local_name(item.tag) == "entrystandard"):
            entry_id = _value(_attributes(entry), "id", "name")
            children = list(entry)
            circles = direct_children(entry, "circle")
            rectangles = direct_children(entry, "rectcenter")
            shape: tuple[str, float, float, str] | None = None
            if len(children) == 1 and len(circles) == 1 and not rectangles:
                diameter = _finite_float(_attributes(circles[0]), "diameter")
                if diameter is not None and diameter > 0.0:
                    shape = ("circle", diameter * dictionary_factor, diameter * dictionary_factor, entry_id)
            elif len(children) == 1 and len(rectangles) == 1 and not circles:
                attributes = _attributes(rectangles[0])
                width = _finite_float(attributes, "width")
                height = _finite_float(attributes, "height")
                if width is not None and height is not None and width > 0.0 and height > 0.0:
                    shape = ("rect", width * dictionary_factor, height * dictionary_factor, entry_id)
            if not entry_id or shape is None:
                continue
            if entry_id in standard_shapes:
                duplicate_standard_shapes.add(entry_id)
                standard_shapes.pop(entry_id, None)
            elif entry_id not in duplicate_standard_shapes:
                standard_shapes[entry_id] = shape

    def pad_shape(element: ET.Element) -> tuple[str, float, float, str] | None:
        circles = direct_children(element, "circle")
        standard_refs = direct_children(element, "standardprimitiveref")
        if direct_children(element, "userprimitiveref"):
            return None
        if len(circles) == 1 and not standard_refs:
            diameter = _finite_float(_attributes(circles[0]), "diameter")
            if diameter is not None and diameter > 0.0:
                # Inline circles are retained for legacy homogeneous stacks,
                # but do not have a source primitive identity and therefore
                # cannot participate in a heterogeneous land profile set.
                return ("circle", diameter * unit_factor, diameter * unit_factor, "")
            return None
        if len(standard_refs) == 1 and not circles:
            reference = _value(_attributes(standard_refs[0]), "id", "primitiveref", "ref")
            return standard_shapes.get(reference)
        return None

    component_lookup = {key: str(row.get("id", "")) for row in components for key in (str(row.get("id", "")), str(row.get("reference", "")))}
    component_layer_lookup = {key: str(row.get("layer", "")) for row in components for key in (str(row.get("id", "")), str(row.get("reference", "")))}

    padstack_elements: Dict[str, list[ET.Element]] = {}
    for element in root.iter():
        if _local_name(element.tag) == "padstackdef":
            name = _value(_attributes(element), "name", "id")
            if name:
                padstack_elements.setdefault(name, []).append(element)

    contour_land_definitions, contour_land_padstacks = contour_land.find_standard_contour_land_sources(
        root,
        layer_lookup=layer_lookup,
        copper_layers=copper_layers,
        element_indices=element_indices,
        unit_factor=unit_factor,
    )

    # This is intentionally narrower than general non-REGULAR support.  It
    # accepts only the audited negative-plane THERMAL/UserSpecial pattern,
    # with one zero-offset, uniquely identified profile on the occurrence
    # layer.  Everything else remains ordinary unsupported source geometry.
    nonregular_profiles: Dict[tuple[str, str, str], list[Dict[str, Any]]] = {}
    for name, definitions in padstack_elements.items():
        if len(definitions) != 1:
            continue
        for profile in direct_children(definitions[0], "padstackpaddef"):
            attributes = _attributes(profile)
            profile_use = _value(attributes, "paduse").lower()
            profile_layer = layer_lookup.get(_value(attributes, "layerref", "layer"), "")
            reference = user_primitive_ref(profile)
            profile_location = one_location(profile)
            if (
                profile_use != "thermal" or not profile_layer or reference is None or profile_location is None
                or not math.isclose(profile_location[0], 0.0, abs_tol=1e-12)
                or not math.isclose(profile_location[1], 0.0, abs_tol=1e-12)
                or reference[1] != {"rotation_deg": 0.0, "mirror": False}
            ):
                continue
            primitive_ref = reference[0]
            nonregular_profiles.setdefault((name, profile_layer, primitive_ref), []).append({
                "use": profile_use,
                "source_index": element_indices[id(profile)],
            })

    padstacks: Dict[str, Dict[str, Any]] = {}
    for name, definitions in padstack_elements.items():
        source_id = f"padstack:{name}"
        if name in contour_land_padstacks:
            # This exact source-only subset is handled separately below. Its
            # TOP-only profile cannot honestly type BOTTOM occurrences.
            continue
        if len(definitions) != 1:
            geometry_issue(
                "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_DUPLICATE",
                f"Padstack {name!r} must be declared exactly once.",
                source_id=source_id,
            )
            continue
        definition = definitions[0]
        regular_lands = [
            child for child in direct_children(definition, "padstackpaddef")
            if _value(_attributes(child), "paduse").upper() == "REGULAR"
        ]
        if not regular_lands:
            geometry_issue(
                "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_LANDS",
                f"Padstack {name!r} has no explicit REGULAR copper lands.",
                source_id=source_id,
            )
            continue
        occurrence_shapes: Dict[str, list[tuple[str, tuple[str, float, float, str]]]] = {}
        for profile in direct_children(definition, "padstackpaddef"):
            profile_attributes = _attributes(profile)
            profile_layer = layer_lookup.get(_value(profile_attributes, "layerref", "layer"), "")
            profile_use = _value(profile_attributes, "paduse").upper()
            profile_shape = pad_shape(profile)
            profile_location = one_location(profile)
            if (
                profile_layer and profile_use and profile_shape is not None and profile_location is not None
                and math.isclose(profile_location[0], 0.0, abs_tol=1e-12)
                and math.isclose(profile_location[1], 0.0, abs_tol=1e-12)
            ):
                occurrence_shapes.setdefault(profile_layer, []).append((profile_use, profile_shape))
        land_layers: list[str] = []
        layer_shapes: Dict[str, tuple[str, float, float, str]] = {}
        malformed = False
        for land in regular_lands:
            attributes = _attributes(land)
            layer_ref = _value(attributes, "layerref", "layer")
            layer_name = layer_lookup.get(layer_ref, "")
            location = one_location(land)
            shape = pad_shape(land)
            if (
                not layer_name
                or layer_name not in copper_layers
                or location is None
                or not math.isclose(location[0], 0.0, abs_tol=1e-12)
                or not math.isclose(location[1], 0.0, abs_tol=1e-12)
                or shape is None
                or layer_name in land_layers
            ):
                malformed = True
                break
            land_layers.append(layer_name)
            layer_shapes[layer_name] = shape
        if malformed:
            geometry_issue(
                "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_LANDS",
                f"Padstack {name!r} requires one zero-offset supported REGULAR copper land per layer.",
                source_id=source_id,
            )
            continue
        land_layers.sort(key=copper_layers.index)
        ordered_shapes = [layer_shapes[layer_name] for layer_name in land_layers]
        first_shape = ordered_shapes[0]
        heterogeneous = any(
            shape[0] != first_shape[0]
            or not math.isclose(shape[1], first_shape[1], rel_tol=1e-9, abs_tol=1e-12)
            or not math.isclose(shape[2], first_shape[2], rel_tol=1e-9, abs_tol=1e-12)
            for shape in ordered_shapes[1:]
        )
        if heterogeneous and any(not shape[3] for shape in ordered_shapes):
            geometry_issue(
                "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_LANDS",
                f"Heterogeneous padstack {name!r} requires resolved DictionaryStandard primitives on every REGULAR layer.",
                source_id=source_id,
            )
            continue
        land_profiles = [
            {
                "layer_id": layer_name,
                "use": "regular",
                "shape": shape[0],
                "size_mm": [shape[1], shape[2]],
                "source_primitive_id": shape[3],
            }
            for layer_name, shape in zip(land_layers, ordered_shapes)
        ] if all(shape[3] for shape in ordered_shapes) else []

        hole_defs = direct_children(definition, "padstackholedef")
        hole_status = ""
        drill_mm = 0.0
        if len(hole_defs) > 1:
            geometry_issue(
                "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_HOLES",
                f"Padstack {name!r} contains more than one hole definition.",
                source_id=source_id,
            )
            continue
        if hole_defs:
            hole = hole_defs[0]
            attributes = _attributes(hole)
            hole_status = _value(attributes, "platingstatus").upper()
            drill = _finite_float(attributes, "diameter")
            location = one_location(hole, allow_attributes=True)
            if (
                hole_status not in {"PLATED", "VIA"}
                or drill is None
                or drill <= 0.0
                or location is None
                or not math.isclose(location[0], 0.0, abs_tol=1e-12)
                or not math.isclose(location[1], 0.0, abs_tol=1e-12)
            ):
                geometry_issue(
                    "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_HOLES",
                    f"Padstack {name!r} requires one centered circular PLATED or VIA hole.",
                    source_id=source_id,
                )
                continue
            drill_mm = drill * unit_factor
            if (
                any(drill_mm > min(shape[1], shape[2]) for shape in ordered_shapes)
                or (not heterogeneous and any(
                    math.isclose(drill_mm, min(shape[1], shape[2]), rel_tol=1e-9, abs_tol=1e-12)
                    for shape in ordered_shapes
                ))
            ):
                geometry_issue(
                    "IMPORT_IPC2581_PAD_MALFORMED_DRILL",
                    f"Padstack {name!r} drill must be smaller than its copper land.",
                    source_id=source_id,
                )
                continue
        elif len(land_layers) != 1:
            geometry_issue(
                "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_HOLES",
                f"Hole-free padstack {name!r} must have exactly one REGULAR copper land.",
                source_id=source_id,
            )
            continue
        padstacks[name] = {
            # v1 nominal pad fields intentionally retain the first physical
            # copper profile.  The complete layer-by-layer representation is
            # emitted separately below.
            "shape": first_shape[0],
            "width_mm": first_shape[1],
            "height_mm": first_shape[2],
            "drill_mm": drill_mm,
            "hole_status": hole_status,
            "layers": land_layers,
            "layer_shapes": layer_shapes,
            "occurrence_shapes": occurrence_shapes,
            "land_profiles": land_profiles,
        }

    occurrence_groups: Dict[str, list[Dict[str, Any]]] = {}
    unnetted_occurrence_groups: Dict[str, list[Dict[str, Any]]] = {}
    retained_user_primitive_ids: set[str] = set()
    retained_nonregular_occurrences: list[Dict[str, Any]] = []
    retained_contour_land_occurrences: list[Dict[str, Any]] = []
    for layer_feature in (item for item in root.iter() if _local_name(item.tag) == "layerfeature"):
        feature_attributes = _attributes(layer_feature)
        layer_ref = _value(feature_attributes, "layerref", "layer")
        layer_name = layer_lookup.get(layer_ref, "")
        for set_element in (item for item in layer_feature if _local_name(item.tag) == "set"):
            set_attributes = _attributes(set_element)
            net_ref = _value(set_attributes, "netref", "net") or _value(feature_attributes, "netref", "net")
            net_id = net_lookup.get(net_ref, "")
            pad_usage = _value(set_attributes, "padusage").upper()
            for pad in (item for item in set_element.iter() if _local_name(item.tag) == "pad"):
                attributes = _attributes(pad)
                source_index = element_indices[id(pad)]
                raw_id = _value(attributes, "id", "name")
                stack_name = _value(attributes, "padstackdefref", "padstackref")
                location = one_location(pad)
                shape = pad_shape(pad)
                provisional_id = raw_id or f"pad:{source_index}"
                stack = padstacks.get(stack_name)
                user_reference = user_primitive_ref(pad)
                layer_polarity = str(layer_polarities.get(layer_ref, layer_polarities.get(layer_name, ""))).lower()
                matching_nonregular_profiles = (
                    nonregular_profiles.get((stack_name, layer_name, user_reference[0]), [])
                    if user_reference is not None else []
                )
                if (
                    layer_name in copper_layers
                    and layer_polarity == "negative"
                    and pad_usage.lower() == "via"
                    and location is not None
                    and user_reference is not None
                    and len(matching_nonregular_profiles) == 1
                    and net_id
                ):
                    primitive_ref, xform = user_reference
                    definitions = user_special_elements.get(primitive_ref, [])
                    if len(definitions) == 1:
                        if primitive_ref not in parsed_user_specials:
                            definition, definition_id, definition_index, source_units, definition_factor = definitions[0]
                            parsed_user_specials[primitive_ref] = user_special_definition(
                                definition, primitive_id=definition_id, source_index=definition_index,
                                source_units=source_units, factor=definition_factor,
                            )
                        if parsed_user_specials[primitive_ref] is not None:
                            retained_nonregular_occurrences.append({
                                "source_index": source_index,
                                "source_id": provisional_id,
                                "kind": "retained_padstack_nonregular_occurrence",
                                "status": "retained_unresolved",
                                "reason": "negative_plane_user_primitive_semantics_pending",
                                "padstack_ref": stack_name,
                                "layer_id": layer_name,
                                "layer_polarity": "negative",
                                "raw_net_ref": net_ref,
                                "resolved_net_id": net_id,
                                "occurrence_pad_usage": "via",
                                "matched_profile_use": matching_nonregular_profiles[0]["use"],
                                "at_mm": list(location),
                                "xform": xform,
                                "primitive_ref": primitive_ref,
                            })
                            retained_user_primitive_ids.add(primitive_ref)
                            continue
                handled, contour_row = contour_land.retain_standard_contour_land_occurrence(
                    pad, source_index=source_index, source_id=provisional_id, stack_name=stack_name,
                    definitions=contour_land_definitions, stacks=contour_land_padstacks,
                    layer_name=layer_name, layer_ref=layer_ref, layer_polarity=layer_polarity,
                    copper_layers=copper_layers, net_ref=net_ref, net_id=net_id, location=location,
                    component_lookup=component_lookup, component_layer_lookup=component_layer_lookup,
                    unit_factor=unit_factor, set_element=set_element, layer_feature=layer_feature,
                )
                if handled:
                    if contour_row is not None:
                        retained_contour_land_occurrences.append(contour_row)
                    continue
                if not layer_name:
                    geometry_issue(
                        "IMPORT_IPC2581_LAYER_REF_UNRESOLVED",
                        f"Pad occurrence references unknown layer {layer_ref!r}.",
                        source_id=provisional_id,
                    )
                    continue
                if not net_id and net_ref:
                    geometry_issue(
                        "IMPORT_IPC2581_NET_REF_UNRESOLVED",
                        f"Pad occurrence references unknown net {net_ref!r}.",
                        source_id=provisional_id,
                    )
                    continue
                if stack is None:
                    geometry_issue(
                        "IMPORT_IPC2581_PADSTACK_UNSUPPORTED_REFERENCE",
                        f"Pad occurrence references unresolved or unsupported padstack {stack_name!r}.",
                        source_id=provisional_id,
                    )
                    continue
                if layer_name not in copper_layers:
                    if not net_id:
                        geometry_issue(
                            "IMPORT_IPC2581_NET_REF_UNRESOLVED",
                            "Pad occurrence has no native net identity.",
                            source_id=provisional_id,
                        )
                    continue
                matching_profiles = [candidate for _use, candidate in stack["occurrence_shapes"].get(layer_name, [])]
                if (
                    location is None
                    or shape is None
                    or layer_name not in stack["layers"]
                    or not any(
                        candidate[0] == shape[0]
                        and math.isclose(candidate[1], shape[1], rel_tol=1e-9, abs_tol=1e-12)
                        and math.isclose(candidate[2], shape[2], rel_tol=1e-9, abs_tol=1e-12)
                        for candidate in matching_profiles
                    )
                ):
                    geometry_issue(
                        "IMPORT_IPC2581_PAD_MALFORMED_OCCURRENCE",
                        "Pad occurrence must have one finite location and one supported shape matching its padstack land.",
                        source_id=provisional_id,
                    )
                    continue
                pin_refs = direct_children(pad, "pinref")
                if len(pin_refs) > 1:
                    geometry_issue(
                        "IMPORT_IPC2581_PAD_MALFORMED_PIN",
                        "Pad occurrence may contain at most one direct PinRef.",
                        source_id=provisional_id,
                    )
                    continue
                pin: tuple[str, str] | None = None
                if pin_refs:
                    pin_attributes = _attributes(pin_refs[0])
                    component_ref = _value(pin_attributes, "componentref", "component")
                    pin_number = _value(pin_attributes, "pin", "number")
                    if not component_ref or not pin_number or component_ref not in component_lookup:
                        geometry_issue(
                            "IMPORT_IPC2581_PAD_MALFORMED_PIN",
                            "Pad PinRef must resolve a component and provide a pin number.",
                            source_id=provisional_id,
                        )
                        continue
                    pin = (component_ref, pin_number)
                if not net_id:
                    xform = contour_land.source_xform(pad, factor=unit_factor)
                    if pin_refs or pad_usage or xform is None:
                        geometry_issue(
                            "IMPORT_IPC2581_NET_REF_UNRESOLVED",
                            "Unnetted pad occurrence cannot be retained with PinRef, padUsage, or malformed Xform semantics.",
                            source_id=provisional_id,
                        )
                        continue
                    identity = f"ipc2581:unnetted:{stack_name}:{location[0]:.12g}:{location[1]:.12g}"
                    unnetted_occurrence_groups.setdefault(identity, []).append({
                        "source_index": source_index,
                        "source_id": provisional_id,
                        "stack_name": stack_name,
                        "stack": stack,
                        "layer": layer_name,
                        "raw_layer_ref": layer_ref,
                        "layer_polarity": layer_polarity,
                        "location": location,
                        "shape": shape,
                        "xform": xform,
                        "raw_pad_attributes": dict(sorted(attributes.items())),
                        "raw_set_attributes": dict(sorted(set_attributes.items())),
                        "raw_layer_feature_attributes": dict(sorted(feature_attributes.items())),
                    })
                    continue
                identity = raw_id or f"ipc2581:{stack_name}:{net_ref}:{location[0]:.12g}:{location[1]:.12g}"
                occurrence_groups.setdefault(identity, []).append({
                    "source_index": source_index,
                    "source_id": provisional_id,
                    "stack_name": stack_name,
                    "stack": stack,
                    "layer": layer_name,
                    "net_id": net_id,
                    "net_ref": net_ref,
                    "location": location,
                    "shape": shape,
                    "pad_usage": pad_usage,
                    "pin": pin,
                })

    pads: list[Dict[str, Any]] = []
    vias: list[Dict[str, Any]] = []
    incomplete_occurrence_groups: list[Dict[str, Any]] = []
    normalized_occurrences = 0
    retained_unnetted_groups, normalized_unnetted = finalize_unnetted_padstack_groups(
        unnetted_occurrence_groups, geometry_issue=geometry_issue,
    )
    normalized_occurrences += normalized_unnetted
    for identity, occurrences in occurrence_groups.items():
        first = occurrences[0]
        stack = first["stack"]
        expected_layers = list(stack["layers"])
        actual_layers = [str(item["layer"]) for item in occurrences]
        common_fields = {(item["stack_name"], item["net_id"], item["location"]) for item in occurrences}
        if len(common_fields) != 1 or sorted(actual_layers) != sorted(expected_layers) or len(set(actual_layers)) != len(actual_layers):
            # These occurrence records are individually valid, but their group
            # does not establish a complete pad/via or a connectivity relation.
            # Preserve the normalized source facts without projecting them into
            # typed geometry or resolved net/component references.
            if len(common_fields) == 1 and len(set(actual_layers)) == len(actual_layers) and set(actual_layers) < set(expected_layers):
                ordered = sorted(occurrences, key=lambda item: expected_layers.index(item["layer"]))
                incomplete_occurrence_groups.append({
                    "id": identity, "kind": "incomplete_padstack_occurrence_group",
                    "status": "retained_unresolved", "reason": "missing_required_regular_layers",
                    "padstack_ref": first["stack_name"], "net_id": first["net_id"],
                    "at_mm": list(first["location"]), "expected_regular_layer_ids": expected_layers,
                    "observed_layer_ids": [item["layer"] for item in ordered], "occurrence_count": len(ordered),
                    "occurrences": [{
                        "source_index": item["source_index"], "source_id": item["source_id"],
                        "layer_id": item["layer"], "pad_usage": item["pad_usage"], "at_mm": list(item["location"]),
                        "shape": {"kind": item["shape"][0], "size_mm": [item["shape"][1], item["shape"][2]],
                                  "source_primitive_id": item["shape"][3]},
                        "pin": ({"component_id": item["pin"][0], "pin": item["pin"][1]}
                                if item["pin"] is not None else None),
                    } for item in ordered],
                })
                normalized_occurrences += len(ordered)
            geometry_issue(
                "IMPORT_IPC2581_OCCURRENCES_INCOMPLETE",
                f"Pad/via {identity!r} must occur exactly once on every REGULAR padstack layer ({', '.join(expected_layers)}).",
                source_id=identity,
            )
            continue
        pins = {item["pin"] for item in occurrences if item["pin"] is not None}
        usages = {str(item["pad_usage"]) for item in occurrences if item["pad_usage"]}
        is_via = stack["hole_status"] == "VIA" or usages == {"VIA"}
        if "VIA" in usages and usages != {"VIA"}:
            geometry_issue(
                "IMPORT_IPC2581_VIA_MALFORMED_USAGE",
                f"Via {identity!r} has inconsistent padUsage declarations.",
                source_id=identity,
            )
            continue
        if is_via:
            if (
                pins
                or any(profile["shape"] != "circle" for profile in stack["land_profiles"])
                or stack["shape"] != "circle"
                or stack["drill_mm"] <= 0.0
                or stack["hole_status"] not in {"PLATED", "VIA"}
            ):
                geometry_issue(
                    "IMPORT_IPC2581_VIA_MALFORMED_SEMANTICS",
                    "Through-via occurrences require a plated circular hole and no component PinRef.",
                    source_id=identity,
                )
                continue
            vias.append({
                "id": identity,
                "at": list(first["location"]),
                "diameter": max(profile["size_mm"][0] for profile in stack["land_profiles"]) if stack["land_profiles"] else stack["width_mm"],
                "drill": stack["drill_mm"],
                "layers": [expected_layers[0], expected_layers[-1]],
                "net_id": first["net_id"],
                "type": "through",
                "plating_mm": None,
                "ipc2581_padstack": first["stack_name"],
                "ipc2581_occurrences": [item["source_index"] for item in occurrences],
                "land_profiles": stack["land_profiles"],
            })
        else:
            if len(pins) != 1 or (stack["drill_mm"] > 0.0 and stack["hole_status"] != "PLATED"):
                geometry_issue(
                    "IMPORT_IPC2581_PAD_MALFORMED_SEMANTICS",
                    "Component pads require one resolved PinRef and, when drilled, a PLATED hole.",
                    source_id=identity,
                )
                continue
            component_ref, pin_number = next(iter(pins))
            pads.append({
                "id": identity,
                "name": pin_number,
                "component": component_lookup[component_ref],
                "type": "through_hole" if stack["drill_mm"] > 0.0 else "smd",
                "shape": stack["shape"],
                "at": list(first["location"]),
                "size": [stack["width_mm"], stack["height_mm"]],
                "layers": expected_layers,
                "layer": expected_layers[0],
                "net_id": first["net_id"],
                "drill": stack["drill_mm"],
                "drill_size": [stack["drill_mm"], stack["drill_mm"]],
                "drill_shape": "circle" if stack["drill_mm"] > 0.0 else "none",
                "plated": stack["drill_mm"] > 0.0,
                "ipc2581_padstack": first["stack_name"],
                "ipc2581_occurrences": [item["source_index"] for item in occurrences],
                "land_profiles": stack["land_profiles"],
            })
        normalized_occurrences += len(occurrences)

    retained_geometry = {
        "contract": "spike/retained-padstack-geometry/v1",
        "user_primitives": [parsed_user_specials[item] for item in sorted(retained_user_primitive_ids)],
        "occurrences": retained_nonregular_occurrences,
    }
    retained_contour_land_geometry = contour_land.retained_standard_contour_land_geometry(
        contour_land_definitions, contour_land_padstacks, retained_contour_land_occurrences,
    )
    normalized_occurrences += len(retained_contour_land_occurrences)
    return (
        pads, vias, normalized_occurrences, incomplete_occurrence_groups,
        retained_unnetted_groups, retained_geometry, retained_contour_land_geometry,
    )
