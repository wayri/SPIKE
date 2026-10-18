# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Strict admission for the original bounded solid-thermal reference.

No external implementation or fixture was consulted. Topology must be a
conforming positive tetrahedral complex; independently indexed touching solids
remain separate. Positive-volume intersections are rejected by separating axes.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.spatial import cKDTree

from .tetra_aabb_candidates import overlapping_pairs

MAX_CELLS = 100000
MAX_NODES = 100000
MAX_COMPARISONS = 4000000
MAX_HIERARCHY_VISITS = 8000000
MAX_MATRIX_ENTRIES = 4000000
MAX_WORKSPACE_BYTES = 512 * 1024 * 1024


class AssemblyTetraThermalError(ValueError):
    """Invalid, unsupported, or resource-exceeding thermal reference request."""


def require(condition, message):
    if not condition:
        raise AssemblyTetraThermalError(message)


def keys(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value) and
            set(value) <= set(required) | set(optional), "Unexpected or missing object fields.")


def number(value, label, positive=False, nonnegative=False):
    require(type(value) in (int, float), f"{label} must be a finite number.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise AssemblyTetraThermalError(f"{label} is not representable.") from exc
    require(math.isfinite(result) and (not positive or result > 0) and
            (not nonnegative or result >= 0), f"Invalid {label} physical range.")
    return result


def identifier(value):
    require(isinstance(value, str) and 0 < len(value) <= 256 and value.strip(), "Invalid ID.")
    return value


def indices(value, size, count):
    require(isinstance(value, list) and len(value) == size and
            all(type(i) is int and 0 <= i < count for i in value) and
            len(set(value)) == size, "Invalid vertex indices.")
    return tuple(value)


def _overlap_audit(xyz, cells):
    """SAT interior test with bounded spatial hierarchy and comparison budget."""
    points = [xyz[cell["vertices"]] for cell in cells]
    lows, highs = np.array([p.min(0) for p in points]), np.array([p.max(0) for p in points])
    edges = [[p[j] - p[i] for i, j in itertools.combinations(range(4), 2)] for p in points]
    normals = [[np.cross(p[j] - p[i], p[k] - p[i])
                for i, j, k in itertools.combinations(range(4), 3)] for p in points]
    comparisons = 0
    for i, j in overlapping_pairs(lows, highs, MAX_HIERARCHY_VISITS, require):
        comparisons += 1
        require(comparisons <= MAX_COMPARISONS, "Geometry comparison budget exceeded.")
        axes = np.concatenate((normals[i], normals[j],
                               np.cross(np.array(edges[i])[:, None], np.array(edges[j])).reshape(-1, 3)))
        lengths = np.linalg.norm(axes, axis=1)
        axes = axes[lengths > 0] / lengths[lengths > 0, None]
        # Subtract local origin before projection to avoid translation loss.
        a, b = (points[i] - points[i][0]) @ axes.T, (points[j] - points[i][0]) @ axes.T
        overlap = np.minimum(a.max(0), b.max(0)) - np.maximum(a.min(0), b.min(0))
        tolerance = 1e-11 * max(np.max(highs[i] - lows[i]), np.max(highs[j] - lows[j]))
        require(np.any(overlap <= tolerance), "Overlapping tetrahedral solid interiors.")
    return comparisons


def _hanging_node_audit(xyz, cells, geometry, cell_owners, node_owners):
    """Reject same-body nodes on/in a tetrahedron without its node identity."""
    tree = cKDTree(xyz)
    comparisons = 0
    for cell, (_, gradients), owners in zip(cells, geometry, cell_owners):
        vertices = cell["vertices"]
        p = xyz[vertices]
        center = p.mean(0)
        radius = float(np.max(np.linalg.norm(p - center, axis=1))) * (1 + 1e-10)
        count = int(tree.query_ball_point(center, radius, return_length=True))
        comparisons += count
        require(comparisons <= MAX_COMPARISONS, "Hanging-node comparison budget exceeded.")
        candidates = tree.query_ball_point(center, radius)
        candidates = [i for i in candidates if i not in vertices and node_owners[i] & owners]
        if candidates:
            weights = (xyz[candidates] - p[0]) @ gradients[1:].T
            inside = np.all(weights >= -1e-10, axis=1) & (weights.sum(axis=1) <= 1 + 1e-10)
            require(not np.any(inside), "Nonconforming same-body hanging vertex or unrepresented interface.")
    return comparisons


def validate_request(raw):
    if isinstance(raw, dict):
        require(not set(raw) & {"transient", "radiation", "radiation_surfaces", "airflow", "time_step_s", "duration_s"},
                "Transient, radiation, and airflow are unsupported by this steady solid reference.")
    keys(raw, ("contract", "mesh", "materials", "boundaries"),
         ("mode", "heat_sources_w_m3", "contacts"))
    require(raw["contract"] == "spike/assembly-tetra-thermal-request/v1", "Invalid thermal request contract.")
    require(raw.get("mode", "steady_state") == "steady_state",
            "Only steady_state solid conduction is supported; transient/airflow are unsupported.")
    mesh = raw["mesh"]
    keys(mesh, ("contract", "units", "coordinate_system", "vertices", "cells", "counts", "object_map"))
    require(mesh["contract"] == "spike/solver-mesh/v1" and mesh["units"] in ("m", "mm") and
            mesh["coordinate_system"] == "right_handed_xyz", "Invalid mesh identity or SI conversion.")
    vertices, cells = mesh["vertices"], mesh["cells"]
    require(isinstance(vertices, list) and 4 <= len(vertices) <= MAX_NODES and
            isinstance(cells, list) and 1 <= len(cells) <= MAX_CELLS, "Mesh resource budget exceeded.")
    keys(mesh["counts"], ("vertices", "cells"))
    require(all(type(v) is int for v in mesh["counts"].values()) and
            mesh["counts"] == {"vertices": len(vertices), "cells": len(cells)}, "Mesh counts mismatch.")
    for point in vertices:
        require(isinstance(point, list) and len(point) == 3, "Invalid vertex coordinate.")
        for value in point:
            require(abs(number(value, "coordinate")) <= 1e9, "Coordinate magnitude budget exceeded.")
    objects = mesh["object_map"]
    require(isinstance(objects, dict) and len(objects) <= MAX_CELLS, "Invalid object map.")
    for oid, record in objects.items():
        identifier(oid)
        keys(record, ("kind",), ("net", "layer", "occurrence_id", "body_id"))
        for value in record.values():
            identifier(value)
    materials = raw["materials"]
    require(isinstance(materials, list) and 1 <= len(materials) <= MAX_CELLS, "Invalid material budget.")
    tensors = {}
    for material in materials:
        keys(material, ("id", "thermal_conductivity_w_mk"))
        mid = identifier(material["id"])
        require(mid not in tensors, "Duplicate material ID.")
        value = material["thermal_conductivity_w_mk"]
        if isinstance(value, list):
            require(len(value) == 3 and all(isinstance(row, list) and len(row) == 3 for row in value),
                    "Conductivity tensor must be 3 by 3.")
            tensor = np.array([[number(x, "conductivity") for x in row] for row in value])
        else:
            tensor = np.eye(3) * number(value, "conductivity", positive=True)
        require(np.allclose(tensor, tensor.T, rtol=1e-13, atol=0), "Conductivity tensor must be symmetric.")
        eigenvalues = np.linalg.eigvalsh(tensor)
        require(eigenvalues[0] > 0 and eigenvalues[-1] / eigenvalues[0] <= 1e12,
                "Conductivity tensor must be positive definite and reasonably conditioned.")
        tensors[mid] = tensor
    # Bound Python ownership sets/maps as well as numerical buffers before
    # populating them; many source IDs per tetrahedron otherwise amplify RAM.
    ownership_links = 0
    for cell in cells:
        require(isinstance(cell, dict) and isinstance(cell.get("source_object_ids"), list),
                "Invalid source ownership.")
        ownership_links += len(cell["source_object_ids"])
    ownership_bytes = 1024 * ownership_links
    require(ownership_bytes <= MAX_WORKSPACE_BYTES, "Thermal ownership workspace budget exceeded.")
    ids, used, seen, body_coordinates = set(), set(), set(), {}
    cell_owners, node_owners = [], [set() for _ in vertices]
    for cell in cells:
        keys(cell, ("id", "kind", "vertices", "material_id", "source_object_ids"))
        cid = identifier(cell["id"])
        require(cid not in ids, "Duplicate cell ID.")
        ids.add(cid)
        require(cell["kind"] == "tetrahedron" and isinstance(cell["material_id"], str) and
                cell["material_id"] in tensors, "Invalid tetrahedron material.")
        node_ids = indices(cell["vertices"], 4, len(vertices))
        require(tuple(sorted(node_ids)) not in seen, "Duplicate tetrahedron.")
        seen.add(tuple(sorted(node_ids)))
        used.update(node_ids)
        sources = cell["source_object_ids"]
        require(isinstance(sources, list) and 1 <= len(sources) <= 64 and
                all(isinstance(s, str) and s in objects for s in sources) and
                len(set(sources)) == len(sources), "Invalid source ownership.")
        owners = set()
        for source in sources:
            metadata = objects[source]
            owner = metadata.get("occurrence_id", metadata.get("body_id", source))
            owners.add(owner)
            coordinate_nodes = body_coordinates.setdefault(owner, {})
            for node in node_ids:
                position = tuple(vertices[node])
                require(position not in coordinate_nodes or coordinate_nodes[position] == node,
                        "Duplicate-coordinate vertices inside the same retained body.")
                coordinate_nodes[position] = node
                node_owners[node].add(owner)
        cell_owners.append(owners)
    require(len(used) == len(vertices), "Mesh contains unused nodes.")
    sources = raw.get("heat_sources_w_m3", {})
    require(isinstance(sources, dict) and len(sources) <= len(cells) and set(sources) <= ids,
            "Heat sources must map known cell IDs.")
    sources = {cid: number(value, "volumetric heat source") for cid, value in sources.items()}
    boundaries, contacts = raw["boundaries"], raw.get("contacts", [])
    require(isinstance(boundaries, list) and len(boundaries) <= 4 * len(cells) and
            isinstance(contacts, list) and len(contacts) <= 2 * len(cells), "Surface resource budget exceeded.")
    # Conservative admission estimate for topology, geometry, sparse copies,
    # Krylov vectors and output. Caller-owned JSON and runtime RSS are separate.
    entries = 16 * len(cells) + 9 * len(boundaries) + 36 * len(contacts)
    workspace = 3072 * len(cells) + 1024 * len(vertices) + 96 * entries + ownership_bytes
    require(entries <= MAX_MATRIX_ENTRIES, "Sparse matrix entry budget exceeded.")
    require(workspace <= MAX_WORKSPACE_BYTES, "Thermal workspace estimate budget exceeded.")
    xyz = np.array(vertices, dtype=float) * (1e-3 if mesh["units"] == "mm" else 1)
    faces, geometry, max_condition = {}, [], 0.0
    for cell in cells:
        nodes = cell["vertices"]
        p = xyz[nodes]
        jacobian = (p[1:] - p[0]).T
        determinant = float(np.linalg.det(jacobian))
        require(math.isfinite(determinant) and determinant > 1e-30,
                "Inverted, degenerate, or too small tetrahedron.")
        condition = float(np.linalg.cond(jacobian))
        require(condition <= 1e8, "Tetrahedron conditioning budget exceeded.")
        max_condition = max(max_condition, condition)
        gradients = np.vstack((-np.ones(3), np.eye(3))) @ np.linalg.inv(jacobian)
        geometry.append((determinant / 6, gradients))
        for face in itertools.combinations(nodes, 3):
            f = tuple(sorted(face))
            p0, p1, p2 = xyz[list(f)]
            normal = np.cross(p1 - p0, p2 - p0)
            opposite = next(v for v in nodes if v not in f)
            if np.dot(normal, xyz[opposite] - p0) > 0:
                normal = -normal
            norm = np.linalg.norm(normal)
            record = (float(norm / 2), normal / norm)
            owners = faces.setdefault(f, [])
            require(len(owners) < 2 and (not owners or np.dot(owners[0][1], record[1]) < -1 + 1e-10),
                    "Non-manifold or same-side tetrahedron face.")
            owners.append(record)
    exterior = {face: records[0] for face, records in faces.items() if len(records) == 1}
    assigned, surface_ids, fixed, convection, fluxes, matched = set(), set(), {}, [], [], []
    radiation = []

    def surface(item, field):
        face = tuple(sorted(indices(item[field], 3, len(vertices))))
        require(face in exterior and face not in assigned, "Surface must be an unused exterior face.")
        assigned.add(face)
        return face

    for item in boundaries:
        require(isinstance(item, dict) and isinstance(item.get("type"), str), "Invalid boundary.")
        kind = item["type"]
        fields = {"temperature": ("temperature_k",), "heat_flux": ("heat_flux_w_m2",),
                  "convection": ("heat_transfer_coefficient_w_m2k", "ambient_temperature_k"), "adiabatic": (),
                  "radiation": ("emissivity", "radiation_temperature_k"),
                  "convection_radiation": ("heat_transfer_coefficient_w_m2k", "ambient_temperature_k",
                                           "emissivity", "radiation_temperature_k")}
        require(kind in fields, "Unsupported boundary type (airflow unavailable).")
        keys(item, ("id", "vertices", "type") + fields[kind])
        sid = identifier(item["id"])
        require(sid not in surface_ids, "Duplicate surface ID.")
        surface_ids.add(sid)
        face = surface(item, "vertices")
        area = exterior[face][0]
        if kind == "temperature":
            temp = number(item["temperature_k"], "temperature K", nonnegative=True)
            for node in face:
                require(node not in fixed or fixed[node] == temp, "Conflicting nodal temperatures.")
                fixed[node] = temp
        elif kind == "heat_flux":
            fluxes.append((face, area, number(item["heat_flux_w_m2"], "inward heat flux")))
        elif kind in ("convection", "convection_radiation"):
            convection.append((face, area, number(item["heat_transfer_coefficient_w_m2k"], "convection h", positive=True),
                               number(item["ambient_temperature_k"], "ambient temperature K", nonnegative=True)))
        if kind in ("radiation", "convection_radiation"):
            emissivity = number(item["emissivity"], "emissivity", nonnegative=True)
            require(emissivity <= 1, "Emissivity must be in [0, 1].")
            ambient = number(item["radiation_temperature_k"], "radiation temperature K", positive=True)
            require(ambient <= 10000, "Radiation temperature range must be (0, 10000] K.")
            radiation.append((face, area, emissivity, ambient))
    if radiation:
        require(all(0 < t <= 10000 for t in fixed.values()) and
                all(0 < entry[3] <= 10000 for entry in convection),
                "Radiation temperature range must be (0, 10000] K.")
    for item in contacts:
        keys(item, ("id", "left_vertices", "right_vertices", "thermal_contact_conductance_w_m2k"))
        sid = identifier(item["id"])
        require(sid not in surface_ids, "Duplicate surface ID.")
        surface_ids.add(sid)
        left, right = surface(item, "left_vertices"), surface(item, "right_vertices")
        require(not set(left) & set(right), "Contacts must retain separate body vertices.")
        lp, rp = xyz[list(left)], xyz[list(right)]
        tolerance = 1e-10 * max(np.linalg.norm(lp[1] - lp[0]), np.linalg.norm(lp[2] - lp[0]))
        distances = np.linalg.norm(lp[:, None] - rp[None, :], axis=2)
        permutation = distances.argmin(axis=1)
        require(len(set(permutation.tolist())) == 3 and np.max(distances[np.arange(3), permutation]) <= tolerance and
                np.dot(exterior[left][1], exterior[right][1]) < -1 + 1e-10,
                "Contact requires congruent coincident faces with opposite outward normals.")
        matched.append((sid, left, tuple(right[i] for i in permutation), exterior[left][0],
                        number(item["thermal_contact_conductance_w_m2k"], "contact h", positive=True)))
    comparisons = _overlap_audit(xyz, cells)
    hanging_comparisons = _hanging_node_audit(xyz, cells, geometry, cell_owners, node_owners)
    return {"xyz": xyz, "cells": cells, "tensors": tensors, "geometry": geometry,
            "radiation": radiation, "sources": sources, "fixed": fixed, "convection": convection, "fluxes": fluxes,
            "contacts": matched, "exterior": exterior, "omitted": sorted(set(exterior) - assigned),
            "max_condition": max_condition, "comparisons": comparisons,
            "hanging_comparisons": hanging_comparisons, "matrix_entry_budget": entries,
            "estimated_workspace_bytes": workspace}
