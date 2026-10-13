# SPDX-License-Identifier: Apache-2.0
"""Bounded, approximate resistance routes on the admitted SpiDeR copper graph."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, fields
import heapq
import math
from typing import Any

from .contracts import AnalysisSpec, SpiDeR
from .hybrid_mesh import build_hybrid_mesh
from .layers import ordered_copper_layer_names

REQUEST = "spike/pi-return-path-request/v1"
RESULT = "spike/pi-return-path-result/v1"
MAX_BRANCHES = 50_000
MAX_POINTS = 100_000


class _Rejected(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise _Rejected("PI_RETURN_" + code, message)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _bounded_json(value: Any) -> None:
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        _require(count <= 250_000 and depth <= 32, "INPUT_LIMIT", "Design exceeds the bounded input size or nesting limit.")
        if isinstance(item, float):
            _require(math.isfinite(item), "NONFINITE_INPUT", "Design numbers must be finite.")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def _prepare(design: dict, request: dict) -> tuple[SpiDeR, dict[str, dict]]:
    keys = {"contract", "occurrence_id", "forward_net", "return_net", "source_pad_id", "load_pad_ids", "mesh_target_mm"}
    _require(isinstance(request, dict) and set(request) == keys and request.get("contract") == REQUEST,
             "REQUEST_CONTRACT", "Expected the exact spike/pi-return-path-request/v1 request fields.")
    _require(all(_text(request.get(key)) for key in ("occurrence_id", "forward_net", "return_net", "source_pad_id")),
             "REQUEST_IDENTITY", "Occurrence, net and source pad identities must be nonempty canonical strings.")
    loads = request["load_pad_ids"]
    _require(isinstance(loads, list) and 1 <= len(loads) <= 32 and all(_text(value) for value in loads),
             "LOAD_LIMIT", "Select 1 to 32 load return pad IDs.")
    _require(len(set(loads)) == len(loads) and request["source_pad_id"] not in loads,
             "TERMINAL_IDENTITY", "Load pads must be unique and different from the source pad.")
    target = request["mesh_target_mm"]
    _require(type(target) in (int, float) and math.isfinite(target) and 0.05 <= target <= 1000,
             "MESH_TARGET", "Mesh target must be a finite number between 0.05 and 1000 mm.")
    _require(request["return_net"] != request["forward_net"], "NET_IDENTITY", "Forward and return nets must differ.")
    _require(isinstance(design, dict), "DESIGN_CONTRACT", "Design must be a SpiDeR dictionary.")
    _bounded_json(design)
    _require(design.get("contract", "spike/v1") == "spike/v1" and design.get("units", "mm") == "mm",
             "DESIGN_CONTRACT", "Only millimetre SpiDeR v1 designs are admitted.")
    if "occurrence_id" in design:
        _require(design["occurrence_id"] == request["occurrence_id"], "OCCURRENCE_MISMATCH", "Design occurrence does not match the request.")
    net_names: dict[str, str] = {}
    nets = design.get("nets", [])
    entries = nets.items() if isinstance(nets, dict) else ((net.get("id"), net.get("name")) for net in nets if isinstance(net, dict))
    for identity, name in entries:
        _require(isinstance(identity, (str, int)) and not isinstance(identity, bool) and _text(name),
                 "NET_MAPPING", "Every declared net needs an ID and canonical name.")
        _require(str(identity) not in net_names, "NET_MAPPING", "Net IDs must be unique.")
        net_names[str(identity)] = name
    normalized = {field.name: deepcopy(design[field.name]) for field in fields(SpiDeR) if field.name in design}
    for collection in ("layers", "stackup", "components"):
        _require(isinstance(normalized.get(collection, []), list) and all(isinstance(item, dict) for item in normalized.get(collection, [])),
                 "DESIGN_CONTRACT", "Layer, stackup and component collections must contain dictionaries.")
    normalized["nets"] = [{"id": key, "name": name} for key, name in net_names.items()]
    copper_layers = set(ordered_copper_layer_names(SpiDeR(**normalized)))
    _require(bool(copper_layers), "LAYER_IDENTITY", "The design must declare its physical copper layers.")
    for layer in normalized.get("stackup", []):
        for key in ("thickness", "thickness_mm"):
            if key in layer:
                _require(type(layer[key]) in (int, float) and 0 < layer[key] <= 1e6,
                         "DESIGN_GEOMETRY", "Declared stackup thickness must be positive finite millimetres.")
    all_names = set(net_names.values())
    pads: dict[str, dict] = {}
    geometry_ids: set[str] = set()
    work = 0.0
    for kind in ("pads", "tracks", "vias", "zones"):
        objects = normalized.get(kind, [])
        _require(isinstance(objects, list) and len(objects) <= 5000, "INPUT_LIMIT", "Each copper collection is limited to 5000 objects.")
        for item in objects:
            _require(isinstance(item, dict), "DESIGN_GEOMETRY", "Copper objects must be dictionaries.")
            direct = [item[key] for key in ("net_name", "net") if item.get(key) not in (None, "")]
            mapped = net_names.get(str(item["net_id"])) if "net_id" in item else None
            _require(all(_text(name) for name in direct) and len(set(direct)) <= 1
                     and ("net_id" not in item or mapped is not None)
                     and (not direct or mapped is None or mapped == direct[0]),
                     "NET_MAPPING", "Copper net name and declared net ID must resolve consistently.")
            name = direct[0] if direct else mapped or ""
            item["net_name"] = name
            if name:
                all_names.add(name)
            identity = item.get("id")
            if kind == "pads":
                _require(_text(identity), "PAD_IDENTITY", "Every pad must have an explicit canonical ID.")
                _require(identity not in pads, "PAD_IDENTITY", "Duplicate pad IDs make terminals ambiguous.")
                pads[identity] = item
            if identity:
                _require(isinstance(identity, str) and identity not in geometry_ids, "GEOMETRY_IDENTITY", "Copper object IDs must be unique across geometry kinds.")
                geometry_ids.add(identity)
            if name != request["return_net"]:
                continue
            _require(_text(identity), "GEOMETRY_IDENTITY", "Return copper objects require explicit IDs; generated IDs cannot establish terminal ownership.")
            layer_names = item.get("layers", [item["layer"]] if "layer" in item else [])
            _require(isinstance(layer_names, list) and bool(layer_names)
                     and all(isinstance(layer, str) and (layer in copper_layers or kind == "pads" and layer in {"*.Cu", "F&B.Cu"})
                             for layer in layer_names if not isinstance(layer, str) or layer.endswith(".Cu"))
                     and any(layer in copper_layers or layer in {"*.Cu", "F&B.Cu"} for layer in layer_names),
                     "LAYER_IDENTITY", "Return copper must reference explicit declared copper layers.")
            for key in ("width", "diameter", "thickness", "plating_thickness"):
                if key in item:
                    value = item[key]
                    _require(type(value) in (int, float) and 0 < value <= 1e6, "DESIGN_GEOMETRY", "Copper dimensions must be positive finite millimetres.")
            if kind == "zones":
                _require(item.get("filled_copper_state") == "source_filled", "ZONE_FILL_REQUIRED", "Return zones require authoritative source-filled copper polygons; refill and reimport the board.")
                _require(not item.get("holes") and item.get("source_fill_provenance_complete") is not False,
                         "ZONE_GEOMETRY_UNSUPPORTED", "Zone holes and incomplete source-fill provenance are not admitted by this route planner.")
            coordinates = [item.get(key) for key in ("start", "end", "at") if key in item]
            for point in coordinates:
                xy = [point.get("x"), point.get("y")] if isinstance(point, dict) else point
                _require(isinstance(xy, list) and len(xy) >= 2 and all(type(v) in (int, float) and abs(v) <= 1e6 for v in xy[:2]),
                         "DESIGN_GEOMETRY", "Geometry positions must contain bounded finite x/y coordinates in mm.")
            if kind == "pads":
                _require("at" in item and isinstance(item.get("size"), list) and len(item["size"]) == 2
                         and all(type(v) in (int, float) and 0 < v <= 1e6 for v in item["size"]),
                         "DESIGN_GEOMETRY", "Return pads require an explicit position and positive copper size.")
                _require(item.get("shape", "rect") in {"rect", "circle", "oval", "custom"}, "PAD_SHAPE_UNSUPPORTED",
                         "Return routing requires an admitted pad boundary; bounding-box pad approximations are blocked.")
            if kind == "tracks":
                _require("start" in item and "end" in item and "width" in item, "DESIGN_GEOMETRY", "Return tracks require explicit endpoints and width.")
                def xy(point):
                    return (point["x"], point["y"]) if isinstance(point, dict) else point[:2]
                work += math.dist(xy(item["start"]), xy(item["end"])) / target + 1
            elif kind == "vias":
                _require("at" in item and type(item.get("drill")) in (int, float) and 0 < item["drill"] <= 1e6
                         and len(layer_names) >= 2, "DESIGN_GEOMETRY", "Vias require position, positive drill and explicit layer span.")
                work += len(layer_names)
            elif kind == "zones":
                points = item.get("points", item.get("polygon", []))
                _require(isinstance(points, list) and 3 <= len(points) <= 2048, "DESIGN_GEOMETRY", "Filled zones require 3 to 2048 polygon points.")
                xs = [float(p["x"] if isinstance(p, dict) else p[0]) for p in points]
                ys = [float(p["y"] if isinstance(p, dict) else p[1]) for p in points]
                span_x, span_y = max(xs) - min(xs), max(ys) - min(ys)
                cell = target * math.sqrt(max(1, span_x * span_y / target ** 2 / 3000))
                work += max(1, math.ceil(span_x / cell)) * max(1, math.ceil(span_y / cell))
            else:
                width, height = item["size"]
                cell = min(target, width, height)
                work += (math.ceil(width / cell) + 1) * (math.ceil(height / cell) + 1) * len(copper_layers)
    _require(work <= 250_000, "MESH_LIMIT", "Estimated meshing work exceeds the planning limit; coarsen the mesh or isolate a smaller design.")
    _require(request["forward_net"] in all_names and request["return_net"] in all_names,
             "UNKNOWN_NET", "Requested nets must exist in the loaded design.")
    for identity in [request["source_pad_id"], *loads]:
        _require(identity in pads, "UNKNOWN_PAD", "A requested terminal pad does not exist in this design.")
        _require(pads[identity]["net_name"] == request["return_net"], "PAD_NET_MISMATCH", "Every terminal must belong to the explicit return net.")
    return SpiDeR(**normalized), pads


def _routes(mesh, pads: dict, request: dict) -> list[dict]:
    _require(len(mesh.nodes) <= 100_000 and len(mesh.branches) <= MAX_BRANCHES, "MESH_LIMIT", "Mesh exceeds the route planning capacity.")
    nodes = {node.id: node for node in mesh.nodes}
    _require(len(nodes) == len(mesh.nodes), "INVALID_MESH", "Mesh node IDs must be unique.")
    adjacency = {identity: [] for identity in nodes}
    owned: dict[str, set[int]] = {}
    for node in nodes.values():
        _require(node.net == request["return_net"] and all(math.isfinite(v) for v in (node.x_mm, node.y_mm, node.z_mm)),
                 "INVALID_MESH", "Mesh nodes must be finite and belong to the selected return net.")
    for branch in mesh.branches:
        _require(branch.node_p in nodes and branch.node_n in nodes and branch.net == request["return_net"],
                 "INVALID_MESH", "Mesh branch ownership or endpoints are invalid.")
        _require(all(math.isfinite(v) and v > 0 for v in (branch.width_mm, branch.thickness_mm, branch.conductivity_s_m)),
                 "INVALID_MESH", "Branch cross section and conductivity must be finite and positive.")
        resistance, length = branch.resistance_ohm, branch.length_mm
        _require(math.isfinite(resistance) and resistance >= 0 and math.isfinite(length), "INVALID_MESH", "Branch resistance or length is invalid.")
        adjacency[branch.node_p].append((branch.node_n, resistance, length))
        adjacency[branch.node_n].append((branch.node_p, resistance, length))
        if branch.source_id in pads:
            owned.setdefault(branch.source_id, set()).update((branch.node_p, branch.node_n))
    for cell in mesh.cells:
        if cell.get("source_kind") == "pad" and cell.get("source_id") in pads:
            identity = cell.get("node_id")
            if identity in nodes:
                owned.setdefault(cell["source_id"], set()).add(identity)
    anchors = {}
    for identity in [request["source_pad_id"], *request["load_pad_ids"]]:
        _require(bool(owned.get(identity)), "PAD_UNMESHED", f"Pad {identity} has no exact owned copper node in the admitted mesh.")
        at = pads[identity]["at"]
        x, y = (at["x"], at["y"]) if isinstance(at, dict) else at[:2]
        anchors[identity] = min(owned[identity], key=lambda n: (math.hypot(nodes[n].x_mm - x, nodes[n].y_mm - y), n))
    source = anchors[request["source_pad_id"]]
    distances = {source: 0.0}
    previous: dict[int, tuple[int, float]] = {}
    queue = [(0.0, source)]
    while queue:
        distance, current = heapq.heappop(queue)
        if distance != distances[current]:
            continue
        for neighbor, resistance, length in adjacency[current]:
            candidate = distance + resistance
            _require(math.isfinite(candidate), "NUMERICAL_RANGE", "Accumulated route resistance exceeds the finite numeric range.")
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = current, length
                heapq.heappush(queue, (candidate, neighbor))
    paths = []
    total_points = 0
    for identity in request["load_pad_ids"]:
        terminal = anchors[identity]
        path = {"load_pad_id": identity, "connected": terminal in distances,
                "resistance_ohm": None, "length_mm": None, "points_mm": []}
        if terminal in distances:
            route, length = [terminal], 0.0
            while route[-1] != source:
                parent, segment = previous[route[-1]]
                route.append(parent)
                length += segment
            route.reverse()
            if len(route) == 1:
                route.append(source)
            total_points += len(route)
            _require(total_points <= MAX_POINTS, "OUTPUT_LIMIT", "Route points exceed the response limit; coarsen the mesh.")
            path.update(resistance_ohm=distances[terminal], length_mm=length,
                        points_mm=[[nodes[n].x_mm, nodes[n].y_mm, nodes[n].z_mm] for n in route])
        paths.append(path)
    return paths


def plan_pi_return_path(design: dict, request: dict) -> dict:
    """Return contract-valid connected/disconnected evidence, or a blocked diagnostic."""
    result: dict = {"contract": RESULT, "status": "blocked", "paths": [], "issues": [], "model_status": "approximate"}
    try:
        normalized, pads = _prepare(design, request)
        input_issues = design.get("issues", [])
        _require(isinstance(input_issues, list) and all(isinstance(issue, dict) for issue in input_issues),
                 "DESIGN_CONTRACT", "Design issues must be diagnostic dictionaries.")
        result["issues"].extend(deepcopy(issue) for issue in input_issues if _text(issue.get("message")))
        _require(not any(issue.get("severity") == "error" for issue in input_issues),
                 "DESIGN_BLOCKED", "Resolve blocking import diagnostics before planning return paths.")
        mesh = build_hybrid_mesh(normalized, AnalysisSpec(mode="dc", net_names=[request["return_net"]], mesh={
            "target_size_mm": request["mesh_target_mm"], "max_conductors": MAX_BRANCHES,
            "max_zone_cells": 3000, "max_pad_cells": 3000, "feature_aware": False,
            "node_tolerance_mm": 1e-5,
        }))
        result["issues"].extend(asdict(issue) for issue in mesh.issues)
        _require(not mesh.truncated and not any(issue.severity == "error" or issue.code in {"SPIKE-BE-MESH-W-0002", "SPIKE-BE-MESH-W-0003"} for issue in mesh.issues),
                 "MESH_BLOCKED", "Copper mesh is incomplete or contains blocking diagnostics.")
        result["paths"] = _routes(mesh, pads, request)
        result["status"] = "connected" if all(path["connected"] for path in result["paths"]) else "disconnected"
        result["request"] = deepcopy(request)
        result["issues"].append({"code": "PI_RETURN_APPROXIMATE", "severity": "warning", "message":
            "Minimum series-resistance route on the admitted copper mesh, including modeled attachment resistance. "
            "It is not equivalent terminal resistance, current distribution, loop inductance or a high-frequency optimum. "
            "Pad anchoring, source geometry, copper material defaults and mesh resolution limit accuracy."})
        if result["status"] == "disconnected":
            result["issues"].append({"code": "PI_RETURN_DISCONNECTED", "severity": "warning", "message":
                "One or more load pads have no route to the source on the admitted return copper mesh. Inspect source copper and mesh resolution."})
    except _Rejected as error:
        result.update(status="blocked", paths=[])
        result["issues"].append({"code": error.code, "severity": "error", "message": str(error)})
    except (TypeError, ValueError, KeyError, IndexError, OverflowError, ZeroDivisionError) as error:
        result.update(status="blocked", paths=[])
        result["issues"].append({"code": "PI_RETURN_INVALID_GEOMETRY", "severity": "error", "message": f"Copper geometry could not be admitted: {error}"})
    return result
