# SPDX-License-Identifier: Apache-2.0
"""Explicit geometry/patch incidence for a source-labelled annular stack."""
from __future__ import annotations
import hashlib
import json

from .dc_axial_ownership import compile_axial_ownership
from .dc_annular_land_input import prepare as prepare_land, number, require

REQUEST = "spike/dc-annular-stack-request/v1"


def prepare(raw):
    require(type(raw) is dict and set(raw) == {"contract", "ownership", "lands", "connections", "resistors", "external_currents"}
            and raw["contract"] == REQUEST, "Unsupported annular stack request")
    ownership = compile_axial_ownership(raw["ownership"])
    require(type(raw["lands"]) is list and 2 <= len(raw["lands"]) <= 8
            and len(raw["lands"]) == len(ownership["lands"]), "Supply exactly2..8 owned lands")
    physical = {land["id"]: land for land in ownership["lands"]}
    names, lands, ports, external, work = [], [], [], [], 0
    require(type(raw["external_currents"]) is dict, "External currents require explicit per-land maps")
    for item in raw["lands"]:
        require(type(item) is dict and set(item) == {"land_id", "request", "source_binding"}, "Invalid land record")
        name = item["land_id"]
        require(name in physical and name not in names, "Land ownership identity differs")
        land, request = physical[name], item["request"]
        data = prepare_land(request)
        require(all(c["current_a"] == 0 for c in request["contacts"]), "Master land currents must be zero; coupling computes actual currents")
        require(request["radial_planes_mm"][0] == raw["ownership"]["bore_radius_mm"]
                and request["radial_planes_mm"][-1] == land["outer_radius_mm"]
                and request["axial_planes_mm"][0] == land["z_min_mm"]
                and request["axial_planes_mm"][-1] == land["z_max_mm"]
                and request["conductivity_s_m"] == land["conductivity_s_m"], "Land field support/material differs from owned geometry")
        binding = item["source_binding"]
        if binding is not None:
            require(type(binding) is dict and binding.get("contract") == "spike/source-annular-pad/v1"
                    and {"layer", "net", "center_xy_mm", "bore_radius_mm", "outer_radius_mm",
                         "slab_faces_mm", "conductivity_s_m", "binding_digest"} <= set(binding), "Invalid source binding")
            payload = {k: v for k, v in binding.items() if k != "binding_digest"}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            require(binding.get("binding_digest") == digest and binding["layer"] == land["layer"]
                    and binding["net"] == raw["ownership"]["net"]
                    and binding["center_xy_mm"] == raw["ownership"]["center_xy_mm"]
                    and binding["bore_radius_mm"] == raw["ownership"]["bore_radius_mm"]
                    and binding["outer_radius_mm"] == land["outer_radius_mm"]
                    and binding["slab_faces_mm"] == [land["z_min_mm"], land["z_max_mm"]]
                    and binding["conductivity_s_m"] == land["conductivity_s_m"], "Source geometry/binding differs from field land")
        ids = [p["id"] for p in request["contacts"]]
        source = raw["external_currents"].get(name)
        require(type(source) is dict and set(source) == set(ids), "Every external port current must be explicit")
        external.append([number(source[i], -1e9, 1e9) for i in ids])
        work += len(data["cells"])*len(ids)
        names.append(name); lands.append(request); ports.append(ids)
    require(set(raw["external_currents"]) == set(names) and work <= 8192, "Stack source identity or field-solve work budget exceeded")

    def endpoint(value):
        require(type(value) is dict and set(value) == {"land_id", "contact_id"}, "Explicit edge endpoint required")
        require(value["land_id"] in names, "Unknown edge land")
        b = names.index(value["land_id"])
        require(value["contact_id"] in ports[b], "Unknown edge patch")
        return [b, ports[b].index(value["contact_id"])]

    require(type(raw["connections"]) is list and len(raw["connections"]) == len(ownership["segments"]), "Every physical barrel needs one explicit patch connection")
    edges, metadata, seen = [], [], set()
    segments = {s["id"]: s for s in ownership["segments"]}
    for connection in raw["connections"]:
        require(type(connection) is dict and set(connection) == {"segment_id", "source_contact_id", "target_contact_id"}, "Invalid barrel connection")
        sid = connection["segment_id"]
        require(sid in segments and sid not in seen, "Duplicate or unknown physical barrel")
        seen.add(sid); row = segments[sid]
        ends = []
        for label, z, native in (("source", row["start_mm"][2], row["source_contact"]),
                                 ("target", row["end_mm"][2], row["target_contact"])):
            land_id = row[label+"_land"]; cid = connection[label+"_contact_id"]
            require(cid == native["id"], "Barrel finite contact identity differs")
            b, p = endpoint({"land_id": land_id, "contact_id": cid})
            patch, land = lands[b]["contacts"][p], physical[land_id]
            face = "z_min" if z == land["z_min_mm"] else "z_max" if z == land["z_max_mm"] else None
            require(face is not None and patch["face"] == face
                    and patch["interval_mm"] == [row["inner_radius_mm"], row["outer_radius_mm"]],
                    "Barrel face patch does not match its exact owned annulus/slab face")
            ends.append([b, p])
        edges.append({"p": ends[0], "n": ends[1], "resistance_ohm": row["gap_resistance_ohm"]})
        # The ownership helper's imposed-current diagnostics are not a solution
        # of this circuit. Retain only geometry/material/contact support here;
        # the final edge record reconstructs density from its actual current.
        geometry = {key: value for key, value in row.items() if key not in {
            "imposed_current_a", "current_density_a_mm2", "imposed_current_joule_heat_w", "requires_resolve"}}
        metadata.append({"id": sid, "kind": "physical_barrel", "geometry": geometry})
    require(type(raw["resistors"]) is list and len(raw["resistors"]) <= 16, "Resistor resource budget exceeded")
    for resistor in raw["resistors"]:
        require(type(resistor) is dict and set(resistor) == {"id", "p", "n", "resistance_ohm"}, "Invalid resistor")
        identity = resistor["id"]
        require(type(identity) is str and 0 < len(identity) <= 80 and identity not in seen, "Duplicate or invalid edge ID")
        seen.add(identity)
        edges.append({"p": endpoint(resistor["p"]), "n": endpoint(resistor["n"]), "resistance_ohm": resistor["resistance_ohm"]})
        metadata.append({"id": identity, "kind": "supplied_resistor"})
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= 2*1024*1024, "Stack input budget exceeded")
    return {"lands": lands, "names": names, "ports": ports, "external": external, "edges": edges,
            "metadata": metadata, "ownership": ownership, "digest": hashlib.sha256(encoded).hexdigest()}
