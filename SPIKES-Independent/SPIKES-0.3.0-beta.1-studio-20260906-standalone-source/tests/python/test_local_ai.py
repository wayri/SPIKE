from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

STUDIO_PYTHON = Path(__file__).resolve().parents[2] / "studio/python"
if str(STUDIO_PYTHON) not in sys.path:
    sys.path.insert(0, str(STUDIO_PYTHON))

from spikes_studio.local_ai import (  # noqa: E402
    DatasheetEvidence,
    LocalAIError,
    LocalModelAssistant,
    build_formation_request,
)


class LocalAITests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = build_formation_request(
            [DatasheetEvidence("opamp.pdf", "Gain bandwidth 10 MHz", ("p. 7",))],
            intent="Form an op-amp macromodel",
        )
        self.draft = {
            "contract": "spikes/studio-ai-model-draft/v1",
            "part": {"name": "OPA_TEST", "family": "opamp", "pins": ["IN+", "IN-", "OUT"]},
            "evidence": [{"claim": "GBW", "source": "p. 7"}],
            "symbol": {"terminals": [], "body_keepout": {}},
            "model": {"backend": "spice_behavioral", "source": ".subckt ..."},
            "qualification": {"state": "claimed"},
            "execution": {"allowed": True},
            "validation_plan": ["Compare AC gain"],
        }

    def test_lm_studio_request_is_bounded_and_forced_inert(self) -> None:
        calls = []

        def transport(url, payload, headers, timeout, max_bytes):
            calls.append((url, json.loads(payload), max_bytes))
            return json.dumps({"choices": [{"message": {"content": json.dumps(self.draft)}}]}).encode()

        result = LocalModelAssistant(transport=transport).create_draft(
            "lm_studio", "http://127.0.0.1:1234", "local-model", self.request
        )
        self.assertEqual(calls[0][0], "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(calls[0][1]["response_format"], {"type": "json_object"})
        self.assertFalse(result["execution"]["allowed"])
        self.assertEqual(result["qualification"]["state"], "unreviewed")

    def test_ollama_envelope(self) -> None:
        def transport(url, payload, headers, timeout, max_bytes):
            self.assertEqual(url, "http://localhost:11434/api/chat")
            return json.dumps({"message": {"content": json.dumps(self.draft)}}).encode()

        result = LocalModelAssistant(transport=transport).create_draft(
            "ollama", "http://localhost:11434", "qwen-local", self.request
        )
        self.assertEqual(result["provider"], "ollama")

    def test_non_loopback_or_credentialed_endpoint_is_rejected(self) -> None:
        assistant = LocalModelAssistant(transport=lambda *args: b"{}")
        for endpoint in ("https://127.0.0.1:1234", "http://example.com:1234", "http://user:pw@localhost:1234"):
            with self.subTest(endpoint=endpoint), self.assertRaises(LocalAIError):
                assistant.create_draft("lm_studio", endpoint, "m", self.request)


if __name__ == "__main__":
    unittest.main()
