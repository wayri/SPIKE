# SPDX-License-Identifier: Apache-2.0
"""MCP transport and worker allowlist regression tests."""

import io
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from python.spike_core.automation import SpikeAutomation
from python.spike_core.mcp_server import McpServer, PROTOCOL_VERSION, TOOLS, serve


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def dispatch(request):
            self.calls.append(request)
            print("worker diagnostic")
            if request["method"] == "validate_design":
                return {"ok": False, "error": "invalid geometry"}
            return {"ok": True, "result": {"status": "ready", "method": request["method"]}}

        self.server = McpServer(SpikeAutomation(dispatch))

    def rpc(self, identifier, method, params=None):
        request = {"jsonrpc": "2.0", "id": identifier, "method": method}
        if params is not None:
            request["params"] = params
        return self.server.handle(request)

    def initialize(self):
        return self.rpc(1, "initialize", {"protocolVersion": PROTOCOL_VERSION,
                                          "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})

    def test_handshake_and_tool_list(self):
        self.assertEqual(self.rpc(0, "tools/list")["error"]["code"], -32002)
        initialized = self.initialize()["result"]
        self.assertEqual(initialized["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(initialized["capabilities"], {"tools": {"listChanged": False}})
        self.assertIsNone(self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.rpc(2, "ping")["result"], {})
        listed = self.rpc(3, "tools/list")["result"]["tools"]
        self.assertEqual({item["name"] for item in listed}, set(TOOLS))
        self.assertEqual(next(item for item in listed if item["name"] == "spike_load_design")["inputSchema"]["required"], ["path"])

    def test_call_validation_and_worker_failure(self):
        self.initialize()
        bad = self.rpc(2, "tools/call", {"name": "spike_preflight_analysis", "arguments": {"spec": {}}})
        self.assertEqual(bad["error"]["code"], -32602)
        self.assertEqual(self.calls, [])
        unknown = self.rpc(3, "tools/call", {"name": "run_python_script", "arguments": {}})
        self.assertEqual(unknown["error"]["code"], -32602)
        good = self.rpc(4, "tools/call", {"name": "spike_preflight_analysis", "arguments": {"design": {}, "spec": {}}})
        self.assertFalse(good["result"]["isError"])
        self.assertEqual(json.loads(good["result"]["content"][0]["text"])["method"], "preflight_analysis")
        self.assertEqual(self.calls[-1]["params"], {"design": {}, "spec": {}})
        failed = self.rpc(5, "tools/call", {"name": "spike_validate_design", "arguments": {"design": {}}})
        self.assertTrue(failed["result"]["isError"])
        self.assertIn("invalid geometry", failed["result"]["content"][0]["text"])

    def test_stdio_has_only_json_rpc_frames(self):
        frames = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "spike_capabilities", "arguments": {}}},
        ]
        source = io.BytesIO(b"".join((json.dumps(frame) + "\n").encode() for frame in frames))
        target = io.BytesIO()
        serve(source, target, self.server.automation)
        output = [json.loads(line) for line in target.getvalue().splitlines()]
        self.assertEqual([item["id"] for item in output], [1, 2])
        self.assertEqual(output[1]["result"]["isError"], False)

    def test_bad_json_and_bounded_request(self):
        target = io.BytesIO()
        serve(io.BytesIO(b"not json\n"), target, self.server.automation)
        self.assertEqual(json.loads(target.getvalue())["error"]["code"], -32700)

    def test_gui_tools_are_opt_in_and_validate_arguments(self):
        self.initialize()
        invalid = self.rpc(2, "tools/call", {"name": "spike_gui_add_study_case",
                                             "arguments": {"studyId": "one", "type": "unknown"}})
        self.assertEqual(invalid["error"]["code"], -32602)
        with patch.dict(os.environ, {"SPIKE_MCP_BRIDGE_FILE": ""}):
            unavailable = self.rpc(3, "tools/call", {"name": "spike_gui_list_studies", "arguments": {}})
        self.assertTrue(unavailable["result"]["isError"])
        self.assertIn("bridge unavailable", unavailable["result"]["content"][0]["text"])
        with patch("python.spike_core.mcp_server._call_gui", return_value={"studies": []}) as bridge:
            result = self.server.call_tool("spike_gui_list_studies", {})
        self.assertFalse(result["isError"])
        bridge.assert_called_once_with("list_studies", {})

    def test_gui_bridge_loopback_exchange(self):
        received = []
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)

            def desktop():
                connection, _ = listener.accept()
                with connection:
                    with connection.makefile("rb") as source:
                        request = json.loads(source.readline())
                    received.append(request)
                    response = {"requestId": request["requestId"], "ok": True,
                                "result": {"studies": [{"name": "Sweep"}]}}
                    connection.sendall((json.dumps(response) + "\n").encode())

            thread = threading.Thread(target=desktop, daemon=True)
            thread.start()
            with tempfile.TemporaryDirectory() as temporary:
                rendezvous = Path(temporary) / "bridge.json"
                rendezvous.write_text(json.dumps({"version": 1, "host": "127.0.0.1",
                                                  "port": listener.getsockname()[1], "token": "x" * 32}), encoding="utf-8")
                with patch.dict(os.environ, {"SPIKE_MCP_BRIDGE_FILE": str(rendezvous)}):
                    result = self.server.call_tool("spike_gui_list_studies", {})
            thread.join(timeout=2)
        self.assertFalse(result["isError"])
        self.assertEqual(json.loads(result["content"][0]["text"])["studies"][0]["name"], "Sweep")
        self.assertEqual(received[0]["command"], "list_studies")
        self.assertEqual(received[0]["token"], "x" * 32)
        from python.spike_core.mcp_server import MAX_REQUEST_BYTES
        target = io.BytesIO()
        serve(io.BytesIO(b"x" * (MAX_REQUEST_BYTES + 1)), target, self.server.automation)
        self.assertEqual(json.loads(target.getvalue())["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
