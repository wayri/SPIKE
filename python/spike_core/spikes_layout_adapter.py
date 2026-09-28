# SPDX-License-Identifier: Apache-2.0
"""Bounded, digest-correlated router/placer orchestration over SPIKES jobs."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Dict, Mapping

from .contracts import AnalysisSpec, DesignIR
from .design_ir_v2 import DesignIRV2
from .spikes_native_adapter import prepare_job_envelope
from .spikes_layout_contract import (
    HARD_ACCEPTED_VALIDATION_STATES as _HARD_ACCEPTED_VALIDATION_STATES,
    MAX_ENTITY_IDS,
    MAX_EXTERNAL_RESULTS,
    MAX_PHYSICS_EVALUATIONS,
    MAX_REQUIREMENTS,
    SpikesLayoutAdapterError,
    VALIDATION_STATES as _VALIDATION_STATES,
    artifact as _artifact,
    fail as _fail,
    finite as _finite,
    identifier as _identifier,
    is_digest as _is_digest,
    strict_object as _strict_object,
    validate_requirement as _validate_requirement,
    validate_resources as _validate_resources,
    validate_study as _validate_study,
)
LAYOUT_EVALUATION_CONTRACT = "spike/layout-evaluation/v1"
_ENTITY_COLLECTIONS = ("materials", "layers", "nets", "tracks", "arcs", "zones", "pads", "vias", "castellations", "pins", "components", "component_bonds", "connectors", "regions", "bends", "models", "constraints", "variants", "simulation_models")
_ROUTE_MUTABLE_KINDS = {"tracks", "arcs", "zones", "vias", "castellations"}
_PLACE_MUTABLE_KINDS = {"components", "pads", "pins", "component_bonds", "connectors", "models"}
_ROUTE_SCOPE_KINDS = _ROUTE_MUTABLE_KINDS | {"nets", "layers", "pads", "pins", "components", "regions", "constraints"}
_PLACE_SCOPE_KINDS = _PLACE_MUTABLE_KINDS | {"nets", "layers", "regions", "constraints"}

def validate_layout_request(document: Any) -> Dict[str, Any]:
    """Return a normalized copy of one strict layout-evaluation request."""
    allowed = {
        "contract", "record_type", "evaluation_id", "consumer", "candidate", "baseline",
        "parent_candidate_sha256", "changed_entity_ids", "requirements", "physics_evaluations",
        "resources", "deterministic",
    }
    required = {"contract", "record_type", "evaluation_id", "consumer", "candidate", "requirements", "physics_evaluations", "resources", "deterministic"}
    root = _strict_object(document, allowed, required, "layout request")
    if root["contract"] != LAYOUT_EVALUATION_CONTRACT or root["record_type"] != "request":
        _fail("SPIKE-LAYOUT-CONTRACT-0001", "unsupported layout request contract")
    consumer = _strict_object(root["consumer"], {"kind", "implementation", "version"}, {"kind", "implementation"}, "consumer")
    if consumer["kind"] not in ("autorouter", "autoplacer", "joint"):
        _fail("SPIKE-LAYOUT-CONTRACT-0006", "consumer kind is unsupported")
    for field in ("implementation", "version"):
        if field in consumer and (not isinstance(consumer[field], str) or not consumer[field] or len(consumer[field]) > 128):
            _fail("SPIKE-LAYOUT-CONTRACT-0006", f"consumer.{field} is invalid")
    requirements_raw = root["requirements"]
    if not isinstance(requirements_raw, list) or not 1 <= len(requirements_raw) <= MAX_REQUIREMENTS:
        _fail("SPIKE-LAYOUT-CONTRACT-0003", "requirements exceed the bound")
    requirements = [_validate_requirement(item) for item in requirements_raw]
    requirement_ids = [item["id"] for item in requirements]
    if len(set(requirement_ids)) != len(requirement_ids):
        _fail("SPIKE-LAYOUT-CONTRACT-0007", "requirement IDs must be unique")
    known = set(requirement_ids)
    evaluations_raw = root["physics_evaluations"]
    if not isinstance(evaluations_raw, list) or len(evaluations_raw) > MAX_PHYSICS_EVALUATIONS:
        _fail("SPIKE-LAYOUT-CONTRACT-0003", "physics_evaluations exceed the bound")
    evaluations: list[Dict[str, Any]] = []
    bound: set[str] = set()
    evaluation_ids: set[str] = set()
    output_allowlist = {"summary", "issues", "fields", "mesh", "convergence", "conservation", "profiling", "checkpoint"}
    for raw in evaluations_raw:
        item = _strict_object(raw, {"id", "requirement_ids", "model", "study", "requested_outputs"}, {"id", "requirement_ids", "model", "study", "requested_outputs"}, "physics_evaluation")
        evaluation_id = _identifier(item["id"], "physics_evaluation.id")
        if evaluation_id in evaluation_ids:
            _fail("SPIKE-LAYOUT-CONTRACT-0007", "physics evaluation IDs must be unique")
        evaluation_ids.add(evaluation_id)
        ids = item["requirement_ids"]
        if not isinstance(ids, list) or not ids or len(ids) > MAX_REQUIREMENTS or any(req not in known for req in ids) or len(set(ids)) != len(ids):
            _fail("SPIKE-LAYOUT-CONTRACT-0007", "physics evaluation requirement binding is invalid")
        if any(next(req for req in requirements if req["id"] == req_id)["evaluator"] != "native_solver" for req_id in ids):
            _fail("SPIKE-LAYOUT-CONTRACT-0007", "physics evaluation may bind only native_solver requirements")
        outputs = item["requested_outputs"]
        if not isinstance(outputs, list) or not outputs or len(outputs) > 64 or len(set(outputs)) != len(outputs) or any(output not in output_allowlist for output in outputs):
            _fail("SPIKE-LAYOUT-CONTRACT-0006", "requested_outputs contain unsupported values")
        bound.update(ids)
        model = _artifact(item["model"], "physics_evaluation.model", 64 * 1024 * 1024)
        if model["contract"] != "spike/physics-model/v1":
            _fail("SPIKE-LAYOUT-CONTRACT-0004", "physics evaluation model contract is unsupported")
        evaluations.append({
            "id": evaluation_id,
            "requirement_ids": list(ids),
            "model": model,
            "study": _validate_study(item["study"]),
            "requested_outputs": list(outputs),
        })
    native_ids = {item["id"] for item in requirements if item["evaluator"] == "native_solver"}
    if bound != native_ids:
        _fail("SPIKE-LAYOUT-CONTRACT-0007", "every native requirement must be bound exactly once")
    counts: Dict[str, int] = {}
    for item in evaluations:
        for requirement_id in item["requirement_ids"]:
            counts[requirement_id] = counts.get(requirement_id, 0) + 1
    if any(count != 1 for count in counts.values()):
        _fail("SPIKE-LAYOUT-CONTRACT-0007", "native requirements cannot be bound to multiple jobs")
    changed = root.get("changed_entity_ids", [])
    if not isinstance(changed, list) or len(changed) > MAX_ENTITY_IDS or len(set(changed)) != len(changed) or any(not isinstance(item, str) or not item or len(item) > 256 for item in changed):
        _fail("SPIKE-LAYOUT-CONTRACT-0003", "changed_entity_ids exceed the bound or are invalid")
    candidate = _artifact(root["candidate"], "candidate", 1 << 30)
    if candidate["contract"] != "spike/design-ir/v2":
        _fail("SPIKE-LAYOUT-CONTRACT-0004", "candidate must be spike/design-ir/v2")
    normalized: Dict[str, Any] = {
        "contract": LAYOUT_EVALUATION_CONTRACT,
        "record_type": "request",
        "evaluation_id": _identifier(root["evaluation_id"], "evaluation_id"),
        "consumer": copy.deepcopy(consumer),
        "candidate": candidate,
        "requirements": requirements,
        "physics_evaluations": evaluations,
        "resources": _validate_resources(root["resources"]),
        "deterministic": root["deterministic"],
    }
    if not isinstance(normalized["deterministic"], bool):
        _fail("SPIKE-LAYOUT-CONTRACT-0001", "deterministic must be boolean")
    if "baseline" in root:
        baseline = _artifact(root["baseline"], "baseline", 1 << 30)
        if baseline["contract"] != "spike/design-ir/v2":
            _fail("SPIKE-LAYOUT-CONTRACT-0004", "baseline must be spike/design-ir/v2")
        normalized["baseline"] = baseline
    if "parent_candidate_sha256" in root:
        parent = root["parent_candidate_sha256"]
        if not _is_digest(parent):
            _fail("SPIKE-LAYOUT-CONTRACT-0004", "parent_candidate_sha256 is invalid")
        normalized["parent_candidate_sha256"] = parent
    if changed:
        normalized["changed_entity_ids"] = list(changed)
    return normalized


def _coerce_design_ir_v2(value: Any, label: str) -> DesignIRV2:
    if isinstance(value, DesignIRV2):
        return value
    if not isinstance(value, Mapping):
        _fail("SPIKE-LAYOUT-PREFLIGHT-0001", f"{label} must be a complete DesignIR v2 object")
    if value.get("contract") != "spike/design-ir/v2":
        _fail("SPIKE-LAYOUT-PREFLIGHT-0001", f"{label} has an unsupported contract")
    try:
        return DesignIRV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0001", f"{label} is not a valid complete DesignIR v2 object: {exc}")
    raise AssertionError("unreachable")


def canonical_design_ir_json(candidate: Any) -> str:
    """Return the canonical UTF-8 JSON representation used for artifact identity."""
    design = _coerce_design_ir_v2(candidate, "candidate")
    try:
        return json.dumps(
            design.to_dict(), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0001", f"candidate is not canonically serializable: {exc}")
    raise AssertionError("unreachable")


def design_ir_artifact_identity(candidate: Any) -> Dict[str, Any]:
    """Return the digest and byte size of canonical ``spike/design-ir/v2`` JSON."""
    payload = canonical_design_ir_json(candidate).encode("utf-8")
    return {
        "contract": "spike/design-ir/v2",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }


def _entity_index(design: DesignIRV2) -> tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
    serialized = design.to_dict()
    kinds: Dict[str, str] = {}
    records: Dict[str, Dict[str, Any]] = {}
    for collection in _ENTITY_COLLECTIONS:
        for raw in serialized.get(collection, []):
            entity_id = raw.get("id") if isinstance(raw, dict) else None
            if not isinstance(entity_id, str) or not entity_id:
                _fail("SPIKE-LAYOUT-PREFLIGHT-0002", f"{collection} contains an empty entity ID")
            if entity_id in kinds:
                _fail("SPIKE-LAYOUT-PREFLIGHT-0002", f"entity ID {entity_id} occurs more than once")
            kinds[entity_id] = collection
            records[entity_id] = raw
    return kinds, records


def _require_reference(
    owner: Mapping[str, Any], field: str, allowed: set[str], kinds: Mapping[str, str],
    *, optional: bool = False,
) -> None:
    target = owner.get(field, "")
    if optional and target == "":
        return
    if not isinstance(target, str) or target not in kinds or kinds[target] not in allowed:
        _fail(
            "SPIKE-LAYOUT-PREFLIGHT-0003",
            f"entity {owner.get('id', '<unknown>')}.{field} does not reference {sorted(allowed)}",
        )


def _require_references(
    owner: Mapping[str, Any], field: str, allowed: set[str], kinds: Mapping[str, str],
) -> None:
    targets = owner.get(field, [])
    if not isinstance(targets, list):
        _fail("SPIKE-LAYOUT-PREFLIGHT-0003", f"entity {owner.get('id', '<unknown>')}.{field} must be an array")
    for target in targets:
        if not isinstance(target, str) or target not in kinds or kinds[target] not in allowed:
            _fail(
                "SPIKE-LAYOUT-PREFLIGHT-0003",
                f"entity {owner.get('id', '<unknown>')}.{field} contains an inapplicable reference",
            )


def _validate_design_references(records: Mapping[str, Mapping[str, Any]], kinds: Mapping[str, str]) -> None:
    for entity_id, item in records.items():
        kind = kinds[entity_id]
        if kind == "layers":
            _require_reference(item, "material_id", {"materials"}, kinds, optional=True)
            _require_references(item, "region_ids", {"regions"}, kinds)
        elif kind in {"tracks", "arcs"}:
            _require_reference(item, "net_id", {"nets"}, kinds)
            _require_reference(item, "layer_id", {"layers"}, kinds)
        elif kind == "zones":
            _require_reference(item, "net_id", {"nets"}, kinds)
            _require_references(item, "layer_ids", {"layers"}, kinds)
        elif kind == "pads":
            _require_reference(item, "net_id", {"nets"}, kinds, optional=True)
            _require_reference(item, "component_id", {"components"}, kinds, optional=True)
            _require_reference(item, "pin_id", {"pins"}, kinds, optional=True)
            _require_references(item, "layer_ids", {"layers"}, kinds)
        elif kind == "vias":
            _require_reference(item, "net_id", {"nets"}, kinds)
            _require_reference(item, "start_layer_id", {"layers"}, kinds)
            _require_reference(item, "end_layer_id", {"layers"}, kinds)
        elif kind == "castellations":
            _require_reference(item, "net_id", {"nets"}, kinds)
            _require_reference(item, "via_id", {"vias"}, kinds)
            _require_reference(item, "boundary_region_id", {"regions"}, kinds)
        elif kind == "pins":
            _require_reference(item, "component_id", {"components"}, kinds, optional=True)
            _require_reference(item, "net_id", {"nets"}, kinds, optional=True)
            _require_references(item, "pad_ids", {"pads"}, kinds)
        elif kind == "components":
            _require_references(item, "pin_ids", {"pins"}, kinds)
            _require_references(item, "model_ids", {"models"}, kinds)
        elif kind == "component_bonds":
            _require_reference(item, "component_id", {"components"}, kinds, optional=True)
            _require_reference(item, "pin_id", {"pins"}, kinds, optional=True)
            _require_reference(item, "pad_id", {"pads"}, kinds, optional=True)
            _require_reference(item, "electrical_material_id", {"materials"}, kinds, optional=True)
            _require_reference(item, "thermal_material_id", {"materials"}, kinds, optional=True)
        elif kind == "connectors":
            _require_reference(item, "component_id", {"components"}, kinds, optional=True)
            _require_references(item, "pin_ids", {"pins"}, kinds)
            _require_reference(item, "mating_connector_id", {"connectors"}, kinds, optional=True)
        elif kind == "regions":
            _require_references(item, "layer_ids", {"layers"}, kinds)
        elif kind == "bends":
            _require_reference(item, "region_id", {"regions"}, kinds)


def _validate_artifact_identity(design: DesignIRV2, artifact: Mapping[str, Any], label: str) -> Dict[str, Any]:
    identity = design_ir_artifact_identity(design)
    if artifact["sha256"] != identity["sha256"]:
        _fail(
            "SPIKE-LAYOUT-PREFLIGHT-0004",
            f"{label} SHA-256 does not bind the supplied canonical DesignIR v2",
        )
    if artifact["bytes"] != identity["bytes"]:
        _fail(
            "SPIKE-LAYOUT-PREFLIGHT-0004",
            f"{label} byte count does not bind the supplied canonical DesignIR v2",
        )
    return identity


def _validate_lineage_identity(candidate: DesignIRV2, reference: DesignIRV2, label: str) -> None:
    if candidate.design_id != reference.design_id:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0005", f"{label} and candidate design_id values do not correlate")
    if candidate.source != reference.source:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0005", f"{label} and candidate source identities do not correlate")
    if candidate.frame != reference.frame:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0005", f"{label} and candidate coordinate frames do not correlate")
    candidate_kinds, candidate_records = _entity_index(candidate)
    reference_kinds, reference_records = _entity_index(reference)
    candidate_sources = {
        (kind, str(candidate_records[entity_id].get("source_id", ""))): entity_id
        for entity_id, kind in candidate_kinds.items()
        if candidate_records[entity_id].get("source_id")
    }
    for reference_id, kind in reference_kinds.items():
        source_id = str(reference_records[reference_id].get("source_id", ""))
        candidate_id = candidate_sources.get((kind, source_id)) if source_id else None
        if candidate_id is not None and candidate_id != reference_id:
            _fail(
                "SPIKE-LAYOUT-PREFLIGHT-0005",
                f"{label} entity canonical identity changed for {kind}:{source_id}",
            )


def _actual_entity_changes(candidate: DesignIRV2, reference: DesignIRV2) -> tuple[set[str], Dict[str, str]]:
    candidate_kinds, candidate_records = _entity_index(candidate)
    reference_kinds, reference_records = _entity_index(reference)
    all_ids = set(candidate_records) | set(reference_records)
    changed = {
        entity_id for entity_id in all_ids
        if candidate_kinds.get(entity_id) != reference_kinds.get(entity_id)
        or candidate_records.get(entity_id) != reference_records.get(entity_id)
    }
    combined_kinds = {**reference_kinds, **candidate_kinds}
    return changed, combined_kinds


def preflight_layout_candidate(
    document: Any,
    candidate: Any,
    *,
    baseline: Any | None = None,
    parent: Any | None = None,
) -> Dict[str, Any]:
    """Semantically bind a layout request to complete DesignIR v2 candidates.

    ``baseline`` represents the fixed comparison design. ``parent`` represents
    the immediately preceding candidate. When either lineage artifact is
    declared, its complete DesignIR must be supplied so digests, canonical
    identities, and the exact entity change set can be verified fail-closed.
    The exact change set intentionally covers canonical entities only; ordinary
    metadata and issue-list differences do not masquerade as layout mutations.
    """
    request = validate_layout_request(document)
    design = _coerce_design_ir_v2(candidate, "candidate")
    candidate_identity = _validate_artifact_identity(design, request["candidate"], "candidate")
    candidate_kinds, candidate_records = _entity_index(design)
    _validate_design_references(candidate_records, candidate_kinds)

    consumer = request["consumer"]["kind"]
    mutable = (
        _ROUTE_MUTABLE_KINDS if consumer == "autorouter"
        else _PLACE_MUTABLE_KINDS if consumer == "autoplacer"
        else _ROUTE_MUTABLE_KINDS | _PLACE_MUTABLE_KINDS
    )
    scoped = (
        _ROUTE_SCOPE_KINDS if consumer == "autorouter"
        else _PLACE_SCOPE_KINDS if consumer == "autoplacer"
        else _ROUTE_SCOPE_KINDS | _PLACE_SCOPE_KINDS
    )
    frame_id = design.frame.frame_id
    scope_bindings: Dict[str, list[Dict[str, str]]] = {}
    for requirement in request["requirements"]:
        scope = requirement["scope"]
        if scope["frame"] != frame_id:
            _fail(
                "SPIKE-LAYOUT-PREFLIGHT-0006",
                f"requirement {requirement['id']} uses frame {scope['frame']} instead of {frame_id}",
            )
        bindings: list[Dict[str, str]] = []
        for entity_id in scope["entity_ids"]:
            kind = candidate_kinds.get(entity_id)
            if kind is None:
                _fail("SPIKE-LAYOUT-PREFLIGHT-0006", f"requirement {requirement['id']} scopes unknown entity {entity_id}")
            if kind not in scoped:
                _fail(
                    "SPIKE-LAYOUT-PREFLIGHT-0006",
                    f"{kind} entity {entity_id} is inapplicable to {consumer} requirements",
                )
            bindings.append({"entity_id": entity_id, "kind": kind})
        scope_bindings[requirement["id"]] = bindings

    baseline_design: DesignIRV2 | None = None
    parent_design: DesignIRV2 | None = None
    lineage: Dict[str, str] = {}
    if "baseline" in request:
        if baseline is None:
            _fail("SPIKE-LAYOUT-PREFLIGHT-0005", "declared baseline DesignIR v2 was not supplied")
        baseline_design = _coerce_design_ir_v2(baseline, "baseline")
        baseline_identity = _validate_artifact_identity(baseline_design, request["baseline"], "baseline")
        _validate_lineage_identity(design, baseline_design, "baseline")
        lineage["baseline_sha256"] = baseline_identity["sha256"]
    elif baseline is not None:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0005", "a baseline was supplied but is not declared by the request")
    if "parent_candidate_sha256" in request:
        if parent is None:
            _fail("SPIKE-LAYOUT-PREFLIGHT-0005", "declared parent DesignIR v2 was not supplied")
        parent_design = _coerce_design_ir_v2(parent, "parent")
        parent_identity = design_ir_artifact_identity(parent_design)
        if parent_identity["sha256"] != request["parent_candidate_sha256"]:
            _fail("SPIKE-LAYOUT-PREFLIGHT-0005", "parent candidate digest does not correlate")
        _validate_lineage_identity(design, parent_design, "parent")
        lineage["parent_candidate_sha256"] = parent_identity["sha256"]
    elif parent is not None:
        _fail("SPIKE-LAYOUT-PREFLIGHT-0005", "a parent was supplied but is not declared by the request")

    comparison = parent_design or baseline_design
    declared_changed = set(request.get("changed_entity_ids", []))
    if comparison is not None:
        actual_changed, change_kinds = _actual_entity_changes(design, comparison)
        if declared_changed != actual_changed:
            _fail(
                "SPIKE-LAYOUT-PREFLIGHT-0007",
                "changed_entity_ids do not exactly describe candidate changes from its parent/baseline",
            )
    else:
        change_kinds = candidate_kinds
        unknown_changed = declared_changed - set(candidate_kinds)
        if unknown_changed:
            _fail("SPIKE-LAYOUT-PREFLIGHT-0007", "changed_entity_ids contain unknown entities without lineage evidence")
    inapplicable_changed = {
        entity_id: change_kinds.get(entity_id, "unknown")
        for entity_id in declared_changed
        if change_kinds.get(entity_id) not in mutable
    }
    if inapplicable_changed:
        _fail(
            "SPIKE-LAYOUT-PREFLIGHT-0007",
            f"changed entities are inapplicable to {consumer}: {inapplicable_changed}",
        )

    return {
        "contract": LAYOUT_EVALUATION_CONTRACT,
        "evaluation_id": request["evaluation_id"],
        "consumer_kind": consumer,
        "candidate_sha256": candidate_identity["sha256"],
        "candidate_canonical_bytes": candidate_identity["bytes"],
        "candidate_design_id": design.design_id,
        "candidate_source_digest": design.source.source_digest,
        "frame_id": frame_id,
        "entity_count": len(candidate_kinds),
        "changed_entities": [
            {"entity_id": entity_id, "kind": change_kinds[entity_id]}
            for entity_id in sorted(declared_changed)
        ],
        "scope_bindings": scope_bindings,
        **lineage,
    }


def canonical_layout_json(document: Any) -> str:
    """Serialize a validated request canonically with non-finite values forbidden."""
    normalized = validate_layout_request(document)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _derived_request_id(request: Mapping[str, Any], evaluation_id: str) -> str:
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    digest = hashlib.sha256((canonical + "\n" + evaluation_id).encode("utf-8")).hexdigest()
    return f"layout.{digest[:32]}"


def prepare_native_jobs(document: Any, design: DesignIR) -> list[Dict[str, Any]]:
    """Derive deterministic, correlation-bound ``solver-job/v1`` envelopes."""
    request = validate_layout_request(document)
    if not isinstance(design, DesignIR):
        _fail("SPIKE-LAYOUT-CONTRACT-0001", "design must be a DesignIR instance")
    jobs: list[Dict[str, Any]] = []
    for evaluation in request["physics_evaluations"]:
        request_id = _derived_request_id(request, evaluation["id"])
        spec = AnalysisSpec(
            analysis_id=evaluation["id"],
            options={
                "native_study": evaluation["study"],
                "native_requested_outputs": evaluation["requested_outputs"],
                "native_resources": request["resources"],
                "deterministic": request["deterministic"],
            },
        )
        model = {key: evaluation["model"][key] for key in ("path", "sha256", "bytes")}
        jobs.append({
            "physics_evaluation_id": evaluation["id"],
            "requirement_ids": list(evaluation["requirement_ids"]),
            "candidate_sha256": request["candidate"]["sha256"],
            "request_id": request_id,
            "job": prepare_job_envelope(design, spec, model, request_id=request_id),
        })
    return jobs


def _evaluate_requirement(requirement: Mapping[str, Any], value: float) -> tuple[str, float | None]:
    relation = requirement["relation"]
    if relation == "le":
        margin = float(requirement["upper_si"]) - value
    elif relation == "ge":
        margin = value - float(requirement["lower_si"])
    elif relation == "between":
        margin = min(value - float(requirement["lower_si"]), float(requirement["upper_si"]) - value)
    elif relation == "target":
        margin = float(requirement["absolute_tolerance_si"]) - abs(value - float(requirement["target_si"]))
    else:
        return "evaluated", None
    return ("satisfied" if margin >= 0 else "violated"), margin


def _objective_term(requirement: Mapping[str, Any], result: Mapping[str, Any]) -> float | None:
    """Return one dimensionless lower-is-better objective contribution.

    A scalar is emitted only when the request supplies an explicit positive SI
    normalization. This prevents resistance, delay, loss, temperature, and BER
    from being combined as though their numerical magnitudes had common units.
    """
    if requirement["kind"] != "objective" or "normalization_si" not in requirement:
        return None
    value = result.get("value_si")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    scale = float(requirement["normalization_si"])
    weight = float(requirement["weight"])
    relation = requirement["relation"]
    if relation == "minimize":
        raw = float(value) / scale
    elif relation == "maximize":
        raw = -float(value) / scale
    elif relation == "target":
        raw = abs(float(value) - float(requirement["target_si"])) / scale
    else:
        margin = result.get("margin_si")
        if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not math.isfinite(float(margin)):
            return None
        raw = max(0.0, -float(margin)) / scale
    term = weight * raw
    return term if math.isfinite(term) else None


def map_layout_results(
    document: Any,
    native_results: Mapping[str, Any],
    *,
    external_results: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Correlate native/external metrics and compute fail-closed feasibility."""
    request = validate_layout_request(document)
    if not isinstance(native_results, Mapping) or len(native_results) > MAX_PHYSICS_EVALUATIONS:
        _fail("SPIKE-LAYOUT-RESULT-0001", "native_results exceed the bound")
    external = external_results or {}
    if not isinstance(external, Mapping) or len(external) > MAX_EXTERNAL_RESULTS:
        _fail("SPIKE-LAYOUT-RESULT-0001", "external_results exceed the bound")
    expected_jobs = {item["id"]: _derived_request_id(request, item["id"]) for item in request["physics_evaluations"]}
    if any(key not in set(expected_jobs.values()) for key in native_results):
        _fail("SPIKE-LAYOUT-RESULT-0002", "native result references an unknown request")
    requirement_results: list[Dict[str, Any]] = []
    job_results: list[Dict[str, Any]] = []
    evaluation_by_requirement = {
        requirement_id: item
        for item in request["physics_evaluations"]
        for requirement_id in item["requirement_ids"]
    }
    for evaluation_id, request_id in expected_jobs.items():
        raw = native_results.get(request_id)
        status = "missing"
        if raw is not None:
            if not isinstance(raw, dict) or raw.get("contract") != "spike/result-bundle/v2" or raw.get("request_id") != request_id:
                _fail("SPIKE-LAYOUT-RESULT-0002", f"native result correlation failed for {evaluation_id}")
            status = raw.get("status", "failed")
            if status not in ("completed", "failed", "cancelled", "unsupported"):
                _fail("SPIKE-LAYOUT-RESULT-0003", "native result status is invalid")
        job_results.append({"physics_evaluation_id": evaluation_id, "request_id": request_id, "status": status})
    known_requirements = {item["id"] for item in request["requirements"]}
    if any(key not in known_requirements for key in external):
        _fail("SPIKE-LAYOUT-RESULT-0002", "external result references an unknown requirement")
    for requirement in request["requirements"]:
        result: Dict[str, Any] = {
            "requirement_id": requirement["id"],
            "metric_id": requirement["metric_id"],
            "status": "unknown",
            "validation_state": "unsupported",
        }
        if requirement["evaluator"] == "native_solver":
            evaluation = evaluation_by_requirement[requirement["id"]]
            request_id = expected_jobs[evaluation["id"]]
            raw = native_results.get(request_id)
            if raw is not None:
                native_status = raw.get("status")
                validation_state = raw.get("validation_state", "unsupported")
                if validation_state not in _VALIDATION_STATES:
                    _fail("SPIKE-LAYOUT-RESULT-0003", "native validation_state is invalid")
                result["validation_state"] = validation_state
                if native_status == "unsupported":
                    result["status"] = "unsupported"
                elif native_status in ("failed", "cancelled"):
                    result["status"] = "error"
                elif native_status == "completed":
                    summary = raw.get("summary")
                    value = summary.get(requirement["result_key"]) if isinstance(summary, dict) else None
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                        result["status"] = "unknown"
                    else:
                        numeric = float(value)
                        result["value_si"] = numeric
                        result["status"], margin = _evaluate_requirement(requirement, numeric)
                        if margin is not None:
                            result["margin_si"] = margin
        else:
            raw_external = external.get(requirement["id"])
            if raw_external is not None:
                item = _strict_object(raw_external, {"status", "value_si", "validation_state"}, {"status", "validation_state"}, "external result")
                if item["status"] not in ("satisfied", "violated", "evaluated", "unknown", "unsupported", "error"):
                    _fail("SPIKE-LAYOUT-RESULT-0003", "external result status is invalid")
                result["status"] = item["status"]
                if item["validation_state"] not in _VALIDATION_STATES:
                    _fail("SPIKE-LAYOUT-RESULT-0003", "external validation_state is invalid")
                result["validation_state"] = item["validation_state"]
                if "value_si" in item:
                    numeric = _finite(item["value_si"], "external value_si")
                    result["value_si"] = numeric
                    computed, margin = _evaluate_requirement(requirement, numeric)
                    if item["status"] in ("satisfied", "violated", "evaluated") and item["status"] != computed:
                        _fail("SPIKE-LAYOUT-RESULT-0003", "external status contradicts its numeric value")
                    if margin is not None:
                        result["margin_si"] = margin
        requirement_results.append(result)
    hard = [result for result, requirement in zip(requirement_results, request["requirements"]) if requirement["kind"] == "hard_constraint"]
    feasible = all(
        result["status"] == "satisfied"
        and result["validation_state"] in _HARD_ACCEPTED_VALIDATION_STATES
        for result in hard
    )
    statuses = {result["status"] for result in requirement_results}
    if statuses == {"unsupported"}:
        overall = "unsupported"
    elif "error" in statuses:
        overall = "failed"
    elif statuses & {"unknown", "unsupported"}:
        overall = "partial"
    else:
        overall = "completed"
    mapped = {
        "contract": LAYOUT_EVALUATION_CONTRACT,
        "record_type": "result",
        "evaluation_id": request["evaluation_id"],
        "candidate_sha256": request["candidate"]["sha256"],
        "status": overall,
        "feasible": feasible,
        "requirements": requirement_results,
        "native_jobs": job_results,
    }
    objectives = [
        (requirement, result)
        for requirement, result in zip(request["requirements"], requirement_results)
        if requirement["kind"] == "objective"
    ]
    terms = [_objective_term(requirement, result) for requirement, result in objectives]
    mapped["objective_score_state"] = (
        "available" if objectives and all(term is not None for term in terms)
        else "not_requested" if not objectives
        else "normalization_or_result_missing"
    )
    if objectives and all(term is not None for term in terms):
        mapped["objective_score"] = math.fsum(float(term) for term in terms)
        mapped["objective_score_lower_is_better"] = True
        mapped["objective_terms"] = [
            {"requirement_id": requirement["id"], "dimensionless_term": float(term)}
            for (requirement, _), term in zip(objectives, terms)
        ]
    return mapped


__all__ = [
    "LAYOUT_EVALUATION_CONTRACT",
    "SpikesLayoutAdapterError",
    "canonical_design_ir_json",
    "canonical_layout_json",
    "design_ir_artifact_identity",
    "map_layout_results",
    "preflight_layout_candidate",
    "prepare_native_jobs",
    "validate_layout_request",
]
