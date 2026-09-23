"""Project solved branch values onto authoritative conductor mesh faces."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence

import numpy as np
from scipy.spatial import cKDTree


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


def bind_result_faces(
    cells: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
) -> List[tuple[Dict[str, Any], Dict[str, Any], tuple[float, float, float]]]:
    """Bind each face once to its nearest physical branch of the same source."""

    edges_by_source: Dict[str, List[Dict[str, Any]]] = {}
    for edge in edges:
        edges_by_source.setdefault(str(edge["source_id"]), []).append(edge)

    indexes: Dict[tuple[str, str], tuple[List[Dict[str, Any]], cKDTree]] = {}
    bindings = []
    for cell in cells:
        vertices = cell.get("vertices_mm", [])
        source_id = str(cell.get("source_id", ""))
        candidates = edges_by_source.get(source_id, [])
        if len(vertices) < 3 or not candidates:
            continue
        cell_layer = str(cell.get("layer", ""))
        key = (source_id, cell_layer)
        if key not in indexes:
            layer_candidates = [
                edge for edge in candidates
                if str(edge.get("layer", "")) == cell_layer
                or cell_layer in str(edge.get("layer", "")).split("->")
                or str(edge.get("layer", "")) in cell_layer.split("->")
            ]
            matched = layer_candidates or candidates
            points = np.asarray(
                [(float(edge["x_mm"]), float(edge["y_mm"]), float(edge["z_mm"])) for edge in matched],
                dtype=float,
            )
            indexes[key] = (matched, cKDTree(points))
        matched, tree = indexes[key]
        count = len(vertices)
        center = tuple(
            sum(float(vertex[axis]) for vertex in vertices) / count
            for axis in range(3)
        )
        distance, nearest = tree.query(center, k=min(2, len(matched)))
        if len(matched) == 1:
            edge = matched[int(nearest)]
        else:
            first_distance, second_distance = distance
            if second_distance - first_distance > max(1e-12, first_distance * 1e-12):
                edge = matched[int(nearest[0])]
            else:
                # Match the former stable list-order tie break for symmetric cells.
                radius = first_distance + max(1e-12, first_distance * 1e-12)
                possible = tree.query_ball_point(center, radius)
                winner = min(
                    possible,
                    key=lambda index: (
                        sum((center[axis] - float(matched[index][field])) ** 2
                            for axis, field in enumerate(("x_mm", "y_mm", "z_mm"))),
                        index,
                    ),
                )
                edge = matched[winner]
        bindings.append((cell, edge, center))
    return bindings


def project_result_faces(
    cells: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    value: Callable[[Dict[str, Any]], float | None],
    *,
    bindings: Sequence[tuple[Dict[str, Any], Dict[str, Any], tuple[float, float, float]]] | None = None,
) -> List[Dict[str, Any]]:
    """Return scalar samples on exact mesh faces using reusable spatial bindings."""

    samples: List[Dict[str, Any]] = []
    for cell, edge, center in bindings if bindings is not None else bind_result_faces(cells, edges):
        vertices = cell["vertices_mm"]
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
