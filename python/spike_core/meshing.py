"""Versioned PCB meshing service shared by preflight, CLI, and solver adapters.

The connected hybrid graph remains the electrical discretization used by the
current DC and PEEC solvers. This module adds stable surface and conductor-volume
representations for inspection and future field-solver plugins.
"""

from __future__ import annotations

from collections import Counter
import ctypes
from dataclasses import dataclass
from math import hypot, sqrt
import os
import platform
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .contracts import AnalysisSpec, DesignIR
from .dc_result_utils import stratified_sample_records
from .hybrid_mesh import DEFAULT_COPPER_THICKNESS_MM, HybridMesh, build_hybrid_mesh
from .layers import copper_stack_profile
from .pi_path_dc import build_pi_path_interface_elements


Point3D = Tuple[float, float, float]
MESH_CONTRACT = "spike/mesh/v3"
SURFACE_2_5D = "surface_2_5d"
VOLUME_3D = "volume_3d"
MEBIBYTE = 1024 * 1024
DEFAULT_PREVIEW_MEMORY_MB = 512
MAX_PHYSICAL_MEMORY_FRACTION = 0.75
SURFACE_RESIDENT_BYTES_PER_CELL = 2048
VOLUME_RESIDENT_BYTES_PER_CELL = 3584


def _physical_memory_bytes() -> int | None:
    """Return installed physical memory using only the Python standard library."""

    try:
        if platform.system() == "Windows":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong),
                    ("avail_phys", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("avail_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("avail_virtual", ctypes.c_ulonglong),
                    ("avail_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_phys)
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        total = int(page_size) * int(page_count)
        return total if total > 0 else None
    except (AttributeError, OSError, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MeshingOptions:
    dimension: str
    max_cells: int
    requested_max_cells: int
    memory_budget_bytes: int
    estimated_resident_bytes_per_cell: int
    capacity_cells: int
    physical_memory_bytes: int | None

    @classmethod
    def from_spec(
        cls,
        spec: AnalysisSpec,
        physical_memory_bytes: int | None = None,
    ) -> "MeshingOptions":
        dimension = str(spec.mesh.get("dimension", SURFACE_2_5D))
        if dimension not in {SURFACE_2_5D, VOLUME_3D}:
            raise ValueError(
                f"Unsupported mesh dimension {dimension!r}; "
                f"expected {SURFACE_2_5D!r} or {VOLUME_3D!r}."
            )
        requested = max(100, int(spec.mesh.get("max_preview_cells", 25000)))
        detected_memory = physical_memory_bytes if physical_memory_bytes is not None else _physical_memory_bytes()
        requested_budget_mb = float(spec.mesh.get("memory_budget_mb", DEFAULT_PREVIEW_MEMORY_MB))
        if not requested_budget_mb > 0:
            raise ValueError("mesh.memory_budget_mb must be positive")
        requested_budget_bytes = int(requested_budget_mb * MEBIBYTE)
        physical_ceiling = (
            int(detected_memory * MAX_PHYSICAL_MEMORY_FRACTION)
            if detected_memory is not None and detected_memory > 0
            else requested_budget_bytes
        )
        memory_budget_bytes = max(MEBIBYTE, min(requested_budget_bytes, physical_ceiling))
        fixed_bytes = max(0, int(spec.mesh.get("fixed_memory_estimate_bytes", 0)))
        resident_bytes_per_cell = max(
            256,
            int(spec.mesh.get(
                "estimated_resident_bytes_per_cell",
                VOLUME_RESIDENT_BYTES_PER_CELL if dimension == VOLUME_3D else SURFACE_RESIDENT_BYTES_PER_CELL,
            )),
        )
        capacity_cells = max(100, (max(0, memory_budget_bytes - fixed_bytes)) // resident_bytes_per_cell)
        return cls(
            dimension=dimension,
            max_cells=min(requested, capacity_cells),
            requested_max_cells=requested,
            memory_budget_bytes=memory_budget_bytes,
            estimated_resident_bytes_per_cell=resident_bytes_per_cell,
            capacity_cells=capacity_cells,
            physical_memory_bytes=detected_memory,
        )


def _copper_thicknesses(design: DesignIR) -> Dict[str, float]:
    return copper_stack_profile(design, DEFAULT_COPPER_THICKNESS_MM)[2]


def _via_centers(design: DesignIR) -> Dict[str, Tuple[float, float]]:
    result: Dict[str, Tuple[float, float]] = {}
    for index, via in enumerate(design.vias):
        point = via.get("at", (0, 0))
        if isinstance(point, dict):
            center = (float(point.get("x", 0)), float(point.get("y", 0)))
        else:
            center = (float(point[0]), float(point[1]))
        result[str(via.get("id", f"via-{index + 1}"))] = center
    return result


def _surface_cell(cell: Dict[str, Any]) -> Dict[str, Any]:
    vertex_count = len(cell.get("vertices_mm", []))
    return {
        **cell,
        "kind": "surface",
        "topology": "quad4" if vertex_count == 4 else f"polygon{vertex_count}",
        "material": "copper",
    }


def _horizontal_volume(
    vertices: Sequence[Point3D],
    thickness_mm: float,
) -> List[List[float]]:
    lower = [[x, y, z - thickness_mm / 2] for x, y, z in vertices]
    upper = [[x, y, z + thickness_mm / 2] for x, y, z in vertices]
    return lower + upper


def _via_volume(
    vertices: Sequence[Point3D],
    center: Tuple[float, float],
    plating_mm: float,
) -> List[List[float]]:
    outer = [list(point) for point in vertices]
    inner: List[List[float]] = []
    for x, y, z in vertices:
        radius = hypot(x - center[0], y - center[1])
        inner_radius = max(radius - plating_mm, radius * 0.1)
        ratio = inner_radius / max(radius, 1e-12)
        inner.append([
            center[0] + (x - center[0]) * ratio,
            center[1] + (y - center[1]) * ratio,
            z,
        ])
    return outer + inner


def _volume_cell(
    cell: Dict[str, Any],
    thicknesses: Dict[str, float],
    via_centers: Dict[str, Tuple[float, float]],
    plating_mm: float,
) -> Dict[str, Any]:
    vertices = [tuple(float(value) for value in point) for point in cell["vertices_mm"]]
    source_kind = str(cell.get("source_kind", ""))
    explicit_inner = cell.get("inner_vertices_mm")
    if source_kind in {"via", "pad_barrel"} and isinstance(explicit_inner, list):
        inner_vertices = [
            [float(value) for value in point[:3]]
            for point in explicit_inner
            if isinstance(point, (list, tuple)) and len(point) >= 3
        ]
        if len(inner_vertices) != len(vertices):
            raise ValueError(
                f"Barrel cell {cell.get('id', '')!r} has mismatched inner and outer vertices."
            )
        volume_vertices = [list(point) for point in vertices] + inner_vertices
        topology = "hex8_barrel"
    elif source_kind == "via":
        center = via_centers.get(str(cell.get("source_id")))
        if center is None:
            center = (
                sum(point[0] for point in vertices) / len(vertices),
                sum(point[1] for point in vertices) / len(vertices),
            )
        volume_vertices = _via_volume(vertices, center, plating_mm)
        topology = "hex8_barrel"
    else:
        thickness = thicknesses.get(
            str(cell.get("layer", "")),
            DEFAULT_COPPER_THICKNESS_MM,
        )
        volume_vertices = _horizontal_volume(vertices, thickness)
        topology = "hex8" if len(vertices) == 4 else f"prism{len(vertices)}"
    return {
        **cell,
        "kind": "volume",
        "topology": topology,
        "material": "copper",
        "vertices_mm": volume_vertices,
    }


def _edges(cell: Dict[str, Any]) -> Iterable[Tuple[Point3D, Point3D]]:
    vertices = [tuple(float(value) for value in point) for point in cell["vertices_mm"]]
    topology = str(cell.get("topology", ""))
    if topology.startswith("prism") and len(vertices) >= 6 and len(vertices) % 2 == 0:
        face_vertices = len(vertices) // 2
        indexes = tuple(
            [(index, (index + 1) % face_vertices) for index in range(face_vertices)]
            + [(index + face_vertices, (index + 1) % face_vertices + face_vertices) for index in range(face_vertices)]
            + [(index, index + face_vertices) for index in range(face_vertices)]
        )
    elif len(vertices) == 4:
        indexes = ((0, 1), (1, 2), (2, 3), (3, 0))
    elif cell.get("kind") == "volume" and len(vertices) == 8:
        indexes = (
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        )
    else:
        indexes = tuple((index, (index + 1) % len(vertices)) for index in range(len(vertices)))
    for start, end in indexes:
        yield vertices[start], vertices[end]


def _distance(a: Point3D, b: Point3D) -> float:
    return sqrt(sum((right - left) ** 2 for left, right in zip(a, b)))


def _quality(cells: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    edge_lengths = [
        _distance(start, end)
        for cell in cells
        for start, end in _edges(cell)
    ]
    lengths = [length for length in edge_lengths if length > 1e-12]
    aspect_ratios: List[float] = []
    for cell in cells:
        cell_edges = [_distance(start, end) for start, end in _edges(cell)]
        positive = [value for value in cell_edges if value > 1e-12]
        if positive:
            aspect_ratios.append(max(positive) / min(positive))
    return {
        "zero_length_edges": sum(length <= 1e-12 for length in edge_lengths),
        "minimum_edge_mm": min(lengths, default=0.0),
        "maximum_edge_mm": max(lengths, default=0.0),
        "maximum_aspect_ratio": max(aspect_ratios, default=0.0),
        "mean_aspect_ratio": (
            sum(aspect_ratios) / len(aspect_ratios) if aspect_ratios else 0.0
        ),
    }


class MeshingEngine:
    """Generate deterministic, renderer-neutral PCB meshes."""

    def build(self, design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
        options = MeshingOptions.from_spec(spec)
        hybrid = build_hybrid_mesh(design, spec)
        return self.preview(design, spec, hybrid, options)

    def preview(
        self,
        design: DesignIR,
        spec: AnalysisSpec,
        hybrid: HybridMesh,
        options: MeshingOptions,
    ) -> Dict[str, Any]:
        # Preview admission is intentionally separate from solve topology.  A
        # prefix slice followed the builder order (tracks, vias, zones, pads),
        # which made the visual preview omit later geometry and create visible
        # row/column streaks.  Sampling preserves source ownership and spatial
        # coverage without modifying the electrical mesh or solver inputs.
        source_cells = stratified_sample_records(hybrid.cells, options.max_cells)
        if options.dimension == VOLUME_3D:
            thicknesses = _copper_thicknesses(design)
            centers = _via_centers(design)
            plating = max(
                float(spec.mesh.get("via_plating_thickness_mm", 0.025)),
                0.005,
            )
            cells = [
                _volume_cell(cell, thicknesses, centers, plating)
                for cell in source_cells
            ]
        else:
            cells = [_surface_cell(cell) for cell in source_cells]

        source_counts = Counter(str(cell.get("source_kind", "unknown")) for cell in cells)
        topology_counts = Counter(str(cell.get("topology", "unknown")) for cell in cells)
        layer_counts = Counter(str(cell.get("layer", "")) for cell in cells)
        net_counts = Counter(str(cell.get("net", "")) for cell in cells)
        vertex_count = sum(len(cell["vertices_mm"]) for cell in cells)
        quality = _quality(cells)
        component_bridges, bridge_issues = build_pi_path_interface_elements(
            hybrid, design, spec,
        )
        return {
            "contract": MESH_CONTRACT,
            "dimension": options.dimension,
            "scope": {
                "all_nets": not bool(spec.net_names),
                "requested_nets": sorted({str(value) for value in spec.net_names if str(value)}),
            },
            "formulation": spec.formulation,
            "electrical_topology": "connected_hybrid_graph",
            "target_size_mm": hybrid.target_size_mm,
            "cells": cells,
            "component_bridges": component_bridges,
            "cell_count": len(cells),
            "component_bridge_count": len(component_bridges),
            "vertex_count": vertex_count,
            "counts": {
                "track": source_counts.get("track", 0),
                "zone": source_counts.get("zone", 0),
                "via": source_counts.get("via", 0),
                "pad_barrel": source_counts.get("pad_barrel", 0),
                "pad": source_counts.get("pad", 0),
                "dielectric": source_counts.get("dielectric", 0),
            },
            "topology_counts": dict(topology_counts),
            "layer_counts": dict(layer_counts),
            "net_counts": dict(net_counts),
            "material_counts": {"copper": len(cells)},
            "geometry_counts": dict(hybrid.geometry_counts),
            "node_count": len(hybrid.nodes),
            "branch_count": len(hybrid.branches),
            "branch_admission": dict(hybrid.branch_admission),
            "truncated": hybrid.truncated or len(hybrid.cells) > options.max_cells,
            "preview_admission": {
                "requested_cells": options.requested_max_cells,
                "admitted_cells": options.max_cells,
                "capacity_cells": options.capacity_cells,
                "memory_budget_bytes": options.memory_budget_bytes,
                "estimated_resident_bytes_per_cell": options.estimated_resident_bytes_per_cell,
                "physical_memory_bytes": options.physical_memory_bytes,
                "limited_by_memory": options.max_cells < options.requested_max_cells,
                "meaning": "Resource admission only; numerical convergence and solver validity are separate gates.",
            },
            "estimated_matrix_unknowns": len(hybrid.nodes) + len(hybrid.branches),
            "estimated_geometry_bytes": vertex_count * 3 * 8,
            "estimated_resident_geometry_bytes": len(cells) * options.estimated_resident_bytes_per_cell,
            "quality": quality,
            "issues": [issue.__dict__ for issue in [*hybrid.issues, *bridge_issues]],
            "provenance": {
                "generator": MESH_CONTRACT,
                "source_mesh": "spike/hybrid-conductor/v1",
                "volume_usage": (
                    "preview_and_plugin_exchange"
                    if options.dimension == VOLUME_3D
                    else "solver_and_preview"
                ),
            },
        }


def build_mesh(design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
    return MeshingEngine().build(design, spec)
