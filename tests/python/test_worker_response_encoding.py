# SPDX-License-Identifier: Apache-2.0
"""JSON-line transport preserves values while avoiding formatting payload."""
import io
import json
import unittest
from unittest.mock import patch

from python.spike_core.worker_protocol import serve_json_lines


class WorkerResponseEncodingTests(unittest.TestCase):
    def test_dense_response_roundtrip_and_line_framing(self):
        rows = [{"id": str(i), "value": i / 7, "layer": "F.Cu"} for i in range(1000)]
        payload = {"ok": True, "result": {"samples": rows, "label": "line\nµ"}}
        incoming = io.StringIO('{"id":"dense","method":"fixture"}\n')
        outgoing = io.StringIO()
        with patch("sys.stdin", incoming), patch("sys.stdout", outgoing):
            self.assertEqual(serve_json_lines(lambda request: payload, "test"), 0)
        wire = outgoing.getvalue()
        self.assertEqual(len(wire.splitlines()), 1)
        decoded = json.loads(wire)
        self.assertEqual(decoded["result"], payload["result"])
        self.assertEqual(decoded["id"], "dense")
        self.assertLess(len(wire), len(json.dumps(decoded)) * 0.95)


if __name__ == "__main__":
    unittest.main()
