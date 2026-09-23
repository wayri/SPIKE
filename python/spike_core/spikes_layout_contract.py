# SPDX-License-Identifier: MIT
"""Strict bounded contract primitives shared by SPIKES layout orchestration."""

from __future__ import annotations

import copy
import math
import re
from typing import Any, Dict


MAX_REQUIREMENTS = 1024
MAX_PHYSICS_EVALUATIONS = 64
MAX_ENTITY_IDS = 4096
MAX_EXTERNAL_RESULTS = 1024

_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9._-]{1,127}$", flags=re.ASCII)
_METRIC_RE = re.compile(r"^[a-z][a-z0-9._-]{1,127}$", flags=re.ASCII)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_RESULT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$", flags=re.ASCII)
VALIDATION_STATES = {
    "qualified", "validated", "reference_validated", "verification_only", "cad_drc",
    "experimental", "approximate", "unvalidated", "unsupported",
}
HARD_ACCEPTED_VALIDATION_STATES = {
    "qualified", "validated", "reference_validated", "verification_only", "cad_drc",
}


class SpikesLayoutAdapterError(ValueError):
    """A layout request/result failed a stable public boundary check."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise SpikesLayoutAdapterError(code, message)


def strict_object(value: Any, allowed: set[str], required: set[str], label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        fail("SPIKE-LAYOUT-CONTRACT-0001", f"{label} must be an object")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        fail("SPIKE-LAYOUT-CONTRACT-0001", f"{label} has unknown or missing fields")
    return value


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        fail("SPIKE-LAYOUT-CONTRACT-0002", f"{label} is not a bounded identifier")
    return value


def is_digest(value: Any) -> bool:
    """Return whether *value* is a canonical lowercase SHA-256 digest."""
    return isinstance(value, str) and _DIGEST_RE.fullmatch(value) is not None


def finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        fail("SPIKE-LAYOUT-CONTRACT-0003", f"{label} must be finite")
    return float(value)


def artifact(value: Any, label: str, maximum: int) -> Dict[str, Any]:
    obj = strict_object(value, {"path", "sha256", "bytes", "contract"}, {"path", "sha256", "bytes", "contract"}, label)
    path = obj["path"]
    normalized = path.replace("\\", "/") if isinstance(path, str) else ""
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in ("", ".", "..") for part in parts)
    ):
        fail("SPIKE-LAYOUT-CONTRACT-0004", f"{label}.path must be normalized and job-relative")
    digest = obj["sha256"]
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        fail("SPIKE-LAYOUT-CONTRACT-0004", f"{label}.sha256 must be lowercase SHA-256")
    size = obj["bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= maximum:
        fail("SPIKE-LAYOUT-CONTRACT-0004", f"{label}.bytes exceeds its bound")
    contract = obj["contract"]
    if not isinstance(contract, str) or not contract or len(contract) > 128:
        fail("SPIKE-LAYOUT-CONTRACT-0004", f"{label}.contract is invalid")
    return {"path": normalized, "sha256": digest, "bytes": size, "contract": contract}


def dimension(value: Any) -> list[Any]:
    if not isinstance(value, list) or len(value) != 7:
        fail("SPIKE-LAYOUT-CONTRACT-0005", "dimension must contain seven SI exponents")
    normalized: list[Any] = []
    for exponent in value:
        if isinstance(exponent, bool):
            fail("SPIKE-LAYOUT-CONTRACT-0005", "dimension exponent is invalid")
        if isinstance(exponent, int) and -1024 <= exponent <= 1024:
            normalized.append(exponent)
        elif (
            isinstance(exponent, list)
            and len(exponent) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) for item in exponent)
            and -1024 <= exponent[0] <= 1024
            and 1 <= exponent[1] <= 1024
        ):
            normalized.append([exponent[0], exponent[1]])
        else:
            fail("SPIKE-LAYOUT-CONTRACT-0005", "dimension exponent is invalid")
    return normalized


def validate_scope(value: Any) -> Dict[str, Any]:
    obj = strict_object(value, {"frame", "entity_ids"}, {"frame", "entity_ids"}, "requirement.scope")
    frame = obj["frame"]
    if not isinstance(frame, str) or not frame or len(frame) > 128:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement scope frame is invalid")
    entities = obj["entity_ids"]
    if not isinstance(entities, list) or len(entities) > MAX_ENTITY_IDS:
        fail("SPIKE-LAYOUT-CONTRACT-0003", "requirement entity_ids exceed the bound")
    if any(not isinstance(item, str) or not item or len(item) > 256 for item in entities) or len(set(entities)) != len(entities):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement entity_ids are invalid or duplicate")
    return {"frame": frame, "entity_ids": list(entities)}


def validate_requirement(value: Any) -> Dict[str, Any]:
    allowed = {
        "id", "evaluator", "kind", "metric_id", "result_key", "relation", "dimension",
        "lower_si", "upper_si", "target_si", "absolute_tolerance_si", "weight",
        "normalization_si", "scope",
    }
    required = {"id", "evaluator", "kind", "metric_id", "relation", "dimension", "scope"}
    obj = strict_object(value, allowed, required, "requirement")
    result: Dict[str, Any] = {
        "id": identifier(obj["id"], "requirement.id"),
        "evaluator": obj["evaluator"],
        "kind": obj["kind"],
        "metric_id": obj["metric_id"],
        "relation": obj["relation"],
        "dimension": dimension(obj["dimension"]),
        "scope": validate_scope(obj["scope"]),
    }
    if result["evaluator"] not in ("cad_drc", "native_solver", "custom"):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement evaluator is unsupported")
    if result["kind"] not in ("hard_constraint", "soft_constraint", "objective"):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement kind is unsupported")
    if not isinstance(result["metric_id"], str) or _METRIC_RE.fullmatch(result["metric_id"]) is None:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement metric_id is invalid")
    if result["relation"] not in ("le", "ge", "between", "target", "minimize", "maximize"):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement relation is unsupported")
    for field in ("lower_si", "upper_si", "target_si", "absolute_tolerance_si", "weight", "normalization_si"):
        if field in obj:
            result[field] = finite(obj[field], f"requirement.{field}")
    if "absolute_tolerance_si" in result and result["absolute_tolerance_si"] < 0:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "absolute tolerance must be non-negative")
    if "weight" in result and result["weight"] <= 0:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "objective weight must be positive")
    if "normalization_si" in result and result["normalization_si"] <= 0:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "objective normalization_si must be positive")
    relation = result["relation"]
    if relation == "le" and "upper_si" not in result:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "le requires upper_si")
    if relation == "ge" and "lower_si" not in result:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "ge requires lower_si")
    if relation == "between" and not {"lower_si", "upper_si"} <= set(result):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "between requires lower_si and upper_si")
    if "lower_si" in result and "upper_si" in result and result["lower_si"] > result["upper_si"]:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "requirement bounds are contradictory")
    if relation == "target" and not {"target_si", "absolute_tolerance_si"} <= set(result):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "target requires target_si and absolute_tolerance_si")
    if relation in ("minimize", "maximize") and result["kind"] != "objective":
        fail("SPIKE-LAYOUT-CONTRACT-0006", "minimize/maximize are objective-only")
    if result["kind"] == "objective" and "weight" not in result:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "objective requires a positive weight")
    if "normalization_si" in result and result["kind"] != "objective":
        fail("SPIKE-LAYOUT-CONTRACT-0006", "normalization_si is objective-only")
    if result["evaluator"] == "native_solver":
        key = obj.get("result_key")
        if not isinstance(key, str) or _RESULT_KEY_RE.fullmatch(key) is None:
            fail("SPIKE-LAYOUT-CONTRACT-0006", "native requirement requires a bounded result_key")
        result["result_key"] = key
    elif "result_key" in obj:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "result_key is native-solver-only")
    return result


def validate_study(value: Any) -> Dict[str, Any]:
    obj = strict_object(value, {"type", "integrator", "time_step", "steps"}, {"type"}, "physics_evaluation.study")
    if obj["type"] not in ("stationary", "transient"):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "study type is unsupported")
    if "integrator" in obj and obj["integrator"] not in ("backward_euler", "bdf2"):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "study integrator is unsupported")
    if "time_step" in obj and finite(obj["time_step"], "study.time_step") <= 0:
        fail("SPIKE-LAYOUT-CONTRACT-0006", "study time_step must be positive")
    if "steps" in obj and (isinstance(obj["steps"], bool) or not isinstance(obj["steps"], int) or not 1 <= obj["steps"] <= 1_000_000):
        fail("SPIKE-LAYOUT-CONTRACT-0006", "study steps exceed the bound")
    return copy.deepcopy(obj)


def validate_resources(value: Any) -> Dict[str, Any]:
    obj = strict_object(value, {"max_memory_bytes", "max_wall_time_s", "ranks", "threads"}, {"max_memory_bytes", "max_wall_time_s", "ranks", "threads"}, "resources")
    limits = (("max_memory_bytes", 16 * 1024 * 1024, 1 << 50), ("ranks", 1, 65536), ("threads", 1, 4096))
    result: Dict[str, Any] = {}
    for field, low, high in limits:
        item = obj[field]
        if isinstance(item, bool) or not isinstance(item, int) or not low <= item <= high:
            fail("SPIKE-LAYOUT-CONTRACT-0003", f"resources.{field} exceeds the bound")
        result[field] = item
    wall = finite(obj["max_wall_time_s"], "resources.max_wall_time_s")
    if not 0 < wall <= 604800:
        fail("SPIKE-LAYOUT-CONTRACT-0003", "resources.max_wall_time_s exceeds the bound")
    result["max_wall_time_s"] = wall
    return result


__all__ = [
    "HARD_ACCEPTED_VALIDATION_STATES", "MAX_ENTITY_IDS", "MAX_EXTERNAL_RESULTS",
    "MAX_PHYSICS_EVALUATIONS", "MAX_REQUIREMENTS", "SpikesLayoutAdapterError",
    "VALIDATION_STATES", "artifact", "fail", "finite", "identifier", "is_digest", "strict_object",
    "validate_requirement", "validate_resources", "validate_study",
]
