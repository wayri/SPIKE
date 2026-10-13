# SPDX-License-Identifier: Apache-2.0
"""Adversarial provider boundary and real loopback HTTP protocol checks."""
import json
import math
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_core import assistant_provider as p
from spike_core import assistant_credentials as c
from spike_core.service_assistant import handle_assistant_request as handle


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.reply = {"choices": [{"finish_reason": "stop", "message": {"content": "Local answer"}}]}
        self.delay = 0
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                owner.requests.append((self.path, dict(self.headers), json.loads(body) if body else None))
                time.sleep(owner.delay)
                self.send_response(owner.status)
                self.end_headers()
                raw = owner.reply if isinstance(owner.reply, bytes) else json.dumps(owner.reply).encode()
                try:
                    self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
            def do_GET(self):
                self.do_POST()
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def params(self, **changes):
        result = {"provider": "lmstudio", "model": "user-model", "endpoint": self.endpoint,
                  "messages": [{"role": "user", "content": "hello"}], "tools": [], "share_project_context": False}
        result.update(changes)
        return result

    def test_loopback_roundtrip_no_proxy_or_credentials(self):
        with patch.dict("os.environ", {"HTTP_PROXY": "http://invalid:9999"}), patch.object(c, "get_credential", side_effect=AssertionError("must not read")):
            result = handle("assistant_turn", self.params())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["message"]["content"], "Local answer")
        path, headers, payload = self.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertNotIn("Authorization", headers)
        self.assertFalse(payload["stream"])

    def test_tool_roundtrip_ollama(self):
        tools = [{"name": "inspect", "description": "Read selected evidence", "parameters": {"type": "object", "properties": {}}}]
        self.reply = {"done": True, "message": {"content": "", "tool_calls": [{"function": {"name": "inspect", "arguments": {"count": 1}}}]}}
        first = p.assistant_turn(self.params(provider="ollama", tools=tools))
        call = first["message"]["tool_calls"][0]
        self.assertEqual(call["id"], "call_1_0")
        self.reply = {"done": True, "message": {"content": "Observed result"}}
        history = [{"role": "user", "content": "hello"}, first["message"], {"role": "tool", "tool_call_id": call["id"], "content": "evidence"}]
        p.assistant_turn(self.params(provider="ollama", tools=tools, messages=history))
        self.assertEqual(self.requests[-1][2]["messages"][-1]["tool_name"], "inspect")
        self.assertEqual(self.requests[-1][2]["messages"][-2]["tool_calls"][0]["function"]["arguments"], {"count": 1})

    def test_malformed_duplicate_nonfinite_and_oversize(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'not json', b'['):
            self.reply = raw
            self.assertFalse(handle("assistant_turn", self.params())["ok"])
        self.reply = b'x' * (p.RESPONSE_LIMIT + 1)
        self.assertFalse(handle("assistant_turn", self.params())["ok"])
        for change in ({"messages": [{}] * 129}, {"system": "x" * p.REQUEST_LIMIT}, {"tools": [math.nan]}):
            self.assertFalse(handle("assistant_turn", self.params(**change))["ok"])

    def test_http_redirect_and_error_body_redacted(self):
        for status in (302, 401, 500):
            self.status = status
            self.reply = b'PRIVATE_KEY_AND_PROJECT'
            result = handle("assistant_turn", self.params())
            self.assertFalse(result["ok"])
            self.assertNotIn("PRIVATE", json.dumps(result))

    def test_deadline(self):
        self.delay = .2
        with patch.object(p, "TIMEOUT", .05):
            before = time.monotonic()
            self.assertFalse(handle("assistant_turn", self.params())["ok"])
            self.assertLess(time.monotonic() - before, .18)

    def test_endpoint_confinement(self):
        for endpoint in ("http://example.org:80", "http://127.0.0.1", "http://user:key@127.0.0.1:80", "https://127.0.0.1:80", "http://127.0.0.1:80/evil", "http://127.0.0.1:80?secret=x"):
            with self.assertRaises(p.ProviderError):
                p._destination("lmstudio", endpoint)
        with self.assertRaises(p.ProviderError):
            p._destination("openai", self.endpoint)
        self.assertEqual(p._destination("lmstudio", "http://localhost:1234")[1], "127.0.0.1")
        self.assertEqual(p._destination("lmstudio", "http://[::1]:1234")[1], "::1")

    def test_models_and_status_do_not_probe_implicitly(self):
        self.reply = {"data": [{"id": "b"}, {"id": "a"}, {"id": "a"}]}
        self.assertEqual(p.assistant_models({"provider": "lmstudio", "endpoint": self.endpoint})["models"], ["a", "b"])
        self.assertEqual(self.requests[-1][0], "/v1/models")
        with patch.object(p, "_request", side_effect=AssertionError("no status network probe")), patch.object(c, "get_credential", return_value="private-key"):
            status = p.assistant_provider_status({"provider": "openai"})
            self.assertFalse(status["network_probed"])
            self.assertNotIn("private-key", json.dumps(status))

    def test_cloud_headers_tls_and_fixed_host(self):
        for selected in ("openai", "anthropic"):
            connection = MagicMock()
            response = connection.getresponse.return_value
            response.status = 200
            response.getheader.return_value = None
            response.read1.side_effect = [b'{"data":[]}', b'']
            with patch.object(c, "get_credential", return_value="private-key") as read, patch.object(p.http.client, "HTTPSConnection", return_value=connection) as constructor:
                self.assertEqual(p.assistant_models({"provider": selected})["models"], [])
                self.assertEqual(constructor.call_args.args[:2], (p.CLOUD[selected], 443))
                self.assertTrue(constructor.call_args.kwargs["context"].check_hostname)
                headers = connection.request.call_args.args[3]
                self.assertEqual(headers.get("Authorization") if selected == "openai" else headers.get("x-api-key"), "Bearer private-key" if selected == "openai" else "private-key")
                if selected == "anthropic":
                    self.assertEqual(headers["anthropic-version"], "2023-06-01")
                read.reset_mock()
                with self.assertRaises(p.ProviderError):
                    p.assistant_models({"provider": selected, "endpoint": self.endpoint})
                read.assert_not_called()

    def test_native_store_write_uses_credential_api(self):
        if sys.platform != "win32":
            self.skipTest("Windows ctypes credential structure")
        api, structure = c._native()
        fake = MagicMock()
        fake.CredWriteW.return_value = True
        saved = []
        def capture(pointer, flags):
            record = pointer._obj
            saved.append((record.TargetName, c.ctypes.string_at(record.CredentialBlob, record.CredentialBlobSize), record.Persist))
            return True
        fake.CredWriteW.side_effect = capture
        with patch.object(c, "_native", return_value=(fake, structure)):
            c.set_credential("openai", "unit-test-key")
        self.assertEqual(saved, [("SPIKE/assistant/openai", b"unit-test-key", 2)])
        with self.assertRaises(ValueError):
            c.set_credential("openai", "header\r\ninjection")

    def test_cloud_consent_and_formats(self):
        tools = [{"name": "inspect", "description": "Read", "parameters": {"type": "object"}}]
        history = [{"role": "user", "content": "Check"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "inspect", "arguments": {"x": 1}}]}, {"role": "tool", "tool_call_id": "c1", "content": "result"}]
        with patch.object(p, "_request") as request:
            self.assertFalse(handle("assistant_turn", self.params(provider="openai"))["ok"])
            request.assert_not_called()
            request.return_value = {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "answer"}]}]}
            args = self.params(provider="openai", endpoint=None, allow_cloud=True, messages=history, tools=tools)
            self.assertTrue(handle("assistant_turn", args)["ok"])
            payload = request.call_args.args[3]
            self.assertFalse(payload["store"])
            self.assertEqual(payload["input"][-2]["type"], "function_call")
            self.assertEqual(payload["input"][-1]["call_id"], "c1")
            request.return_value = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "answer"}]}
            args["provider"] = "anthropic"
            self.assertTrue(handle("assistant_turn", args)["ok"])
            messages = request.call_args.args[3]["messages"]
            self.assertEqual(messages[-1]["content"][0]["tool_use_id"], "c1")
            self.assertEqual(messages[-2]["content"][0]["type"], "tool_use")

    def test_credential_routes_and_secret_redaction(self):
        with patch.object(c, "set_credential") as save:
            result = handle("assistant_set_credential", {"provider": "openai", "key": "private-key"})
            save.assert_called_once_with("openai", "private-key")
            self.assertNotIn("private-key", json.dumps(result))
        with patch.object(c, "set_credential", side_effect=RuntimeError("private-key")):
            self.assertNotIn("private-key", json.dumps(handle("assistant_set_credential", {"provider": "openai", "key": "private-key"})))
        with patch.object(c.sys, "platform", "linux"):
            with self.assertRaises(RuntimeError):
                c.set_credential("openai", "key")
        self.assertFalse(handle("assistant_turn", self.params(unrecognized="field"))["ok"])
        self.assertIsNone(handle("not_assistant", {}))

    def test_incomplete_unavailable_duplicate_calls_rejected(self):
        self.reply = {"choices": [{"finish_reason": "length", "message": {"content": "truncated"}}]}
        self.assertFalse(handle("assistant_turn", self.params())["ok"])
        self.reply = {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{"id": "x", "function": {"name": "execute_shell", "arguments": "{}"}}]}}]}
        self.assertFalse(handle("assistant_turn", self.params())["ok"])
        with self.assertRaises(p.ProviderError):
            p._calls([{"id": "x", "name": "n", "arguments": {}}] * 2)
        with self.assertRaises(p.ProviderError):
            p._calls([{"id": str(i), "name": "n", "arguments": {}} for i in range(9)])
        self.assertFalse(handle("assistant_turn", self.params(messages=[{"role": "tool", "tool_call_id": "missing", "content": "x"}]))["ok"])


if __name__ == "__main__":
    unittest.main()
