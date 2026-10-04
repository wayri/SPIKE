# SPDX-License-Identifier: Apache-2.0
"""Bounded, design-neutral table and plot data published by Python scripts."""

from __future__ import annotations

import math
import uuid
from typing import Any


CONTRACT = "spike/data-view/v1"
MAX_VIEWS = 12
MAX_CELLS = 100_000
MAX_COLUMNS = 32
MAX_SERIES = 12
MAX_SAMPLES = 20_000
MAX_SPATIAL_SAMPLES = 10_000
MAX_MESH_VERTICES = 10_000
MAX_MESH_TRIANGLES = 10_000
MAX_STRING_BYTES = 1_000_000
MAX_LABEL_CHARS = 2_000
PLOT_KINDS = frozenset(("line", "scatter", "polar"))


def _label(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > MAX_LABEL_CHARS or (not allow_empty and not value.strip()):
        raise ValueError(f"{field} must be a nonempty string of at most {MAX_LABEL_CHARS} characters.")
    return value


def _number(value: Any, field: str, *, nullable: bool = False) -> int | float | None:
    if nullable and value is None:
        return None
    try:
        finite = math.isfinite(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else False
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{field} must be a finite number{', or null' if nullable else ''}.")
    return value


def _list(value: Any, field: str, maximum: int, *, allow_empty: bool = False) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum or (not allow_empty and not value):
        raise ValueError(f"{field} must be a list containing {1 if not allow_empty else 0} to {maximum} items.")
    return value


def _keys(value: dict[str, Any], required: set[str], field: str) -> None:
    if set(value) != required:
        raise ValueError(f"{field} has missing or unsupported fields.")


def _string_size(text: str) -> int:
    return len(text.encode("utf-8"))


def admit_views(value: Any) -> list[dict[str, Any]]:
    """Validate and copy the complete child payload at publication and host ingress."""
    views = _list(value, "views", MAX_VIEWS, allow_empty=True)
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    total_cells = total_string_bytes = 0
    for index, raw in enumerate(views):
        if not isinstance(raw, dict):
            raise ValueError(f"view {index} must be an object.")
        kind = raw.get("kind")
        shared = {"contract", "id", "kind", "title", "provenance"}
        table_fields = {"columns", "rows", "units"}
        plot_fields = {"x", "series", "x_label", "y_label", "x_unit", "y_unit"}
        spatial_fields = {"samples", "quantity", "coordinate_unit", "value_unit"}
        mesh_fields = {"vertices", "triangles", "coordinate_unit"}
        if kind == "table":
            _keys(raw, shared | table_fields, f"view {index}")
        elif kind in PLOT_KINDS:
            _keys(raw, shared | plot_fields, f"view {index}")
        elif kind == "spatial":
            _keys(raw, shared | spatial_fields, f"view {index}")
        elif kind == "mesh":
            _keys(raw, shared | mesh_fields, f"view {index}")
        else:
            raise ValueError(f"view {index} has an unsupported kind.")
        if raw["contract"] != CONTRACT:
            raise ValueError(f"view {index} has an unsupported contract.")
        identifier = raw["id"]
        try:
            parsed_id = uuid.UUID(identifier) if isinstance(identifier, str) else None
        except (ValueError, AttributeError):
            parsed_id = None
        if parsed_id is None or str(parsed_id) != identifier or identifier in ids:
            raise ValueError(f"view {index} needs a unique UUID.")
        ids.add(identifier)
        title = _label(raw["title"], "title")
        provenance = _label(raw["provenance"], "provenance")
        total_string_bytes += _string_size(identifier) + _string_size(title) + _string_size(provenance)
        base = {"contract": CONTRACT, "id": identifier, "kind": kind, "title": title, "provenance": provenance}
        if kind == "table":
            columns = [_label(item, "column") for item in _list(raw["columns"], "columns", MAX_COLUMNS)]
            units = [_label(item, "unit", allow_empty=True) for item in _list(raw["units"], "units", MAX_COLUMNS, allow_empty=True)]
            if units and len(units) != len(columns):
                raise ValueError("Table units must match the column count.")
            rows = _list(raw["rows"], "rows", MAX_CELLS, allow_empty=True)
            total_cells += len(rows) * len(columns)
            if total_cells > MAX_CELLS:
                raise ValueError("Published views exceed the 100,000-cell limit.")
            clean_rows = []
            for row in rows:
                if not isinstance(row, list) or len(row) != len(columns):
                    raise ValueError("Table rows must be rectangular.")
                clean_row = []
                for cell in row:
                    if isinstance(cell, str):
                        total_string_bytes += _string_size(cell)
                    elif cell is not None and not isinstance(cell, bool):
                        _number(cell, "table cell")
                    elif not (cell is None or isinstance(cell, bool)):
                        raise ValueError("Table cells must be JSON scalars.")
                    clean_row.append(cell)
                clean_rows.append(clean_row)
            total_string_bytes += sum(map(_string_size, columns)) + sum(map(_string_size, units))
            normalized.append({**base, "columns": columns, "units": units, "rows": clean_rows})
        elif kind == "spatial":
            samples = _list(raw["samples"], "samples", MAX_SPATIAL_SAMPLES)
            total_cells += len(samples) * 9
            if total_cells > MAX_CELLS:
                raise ValueError("Published views exceed the 100,000-cell limit.")
            clean_samples = []
            scalar_keys = {"x", "y", "z", "value_real", "value_imag"}
            vector_keys = {"x", "y", "z", "vector_real", "vector_imag"}
            for sample in samples:
                if not isinstance(sample, dict) or set(sample) not in (scalar_keys, vector_keys):
                    raise ValueError("Spatial samples must contain coordinates and one scalar or vector value.")
                clean = {axis: _number(sample[axis], f"sample {axis}") for axis in ("x", "y", "z")}
                if set(sample) == scalar_keys:
                    clean.update(value_real=_number(sample["value_real"], "value_real"),
                                 value_imag=_number(sample["value_imag"], "value_imag"))
                else:
                    for key in ("vector_real", "vector_imag"):
                        vector = _list(sample[key], key, 3)
                        if len(vector) != 3:
                            raise ValueError(f"{key} must contain exactly three components.")
                        clean[key] = [_number(component, key) for component in vector]
                clean_samples.append(clean)
            labels = {key: _label(raw[key], key, allow_empty=key.endswith("_unit"))
                      for key in ("quantity", "coordinate_unit", "value_unit")}
            total_string_bytes += sum(map(_string_size, labels.values()))
            normalized.append({**base, "samples": clean_samples, **labels})
        elif kind == "mesh":
            vertices = _list(raw["vertices"], "vertices", MAX_MESH_VERTICES)
            triangles = _list(raw["triangles"], "triangles", MAX_MESH_TRIANGLES)
            clean_vertices = []
            for vertex in vertices:
                if not isinstance(vertex, list) or len(vertex) != 3:
                    raise ValueError("Mesh vertices must contain exactly three coordinates.")
                clean_vertices.append([_number(item, "vertex coordinate") for item in vertex])
            clean_triangles = []
            for triangle in triangles:
                if (not isinstance(triangle, list) or len(triangle) != 3 or
                        any(isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= len(vertices) for item in triangle) or
                        len(set(triangle)) != 3):
                    raise ValueError("Mesh triangles must contain three distinct in-bounds integer vertex indices.")
                clean_triangles.append(list(triangle))
            total_cells += len(vertices) * 3 + len(triangles) * 3
            coordinate_unit = _label(raw["coordinate_unit"], "coordinate_unit", allow_empty=True)
            total_string_bytes += _string_size(coordinate_unit)
            normalized.append({**base, "vertices": clean_vertices, "triangles": clean_triangles,
                               "coordinate_unit": coordinate_unit})
        else:
            x = [_number(item, "x sample") for item in _list(raw["x"], "x", MAX_SAMPLES)]
            series = _list(raw["series"], "series", MAX_SERIES)
            total_cells += len(x) * (1 + len(series))
            if total_cells > MAX_CELLS:
                raise ValueError("Published views exceed the 100,000-cell limit.")
            clean_series = []
            for item in series:
                if not isinstance(item, dict):
                    raise ValueError("Each series must be an object.")
                _keys(item, {"name", "values"}, "series")
                name = _label(item["name"], "series name")
                values = _list(item["values"], "series values", MAX_SAMPLES)
                if len(values) != len(x):
                    raise ValueError("Series length must match x.")
                clean = [_number(sample, "series sample", nullable=True) for sample in values]
                if kind == "polar" and any(sample is not None and sample < 0 for sample in clean):
                    raise ValueError("Polar radius must be nonnegative.")
                total_string_bytes += _string_size(name)
                clean_series.append({"name": name, "values": clean})
            labels = {key: _label(raw[key], key, allow_empty=key.endswith("_unit"))
                      for key in ("x_label", "y_label", "x_unit", "y_unit")}
            if kind == "polar":
                if labels["x_unit"] not in ("", "deg"):
                    raise ValueError("Polar x_unit must be degrees.")
                labels["x_unit"] = "deg"
            total_string_bytes += sum(map(_string_size, labels.values()))
            normalized.append({**base, "x": x, "series": clean_series, **labels})
        if total_string_bytes > MAX_STRING_BYTES:
            raise ValueError("Published views exceed the 1 MB string-data limit.")
    return normalized


class ScriptViews:
    """Per-script collector; every append validates the aggregate bounds."""

    def __init__(self) -> None:
        self._views: list[dict[str, Any]] = []

    @property
    def views(self) -> list[dict[str, Any]]:
        return admit_views(self._views)

    def publish_table(self, title: str, columns: list[str], rows: list[list[Any]], *,
                      units: list[str] | None = None, provenance: str = "user script") -> None:
        candidate = {"contract": CONTRACT, "id": str(uuid.uuid4()), "kind": "table",
                     "title": title, "provenance": provenance, "columns": columns,
                     "rows": rows, "units": units if units is not None else []}
        self._views = admit_views([*self._views, candidate])

    def publish_plot(self, title: str, x: list[int | float],
                     series: list[dict[str, Any]], *, x_label: str = "x",
                     y_label: str = "y", x_unit: str = "", y_unit: str = "",
                     kind: str = "line", provenance: str = "user script") -> None:
        candidate = {"contract": CONTRACT, "id": str(uuid.uuid4()), "kind": kind,
                     "title": title, "provenance": provenance, "x": x, "series": series,
                     "x_label": x_label, "y_label": y_label, "x_unit": x_unit,
                     "y_unit": y_unit}
        self._views = admit_views([*self._views, candidate])

    def publish_spatial(self, title: str, samples: list[dict[str, Any]], *,
                        quantity: str, unit: str = "", coordinate_unit: str = "m",
                        provenance: str = "user script") -> None:
        """Publish bounded design-neutral scalar or vector samples for linked 3D review."""
        normalized = []
        for sample in samples:
            if not isinstance(sample, dict):
                raise TypeError("Spatial samples must be dictionaries.")
            point = {axis: sample.get(axis) for axis in ("x", "y", "z")}
            if all(key in sample for key in ("vx", "vy", "vz")):
                point.update(vector_real=[sample["vx"], sample["vy"], sample["vz"]],
                             vector_imag=[sample.get("vx_imag", 0), sample.get("vy_imag", 0), sample.get("vz_imag", 0)])
            elif "vector" in sample:
                vector = sample["vector"]
                if not isinstance(vector, (list, tuple)) or len(vector) != 3:
                    raise ValueError("Spatial vector must contain exactly three components.")
                point.update(vector_real=[float(complex(item).real) for item in vector],
                             vector_imag=[float(complex(item).imag) for item in vector])
            elif "real" in sample:
                point.update(value_real=sample["real"], value_imag=sample.get("imag", 0))
            elif "value" in sample:
                value = complex(sample["value"])
                point.update(value_real=float(value.real), value_imag=float(value.imag))
            else:
                raise ValueError("Spatial sample needs value or vector.")
            normalized.append(point)
        candidate = {"contract": CONTRACT, "id": str(uuid.uuid4()), "kind": "spatial",
                     "title": title, "provenance": provenance, "samples": normalized,
                     "quantity": quantity, "coordinate_unit": coordinate_unit,
                     "value_unit": unit}
        self._views = admit_views([*self._views, candidate])

    def publish_mesh(self, title: str, vertices: list[list[Any]], triangles: list[list[Any]], *,
                     coordinate_unit: str = "m", provenance: str = "user script") -> None:
        """Publish a bounded corner-node triangle preview, not a CAD surface model."""
        candidate = {"contract": CONTRACT, "id": str(uuid.uuid4()), "kind": "mesh",
                     "title": title, "provenance": provenance, "vertices": vertices,
                     "triangles": triangles, "coordinate_unit": coordinate_unit}
        self._views = admit_views([*self._views, candidate])
