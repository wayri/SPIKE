# SPDX-License-Identifier: Apache-2.0
"""Canonical supported-subset DesignIR handoff for the private SPIKES compiler.

This module only translates normalized planar layout records.  It deliberately
does not perform Boolean operations, mesh generation, terminal construction,
physics execution, or capability qualification.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Iterable, Mapping, Sequence

from .design_ir_v2 import DesignIRV2
from .spikes_layout_adapter import (
    design_ir_artifact_identity,
    preflight_layout_candidate,
    validate_layout_request,
)
from .spikes_layout_contract import SpikesLayoutAdapterError, is_digest


DESIGNIR_LAYOUT_HANDOFF_CONTRACT = (
    "spike/designir-layout-handoff/v1-supported-planar-subset"
)

_CONDUCTOR_LAYER_TYPES = {"copper", "signal", "power", "mixed", "conductor"}
_DIELECTRIC_LAYER_TYPES = {
    "dielectric", "substrate", "core", "prepreg", "soldermask", "solder_mask"
}
_UNSUPPORTED_COLLECTIONS = (
    "drills", "castellations", "pins", "components", "component_bonds",
    "connectors", "regions", "bends", "models", "constraints", "variants",
    "simulation_models",
)
_MAX_ID_BYTES = 1024
_MAX_RECORDS = 8_000_000
_MAX_POLYGON_POINTS = 64_000_000
_MAX_CANONICAL_BYTES = 1 << 30


def _fail(code: str, message: str) -> None:
    raise SpikesLayoutAdapterError(code, message)


def _coerce(value: Any) -> DesignIRV2:
    if isinstance(value, DesignIRV2):
        return value
    if not isinstance(value, Mapping) or value.get("contract") != "spike/design-ir/v2":
        _fail("SPIKE-LAYOUT-HANDOFF-0001", "candidate must be complete DesignIR v2")
    try:
        return DesignIRV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        _fail("SPIKE-LAYOUT-HANDOFF-0001", f"candidate is invalid: {exc}")
    raise AssertionError("unreachable")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label} must be finite")
    return 0.0 if result == 0.0 else result


def _positive(value: Any, label: str, *, zero: bool = False) -> float:
    result = _finite(value, label)
    if (zero and result < 0.0) or (not zero and result <= 0.0):
        _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label} has an invalid sign")
    return result


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("SPIKE-LAYOUT-HANDOFF-0002", f"{label} is empty")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        _fail("SPIKE-LAYOUT-HANDOFF-0002", f"{label} is not valid UTF-8")
    if size > _MAX_ID_BYTES:
        _fail("SPIKE-LAYOUT-HANDOFF-0002", f"{label} exceeds {_MAX_ID_BYTES} bytes")
    return value


def _point(value: Sequence[Any], label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label} must contain two coordinates")
    return [_finite(value[0], f"{label}.x"), _finite(value[1], f"{label}.y")]


def _id_list(values: Sequence[Any], label: str) -> list[str]:
    if not isinstance(values, (list, tuple)) or not values:
        _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label} must not be empty")
    result = sorted((_identity(value, label) for value in values),
                    key=lambda value: value.encode("utf-8"))
    if len(result) != len(set(result)):
        _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label} contains duplicates")
    return result


def _frame(design: DesignIRV2) -> Dict[str, Any]:
    frame = design.frame
    if frame.units != "mm" or frame.handedness != "right" or frame.parent_frame_id:
        _fail(
            "SPIKE-LAYOUT-HANDOFF-0003",
            "only root, right-handed millimetre frames are supported",
        )
    values = tuple(_finite(item, "frame transform") for item in frame.transform)
    tolerance = 1.0e-12
    expected_bottom = (0.0, 0.0, 0.0, 1.0)
    if any(abs(values[12 + i] - expected_bottom[i]) > tolerance for i in range(4)):
        _fail("SPIKE-LAYOUT-HANDOFF-0003", "frame transform is not affine")
    rotation = [
        values[0], values[1], values[2],
        values[4], values[5], values[6],
        values[8], values[9], values[10],
    ]
    for row in range(3):
        for column in range(3):
            dot = math.fsum(rotation[3 * row + axis] * rotation[3 * column + axis]
                            for axis in range(3))
            target = 1.0 if row == column else 0.0
            if abs(dot - target) > tolerance:
                _fail("SPIKE-LAYOUT-HANDOFF-0003", "frame rotation is not orthonormal")
    determinant = (
        rotation[0] * (rotation[4] * rotation[8] - rotation[5] * rotation[7])
        - rotation[1] * (rotation[3] * rotation[8] - rotation[5] * rotation[6])
        + rotation[2] * (rotation[3] * rotation[7] - rotation[4] * rotation[6])
    )
    if abs(determinant - 1.0) > tolerance:
        _fail("SPIKE-LAYOUT-HANDOFF-0003", "frame rotation is not right-handed")
    return {
        "frame_id": _identity(frame.frame_id, "frame ID"),
        "parent_frame_id": "",
        "units": "mm",
        "rotation": rotation,
        "translation_mm": [values[3], values[7], values[11]],
    }


def _optional_positive(value: Any, label: str, *, zero: bool = False) -> float | None:
    return None if value is None else _positive(value, label, zero=zero)


def _materials(design: DesignIRV2) -> list[Dict[str, Any]]:
    result: list[Dict[str, Any]] = []
    for item in sorted(design.materials, key=lambda value: value.id.encode("utf-8")):
        record: Dict[str, Any] = {
            "public_id": _identity(item.id, "material ID"),
            "material_class": str(item.material_class),
        }
        optional = (
            ("electrical_conductivity_s_per_m", item.conductivity_s_per_m, False),
            ("relative_permittivity", item.relative_permittivity, False),
            ("loss_tangent", item.loss_tangent, True),
            ("thermal_conductivity_w_per_mk", item.thermal_conductivity_w_per_mk, False),
            ("density_kg_per_m3", item.density_kg_per_m3, False),
            ("heat_capacity_j_per_kgk", item.heat_capacity_j_per_kgk, False),
        )
        for name, value, zero in optional:
            normalized = _optional_positive(value, f"material {item.id} {name}", zero=zero)
            if normalized is not None:
                if name == "loss_tangent" and normalized > 1.0:
                    _fail("SPIKE-LAYOUT-HANDOFF-0005", "loss tangent exceeds one")
                record[name] = normalized
        result.append(record)
    if not result:
        _fail("SPIKE-LAYOUT-HANDOFF-0005", "at least one material is required")
    return result


def _layers(design: DesignIRV2, materials: Mapping[str, Dict[str, Any]]) -> list[Dict[str, Any]]:
    result: list[Dict[str, Any]] = []
    for item in sorted(design.layers, key=lambda value: (value.order, value.id.encode("utf-8"))):
        kind_text = item.layer_type.lower()
        if kind_text in _CONDUCTOR_LAYER_TYPES:
            kind = "conductor"
        elif kind_text in _DIELECTRIC_LAYER_TYPES:
            kind = "dielectric"
        else:
            _fail("SPIKE-LAYOUT-HANDOFF-0004", f"layer type {item.layer_type!r} is unsupported")
        if item.material_id not in materials:
            _fail("SPIKE-LAYOUT-HANDOFF-0005", f"layer {item.id} lacks a supported material")
        thickness = _positive(item.thickness_mm, f"layer {item.id} thickness")
        bottom = _finite(item.z_mm, f"layer {item.id} z")
        material = materials[item.material_id]
        if kind == "conductor" and "electrical_conductivity_s_per_m" not in material:
            _fail("SPIKE-LAYOUT-HANDOFF-0005", "conductor material lacks conductivity")
        if kind == "dielectric" and "relative_permittivity" not in material:
            _fail("SPIKE-LAYOUT-HANDOFF-0005", "dielectric material lacks permittivity")
        result.append({
            "public_id": _identity(item.id, "layer ID"), "kind": kind,
            "order": item.order, "z_bottom_mm": bottom,
            "z_top_mm": bottom + thickness, "material_id": item.material_id,
        })
    if not result:
        _fail("SPIKE-LAYOUT-HANDOFF-0005", "at least one physical layer is required")
    if any(isinstance(item["order"], bool) or not isinstance(item["order"], int) or
           item["order"] < 0 for item in result):
        _fail("SPIKE-LAYOUT-HANDOFF-0005", "layer orders must be nonnegative integers")
    if len({item["order"] for item in result}) != len(result):
        _fail("SPIKE-LAYOUT-HANDOFF-0005", "layer orders must be unique")
    for previous, current in zip(result, result[1:]):
        if current["order"] <= previous["order"]:
            _fail("SPIKE-LAYOUT-HANDOFF-0005", "layer order must increase with z")
        if abs(current["z_bottom_mm"] - previous["z_top_mm"]) > 1.0e-12:
            _fail("SPIKE-LAYOUT-HANDOFF-0005", "supported stackups must be contiguous")
        # Bind a tolerance-certified shared interface to one exact binary64
        # value so the private non-overlap check cannot see a one-ulp overlap
        # produced solely by z_bottom + thickness evaluation.
        previous["z_top_mm"] = current["z_bottom_mm"]
    return result


def _rings(values: Iterable[Sequence[Any]], label: str) -> list[list[list[float]]]:
    result: list[list[list[float]]] = []
    for index, ring in enumerate(values):
        if not isinstance(ring, (list, tuple)) or len(ring) < 3:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label}[{index}] has too few points")
        points = [_point(point, f"{label}[{index}]") for point in ring]
        if points[0] == points[-1]:
            points.pop()
        if len(points) < 3 or len({tuple(point) for point in points}) < 3:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", f"{label}[{index}] is degenerate")
        result.append(points)
    return result


def _supported_sources(design: DesignIRV2) -> Dict[str, list[Dict[str, Any]]]:
    tracks = []
    for item in sorted(design.tracks, key=lambda value: value.id.encode("utf-8")):
        if item.path is not None:
            _fail("SPIKE-LAYOUT-HANDOFF-0004", "track-path joining is unsupported")
        start = _point(item.start_mm, "track start")
        end = _point(item.end_mm, "track end")
        if start == end:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", "track endpoints must be distinct")
        tracks.append({
            "public_id": _identity(item.id, "track ID"), "net_id": item.net_id,
            "layer_id": item.layer_id, "start_mm": start, "end_mm": end,
            "width_mm": _positive(item.width_mm, "track width"),
        })
    arcs = []
    for item in sorted(design.arcs, key=lambda value: value.id.encode("utf-8")):
        points = [_point(item.start_mm, "arc start"), _point(item.mid_mm, "arc mid"),
                  _point(item.end_mm, "arc end")]
        if len({tuple(point) for point in points}) != 3:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", "arc points must be distinct")
        orientation = ((points[1][0] - points[0][0]) * (points[2][1] - points[0][1]) -
                       (points[1][1] - points[0][1]) * (points[2][0] - points[0][0]))
        if orientation == 0.0:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", "arc points must not be collinear")
        arcs.append({
            "public_id": _identity(item.id, "arc ID"), "net_id": item.net_id,
            "layer_id": item.layer_id, "start_mm": points[0], "mid_mm": points[1],
            "end_mm": points[2], "width_mm": _positive(item.width_mm, "arc width"),
        })
    zones = []
    for item in sorted(design.zones, key=lambda value: value.id.encode("utf-8")):
        if item.boundary_rings or len(item.outlines_mm) != 1:
            _fail("SPIKE-LAYOUT-HANDOFF-0004", "zones require one point-only outer ring")
        if not (item.filled_copper_state == "source_filled" and
                item.source_fill_provenance_complete and
                item.source_fill_representation == "flat_polygon_path"):
            _fail("SPIKE-LAYOUT-HANDOFF-0004", "zone fill provenance is unresolved")
        outer = _rings(item.outlines_mm, f"zone {item.id} outer")[0]
        holes = _rings(item.holes_mm, f"zone {item.id} holes")
        zones.append({
            "public_id": _identity(item.id, "zone ID"), "net_id": item.net_id,
            "layer_ids": _id_list(item.layer_ids, f"zone {item.id} layer IDs"),
            "outer_mm": outer, "holes_mm": holes,
            "fill_provenance": {
                "state": "source_filled", "complete": True,
                "representation": "flat_polygon_path",
                "group_id": _identity(item.source_fill_group_id, "zone fill group ID"),
                "group_sha256": item.source_fill_group_sha256,
                "component_ordinal": item.source_fill_component_ordinal,
                "component_count": item.source_fill_component_count,
                "component_sha256": item.source_fill_component_sha256,
            },
        })
    pads = []
    for item in sorted(design.pads, key=lambda value: value.id.encode("utf-8")):
        if (item.shape not in {"rectangle", "circle"} or item.component_id or item.pin_id or
                item.land_profiles or item.custom_geometry or item.plated or
                item.drill_shape != "none" or any(value != 0.0 for value in item.drill_size_mm)):
            _fail("SPIKE-LAYOUT-HANDOFF-0004", f"pad {item.id} geometry is unsupported")
        size = _point(item.size_mm, f"pad {item.id} size")
        _positive(size[0], "pad size x"); _positive(size[1], "pad size y")
        if item.shape == "circle" and size[0] != size[1]:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", "circular pads require equal dimensions")
        pads.append({
            "public_id": _identity(item.id, "pad ID"), "net_id": item.net_id,
            "component_id": "",
            "layer_ids": _id_list(item.layer_ids, f"pad {item.id} layer IDs"),
            "center_mm": _point(item.center_mm, f"pad {item.id} center"),
            "size_x_mm": size[0], "size_y_mm": size[1], "shape": item.shape,
        })
    vias = []
    for item in sorted(design.vias, key=lambda value: value.id.encode("utf-8")):
        if item.via_type not in {"through", "blind", "buried"} or item.land_profiles:
            _fail("SPIKE-LAYOUT-HANDOFF-0004", f"via {item.id} process is unsupported")
        plating = _optional_positive(item.plating_mm, f"via {item.id} plating")
        if plating is None:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", "vias require explicit plating thickness")
        diameter = _positive(item.diameter_mm, f"via {item.id} diameter")
        drill = _positive(item.drill_mm, f"via {item.id} drill")
        if diameter <= drill or drill + 2.0 * plating > diameter:
            _fail("SPIKE-LAYOUT-HANDOFF-0006", "via plating geometry is inconsistent")
        vias.append({
            "public_id": _identity(item.id, "via ID"), "net_id": item.net_id,
            "center_mm": _point(item.center_mm, f"via {item.id} center"),
            "diameter_mm": diameter, "drill_mm": drill,
            "start_layer_id": item.start_layer_id, "end_layer_id": item.end_layer_id,
            "plating_mm": plating, "via_type": item.via_type,
        })
    return {"tracks": tracks, "arcs": arcs, "zones": zones, "pads": pads, "vias": vias}


def _canonical_payload(document: Mapping[str, Any]) -> bytes:
    payload = copy.deepcopy(dict(document))
    payload.pop("identity", None)
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        _fail("SPIKE-LAYOUT-HANDOFF-0007", f"handoff cannot be canonicalized: {exc}")
    if len(encoded) > _MAX_CANONICAL_BYTES:
        _fail("SPIKE-LAYOUT-HANDOFF-0007", "handoff canonical bytes exceed the bound")
    return encoded


def build_designir_layout_handoff(
    request_document: Any, candidate: Any, *, baseline: Any | None = None,
    parent: Any | None = None,
) -> Dict[str, Any]:
    """Compile a preflighted DesignIR v2 autorouter candidate to the public handoff."""
    request = validate_layout_request(request_document)
    design = _coerce(candidate)
    preflight = preflight_layout_candidate(
        request, design, baseline=baseline, parent=parent,
    )
    if request["consumer"]["kind"] != "autorouter":
        _fail("SPIKE-LAYOUT-HANDOFF-0004", "only the autorouter subset is supported")
    if not is_digest(design.source.source_digest):
        _fail("SPIKE-LAYOUT-HANDOFF-0002", "source digest must be lowercase SHA-256")
    for collection in _UNSUPPORTED_COLLECTIONS:
        if getattr(design, collection):
            _fail("SPIKE-LAYOUT-HANDOFF-0004", f"{collection} are unsupported")
    if (design.retained_padstack_occurrence_groups or
            design.retained_nonregular_padstack_geometry is not None or
            design.retained_standard_contour_land_geometry is not None):
        _fail("SPIKE-LAYOUT-HANDOFF-0004", "retained padstack geometry is unsupported")

    material_records = _materials(design)
    material_lookup = {item["public_id"]: item for item in material_records}
    layer_records = _layers(design, material_lookup)
    source_records = _supported_sources(design)
    record_count = sum(len(items) for items in source_records.values())
    if record_count > _MAX_RECORDS:
        _fail("SPIKE-LAYOUT-HANDOFF-0007", "source entity count exceeds the bound")
    point_count = sum(
        len(zone["outer_mm"]) + sum(len(hole) for hole in zone["holes_mm"])
        for zone in source_records["zones"]
    )
    if point_count > _MAX_POLYGON_POINTS:
        _fail("SPIKE-LAYOUT-HANDOFF-0007", "polygon point count exceeds the bound")
    supported_ids = {
        item["public_id"] for records in source_records.values() for item in records
    }
    if any(item not in supported_ids for item in request.get("changed_entity_ids", [])):
        _fail("SPIKE-LAYOUT-HANDOFF-0004", "changed entities leave the supported subset")

    lineage: Dict[str, Any] = {
        "source_sha256": design.source.source_digest,
        "candidate_sha256": design_ir_artifact_identity(design)["sha256"],
    }
    for key in ("parent_candidate_sha256", "baseline_sha256"):
        if key in preflight:
            lineage[key] = preflight[key]
    result: Dict[str, Any] = {
        "contract": DESIGNIR_LAYOUT_HANDOFF_CONTRACT,
        "consumer_kind": "autorouter",
        "lineage": lineage,
        "frame": _frame(design),
        "materials": material_records,
        "layers": layer_records,
        "nets": [{"public_id": _identity(item.id, "net ID")}
                 for item in sorted(design.nets, key=lambda value: value.id.encode("utf-8"))],
        **source_records,
        "changed_entity_ids": sorted(request.get("changed_entity_ids", []),
                                     key=lambda value: value.encode("utf-8")),
        "claims": {
            "supported_planar_subset": True,
            "solid_boolean_meshing_performed": False,
            "conforming_volume_mesh_generated": False,
            "product_em_ready": False,
        },
    }
    payload = _canonical_payload(result)
    result["identity"] = {
        "canonical_bytes": len(payload),
        "canonical_sha256": hashlib.sha256(payload).hexdigest(),
    }
    return result


def canonical_designir_layout_handoff_json(document: Mapping[str, Any]) -> str:
    """Serialize a generated handoff including its evidence deterministically."""
    validate_designir_layout_handoff_identity(document)
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def validate_designir_layout_handoff_identity(document: Mapping[str, Any]) -> None:
    """Recompute the bounded canonical evidence carried by a handoff."""
    if not isinstance(document, Mapping) or document.get("contract") != DESIGNIR_LAYOUT_HANDOFF_CONTRACT:
        _fail("SPIKE-LAYOUT-HANDOFF-0001", "handoff contract is unsupported")
    identity = document.get("identity")
    if not isinstance(identity, Mapping) or set(identity) != {"canonical_bytes", "canonical_sha256"}:
        _fail("SPIKE-LAYOUT-HANDOFF-0001", "handoff identity is malformed")
    payload = _canonical_payload(document)
    if identity.get("canonical_bytes") != len(payload) or identity.get("canonical_sha256") != hashlib.sha256(payload).hexdigest():
        _fail("SPIKE-LAYOUT-HANDOFF-0002", "handoff canonical identity differs")


__all__ = [
    "DESIGNIR_LAYOUT_HANDOFF_CONTRACT",
    "build_designir_layout_handoff",
    "canonical_designir_layout_handoff_json",
    "validate_designir_layout_handoff_identity",
]
