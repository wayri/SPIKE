"""Build the solver-neutral geometry and excitation handoff bundle."""

from __future__ import annotations

from dataclasses import replace
from math import hypot
from typing import Any, Dict, Iterable, List, Sequence

from .contracts import AnalysisSpec, DesignIR
from .geometry import extract_net_geometry
from .mesh_ownership import audit_dc_conductor_volume_ownership
from .meshing import VOLUME_3D, build_mesh


DC_FEM_GEOMETRY_CONTRACT = "spike/dc-fem-conductor-volumes/v1"


def _terminal_position(terminal: Dict[str, Any]) -> tuple[float, float] | None:
    point = terminal.get("position_mm")
    if isinstance(point, dict):
        point = (point.get("x"), point.get("y"))
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        try:
            return float(point[0]), float(point[1])
        except (TypeError, ValueError):
            return None
    try:
        return float(terminal["x_mm"]), float(terminal["y_mm"])
    except (KeyError, TypeError, ValueError):
        return None


def _terminal_object_id(terminal: Dict[str, Any]) -> str:
    direct = str(terminal.get("object_id", "")).strip()
    if direct:
        return direct
    anchor = terminal.get("geometry_anchor")
    return str(anchor.get("id", "")).strip() if isinstance(anchor, dict) else ""


def _centroid(vertices: Sequence[Sequence[float]]) -> tuple[float, float]:
    return (
        sum(float(point[0]) for point in vertices) / len(vertices),
        sum(float(point[1]) for point in vertices) / len(vertices),
    )


def _point_segment_distance(
    point: tuple[float, float],
    start: Sequence[float],
    end: Sequence[float],
) -> float:
    ax, ay = float(start[0]), float(start[1])
    bx, by = float(end[0]), float(end[1])
    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        return hypot(point[0] - ax, point[1] - ay)
    ratio = ((point[0] - ax) * dx + (point[1] - ay) * dy) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    return hypot(point[0] - (ax + ratio * dx), point[1] - (ay + ratio * dy))


def _point_on_polygon(
    point: tuple[float, float],
    vertices: Sequence[Sequence[float]],
    tolerance_mm: float,
) -> bool:
    """Return whether a board-plane point lies in or immediately on a cell."""

    polygon = list(vertices)
    if len(polygon) < 3:
        return False
    for index, start in enumerate(polygon):
        if _point_segment_distance(point, start, polygon[(index + 1) % len(polygon)]) <= tolerance_mm:
            return True
    inside = False
    px, py = point
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if (y1 > py) != (y2 > py):
            crossing_x = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < crossing_x:
                inside = not inside
        previous = current
    return inside


def _terminal_face(
    terminal: Dict[str, Any],
    role: str,
    index: int,
    volumes: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    object_id = _terminal_object_id(terminal)
    net = str(terminal.get("net") or terminal.get("net_name") or "").strip()
    layer = str(terminal.get("layer") or "").strip()
    candidates = [
        volume for volume in volumes
        if (not object_id or str(volume.get("source_id", "")) == object_id)
        and (not net or str(volume.get("net", "")) == net)
        and (not layer or str(volume.get("layer", "")) == layer)
    ]
    position = _terminal_position(terminal)
    if not candidates and object_id:
        raise ValueError(f"{role} terminal {index + 1} does not map to conductor object {object_id!r}.")
    if not candidates:
        candidates = [
            volume for volume in volumes
            if (not net or str(volume.get("net", "")) == net)
            and (not layer or str(volume.get("layer", "")) == layer)
        ]
    if not candidates or position is None:
        raise ValueError(
            f"{role} terminal {index + 1} requires a mapped conductor object or a coordinate on selected copper."
        )

    def distance(volume: Dict[str, Any]) -> float:
        center = _centroid(volume["vertices_mm"])
        return hypot(center[0] - position[0], center[1] - position[1])

    if not object_id:
        try:
            snap_tolerance_mm = float(terminal.get("snap_tolerance_mm", 0.05))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{role} terminal {index + 1} snap_tolerance_mm must be numeric.") from exc
        if not 0.0 <= snap_tolerance_mm <= 5.0:
            raise ValueError(f"{role} terminal {index + 1} snap_tolerance_mm must be between 0 and 5 mm.")
        containing = []
        for volume in candidates:
            vertices = volume.get("vertices_mm", [])
            face_size = len(vertices) // 2
            if face_size >= 3 and _point_on_polygon(position, vertices[:face_size], snap_tolerance_mm):
                containing.append(volume)
        if not containing:
            raise ValueError(
                f"{role} terminal {index + 1} coordinate is not on selected copper within "
                f"{snap_tolerance_mm:g} mm."
            )
        candidates = containing
    selected = min(candidates, key=distance)
    vertices = selected["vertices_mm"]
    if len(vertices) < 6 or len(vertices) % 2:
        raise ValueError(f"{role} terminal {index + 1} mapped to a non-volumetric conductor cell.")
    face_size = len(vertices) // 2
    use_lower_face = str(selected.get("layer", "")).startswith("B.")
    face = vertices[:face_size] if use_lower_face else vertices[face_size:]
    return {
        "id": str(terminal.get("id") or f"{role}-{index + 1}"),
        "role": role,
        "cell_id": str(selected["id"]),
        "source_id": str(selected.get("source_id", "")),
        "net": str(selected.get("net", "")),
        "layer": str(selected.get("layer", "")),
        "vertices_mm": [list(point) for point in face],
        "position_mm": [position[0], position[1]],
    }


def build_dc_fem_geometry(design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
    """Build the bounded conductor-volume contract required by external DC FEM.

    This is deliberately stricter than the renderer preview.  It rejects
    decimated geometry and terminals that cannot be assigned to an explicit
    conductor boundary, so a graph mesh can never be passed off as a field mesh.
    """

    if str(spec.mode).strip().lower() not in {"dc", "bulk_dc", "dc_ir_drop"}:
        raise ValueError("DC FEM conductor geometry can only be built for a DC analysis.")
    mesh_spec = replace(spec, mesh={
        **spec.mesh,
        "dimension": VOLUME_3D,
        "max_preview_cells": int(spec.mesh.get("max_solver_cells", spec.mesh.get("max_preview_cells", 25000))),
    })
    mesh = build_mesh(design, mesh_spec)
    if mesh.get("truncated"):
        raise ValueError("DC FEM geometry was resource-truncated; increase the solver memory/cell budget.")
    volumes = [
        {
            **cell,
            "material_region_id": f"copper:{cell.get('layer', '')}",
        }
        for cell in mesh.get("cells", [])
        if cell.get("kind") == "volume"
    ]
    if not volumes:
        raise ValueError("DC FEM geometry contains no conductor volumes for the selected nets.")
    invalid = [
        str(cell.get("id", "")) for cell in volumes
        if len(cell.get("vertices_mm", [])) < 6 or len(cell.get("vertices_mm", [])) % 2
    ]
    if invalid:
        raise ValueError(f"DC FEM geometry contains non-volumetric cells: {', '.join(invalid[:5])}.")
    ownership_audit = audit_dc_conductor_volume_ownership(
        design,
        volumes,
        spec.mesh.get("ownership_tolerance_mm", 1e-6),
    )

    stackup = {
        str(layer.get("name") or layer.get("layer") or ""): layer
        for layer in design.stackup if isinstance(layer, dict)
    }
    regions = []
    for layer in sorted({str(cell.get("layer", "")) for cell in volumes}):
        raw = stackup.get(layer, {})
        regions.append({
            "id": f"copper:{layer}",
            "material": "copper",
            "layer": layer,
            "conductivity_s_m": float(raw.get("conductivity_s_m", raw.get("conductivity", 5.8e7))),
            "cell_ids": [str(cell["id"]) for cell in volumes if str(cell.get("layer", "")) == layer],
        })
    boundary_faces = [
        _terminal_face(terminal, role, index, volumes)
        for role, terminals in (("source", spec.sources), ("load", spec.loads))
        for index, terminal in enumerate(terminals)
        if isinstance(terminal, dict)
    ]
    if not any(face["role"] == "source" for face in boundary_faces):
        raise ValueError("DC FEM geometry requires at least one explicit source boundary face.")
    if not any(face["role"] == "load" for face in boundary_faces):
        raise ValueError("DC FEM geometry requires at least one explicit load boundary face.")
    return {
        "contract": DC_FEM_GEOMETRY_CONTRACT,
        "units": "mm",
        "coordinate_system": {"plane": "XY", "normal": "+Z"},
        "volumes": volumes,
        "material_regions": regions,
        "terminal_boundary_faces": boundary_faces,
        "ownership_audit": ownership_audit,
        "quality": dict(mesh.get("quality", {})),
        "resource_admission": dict(mesh.get("preview_admission", {})),
        "source_mesh_contract": mesh.get("contract"),
        "counts": {
            "volumes": len(volumes),
            "material_regions": len(regions),
            "terminal_boundary_faces": len(boundary_faces),
        },
    }


def build_solver_geometry(design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
    selected_nets = [
        extract_net_geometry(design, net_name)
        for net_name in spec.net_names
        if net_name
    ]
    materials = []
    for layer in design.stackup:
        material = {
            "layer": layer.get("name", ""),
            "type": layer.get("type", "unknown"),
            "material": layer.get("material", ""),
            "thickness_mm": layer.get("thickness"),
            "conductivity_s_m": layer.get("conductivity"),
            "epsilon_r": layer.get("epsilon_r", layer.get("epsilonR")),
            "loss_tangent": layer.get("loss_tangent", layer.get("lossTangent")),
        }
        materials.append(material)
    return {
        "contract": "spike/solver-geometry/v1",
        "design_id": design.design_id,
        "units": design.units,
        "coordinate_system": {
            "plane": "XY",
            "normal": "+Z",
            "origin": design.metadata.get("origin", [0, 0, 0]),
        },
        "selection": {
            "net_names": list(spec.net_names),
            "complete_nets": selected_nets,
        },
        "conductors": {
            "tracks": design.tracks,
            "zones": design.zones,
            "vias": design.vias,
            "pads": design.pads,
        },
        "assembly": {
            "technology": design.technology,
            "regions": design.regions,
            "bends": design.bends,
            "layers": design.layers,
            "stackup": design.stackup,
            "materials": materials,
            "components": design.components,
            "component_bonds": design.component_bonds,
            "connectors": design.connectors,
        },
        "excitations": {
            "sources": spec.sources,
            "loads": spec.loads,
            "probes": spec.probes,
            "ports": spec.options.get("ports", []),
        },
        "frequency": {
            "start_hz": spec.frequency_start_hz,
            "stop_hz": spec.frequency_stop_hz,
            "points": spec.frequency_points,
        },
        "mesh": spec.mesh,
        "limits": spec.limits,
        "source_metadata": design.metadata,
        "counts": {
            "layers": len(design.layers),
            "tracks": len(design.tracks),
            "zones": len(design.zones),
            "vias": len(design.vias),
            "pads": len(design.pads),
            "components": len(design.components),
            "component_bonds": len(design.component_bonds),
            "regions": len(design.regions),
            "bends": len(design.bends),
        },
    }
