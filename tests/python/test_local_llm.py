# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from python.spike_core.local_llm import LocalModelError, chat, list_models


class FakeTools:
    def __init__(self):
        self.calls = []

    def tools(self):
        return [{"name": "spike_gui_status", "description": "Status", "inputSchema": {"type": "object", "properties": {}}}]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"content": [{"type": "text", "text": '{"workspace":"EM"}'}], "isError": False}


class Handler(BaseHTTPRequestHandler):
    requests = []
    responses = []

    def do_GET(self):
        data = {"data": [{"id": "local-lm"}]} if self.path == "/v1/models" else {"models": [{"name": "local-ollama"}]}
        self._send(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append((self.path, body))
        if self.responses:
            self._send(self.responses.pop(0))
            return
        second = len(self.requests) == 2
        if self.path == "/v1/chat/completions":
            message = {"role": "assistant", "content": "EM ready"} if second else {"role": "assistant", "content": "", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "spike_gui_status", "arguments": "{}"}}]}
            data = {"choices": [{"message": message, "finish_reason": "stop" if second else "tool_calls"}]}
        else:
            message = {"role": "assistant", "content": "EM ready"} if second else {"role": "assistant", "content": "", "tool_calls": [{"type": "function", "function": {"name": "spike_gui_status", "arguments": {}}}]}
            data = {"message": message, "done": True}
        self._send(data)

    def _send(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class LocalModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.http.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()

    def setUp(self):
        Handler.requests.clear()
        Handler.responses.clear()

    def test_lmstudio_tool_roundtrip(self):
        tools = FakeTools()
        self.assertEqual(list_models("lmstudio", self.origin), ["local-lm"])
        self.assertEqual(chat("lmstudio", "local-lm", "show status", endpoint=self.origin, server=tools), "EM ready")
        self.assertEqual(tools.calls, [("spike_gui_status", {})])
        self.assertEqual(Handler.requests[1][1]["messages"][-1]["tool_call_id"], "call-1")

    def test_lmstudio_null_content_tool_roundtrip(self):
        Handler.responses.extend([
            {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "call-null", "type": "function", "function": {
                    "name": "spike_gui_status", "arguments": "{}"}}]}}]},
            {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "EM ready"}}]},
        ])
        tools = FakeTools()
        self.assertEqual(chat("lmstudio", "local-lm", "show status", endpoint=self.origin, server=tools), "EM ready")
        self.assertEqual(tools.calls, [("spike_gui_status", {})])
        history = Handler.requests[1][1]["messages"]
        self.assertEqual(history[-2]["content"], "")
        self.assertEqual(history[-1]["tool_call_id"], "call-null")

    def test_ollama_tool_roundtrip(self):
        tools = FakeTools()
        self.assertEqual(list_models("ollama", self.origin), ["local-ollama"])
        self.assertEqual(chat("ollama", "local-ollama", "show status", endpoint=self.origin, server=tools), "EM ready")
        self.assertEqual(tools.calls, [("spike_gui_status", {})])
        self.assertEqual(Handler.requests[1][1]["messages"][-1]["tool_name"], "spike_gui_status")

    def test_non_loopback_endpoint_rejected(self):
        with self.assertRaises(LocalModelError):
            list_models("ollama", "https://example.com:11434")

    def test_ollama_incomplete_response_is_rejected_before_tool_execution(self):
        Handler.responses.append({"message": {"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": "spike_gui_status", "arguments": {}}}
        ]}, "done": False})
        tools = FakeTools()
        with self.assertRaisesRegex(LocalModelError, "incomplete"):
            chat("ollama", "local-ollama", "show status", endpoint=self.origin, server=tools)
        self.assertEqual(tools.calls, [])

    def test_lmstudio_missing_tool_id_is_rejected_before_tool_execution(self):
        Handler.responses.append({"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": "spike_gui_status", "arguments": "{}"}}
        ]}}]})
        tools = FakeTools()
        with self.assertRaisesRegex(LocalModelError, "lacks an ID"):
            chat("lmstudio", "local-lm", "show status", endpoint=self.origin, server=tools)
        self.assertEqual(tools.calls, [])

    def test_lmstudio_truncated_response_is_rejected(self):
        Handler.responses.append({"choices": [{"finish_reason": "length", "message": {
            "role": "assistant", "content": "partial"
        }}]})
        with self.assertRaisesRegex(LocalModelError, "incomplete"):
            chat("lmstudio", "local-lm", "show status", endpoint=self.origin, server=FakeTools())

    def test_empty_assistant_response_is_rejected(self):
        Handler.responses.append({"message": {"role": "assistant", "content": ""}, "done": True})
        with self.assertRaisesRegex(LocalModelError, "no text or tool calls"):
            chat("ollama", "local-ollama", "show status", endpoint=self.origin, server=FakeTools())

    def test_null_text_only_response_is_rejected(self):
        Handler.responses.append({"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": None
        }}]})
        with self.assertRaisesRegex(LocalModelError, "invalid assistant content"):
            chat("lmstudio", "local-lm", "show status", endpoint=self.origin, server=FakeTools())

    def test_tool_round_limit_does_not_execute_extra_call(self):
        tools = FakeTools()
        tool_message = {"message": {"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": "spike_gui_status", "arguments": {}}}
        ]}, "done": True}
        with patch("python.spike_core.local_llm._request", return_value=tool_message):
            with self.assertRaisesRegex(LocalModelError, "tool-round limit"):
                chat("ollama", "local-ollama", "show status", server=tools)
        self.assertEqual(len(tools.calls), 8)

    def test_worker_entry_mcp_mode(self):
        root = Path(__file__).resolve().parents[2]
        request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}}
        completed = subprocess.run([sys.executable, str(root / "scripts" / "spike_worker_entry.py"), "--mcp"], input=json.dumps(request) + "\n", text=True, capture_output=True, cwd=root, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["result"]["protocolVersion"], "2025-11-25")


if __name__ == "__main__":
    unittest.main()
