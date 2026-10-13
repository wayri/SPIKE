# SPDX-License-Identifier: Apache-2.0
"""Read-only MCP resources confined to SPIKE's installed schema catalog."""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from .contract_catalog import installed_schema_catalog, schema_operation
from .mcp_protocol import ProtocolError
from .mcp_protocol_catalog import CatalogPager

SCHEMA_URI_PREFIX = "spike://schemas/"
MAX_SCHEMA_BYTES = 1024 * 1024
_SCHEMA_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.schema\.json\Z")


class ResourceDescriptor(TypedDict):
    uri: str
    name: str
    description: str
    mimeType: str
    _meta: dict[str, str]


class TextResourceContents(TypedDict):
    uri: str
    mimeType: str
    text: str


class ReadResourceResult(TypedDict):
    contents: list[TextResourceContents]


class SchemaResources:
    """Expose only exact, enumerated schema URIs; never interpret a file path."""

    def __init__(self, pager: CatalogPager | None = None) -> None:
        self.pager = pager or CatalogPager()

    @staticmethod
    def _names() -> list[str]:
        names = list(installed_schema_catalog())
        if (not isinstance(names, list) or len(names) > 8192
                or any(not isinstance(name, str) or len(name) > 255 or not _SCHEMA_NAME.fullmatch(name)
                       for name in names)):
            raise ProtocolError("Installed schema catalog is invalid or exceeds its limit", -32603)
        return sorted(names)

    def list(self, params: dict[str, Any]) -> dict[str, Any]:
        catalog = schema_operation("read", {})
        hashes = {item["name"]: item["sha256"] for item in catalog["descriptors"]}
        resources: list[ResourceDescriptor] = [{
            "uri": SCHEMA_URI_PREFIX + name, "name": name,
            "description": "Installed SPIKE contract schema; validation does not establish solver admission.",
            "mimeType": "application/schema+json",
            "_meta": {"org.spike/schemaSha256": hashes[name]},
        } for name in catalog["schemas"]]
        return self.pager.page(resources, params, "resources", "uri")

    def read(self, params: dict[str, Any]) -> ReadResourceResult:
        if not isinstance(params, dict) or set(params) - {"uri", "_meta"}:
            raise ProtocolError("Invalid resources/read parameters")
        uri = params.get("uri")
        if not isinstance(uri, str) or len(uri) > 512 or not uri.startswith(SCHEMA_URI_PREFIX):
            raise ProtocolError("Choose an exact URI from resources/list")
        name = uri[len(SCHEMA_URI_PREFIX):]
        if not _SCHEMA_NAME.fullmatch(name) or name not in self._names():
            raise ProtocolError("Resource not found; choose an exact URI from resources/list")
        value = schema_operation("read", {"name": name})
        text = json.dumps(value["schema"], ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        if len(text.encode("utf-8")) > MAX_SCHEMA_BYTES:
            raise ProtocolError("Schema resource exceeds size limit", -32603)
        return {"contents": [{"uri": uri, "mimeType": "application/schema+json", "text": text}]}
