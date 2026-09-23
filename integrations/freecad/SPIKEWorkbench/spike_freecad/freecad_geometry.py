"""FreeCAD geometry creation and envelope export helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .constants import (
    EXPORT_ROLES,
    GEOMETRY_CONTRACT,
    MECHANICAL_CONTRACT,
    OBJECT_ROLES,
    ROLE_COLORS,
    SCHEMA_VERSION,
    SUPPORTED_UNITS,
    WORKBENCH_VERSION,
)
from .contracts import ContractError, validate_mechanical_exchange


_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]+")


def _internal_name(value: str, fallback: str) -> str:
    candidate = _SAFE_NAME.sub("_", value).strip("_") or fallback
    if candidate[0].isdigit():
        candidate = f"SPIKE_{candidate}"
    return candidate[:200]


def _unique_name(document: Any, base: str) -> str:
    candidate = base
    index = 2
    while document.getObject(candidate) is not None:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _vector(values: Sequence[float], offset: Sequence[float]) -> Any:
    import FreeCAD as App

    return App.Vector(
        float(values[0]) + float(offset[0]),
        float(values[1]) + float(offset[1]),
        float(values[2]) + float(offset[2]),
    )


def _shape_from_primitive(primitive: Mapping[str, Any], offset: Sequence[float]) -> Any:
    import FreeCAD as App
    import Part

    primitive_type = primitive["type"]
    if primitive_type == "box":
        return Part.makeBox(
            float(primitive["size"][0]),
            float(primitive["size"][1]),
            float(primitive["size"][2]),
            _vector(primitive["origin"], offset),
        )
    if primitive_type == "cylinder":
        axis = primitive.get("axis", [0.0, 0.0, 1.0])
        return Part.makeCylinder(
            float(primitive["radius"]),
            float(primitive["height"]),
            _vector(primitive["center"], offset),
            App.Vector(float(axis[0]), float(axis[1]), float(axis[2])),
        )
    if primitive_type == "polygon_prism":
        z_value = float(primitive["z"]) + float(offset[2])
        points = [
            App.Vector(
                float(point[0]) + float(offset[0]),
                float(point[1]) + float(offset[1]),
                z_value,
            )
            for point in primitive["points"]
        ]
        if not points[0].isEqual(points[-1], 1.0e-9):
            points.append(points[0])
        wire = Part.makePolygon(points)
        face = Part.Face(wire)
        return face.extrude(App.Vector(0.0, 0.0, float(primitive["height"])))
    raise ContractError("$.objects[].primitive.type", f"unsupported primitive {primitive_type!r}")


def _add_read_only_string(obj: Any, name: str, value: str) -> None:
    obj.addProperty("App::PropertyString", name, "SPIKE Exchange")
    setattr(obj, name, value)
    obj.setEditorMode(name, 1)


def _decorate_object(
    obj: Any,
    record: Mapping[str, Any],
    contract: str,
    source_path: str,
) -> None:
    _add_read_only_string(obj, "SPIKEObjectId", str(record["id"]))
    _add_read_only_string(obj, "SPIKEContract", contract)
    _add_read_only_string(obj, "SPIKESourcePath", source_path)
    primitive_json = json.dumps(record["primitive"], sort_keys=True, separators=(",", ":"))
    primitive_digest = hashlib.sha256(primitive_json.encode("utf-8")).hexdigest()
    _add_read_only_string(obj, "SPIKEPrimitiveSHA256", primitive_digest)
    primitive_record = primitive_json
    if len(primitive_record) > 4096:
        primitive_record = f"omitted from property; sha256={primitive_digest}"
    _add_read_only_string(obj, "SPIKEPrimitiveJSON", primitive_record)
    obj.addProperty("App::PropertyEnumeration", "SPIKERole", "SPIKE Exchange")
    obj.SPIKERole = list(OBJECT_ROLES)
    obj.SPIKERole = str(record["role"])
    obj.addProperty("App::PropertyBool", "SPIKEExport", "SPIKE Exchange")
    obj.SPIKEExport = record["role"] in EXPORT_ROLES
    obj.addProperty("App::PropertyString", "SPIKEMetadataJSON", "SPIKE Exchange")
    obj.SPIKEMetadataJSON = json.dumps(
        record.get("metadata", {}),
        sort_keys=True,
        separators=(",", ":"),
    )

    view = getattr(obj, "ViewObject", None)
    if view is not None:
        visual = record.get("visual", {})
        color = tuple(visual.get("color", ROLE_COLORS[record["role"]]))
        opacity = float(visual.get("opacity", 0.45 if record["role"] == "keepout" else 1.0))
        view.ShapeColor = tuple(float(component) for component in color)
        view.LineColor = tuple(float(component) for component in color)
        view.Transparency = int(round((1.0 - opacity) * 100.0))


def import_geometry_exchange(
    document: Any,
    payload: Mapping[str, Any],
    source_path: str,
) -> List[Any]:
    """Create validated primitive solids in an existing FreeCAD document."""

    design = payload["design"]
    offset = payload["coordinate_system"]["origin"]
    group_base = _internal_name(f"SPIKE_{design['name']}", "SPIKE_Exchange")
    imported: List[Any] = []
    document.openTransaction("Import SPIKE geometry exchange")
    try:
        group = document.addObject("App::DocumentObjectGroup", _unique_name(document, group_base))
        group.Label = f"SPIKE: {design['name']}"
        _add_read_only_string(group, "SPIKEContract", str(payload["contract"]))
        _add_read_only_string(group, "SPIKEDesignId", str(design["id"]))
        _add_read_only_string(group, "SPIKESourcePath", source_path)

        for index, record in enumerate(payload["objects"]):
            base = _internal_name(str(record["id"]), f"SPIKE_Object_{index + 1}")
            obj = document.addObject("Part::Feature", _unique_name(document, base))
            obj.Label = str(record["name"])
            obj.Shape = _shape_from_primitive(record["primitive"], offset)
            if obj.Shape.isNull():
                raise ContractError(f"$.objects[{index}].primitive", "FreeCAD produced a null shape")
            _decorate_object(obj, record, str(payload["contract"]), source_path)
            group.addObject(obj)
            imported.append(obj)
        document.recompute()
    except Exception:
        document.abortTransaction()
        raise
    else:
        document.commitTransaction()
    return imported


def exportable_objects(document: Any, selected: Iterable[Any]) -> List[Any]:
    """Return selected shape objects, or explicitly tagged document objects."""

    selected_shapes = [obj for obj in selected if getattr(obj, "Shape", None) is not None]
    candidates = selected_shapes or [
        obj
        for obj in document.Objects
        if bool(getattr(obj, "SPIKEExport", False)) and getattr(obj, "Shape", None) is not None
    ]
    unique: Dict[str, Any] = {}
    for obj in candidates:
        unique[str(obj.Name)] = obj
    return list(unique.values())


def _object_role(obj: Any, fallback: Optional[str]) -> str:
    role = str(getattr(obj, "SPIKERole", ""))
    if role in EXPORT_ROLES:
        return role
    if fallback in EXPORT_ROLES:
        return str(fallback)
    raise ContractError(
        f"$.objects[{obj.Name}].role",
        "object is not tagged as component_envelope or keepout",
    )


def _box_record(obj: Any, role: str, identifier: str) -> Dict[str, Any]:
    bounds = obj.Shape.BoundBox
    values = (
        bounds.XMin,
        bounds.YMin,
        bounds.ZMin,
        bounds.XLength,
        bounds.YLength,
        bounds.ZLength,
    )
    if not all(math.isfinite(float(value)) for value in values):
        raise ContractError(f"$.objects[{obj.Name}]", "shape has non-finite bounds")
    if min(float(bounds.XLength), float(bounds.YLength), float(bounds.ZLength)) <= 0.0:
        raise ContractError(
            f"$.objects[{obj.Name}]",
            "mechanical exchange requires a three-dimensional solid envelope",
        )
    metadata: Dict[str, Any] = {}
    raw_metadata = str(getattr(obj, "SPIKEMetadataJSON", ""))
    if raw_metadata:
        try:
            parsed = json.loads(raw_metadata)
            if isinstance(parsed, dict):
                metadata = {
                    str(key): value
                    for key, value in parsed.items()
                    if value is None or isinstance(value, (str, bool, int, float))
                }
        except (TypeError, ValueError):
            metadata = {}
    metadata["export_note"] = "Global axis-aligned bounding box; not exact B-Rep geometry."
    return {
        "id": identifier,
        "name": str(obj.Label or obj.Name),
        "role": role,
        "representation": "axis_aligned_bounding_box",
        "primitive": {
            "type": "box",
            "origin": [float(bounds.XMin), float(bounds.YMin), float(bounds.ZMin)],
            "size": [float(bounds.XLength), float(bounds.YLength), float(bounds.ZLength)],
        },
        "source": {
            "freecad_name": str(obj.Name),
            "freecad_type_id": str(obj.TypeId),
        },
        "metadata": metadata,
    }


def build_mechanical_exchange(
    document: Any,
    objects: Sequence[Any],
    fallback_role: Optional[str] = None,
) -> Mapping[str, Any]:
    """Build a validated AABB envelope/keepout exchange payload."""

    import FreeCAD as App

    records = []
    used_identifiers = set()
    for index, obj in enumerate(objects):
        base_identifier = str(getattr(obj, "SPIKEObjectId", "") or f"freecad/{obj.Name}")
        identifier = base_identifier
        suffix = 2
        while identifier in used_identifiers:
            identifier = f"{base_identifier}/{suffix}"
            suffix += 1
        used_identifiers.add(identifier)
        records.append(_box_record(obj, _object_role(obj, fallback_role), identifier))

    freecad_version = ".".join(str(value) for value in App.Version()[:3])
    payload: Mapping[str, Any] = {
        "contract": MECHANICAL_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "units": SUPPORTED_UNITS,
        "coordinate_system": {
            "handedness": "right",
            "up_axis": "Z",
            "origin": [0.0, 0.0, 0.0],
        },
        "generator": {
            "name": "SPIKE FreeCAD Workbench",
            "version": WORKBENCH_VERSION,
            "freecad_version": freecad_version,
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_document": {
            "name": str(document.Name),
            "label": str(document.Label or document.Name),
        },
        "objects": records,
    }
    validate_mechanical_exchange(payload)
    return payload


__all__ = [
    "build_mechanical_exchange",
    "exportable_objects",
    "import_geometry_exchange",
]
