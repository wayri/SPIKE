"""Coordinate-frame composition and world-preserving AssemblyIR reparenting."""

from __future__ import annotations

import math
from typing import Dict, Iterable

from .assembly_placement_policy import AssemblyPlacementPolicy
from .design_ir_v2 import AssemblyIRV1
from .design_ir_v2_schema import CoordinateFrame


IDENTITY = (
    1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
)


def multiply(left: Iterable[float], right: Iterable[float]) -> tuple[float, ...]:
    a, b = tuple(left), tuple(right)
    return tuple(sum(a[row * 4 + k] * b[k * 4 + col] for k in range(4)) for row in range(4) for col in range(4))


def _affine(matrix: Iterable[float], label: str) -> tuple[float, ...]:
    value = tuple(float(item) for item in matrix)
    if len(value) != 16 or not all(math.isfinite(item) for item in value):
        raise ValueError(f"{label} must be a finite 4x4 transform.")
    if any(abs(value[index]) > 1e-12 for index in (12, 13, 14)) or abs(value[15] - 1.0) > 1e-12:
        raise ValueError(f"{label} must be an affine transform with canonical homogeneous row.")
    return value


def validate_rigid_transform(matrix: Iterable[float], label: str = "Assembly placement") -> tuple[float, ...]:
    """Require a canonical proper-rigid placement matrix (rotation + translation)."""

    value = _affine(matrix, label)
    rows = (value[0:3], value[4:7], value[8:11])
    tolerance = 1e-8
    for index, row in enumerate(rows):
        norm = sum(component * component for component in row)
        if abs(norm - 1.0) > tolerance:
            raise ValueError(f"{label} rotation row {index} must have unit length; scale and shear are not permitted.")
    for left, right in ((rows[0], rows[1]), (rows[0], rows[2]), (rows[1], rows[2])):
        if abs(sum(a * b for a, b in zip(left, right))) > tolerance:
            raise ValueError(f"{label} rotation rows must be orthogonal; scale and shear are not permitted.")
    determinant = (
        value[0] * (value[5] * value[10] - value[6] * value[9])
        - value[1] * (value[4] * value[10] - value[6] * value[8])
        + value[2] * (value[4] * value[9] - value[5] * value[8])
    )
    if abs(determinant - 1.0) > tolerance:
        raise ValueError(f"{label} must use a proper right-handed rotation with determinant +1.")
    return value


def enforce_placement_policy(
    existing: Iterable[float], requested: Iterable[float], policy: AssemblyPlacementPolicy | None,
) -> None:
    """Enforce topology-free parent-local translation and rotation increments."""

    old = validate_rigid_transform(existing, "Existing MCAD placement")
    new = validate_rigid_transform(requested, "MCAD placement")
    if policy is None:
        return
    if policy.translation_snap_mm is not None:
        step = policy.translation_snap_mm
        for axis, index in zip("XYZ", (3, 7, 11)):
            delta = new[index] - old[index]
            snapped = round(delta / step) * step
            if abs(delta - snapped) > 1e-8:
                raise ValueError(
                    f"MCAD placement {axis} delta {delta:g} mm violates the persisted {step:g} mm translation increment."
                )
    if policy.rotation_snap_deg is not None:
        # trace(R_new * transpose(R_old)) gives the principal relative angle.
        trace = sum(new[row * 4 + column] * old[row * 4 + column] for row in range(3) for column in range(3))
        cosine = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
        angle = math.acos(cosine)
        step = math.radians(policy.rotation_snap_deg)
        snapped = round(angle / step) * step
        if abs(angle - snapped) > 1e-8:
            raise ValueError(
                f"MCAD placement rotation delta {math.degrees(angle):g} deg violates the persisted {policy.rotation_snap_deg:g} deg rotation increment."
            )


def inverse_affine(matrix: Iterable[float]) -> tuple[float, ...]:
    value = _affine(matrix, "Assembly frame")
    a, b, c, tx, d, e, f, ty, g, h, i, tz = value[:12]
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
        raise ValueError("Assembly frame is singular or too ill-conditioned to reparent safely.")
    inverse_det = 1.0 / determinant
    inverse = (
        (e * i - f * h) * inverse_det, (c * h - b * i) * inverse_det, (b * f - c * e) * inverse_det,
        (f * g - d * i) * inverse_det, (a * i - c * g) * inverse_det, (c * d - a * f) * inverse_det,
        (d * h - e * g) * inverse_det, (b * g - a * h) * inverse_det, (a * e - b * d) * inverse_det,
    )
    itx = -(inverse[0] * tx + inverse[1] * ty + inverse[2] * tz)
    ity = -(inverse[3] * tx + inverse[4] * ty + inverse[5] * tz)
    itz = -(inverse[6] * tx + inverse[7] * ty + inverse[8] * tz)
    return (
        inverse[0], inverse[1], inverse[2], itx,
        inverse[3], inverse[4], inverse[5], ity,
        inverse[6], inverse[7], inverse[8], itz,
        0.0, 0.0, 0.0, 1.0,
    )


def _frames(assembly: AssemblyIRV1) -> Dict[str, CoordinateFrame]:
    return {
        frame.frame_id: frame
        for frame in (*[board.frame for board in assembly.boards], *[part.frame for part in assembly.parts])
    }


def resolve_world(assembly: AssemblyIRV1, frame: CoordinateFrame) -> tuple[float, ...]:
    root = assembly.frame.frame_id
    lookup = _frames(assembly)
    current = frame
    resolved = IDENTITY
    visited: set[str] = set()
    while current.frame_id != root:
        if current.frame_id in visited:
            raise ValueError(f"Assembly frame hierarchy contains a cycle at {current.frame_id}.")
        visited.add(current.frame_id)
        resolved = multiply(_affine(current.transform, f"Assembly frame {current.frame_id}"), resolved)
        parent_id = current.parent_frame_id or root
        if parent_id == root:
            return resolved
        if parent_id not in lookup:
            raise ValueError(f"Assembly frame {current.frame_id} references unknown parent {parent_id}.")
        current = lookup[parent_id]
    return resolved


def reparent_part_preserving_world(assembly: AssemblyIRV1, part_id: str, new_parent_frame_id: str) -> tuple[str, str]:
    root = assembly.frame.frame_id
    if assembly.frame.parent_frame_id or tuple(assembly.frame.transform) != IDENTITY:
        raise ValueError("Assembly reparenting requires the canonical identity root frame.")
    part = next((item for item in assembly.parts if item.id == part_id), None)
    if part is None:
        raise ValueError(f"AssemblyIR part {part_id} does not exist.")
    destination = new_parent_frame_id or root
    lookup = _frames(assembly)
    if destination != root and destination not in lookup:
        raise ValueError(f"Reparent destination frame {destination} does not exist.")
    if destination == part.frame.frame_id:
        raise ValueError("An AssemblyIR part cannot be parented to itself.")
    cursor = destination
    visited: set[str] = set()
    while cursor != root:
        if cursor == part.frame.frame_id:
            raise ValueError("An AssemblyIR part cannot be parented beneath its descendant.")
        if cursor in visited or cursor not in lookup:
            raise ValueError("The requested reparent destination has an invalid frame chain.")
        visited.add(cursor)
        cursor = lookup[cursor].parent_frame_id or root
    world_before = resolve_world(assembly, part.frame)
    parent_world = IDENTITY if destination == root else resolve_world(assembly, lookup[destination])
    local = multiply(inverse_affine(parent_world), world_before)
    old_parent = part.frame.parent_frame_id or root
    part.frame = CoordinateFrame(
        frame_id=part.frame.frame_id, parent_frame_id=destination, units="mm", handedness="right", transform=local,
    )
    assembly.__post_init__()
    world_after = resolve_world(assembly, part.frame)
    if any(abs(before - after) > 1e-9 for before, after in zip(world_before, world_after)):
        raise ValueError("Assembly reparenting did not preserve the part world transform.")
    return old_parent, destination
