# SPDX-License-Identifier: Apache-2.0
"""Attachment boundary tests; provider transports use inert mocked responses."""
import base64
import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from spike_core import assistant_provider as p
from spike_core import assistant_media as media


def attachment(data=b"\x89PNG\r\n\x1a\nfixture", mime="image/png"):
    return {"id": "a1", "name": "evidence", "mimeType": mime,
            "dataUrl": "data:" + mime + ";base64," + base64.b64encode(data).decode(),
            "sha256": hashlib.sha256(data).hexdigest()}


class AssistantMediaTests(unittest.TestCase):
    def params(self, *items, provider="lmstudio", **changes):
        return {"provider": provider, "model": "exact-model", "allow_cloud": True,
                "messages": [{"role": "user", "content": "Explain", "attachments": list(items)}], **changes}

    def test_four_transports_preserve_image_bytes(self):
        item = attachment()
        history = p._history(self.params(item))
        for provider in ("openai", "anthropic", "lmstudio", "ollama"):
            payload = p._payload(provider, "exact-model", history, [], "")
            if provider == "openai":
                self.assertEqual(payload["input"][0]["content"][-1], {"type": "input_image", "image_url": item["dataUrl"]})
            elif provider == "anthropic":
                self.assertEqual(payload["messages"][0]["content"][-1]["source"]["data"], item["dataUrl"].split(",")[1])
            elif provider == "lmstudio":
                self.assertEqual(payload["messages"][0]["content"][-1]["image_url"]["url"], item["dataUrl"])
            else:
                self.assertEqual(payload["messages"][0]["images"], [item["dataUrl"].split(",")[1]])

    def test_text_preserves_hash_name_and_untrusted_boundary(self):
        item = attachment("UTF-8 evidence \u03a9".encode(), "text/plain")
        for provider in ("openai", "anthropic", "lmstudio", "ollama"):
            payload = p._payload(provider, "m", p._history(self.params(item)), [], "")
            self.assertIn(item["sha256"], str(payload))
            self.assertIn("SPIKE UNTRUSTED ATTACHMENT EVIDENCE", str(payload))
            self.assertIn("UTF-8 evidence", str(payload))

    def test_malformed_attachment_rejected_before_network(self):
        variants = [{"sha256": "0" * 64}, {"dataUrl": "https://private.example/image.png"},
                    {"dataUrl": "data:image/png;base64,!!!!"}, {"mimeType": "image/svg+xml"},
                    {"id": ""}, {"name": "bad\nname"}, {"extra": "field"}]
        cases = [{**attachment(), **change} for change in variants]
        cases += [attachment(b"not png"), attachment(b"\xff", "text/plain"), attachment(b"x\x00", "text/plain")]
        with patch.object(p, "_request") as request:
            for item in cases:
                with self.subTest(item=item):
                    with self.assertRaises(p.ProviderError):
                        p.assistant_turn(self.params(item))
            request.assert_not_called()

    def test_mime_signatures(self):
        for data, mime in ((b"\xff\xd8\xfffixture", "image/jpeg"), (b"RIFF0000WEBPfixture", "image/webp")):
            self.assertEqual(p._history(self.params(attachment(data, mime)))[0]["attachments"][0]["mimeType"], mime)

    def test_entire_history_counts_images_and_attachment_budget(self):
        item = attachment()
        params = self.params(item)
        params["messages"] *= 5
        with self.assertRaisesRegex(p.ProviderError, "full request"):
            p._history(params)
        params = self.params(attachment(b"x", "text/plain"))
        params["messages"] *= 9
        with self.assertRaisesRegex(p.ProviderError, "full request"):
            p._history(params)
        with self.assertRaises(p.ProviderError):
            p._history(self.params(attachment(b"x" * (media.TEXT_LIMIT + 1), "text/plain")))
        with patch.object(media, "IMAGE_LIMIT", 12):
            with self.assertRaises(p.ProviderError):
                p._history(self.params(item))
        with patch.object(media, "TOTAL_LIMIT", 12):
            with self.assertRaises(p.ProviderError):
                p._history(self.params(item))

    def test_aggregate_text_budget_survives_larger_transport(self):
        params = self.params(*[attachment(b"x" * media.TEXT_LIMIT, "text/plain")] * 8)
        with patch.object(p, "_request") as request:
            with self.assertRaisesRegex(p.ProviderError, "2 MiB"):
                p.assistant_turn(params)
            request.assert_not_called()

    def test_local_vision_verified_for_exact_model_before_chat(self):
        reply = {"choices": [{"finish_reason": "stop", "message": {"content": "Answer"}}]}
        with patch.object(p, "_request", side_effect=[{"data": [{"id": "exact-model", "type": "vlm"}]}, reply]) as request:
            self.assertEqual(p.assistant_turn(self.params(attachment()))["message"]["content"], "Answer")
            self.assertEqual([call.args[2] for call in request.call_args_list], ["/api/v0/models", "/v1/chat/completions"])
        for metadata in ({"data": [{"id": "other-model", "type": "vlm"}]}, {"data": [{"id": "exact-model", "type": "llm"}]}, {}):
            with patch.object(p, "_request", return_value=metadata) as request:
                with self.assertRaisesRegex(p.ProviderError, "verified vision"):
                    p.assistant_turn(self.params(attachment()))
                self.assertEqual(request.call_count, 1)
        with patch.object(p, "_request", return_value={"capabilities": ["vision"]}) as request:
            p._require_local_vision("ollama", "exact-model", None)
            self.assertEqual(request.call_args.args[3], {"model": "exact-model"})

    def test_cloud_consent_still_gates_images(self):
        with patch.object(p, "_request") as request:
            with self.assertRaisesRegex(p.ProviderError, "Confirm sending"):
                p.assistant_turn(self.params(attachment(), provider="openai", allow_cloud=False))
            request.assert_not_called()

    def test_media_outputs_rejected_explicitly(self):
        cases = [("openai", {"output": [{"type": "image_generation_call"}]}),
                 ("anthropic", {"stop_reason": "end_turn", "content": [{"type": "image"}]}),
                 ("ollama", {"done": True, "message": {"content": "Answer", "images": ["unvalidated"]}})]
        for provider, result in cases:
            with self.assertRaisesRegex(p.ProviderError, "media output is unsupported"):
                p._normalize(provider, result, 1)


if __name__ == "__main__":
    unittest.main()
