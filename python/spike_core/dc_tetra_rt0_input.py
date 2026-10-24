# SPDX-License-Identifier: Apache-2.0
"""Retained solid geometry and finite exterior-current contact admission."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from python.spike_core.assembly_tetra_thermal_validation import validate_request as validate_geometry

REQUEST = "spike/tetra-dc-rt0-request/v1"
SCALABLE_REQUEST = "spike/tetra-dc-rt0-scalable-request/v1"


def grouped_sums(labels, values, count):
    groups = [[] for _ in range(count)]
    for label, value in zip(labels, values): groups[int(label)].append(float(value))
    return np.asarray([math.fsum(group) for group in groups])


class DCTetraRT0Error(ValueError):
    pass


def require(value, message):
    if not value: raise DCTetraRT0Error(message)


def real(value, low, high):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            "Tetra DC requires explicit finite real inputs within budget")
    return float(value)


def prepare(raw):
    require(type(raw) is dict and set(raw) == {"contract", "mesh", "conductivity_s_m", "contacts"}
            and raw["contract"] in (REQUEST, SCALABLE_REQUEST), "Unsupported tetra DC contract")
    scalable = raw["contract"] == SCALABLE_REQUEST
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= (64 if scalable else 16)*1024*1024, "Tetra DC serialized input exceeds profile budget")
    mesh = raw["mesh"]
    require(type(mesh) is dict and type(mesh.get("cells")) is list and 1 <= len(mesh["cells"]) <= (50000 if scalable else 5000),
            "Tetra DC retained cell profile budget exceeded")
    require(type(mesh.get("vertices")) is list and 4 <= len(mesh["vertices"]) <= (50000 if scalable else 10000),
            "Tetra DC retained vertex profile budget exceeded")
    audit = deepcopy(mesh)
    for c in audit["cells"]: c["material_id"] = "dc-geometry-only"
    geometry = validate_geometry({"contract": "spike/assembly-tetra-thermal-request/v1", "mesh": audit,
        "materials": [{"id": "dc-geometry-only", "thermal_conductivity_w_mk": 1.}], "boundaries": []})
    cells = mesh["cells"]; xyz = geometry["xyz"]
    sigma = raw["conductivity_s_m"]
    require(type(sigma) is dict and set(sigma) == {c["id"] for c in cells}, "Conductivity must cover exactly all physical cells")
    sigma = np.array([real(sigma[c["id"]], 1e-6, 1e12) for c in cells])
    keys, face_map, ids, owners, area = [], {}, [], [], []
    for n, c in enumerate(cells):
        row = []
        for opposite in range(4):
            key = tuple(sorted(v for k, v in enumerate(c["vertices"]) if k != opposite))
            if key not in face_map:
                face_map[key] = len(keys); keys.append(key); owners.append([])
                p = xyz[list(key)]
                area.append(float(np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[0]))/2))
            f = face_map[key]; owners[f].append(n); row.append(f)
        ids.append(row)
    # A source object label never legitimizes an unintended cross-net weld.
    cell_nets = [{mesh["object_map"][s].get("net") for s in c["source_object_ids"]
                 if mesh["object_map"][s].get("net")} for c in cells]
    require(all(len(nets) <= 1 for nets in cell_nets), "One physical cell spans different source nets")
    for attached in owners:
        if len(attached) == 2:
            nets = [cell_nets[n] for n in attached]
            require(not nets[0] or not nets[1] or nets[0] == nets[1], "Shared face joins different source nets")
    ids, area = np.array(ids, dtype=int), np.asarray(area)
    count = len(keys)
    rows = np.repeat(ids, 4, axis=1).ravel(); columns = np.tile(ids, (1, 4)).ravel()
    graph = coo_matrix((np.ones(len(rows)), (rows, columns)), shape=(count, count)).tocsr()
    components, labels = connected_components(graph, directed=False)
    gauges = np.full(components, count, dtype=int)
    np.minimum.at(gauges, labels, np.arange(count))
    contacts = raw["contacts"]
    require(type(contacts) is list and 2 <= len(contacts) <= 4096, "Supply2..4096 explicit finite contacts")
    used, names, patches = set(), set(), []
    prescribed = np.zeros(count)
    for contact in contacts:
        require(type(contact) is dict and set(contact) == {"id", "faces", "current_a"}, "Invalid finite tetra contact")
        name = contact["id"]
        require(type(name) is str and 0 < len(name) <= 128 and not any(ord(c) < 32 for c in name)
                and name not in names, "Invalid or duplicate finite contact identity")
        names.add(name)
        require(type(contact["faces"]) is list and 1 <= len(contact["faces"]) <= count, "Finite contact face budget exceeded")
        selected = []
        for face in contact["faces"]:
            require(type(face) is list and len(face) == 3 and all(type(v) is int for v in face)
                    and len(set(face)) == 3, "Contact needs exact triangular face identities")
            key = tuple(sorted(face)); f = face_map.get(key)
            require(f is not None and len(owners[f]) == 1 and f not in used, "Finite contact is missing, internal, duplicated or overlapping")
            used.add(f); selected.append(f)
        current = real(contact["current_a"], -1e9, 1e9)
        selected = np.array(selected, dtype=int); total = math.fsum(area[selected])
        values = -current*(area[selected]/total)
        require(np.isfinite(values).all() and (current == 0 or np.all(values != 0)), "Tetra contact stamping underflowed")
        prescribed[selected] = values
        patches.append({"id": name, "faces": deepcopy(contact["faces"]), "face_ids": selected,
                        "area_m2": total, "current_a": current})
    scale = math.fsum(abs(p["current_a"]) for p in patches)
    balances = grouped_sums(labels, np.abs(prescribed), components)
    balance = grouped_sums(labels, prescribed, components)
    require(np.all(np.abs(balance) <= 64*np.finfo(float).eps*balances),
            "A disconnected conductor has unbalanced prescribed current")
    volumes = np.array([v for v, _ in geometry["geometry"]])
    return {"xyz": xyz, "cells": cells, "sigma": sigma, "face_keys": keys, "face_ids": ids,
            "face_area": area, "owners": owners, "prescribed": prescribed, "patches": patches,
            "current_scale": scale, "gauges": gauges, "components": components, "labels": labels,
            "component_drives": balances, "volumes": volumes, "scalable": scalable,
            "digest": hashlib.sha256(encoded).hexdigest(), "geometry_audit": geometry}
