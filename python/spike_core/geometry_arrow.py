"""Deterministic Apache Arrow projection for canonical copper geometry."""

from __future__ import annotations

from typing import Any, Iterable

from .design_ir_v2 import DesignIRV2, content_digest


GEOMETRY_ARROW_CONTRACT_V1 = "spike/copper-geometry-arrow/v1"
GEOMETRY_ARROW_CONTRACT_V2 = "spike/copper-geometry-arrow/v2"
GEOMETRY_ARROW_CONTRACT_V3 = "spike/copper-geometry-arrow/v3"
GEOMETRY_ARROW_CONTRACT_V4 = "spike/copper-geometry-arrow/v4"
# Compatibility alias for callers and acceptance probes that intentionally
# exercise the path-less v1 projection.
GEOMETRY_ARROW_CONTRACT = GEOMETRY_ARROW_CONTRACT_V1
GEOMETRY_ARROW_CONTRACTS = frozenset((
    GEOMETRY_ARROW_CONTRACT_V1, GEOMETRY_ARROW_CONTRACT_V2, GEOMETRY_ARROW_CONTRACT_V3,
    GEOMETRY_ARROW_CONTRACT_V4,
))
GEOMETRY_ARROW_TABLE_NAME = "copper_geometry"
GEOMETRY_ARROW_MEMBER_NAME = "copper_geometry.arrow"
MAX_GEOMETRY_ARROW_ROWS = 10_000_000
MAX_GEOMETRY_ARROW_IPC_BYTES = 256 * 1024 * 1024
_ROW_COLUMNS = (
    "kind", "id", "source_id", "name", "net_id", "layer_id", "layer_ids",
    "start_x_mm", "start_y_mm", "mid_x_mm", "mid_y_mm", "end_x_mm", "end_y_mm",
    "center_x_mm", "center_y_mm", "width_mm", "size_x_mm", "size_y_mm",
    "diameter_mm", "drill_mm", "drill_x_mm", "drill_y_mm", "drill_shape",
    "start_layer_id", "end_layer_id", "via_type", "shape", "component_id", "pin_id",
    "plated", "outlines_mm", "holes_mm",
)
_PATH_COLUMNS = ("path_id", "path_step_index", "path_step_count", "path_end_cap", "path_join_style")
_BOUNDARY_COLUMNS = ("boundary_rings", "fill_style_id", "fill_property")
_LAND_PROFILE_COLUMNS = ("land_profiles",)


class GeometryArrowError(ValueError):
    """Raised when an Arrow geometry table is unavailable or invalid."""


def _validate_decode_limits(*, max_ipc_bytes: int, max_rows: int) -> None:
    if (not isinstance(max_ipc_bytes, int) or isinstance(max_ipc_bytes, bool)
            or not 0 < max_ipc_bytes <= MAX_GEOMETRY_ARROW_IPC_BYTES):
        raise GeometryArrowError("Geometry Arrow IPC byte limit is invalid.")
    if (not isinstance(max_rows, int) or isinstance(max_rows, bool)
            or not 0 < max_rows <= MAX_GEOMETRY_ARROW_ROWS):
        raise GeometryArrowError("Geometry Arrow row limit is invalid.")


def _geometry_row_count(design: DesignIRV2) -> int:
    """Count projected rows without constructing their nested Python values."""
    return sum(len(items) for items in (
        design.tracks, design.arcs, design.zones, design.pads, design.vias,
    ))


def _require_row_budget(design: DesignIRV2, max_rows: int) -> None:
    if _geometry_row_count(design) > max_rows:
        raise GeometryArrowError(f"Geometry table exceeds the {max_rows}-row limit.")


def _pyarrow():
    try:
        import pyarrow as pa
    except (ImportError, OSError) as exc:
        raise GeometryArrowError(
            "Apache Arrow geometry support requires the pinned pyarrow runtime."
        ) from exc
    return pa


def canonical_design_digest(design: DesignIRV2) -> str:
    payload = design.to_dict()
    for name in (
        "materials", "layers", "nets", "tracks", "arcs", "zones", "pads", "vias", "drills",
        "castellations", "pins", "components", "component_bonds", "connectors", "regions",
        "bends", "models", "constraints", "variants", "simulation_models",
    ):
        payload[name] = sorted(payload.get(name, []), key=lambda item: str(item.get("id", "")))
    return content_digest(payload)


def geometry_arrow_contract(design: DesignIRV2) -> str:
    if any(item.land_profiles for item in [*design.pads, *design.vias]):
        return GEOMETRY_ARROW_CONTRACT_V4
    if any(item.boundary_rings for item in design.zones):
        return GEOMETRY_ARROW_CONTRACT_V3
    return GEOMETRY_ARROW_CONTRACT_V2 if any(item.path is not None for item in design.tracks) else GEOMETRY_ARROW_CONTRACT_V1


def _metadata(design: DesignIRV2, contract: str) -> dict[bytes, bytes]:
    return {
        b"spike.contract": contract.encode("ascii"),
        b"spike.table": GEOMETRY_ARROW_TABLE_NAME.encode("ascii"),
        b"spike.design_id": design.design_id.encode("utf-8"),
        b"spike.design_ir_sha256": canonical_design_digest(design).encode("ascii"),
        b"spike.units": b"mm",
        b"spike.frame_id": design.frame.frame_id.encode("utf-8"),
    }


def _schema(design: DesignIRV2, contract: str):
    pa = _pyarrow()
    point = pa.struct([pa.field("x_mm", pa.float64(), nullable=False), pa.field("y_mm", pa.float64(), nullable=False)])
    polygons = pa.list_(pa.list_(point))
    boundary_segment = pa.struct([
        pa.field("kind", pa.string(), nullable=False), pa.field("end_mm", point, nullable=False),
        pa.field("center_mm", point), pa.field("clockwise", pa.bool_()),
    ])
    boundary_ring = pa.struct([
        pa.field("role", pa.string(), nullable=False), pa.field("start_mm", point, nullable=False),
        pa.field("segments", pa.list_(boundary_segment), nullable=False),
    ])
    land_profile = pa.struct([
        pa.field("layer_id", pa.string(), nullable=False), pa.field("use", pa.string(), nullable=False),
        pa.field("shape", pa.string(), nullable=False),
        pa.field("size_mm", point, nullable=False), pa.field("offset_mm", point, nullable=False),
        pa.field("source_primitive_id", pa.string(), nullable=False),
    ])
    fields = [
        pa.field("kind", pa.string(), nullable=False),
        pa.field("id", pa.string(), nullable=False),
        pa.field("source_id", pa.string(), nullable=False),
        pa.field("name", pa.string(), nullable=False),
        pa.field("net_id", pa.string(), nullable=False),
        pa.field("layer_id", pa.string()),
        pa.field("layer_ids", pa.list_(pa.string())),
        pa.field("start_x_mm", pa.float64()), pa.field("start_y_mm", pa.float64()),
        pa.field("mid_x_mm", pa.float64()), pa.field("mid_y_mm", pa.float64()),
        pa.field("end_x_mm", pa.float64()), pa.field("end_y_mm", pa.float64()),
        pa.field("center_x_mm", pa.float64()), pa.field("center_y_mm", pa.float64()),
        pa.field("width_mm", pa.float64()),
        pa.field("size_x_mm", pa.float64()), pa.field("size_y_mm", pa.float64()),
        pa.field("diameter_mm", pa.float64()), pa.field("drill_mm", pa.float64()),
        pa.field("drill_x_mm", pa.float64()), pa.field("drill_y_mm", pa.float64()),
        pa.field("drill_shape", pa.string()),
        pa.field("start_layer_id", pa.string()), pa.field("end_layer_id", pa.string()),
        pa.field("via_type", pa.string()), pa.field("shape", pa.string()),
        pa.field("component_id", pa.string()), pa.field("pin_id", pa.string()),
        pa.field("plated", pa.bool_()),
        pa.field("outlines_mm", polygons), pa.field("holes_mm", polygons),
    ]
    if contract in {GEOMETRY_ARROW_CONTRACT_V2, GEOMETRY_ARROW_CONTRACT_V3, GEOMETRY_ARROW_CONTRACT_V4}:
        fields.extend([
            pa.field("path_id", pa.string()),
            pa.field("path_step_index", pa.int32()),
            pa.field("path_step_count", pa.int32()),
            pa.field("path_end_cap", pa.string()),
            pa.field("path_join_style", pa.string()),
        ])
    elif contract != GEOMETRY_ARROW_CONTRACT_V1:
        raise GeometryArrowError(f"Unsupported geometry Arrow contract: {contract}")
    if contract in {GEOMETRY_ARROW_CONTRACT_V3, GEOMETRY_ARROW_CONTRACT_V4}:
        fields.extend([
            pa.field("boundary_rings", pa.list_(boundary_ring)),
            pa.field("fill_style_id", pa.string()), pa.field("fill_property", pa.string()),
        ])
    if contract == GEOMETRY_ARROW_CONTRACT_V4:
        fields.append(pa.field("land_profiles", pa.list_(land_profile)))
    return pa.schema(fields, metadata=_metadata(design, contract))


def _polygons(value: Iterable[Iterable[tuple[float, float]]]) -> list[list[dict[str, float]]]:
    return [[{"x_mm": float(point[0]), "y_mm": float(point[1])} for point in polygon] for polygon in value]


def _boundary_rings(value: Iterable[Any]) -> list[dict[str, Any]]:
    return [{
        "role": ring.role,
        "start_mm": {"x_mm": float(ring.start_mm[0]), "y_mm": float(ring.start_mm[1])},
        "segments": [{
            "kind": segment.kind,
            "end_mm": {"x_mm": float(segment.end_mm[0]), "y_mm": float(segment.end_mm[1])},
            "center_mm": None if segment.center_mm is None else {
                "x_mm": float(segment.center_mm[0]), "y_mm": float(segment.center_mm[1]),
            },
            "clockwise": segment.clockwise,
        } for segment in ring.segments],
    } for ring in value]


def _land_profiles(value: Iterable[Any]) -> list[dict[str, Any]]:
    return [{
        "layer_id": item.layer_id, "use": item.use, "shape": item.shape,
        "size_mm": {"x_mm": float(item.size_mm[0]), "y_mm": float(item.size_mm[1])},
        "offset_mm": {"x_mm": float(item.offset_mm[0]), "y_mm": float(item.offset_mm[1])},
        "source_primitive_id": item.source_primitive_id,
    } for item in value]


def canonical_geometry_rows(
    design: DesignIRV2,
    *,
    contract: str | None = None,
    max_rows: int = MAX_GEOMETRY_ARROW_ROWS,
) -> list[dict[str, Any]]:
    _validate_decode_limits(max_ipc_bytes=MAX_GEOMETRY_ARROW_IPC_BYTES, max_rows=max_rows)
    _require_row_budget(design, max_rows)
    contract = contract or geometry_arrow_contract(design)
    if contract not in GEOMETRY_ARROW_CONTRACTS:
        raise GeometryArrowError(f"Unsupported geometry Arrow contract: {contract}")
    rows: list[dict[str, Any]] = []

    def base(kind: str, entity: Any) -> dict[str, Any]:
        return {
            "kind": kind,
            "id": entity.id,
            "source_id": entity.source_id,
            "name": entity.name,
            "net_id": entity.net_id,
        }

    for item in design.tracks:
        row = {**base("track", item), "layer_id": item.layer_id,
               "start_x_mm": item.start_mm[0], "start_y_mm": item.start_mm[1],
               "end_x_mm": item.end_mm[0], "end_y_mm": item.end_mm[1], "width_mm": item.width_mm}
        if contract in {GEOMETRY_ARROW_CONTRACT_V2, GEOMETRY_ARROW_CONTRACT_V3, GEOMETRY_ARROW_CONTRACT_V4} and item.path is not None:
            row.update({
                "path_id": item.path.path_id,
                "path_step_index": item.path.step_index,
                "path_step_count": item.path.step_count,
                "path_end_cap": item.path.end_cap,
                "path_join_style": item.path.join_style,
            })
        rows.append(row)
    for item in design.arcs:
        rows.append({**base("arc", item), "layer_id": item.layer_id,
                     "start_x_mm": item.start_mm[0], "start_y_mm": item.start_mm[1],
                     "mid_x_mm": item.mid_mm[0], "mid_y_mm": item.mid_mm[1],
                     "end_x_mm": item.end_mm[0], "end_y_mm": item.end_mm[1], "width_mm": item.width_mm})
    for item in design.zones:
        row = {**base("zone", item), "layer_ids": sorted(item.layer_ids),
               "outlines_mm": _polygons(item.outlines_mm), "holes_mm": _polygons(item.holes_mm)}
        if contract in {GEOMETRY_ARROW_CONTRACT_V3, GEOMETRY_ARROW_CONTRACT_V4} and item.boundary_rings:
            row.update({"boundary_rings": _boundary_rings(item.boundary_rings),
                        "fill_style_id": item.fill_style_id, "fill_property": item.fill_property})
        rows.append(row)
    for item in design.pads:
        row = {**base("pad", item), "layer_ids": sorted(item.layer_ids),
                     "center_x_mm": item.center_mm[0], "center_y_mm": item.center_mm[1],
                     "size_x_mm": item.size_mm[0], "size_y_mm": item.size_mm[1],
                     "shape": item.shape, "component_id": item.component_id,
                     "pin_id": item.pin_id, "plated": item.plated,
                     "drill_x_mm": item.drill_size_mm[0], "drill_y_mm": item.drill_size_mm[1],
                     "drill_shape": item.drill_shape}
        if contract == GEOMETRY_ARROW_CONTRACT_V4 and item.land_profiles:
            row["land_profiles"] = _land_profiles(item.land_profiles)
        rows.append(row)
    for item in design.vias:
        row = {**base("via", item), "center_x_mm": item.center_mm[0], "center_y_mm": item.center_mm[1],
                     "diameter_mm": item.diameter_mm, "drill_mm": item.drill_mm,
                     "start_layer_id": item.start_layer_id, "end_layer_id": item.end_layer_id,
                     "via_type": item.via_type}
        if contract == GEOMETRY_ARROW_CONTRACT_V4 and item.land_profiles:
            row["land_profiles"] = _land_profiles(item.land_profiles)
        rows.append(row)
    rows.sort(key=lambda row: (str(row["kind"]), str(row["id"])))
    if contract == GEOMETRY_ARROW_CONTRACT_V4:
        columns = (*_ROW_COLUMNS, *_PATH_COLUMNS, *_BOUNDARY_COLUMNS, *_LAND_PROFILE_COLUMNS)
    elif contract == GEOMETRY_ARROW_CONTRACT_V3:
        columns = (*_ROW_COLUMNS, *_PATH_COLUMNS, *_BOUNDARY_COLUMNS)
    elif contract == GEOMETRY_ARROW_CONTRACT_V2:
        columns = (*_ROW_COLUMNS, *_PATH_COLUMNS)
    else:
        columns = _ROW_COLUMNS
    return [{name: row.get(name) for name in columns} for row in rows]


def _serialize_geometry_arrow(
    design: DesignIRV2,
    *,
    contract: str | None = None,
    max_rows: int = MAX_GEOMETRY_ARROW_ROWS,
) -> bytes:
    pa = _pyarrow()
    contract = contract or geometry_arrow_contract(design)
    rows = canonical_geometry_rows(design, contract=contract, max_rows=max_rows)
    table = pa.Table.from_pylist(rows, schema=_schema(design, contract))
    sink = pa.BufferOutputStream()
    options = pa.ipc.IpcWriteOptions(compression=None)
    with pa.ipc.new_file(sink, table.schema, options=options) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes()


def build_geometry_arrow(design: DesignIRV2) -> bytes:
    result = _serialize_geometry_arrow(design)
    validate_geometry_arrow(result, design)
    return result


def validate_geometry_arrow(
    data: bytes,
    design: DesignIRV2,
    *,
    max_ipc_bytes: int = MAX_GEOMETRY_ARROW_IPC_BYTES,
    max_rows: int = MAX_GEOMETRY_ARROW_ROWS,
) -> list[dict[str, Any]]:
    _validate_decode_limits(max_ipc_bytes=max_ipc_bytes, max_rows=max_rows)
    if not isinstance(data, bytes):
        raise GeometryArrowError("Geometry member must contain Arrow IPC bytes.")
    if len(data) > max_ipc_bytes:
        raise GeometryArrowError(f"Geometry Arrow IPC payload exceeds the {max_ipc_bytes}-byte limit.")
    if len(data) < 12 or not data.startswith(b"ARROW1") or not data.endswith(b"ARROW1"):
        raise GeometryArrowError("Geometry member is not a valid Arrow IPC file.")
    # The DesignIR is the trusted source for this design-bound projection.
    # Reject its projected row count before building nested canonical values.
    _require_row_budget(design, max_rows)
    pa = _pyarrow()
    try:
        reader = pa.ipc.open_file(pa.BufferReader(data))
    except (pa.ArrowException, OSError, ValueError) as exc:
        raise GeometryArrowError("Geometry member is not a valid Arrow IPC file.") from exc
    metadata = reader.schema.metadata or {}
    try:
        contract = metadata.get(b"spike.contract", b"").decode("ascii")
    except UnicodeDecodeError as exc:
        raise GeometryArrowError("Geometry Arrow contract metadata is invalid.") from exc
    expected_contract = geometry_arrow_contract(design)
    if contract != expected_contract:
        raise GeometryArrowError(
            f"Geometry Arrow contract {contract!r} does not match the required {expected_contract!r} projection."
        )
    expected_bytes = _serialize_geometry_arrow(design, contract=contract, max_rows=max_rows)
    if data != expected_bytes:
        raise GeometryArrowError(
            "Geometry Arrow bytes do not exactly match the canonical uncompressed DesignIR projection."
        )
    expected_schema = _schema(design, contract)
    if not reader.schema.equals(expected_schema, check_metadata=True):
        raise GeometryArrowError("Geometry Arrow schema or DesignIR binding metadata is invalid.")
    # Do not decode untrusted record batches.  Exact equality above proves the
    # file is the local, uncompressed serialization, so return those local
    # canonical rows instead of materializing Arrow buffers into Python.
    return canonical_geometry_rows(design, contract=contract, max_rows=max_rows)
