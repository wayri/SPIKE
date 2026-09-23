"""Bounded localhost adapters for assisted datasheet-to-part drafting.

This module intentionally produces *drafts*, not executable models.  LM Studio
and Ollama are contacted only over loopback HTTP, responses are size bounded,
and generated C/SPICE/HDL text is never evaluated by this package.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse
from urllib.request import Request, urlopen


AI_DRAFT_CONTRACT = "spikes/studio-ai-model-draft/v1"
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 45.0


class LocalAIError(RuntimeError):
    """The provider, response, or requested operation failed a safety check."""


@dataclass(frozen=True, slots=True)
class DatasheetEvidence:
    source_name: str
    text: str
    page_refs: tuple[str, ...] = ()
    extracted_tables: tuple[Mapping[str, Any], ...] = ()
    image_observations: tuple[Mapping[str, Any], ...] = ()

    def as_prompt_object(self) -> dict[str, Any]:
        encoded = self.text.encode("utf-8")
        if not self.source_name.strip() or len(encoded) > MAX_EVIDENCE_BYTES:
            raise LocalAIError("datasheet evidence needs a name and must not exceed 8 MiB")
        return {
            "source_name": self.source_name,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "text": self.text,
            "page_refs": list(self.page_refs),
            "extracted_tables": list(self.extracted_tables),
            "image_observations": list(self.image_observations),
        }


Transport = Callable[[str, bytes, Mapping[str, str], float, int], bytes]


def _require_loopback_http(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LocalAIError("local AI endpoint must be a plain loopback HTTP URL")
    hostname = (parsed.hostname or "").lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise LocalAIError("local AI endpoint must resolve explicitly to localhost/loopback")
    if parsed.port is None or not (1 <= parsed.port <= 65535):
        raise LocalAIError("local AI endpoint must include an explicit port")
    return endpoint.rstrip("/")


def _urlopen_transport(
    url: str,
    payload: bytes,
    headers: Mapping[str, str],
    timeout: float,
    max_bytes: int,
) -> bytes:
    request = Request(url, data=payload, headers=dict(headers), method="POST")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL is loopback-validated
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise LocalAIError("local AI response exceeded the configured size limit")
    return body


FORMATION_PROMPT = """You are the SPIKES Studio model-formation assistant.
Return exactly one JSON object, without markdown. Build an evidence-traceable
draft electronic part from supplied datasheet evidence. Never claim parameters
that are absent; record unknowns and assumptions. Pin identity, units, sign
conventions, valid operating envelope, delays, parasitics, temperature behavior,
breakdown/limit behavior and equation provenance are mandatory where applicable.
Propose a toolkit-neutral symbol with terminal anchors and body keep-out geometry.
Model text may be SPICE, Verilog-A, or C-block source, but must be marked inert.
Set contract to spikes/studio-ai-model-draft/v1, qualification.state to
unreviewed, execution.allowed to false, and include a validation_plan."""


def build_formation_request(
    evidence: Sequence[DatasheetEvidence],
    *,
    intent: str,
    preferred_backend: str = "spice_behavioral",
) -> dict[str, Any]:
    if not evidence:
        raise LocalAIError("at least one datasheet evidence item is required")
    if preferred_backend not in {"spice_compact", "spice_behavioral", "verilog_a", "c_block"}:
        raise LocalAIError("unsupported requested model backend")
    sources = [item.as_prompt_object() for item in evidence]
    return {
        "task": "form_electronic_part_draft",
        "intent": intent.strip() or "Create a simulatable electronic part draft",
        "preferred_backend": preferred_backend,
        "required_contract": AI_DRAFT_CONTRACT,
        "safety": {"generated_source_is_inert": True, "human_review_required": True},
        "evidence": sources,
    }


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1])
            if stripped.lstrip().startswith("json"):
                stripped = stripped.lstrip()[4:].lstrip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LocalAIError("local AI did not return one valid JSON object") from exc
    if not isinstance(value, dict):
        raise LocalAIError("local AI response must be a JSON object")
    return value


def _fail_closed_draft(value: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
    if value.get("contract") != AI_DRAFT_CONTRACT:
        raise LocalAIError("local AI response used an unsupported contract")
    qualification = value.setdefault("qualification", {})
    if not isinstance(qualification, dict):
        raise LocalAIError("qualification must be an object")
    qualification["state"] = "unreviewed"
    qualification["human_review_required"] = True
    execution = value.setdefault("execution", {})
    if not isinstance(execution, dict):
        raise LocalAIError("execution must be an object")
    execution["allowed"] = False
    execution["generated_source_is_inert"] = True
    value["provider"] = provider
    value["provider_model"] = model
    return value


class LocalModelAssistant:
    """A provider-neutral, dependency-free client for LM Studio and Ollama."""

    def __init__(self, *, transport: Transport = _urlopen_transport, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if not (0.1 <= timeout <= 300.0):
            raise LocalAIError("timeout must be between 0.1 and 300 seconds")
        self._transport = transport
        self._timeout = timeout

    def create_draft(
        self,
        provider: str,
        endpoint: str,
        model: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        base = _require_loopback_http(endpoint)
        provider_key = provider.strip().lower()
        user_content = json.dumps(dict(request), ensure_ascii=False, separators=(",", ":"))
        if provider_key == "lm_studio":
            url = base + "/v1/chat/completions"
            payload = {
                "model": model,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": FORMATION_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            }
        elif provider_key == "ollama":
            url = base + "/api/chat"
            payload = {
                "model": model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": FORMATION_PROMPT},
                    {"role": "user", "content": user_content},
                ],
            }
        else:
            raise LocalAIError("provider must be 'lm_studio' or 'ollama'")
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        raw = self._transport(url, encoded, {"Content-Type": "application/json"}, self._timeout, MAX_RESPONSE_BYTES)
        try:
            envelope = json.loads(raw.decode("utf-8"))
            if provider_key == "lm_studio":
                content = envelope["choices"][0]["message"]["content"]
            else:
                content = envelope["message"]["content"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LocalAIError("local AI provider returned an invalid response envelope") from exc
        return _fail_closed_draft(_extract_json(content), provider_key, model)

