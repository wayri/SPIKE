# SPDX-License-Identifier: Apache-2.0
"""Explicit, occurrence-bound STEP handoff; no source placement inference."""
from __future__ import annotations

import copy
import json

from .mcad_export_contract import MAX_BYTES, rigid_transform, validate_assembly
from .spider_v2_schema import content_digest


def bind_component_models(assembly: dict, bindings: object) -> None:
    """Append explicitly supplied solids and resolve only fully supplied occurrences.

    Input is inert JSON. Assets remain embedded; no file paths or URLs are opened.
    Existing MCAD validation owns STEP byte/digest, material and geometry checks.
    """
    if bindings is None:
        return
    if not isinstance(bindings, list) or len(bindings) > 10000:
        raise ValueError("component_models requires at most 10000 explicit bindings.")
    if len(json.dumps(bindings, allow_nan=False).encode("utf-8")) > MAX_BYTES:
        raise ValueError("component_models exceeds the 64 MiB MCAD budget.")
    properties = assembly.get("properties", {})
    occurrences = {item["id"]: item for item in properties.get("component_occurrences", [])}
    models = properties.get("retained_design_models", {})
    digests = properties.get("retained_design_digests", {})
    supplied: dict[str, set[str]] = {}
    objects = []
    required = {"occurrence_id", "model_id", "design_digest", "model_to_board_mm",
                "geometry", "placement_reference"}
    for binding in bindings:
        if (not isinstance(binding, dict) or not required.issubset(binding)
                or set(binding) - required - {"material_id"}):
            raise ValueError("component_models binding fields are incomplete or unknown.")
        occurrence_id, model_id = binding["occurrence_id"], binding["model_id"]
        if not isinstance(occurrence_id, str) or not isinstance(model_id, str):
            raise ValueError("Component occurrence and model identities must be strings.")
        occurrence = occurrences.get(occurrence_id)
        if occurrence is None or model_id not in occurrence["model_ids"]:
            raise ValueError("Component model binding has an unknown occurrence or model owner.")
        design_id = occurrence["design_id"]
        if binding["design_digest"] != digests.get(design_id):
            raise ValueError("Component model binding has a stale retained design digest.")
        source_model = next((item for item in models.get(design_id, [])
                             if item["id"] == model_id), None)
        if source_model is None:
            raise ValueError("Component model binding requires a retained canonical model.")
        owned = supplied.setdefault(occurrence_id, set())
        if model_id in owned:
            raise ValueError("Component model binding duplicates a model occurrence.")
        owned.add(model_id)
        reference = binding["placement_reference"]
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 2048:
            raise ValueError("Component placement requires a bounded review reference.")
        transform = rigid_transform(binding["model_to_board_mm"])
        geometry = binding["geometry"]
        if not isinstance(geometry, dict) or geometry.get("type") != "step":
            raise ValueError("Component model binding requires a complete embedded STEP solid.")
        if source_model.get("digest") and source_model["digest"] != geometry.get("sha256"):
            raise ValueError("Component model STEP differs from its retained model digest.")
        row = {"id": occurrence_id + "/model:" + model_id,
               "name": occurrence["name"] + " / " + model_id,
               "kind": "component", "parent_id": occurrence["board_occurrence_id"],
               "transform": copy.deepcopy(transform), "geometry": copy.deepcopy(geometry),
               "source": {"component_occurrence_id": occurrence_id, "model_id": model_id,
                          "design_digest": binding["design_digest"], "uri": source_model["uri"],
                          "supplied_step_sha256": geometry.get("sha256")},
               "properties": {"placement_reference": reference,
                              "placement_state": "explicit_board_local",
                              "solver_ready": False, "material_qualified": False}}
        if "material_id" in binding:
            row["material_id"] = binding["material_id"]
        objects.append(row)
    # Validate on a copy first: rejected handoffs never partly mutate projection.
    candidate = copy.deepcopy(assembly)
    candidate["objects"].extend(objects)
    if objects:
        validate_assembly(candidate)
    assembly["objects"].extend(objects)
    complete = {key for key, ids in supplied.items()
                if ids == set(occurrences[key]["model_ids"])}
    assembly["diagnostics"][:] = [item for item in assembly["diagnostics"]
        if not (item["code"] == "COMPONENT_GEOMETRY_REQUIRED" and item["source_id"] in complete)]


def retained_design_digest(design: dict) -> str:
    """Digest of the exact canonical design presented by mechanical projection."""
    return content_digest(design)
