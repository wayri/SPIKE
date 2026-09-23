"""Deterministic single-constraint placement from exact package-shape descriptors."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Mapping

from .assembly_frames import IDENTITY, enforce_placement_policy, inverse_affine, multiply, resolve_world, validate_rigid_transform
from .design_ir_v2 import AssemblyIRV1
from .design_ir_v2_schema import CoordinateFrame


class AssemblyGeometricConstraintError(ValueError):
    """Raised when one exact geometric snap cannot be applied unambiguously."""


def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def _norm(value): return math.sqrt(_dot(value, value))
def _scale(value, factor): return tuple(item * factor for item in value)
def _add(a, b): return tuple(x + y for x, y in zip(a, b))
def _sub(a, b): return tuple(x - y for x, y in zip(a, b))


def _unit(value: Iterable[float], label: str) -> tuple[float, float, float]:
    result = tuple(float(item) for item in value)
    length = _norm(result)
    if len(result) != 3 or not math.isfinite(length) or length <= 1e-12:
        raise AssemblyGeometricConstraintError(f"{label} is degenerate.")
    return tuple(item / length for item in result)  # type: ignore[return-value]


def _transform_point(matrix, point):
    return (
        matrix[0] * point[0] + matrix[1] * point[1] + matrix[2] * point[2] + matrix[3],
        matrix[4] * point[0] + matrix[5] * point[1] + matrix[6] * point[2] + matrix[7],
        matrix[8] * point[0] + matrix[9] * point[1] + matrix[10] * point[2] + matrix[11],
    )


def _transform_direction(matrix, direction):
    return _unit((
        matrix[0] * direction[0] + matrix[1] * direction[1] + matrix[2] * direction[2],
        matrix[4] * direction[0] + matrix[5] * direction[1] + matrix[6] * direction[2],
        matrix[8] * direction[0] + matrix[9] * direction[1] + matrix[10] * direction[2],
    ), "Transformed selector direction")


def _rotation(source, target):
    source, target = _unit(source, "Source direction"), _unit(target, "Target direction")
    cosine = max(-1.0, min(1.0, _dot(source, target)))
    axis = _cross(source, target)
    sine = _norm(axis)
    if sine <= 1e-12:
        if cosine > 0:
            return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        basis = min(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), key=lambda item: abs(_dot(source, item)))
        axis = _unit(_cross(source, basis), "Antiparallel rotation axis")
        x, y, z = axis
        return ((2*x*x-1, 2*x*y, 2*x*z), (2*y*x, 2*y*y-1, 2*y*z), (2*z*x, 2*z*y, 2*z*z-1))
    x, y, z = _scale(axis, 1.0 / sine)
    one = 1.0 - cosine
    return (
        (cosine+x*x*one, x*y*one-z*sine, x*z*one+y*sine),
        (y*x*one+z*sine, cosine+y*y*one, y*z*one-x*sine),
        (z*x*one-y*sine, z*y*one+x*sine, cosine+z*z*one),
    )


def _rotate(rotation, value):
    return tuple(sum(rotation[row][column] * value[column] for column in range(3)) for row in range(3))


def _delta(rotation, pivot, translation):
    rotated_pivot = _rotate(rotation, pivot)
    offset = _add(_sub(pivot, rotated_pivot), translation)
    return (
        rotation[0][0], rotation[0][1], rotation[0][2], offset[0],
        rotation[1][0], rotation[1][1], rotation[1][2], offset[1],
        rotation[2][0], rotation[2][1], rotation[2][2], offset[2],
        0.0, 0.0, 0.0, 1.0,
    )


def _entity(index, reference):
    shape = next((item for item in index["shapes"] if item["shape_id"] == reference["shape_id"]), None)
    if shape is None:
        raise AssemblyGeometricConstraintError("Constraint reference shape is missing.")
    entity = next((item for item in shape["entities"] if item["topology_id"] == reference["topology_id"]), None)
    if entity is None or not isinstance(entity.get("geometry"), Mapping):
        raise AssemblyGeometricConstraintError("Constraint application requires re-extraction with exact analytic descriptors.")
    return shape, entity


def _world_geometry(assembly, models, shape, entity):
    part = next(item for item in assembly.parts if item.id == shape["part_id"])
    model = next((item for item in models.get("models", []) if item.get("id") == shape["source_model_id"]), None)
    if model is None:
        raise AssemblyGeometricConstraintError("Constraint source model is missing.")
    model_transform = model.get("transform") or IDENTITY
    model_transform = validate_rigid_transform(model_transform, "Exact selector source-model transform")
    world = multiply(resolve_world(assembly, part.frame), model_transform)
    geometry = entity["geometry"]
    origin = geometry.get("origin_mm")
    direction = geometry.get("direction")
    return {
        "representation": geometry["representation"],
        "origin": _transform_point(world, origin) if origin is not None else None,
        "direction": _transform_direction(world, direction) if direction is not None else None,
    }


def _target_for_angle(anchor, moving, degrees):
    radians = math.radians(degrees)
    perpendicular = _sub(moving, _scale(anchor, _dot(moving, anchor)))
    if _norm(perpendicular) <= 1e-12:
        basis = min(((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), key=lambda item: abs(_dot(anchor, item)))
        perpendicular = _cross(anchor, basis)
    perpendicular = _unit(perpendicular, "Angle reference plane")
    return _unit(_add(_scale(anchor, math.cos(radians)), _scale(perpendicular, math.sin(radians))), "Angle target")


def apply_single_geometric_constraint(
    assembly: AssemblyIRV1, models: Mapping[str, Any], index: Mapping[str, Any],
    constraint_id: str, moving_part_id: str,
) -> Dict[str, Any]:
    """Apply one persisted two-reference constraint; never solve a constraint graph."""

    constraint = next((item for item in index.get("constraints", []) if item.get("constraint_id") == constraint_id), None)
    if constraint is None:
        raise AssemblyGeometricConstraintError(f"Exact geometric constraint {constraint_id} does not exist.")
    references = constraint.get("references")
    if not isinstance(references, list) or len(references) != 2:
        raise AssemblyGeometricConstraintError("Constraint application requires exactly two persisted topology references.")
    moving_refs = [item for item in references if item.get("part_id") == moving_part_id]
    anchor_refs = [item for item in references if item.get("part_id") != moving_part_id]
    if len(moving_refs) != 1 or len(anchor_refs) != 1:
        raise AssemblyGeometricConstraintError("Choose exactly one referenced moving part and one distinct anchor part.")
    moving_part = next((item for item in assembly.parts if item.id == moving_part_id), None)
    if moving_part is None:
        raise AssemblyGeometricConstraintError(f"AssemblyIR part {moving_part_id} does not exist.")
    lookup = {
        frame.frame_id: frame
        for frame in (*[board.frame for board in assembly.boards], *[part.frame for part in assembly.parts])
    }
    cursor = anchor_refs[0]["part_id"]
    anchor_part = next(item for item in assembly.parts if item.id == cursor)
    parent = anchor_part.frame.parent_frame_id
    while parent and parent != assembly.frame.frame_id:
        if parent == moving_part.frame.frame_id:
            raise AssemblyGeometricConstraintError("The anchor part cannot be a descendant of the moving part.")
        if parent not in lookup:
            raise AssemblyGeometricConstraintError("The anchor part has an invalid frame chain.")
        parent = lookup[parent].parent_frame_id
    moving_shape, moving_entity = _entity(index, moving_refs[0])
    anchor_shape, anchor_entity = _entity(index, anchor_refs[0])
    moving = _world_geometry(assembly, models, moving_shape, moving_entity)
    anchor = _world_geometry(assembly, models, anchor_shape, anchor_entity)
    kind = constraint["kind"]
    point_m, point_a = moving["origin"], anchor["origin"]
    direction_m, direction_a = moving["direction"], anchor["direction"]
    rotation = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    translation = (0.0, 0.0, 0.0)
    if kind == "coincident":
        if moving["representation"] != "point" or anchor["representation"] != "point":
            raise AssemblyGeometricConstraintError("Coincident application currently requires two exact vertices.")
        translation = _sub(point_a, point_m)
    elif kind in {"axis", "concentric", "edge", "face"}:
        required = {"axis": "axis", "concentric": "axis", "edge": "line", "face": "plane"}[kind]
        if moving["representation"] != required or anchor["representation"] != required:
            raise AssemblyGeometricConstraintError(f"{kind.capitalize()} application requires two exact {required} descriptors.")
        rotation = _rotation(direction_m, direction_a)
        # The rotation delta is constructed about the moving selector origin,
        # so that origin remains stationary until the explicit translation.
        separation = _sub(point_a, point_m)
        if kind in {"concentric", "edge"}:
            translation = _sub(separation, _scale(direction_a, _dot(separation, direction_a)))
        elif kind == "face":
            translation = _scale(direction_a, _dot(separation, direction_a))
    elif kind == "distance":
        if moving["representation"] != "point" or anchor["representation"] != "point":
            raise AssemblyGeometricConstraintError("Distance application currently requires two exact vertices.")
        distance = constraint.get("value_mm")
        if isinstance(distance, bool) or not isinstance(distance, (int, float)) or not math.isfinite(distance) or distance < 0:
            raise AssemblyGeometricConstraintError("Distance application requires a non-negative finite value_mm.")
        separation = _sub(point_m, point_a)
        current = _norm(separation)
        if current <= 1e-12:
            raise AssemblyGeometricConstraintError("A zero-distance vertex pair has no deterministic distance direction.")
        translation = _scale(separation, float(distance) / current - 1.0)
    elif kind == "angle":
        if direction_m is None or direction_a is None:
            raise AssemblyGeometricConstraintError("Angle application requires two direction-bearing exact selectors.")
        degrees = constraint.get("value_deg")
        if isinstance(degrees, bool) or not isinstance(degrees, (int, float)) or not math.isfinite(degrees) or not 0 <= degrees <= 180:
            raise AssemblyGeometricConstraintError("Angle application requires value_deg within 0 through 180 degrees.")
        rotation = _rotation(direction_m, _target_for_angle(direction_a, direction_m, float(degrees)))
    else:
        raise AssemblyGeometricConstraintError(f"Constraint kind {kind} is not applicable.")
    world_before = resolve_world(assembly, moving_part.frame)
    delta = _delta(rotation, point_m, translation)
    world_after = multiply(delta, world_before)
    root = assembly.frame.frame_id
    parent_id = moving_part.frame.parent_frame_id or root
    parent_world = IDENTITY if parent_id == root else resolve_world(assembly, lookup[parent_id])
    local_after = validate_rigid_transform(multiply(inverse_affine(parent_world), world_after), "Applied MCAD placement")
    enforce_placement_policy(moving_part.frame.transform, local_after, moving_part.placement_policy)
    before_local = tuple(moving_part.frame.transform)
    moving_part.frame = CoordinateFrame(
        frame_id=moving_part.frame.frame_id, parent_frame_id=parent_id, units="mm", handedness="right", transform=local_after,
    )
    assembly.__post_init__()
    applied = _world_geometry(assembly, models, moving_shape, moving_entity)
    position_residual = 0.0
    angle_residual = 0.0
    if applied["direction"] is not None and direction_a is not None:
        actual_angle = math.degrees(math.acos(max(-1.0, min(1.0, _dot(applied["direction"], direction_a)))))
        angle_residual = abs(actual_angle - float(constraint["value_deg"])) if kind == "angle" else actual_angle
    if kind == "coincident":
        position_residual = _norm(_sub(applied["origin"], point_a))
    elif kind in {"concentric", "edge"}:
        separation = _sub(applied["origin"], point_a)
        position_residual = _norm(_sub(separation, _scale(direction_a, _dot(separation, direction_a))))
    elif kind == "face":
        position_residual = abs(_dot(_sub(applied["origin"], point_a), direction_a))
    elif kind == "distance":
        position_residual = abs(_norm(_sub(applied["origin"], point_a)) - float(constraint["value_mm"]))
    if position_residual > 1e-8 or angle_residual > 1e-7:
        moving_part.frame = CoordinateFrame(
            frame_id=moving_part.frame.frame_id, parent_frame_id=parent_id, units="mm", handedness="right", transform=before_local,
        )
        assembly.__post_init__()
        raise AssemblyGeometricConstraintError("Exact geometric application exceeded its deterministic residual tolerance.")
    return {
        "constraint_id": constraint_id, "constraint_kind": kind,
        "anchor_part_id": anchor_refs[0]["part_id"], "moving_part_id": moving_part_id,
        "old_local_transform": list(before_local), "new_local_transform": list(local_after),
        "residual": {
            "position_mm": position_residual, "angle_deg": angle_residual,
            "position_tolerance_mm": 1e-8, "angle_tolerance_deg": 1e-7,
        },
        "geometry_source": "exact_brep_descriptor", "single_constraint_only": True,
    }
