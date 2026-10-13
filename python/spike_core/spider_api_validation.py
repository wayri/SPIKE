# SPDX-License-Identifier: Apache-2.0
"""Bounded validation helpers for the read-only SpiDeR interoperability API."""

from __future__ import annotations

import json
import math
from dataclasses import fields
from typing import Any, Mapping

from .contracts import SpiDeR
from .designir_compat import from_designir
from .spider_v2 import SpiDeRV2
from .spider_v2_schema import content_digest


API_RESULT_CONTRACT = "spider/api-result/v1"
ENTITY_TYPES = (
    "materials", "layers", "nets", "tracks", "arcs", "zones", "pads", "vias",
    "drills", "castellations", "pins", "components", "component_bonds",
    "connectors", "regions", "bends", "models", "constraints", "variants",
    "simulation_models",
)
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_ENTITIES = 100_000
MAX_DEPTH = 64
MAX_NODES = 1_000_000
V1_COLLECTIONS = (
    "layers", "nets", "tracks", "vias", "pads", "zones", "components",
    "component_bonds", "connectors", "stackup", "regions", "bends",
)
V1_REQUIRED = (
    "contract", "design_id", "name", "source_format", "units", "layers", "nets",
    "tracks", "vias", "pads", "zones", "components", "stackup", "issues", "metadata",
)


def issue(code: str, message: str, path: str = "", severity: str = "error") -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "path": path}


def revision_of(document: Mapping[str, Any]) -> str | None:
    try:
        return content_digest(document)
    except (TypeError, ValueError, RecursionError, OverflowError):
        return None


def source_revision_of(document: Mapping[str, Any], revision: str | None) -> tuple[str | None, str]:
    if document.get("contract") == "spike/design-ir/v2":
        source = document.get("source")
        value = source.get("source_digest") if isinstance(source, Mapping) else None
    else:
        metadata = document.get("metadata")
        value = metadata.get("source_sha256") if isinstance(metadata, Mapping) else None
    if isinstance(value, str) and value:
        return value, "declared"
    return revision, "derived_document_revision"


def _bounded_json(document: Any, add: Any) -> None:
    try:
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        add(issue("spider.invalid_json_value", str(exc), "/"))
        return
    if len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        add(issue("spider.document_too_large", f"Inline document exceeds {MAX_DOCUMENT_BYTES} bytes.", "/"))
    stack = [(document, 0, "/")]
    nodes = 0
    while stack:
        value, depth, path = stack.pop()
        nodes += 1
        if nodes > MAX_NODES:
            add(issue("spider.document_too_complex", f"Document exceeds {MAX_NODES} JSON values.", path))
            return
        if depth > MAX_DEPTH:
            add(issue("spider.document_too_deep", f"Document nesting exceeds {MAX_DEPTH} levels.", path))
            return
        if isinstance(value, float) and not math.isfinite(value):
            add(issue("spider.nonfinite_number", "Numeric values must be finite.", path))
        elif isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    add(issue("spider.invalid_object_key", "Object keys must be strings.", path))
                    continue
                stack.append((child, depth + 1, f"{path.rstrip('/')}/{key}"))
        elif isinstance(value, (list, tuple)):
            stack.extend((child, depth + 1, f"{path.rstrip('/')}/{index}") for index, child in enumerate(value))
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            add(issue("spider.invalid_json_value", f"Unsupported value type {type(value).__name__}.", path))


def _records(document: Mapping[str, Any], names: tuple[str, ...], add: Any) -> None:
    total = 0
    for name in names:
        values = document.get(name, [])
        if not isinstance(values, list):
            add(issue("spider.invalid_collection", "Entity collection must be an array.", f"/{name}"))
            continue
        total += len(values)
        if len(values) > MAX_ENTITIES:
            add(issue("spider.collection_too_large", f"Collection exceeds {MAX_ENTITIES} entities.", f"/{name}"))
        for index, value in enumerate(values):
            if not isinstance(value, Mapping):
                add(issue("spider.invalid_entity", "Entity must be an object.", f"/{name}/{index}"))
    if total > MAX_ENTITIES:
        add(issue("spider.too_many_entities", f"Document exceeds {MAX_ENTITIES} total entities.", "/"))


def _duplicates(document: Mapping[str, Any], names: tuple[str, ...], add: Any, *, global_ids: bool) -> None:
    all_ids: dict[str, str] = {}
    for name in names:
        seen_ids: dict[str, int] = {}
        seen_sources: dict[str, int] = {}
        values = document.get(name, [])
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if not isinstance(value, Mapping):
                continue
            entity_id = value.get("id")
            if isinstance(entity_id, str) and entity_id:
                prior = all_ids.get(entity_id) if global_ids else str(seen_ids.get(entity_id, ""))
                if prior:
                    add(issue("spider.duplicate_entity_id", f"Duplicate entity id {entity_id!r} (first at {prior}).", f"/{name}/{index}/id"))
                all_ids[entity_id] = f"/{name}/{index}/id"
                seen_ids[entity_id] = index
            source_id = value.get("source_id")
            if isinstance(source_id, str) and source_id:
                if source_id in seen_sources:
                    add(issue("spider.duplicate_source_id", f"Duplicate {name} source_id {source_id!r}.", f"/{name}/{index}/source_id"))
                seen_sources[source_id] = index


def _known(document: Mapping[str, Any], name: str, aliases: tuple[str, ...] = ()) -> set[str]:
    result: set[str] = set()
    values = document.get(name, [])
    if not isinstance(values, list):
        return result
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for key in ("id", "source_id", "name", *aliases):
            item = value.get(key)
            if isinstance(item, str) and item:
                result.add(item)
    return result


def _check_ref(value: Any, known: set[str], path: str, kind: str, add: Any) -> None:
    if isinstance(value, str) and value and value not in known:
        add(issue("spider.dangling_reference", f"Reference to unknown {kind} {value!r}.", path))


def _number(value: Any, path: str, add: Any, *, minimum: float | None = None, exclusive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        add(issue("spider.invalid_number", "Value must be a finite number and not a boolean.", path))
    elif minimum is not None and (value < minimum or (exclusive and value == minimum)):
        relation = "greater than" if exclusive else "at least"
        add(issue("spider.invalid_physical_value", f"Value must be {relation} {minimum}.", path))


def _point(value: Any, path: str, add: Any, *, positive: bool = False) -> None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        add(issue("spider.invalid_point", "Point must contain exactly two numeric coordinates.", path))
        return
    for index, coordinate in enumerate(value):
        _number(coordinate, f"{path}/{index}", add, minimum=0.0 if positive else None, exclusive=positive)


def _v2_numeric_checks(document: Mapping[str, Any], add: Any) -> None:
    frame = document.get("frame")
    if isinstance(frame, Mapping):
        transform = frame.get("transform")
        if not isinstance(transform, (list, tuple)) or len(transform) != 16:
            add(issue("spider.invalid_transform", "Coordinate-frame transform must contain 16 numbers.", "/frame/transform"))
        else:
            for index, value in enumerate(transform):
                _number(value, f"/frame/transform/{index}", add)
    scalar_rules: dict[str, dict[str, tuple[float | None, bool]]] = {
        "materials": {
            "conductivity_s_per_m": (0.0, False), "relative_permittivity": (0.0, True),
            "loss_tangent": (0.0, False), "thermal_conductivity_w_per_mk": (0.0, False),
            "density_kg_per_m3": (0.0, True), "heat_capacity_j_per_kgk": (0.0, True),
        },
        "layers": {"z_mm": (None, False), "thickness_mm": (0.0, True)},
        "tracks": {"width_mm": (0.0, True)}, "arcs": {"width_mm": (0.0, True)},
        "vias": {"diameter_mm": (0.0, True), "drill_mm": (0.0, True), "plating_mm": (0.0, False)},
        "castellations": {"retained_fraction": (0.0, True)},
        "components": {"rotation_deg": (None, False)},
        "component_bonds": {"contact_area_mm2": (0.0, True), "thickness_mm": (0.0, True)},
        "bends": {"angle_deg": (None, False), "radius_mm": (0.0, True)},
    }
    point_rules: dict[str, tuple[str, ...]] = {
        "tracks": ("start_mm", "end_mm"), "arcs": ("start_mm", "mid_mm", "end_mm"),
        "pads": ("center_mm", "size_mm", "drill_size_mm"), "vias": ("center_mm",),
        "drills": ("center_mm",), "components": ("position_mm",),
        "bends": ("line_start_mm", "line_end_mm"),
    }
    for collection in ENTITY_TYPES:
        values = document.get(collection, [])
        if not isinstance(values, list):
            continue
        for index, entity in enumerate(values):
            if not isinstance(entity, Mapping):
                continue
            if not isinstance(entity.get("id"), str) or not entity.get("id"):
                add(issue("spider.invalid_entity_id", "Typed entities require a non-empty string id.", f"/{collection}/{index}/id"))
            if "source_id" in entity and not isinstance(entity.get("source_id"), str):
                add(issue("spider.invalid_source_id", "source_id must be a string.", f"/{collection}/{index}/source_id"))
            for field_name, (minimum, exclusive) in scalar_rules.get(collection, {}).items():
                if entity.get(field_name) is not None:
                    _number(entity[field_name], f"/{collection}/{index}/{field_name}", add, minimum=minimum, exclusive=exclusive)
            for field_name in point_rules.get(collection, ()):
                if field_name in entity:
                    _point(entity[field_name], f"/{collection}/{index}/{field_name}", add, positive=field_name in {"size_mm", "drill_size_mm"})
            for polygon_field in ("outlines_mm", "holes_mm", "source_zone_outline_paths_mm"):
                polygons = entity.get(polygon_field)
                if polygons is None:
                    continue
                if not isinstance(polygons, list):
                    add(issue("spider.invalid_polygon_collection", "Polygon collection must be an array.", f"/{collection}/{index}/{polygon_field}"))
                    continue
                for polygon_index, polygon in enumerate(polygons):
                    if not isinstance(polygon, list):
                        add(issue("spider.invalid_polygon", "Polygon must be an array of points.", f"/{collection}/{index}/{polygon_field}/{polygon_index}"))
                        continue
                    for point_index, point_value in enumerate(polygon):
                        _point(point_value, f"/{collection}/{index}/{polygon_field}/{polygon_index}/{point_index}", add)


def _v1_checks(document: Mapping[str, Any], add: Any) -> None:
    for name in V1_REQUIRED:
        if name not in document:
            add(issue("spider.missing_field", f"Required field {name!r} is missing.", f"/{name}"))
    if document.get("units") != "mm":
        add(issue("spider.unsupported_units", "SpiDeR v1 canonical units must be 'mm'.", "/units"))
    _records(document, V1_COLLECTIONS, add)
    _duplicates(document, V1_COLLECTIONS, add, global_ids=False)
    nets = _known(document, "nets", ("net_name",))
    layers = _known(document, "layers", ("layer",))
    components = _known(document, "components", ("reference",))
    regions = _known(document, "regions")
    for collection in ("tracks", "vias", "pads", "zones"):
        values = document.get(collection, [])
        if not isinstance(values, list):
            continue
        for index, entity in enumerate(values):
            if not isinstance(entity, Mapping):
                continue
            for key in ("net_id", "net_name", "net"):
                if key in entity:
                    _check_ref(entity[key], nets, f"/{collection}/{index}/{key}", "net", add)
            layer_values = entity.get("layers", [])
            if "layer" in entity:
                layer_values = [entity["layer"]]
            if "layer_id" in entity:
                layer_values = [entity["layer_id"]]
            if isinstance(layer_values, list):
                for offset, layer in enumerate(layer_values):
                    _check_ref(layer, layers, f"/{collection}/{index}/layers/{offset}", "layer", add)
            if "component_id" in entity:
                _check_ref(entity["component_id"], components, f"/{collection}/{index}/component_id", "component", add)
    for index, bend in enumerate(document.get("bends", []) if isinstance(document.get("bends", []), list) else []):
        if isinstance(bend, Mapping) and "region_id" in bend:
            _check_ref(bend["region_id"], regions, f"/bends/{index}/region_id", "region", add)


V2_REFS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    "layers": (("material_id", "materials", False), ("region_ids", "regions", True)),
    "tracks": (("net_id", "nets", False), ("layer_id", "layers", False)),
    "arcs": (("net_id", "nets", False), ("layer_id", "layers", False)),
    "zones": (("net_id", "nets", False), ("layer_ids", "layers", True)),
    "pads": (("net_id", "nets", False), ("component_id", "components", False), ("pin_id", "pins", False), ("layer_ids", "layers", True)),
    "vias": (("net_id", "nets", False), ("start_layer_id", "layers", False), ("end_layer_id", "layers", False)),
    "drills": (("source_layer_id", "layers", False), ("net_id", "nets", False), ("component_id", "components", False), ("span_layer_ids", "layers", True)),
    "castellations": (("net_id", "nets", False), ("via_id", "vias", False), ("boundary_region_id", "regions", False)),
    "pins": (("component_id", "components", False), ("net_id", "nets", False), ("pad_ids", "pads", True)),
    "components": (("pin_ids", "pins", True), ("model_ids", "models", True)),
    "component_bonds": (("component_id", "components", False), ("pin_id", "pins", False), ("pad_id", "pads", False), ("electrical_material_id", "materials", False), ("thermal_material_id", "materials", False)),
    "connectors": (("component_id", "components", False), ("pin_ids", "pins", True), ("mating_connector_id", "connectors", False)),
    "regions": (("layer_ids", "layers", True),),
    "bends": (("region_id", "regions", False),),
}


def _v2_checks(document: Mapping[str, Any], add: Any) -> None:
    for name in ("contract", "design_id", "name", "source", "frame"):
        if name not in document:
            add(issue("spider.missing_field", f"Required field {name!r} is missing.", f"/{name}"))
    allowed = {field.name for field in fields(SpiDeRV2)}
    for key in document:
        if key not in allowed:
            add(issue("spider.unknown_field", f"Unknown SpiDeR v2 field {key!r}.", f"/{key}"))
    source = document.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("source_digest"), str) or not source.get("source_digest"):
        add(issue("spider.invalid_source", "SpiDeR v2 requires a non-empty source.source_digest.", "/source/source_digest"))
    elif not isinstance(source.get("source_format"), str) or not source.get("source_format"):
        add(issue("spider.invalid_source", "SpiDeR v2 requires a non-empty source.source_format.", "/source/source_format"))
    frame = document.get("frame")
    if not isinstance(frame, Mapping) or frame.get("units") != "mm" or frame.get("handedness") != "right":
        add(issue("spider.unsupported_units", "SpiDeR v2 frame must be right-handed and use 'mm'.", "/frame"))
    _records(document, ENTITY_TYPES, add)
    _duplicates(document, ENTITY_TYPES, add, global_ids=True)
    _v2_numeric_checks(document, add)
    for field_name in ("metadata", "vendor_extensions"):
        if field_name in document and not isinstance(document[field_name], Mapping):
            add(issue("spider.invalid_object", f"{field_name} must be an object.", f"/{field_name}"))
    issues_value = document.get("issues", [])
    if not isinstance(issues_value, list) or any(not isinstance(value, Mapping) for value in issues_value):
        add(issue("spider.invalid_issues", "issues must be an array of issue objects.", "/issues"))
    for collection in ENTITY_TYPES:
        values = document.get(collection, [])
        if not isinstance(values, list):
            continue
        for index, entity in enumerate(values):
            if not isinstance(entity, Mapping):
                continue
            if "extensions" in entity and not isinstance(entity["extensions"], Mapping):
                add(issue("spider.invalid_extensions", "extensions must be an object.", f"/{collection}/{index}/extensions"))
            if collection in {"constraints", "variants", "simulation_models"} and "data" in entity and not isinstance(entity["data"], Mapping):
                add(issue("spider.invalid_named_record", "Named-record data must be an object.", f"/{collection}/{index}/data"))
    known = {name: _known(document, name) for name in ENTITY_TYPES}
    for collection, specs in V2_REFS.items():
        values = document.get(collection, [])
        if not isinstance(values, list):
            continue
        for index, entity in enumerate(values):
            if not isinstance(entity, Mapping):
                continue
            for field_name, target, many in specs:
                value = entity.get(field_name)
                if many:
                    if value is None:
                        continue
                    if not isinstance(value, list):
                        add(issue("spider.invalid_reference_list", "Reference collection must be an array.", f"/{collection}/{index}/{field_name}"))
                        continue
                    for offset, item in enumerate(value):
                        _check_ref(item, known[target], f"/{collection}/{index}/{field_name}/{offset}", target, add)
                else:
                    _check_ref(value, known[target], f"/{collection}/{index}/{field_name}", target, add)
            if collection == "drills" and entity.get("owner_kind") in {"pad", "via"}:
                target = f"{entity['owner_kind']}s"
                _check_ref(entity.get("owner_id"), known[target], f"/drills/{index}/owner_id", target, add)


def validate_document(document: Any, max_issues: int = 200) -> tuple[Any | None, dict[str, Any]]:
    """Validate one inline v1/v2 document and hydrate it only after clean checks."""
    issues: list[dict[str, str]] = []
    overflow = False

    def add(value: dict[str, str]) -> None:
        nonlocal overflow
        if len(issues) < max_issues:
            issues.append(value)
        else:
            overflow = True

    if not isinstance(document, Mapping):
        add(issue("spider.invalid_document", "document must be a JSON object.", "/"))
        return None, {"issues": issues, "issues_truncated": overflow}
    _bounded_json(document, add)
    contract = document.get("contract")
    if contract == "spike/v1":
        _v1_checks(document, add)
    elif contract == "spike/design-ir/v2":
        _v2_checks(document, add)
    else:
        add(issue("spider.unsupported_contract", "Supported contracts are 'spike/v1' and 'spike/design-ir/v2'.", "/contract"))
    model = None
    if not any(value["severity"] == "error" for value in issues) and not overflow:
        try:
            model = from_designir(document)
        except (TypeError, ValueError, KeyError) as exc:
            add(issue("spider.invalid_contract_value", str(exc), "/"))
    revision = revision_of(document)
    source_revision, source_revision_kind = source_revision_of(document, revision)
    return model, {
        "document_contract": contract,
        "document_revision": revision,
        "source_revision": source_revision,
        "source_revision_kind": source_revision_kind,
        "issues": issues,
        "issues_truncated": overflow,
    }


def as_v2(model: SpiDeR | SpiDeRV2, source_revision: str) -> SpiDeRV2:
    if isinstance(model, SpiDeRV2):
        return model
    return SpiDeRV2.from_v1(model, source_digest=source_revision)
