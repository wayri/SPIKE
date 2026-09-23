"""Strict JSON contracts for SPIKE ECAD/MCAD exchange.

This module deliberately has no FreeCAD dependency. It parses JSON as inert
data, rejects duplicate keys and non-finite numbers, applies resource limits,
and accepts only explicitly supported schema versions and primitives.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Union

from .constants import (
    EXPORT_ROLES,
    GEOMETRY_CONTRACT,
    MAX_ABS_COORDINATE_MM,
    MAX_DIMENSION_MM,
    MAX_DOCUMENT_NODES,
    MAX_FILE_BYTES,
    MAX_METADATA_ENTRIES,
    MAX_NESTING_DEPTH,
    MAX_OBJECTS,
    MAX_POLYGON_POINTS,
    MAX_STRING_LENGTH,
    MECHANICAL_CONTRACT,
    OBJECT_ROLES,
    SCHEMA_VERSION,
    SUPPORTED_UNITS,
)


class ContractError(ValueError):
    """Raised when an exchange document violates its declared contract."""

    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("$", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError("$", f"non-finite JSON number {value!r} is not allowed")


def _parse_json_bytes(raw: bytes) -> Any:
    if len(raw) > MAX_FILE_BYTES:
        raise ContractError("$", f"file exceeds the {MAX_FILE_BYTES} byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("$", "file must be UTF-8 JSON") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("$", f"invalid JSON: {exc}") from exc
    _validate_resource_limits(value)
    return value


def _validate_resource_limits(root: Any) -> None:
    nodes = 0
    stack = [(root, 0)]
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_DOCUMENT_NODES:
            raise ContractError("$", "document contains too many JSON values")
        if depth > MAX_NESTING_DEPTH:
            raise ContractError("$", "document nesting is too deep")
        if isinstance(value, str):
            if len(value) > MAX_STRING_LENGTH:
                raise ContractError("$", "document contains an oversized string")
        elif isinstance(value, Mapping):
            for key in value:
                if len(key) > MAX_STRING_LENGTH:
                    raise ContractError("$", "document contains an oversized object key")
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(path, "expected an object")
    return value


def _list(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ContractError(path, "expected an array")
    return value


def _keys(
    value: Mapping[str, Any],
    path: str,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = sorted(required_set - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ContractError(path, f"missing required keys: {', '.join(missing)}")
    if unknown:
        raise ContractError(path, f"unsupported keys: {', '.join(unknown)}")


def _string(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ContractError(path, "expected a string")
    if not allow_empty and not value.strip():
        raise ContractError(path, "must not be empty")
    if len(value) > MAX_STRING_LENGTH:
        raise ContractError(path, "string is too long")
    return value


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(path, "expected an integer")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(path, "expected a number")
    result = float(value)
    if not math.isfinite(result):
        raise ContractError(path, "number must be finite")
    return result


def _coordinate(value: Any, path: str, length: int) -> List[float]:
    items = _list(value, path)
    if len(items) != length:
        raise ContractError(path, f"expected exactly {length} coordinates")
    result = [_number(item, f"{path}[{index}]") for index, item in enumerate(items)]
    if any(abs(item) > MAX_ABS_COORDINATE_MM for item in result):
        raise ContractError(path, "coordinate exceeds the supported range")
    return result


def _dimension(value: Any, path: str) -> float:
    result = _number(value, path)
    if result <= 0.0 or result > MAX_DIMENSION_MM:
        raise ContractError(path, "dimension must be positive and within range")
    return result


def _enum(value: Any, path: str, allowed: Iterable[str]) -> str:
    result = _string(value, path)
    allowed_values = tuple(allowed)
    if result not in allowed_values:
        raise ContractError(path, f"expected one of: {', '.join(allowed_values)}")
    return result


def _metadata(value: Any, path: str) -> None:
    mapping = _mapping(value, path)
    if len(mapping) > MAX_METADATA_ENTRIES:
        raise ContractError(path, "metadata has too many entries")
    for key, item in mapping.items():
        _string(key, f"{path}.<key>")
        item_path = f"{path}.{key}"
        if item is None or isinstance(item, (str, bool)):
            if isinstance(item, str):
                _string(item, item_path, allow_empty=True)
            continue
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            _number(item, item_path)
            continue
        raise ContractError(item_path, "metadata values must be scalar JSON values")


def _coordinate_system(value: Any, path: str) -> None:
    mapping = _mapping(value, path)
    _keys(mapping, path, ("handedness", "up_axis", "origin"))
    if mapping["handedness"] != "right":
        raise ContractError(f"{path}.handedness", "only right-handed coordinates are supported")
    if mapping["up_axis"] != "Z":
        raise ContractError(f"{path}.up_axis", "only Z-up coordinates are supported")
    _coordinate(mapping["origin"], f"{path}.origin", 3)


def _generator(value: Any, path: str) -> None:
    mapping = _mapping(value, path)
    _keys(mapping, path, ("name", "version"), ("freecad_version",))
    _string(mapping["name"], f"{path}.name")
    _string(mapping["version"], f"{path}.version")
    if "freecad_version" in mapping:
        _string(mapping["freecad_version"], f"{path}.freecad_version")


def _box_primitive(value: Mapping[str, Any], path: str) -> None:
    _keys(value, path, ("type", "origin", "size"))
    _coordinate(value["origin"], f"{path}.origin", 3)
    size = _list(value["size"], f"{path}.size")
    if len(size) != 3:
        raise ContractError(f"{path}.size", "expected exactly three dimensions")
    for index, item in enumerate(size):
        _dimension(item, f"{path}.size[{index}]")


def _cylinder_primitive(value: Mapping[str, Any], path: str) -> None:
    _keys(value, path, ("type", "center", "radius", "height"), ("axis",))
    _coordinate(value["center"], f"{path}.center", 3)
    _dimension(value["radius"], f"{path}.radius")
    _dimension(value["height"], f"{path}.height")
    axis = _coordinate(value.get("axis", [0.0, 0.0, 1.0]), f"{path}.axis", 3)
    if math.sqrt(sum(item * item for item in axis)) < 1.0e-12:
        raise ContractError(f"{path}.axis", "axis vector must be non-zero")


def _polygon_prism_primitive(value: Mapping[str, Any], path: str) -> None:
    _keys(value, path, ("type", "points", "z", "height"))
    points = _list(value["points"], f"{path}.points")
    if len(points) < 3:
        raise ContractError(f"{path}.points", "a polygon needs at least three points")
    if len(points) > MAX_POLYGON_POINTS:
        raise ContractError(f"{path}.points", "polygon has too many points")
    normalized = [
        _coordinate(point, f"{path}.points[{index}]", 2)
        for index, point in enumerate(points)
    ]
    z_value = _number(value["z"], f"{path}.z")
    if abs(z_value) > MAX_ABS_COORDINATE_MM:
        raise ContractError(f"{path}.z", "coordinate exceeds the supported range")
    _dimension(value["height"], f"{path}.height")
    area_twice = 0.0
    for index, point in enumerate(normalized):
        next_point = normalized[(index + 1) % len(normalized)]
        area_twice += point[0] * next_point[1] - next_point[0] * point[1]
    if abs(area_twice) < 1.0e-12:
        raise ContractError(f"{path}.points", "polygon area must be non-zero")


def _primitive(value: Any, path: str, *, boxes_only: bool = False) -> None:
    mapping = _mapping(value, path)
    primitive_type = _string(mapping.get("type"), f"{path}.type")
    if primitive_type == "box":
        _box_primitive(mapping, path)
    elif not boxes_only and primitive_type == "cylinder":
        _cylinder_primitive(mapping, path)
    elif not boxes_only and primitive_type == "polygon_prism":
        _polygon_prism_primitive(mapping, path)
    else:
        supported = "box" if boxes_only else "box, cylinder, polygon_prism"
        raise ContractError(f"{path}.type", f"unsupported primitive; expected {supported}")


def _visual(value: Any, path: str) -> None:
    mapping = _mapping(value, path)
    _keys(mapping, path, (), ("color", "opacity"))
    if "color" in mapping:
        color = _list(mapping["color"], f"{path}.color")
        if len(color) != 3:
            raise ContractError(f"{path}.color", "expected three RGB components")
        for index, item in enumerate(color):
            component = _number(item, f"{path}.color[{index}]")
            if component < 0.0 or component > 1.0:
                raise ContractError(f"{path}.color[{index}]", "RGB component must be from 0 to 1")
    if "opacity" in mapping:
        opacity = _number(mapping["opacity"], f"{path}.opacity")
        if opacity < 0.0 or opacity > 1.0:
            raise ContractError(f"{path}.opacity", "opacity must be from 0 to 1")


def validate_geometry_exchange(value: Any) -> Mapping[str, Any]:
    """Validate and return a SPIKE-to-FreeCAD geometry exchange document."""

    root = _mapping(value, "$")
    _keys(
        root,
        "$",
        ("contract", "schema_version", "units", "coordinate_system", "design", "objects"),
        ("generator", "metadata"),
    )
    if root["contract"] != GEOMETRY_CONTRACT:
        raise ContractError("$.contract", f"expected {GEOMETRY_CONTRACT!r}")
    if _integer(root["schema_version"], "$.schema_version") != SCHEMA_VERSION:
        raise ContractError("$.schema_version", f"only schema version {SCHEMA_VERSION} is supported")
    if root["units"] != SUPPORTED_UNITS:
        raise ContractError("$.units", f"only {SUPPORTED_UNITS!r} units are supported")
    _coordinate_system(root["coordinate_system"], "$.coordinate_system")

    design = _mapping(root["design"], "$.design")
    _keys(design, "$.design", ("id", "name"), ("revision",))
    _string(design["id"], "$.design.id")
    _string(design["name"], "$.design.name")
    if "revision" in design:
        _string(design["revision"], "$.design.revision", allow_empty=True)
    if "generator" in root:
        _generator(root["generator"], "$.generator")
    if "metadata" in root:
        _metadata(root["metadata"], "$.metadata")

    objects = _list(root["objects"], "$.objects")
    if len(objects) > MAX_OBJECTS:
        raise ContractError("$.objects", f"at most {MAX_OBJECTS} objects are supported")
    identifiers = set()
    for index, item in enumerate(objects):
        path = f"$.objects[{index}]"
        obj = _mapping(item, path)
        _keys(obj, path, ("id", "name", "role", "primitive"), ("visual", "metadata"))
        identifier = _string(obj["id"], f"{path}.id")
        if identifier in identifiers:
            raise ContractError(f"{path}.id", f"duplicate object id {identifier!r}")
        identifiers.add(identifier)
        _string(obj["name"], f"{path}.name")
        _enum(obj["role"], f"{path}.role", OBJECT_ROLES)
        _primitive(obj["primitive"], f"{path}.primitive")
        if "visual" in obj:
            _visual(obj["visual"], f"{path}.visual")
        if "metadata" in obj:
            _metadata(obj["metadata"], f"{path}.metadata")
    return root


def validate_mechanical_exchange(value: Any) -> Mapping[str, Any]:
    """Validate and return a FreeCAD-to-SPIKE envelope/keepout document."""

    root = _mapping(value, "$")
    _keys(
        root,
        "$",
        (
            "contract",
            "schema_version",
            "units",
            "coordinate_system",
            "generator",
            "generated_at",
            "source_document",
            "objects",
        ),
    )
    if root["contract"] != MECHANICAL_CONTRACT:
        raise ContractError("$.contract", f"expected {MECHANICAL_CONTRACT!r}")
    if _integer(root["schema_version"], "$.schema_version") != SCHEMA_VERSION:
        raise ContractError("$.schema_version", f"only schema version {SCHEMA_VERSION} is supported")
    if root["units"] != SUPPORTED_UNITS:
        raise ContractError("$.units", f"only {SUPPORTED_UNITS!r} units are supported")
    _coordinate_system(root["coordinate_system"], "$.coordinate_system")
    _generator(root["generator"], "$.generator")
    _string(root["generated_at"], "$.generated_at")

    source = _mapping(root["source_document"], "$.source_document")
    _keys(source, "$.source_document", ("name", "label"))
    _string(source["name"], "$.source_document.name")
    _string(source["label"], "$.source_document.label")

    objects = _list(root["objects"], "$.objects")
    if not objects:
        raise ContractError("$.objects", "at least one envelope or keepout is required")
    if len(objects) > MAX_OBJECTS:
        raise ContractError("$.objects", f"at most {MAX_OBJECTS} objects are supported")
    identifiers = set()
    for index, item in enumerate(objects):
        path = f"$.objects[{index}]"
        obj = _mapping(item, path)
        _keys(obj, path, ("id", "name", "role", "representation", "primitive", "source"), ("metadata",))
        identifier = _string(obj["id"], f"{path}.id")
        if identifier in identifiers:
            raise ContractError(f"{path}.id", f"duplicate object id {identifier!r}")
        identifiers.add(identifier)
        _string(obj["name"], f"{path}.name")
        _enum(obj["role"], f"{path}.role", EXPORT_ROLES)
        if obj["representation"] != "axis_aligned_bounding_box":
            raise ContractError(f"{path}.representation", "only axis_aligned_bounding_box is supported")
        _primitive(obj["primitive"], f"{path}.primitive", boxes_only=True)
        source_info = _mapping(obj["source"], f"{path}.source")
        _keys(source_info, f"{path}.source", ("freecad_name", "freecad_type_id"))
        _string(source_info["freecad_name"], f"{path}.source.freecad_name")
        _string(source_info["freecad_type_id"], f"{path}.source.freecad_type_id")
        if "metadata" in obj:
            _metadata(obj["metadata"], f"{path}.metadata")
    return root


def _read_limited_file(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ContractError("$", f"file exceeds the {MAX_FILE_BYTES} byte limit")
    return raw


def load_geometry_exchange(path: Union[os.PathLike, str]) -> Mapping[str, Any]:
    """Read and validate a local UTF-8 geometry exchange JSON file."""

    source = Path(path)
    if not source.is_file():
        raise ContractError("$", f"not a regular file: {source}")
    return validate_geometry_exchange(_parse_json_bytes(_read_limited_file(source)))


def load_mechanical_exchange(path: Union[os.PathLike, str]) -> Mapping[str, Any]:
    """Read and validate a local UTF-8 mechanical exchange JSON file."""

    source = Path(path)
    if not source.is_file():
        raise ContractError("$", f"not a regular file: {source}")
    return validate_mechanical_exchange(_parse_json_bytes(_read_limited_file(source)))


def write_mechanical_exchange(
    path: Union[os.PathLike, str],
    payload: Mapping[str, Any],
) -> Path:
    """Validate and atomically write a mechanical exchange document."""

    validate_mechanical_exchange(payload)
    destination = Path(path)
    if destination.suffix.lower() != ".json":
        destination = destination.with_suffix(".json")
    if not destination.parent.is_dir():
        raise ContractError("$", f"destination directory does not exist: {destination.parent}")

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
    return destination


__all__ = [
    "ContractError",
    "load_geometry_exchange",
    "load_mechanical_exchange",
    "validate_geometry_exchange",
    "validate_mechanical_exchange",
    "write_mechanical_exchange",
]
