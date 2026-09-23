"""Project solved branch values onto authoritative conductor mesh faces."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence

import numpy as np


TOPOLOGY_VISUALIZATION_KINDS = {
    "zone_attachment",
    "pad_attachment",
    "pad_zone_attachment",
    "source_contact",
    "load_contact",
}


def physical_result_edges(edges: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Exclude graph-only connectivity edges from rendered physics output."""

    return [edge for edge in edges if edge["kind"] not in TOPOLOGY_VISUALIZATION_KINDS]


def project_result_faces(
    cells: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    value: Callable[[Dict[str, Any]], float | None],
) -> List[Dict[str, Any]]:
    """Return scalar samples whose footprint is the exact source mesh cell."""

    edges_by_source: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        edges_by_source.setdefault(str(edge["source_id"]), []).append(edge)

    samples: List[Dict[str, Any]] = []
    for cell in cells:
        vertices = cell.get("vertices_mm", [])
        candidates = edges_by_source.get(str(cell.get("source_id", "")), [])
        if len(vertices) < 3 or not candidates:
            continue
        cell_layer = str(cell.get("layer", ""))
        layer_candidates = [
            edge for edge in candidates
            if str(edge.get("layer", "")) == cell_layer
            or cell_layer in str(edge.get("layer", "")).split("->")
            or str(edge.get("layer", "")) in cell_layer.split("->")
        ]
        if layer_candidates:
            candidates = layer_candidates
        count = len(vertices)
        center = tuple(
            sum(float(vertex[axis]) for vertex in vertices) / count
            for axis in range(3)
        )
        edge = min(
            candidates,
            key=lambda item: sum(
                (center[axis] - float(item[key])) ** 2
                for axis, key in enumerate(("x_mm", "y_mm", "z_mm"))
            ),
        )
        resolved = value(edge)
        if resolved is None or not np.isfinite(resolved):
            continue
        samples.append({
            "x_mm": center[0],
            "y_mm": center[1],
            "z_mm": center[2],
            "layer": cell.get("layer", edge["layer"]),
            "net": cell.get("net", edge["net"]),
            "element_id": cell["id"],
            "source_kind": cell.get("source_kind", edge["kind"]),
            "vertices_mm": vertices,
            "value": float(resolved),
        })
    return samples
