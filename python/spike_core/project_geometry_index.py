"""Geometry-index canonicalization and generated Arrow package members."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Type

from .design_ir_v2 import DesignIRV2
from .geometry_arrow import (
    GEOMETRY_ARROW_CONTRACTS, GEOMETRY_ARROW_MEMBER_NAME, GeometryArrowError,
    build_geometry_arrow, canonical_design_digest, canonical_geometry_rows,
    geometry_arrow_contract, validate_geometry_arrow,
)


def validate_geometry_index(
    index: Any,
    member_digests: Mapping[str, str],
    design_ir: Mapping[str, Any],
    *,
    safe_member_path: Callable[[str], str],
    error_type: Type[ValueError] = ValueError,
) -> Dict[str, Any]:
    if not isinstance(index, Mapping) or index.get("contract") != "spike/geometry-index/v1":
        raise error_type("The geometry index contract is invalid.")
    tables = index.get("tables")
    if not isinstance(tables, list) or len(tables) > 256:
        raise error_type("The geometry index tables must be a bounded array.")
    try:
        design = DesignIRV2.from_dict(design_ir)
    except (TypeError, ValueError) as exc:
        raise error_type(f"The geometry index DesignIR binding is invalid: {exc}") from exc
    expected_design_digest = canonical_design_digest(design)
    normalized: list[Dict[str, Any]] = []
    paths: set[str] = set()
    for raw in tables:
        if not isinstance(raw, Mapping):
            raise error_type("The geometry index contains an invalid table record.")
        path = safe_member_path(str(raw.get("path", "")))
        if not path.startswith("geometry/") or not path.endswith(".arrow"):
            raise error_type("Geometry tables must use package-local geometry/*.arrow paths.")
        if path in paths:
            raise error_type(f"The geometry index repeats table path: {path}")
        paths.add(path)
        if raw.get("encoding") != "arrow-ipc":
            raise error_type(f"Geometry table {path} has an unsupported encoding.")
        digest = str(raw.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or member_digests.get(path) != digest:
            raise error_type(f"Geometry table {path} is missing or has an invalid digest binding.")
        record = {"path": path, "encoding": "arrow-ipc", "sha256": digest}
        schema = str(raw.get("schema", ""))
        if schema:
            if schema not in GEOMETRY_ARROW_CONTRACTS:
                raise error_type(f"Geometry table {path} has an unsupported schema.")
            if schema != geometry_arrow_contract(design):
                raise error_type(f"Geometry table {path} schema does not match its DesignIR path semantics.")
            if str(raw.get("design_id", "")) != design.design_id:
                raise error_type(f"Geometry table {path} is bound to another design identity.")
            if str(raw.get("design_ir_sha256", "")) != expected_design_digest:
                raise error_type(f"Geometry table {path} is bound to another DesignIR digest.")
            rows = raw.get("rows")
            if not isinstance(rows, int) or isinstance(rows, bool) or rows < 0 or rows > 10_000_000:
                raise error_type(f"Geometry table {path} has an invalid row count.")
            record.update({"schema": schema, "rows": rows, "design_id": design.design_id,
                           "design_ir_sha256": expected_design_digest})
        normalized.append(record)
    orphaned = sorted(path for path in member_digests if path.startswith("geometry/") and path.endswith(".arrow") and path not in paths)
    if orphaned:
        raise error_type(f"Package contains unindexed Arrow geometry: {orphaned[0]}")
    return {"contract": "spike/geometry-index/v1", "tables": normalized}


def build_geometry_members(
    design_ir: Mapping[str, Any],
    geometry_tables: Optional[Mapping[str, bytes]],
    *,
    generate: bool,
    safe_member_path: Callable[[str], str],
    sha256: Callable[[bytes], str],
    error_type: Type[ValueError] = ValueError,
) -> tuple[Dict[str, bytes], Dict[str, Any]]:
    generated = False
    if generate:
        if geometry_tables is not None:
            raise error_type("Generated and caller-supplied geometry tables cannot be combined.")
        try:
            typed_design = DesignIRV2.from_dict(design_ir)
            geometry_tables = {GEOMETRY_ARROW_MEMBER_NAME: build_geometry_arrow(typed_design)}
        except (TypeError, ValueError, GeometryArrowError) as exc:
            raise error_type(f"Canonical Arrow geometry generation failed: {exc}") from exc
        generated = True
    members: Dict[str, bytes] = {}
    records: list[Dict[str, Any]] = []
    for name, raw in sorted((geometry_tables or {}).items()):
        safe_name = re.sub(r"[^A-Za-z0-9._+-]", "-", Path(name).name)
        if not safe_name.endswith(".arrow"):
            safe_name += ".arrow"
        path = safe_member_path(f"geometry/{safe_name}")
        data = bytes(raw)
        members[path] = data
        record: Dict[str, Any] = {"path": path, "encoding": "arrow-ipc", "sha256": sha256(data)}
        if generated:
            try:
                validate_geometry_arrow(data, typed_design)
            except GeometryArrowError as exc:
                raise error_type(f"Generated Arrow geometry is invalid: {exc}") from exc
            record.update({"schema": geometry_arrow_contract(typed_design),
                           "rows": len(canonical_geometry_rows(typed_design)),
                           "design_id": typed_design.design_id,
                           "design_ir_sha256": canonical_design_digest(typed_design)})
        records.append(record)
    return members, {"contract": "spike/geometry-index/v1", "tables": records}
