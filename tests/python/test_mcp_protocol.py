# SPDX-License-Identifier: Apache-2.0
"""Native-free MCP lifecycle, framing, cursor and installed-resource checks."""
import json
import unittest
from unittest.mock import patch

from python.spike_core.mcp_protocol import (
    LEGACY_VERSION, MODERN_VERSION, META_PREFIX, SUPPORTED_VERSIONS,
    McpProtocol, ProtocolError, decode_request, encode_response,
)
from python.spike_core.mcp_protocol_catalog import CatalogPager
from python.spike_core.mcp_resources import SchemaResources, SCHEMA_URI_PREFIX


def request(method, params=None, modern=True, identifier=1):
    params = dict(params or {})
    if modern:
        params["_meta"] = {META_PREFIX + "protocolVersion": MODERN_VERSION,
                           META_PREFIX + "clientCapabilities": {}}
    return {"jsonrpc": "2.0", "id": identifier, "method": method, "params": params}


class ProtocolTests(unittest.TestCase):
    def test_modern_discovery_and_direct_requests_are_stateless(self):
        protocol = McpProtocol()
        handled, response = protocol.gate(request("server/discover"))
        self.assertTrue(handled)
        result = response["result"]
        self.assertEqual(result["supportedVersions"], list(SUPPORTED_VERSIONS))
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["capabilities"], {"tools": {}, "resources": {}})
        self.assertIn(META_PREFIX + "serverInfo", result["_meta"])
        self.assertFalse(protocol.initialized)
        self.assertEqual(McpProtocol().gate(request("tools/list")), (False, None))
        self.assertEqual(protocol.result(request("tools/call"), {"isError": True})["result"]["resultType"], "complete")

    def test_legacy_fallback_and_concurrent_modern(self):
        protocol = McpProtocol()
        self.assertEqual(protocol.gate(request("tools/list", modern=False))[1]["error"]["code"], -32002)
        response = protocol.gate(request("initialize", {"protocolVersion": "2000-01-01"}, modern=False))[1]
        self.assertEqual(response["result"]["protocolVersion"], LEGACY_VERSION)
        self.assertNotIn("resultType", response["result"])
        self.assertEqual(response["result"]["capabilities"]["resources"], {"subscribe": False, "listChanged": False})
        self.assertTrue(protocol.initialized)
        self.assertEqual(protocol.gate(request("tools/list", modern=False)), (False, None))
        self.assertEqual(protocol.gate(request("tools/list")), (False, None))
        self.assertEqual(protocol.gate(request("ping", modern=False))[1]["result"], {})
        self.assertEqual(protocol.gate(request("initialize", {"protocolVersion": LEGACY_VERSION}, modern=False))[1]["error"]["code"], -32602)

    def test_version_negotiation_and_missing_metadata(self):
        protocol = McpProtocol()
        message = request("tools/list")
        message["params"]["_meta"][META_PREFIX + "protocolVersion"] = "2999-01-01"
        error = protocol.gate(message)[1]["error"]
        self.assertEqual(error["code"], -32022)
        self.assertEqual(error["data"], {"supported": list(SUPPORTED_VERSIONS), "requested": "2999-01-01"})
        for key in ("protocolVersion", "clientCapabilities"):
            message = request("tools/list")
            del message["params"]["_meta"][META_PREFIX + key]
            self.assertEqual(protocol.gate(message)[1]["error"]["code"], -32602)
        self.assertEqual(protocol.gate(request("server/discover", modern=False))[1]["error"]["code"], -32602)
        self.assertEqual(protocol.gate(request("initialize"))[1]["error"]["code"], -32601)

    def test_notifications_never_dispatch_or_respond(self):
        protocol = McpProtocol()
        for method in ("notifications/initialized", "notifications/cancelled", "tools/call", "initialize"):
            message = request(method)
            del message["id"]
            self.assertEqual(protocol.gate(message), (True, None))
        self.assertFalse(protocol.initialized)

    def test_request_envelopes_and_metadata(self):
        protocol = McpProtocol()
        for identifier in (None, True, 1.5, [], {}):
            result = protocol.gate(request("ping", identifier=identifier))[1]
            self.assertEqual(result["error"]["code"], -32600)
            self.assertIsNone(result["id"])
        for value in ([], "bad", None):
            message = request("ping")
            message["params"] = value
            self.assertEqual(protocol.gate(message)[1]["error"]["code"], -32602)
        for meta in ([], {"bad/key/name": 1}, {META_PREFIX + "protocolVersion": MODERN_VERSION}):
            message = request("ping")
            message["params"]["_meta"] = meta
            self.assertEqual(protocol.gate(message)[1]["error"]["code"], -32602)
        self.assertEqual(protocol.gate([])[1]["error"]["code"], -32600)
        self.assertEqual(protocol.gate({**request("ping"), "result": {}})[1]["error"]["code"], -32600)

    def test_strict_framing_and_complete_response_budget(self):
        good = (json.dumps(request("ping")) + "\n").encode()
        self.assertEqual(decode_request(good)["method"], "ping")
        self.assertEqual(decode_request(good[:-1] + b"\r\n")["method"], "ping")
        for line in (good[:-1], good + good, b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'\xff\n', b'{}\r \n'):
            with self.assertRaises(ProtocolError):
                decode_request(line)
        with self.assertRaises(ProtocolError):
            decode_request(good, max_bytes=10)
        with self.assertRaises(ProtocolError):
            decode_request(b'[' * 70 + b'0' + b']' * 70 + b'\n')
        response = McpProtocol().result(request("ping"), {})
        encoded = encode_response(response)
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(json.loads(encoded), response)
        with self.assertRaises(ProtocolError):
            encode_response(response, max_bytes=len(encoded) - 1)
        with self.assertRaises(ProtocolError):
            encode_response({"result": float("inf")})


class CatalogTests(unittest.TestCase):
    def test_deterministic_paging_and_namespace_catalog_binding(self):
        pager = CatalogPager(page_size=2)
        items = [{"name": name, "uri": name} for name in "edcba"]
        first = pager.page(items, {}, "tools", "name")
        self.assertEqual([item["name"] for item in first["tools"]], ["a", "b"])
        self.assertEqual(first, pager.page(list(reversed(items)), {}, "tools", "name"))
        second = pager.page(items, {"cursor": first["nextCursor"]}, "tools", "name")
        last = pager.page(items, {"cursor": second["nextCursor"]}, "tools", "name")
        self.assertEqual([item["name"] for item in last["tools"]], ["e"])
        self.assertNotIn("nextCursor", last)
        for catalog, namespace, key in ((items, "resources", "uri"),
                (items + [{"name": "f"}], "tools", "name"),
                ([{**item, "description": "changed"} for item in items], "tools", "name")):
            with self.assertRaises(ProtocolError):
                pager.page(catalog, {"cursor": first["nextCursor"]}, namespace, key)
        with self.assertRaises(ProtocolError):
            CatalogPager(page_size=3).page(items, {"cursor": first["nextCursor"]}, "tools", "name")

    def test_pagination_malformed_and_budgets(self):
        pager = CatalogPager(page_size=1)
        for cursor in (None, False, 3, "", "x" * 64, "x" * 4096):
            with self.assertRaises(ProtocolError):
                pager.page([{"name": "a"}], {"cursor": cursor}, "tools", "name")
        with self.assertRaises(ProtocolError):
            pager.page([], {"pageSize": 99999}, "tools", "name")
        with self.assertRaises(ProtocolError):
            CatalogPager(max_items=1).page([{"name": "a"}, {"name": "b"}], {}, "tools", "name")
        with self.assertRaises(ProtocolError):
            CatalogPager(max_catalog_bytes=2).page([{"name": "a"}], {}, "tools", "name")
        with self.assertRaises(ProtocolError):
            pager.page([{"name": "a"}, {"name": "a"}], {}, "tools", "name")
        self.assertEqual(pager.page([], {}, "tools", "name"), {"tools": []})

    def test_installed_schema_resources_and_uri_confinement(self):
        resources = SchemaResources(CatalogPager(page_size=32))
        seen = []
        params = {}
        while True:
            page = resources.list(params)
            seen.extend(page["resources"])
            if "nextCursor" not in page:
                break
            params = {"cursor": page["nextCursor"]}
        self.assertGreater(len(seen), 32)
        self.assertEqual(len({item["uri"] for item in seen}), len(seen))
        uri = SCHEMA_URI_PREFIX + "design-ir-v1.schema.json"
        result = resources.read({"uri": uri})
        content = result["contents"][0]
        self.assertEqual(content["uri"], uri)
        self.assertEqual(content["mimeType"], "application/schema+json")
        self.assertEqual(json.loads(content["text"])["type"], "object")
        for path in ("file:///etc/passwd", "https://example.com/a.schema.json", SCHEMA_URI_PREFIX + "../LICENSE",
                SCHEMA_URI_PREFIX + "%2e%2e%2fLICENSE", SCHEMA_URI_PREFIX + "design-ir-v1.schema.json?x=1",
                SCHEMA_URI_PREFIX + "design-ir-v1.schema.json#x", SCHEMA_URI_PREFIX + "missing.schema.json",
                SCHEMA_URI_PREFIX + "..\\LICENSE", "spike://schemas@host/design-ir-v1.schema.json"):
            with self.assertRaises(ProtocolError):
                resources.read({"uri": path})

    def test_schema_hash_change_invalidates_resource_cursor(self):
        def catalog(digest):
            return {"schemas": ["a.schema.json", "b.schema.json"], "descriptors": [
                {"name": name, "sha256": digest} for name in ["a.schema.json", "b.schema.json"]]}
        resources = SchemaResources(CatalogPager(page_size=1))
        with patch("python.spike_core.mcp_resources.schema_operation", return_value=catalog("old")):
            cursor = resources.list({})["nextCursor"]
        with patch("python.spike_core.mcp_resources.schema_operation", return_value=catalog("new")):
            with self.assertRaisesRegex(ProtocolError, "stale cursor"):
                resources.list({"cursor": cursor})

    def test_resource_payload_limit(self):
        def operation(name, args):
            if not args:
                return {"schemas": ["a.schema.json"]}
            return {"schema": {"description": "x" * (1024 * 1024)}}
        with patch("python.spike_core.mcp_resources.schema_operation", side_effect=operation), \
                patch("python.spike_core.mcp_resources.installed_schema_catalog", return_value={"a.schema.json": None}):
            with self.assertRaisesRegex(ProtocolError, "size limit"):
                SchemaResources().read({"uri": SCHEMA_URI_PREFIX + "a.schema.json"})


if __name__ == "__main__":
    unittest.main()
