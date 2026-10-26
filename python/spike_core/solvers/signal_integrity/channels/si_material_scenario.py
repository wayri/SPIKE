# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Immutable, source-bound material preparation for SI design scenarios."""

from __future__ import annotations

import copy
from dataclasses import fields
import json
import math
from typing import Any, Mapping

from ....spider_v2 import SpiDeRV2
from ....spider_v2_schema import content_digest


REQUEST_CONTRACT = "spike/si-material-scenario-request/v1"
SCENARIO_CONTRACT = "spike/si-material-scenario/v1"
RESULT_CONTRACT = "spike/si-material-scenario-result/v1"
METADATA_KEY = "spike.si_material_scenario"

MAX_MATERIAL_OVERRIDES = 256
MAX_DESIGN_BYTES = 128 * 1024 * 1024
MAX_DESIGN_ENTITIES = 250_000
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_TEXT_LENGTH = 1024
MAX_CONDUCTIVITY_S_PER_M = 1.0e12
MAX_TEMPERATURE_K = 1.0e5
ASSUMPTION_STATUSES = frozenset({"assumed", "reported", "measured"})
CONDUCTIVE_MATERIAL_TYPES = frozenset({"conductor", "copper"})

_REQUEST_FIELDS = {
    "contract", "design_digest_sha256", "source_digest", "material_overrides",
}
_OVERRIDE_FIELDS = {
    "material_id", "material_type", "conductivity_s_per_m", "provenance",
}
_PROVENANCE_FIELDS = {"source", "model", "temperature_k", "assumption_status"}
_ENTITY_COLLECTIONS = (
    "materials", "layers", "nets", "tracks", "arcs", "zones", "pads", "vias",
    "drills", "castellations", "pins", "components", "component_bonds",
    "connectors", "regions", "bends", "models", "constraints", "variants",
    "simulation_models",
)


class SiMaterialScenarioError(ValueError):
    """Raised when an SI material scenario is malformed or stale."""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SiMaterialScenarioError(f"{path} must be an object.")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing or unknown:
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(sorted(missing)))
        if unknown:
            details.append("unknown fields: " + ", ".join(sorted(unknown)))
        raise SiMaterialScenarioError(f"{path} has " + "; ".join(details) + ".")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise SiMaterialScenarioError(
            f"{path} must be a non-empty string of at most {MAX_TEXT_LENGTH} characters."
        )
    if value != value.strip():
        raise SiMaterialScenarioError(f"{path} must not have leading or trailing whitespace.")
    return value


def _sha256(value: Any, path: str) -> str:
    text = _text(value, path)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise SiMaterialScenarioError(f"{path} must be a lowercase SHA-256 digest.")
    return text


def _positive_number(value: Any, path: str, *, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SiMaterialScenarioError(f"{path} must be a JSON number, not a string or boolean.")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise SiMaterialScenarioError(
            f"{path} must be finite, positive, and no greater than {upper:g}."
        ) from None
    if not math.isfinite(number) or number <= 0.0 or number > upper:
        raise SiMaterialScenarioError(
            f"{path} must be finite, positive, and no greater than {upper:g}."
        )
    return number


def _canonical_json_bytes(value: Any, path: str, maximum: int) -> bytes:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise SiMaterialScenarioError(
            f"{path} must contain finite canonical JSON values: {exc}"
        ) from None
    if len(encoded) > maximum:
        raise SiMaterialScenarioError(f"{path} exceeds the {maximum}-byte admission limit.")
    return encoded


def _validated_design(design: Any) -> tuple[SpiDeRV2, dict[str, Any]]:
    if not isinstance(design, dict):
        raise SiMaterialScenarioError("design must be a canonical SpiDeR v2 object.")
    allowed = {field.name for field in fields(SpiDeRV2)}
    required = {"contract", "design_id", "name", "source", "materials"}
    unknown = set(design) - allowed
    missing = required - set(design)
    if unknown or missing:
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(sorted(missing)))
        if unknown:
            details.append("unknown fields: " + ", ".join(sorted(unknown)))
        raise SiMaterialScenarioError("design has " + "; ".join(details) + ".")
    if design.get("contract") != "spike/design-ir/v2":
        raise SiMaterialScenarioError("design must use spike/design-ir/v2.")
    _canonical_json_bytes(design, "design", MAX_DESIGN_BYTES)
    try:
        model = SpiDeRV2.from_dict(design)
    except (TypeError, ValueError, KeyError, RecursionError) as exc:
        raise SiMaterialScenarioError(f"design must be valid spike/design-ir/v2: {exc}") from None
    entity_count = sum(len(getattr(model, name)) for name in _ENTITY_COLLECTIONS)
    if entity_count > MAX_DESIGN_ENTITIES:
        raise SiMaterialScenarioError(
            f"design exceeds the {MAX_DESIGN_ENTITIES}-entity material-scenario admission limit."
        )
    source = design.get("source")
    if not isinstance(source, Mapping):
        raise SiMaterialScenarioError("design.source must be an object.")
    _sha256(source.get("source_digest"), "design.source.source_digest")
    metadata = design.get("metadata", {})
    if isinstance(metadata, Mapping) and METADATA_KEY in metadata:
        raise SiMaterialScenarioError(
            f"design already carries {METADATA_KEY}; prepare a new scenario from its bound base design."
        )
    return model, copy.deepcopy(design)


def prepare_si_material_scenario(design: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Return a new SpiDeR v2 design with explicit, auditable SI material values.

    The supplied design is never mutated. Its native source identity is retained;
    scenario identity and user-supplied material provenance are recorded separately.
    """

    _canonical_json_bytes(request, "request", MAX_REQUEST_BYTES)
    request_object = _object(request, "request")
    _exact_fields(request_object, _REQUEST_FIELDS, "request")
    if request_object["contract"] != REQUEST_CONTRACT:
        raise SiMaterialScenarioError(f"request.contract must be {REQUEST_CONTRACT!r}.")
    model, prepared = _validated_design(design)

    base_design_sha256 = content_digest(design)
    expected_design_sha256 = _sha256(
        request_object["design_digest_sha256"], "request.design_digest_sha256"
    )
    if expected_design_sha256 != base_design_sha256:
        raise SiMaterialScenarioError("request design digest is stale or belongs to another design revision.")

    source_digest = _sha256(request_object["source_digest"], "request.source_digest")
    actual_source_digest = str(design["source"]["source_digest"])
    if source_digest != actual_source_digest:
        raise SiMaterialScenarioError("request source digest does not match the design source identity.")

    raw_overrides = request_object["material_overrides"]
    if not isinstance(raw_overrides, list):
        raise SiMaterialScenarioError("request.material_overrides must be an array.")
    if not 1 <= len(raw_overrides) <= MAX_MATERIAL_OVERRIDES:
        raise SiMaterialScenarioError(
            f"request.material_overrides must contain 1 through {MAX_MATERIAL_OVERRIDES} entries."
        )

    material_models = {material.id: material for material in model.materials}
    material_rows = prepared.get("materials")
    if not isinstance(material_rows, list):
        raise SiMaterialScenarioError("design.materials must be an array.")
    material_dicts = {
        row.get("id"): row for row in material_rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, raw_override in enumerate(raw_overrides):
        path = f"request.material_overrides[{index}]"
        override = _object(raw_override, path)
        _exact_fields(override, _OVERRIDE_FIELDS, path)
        material_id = _text(override["material_id"], f"{path}.material_id")
        if material_id in seen:
            raise SiMaterialScenarioError(f"{path}.material_id duplicates {material_id!r}.")
        seen.add(material_id)
        material = material_models.get(material_id)
        material_row = material_dicts.get(material_id)
        if material is None or material_row is None:
            raise SiMaterialScenarioError(f"{path}.material_id references unknown material {material_id!r}.")
        material_type = _text(override["material_type"], f"{path}.material_type")
        if material_type not in CONDUCTIVE_MATERIAL_TYPES:
            choices = ", ".join(sorted(CONDUCTIVE_MATERIAL_TYPES))
            raise SiMaterialScenarioError(f"{path}.material_type must be one of: {choices}.")
        if material.material_class != material_type:
            raise SiMaterialScenarioError(
                f"{path} targets material class {material.material_class!r}, not {material_type!r}."
            )
        conductivity = _positive_number(
            override["conductivity_s_per_m"],
            f"{path}.conductivity_s_per_m",
            upper=MAX_CONDUCTIVITY_S_PER_M,
        )
        raw_provenance = _object(override["provenance"], f"{path}.provenance")
        _exact_fields(raw_provenance, _PROVENANCE_FIELDS, f"{path}.provenance")
        assumption_status = _text(
            raw_provenance["assumption_status"], f"{path}.provenance.assumption_status"
        )
        if assumption_status not in ASSUMPTION_STATUSES:
            choices = ", ".join(sorted(ASSUMPTION_STATUSES))
            raise SiMaterialScenarioError(
                f"{path}.provenance.assumption_status must be one of: {choices}."
            )
        provenance = {
            "source": _text(raw_provenance["source"], f"{path}.provenance.source"),
            "model": _text(raw_provenance["model"], f"{path}.provenance.model"),
            "temperature_k": _positive_number(
                raw_provenance["temperature_k"],
                f"{path}.provenance.temperature_k",
                upper=MAX_TEMPERATURE_K,
            ),
            "assumption_status": assumption_status,
        }
        original_value = material_row.get("conductivity_s_per_m")
        material_row["conductivity_s_per_m"] = conductivity
        normalized.append({
            "material_id": material_id,
            "material_type": material_type,
            "property": "conductivity_s_per_m",
            "value": conductivity,
            "base_value": original_value,
            "provenance": provenance,
        })

    scenario_payload = {
        "contract": SCENARIO_CONTRACT,
        "base_design_sha256": base_design_sha256,
        "source_digest": source_digest,
        "material_overrides": normalized,
    }
    scenario_sha256 = content_digest(scenario_payload)
    scenario_record = {**scenario_payload, "scenario_sha256": scenario_sha256}
    metadata = prepared.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise SiMaterialScenarioError("design.metadata must be an object.")
    metadata[METADATA_KEY] = copy.deepcopy(scenario_record)

    if prepared.get("source") != design.get("source"):
        raise AssertionError("SI material preparation must preserve native source identity.")
    prepared_design_sha256 = content_digest(prepared)
    return {
        "contract": RESULT_CONTRACT,
        "design": prepared,
        "provenance": {
            **scenario_record,
            "prepared_design_sha256": prepared_design_sha256,
        },
    }


__all__ = [
    "ASSUMPTION_STATUSES", "CONDUCTIVE_MATERIAL_TYPES", "METADATA_KEY", "REQUEST_CONTRACT", "RESULT_CONTRACT",
    "SCENARIO_CONTRACT", "SiMaterialScenarioError", "prepare_si_material_scenario",
]
