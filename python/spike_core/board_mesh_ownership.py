"""Bounded whole-board accounting for admitted conductor-volume ownership.

The existing :mod:`mesh_ownership` audit proves that every supplied volume is
inside its canonical copper owner.  This sidecar adds the other half of the
contract: every canonical copper source in the declared mesh scope is recorded
exactly once as owned, intentionally omitted, or unsupported.  It deliberately
does not claim that unsupported source primitives, native overlays, fields, or
physics have been completed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import fields
import json
from math import hypot, isfinite
from typing import Any, Callable, Dict, Mapping, Sequence

from .contracts import DesignIR
from .design_ir_v2_schema import content_digest
from .hybrid_mesh import (
    _custom_pad_local_polygon,
    _net,
    _normalize_filled_zone_polygon,
    _pad_drill_size,
    _pad_is_plated,
    _pad_layers,
    _pad_size,
    _point,
)
from .layers import copper_stack_profile
from .mesh_ownership import audit_dc_conductor_volume_ownership


CONTRACT = "spike/pcb-board-mesh-ownership/v1"
ERROR_CODE = "SPIKE-BE-MESH-E-0017"
MESH_CONTRACT = "spike/mesh/v3"
GEOMETRY_CONTRACT = "spike/v1"

MAX_SOURCE_RECORDS = 131_072
MAX_MESH_CELLS = 1_048_576
MAX_WORK_STEPS = 16_777_216
MAX_SERIALIZED_BYTES = 67_108_864


class BoardMeshOwnershipError(ValueError):
    code = ERROR_CODE


def _fail(message: str) -> None:
    raise BoardMeshOwnershipError(f"{ERROR_CODE}: {message}")


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BoardMeshOwnershipError(
            f"{ERROR_CODE}: ownership inputs must be finite JSON values"
        ) from error


def _design(value: DesignIR | Mapping[str, Any]) -> tuple[DesignIR, Dict[str, Any]]:
    if isinstance(value, DesignIR):
        payload = value.to_dict()
        design = value
    elif isinstance(value, Mapping):
        payload = dict(value)
        allowed = {item.name for item in fields(DesignIR)}
        try:
            design = DesignIR(**{key: payload[key] for key in allowed if key in payload})
        except (TypeError, ValueError) as error:
            raise BoardMeshOwnershipError(
                f"{ERROR_CODE}: source geometry is not a valid SPIKE v1 solver projection"
            ) from error
    else:
        _fail("source geometry must be a DesignIR or mapping")
    if str(payload.get("contract") or "") != GEOMETRY_CONTRACT:
        _fail("board ownership v1 requires a spike/v1 solver geometry projection")
    if not str(payload.get("design_id") or "").strip():
        _fail("source geometry requires a non-empty design identity")
    return design, payload


def _cancel(cancel_check: Callable[[], Any] | None) -> None:
    if cancel_check is not None and bool(cancel_check()):
        _fail("board ownership generation was cancelled")


def _source_id(record: Mapping[str, Any], kind: str, index: int) -> str:
    fields_for_kind = ("id", "component_pad") if kind == "pad" else ("id",)
    for field in fields_for_kind:
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return f"{kind}-{index + 1}"


def _mesh_scope(
    mesh: Mapping[str, Any], design: DesignIR, cells: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    raw = mesh.get("scope")
    source_nets = {
        _net(item) for records in (design.tracks, design.zones, design.pads, design.vias)
        for item in records if _net(item)
    }
    cell_nets = {str(item.get("net") or "") for item in cells if str(item.get("net") or "")}
    if isinstance(raw, Mapping):
        requested = raw.get("requested_nets", ())
        if not isinstance(requested, Sequence) or isinstance(requested, (str, bytes)):
            _fail("mesh scope requested_nets must be an array")
        requested_nets = sorted({str(value) for value in requested if str(value)})
        all_nets = raw.get("all_nets")
        if not isinstance(all_nets, bool):
            _fail("mesh scope all_nets must be boolean")
        if all_nets and requested_nets:
            _fail("an all-net mesh scope cannot also name requested nets")
    elif source_nets.issubset(cell_nets):
        # Compatibility for pre-sidecar mesh fixtures which already contain
        # every electrically owned source net.  Ambiguous partial meshes below
        # are rejected instead of guessing their requested scope.
        all_nets, requested_nets = True, []
    else:
        _fail("partial mesh ownership requires explicit requested-net scope")
    if not all_nets and not requested_nets:
        _fail("partial mesh ownership requires at least one requested net")
    unexpected = cell_nets - (source_nets if all_nets else set(requested_nets))
    if unexpected:
        _fail("mesh cells escape the declared requested-net scope")
    return {"all_nets": all_nets, "requested_nets": requested_nets}


def _selected(net: str, scope: Mapping[str, Any]) -> bool:
    return bool(net) and (
        bool(scope["all_nets"]) or net in set(scope["requested_nets"])
    )


def _unsupported_reason(kind: str, record: Mapping[str, Any], design: DesignIR) -> str:
    try:
        if kind == "track":
            start, end = _point(record.get("start", (0, 0))), _point(record.get("end", (0, 0)))
            width = float(record.get("width", 0.0))
            if not isfinite(width) or width <= 0 or hypot(end[0] - start[0], end[1] - start[1]) <= 1e-9:
                return "unsupported_geometry"
        elif kind == "zone":
            polygon = _normalize_filled_zone_polygon(
                [_point(value) for value in record.get("points", ())]
            )
            if len(polygon) < 3:
                return "unsupported_geometry"
        elif kind == "pad":
            if str(record.get("shape", "rect")).lower() == "custom" and not _custom_pad_local_polygon(dict(record)):
                return "unsupported_geometry"
            width, height = _pad_size(dict(record))
            if min(width, height) <= 0:
                return "unsupported_geometry"
            drill_width, drill_height = _pad_drill_size(dict(record))
            if (not _pad_is_plated(dict(record)) and max(drill_width, drill_height) > 0
                    and not _net(dict(record))):
                return "non_electrical_unplated_hole"
            if not _pad_layers(dict(record), copper_stack_profile(design)[0]):
                return "unsupported_geometry"
        elif kind == "via":
            diameter = float(record.get("size", record.get("diameter", 0.0)))
            drill = float(record.get("drill", 0.0))
            layers = record.get("layers", ())
            if (not isfinite(diameter) or not isfinite(drill) or drill <= 0
                    or diameter <= drill or not isinstance(layers, Sequence)
                    or isinstance(layers, (str, bytes)) or len(layers) < 2):
                return "unsupported_geometry"
    except (IndexError, TypeError, ValueError):
        return "unsupported_geometry"
    return "admitted_source_emitted_no_volume"


def build_board_mesh_ownership_overlay(
    mesh: Mapping[str, Any], *, source_geometry: DesignIR | Mapping[str, Any],
    cancel_check: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    """Build deterministic ownership/accounting evidence for one supplied mesh."""

    if not isinstance(mesh, Mapping) or str(mesh.get("contract") or "") != MESH_CONTRACT:
        _fail("board ownership v1 requires a spike/mesh/v3 input")
    # Pre-sidecar v3 fixtures did not always persist the dimension even though
    # every cell already carries volumetric topology.  Accept that exact legacy
    # shape, while rejecting any explicit non-volume declaration below.
    if str(mesh.get("dimension") or "volume_3d") != "volume_3d":
        _fail("board ownership requires volume_3d conductor cells")
    if bool(mesh.get("truncated")):
        _fail("resource-truncated meshes are ineligible for ownership evidence")
    raw_cells = mesh.get("cells")
    if not isinstance(raw_cells, Sequence) or isinstance(raw_cells, (str, bytes)):
        _fail("mesh cells must be an array")
    cells = [dict(item) for item in raw_cells if isinstance(item, Mapping)]
    if len(cells) != len(raw_cells) or not cells:
        _fail("mesh cells must be non-empty objects")
    if len(cells) > MAX_MESH_CELLS:
        _fail("mesh cell count exceeds the board ownership resource limit")
    if any(str(item.get("kind") or "") != "volume" for item in cells):
        _fail("board ownership accepts only conductor volume cells")

    design, geometry_payload = _design(source_geometry)
    source_count = sum(len(records) for records in (
        design.tracks, design.zones, design.pads, design.vias,
    ))
    if not 0 < source_count <= MAX_SOURCE_RECORDS:
        _fail("source record count is outside the board ownership resource limit")
    serialized_bytes = len(_canonical_bytes(geometry_payload)) + len(_canonical_bytes(dict(mesh)))
    if serialized_bytes > MAX_SERIALIZED_BYTES:
        _fail("canonical ownership inputs exceed the 64 MiB serialized limit")
    vertex_references = sum(len(item.get("vertices_mm", ())) for item in cells)
    work_steps = source_count + len(cells) + vertex_references
    if work_steps > MAX_WORK_STEPS:
        _fail("board ownership work estimate exceeds its admitted limit")

    scope = _mesh_scope(mesh, design, cells)
    _cancel(cancel_check)
    try:
        supplied_audit = audit_dc_conductor_volume_ownership(design, cells)
    except ValueError as error:
        raise BoardMeshOwnershipError(
            f"{ERROR_CODE}: supplied conductor-volume ownership failed: {error}"
        ) from error
    _cancel(cancel_check)

    grouped: Dict[tuple[str, str], list[str]] = defaultdict(list)
    for index, cell in enumerate(cells):
        if index % 256 == 0:
            _cancel(cancel_check)
        cell_kind = str(cell.get("source_kind") or "")
        owner_kind = "pad" if cell_kind == "pad_barrel" else cell_kind
        grouped[(owner_kind, str(cell.get("source_id") or ""))].append(str(cell["id"]))

    records: list[Dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for kind, source_items in (
        ("track", design.tracks), ("zone", design.zones),
        ("pad", design.pads), ("via", design.vias),
    ):
        for index, source in enumerate(source_items):
            if len(records) % 256 == 0:
                _cancel(cancel_check)
            source_id = _source_id(source, kind, index)
            source_key = (kind, source_id)
            if source_key in seen_keys:
                _fail(f"duplicate canonical source {kind}:{source_id}")
            seen_keys.add(source_key)
            cell_ids = sorted(grouped.pop(source_key, ()))
            net = _net(source)
            if cell_ids:
                if not _selected(net, scope):
                    _fail(f"mesh cells exist for out-of-scope source {kind}:{source_id}")
                status, reason = "owned", "owned_by_exact_volume_containment"
            elif not net:
                status, reason = "intentionally_omitted", (
                    "non_electrical_unplated_hole"
                    if _unsupported_reason(kind, source, design) == "non_electrical_unplated_hole"
                    else "source_has_no_electrical_net"
                )
            elif not _selected(net, scope):
                status, reason = "intentionally_omitted", "outside_requested_net_scope"
            else:
                status, reason = "unsupported", _unsupported_reason(kind, source, design)
            records.append({
                "source_key": f"{kind}:{source_id}", "source_kind": kind,
                "source_id": source_id, "status": status,
                "mesh_cell_count": len(cell_ids),
                "mesh_cell_ids_sha256": content_digest(cell_ids),
                "reason_code": reason,
            })
    if grouped:
        _fail("mesh cells contain an owner not present in canonical source accounting")
    records.sort(key=lambda item: (item["source_kind"], item["source_id"]))
    counts = Counter(item["status"] for item in records)
    owned_cells = sum(item["mesh_cell_count"] for item in records if item["status"] == "owned")
    if owned_cells != len(cells):
        _fail("owned mesh-cell accounting is incomplete")

    return {
        "contract": CONTRACT,
        "source": {
            "mesh_contract": MESH_CONTRACT,
            "mesh_sha256": content_digest(dict(mesh)),
            "geometry_contract": GEOMETRY_CONTRACT,
            "geometry_sha256": content_digest(geometry_payload),
            "design_id": str(geometry_payload["design_id"]),
            "scope": scope,
        },
        "source_records": records,
        "accounting": {
            "status": "passed", "supplied_source_count": len(records),
            "supplied_mesh_cell_count": len(cells),
            "owned_source_count": counts["owned"], "owned_mesh_cell_count": owned_cells,
            "intentionally_omitted_source_count": counts["intentionally_omitted"],
            "intentionally_omitted_mesh_cell_count": 0,
            "unsupported_source_count": counts["unsupported"],
            "unsupported_mesh_cell_count": 0, "all_source_records_accounted": True,
            "supplied_geometry_audit": supplied_audit,
        },
        "resources": {
            "maximum_source_records": MAX_SOURCE_RECORDS,
            "maximum_mesh_cells": MAX_MESH_CELLS,
            "maximum_work_steps": MAX_WORK_STEPS,
            "maximum_serialized_bytes": MAX_SERIALIZED_BYTES,
            "actual_source_records": len(records), "actual_mesh_cells": len(cells),
            "actual_work_steps": work_steps, "actual_serialized_bytes": serialized_bytes,
            "cancellation_supported": True,
        },
        "qualification": {
            "state": "bounded_supplied_copper_ownership_only",
            "all_supplied_geometry_owned": True,
            "complete_board_copper_coverage": False,
            "native_geometric_overlay_verified": False,
            "field_convergence_performed": False,
            "physics_ready": False, "solver_ready": False,
        },
    }


def validate_board_mesh_ownership_overlay(
    report: Mapping[str, Any], *, mesh: Mapping[str, Any],
    source_geometry: DesignIR | Mapping[str, Any],
) -> Dict[str, Any]:
    regenerated = build_board_mesh_ownership_overlay(
        mesh, source_geometry=source_geometry,
    )
    if dict(report) != regenerated:
        _fail("board ownership overlay does not match deterministic regeneration")
    return regenerated


__all__ = [
    "CONTRACT", "ERROR_CODE", "BoardMeshOwnershipError",
    "build_board_mesh_ownership_overlay", "validate_board_mesh_ownership_overlay",
]
