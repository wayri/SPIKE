# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Admission for the original bounded scalar DC retained-solid reference.

Geometry admission reuses the existing nonmutating tetrahedral thermal audit
with a private unit-conductivity request. That request does not run a thermal
solve, infer electrical materials, or change the supplied mesh.
"""
from __future__ import annotations

import itertools

from .assembly_tetra_thermal_validation import (
    AssemblyTetraThermalError, identifier, indices, keys, number, require,
    validate_request as validate_geometry,
)


class AssemblyTetraElectricalError(ValueError):
    """Invalid, unsupported, or resource-exceeding electrical request."""


REQUEST_CONTRACT = "spike/assembly-tetra-electrical-request/v1"


def validate_request(raw):
    """Return SI geometry, complete scalar conductivities and explicit anchors."""
    try:
        return _validate(raw)
    except AssemblyTetraThermalError as exc:
        raise AssemblyTetraElectricalError(str(exc)) from exc


def _validate(raw):
    keys(raw, ("contract", "mesh", "conductivity_s_m", "terminals"), ("contacts",))
    require(raw["contract"] == REQUEST_CONTRACT, "Invalid electrical request contract.")
    mesh = raw["mesh"]
    require(isinstance(mesh, dict) and isinstance(mesh.get("cells"), list) and
            isinstance(mesh.get("object_map"), dict), "Invalid electrical mesh.")
    cells, objects = mesh["cells"], mesh["object_map"]
    require(1 <= len(cells) <= 5000 and len(objects) <= 5000, "Mesh resource budget exceeded.")
    require(isinstance(mesh.get("vertices"), list) and 4 <= len(mesh["vertices"]) <= 10000,
            "Mesh resource budget exceeded.")
    # Preserve both levels of identity. Thermal's single owner key is replaced
    # only in this private audit copy, never in the retained source mesh.
    audit_objects, owners = {}, {}
    for source, record in objects.items():
        identifier(source)
        keys(record, ("kind",), ("net", "layer", "occurrence_id", "body_id"))
        for value in record.values():
            identifier(value)
        identity = (record.get("occurrence_id"), record.get("body_id"))
        if identity == (None, None):
            identity = (None, source)
        owner = owners.setdefault(identity, f"electrical-body-{len(owners)}")
        audit_objects[source] = {**record, "occurrence_id": owner}
    audit_cells, cell_owners, node_owners = [], {}, {}
    for cell in cells:
        keys(cell, ("id", "kind", "vertices", "material_id", "source_object_ids"))
        identifier(cell["id"])
        identifier(cell["material_id"])
        require(isinstance(cell["source_object_ids"], list) and
                1 <= len(cell["source_object_ids"]) <= 64 and
                all(isinstance(s, str) and s in audit_objects for s in cell["source_object_ids"]),
                "Invalid source ownership.")
        identities = {audit_objects[s]["occurrence_id"] for s in cell["source_object_ids"]}
        require(len(identities) == 1, "A tetrahedron cannot span distinct retained bodies.")
        require(isinstance(cell["vertices"], list) and len(cell["vertices"]) == 4 and
                all(type(v) is int for v in cell["vertices"]), "Invalid vertex indices.")
        owner = next(iter(identities))
        cell_owners[cell["id"]] = owner
        for node in cell["vertices"]:
            require(node not in node_owners or node_owners[node] == owner,
                    "Distinct retained bodies must not share electrical node identities; use an explicit contact.")
            node_owners[node] = owner
        audit_cells.append({**cell, "material_id": "electrical-geometry-only"})
    conductivities = raw["conductivity_s_m"]
    require(isinstance(conductivities, dict) and set(conductivities) == set(cell_owners),
            "Conductivity must map exactly all cell IDs.")
    conductivities = {cid: number(value, "scalar conductivity S/m", nonnegative=True)
                      for cid, value in conductivities.items()}
    contacts = raw.get("contacts", [])
    terminals = raw["terminals"]
    require(isinstance(contacts, list) and len(contacts) <= 2 * len(cells) and
            isinstance(terminals, list) and len(terminals) <= 4 * len(cells),
            "Electrical surface resource budget exceeded.")
    audit_contacts = []
    for item in contacts:
        keys(item, ("id", "left_vertices", "right_vertices", "electrical_contact_conductance_s_m2"))
        audit_contacts.append({"id": item["id"], "left_vertices": item["left_vertices"],
                               "right_vertices": item["right_vertices"],
                               "thermal_contact_conductance_w_m2k": number(
                                   item["electrical_contact_conductance_s_m2"], "contact S/m2", positive=True)})
    data = validate_geometry({"contract": "spike/assembly-tetra-thermal-request/v1",
                              "mesh": {**mesh, "cells": audit_cells, "object_map": audit_objects},
                              "materials": [{"id": "electrical-geometry-only", "thermal_conductivity_w_mk": 1.}],
                              "boundaries": [], "contacts": audit_contacts})
    data["cells"] = cells
    face_cells = {}
    for cell in cells:
        for face in itertools.combinations(cell["vertices"], 3):
            if tuple(sorted(face)) in data["exterior"]:
                face_cells[tuple(sorted(face))] = cell["id"]
    assigned, surface_ids = set(), set()
    for sid, left, right, _, _ in data["contacts"]:
        lc, rc = face_cells[tuple(sorted(left))], face_cells[tuple(sorted(right))]
        require(cell_owners[lc] != cell_owners[rc], "Electrical contact requires distinct retained bodies.")
        require(conductivities[lc] > 0 and conductivities[rc] > 0,
                "Electrical contact cannot touch an insulating cell.")
        assigned.update((tuple(sorted(left)), tuple(sorted(right))))
        surface_ids.add(sid)
    fixed, node_terminals, accepted = {}, {}, []
    for terminal in terminals:
        keys(terminal, ("id", "vertices", "voltage_v"))
        tid = identifier(terminal["id"])
        require(tid not in surface_ids, "Duplicate electrical surface ID.")
        surface_ids.add(tid)
        face = tuple(sorted(indices(terminal["vertices"], 3, len(data["xyz"]))))
        require(face in data["exterior"] and face not in assigned,
                "Terminal must be an unused exterior triangle.")
        require(conductivities[face_cells[face]] > 0, "Terminal cannot touch an insulating cell.")
        assigned.add(face)
        voltage = number(terminal["voltage_v"], "terminal voltage V")
        for node in face:
            require(node not in fixed or fixed[node] == voltage, "Conflicting nodal terminal voltages.")
            fixed[node] = voltage
            node_terminals.setdefault(node, []).append(tid)
        accepted.append((tid, face, voltage))
    data.update(conductivities=conductivities, fixed=fixed, terminals=accepted,
                node_terminals=node_terminals, face_cells=face_cells)
    return data
