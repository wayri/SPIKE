# SPDX-License-Identifier: Apache-2.0
"""Bounded JSON-line framing and dual-era MCP request admission.

This module owns transport semantics only; application tools remain allowlisted
by the server composition root. No metadata grants application permissions.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

LEGACY_VERSION = "2025-11-25"
MODERN_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = (MODERN_VERSION, LEGACY_VERSION)
META_PREFIX = "io.modelcontextprotocol/"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 100_000
_META_KEY = re.compile(r"(?:[A-Za-z](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*/)?(?:[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?)?\Z")


class ProtocolError(ValueError):
    """A client-visible protocol failure with a stable JSON-RPC code."""

    def __init__(self, message: str, code: int = -32602) -> None:
        super().__init__(message)
        self.code = code


def _bounded_json(value: Any) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            raise ProtocolError("JSON structure exceeds depth or item limit")
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise ProtocolError("JSON object keys must be strings")
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise ProtocolError("Non-finite numbers are not JSON")
        elif current is not None and type(current) not in (str, bool, int, float):
            raise ProtocolError("Unsupported JSON value")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def decode_request(line: bytes, max_bytes: int = MAX_REQUEST_BYTES) -> Any:
    """Decode one complete UTF-8 line; framing failures never dispatch tools."""
    if not isinstance(line, bytes) or len(line) > max_bytes:
        raise ProtocolError("Request exceeds size limit", -32700)
    if not line.endswith(b"\n") or b"\n" in line[:-1] or b"\r" in line[:-2]:
        raise ProtocolError("Expected one newline-delimited JSON message", -32700)
    try:
        value = json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        _bounded_json(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("Invalid or excessively nested JSON", -32700) from exc


def encode_response(response: dict[str, Any], max_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    """Serialize the complete response, including text/structured duplication."""
    try:
        encoded = (json.dumps(response, allow_nan=False, ensure_ascii=False,
                              separators=(",", ":")) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ProtocolError("Response is not valid JSON", -32603) from exc
    if len(encoded) > max_bytes:
        raise ProtocolError("Response exceeds size limit", -32603)
    return encoded


def request_params(request: dict[str, Any]) -> dict[str, Any]:
    params = request.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError("Parameters must be an object")
    return params


class McpProtocol:
    """Gate requests before application dispatch; decorate every result afterward."""

    def __init__(self) -> None:
        self.initialized = False
        self.server_info = {"name": "spike-local", "version": "1.0.0"}

    @staticmethod
    def modern(request: dict[str, Any]) -> bool:
        params = request.get("params", {})
        meta = params.get("_meta", {}) if isinstance(params, dict) else {}
        return isinstance(meta, dict) and any(
            key in meta for key in (META_PREFIX + "protocolVersion", META_PREFIX + "clientCapabilities",
                                    META_PREFIX + "clientInfo"))

    @staticmethod
    def capabilities(modern: bool = False) -> dict[str, Any]:
        if modern:
            return {"tools": {}, "resources": {}}
        return {"tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False}}

    def result(self, request: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
        result = dict(value)
        if self.modern(request):
            result["resultType"] = "complete"
            result["_meta"] = {**result.get("_meta", {}),
                               META_PREFIX + "serverInfo": dict(self.server_info)}
        return {"jsonrpc": "2.0", "id": request.get("id"), "result": result}

    @staticmethod
    def error(request: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        identifier = request.get("id") if isinstance(request, dict) else None
        if type(identifier) not in (str, int):
            identifier = None
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": identifier, "error": error}

    def gate(self, request: Any) -> tuple[bool, dict[str, Any] | None]:
        """Return (handled, response); False admits application dispatch.

        A notification is always consumed without dispatch or a response.
        Legacy initialize permits the previously supported minimal parameters.
        Modern requests do not change legacy session state.
        """
        if (not isinstance(request, dict) or request.get("jsonrpc") != "2.0"
                or not isinstance(request.get("method"), str) or not request["method"]
                or ("id" in request and type(request["id"]) not in (str, int))
                or "result" in request or "error" in request):
            return True, self.error(None, -32600, "Invalid JSON-RPC request")
        if "id" not in request:
            return True, None
        try:
            _bounded_json(request)
            if len(json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > MAX_REQUEST_BYTES:
                raise ProtocolError("Request exceeds size limit")
            params = request_params(request)
            meta = params.get("_meta", {})
            if not isinstance(meta, dict) or any(not _META_KEY.fullmatch(key) for key in meta):
                raise ProtocolError("Invalid request metadata")
            modern = self.modern(request)
            method = request["method"]
            if modern or method == "server/discover":
                version = meta.get(META_PREFIX + "protocolVersion")
                capabilities = meta.get(META_PREFIX + "clientCapabilities")
                if not isinstance(version, str) or not isinstance(capabilities, dict):
                    raise ProtocolError("Modern requests require protocolVersion and clientCapabilities metadata")
                if version == LEGACY_VERSION:
                    raise ProtocolError("Legacy protocol requires initialize without per-request version metadata")
                if version != MODERN_VERSION:
                    return True, self.error(request, -32022, "Unsupported protocol version",
                                            {"supported": list(SUPPORTED_VERSIONS), "requested": version})
                info = meta.get(META_PREFIX + "clientInfo")
                if META_PREFIX + "clientInfo" in meta and (not isinstance(info, dict)
                        or not isinstance(info.get("name"), str) or not isinstance(info.get("version"), str)):
                    raise ProtocolError("Invalid clientInfo metadata")
                if method == "initialize":
                    return True, self.error(request, -32601, "Use per-request metadata for the modern protocol")
                if method == "server/discover":
                    if set(params) - {"_meta"}:
                        raise ProtocolError("Unknown server/discover parameter")
                    return True, self.result(request, {"supportedVersions": list(SUPPORTED_VERSIONS),
                                                       "capabilities": self.capabilities(True)})
            elif method == "initialize":
                if self.initialized or not isinstance(params.get("protocolVersion"), str):
                    raise ProtocolError("Invalid initialize parameters")
                if "capabilities" in params and not isinstance(params["capabilities"], dict):
                    raise ProtocolError("Invalid initialize capabilities")
                if "clientInfo" in params and (not isinstance(params["clientInfo"], dict)
                        or not isinstance(params["clientInfo"].get("name"), str)
                        or not isinstance(params["clientInfo"].get("version"), str)):
                    raise ProtocolError("Invalid initialize clientInfo")
                self.initialized = True
                return True, self.result(request, {"protocolVersion": LEGACY_VERSION,
                    "capabilities": self.capabilities(), "serverInfo": dict(self.server_info)})
            if method == "ping":
                if set(params) - {"_meta"}:
                    raise ProtocolError("Unknown ping parameter")
                return True, self.result(request, {})
            if not modern and not self.initialized:
                return True, self.error(request, -32002, "Initialize first")
            return False, None
        except (ValueError, UnicodeError, RecursionError) as exc:
            return True, self.error(request, getattr(exc, "code", -32602), str(exc))
