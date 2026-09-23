"""Deterministic planning boundary for multi-board PI and SI analyses.

The planner makes retained board and harness scope explicit before any solver is
allowed to run.  It deliberately does not turn a connectivity graph into a
physics qualification claim: independent per-board execution is available to
existing solver routes, while coupled harness execution remains fail-closed
until a solver adapter consumes this exact graph contract.
"""

from __future__ import annotations

import hashlib
import json
from math import isfinite
from typing import Any, Dict, Iterable, Mapping, Sequence

from .assembly_scale import (
    MAX_BOARDS,
    MAX_BOARD_EXTENT_MM,
    MAX_COMPONENTS_PER_BOARD,
    MAX_COPPER_LAYERS,
    MAX_NETS_PER_BOARD,
    design_scale,
)
from .design_ir_v2 import AssemblyIRV1


REQUEST_CONTRACT = "spike/multiboard-analysis-request/v1"
PLAN_CONTRACT = "spike/multiboard-analysis-plan/v1"
MAX_BOARD_DIMENSION_MM = MAX_BOARD_EXTENT_MM
SUPPORTED_DOMAINS = {"pi", "si"}
SUPPORTED_MODES = {"independent_board_batch", "coupled_harness_network"}


class MultiboardAnalysisError(ValueError):
    """Raised for malformed or ambiguous multi-board requests."""


def _digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _xy(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 2:
        return None
    try:
        x, y = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    return (x, y) if isfinite(x) and isfinite(y) else None


def _points(value: Any) -> Iterable[tuple[float, float]]:
    point = _xy(value)
    if point is not None:
        yield point
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            yield from _points(item)


def _design_summary(raw: Any) -> Dict[str, Any]:
    design = _mapping(raw)
    scale = design_scale(design)
    counts = {key: len(design.get(key) or []) for key in ("tracks", "arcs", "vias", "pads", "zones", "regions")}
    coordinates: list[tuple[float, float]] = []
    coordinate_fields = {
        "tracks": ("start_mm", "end_mm", "start", "end"),
        "arcs": ("start_mm", "mid_mm", "end_mm", "start", "mid", "end"),
        "vias": ("position_mm", "at", "position"),
        "pads": ("position_mm", "at", "position"),
        "components": ("position_mm", "at", "position"),
        "zones": ("polygons_mm", "polygon", "outline", "points"),
        "regions": ("outlines_mm", "outline", "points"),
    }
    for collection, fields in coordinate_fields.items():
        for entity in design.get(collection) or []:
            item = _mapping(entity)
            for field in fields:
                if field in item:
                    coordinates.extend(_points(item[field]))
    if scale["board_size_mm"] is not None:
        dimensions = list(scale["board_size_mm"])
        bounds = None
    elif coordinates:
        xs = [point[0] for point in coordinates]
        ys = [point[1] for point in coordinates]
        bounds = [min(xs), min(ys), max(xs), max(ys)]
        dimensions = [bounds[2] - bounds[0], bounds[3] - bounds[1]]
    else:
        bounds = None
        dimensions = None
    return {
        "copper_layers": scale["copper_layers"],
        "nets": scale["nets"],
        "components": scale["components"],
        **counts,
        "primitive_count": scale["primitives"],
        "bounds_mm": bounds,
        "dimensions_mm": dimensions,
    }


def _endpoint(value: str, known_boards: set[str]) -> Dict[str, str]:
    raw = str(value or "")
    # AssemblyIR/viewport endpoint references use ``board::connector``.  Keep
    # the original single-colon form for imported projects, but prefer the
    # unambiguous canonical separator so the connector identity is preserved.
    separator = "::" if "::" in raw else ":"
    board_id, found, connector_id = raw.partition(separator)
    board_id = board_id.strip()
    connector_id = connector_id.strip()
    if not found or not board_id or not connector_id:
        raise MultiboardAnalysisError(f"Harness endpoint {value!r} must use board_id:connector_or_pin syntax.")
    if board_id not in known_boards:
        raise MultiboardAnalysisError(f"Harness endpoint {value!r} references an unknown board instance.")
    return {"board_id": board_id, "connector_id": connector_id, "endpoint": f"{board_id}:{connector_id}"}


def plan_multiboard_analysis(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate and normalize a bounded multi-board PI/SI execution plan."""

    if not isinstance(raw, Mapping) or raw.get("contract") != REQUEST_CONTRACT:
        raise MultiboardAnalysisError(f"Multi-board request contract must be {REQUEST_CONTRACT}.")
    domain = str(raw.get("domain") or "").strip().lower()
    mode = str(raw.get("mode") or "").strip().lower()
    if domain not in SUPPORTED_DOMAINS:
        raise MultiboardAnalysisError("Multi-board domain must be pi or si.")
    if mode not in SUPPORTED_MODES:
        raise MultiboardAnalysisError("Multi-board mode must be independent_board_batch or coupled_harness_network.")
    assembly_raw = raw.get("assembly")
    designs_raw = raw.get("designs")
    if not isinstance(assembly_raw, Mapping) or not isinstance(designs_raw, Mapping):
        raise MultiboardAnalysisError("Multi-board requests require assembly and designs objects.")
    assembly = AssemblyIRV1.from_dict(assembly_raw)
    if not assembly.boards:
        raise MultiboardAnalysisError("Multi-board analysis requires at least one board instance.")
    if len(assembly.boards) > MAX_BOARDS:
        raise MultiboardAnalysisError(f"Multi-board analysis supports at most {MAX_BOARDS} board instances.")

    board_ids = {board.id for board in assembly.boards}
    selected_raw = raw.get("selected_board_ids")
    selected = sorted(board_ids) if selected_raw is None else [str(value).strip() for value in selected_raw]
    if not selected or any(not value for value in selected) or len(selected) != len(set(selected)):
        raise MultiboardAnalysisError("selected_board_ids must contain unique non-empty board identities.")
    unknown = sorted(set(selected) - board_ids)
    if unknown:
        raise MultiboardAnalysisError(f"selected_board_ids references unknown boards: {', '.join(unknown[:5])}.")
    selected_set = set(selected)

    issues: list[Dict[str, Any]] = []
    boards: list[Dict[str, Any]] = []
    for board in sorted(assembly.boards, key=lambda item: item.id):
        if board.id not in selected_set:
            continue
        design = designs_raw.get(board.design_id)
        if not isinstance(design, Mapping):
            issues.append({
                "code": "MULTIBOARD_DESIGN_UNRESOLVED", "severity": "error",
                "entity_id": board.id,
                "message": f"Board {board.id} references unavailable design {board.design_id}.",
            })
            continue
        summary = _design_summary(design)
        if summary["copper_layers"] < 1 or summary["copper_layers"] > MAX_COPPER_LAYERS:
            issues.append({
                "code": "MULTIBOARD_LAYER_LIMIT", "severity": "error", "entity_id": board.id,
                "message": f"Board {board.id} has {summary['copper_layers']} copper layers; supported range is 1 through {MAX_COPPER_LAYERS}.",
            })
        if summary["components"] > MAX_COMPONENTS_PER_BOARD:
            issues.append({
                "code": "MULTIBOARD_COMPONENT_LIMIT", "severity": "error", "entity_id": board.id,
                "message": f"Board {board.id} has {summary['components']} components; supported maximum is {MAX_COMPONENTS_PER_BOARD}.",
            })
        if summary["nets"] > MAX_NETS_PER_BOARD:
            issues.append({
                "code": "MULTIBOARD_NET_LIMIT", "severity": "error", "entity_id": board.id,
                "message": f"Board {board.id} has {summary['nets']} nets; supported maximum is {MAX_NETS_PER_BOARD}.",
            })
        dimensions = summary["dimensions_mm"]
        if dimensions is None:
            issues.append({
                "code": "MULTIBOARD_BOUNDS_UNAVAILABLE", "severity": "warning", "entity_id": board.id,
                "message": f"Board {board.id} has no retained geometry bounds; the 1 m dimension policy could not be verified.",
            })
        elif max(dimensions) > MAX_BOARD_DIMENSION_MM:
            issues.append({
                "code": "MULTIBOARD_DIMENSION_LIMIT", "severity": "error", "entity_id": board.id,
                "message": f"Board {board.id} dimensions are {dimensions[0]:.3f} x {dimensions[1]:.3f} mm; each axis is limited to {MAX_BOARD_DIMENSION_MM:.0f} mm.",
            })
        boards.append({
            "board_id": board.id,
            "design_id": board.design_id,
            "namespace": f"{assembly.assembly_id}/{board.id}",
            "frame_id": board.frame.frame_id,
            "transform": list(board.frame.transform),
            **summary,
        })

    harnesses: list[Dict[str, Any]] = []
    omitted_harness_ids: list[str] = []
    for harness in sorted(assembly.harnesses, key=lambda item: item.id):
        endpoint_a = _endpoint(harness.endpoint_a, board_ids)
        endpoint_b = _endpoint(harness.endpoint_b, board_ids)
        if endpoint_a["board_id"] == endpoint_b["board_id"]:
            raise MultiboardAnalysisError(f"Harness {harness.id} must connect two distinct board instances.")
        if endpoint_a["board_id"] not in selected_set or endpoint_b["board_id"] not in selected_set:
            omitted_harness_ids.append(harness.id)
            continue
        harnesses.append({
            "harness_id": harness.id,
            "endpoint_a": endpoint_a,
            "endpoint_b": endpoint_b,
            "length_mm": harness.length_mm,
            "conductor_material_id": harness.conductor_material_id,
            "gauge_awg": harness.gauge_awg,
            "pin_map": {str(key): str(value) for key, value in sorted(harness.pin_map.items())},
        })

    graph = {
        "assembly_id": assembly.assembly_id,
        "domain": domain,
        "boards": boards,
        "harnesses": harnesses,
        "connector_mappings": [item.to_dict() for item in sorted(assembly.connector_mappings, key=lambda item: item.id)],
    }
    graph_digest = _digest(graph)
    coupled = mode == "coupled_harness_network"
    if coupled:
        issues.append({
            "code": "MULTIBOARD_COUPLED_SOLVER_NOT_QUALIFIED", "severity": "error",
            "message": "The board/harness graph is valid, but no qualified PI or SI adapter currently consumes coupled cross-board entities.",
        })
    admitted = bool(boards) and not any(issue["severity"] == "error" for issue in issues)
    result: Dict[str, Any] = {
        "contract": PLAN_CONTRACT,
        "request_contract": REQUEST_CONTRACT,
        "domain": domain,
        "mode": mode,
        "state": "admitted" if admitted else "blocked",
        "can_plan": admitted,
        "independent_jobs_admissible": admitted and not coupled,
        "can_execute_coupled": False,
        "coupled_physics": False,
        "execution_strategy": "single_board_dispatch_required" if not coupled else "none",
        "board_limit": MAX_BOARDS,
        "copper_layer_limit_per_board": MAX_COPPER_LAYERS,
        "board_dimension_limit_mm": MAX_BOARD_DIMENSION_MM,
        "component_limit_per_board": MAX_COMPONENTS_PER_BOARD,
        "net_limit_per_board": MAX_NETS_PER_BOARD,
        "selected_board_ids": selected,
        "omitted_harness_ids": omitted_harness_ids,
        "graph": graph,
        "graph_digest": graph_digest,
        "issues": issues,
        "meaning": (
            "An admitted independent plan preserves board identity but still requires caller-controlled single-board dispatch and excludes cross-board coupling. "
            "A coupled plan remains blocked until a solver consumes the retained harness graph and passes PI/SI validation."
        ),
    }
    result["plan_digest"] = _digest(result)
    return result
