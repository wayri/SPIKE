# SPDX-License-Identifier: MIT
"""Bounded authenticated transport for large normalized design snapshots."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
import zlib

from .project_package import ProjectPackageError

NORMALIZED_SOURCE_WRAPPER = "spike/normalized-source-zlib/v1"
MAX_NORMALIZED_SOURCE_BYTES = 512 * 1024 * 1024


def encode_normalized_source(source_text: str, *, canonical_design_omitted: bool = False) -> dict:
    raw = source_text.encode("utf-8")
    return {"contract": NORMALIZED_SOURCE_WRAPPER, "encoding": "zlib+base64+utf8",
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "data": base64.b64encode(zlib.compress(raw, level=9)).decode("ascii"),
            **({"canonical_design_omitted": True} if canonical_design_omitted else {})}


def decode_normalized_source(value: Any) -> str:
    if isinstance(value, str):
        if value.lstrip().startswith("{"):
            try:
                candidate = json.loads(value)
            except json.JSONDecodeError:
                candidate = None
            if isinstance(candidate, dict) and candidate.get("contract") == NORMALIZED_SOURCE_WRAPPER:
                return decode_normalized_source(candidate)
        return value
    if (not isinstance(value, dict) or value.get("contract") != NORMALIZED_SOURCE_WRAPPER
            or value.get("encoding") != "zlib+base64+utf8"):
        raise ProjectPackageError("Invalid compressed normalized source wrapper.")
    expected = value.get("bytes")
    if not isinstance(expected, int) or expected < 0 or expected > MAX_NORMALIZED_SOURCE_BYTES:
        raise ProjectPackageError("Compressed normalized source byte count is invalid.")
    try:
        compressed = base64.b64decode(value["data"], validate=True)
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(compressed, expected + 1)
    except (KeyError, ValueError, zlib.error) as exc:
        raise ProjectPackageError("Compressed normalized source data is invalid.") from exc
    if len(raw) > expected or decompressor.unconsumed_tail:
        raise ProjectPackageError("Compressed normalized source exceeds its declared byte count.")
    try:
        raw += decompressor.flush(expected - len(raw) + 1)
    except zlib.error as exc:
        raise ProjectPackageError("Compressed normalized source data is invalid.") from exc
    if len(raw) > expected:
        raise ProjectPackageError("Compressed normalized source exceeds its declared byte count.")
    if not decompressor.eof or decompressor.unused_data:
        raise ProjectPackageError("Compressed normalized source has an incomplete or trailing stream.")
    if len(raw) != expected or hashlib.sha256(raw).hexdigest() != value.get("sha256"):
        raise ProjectPackageError("Compressed normalized source integrity check failed.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectPackageError("Compressed normalized source is not UTF-8.") from exc


def compact_normalized_source_for_open(value: Any) -> dict:
    """Omit the canonical copy already returned beside the projected project."""
    snapshot = json.loads(decode_normalized_source(value))
    if not isinstance(snapshot, dict) or snapshot.get("contract") != "spike/design-snapshot/v1":
        raise ProjectPackageError("Invalid normalized source snapshot.")
    snapshot.pop("canonical_design", None)
    return encode_normalized_source(
        json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        canonical_design_omitted=True,
    )
