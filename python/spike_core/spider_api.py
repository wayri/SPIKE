# SPDX-License-Identifier: Apache-2.0
"""Read-only, bounded SpiDeR v1/v2 interoperability operations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from .contracts import SpiDeR
from .spider_v2 import SpiDeRV2
from .spider_v2_schema import content_digest
from .spider_api_validation import (
    API_RESULT_CONTRACT, ENTITY_TYPES, V2_REFS, as_v2, issue, validate_document,
)


METHODS = (
    "spider_capabilities", "validate_spider", "normalize_spider", "query_spider",
    "compare_spider",
)
_IDENTITY_FRAME = [
    1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0,
]


def _response(method: str, ok: bool, **values: Any) -> dict[str, Any]:
    # Caller evidence can describe an input contract, but can never replace the
    # response envelope identity or dispatch result.
    return {
        **values, "contract": API_RESULT_CONTRACT, "method": method, "ok": ok,
        "validation_is_not_solver_admission": True,
    }


def _projection_losses(model: SpiDeRV2) -> list[str]:
    losses: list[str] = []
    if list(model.frame.transform) != _IDENTITY_FRAME or model.frame.frame_id != "board" or model.frame.parent_frame_id:
        losses.append("coordinate_frame")
    for name in ("pins", "constraints", "variants", "simulation_models"):
        if getattr(model, name):
            losses.append(name)
    if model.vendor_extensions:
        losses.append("vendor_extensions")
    return losses


def _semantic_entity(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entity.items() if key not in {"id", "extensions"}}


def _roundtrip_projection_losses(model: SpiDeRV2, projected: SpiDeR) -> list[str]:
    """Detect stale legacy snapshots or fields that v1 cannot reproduce."""
    restored = SpiDeRV2.from_v1(projected, source_digest=model.source.source_digest)
    before, after = model.to_dict(), restored.to_dict()
    losses: list[str] = []
    for entity_type in ENTITY_TYPES:
        if entity_type in {"pins", "constraints", "variants", "simulation_models"}:
            continue
        left = {
            item.get("source_id") or item.get("id"): _semantic_entity(item)
            for item in before.get(entity_type, [])
        }
        right = {
            item.get("source_id") or item.get("id"): _semantic_entity(item)
            for item in after.get(entity_type, [])
        }
        for identity in sorted(set(left) | set(right)):
            if left.get(identity) != right.get(identity):
                losses.append(f"semantic_roundtrip:{entity_type}:{identity}")
                if len(losses) >= 50:
                    losses.append("semantic_roundtrip:additional_differences")
                    return losses
    return losses


def normalize_document(
    document: Any, *, target_contract: str | None = None, max_issues: int = 200,
    require_lossless: bool = False,
) -> dict[str, Any]:
    """Normalize an inline SpiDeR document with revision and projection evidence."""
    model, report = validate_document(document, max_issues=max_issues)
    source_contract = report.get("document_contract")
    target = target_contract or source_contract
    projection = {
        "source_contract": source_contract,
        "target_contract": target,
        "migration_applied": source_contract != target,
        "lossy": False,
        "losses": [],
    }
    if model is None:
        return _response("normalize_spider", False, **report, normalized_document=None,
                         normalized_revision=None, projection=projection)
    try:
        if target == "spike/design-ir/v2":
            normalized_model = as_v2(model, report["source_revision"])
        elif target == "spike/v1":
            if isinstance(model, SpiDeRV2):
                losses = _projection_losses(model)
                projected = model.to_v1()
                losses.extend(_roundtrip_projection_losses(model, projected))
                projection.update({"lossy": bool(losses), "losses": losses})
                if require_lossless and losses:
                    validation_issues = list(report["issues"])
                    validation_issues.append(issue(
                        "spider.lossy_projection",
                        "Legacy-worker projection would omit: " + ", ".join(losses) + ".",
                        "/", "error",
                    ))
                    return _response("normalize_spider", False, **{**report, "issues": validation_issues},
                                     normalized_document=None, normalized_revision=None, projection=projection)
                normalized_model = projected
            else:
                normalized_model = model
        else:
            validation_issues = list(report["issues"])
            validation_issues.append(issue("spider.unsupported_target_contract", f"Unsupported target contract {target!r}.", "/target_contract"))
            return _response("normalize_spider", False, **{**report, "issues": validation_issues},
                             normalized_document=None, normalized_revision=None, projection=projection)
        normalized = normalized_model.to_dict()
    except (TypeError, ValueError, KeyError) as exc:
        validation_issues = list(report["issues"])
        validation_issues.append(issue("spider.projection_failed", str(exc), "/"))
        return _response("normalize_spider", False, **{**report, "issues": validation_issues},
                         normalized_document=None, normalized_revision=None, projection=projection)
    return _response(
        "normalize_spider", True, **report, normalized_document=normalized,
        normalized_revision=content_digest(normalized), projection=projection,
    )


def document_for_legacy_worker(document: Any, *, max_issues: int = 200) -> dict[str, Any]:
    """Return a v1 document only when typed-v2 projection is valid and lossless."""
    normalized = normalize_document(
        document, target_contract="spike/v1", max_issues=max_issues, require_lossless=True,
    )
    return {
        "ok": normalized["ok"],
        "document": normalized["normalized_document"],
        "report": {
            key: normalized.get(key) for key in (
                "document_revision", "normalized_revision", "source_revision",
                "source_revision_kind", "projection", "issues", "issues_truncated",
            )
        },
    }


def _capabilities() -> dict[str, Any]:
    return _response(
        "spider_capabilities", True,
        api_contract="spider/api/v1",
        supported_contracts=["spike/v1", "spike/design-ir/v2"],
        methods=list(METHODS),
        features=[
            "bounded_inline_validation", "deterministic_normalization", "source_revision_evidence",
            "canonical_entity_query", "reference_identity", "paginated_revision_diff",
            "lossy_projection_disclosure",
        ],
        canonical_units={"length": "mm", "frame_handedness": "right"},
        entity_types=list(ENTITY_TYPES),
        limits={"document_bytes": 8 * 1024 * 1024, "entities": 100_000, "page_size": 500, "issues": 500},
        mutation=False,
    )


def _params_error(method: str, message: str, path: str = "/params") -> dict[str, Any]:
    return _response(method, False, issues=[issue("spider.invalid_params", message, path)], issues_truncated=False)


def _check_params(method: str, params: Any, allowed: set[str], required: set[str]) -> dict[str, Any] | None:
    if not isinstance(params, Mapping):
        return _params_error(method, "params must be an object.")
    if any(not isinstance(key, str) for key in params):
        return _params_error(method, "parameter names must be strings.")
    unknown = sorted(set(params) - allowed)
    missing = sorted(required - set(params))
    if unknown:
        return _params_error(method, f"Unknown parameter(s): {', '.join(unknown)}.")
    if missing:
        return _params_error(method, f"Missing parameter(s): {', '.join(missing)}.")
    return None


def _page(params: Mapping[str, Any], method: str) -> tuple[int, int] | dict[str, Any]:
    offset = params.get("offset", 0)
    limit = params.get("limit", 100)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        return _params_error(method, "offset must be a non-negative integer.", "/params/offset")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        return _params_error(method, "limit must be an integer from 1 through 500.", "/params/limit")
    return offset, limit


def _types(params: Mapping[str, Any], method: str) -> tuple[str, ...] | dict[str, Any]:
    raw = params.get("entity_types", list(ENTITY_TYPES))
    if (not isinstance(raw, list) or not raw or any(not isinstance(item, str) for item in raw)
            or len(raw) != len(set(raw)) or any(item not in ENTITY_TYPES for item in raw)):
        return _params_error(method, "entity_types must be a non-empty unique array of supported entity types.", "/params/entity_types")
    return tuple(item for item in ENTITY_TYPES if item in raw)


def _references(entity_type: str, entity: Mapping[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for field_name, target, many in V2_REFS.get(entity_type, ()):
        values = entity.get(field_name, []) if many else [entity.get(field_name)]
        if isinstance(values, list):
            refs.extend(
                {"field": field_name, "entity_type": target, "id": value}
                for value in values if isinstance(value, str) and value
            )
    if entity_type == "drills" and entity.get("owner_kind") in {"pad", "via"} and entity.get("owner_id"):
        refs.append({"field": "owner_id", "entity_type": f"{entity['owner_kind']}s", "id": str(entity["owner_id"])})
    return sorted(refs, key=lambda item: (item["field"], item["entity_type"], item["id"]))


def _query(params: Mapping[str, Any]) -> dict[str, Any]:
    method = "query_spider"
    paging = _page(params, method)
    types = _types(params, method)
    if isinstance(paging, dict):
        return paging
    if isinstance(types, dict):
        return types
    for key in ("ids", "source_ids"):
        value = params.get(key, [])
        if (not isinstance(value, list) or len(value) > 256
                or any(not isinstance(item, str) or not item for item in value)
                or len(value) != len(set(value))):
            return _params_error(method, f"{key} must be a unique array of at most 256 non-empty strings.", f"/params/{key}")
    name_contains = params.get("name_contains", "")
    if not isinstance(name_contains, str) or len(name_contains) > 256:
        return _params_error(method, "name_contains must be a string of at most 256 characters.", "/params/name_contains")
    model, report = validate_document(params["document"])
    if model is None:
        return _response(method, False, **report, entities=[], page={"offset": paging[0], "limit": paging[1], "total": 0, "next_offset": None})
    expected = params.get("expected_revision")
    if expected is not None and (
        not isinstance(expected, str) or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        return _params_error(method, "expected_revision must be 64 lowercase hexadecimal characters.", "/params/expected_revision")
    if expected is not None and expected != report["document_revision"]:
        report["issues"].append(issue("spider.revision_conflict", "expected_revision does not match the supplied document.", "/expected_revision"))
        return _response(method, False, **report, entities=[], page={"offset": paging[0], "limit": paging[1], "total": 0, "next_offset": None})
    try:
        v2 = as_v2(model, report["source_revision"] or report["document_revision"])
    except (TypeError, ValueError, KeyError) as exc:
        report["issues"].append(issue("spider.normalization_failed", str(exc), "/"))
        return _response(method, False, **report, entities=[], page={"offset": paging[0], "limit": paging[1], "total": 0, "next_offset": None})
    payload = v2.to_dict()
    ids, source_ids = set(params.get("ids", [])), set(params.get("source_ids", []))
    needle = name_contains.casefold()
    matches: list[dict[str, Any]] = []
    for entity_type in types:
        for entity in payload.get(entity_type, []):
            if ids and entity.get("id") not in ids:
                continue
            if source_ids and entity.get("source_id") not in source_ids:
                continue
            if needle and needle not in str(entity.get("name", "")).casefold():
                continue
            matches.append({
                "entity_type": entity_type, "id": entity.get("id", ""),
                "source_id": entity.get("source_id", ""), "name": entity.get("name", ""),
                "references": _references(entity_type, entity), "entity": entity,
            })
    matches.sort(key=lambda item: (ENTITY_TYPES.index(item["entity_type"]), item["id"], item["source_id"]))
    offset, limit = paging
    page = matches[offset:offset + limit]
    return _response(
        method, True, **report, query_contract="spike/design-ir/v2",
        migration_applied=report["document_contract"] != "spike/design-ir/v2", entities=page,
        frame=asdict(v2.frame), canonical_units={"length": "mm", "frame_handedness": "right"},
        page={"offset": offset, "limit": limit, "total": len(matches),
              "next_offset": offset + limit if offset + limit < len(matches) else None},
    )


def _identity_rows(v2: SpiDeRV2, types: tuple[str, ...]) -> dict[tuple[str, str], dict[str, Any]]:
    payload = v2.to_dict()
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for entity_type in types:
        entities = payload.get(entity_type, [])
        source_counts: dict[str, int] = {}
        for entity in entities:
            source_id = entity.get("source_id", "")
            if source_id:
                source_counts[source_id] = source_counts.get(source_id, 0) + 1
        for entity in entities:
            source_id = entity.get("source_id", "")
            identity = f"source:{source_id}" if source_id and source_counts[source_id] == 1 else f"canonical:{entity['id']}"
            rows[(entity_type, identity)] = entity
    return rows


def _changed_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _compare(params: Mapping[str, Any]) -> dict[str, Any]:
    method = "compare_spider"
    paging = _page(params, method)
    types = _types(params, method)
    if isinstance(paging, dict):
        return paging
    if isinstance(types, dict):
        return types
    before_model, before_report = validate_document(params["before"])
    after_model, after_report = validate_document(params["after"])
    combined_issues = [
        {**value, "path": "/before" + value.get("path", "")} for value in before_report["issues"]
    ] + [
        {**value, "path": "/after" + value.get("path", "")} for value in after_report["issues"]
    ]
    revisions = {
        "before_document": before_report.get("document_revision"), "after_document": after_report.get("document_revision"),
        "before_source": before_report.get("source_revision"), "after_source": after_report.get("source_revision"),
    }
    if before_model is None or after_model is None:
        return _response(method, False, issues=combined_issues, issues_truncated=before_report.get("issues_truncated", False) or after_report.get("issues_truncated", False), revisions=revisions, changes=[])
    try:
        before_v2 = as_v2(before_model, before_report["source_revision"] or before_report["document_revision"])
        after_v2 = as_v2(after_model, after_report["source_revision"] or after_report["document_revision"])
    except (TypeError, ValueError, KeyError) as exc:
        combined_issues.append(issue("spider.normalization_failed", str(exc), "/"))
        return _response(method, False, issues=combined_issues, issues_truncated=False, revisions=revisions, changes=[])
    before_rows, after_rows = _identity_rows(before_v2, types), _identity_rows(after_v2, types)
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before_rows) | set(after_rows)):
        before, after = before_rows.get(key), after_rows.get(key)
        entity_type, identity = key
        if before is None:
            change = "added"
        elif after is None:
            change = "removed"
        elif before == after:
            continue
        else:
            change = "changed"
        changes.append({
            "change": change, "entity_type": entity_type, "identity": identity,
            "source_id": (after or before or {}).get("source_id", ""),
            "before_id": before.get("id") if before else None,
            "after_id": after.get("id") if after else None,
            "changed_fields": _changed_fields(before or {}, after or {}) if change == "changed" else [],
        })
    offset, limit = paging
    before_frame, after_frame = asdict(before_v2.frame), asdict(after_v2.frame)
    before_source, after_source = asdict(before_v2.source), asdict(after_v2.source)
    return _response(
        method, True, issues=combined_issues, issues_truncated=False, revisions=revisions,
        drift={"source": before_source != after_source, "frame": before_frame != after_frame,
               "before_source": before_source, "after_source": after_source,
               "before_frame": before_frame, "after_frame": after_frame},
        projection={"comparison_contract": "spike/design-ir/v2", "lossy": False,
                    "before_migrated": before_report["document_contract"] != "spike/design-ir/v2",
                    "after_migrated": after_report["document_contract"] != "spike/design-ir/v2"},
        changes=changes[offset:offset + limit],
        page={"offset": offset, "limit": limit, "total": len(changes),
              "next_offset": offset + limit if offset + limit < len(changes) else None},
    )


def _handle_spider_request(method: str, params: Any) -> dict[str, Any] | None:
    """Dispatch one interoperability operation; return None for unknown methods."""
    if method not in METHODS:
        return None
    if method == "spider_capabilities":
        error = _check_params(method, params, set(), set())
        return error or _capabilities()
    contracts = {
        "validate_spider": ({"document", "max_issues"}, {"document"}),
        "normalize_spider": ({"document", "target_contract", "max_issues"}, {"document"}),
        "query_spider": ({"document", "entity_types", "ids", "source_ids", "name_contains", "offset", "limit", "expected_revision"}, {"document"}),
        "compare_spider": ({"before", "after", "entity_types", "offset", "limit"}, {"before", "after"}),
    }
    error = _check_params(method, params, *contracts[method])
    if error:
        return error
    max_issues = params.get("max_issues", 200)
    if method in {"validate_spider", "normalize_spider"} and (
        isinstance(max_issues, bool) or not isinstance(max_issues, int) or not 1 <= max_issues <= 500
    ):
        return _params_error(method, "max_issues must be an integer from 1 through 500.", "/params/max_issues")
    if method == "validate_spider":
        model, report = validate_document(params["document"], max_issues=max_issues)
        return _response(method, model is not None, **report)
    if method == "normalize_spider":
        return normalize_document(params["document"], target_contract=params.get("target_contract"), max_issues=max_issues)
    if method == "query_spider":
        return _query(params)
    return _compare(params)


def handle_spider_request(method: str, params: Any) -> dict[str, Any] | None:
    """Bound malformed caller data so supported operations always return diagnostics."""
    if method not in METHODS:
        return None
    try:
        return _handle_spider_request(method, params)
    except (TypeError, ValueError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
        return _response(
            method, False,
            issues=[issue("spider.malformed_request", str(exc), "/")],
            issues_truncated=False,
        )


__all__ = ["document_for_legacy_worker", "handle_spider_request", "normalize_document"]
