"""Typed model-index validation for portable SPIKE project packages."""

from __future__ import annotations

import math
import re
from dataclasses import asdict
from typing import Any, Dict, Mapping

from .design_ir_v2_schema import ModelReference


MODEL_INDEX_CONTRACT_V1 = "spike/model-index/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_MODEL_URI = re.compile(
    r"^package:models/artifacts/(?P<name>[A-Za-z0-9][A-Za-z0-9._+-]*)$"
)
_EXTENSION_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_MODEL_SUFFIXES = {
    "step": {".step", ".stp"},
    "gltf": {".gltf"},
    "glb": {".glb"},
}


class ModelIndexError(ValueError):
    """Raised when model metadata or its package artifact is inconsistent."""


def _package_member_for(model_id: str, uri: Any, model_type: str) -> str:
    if not isinstance(uri, str):
        raise ModelIndexError(f"Model {model_id} package URI must be a string.")
    match = _PACKAGE_MODEL_URI.fullmatch(uri)
    if match is None:
        raise ModelIndexError(
            f"Model {model_id} must reference a safe embedded package model artifact."
        )
    name = match.group("name")
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if suffix not in _MODEL_SUFFIXES[model_type]:
        raise ModelIndexError(
            f"Model {model_id} artifact extension does not match model_type {model_type}."
        )
    return uri.removeprefix("package:")


def _canonical_transform(model_id: str, raw: Any) -> list[float]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)) or len(raw) not in {0, 16}:
        raise ModelIndexError(f"Model {model_id} transform must be empty or contain 16 values.")
    values: list[float] = []
    for value in raw:
        if isinstance(value, bool):
            raise ModelIndexError(f"Model {model_id} transform must contain finite numeric values.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ModelIndexError(
                f"Model {model_id} transform must contain finite numeric values."
            ) from exc
        if not math.isfinite(number):
            raise ModelIndexError(f"Model {model_id} transform must contain finite numeric values.")
        values.append(number)
    return values


def _canonical_extensions(model_id: str, raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ModelIndexError(f"Model {model_id} extensions must be an object.")
    extensions: Dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or _EXTENSION_NAME.fullmatch(key) is None:
            raise ModelIndexError(f"Model {model_id} contains an invalid extension name.")
        extensions[key] = value
    return extensions


def canonicalize_model_index(raw: Any) -> Dict[str, Any]:
    """Return a canonical model index while preserving unknown top-level data."""

    if raw is None or raw == {}:
        return {}
    if not isinstance(raw, Mapping):
        raise ModelIndexError("The model index must be an object.")
    if raw.get("contract") != MODEL_INDEX_CONTRACT_V1:
        raise ModelIndexError("The model index contract is unsupported or missing.")
    models = raw.get("models")
    if not isinstance(models, list):
        raise ModelIndexError("The model index models field must be an array.")

    canonical_models = []
    identities: set[str] = set()
    artifact_claims: Dict[str, tuple[str, str]] = {}
    fields = set(ModelReference.__dataclass_fields__)
    for position, item in enumerate(models):
        if not isinstance(item, Mapping):
            raise ModelIndexError(f"Model index entry {position} must be an object.")
        unknown = {key: value for key, value in item.items() if key not in fields}
        try:
            model = ModelReference(**{key: value for key, value in item.items() if key in fields})
        except TypeError as exc:
            raise ModelIndexError(f"Model index entry {position} is invalid: {exc}") from exc
        if not isinstance(model.id, str) or not model.id.strip() or model.id != model.id.strip() or model.id in identities:
            raise ModelIndexError(f"Model index entry {position} has a missing or duplicate identity.")
        if not isinstance(model.source_id, str) or not isinstance(model.name, str):
            raise ModelIndexError(f"Model {model.id} source_id and name must be strings.")
        if not isinstance(model.model_type, str) or model.model_type not in _MODEL_SUFFIXES:
            raise ModelIndexError(
                f"Model {model.id} model_type must be one of: {', '.join(sorted(_MODEL_SUFFIXES))}."
            )
        if not isinstance(model.digest, str):
            raise ModelIndexError(f"Model {model.id} does not declare a valid SHA-256 digest.")
        digest = model.digest.strip().lower()
        if not _SHA256.fullmatch(digest):
            raise ModelIndexError(f"Model {model.id} does not declare a valid SHA-256 digest.")
        member_path = _package_member_for(model.id, model.uri, model.model_type)
        model.transform = _canonical_transform(model.id, model.transform)
        model.extensions = _canonical_extensions(model.id, model.extensions)
        existing_claim = artifact_claims.get(member_path)
        claim = (digest, model.model_type)
        if existing_claim is not None and existing_claim != claim:
            raise ModelIndexError(
                f"Shared model artifact has inconsistent digest or model_type claims: {member_path}"
            )
        identities.add(model.id)
        artifact_claims[member_path] = claim
        model.digest = digest
        canonical_models.append({**asdict(model), **unknown})

    return {**dict(raw), "contract": MODEL_INDEX_CONTRACT_V1, "models": canonical_models}


def validate_model_artifacts(model_index: Mapping[str, Any], member_digests: Mapping[str, str]) -> None:
    """Require each indexed model artifact to exist and match its declared digest."""

    if not model_index:
        return
    for model in model_index.get("models", []):
        member_path = str(model["uri"]).removeprefix("package:")
        actual_digest = member_digests.get(member_path)
        if actual_digest is None:
            raise ModelIndexError(f"Model artifact is missing from the package: {member_path}")
        if actual_digest.lower() != str(model["digest"]).lower():
            raise ModelIndexError(f"Model artifact digest does not match the model index: {member_path}")
