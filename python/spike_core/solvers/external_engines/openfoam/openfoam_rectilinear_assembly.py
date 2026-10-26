# SPDX-License-Identifier: Apache-2.0
"""Deterministic conforming hexahedral CHT assembly for declared cuboids.

This is a geometry-preparation adapter, not a new flow or heat equation.  It
partitions one axis-aligned domain into air and non-overlapping cuboid solids,
then delegates polyMesh writing and CHT dictionaries to the existing adapters.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .openfoam_multiregion import REQUEST_CONTRACT, prepare_runnable_multiregion_case
from .openfoam_polymesh import REQUEST_CONTRACT as POLYMESH_REQUEST_CONTRACT, write_polymesh


MAX_CELLS = 100_000


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _evidence(identity: str, contract: str, value: Any) -> dict[str, Any]:
    # ``qualified`` is the existing SPIKE evidence-record admission bit.  It
    # qualifies this digest/contract binding only, never physical validation.
    return {"id": identity, "contract": contract, "sha256": _digest(value), "qualified": True}


def _bounds(value: Any, label: str) -> tuple[list[float], list[float]]:
    if not isinstance(value, list) or len(value) != 2 or any(not isinstance(row, list) or len(row) != 3 for row in value):
        raise ValueError(label + " must contain lower/upper XYZ triples")
    low, high = [[float(item) for item in row] for row in value]
    if any(not math.isfinite(item) or abs(item) > 1e6 for item in [*low, *high]) or any(high[i] <= low[i] for i in range(3)):
        raise ValueError(label + " must be finite, bounded and increasing")
    return low, high


def _axes(domain: tuple[list[float], list[float]], solids: list[dict[str, Any]], maximum: float) -> list[list[float]]:
    plans: list[tuple[list[float], list[int]]] = []
    for axis in range(3):
        anchors = {domain[0][axis], domain[1][axis]}
        for solid in solids:
            low, high = solid["bounds_mm"][0][axis], solid["bounds_mm"][1][axis]
            anchors.update((low, high))
        # OpenFOAM's all-geometry determinant check needs a truly 3-D
        # neighbourhood in each standalone region. Retain at least one
        # interior plane per cuboid direction, but reuse an existing plane
        # from another aligned source to avoid nearly coincident slivers.
        for solid in solids:
            low, high = solid["bounds_mm"][0][axis], solid["bounds_mm"][1][axis]
            if not any(low < value < high for value in anchors):
                anchors.add((low + high) / 2)
        ordered = sorted(anchors)
        divisions = [max(1, math.ceil((right-left)/maximum)) for left, right in zip(ordered, ordered[1:])]
        if sum(divisions) > MAX_CELLS:
            raise ValueError("Rectilinear assembly exceeds 100000 cells")
        plans.append((ordered, divisions))
    if math.prod(sum(divisions) for _, divisions in plans) > MAX_CELLS:
        raise ValueError("Rectilinear assembly exceeds 100000 cells")
    axes = []
    for ordered, interval_divisions in plans:
        values = [ordered[0]]
        for (left, right), divisions in zip(zip(ordered, ordered[1:]), interval_divisions):
            values.extend(left + (right-left)*index/divisions for index in range(1, divisions+1))
        axes.append(values)
    return axes


def _inside(point: tuple[float, float, float], bounds: list[list[float]]) -> bool:
    return all(bounds[0][axis] < point[axis] < bounds[1][axis] for axis in range(3))


def _validate(config: Mapping[str, Any]) -> tuple[tuple[list[float], list[float]], list[dict[str, Any]]]:
    required = {"domain_bounds_mm", "solids", "materials", "ambient_temperature_k", "flow_rate_m3_s", "maximum_cell_size_mm", "numerics", "source_evidence"}
    if not isinstance(config, Mapping) or set(config) != required:
        raise ValueError("Rectilinear assembly requires exact configuration fields")
    domain = _bounds(config["domain_bounds_mm"], "domain_bounds_mm")
    maximum = config["maximum_cell_size_mm"]
    if type(maximum) not in (int, float) or not math.isfinite(maximum) or not 0 < maximum <= 1000:
        raise ValueError("maximum_cell_size_mm must be positive and bounded")
    raw_solids = config["solids"]
    if not isinstance(raw_solids, list) or not 1 <= len(raw_solids) <= 32:
        raise ValueError("One to 32 declared cuboid solids are required")
    source = config["source_evidence"]
    if (not isinstance(source, Mapping) or not isinstance(source.get("id"), str) or not source["id"]
            or not isinstance(source.get("sha256"), str) or len(source["sha256"]) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in source["sha256"])):
        raise ValueError("source_evidence requires a nonempty id and SHA-256 digest")
    for label in ("ambient_temperature_k", "flow_rate_m3_s"):
        value = config[label]
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(label + " must be finite and positive")
    numerics = config["numerics"]
    allowed_numerics = {"end_time_s", "delta_t_s", "write_interval_steps", "validation_interval_steps", "outer_correctors"}
    if not isinstance(numerics, Mapping) or set(numerics) - allowed_numerics:
        raise ValueError("numerics must be an object")
    for label in ("end_time_s", "delta_t_s"):
        value = numerics.get(label)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError("numerics." + label + " must be finite and positive")
    if numerics["delta_t_s"] > numerics["end_time_s"] or numerics["end_time_s"] / numerics["delta_t_s"] > 10_000_000:
        raise ValueError("numerics time-step request is outside its bound")
    for label, upper in (("write_interval_steps", 1_000_000), ("validation_interval_steps", 1_000_000), ("outer_correctors", 50)):
        if label in numerics and (type(numerics[label]) is not int or not 1 <= numerics[label] <= upper):
            raise ValueError("numerics." + label + " must be a bounded positive integer")
    solids: list[dict[str, Any]] = []
    names = set()
    for raw in raw_solids:
        if not isinstance(raw, dict) or set(raw) != {"id", "role", "material_id", "bounds_mm", "power_w", "geometry_provenance"}:
            raise ValueError("Every cuboid requires identity, role, material, bounds, power and provenance")
        if not isinstance(raw["role"], str) or not raw["role"] or not isinstance(raw["material_id"], str) or not raw["material_id"]:
            raise ValueError("Cuboid role and material_id must be nonempty strings")
        if not isinstance(raw["id"], str) or not raw["id"].replace("_", "a").isalnum() or not raw["id"][0].isalpha() or raw["id"] in names or raw["id"] == "air":
            raise ValueError("Cuboid region IDs must be unique OpenFOAM-safe identifiers")
        names.add(raw["id"])
        low, high = _bounds(raw["bounds_mm"], raw["id"] + ".bounds_mm")
        if any(low[a] < domain[0][a] or high[a] > domain[1][a] for a in range(3)):
            raise ValueError("Every cuboid must be contained by the air domain")
        if type(raw["power_w"]) not in (int, float) or not math.isfinite(raw["power_w"]) or raw["power_w"] < 0:
            raise ValueError("Cuboid power must be finite and nonnegative")
        provenance = raw["geometry_provenance"]
        if not isinstance(provenance, dict) or provenance.get("kind") != "declared_axis_aligned_cuboid" or provenance.get("exact") is not False or not isinstance(provenance.get("source"), str) or not provenance["source"]:
            raise ValueError("Cuboid geometry must explicitly declare inexact source provenance")
        admitted = dict(raw)
        admitted["bounds_mm"] = [low, high]
        admitted["geometry_provenance"] = dict(provenance)
        solids.append(admitted)
    for index, left in enumerate(solids):
        for right in solids[index+1:]:
            overlap = [min(left["bounds_mm"][1][a], right["bounds_mm"][1][a]) - max(left["bounds_mm"][0][a], right["bounds_mm"][0][a]) for a in range(3)]
            if all(value > 1e-9 for value in overlap):
                raise ValueError("Declared cuboid interiors overlap")
    materials = config["materials"]
    if not isinstance(materials, list) or not materials or any(not isinstance(item, Mapping) for item in materials):
        raise ValueError("materials must be a nonempty list of records")
    material_ids = [item.get("id") for item in materials]
    if any(not isinstance(item, str) or not item for item in material_ids) or len(set(material_ids)) != len(material_ids):
        raise ValueError("material ids must be nonempty and unique")
    if "air" not in material_ids or any(solid["material_id"] not in material_ids for solid in solids):
        raise ValueError("Materials must cover air and every cuboid")
    return domain, solids


def build_rectilinear_assembly_case(config: Mapping[str, Any], output_root: str | Path) -> dict[str, Any]:
    domain, solids = _validate(config)
    axes = _axes(domain, solids, float(config["maximum_cell_size_mm"]))
    root = Path(output_root).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Rectilinear assembly output root must be empty")
    root.mkdir(parents=True, exist_ok=True)
    nx, ny, nz = (len(axis)-1 for axis in axes)
    if nx*ny*nz > MAX_CELLS:
        raise ValueError("Rectilinear assembly exceeds 100000 cells")
    regions: dict[tuple[int, int, int], str] = {}
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                center = tuple((axes[a][index] + axes[a][index+1])/2 for a, index in enumerate((i, j, k)))
                owners = [solid["id"] for solid in solids if _inside(center, solid["bounds_mm"])]
                if len(owners) > 1:
                    raise ValueError("A rectilinear cell has ambiguous solid ownership")
                regions[(i, j, k)] = owners[0] if owners else "air"
    solid_map = {solid["id"]: solid for solid in solids}
    all_regions = ["air", *[solid["id"] for solid in solids]]
    if any(region not in regions.values() for region in all_regions):
        raise ValueError("Every requested region needs at least one hexahedral cell")
    corner_offsets = ((0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1))
    face_templates = {
        (-1,0,0): (0,4,7,3), (1,0,0): (1,2,6,5),
        (0,-1,0): (0,1,5,4), (0,1,0): (3,7,6,2),
        (0,0,-1): (0,3,2,1), (0,0,1): (4,5,6,7),
    }
    mesh_root = root / "meshes"
    written, region_records, interfaces = {}, [], {}
    for region in all_regions:
        owned = [cell for cell, owner in regions.items() if owner == region]
        vertices, point_index, cells, patches = [], {}, [], {}
        def point_id(key):
            if key not in point_index:
                point_index[key] = len(vertices)
                vertices.append([axes[0][key[0]], axes[1][key[1]], axes[2][key[2]]])
            return point_index[key]
        for i, j, k in owned:
            keys = [(i+di, j+dj, k+dk) for di,dj,dk in corner_offsets]
            ids = [point_id(key) for key in keys]
            cells.append({"id": f"{region}_{i}_{j}_{k}", "kind": "hexahedron", "vertices": ids,
                          "source_object_ids": ["region:"+region], "material_id": "air" if region == "air" else solid_map[region]["material_id"]})
            for direction, template in face_templates.items():
                neighbour = (i+direction[0], j+direction[1], k+direction[2])
                other = regions.get(neighbour)
                if other == region:
                    continue
                if other is None:
                    if region != "air":
                        raise ValueError("A solid touches the exterior domain")
                    name = "inlet" if direction == (-1,0,0) else "outlet" if direction == (1,0,0) else "air_external"
                    kind = "patch" if name in ("inlet", "outlet") else "wall"
                    patch = patches.setdefault(name, {"name": name, "type": kind, "faces": []})
                else:
                    iid = "_".join(sorted((region, other)))
                    name = region + "_to_" + other
                    patch = patches.setdefault(name, {"name": name, "type": "mappedWall", "neighbour_region": other,
                        "neighbour_patch": other+"_to_"+region, "interface_id": iid, "faces": []})
                    interfaces[iid] = tuple(sorted((region, other)))
                patch["faces"].append([ids[index] for index in template])
        mesh = {"contract": "spike/solver-mesh/v1", "units": "mm", "coordinate_system": "right_handed_xyz",
                "vertices": vertices, "cells": cells, "object_map": {"region:"+region: {"kind": "thermal_region"}},
                "counts": {"vertices": len(vertices), "cells": len(cells)}}
        request = {"contract": POLYMESH_REQUEST_CONTRACT, "region_id": region, "mesh": mesh,
                   "mesh_evidence": _evidence("rectilinear:"+region, "spike/solver-mesh/v1", mesh),
                   "boundary_patches": list(patches.values())}
        if region != "air" and solid_map[region]["power_w"] > 0:
            request["cell_zones"] = [{"name": "source", "cell_ids": [cell["id"] for cell in cells]}]
        written[region] = write_polymesh(request, mesh_root / region / "polyMesh")
        ownership = {}
        for name, patch in patches.items():
            ownership[name] = ("fan:prescribed" if name == "inlet" else "external:pressure_outlet" if name == "outlet"
                               else "external:fixed_temperature" if name == "air_external" else "interface:"+patch["interface_id"])
        solid = solid_map.get(region)
        region_records.append({"id": region, "kind": "fluid" if region == "air" else "solid",
            "role": "air" if region == "air" else solid["role"], "material_id": "air" if region == "air" else solid["material_id"],
            "mesh_evidence": written[region]["poly_mesh_evidence"], "boundary_ownership": ownership})
    interface_records = []
    for iid, (left, right) in sorted(interfaces.items()):
        interface_records.append({"id": iid, "region_a": left, "region_b": right, "patch_a": left+"_to_"+right,
            "patch_b": right+"_to_"+left, "kind": "conjugate", "evidence": _evidence("interface:"+iid, "spike/qualified-contact/v1", [left, right, axes])})
    sources = []
    for solid in solids:
        if solid["power_w"] <= 0:
            continue
        volume_m3 = math.prod(solid["bounds_mm"][1][axis]-solid["bounds_mm"][0][axis] for axis in range(3))*1e-9
        sources.append({"id": solid["id"]+"_power", "solid_region_id": solid["id"], "power_w": solid["power_w"],
            "evidence": _evidence("power:"+solid["id"], "spike/component-power-table/v1", [solid["id"], solid["power_w"]]),
            "fv_option": {"cell_zone": "source", "volumetric_power_w_m3": solid["power_w"]/volume_m3}})
    materials = list(config["materials"])
    material_ids = {item.get("id") for item in materials if isinstance(item, dict)}
    if "air" not in material_ids or any(solid["material_id"] not in material_ids for solid in solids):
        raise ValueError("Materials must cover air and every cuboid")
    mesh_set = {region: written[region]["poly_mesh_digest"] for region in all_regions}
    translated = {"contract": REQUEST_CONTRACT, "job_id": "rectilinear_assembly",
        "mesh_evidence": _evidence("rectilinear-assembly", "spike/openfoam-multiregion-mesh-set/v1", mesh_set),
        "materials": materials, "regions": region_records, "interfaces": interface_records, "heat_sources": sources,
        "environment": {"enclosure": "open", "radiation": False, "vacuum": False, "medium": "air",
                        "ambient_temperature_k": config["ambient_temperature_k"], "gravity_m_s2": [0,0,0], "dpdt_enabled": False,
                        "pressure_outlets": [{"fluid_region_id": "air", "boundary_patch": "outlet", "static_pressure_pa": 101325,
                                              "backflow_temperature_k": config["ambient_temperature_k"]}]},
        "fans": [{"id": "prescribed", "fluid_region_id": "air", "flow_rate_m3_s": config["flow_rate_m3_s"],
                  "boundary_patch": "inlet", "boundary_evidence": written["air"]["poly_mesh_evidence"]}],
        "heatsinks": [], "numerics": dict(config["numerics"])}
    (root / "geometry-provenance.json").write_text(json.dumps({"source_evidence": config["source_evidence"], "solids": solids,
        "domain_bounds_mm": config["domain_bounds_mm"], "axes_mm": axes}, indent=2), encoding="utf-8")
    (root / "translated-request.json").write_text(json.dumps(translated, indent=2), encoding="utf-8")
    prepared = prepare_runnable_multiregion_case(translated, root / "case", mesh_root)
    return {"contract": "spike/openfoam-rectilinear-assembly/v1", "status": prepared["status"], "axes_mm": axes,
            "cell_counts": {region: sum(owner == region for owner in regions.values()) for region in all_regions},
            "request": translated, "prepared": prepared, "geometry_provenance": {solid["id"]: solid["geometry_provenance"] for solid in solids}}


def run_rectilinear_assembly(config: Mapping[str, Any], output_root: str | Path, *, allow_experimental: bool,
                             timeout_s: int = 600, memory_limit_mb: int = 4096,
                             runtime: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build and run the explicit cuboid-proxy route with native flow tracks."""
    if allow_experimental is not True:
        return {"status": "blocked", "fields": {}, "message": "Rectilinear assembly CHT requires allow_experimental=true.",
                "geometry_mode": "declared_axis_aligned_cuboids", "production_qualified": False}
    built = build_rectilinear_assembly_case(config, output_root)
    from .openfoam_multiregion_execution import run_multiregion_case
    from .openfoam_streamline_export import export_forced_airflow_field_volume
    case = Path(output_root).resolve() / "case"
    result = run_multiregion_case(case, timeout_s=timeout_s, memory_limit_mb=memory_limit_mb, runtime=runtime)
    result.update({"geometry_mode": "declared_axis_aligned_cuboids", "geometry_exact": False,
                   "geometry_provenance": built["geometry_provenance"], "cell_counts": built["cell_counts"],
                   "production_qualified": False})
    if result.get("status") == "completed":
        x_axis, y_axis, z_axis = built["axes_mm"]
        z = z_axis[0] + .30 * (z_axis[-1] - z_axis[0])
        x = x_axis[0] + .02 * (x_axis[-1] - x_axis[0])
        margin = .05 * (y_axis[-1] - y_axis[0])
        try:
            result["flow_field_volume"] = export_forced_airflow_field_volume(case, result,
                seed_line_mm=[[x, y_axis[0] + margin, z], [x, y_axis[-1] - margin, z]], runtime=runtime)
            result["flow_field_volume"]["geometryNote"] += (
                " Solid obstacles are explicitly declared axis-aligned cuboid proxies with source provenance;"
                " they are not exact retained CAD bodies.")
        except (OSError, ValueError, RuntimeError) as exc:
            result["flow_field_volume_error"] = str(exc)
    (Path(output_root).resolve() / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


__all__ = ["build_rectilinear_assembly_case", "run_rectilinear_assembly"]
