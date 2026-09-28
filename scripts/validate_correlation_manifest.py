#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Validate a hash-bound correlation evidence manifest.

Exit status 0 means that metadata is complete for all three evidence classes.
Exit status 2 means the manifest is valid but declares missing or unqualified
evidence.  Exit status 1 means the manifest or its file identities are invalid.
This tool validates evidence bookkeeping; it does not perform numerical
correlation or grant solver signoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path, PurePosixPath
from typing import Any


MANIFEST_CONTRACT = "spike/correlation-evidence-manifest/v1"
REPORT_CONTRACT = "spike/correlation-evidence-validation/v1"
EVIDENCE_KINDS = {"analytical", "independent_solver", "measured"}
EVIDENCE_STATUSES = {"qualified", "unqualified", "missing"}
SHA256_LENGTH = 64
MAX_MANIFEST_BYTES = 8 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON field: {key}")
        value[key] = item
    return value


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _exact_keys(value: Any, expected: set[str], location: str, issues: list[str]) -> bool:
    if not isinstance(value, dict):
        issues.append(f"invalid_type:{location}:expected_object")
        return False
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    issues.extend(f"missing_field:{location}.{key}" for key in missing)
    issues.extend(f"unknown_field:{location}.{key}" for key in extra)
    return not missing and not extra


def _validate_quantity(value: Any, location: str, qualified: bool, measured: bool,
                       issues: list[str]) -> None:
    keys = {"name", "unit", "uncertainty", "tolerance"}
    if not _exact_keys(value, keys, location, issues):
        return
    if not _is_nonempty_string(value["name"]):
        issues.append(f"invalid_value:{location}.name")
    if not _is_nonempty_string(value["unit"]):
        issues.append(f"invalid_value:{location}.unit")

    tolerance = value["tolerance"]
    if tolerance is not None:
        if _exact_keys(tolerance, {"absolute", "relative"}, f"{location}.tolerance", issues):
            values = (tolerance["absolute"], tolerance["relative"])
            if all(item is None for item in values):
                issues.append(f"invalid_value:{location}.tolerance:empty")
            for field, item in zip(("absolute", "relative"), values):
                if item is not None and (not _is_number(item) or item < 0):
                    issues.append(f"invalid_value:{location}.tolerance.{field}")
    elif qualified:
        issues.append(f"missing_qualification_data:{location}.tolerance")

    uncertainty = value["uncertainty"]
    if uncertainty is not None:
        uncertainty_location = f"{location}.uncertainty"
        if _exact_keys(uncertainty, {"absolute", "unit", "confidence"},
                       uncertainty_location, issues):
            if not _is_number(uncertainty["absolute"]) or uncertainty["absolute"] < 0:
                issues.append(f"invalid_value:{uncertainty_location}.absolute")
            if uncertainty["unit"] != value["unit"]:
                issues.append(f"unit_mismatch:{uncertainty_location}.unit")
            confidence = uncertainty["confidence"]
            if not _is_number(confidence) or not 0 < confidence <= 1:
                issues.append(f"invalid_value:{uncertainty_location}.confidence")
    elif qualified and measured:
        issues.append(f"missing_qualification_data:{location}.uncertainty")


def _validate_solver(value: Any, location: str, issues: list[str]) -> None:
    keys = {"name", "version", "provenance", "artifact_sha256"}
    if not _exact_keys(value, keys, location, issues):
        return
    for field in ("name", "version", "provenance"):
        if not _is_nonempty_string(value[field]):
            issues.append(f"invalid_value:{location}.{field}")
    if not _is_sha256(value["artifact_sha256"]):
        issues.append(f"invalid_value:{location}.artifact_sha256")


def _safe_input_path(root: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        return None
    candidate = PurePosixPath(relative)
    if (
        candidate.is_absolute()
        or candidate.as_posix() != relative
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        return None
    resolved = (root / Path(*candidate.parts)).resolve()
    return resolved if resolved.is_relative_to(root) else None


def _validate_dataset(value: Any, index: int, root: Path,
                      issues: list[str]) -> tuple[str | None, str | None, str | None]:
    location = f"datasets[{index}]"
    keys = {"id", "kind", "status", "status_reason", "input", "quantities", "provenance", "solver"}
    if not _exact_keys(value, keys, location, issues):
        return None, None, None

    dataset_id = value["id"] if _is_nonempty_string(value["id"]) else None
    if dataset_id is None:
        issues.append(f"invalid_value:{location}.id")
    kind_value = value["kind"]
    kind = kind_value if isinstance(kind_value, str) and kind_value in EVIDENCE_KINDS else None
    if kind is None:
        issues.append(f"invalid_value:{location}.kind")
    status_value = value["status"]
    status = (
        status_value
        if isinstance(status_value, str) and status_value in EVIDENCE_STATUSES
        else None
    )
    if status is None:
        issues.append(f"invalid_value:{location}.status")

    reason = value["status_reason"]
    if status == "qualified" and reason is not None:
        issues.append(f"invalid_value:{location}.status_reason:qualified_requires_null")
    if status in {"unqualified", "missing"} and not _is_nonempty_string(reason):
        issues.append(f"invalid_value:{location}.status_reason:reason_required")

    input_value = value["input"]
    if status == "missing":
        if input_value is not None:
            issues.append(f"invalid_value:{location}.input:missing_requires_null")
    elif input_value is None:
        issues.append(f"missing_field:{location}.input")
    elif _exact_keys(input_value, {"path", "sha256"}, f"{location}.input", issues):
        input_path = _safe_input_path(root, input_value["path"])
        if input_path is None:
            issues.append(f"unsafe_path:{location}.input.path")
        elif not input_path.is_file():
            issues.append(f"input_missing:{dataset_id or index}:{input_value['path']}")
        elif not _is_sha256(input_value["sha256"]):
            issues.append(f"invalid_value:{location}.input.sha256")
        elif sha256_file(input_path) != input_value["sha256"]:
            issues.append(f"sha256_mismatch:{dataset_id or index}:{input_value['path']}")

    provenance = value["provenance"]
    if status == "missing":
        if provenance is not None:
            issues.append(f"invalid_value:{location}.provenance:missing_requires_null")
    elif _exact_keys(provenance, {"description", "reference"}, f"{location}.provenance", issues):
        for field in ("description", "reference"):
            if not _is_nonempty_string(provenance[field]):
                issues.append(f"invalid_value:{location}.provenance.{field}")

    quantities = value["quantities"]
    if not isinstance(quantities, list) or not quantities:
        issues.append(f"invalid_value:{location}.quantities")
    else:
        quantity_names: set[str] = set()
        for quantity_index, quantity in enumerate(quantities):
            quantity_location = f"{location}.quantities[{quantity_index}]"
            _validate_quantity(quantity, quantity_location, status == "qualified", kind == "measured", issues)
            if isinstance(quantity, dict) and _is_nonempty_string(quantity.get("name")):
                if quantity["name"] in quantity_names:
                    issues.append(f"duplicate_quantity:{location}:{quantity['name']}")
                quantity_names.add(quantity["name"])

    solver = value["solver"]
    if kind == "independent_solver" and status != "missing":
        _validate_solver(solver, f"{location}.solver", issues)
    elif solver is not None:
        issues.append(f"invalid_value:{location}.solver:unexpected")

    return dataset_id, kind, status


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    """Return a structured, fail-closed validation report for *manifest_path*."""
    issues: list[str] = []
    summaries: list[dict[str, str | None]] = []
    manifest_id: str | None = None
    manifest_sha256: str | None = None
    try:
        path = manifest_path.resolve(strict=True)
        size = path.stat().st_size
        if size > MAX_MANIFEST_BYTES:
            issues.append(f"manifest_too_large:{size}:{MAX_MANIFEST_BYTES}")
            return _report("invalid", manifest_sha256, manifest_id, summaries, issues)
        manifest_sha256 = sha256_file(path)
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        issues.append(f"manifest_unreadable:{type(error).__name__}:{error}")
        return _report("invalid", manifest_sha256, manifest_id, summaries, issues)

    root_keys = {"contract", "manifest_id", "subject", "datasets"}
    if not _exact_keys(payload, root_keys, "manifest", issues):
        return _report("invalid", manifest_sha256, manifest_id, summaries, issues)
    if payload["contract"] != MANIFEST_CONTRACT:
        issues.append("invalid_value:manifest.contract")
    if _is_nonempty_string(payload["manifest_id"]):
        manifest_id = payload["manifest_id"]
    else:
        issues.append("invalid_value:manifest.manifest_id")
    if not _is_nonempty_string(payload["subject"]):
        issues.append("invalid_value:manifest.subject")

    datasets = payload["datasets"]
    if not isinstance(datasets, list):
        issues.append("invalid_type:manifest.datasets:expected_array")
    else:
        ids: set[str] = set()
        kinds: list[str] = []
        for index, dataset in enumerate(datasets):
            dataset_id, kind, status = _validate_dataset(dataset, index, path.parent, issues)
            summaries.append({"id": dataset_id, "kind": kind, "status": status})
            if dataset_id is not None:
                if dataset_id in ids:
                    issues.append(f"duplicate_dataset_id:{dataset_id}")
                ids.add(dataset_id)
            if kind is not None:
                kinds.append(kind)
        missing_kinds = sorted(EVIDENCE_KINDS - set(kinds))
        duplicate_kinds = sorted(kind for kind in EVIDENCE_KINDS if kinds.count(kind) > 1)
        issues.extend(f"missing_evidence_class:{kind}" for kind in missing_kinds)
        issues.extend(f"duplicate_evidence_class:{kind}" for kind in duplicate_kinds)

    if issues:
        return _report("invalid", manifest_sha256, manifest_id, summaries, issues)
    blockers = [
        f"evidence_{item['status']}:{item['kind']}:{item['id']}"
        for item in summaries if item["status"] != "qualified"
    ]
    return _report("evidence_incomplete" if blockers else "metadata_complete", manifest_sha256,
                   manifest_id, summaries, blockers)


def _report(status: str, manifest_sha256: str | None, manifest_id: str | None,
            datasets: list[dict[str, str | None]], issues: list[str]) -> dict[str, Any]:
    return {
        "contract": REPORT_CONTRACT,
        "status": status,
        "scope": "evidence integrity and qualification metadata only; not numerical signoff",
        "numerical_correlation_performed": False,
        "solver_signoff": False,
        "manifest_sha256": manifest_sha256,
        "manifest_id": manifest_id,
        "datasets": datasets,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to a v1 correlation evidence manifest")
    parser.add_argument("--output", type=Path, help="Write the validation report instead of stdout")
    arguments = parser.parse_args(argv)
    report = validate_manifest(arguments.manifest)
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(encoded)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    return {"metadata_complete": 0, "invalid": 1, "evidence_incomplete": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
