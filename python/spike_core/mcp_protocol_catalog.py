# SPDX-License-Identifier: Apache-2.0
"""Deterministic, catalog-bound cursors for bounded MCP listing responses."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .mcp_protocol import ProtocolError


class CatalogPager:
    """Cursors are opaque hashes of namespace, catalog, page size and offset.

    They are positions, not authorization tokens. Only current page boundaries
    are accepted; mutations to any descriptor invalidate previous cursors.
    """

    def __init__(self, page_size: int = 128, max_items: int = 8192,
                 max_catalog_bytes: int = 8 * 1024 * 1024) -> None:
        if type(page_size) is not int or not 1 <= page_size <= 256:
            raise ValueError("Page size must be between 1 and 256")
        self.page_size = page_size
        self.max_items = max_items
        self.max_catalog_bytes = max_catalog_bytes

    def page(self, items: list[dict[str, Any]], params: dict[str, Any],
             namespace: str, key: str) -> dict[str, Any]:
        if not isinstance(params, dict) or set(params) - {"cursor", "_meta"}:
            raise ProtocolError("Invalid list parameters")
        cursor = params.get("cursor")
        if "cursor" in params and (not isinstance(cursor, str) or len(cursor) != 64):
            raise ProtocolError("Invalid or stale cursor; restart listing without a cursor")
        if namespace not in {"tools", "resources"} or key not in {"name", "uri"}:
            raise ValueError("Invalid internal catalog namespace")
        if len(items) > self.max_items:
            raise ProtocolError("Catalog exceeds item limit", -32603)
        if any(not isinstance(item, dict) or not isinstance(item.get(key), str) for item in items):
            raise ProtocolError("Invalid catalog descriptor", -32603)
        ordered = sorted(items, key=lambda item: item[key])
        if len({item[key] for item in ordered}) != len(ordered):
            raise ProtocolError("Duplicate catalog identifier", -32603)
        digest = hashlib.sha256()
        size = 0
        for item in ordered:
            encoded = json.dumps(item, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":")).encode("utf-8")
            size += len(encoded) + 1
            if size > self.max_catalog_bytes:
                raise ProtocolError("Catalog exceeds byte limit", -32603)
            digest.update(encoded + b"\n")
        revision = digest.hexdigest()

        def token(offset: int) -> str:
            binding = f"spike-mcp-v1:{namespace}:{revision}:{self.page_size}:{offset}"
            return hashlib.sha256(binding.encode("ascii")).hexdigest()

        offset = 0
        if cursor is not None:
            positions = {token(index): index for index in range(self.page_size, len(ordered), self.page_size)}
            if cursor not in positions:
                raise ProtocolError("Invalid or stale cursor; restart listing without a cursor")
            offset = positions[cursor]
        end = offset + self.page_size
        result = {namespace: ordered[offset:end]}
        if end < len(ordered):
            result["nextCursor"] = token(end)
        return result
