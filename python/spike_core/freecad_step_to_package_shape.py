"""FreeCAD-hosted exact STEP package-shape extractor for SPIKE."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

import FreeCAD as App  # type: ignore[import-not-found]
import Import  # type: ignore[import-not-found]
import Part  # type: ignore[import-not-found]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _brep_bytes(shape, max_bytes: int) -> bytes:
    temporary = tempfile.NamedTemporaryFile(prefix="spike-subshape-", suffix=".brep", delete=False)
    path = Path(temporary.name)
    temporary.close()
    try:
        shape.exportBrep(str(path))
        if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > max_bytes:
            raise RuntimeError("FreeCAD exact BREP subshape violates its byte budget.")
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _safe_attr(value, attribute):
    try:
        return getattr(value, attribute, None)
    except (AttributeError, RuntimeError):
        return None


def _kind_name(value, mapping) -> str:
    name = type(value).__name__.lower()
    for token, result in mapping:
        if token in name:
            return result
    return "other"


def _point(value):
    if value is None:
        return None
    try:
        coordinates = [float(value.x), float(value.y), float(value.z)]
    except (AttributeError, TypeError, ValueError):
        return None
    return coordinates if all(math.isfinite(item) for item in coordinates) else None


def _axis_descriptor(geometry):
    direction = _point(_safe_attr(geometry, "Axis"))
    if direction is None:
        direction = _point(_safe_attr(geometry, "Direction"))
    origin = None
    for attribute in ("Center", "Location", "Position"):
        origin = _point(_safe_attr(geometry, attribute))
        if origin is not None:
            break
    if direction is None or origin is None:
        return None
    norm = math.sqrt(sum(value * value for value in direction))
    if not math.isfinite(norm) or norm <= 1e-15:
        return None
    direction = [value / norm for value in direction]
    for value in direction:
        if abs(value) > 1e-14:
            if value < 0:
                direction = [-item for item in direction]
            break
    return {
        "origin_mm": [float(f"{value:.15g}") for value in origin],
        "direction": [float(f"{value:.15g}") for value in direction],
    }


def _geometry_descriptor(kind, support, geometry, subshape, axis):
    descriptor = {
        "contract": "spike/package-shape-selector-geometry/v1",
        "coordinate_space": "shape_local_mm",
        "representation": "unsupported",
        "origin_mm": None,
        "direction": None,
        "radius_mm": None,
    }
    if kind == "vertex":
        point = _point(_safe_attr(subshape, "Point"))
        if point is None:
            raise RuntimeError("FreeCAD exact vertex did not expose a finite point.")
        descriptor.update(representation="point", origin_mm=[float(f"{value:.15g}") for value in point])
    elif kind == "face" and support["surface_kind"] == "plane" and axis is not None:
        descriptor.update(representation="plane", origin_mm=axis["origin_mm"], direction=axis["direction"])
    elif kind == "edge" and support["curve_kind"] in {"line", "circle"} and axis is not None:
        representation = support["curve_kind"]
        descriptor.update(representation=representation, origin_mm=axis["origin_mm"], direction=axis["direction"])
        if representation == "circle":
            try:
                radius = float(_safe_attr(geometry, "Radius"))
            except (TypeError, ValueError):
                radius = float("nan")
            if not math.isfinite(radius) or radius <= 0:
                raise RuntimeError("FreeCAD exact circle did not expose a positive finite radius.")
            descriptor["radius_mm"] = float(f"{radius:.15g}")
    return descriptor


def _placed_shape(obj):
    # FreeCAD's imported Feature.Shape already carries the feature placement.
    # Applying obj.Placement again would double-transform the exact geometry.
    return obj.Shape.copy()


def extract(arguments: list[str]) -> None:
    if len(arguments) != 5:
        raise RuntimeError("Expected input, output, report, max selectors, and max output bytes.")
    source, output, report = map(Path, arguments[:3])
    max_entities, max_output_bytes = map(int, arguments[3:])
    if not source.is_file() or source.suffix.lower() not in {".step", ".stp"}:
        raise RuntimeError("The extractor input must be one local STEP/STP file.")
    if max_entities <= 0 or max_entities > 500_000 or max_output_bytes <= 0 or max_output_bytes > 512 * 1024**2:
        raise RuntimeError("Package-shape extraction limits exceed the reviewed ceiling.")
    source_sha256 = _sha256(source.read_bytes())
    document = App.newDocument("SPIKE_STEP_PACKAGE_SHAPE")
    try:
        Import.insert(str(source), document.Name)
        document.recompute()
        shape_records = []
        raw_entities = []
        axes = {}
        surface_mapping = (("plane", "plane"), ("cylinder", "cylinder"), ("cone", "cone"), ("sphere", "sphere"), ("torus", "torus"), ("bspline", "nurbs"), ("bezier", "nurbs"))
        curve_mapping = (("line", "line"), ("circle", "circle"), ("ellipse", "ellipse"), ("bspline", "bspline"), ("bezier", "bspline"))
        for obj in document.Objects:
            shape = getattr(obj, "Shape", None)
            if shape is None or shape.isNull():
                continue
            placed = _placed_shape(obj)
            shape_records.append((_sha256(_brep_bytes(placed, max_output_bytes)), placed))
        shape_records.sort(key=lambda item: item[0])
        shapes = [item[1] for item in shape_records]
        for placed in shapes:
            collections = (
                ("solid", placed.Solids), ("shell", placed.Shells),
                ("face", placed.Faces), ("edge", placed.Edges), ("vertex", placed.Vertexes),
            )
            for kind, subshapes in collections:
                for subshape in subshapes:
                    fingerprint = _sha256(_brep_bytes(subshape, max_output_bytes))
                    support = {"surface_kind": None, "curve_kind": None, "axis_key": None}
                    geometry = None
                    if kind == "face":
                        geometry = _safe_attr(subshape, "Surface")
                        if geometry is not None:
                            support["surface_kind"] = _kind_name(geometry, surface_mapping)
                    elif kind == "edge":
                        geometry = _safe_attr(subshape, "Curve")
                        if geometry is not None:
                            support["curve_kind"] = _kind_name(geometry, curve_mapping)
                    axis = _axis_descriptor(geometry) if geometry is not None else None
                    if axis is not None:
                        axis_key = _sha256(json.dumps(axis, sort_keys=True, separators=(",", ":")).encode("ascii"))
                        axes[axis_key] = axis
                        support["axis_key"] = axis_key
                    raw_entities.append({
                        "kind": kind, "fingerprint": fingerprint, "support": support,
                        "geometry": _geometry_descriptor(kind, support, geometry, subshape, axis),
                    })
                    if len(raw_entities) + len(axes) > max_entities:
                        raise RuntimeError("STEP package-shape selector inventory exceeds its configured limit.")
        if not shapes:
            raise RuntimeError("STEP import produced no exact solid or shell geometry.")
        compound = Part.makeCompound(shapes)
        if compound.isNull():
            raise RuntimeError("FreeCAD could not form an exact package-shape compound.")
        compound.exportBrep(str(output))
        if not output.is_file() or output.stat().st_size <= 0 or output.stat().st_size > max_output_bytes:
            output.unlink(missing_ok=True)
            raise RuntimeError("Exact package-shape artifact violates its configured byte budget.")
        entities = []
        axis_native_ids = {}
        for axis_key in sorted(axes):
            native_id = f"axis:{axis_key}"
            axis_native_ids[axis_key] = native_id
            entities.append({
                "native_persistent_id": native_id, "kind": "axis", "fingerprint_sha256": axis_key,
                "support": {"surface_kind": None, "curve_kind": None, "axis_native_persistent_id": None},
                "geometry": {
                    "contract": "spike/package-shape-selector-geometry/v1",
                    "coordinate_space": "shape_local_mm", "representation": "axis",
                    "origin_mm": axes[axis_key]["origin_mm"], "direction": axes[axis_key]["direction"],
                    "radius_mm": None,
                },
            })
        occurrences = {}
        for item in sorted(raw_entities, key=lambda value: (value["kind"], value["fingerprint"], json.dumps(value["support"], sort_keys=True))):
            key = (item["kind"], item["fingerprint"])
            rank = occurrences.get(key, 0)
            occurrences[key] = rank + 1
            support = item["support"]
            entities.append({
                "native_persistent_id": f"{item['kind']}:{item['fingerprint']}:{rank}",
                "kind": item["kind"], "fingerprint_sha256": item["fingerprint"],
                "support": {
                    "surface_kind": support["surface_kind"], "curve_kind": support["curve_kind"],
                    "axis_native_persistent_id": axis_native_ids.get(support["axis_key"]),
                },
                "geometry": item["geometry"],
            })
        if not entities or len(entities) > max_entities:
            raise RuntimeError("Exact package-shape selector inventory is empty or exceeds its limit.")
        artifact_sha256 = _sha256(output.read_bytes())
        freecad_version = ".".join(str(value) for value in App.Version()[:3])
        kernel_version = str(getattr(Part, "OCC_VERSION", "")).strip() or str(App.ConfigGet("OCC_VERSION")).strip()
        if not kernel_version:
            raise RuntimeError("FreeCAD did not expose its Open CASCADE kernel version.")
        report.write_text(json.dumps({
            "contract": "spike/freecad-step-package-shape-report/v2",
            "source_sha256": source_sha256, "artifact_sha256": artifact_sha256,
            "kernel_id": "freecad-occ", "kernel_version": kernel_version,
            "freecad_version": freecad_version, "shape_count": len(shapes),
            "entity_count": len(entities), "entities": entities,
            "topology_ready": True, "solver_ready": False,
        }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    finally:
        App.closeDocument(document.Name)


if __name__ == "__main__":
    extract(sys.argv[1:])
