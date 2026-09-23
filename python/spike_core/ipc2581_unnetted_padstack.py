"""Source-only retention for complete IPC-2581 padstacks without native nets."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping


GeometryIssue = Callable[..., None]


def finalize_unnetted_padstack_groups(
    groups: Mapping[str, list[Dict[str, Any]]],
    *,
    geometry_issue: GeometryIssue,
) -> tuple[list[Dict[str, Any]], int]:
    """Retain only complete regular-layer groups, without inferring connectivity."""
    retained: list[Dict[str, Any]] = []
    normalized = 0
    for identity, occurrences in groups.items():
        first = occurrences[0]
        expected_layers = list(first["stack"]["layers"])
        actual_layers = [str(item["layer"]) for item in occurrences]
        common_fields = {(item["stack_name"], item["location"]) for item in occurrences}
        if (
            len(common_fields) != 1
            or sorted(actual_layers) != sorted(expected_layers)
            or len(set(actual_layers)) != len(actual_layers)
        ):
            for item in occurrences:
                geometry_issue(
                    "IMPORT_IPC2581_NET_REF_UNRESOLVED",
                    "Unnetted padstack occurrence group is incomplete or ambiguous.",
                    source_id=item["source_id"],
                )
            continue
        ordered = sorted(occurrences, key=lambda item: expected_layers.index(item["layer"]))
        retained.append({
            "id": identity,
            "kind": "retained_unnetted_padstack_occurrence_group",
            "status": "retained_unresolved",
            "reason": "native_net_identity_absent",
            "padstack_ref": first["stack_name"],
            "raw_net_ref": "",
            "at_mm": list(first["location"]),
            "expected_regular_layer_ids": expected_layers,
            "occurrence_count": len(ordered),
            "occurrences": [{
                "source_index": item["source_index"],
                "source_id": item["source_id"],
                "layer_id": item["layer"],
                "raw_layer_ref": item["raw_layer_ref"],
                "layer_polarity": item["layer_polarity"],
                "at_mm": list(item["location"]),
                "shape": {
                    "kind": item["shape"][0],
                    "size_mm": [item["shape"][1], item["shape"][2]],
                    "source_primitive_id": item["shape"][3],
                },
                "xform": item["xform"],
                "raw_pad_attributes": item["raw_pad_attributes"],
                "raw_set_attributes": item["raw_set_attributes"],
                "raw_layer_feature_attributes": item["raw_layer_feature_attributes"],
            } for item in ordered],
        })
        normalized += len(ordered)
    retained.sort(key=lambda item: str(item["id"]))
    return retained, normalized
