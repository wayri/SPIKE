"""Fail-closed validation for SPIKES whole-product competitive claims."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


GATE_CONTRACT = "spikes/competitive-release-gate/v1"
REQUIRED_GATES = (
    "compatibility.spice_language_models",
    "analysis.complete_modes",
    "devices.qualified_breadth",
    "extensions.compiled_models",
    "switching.converter_accuracy_convergence",
    "performance.public_corpora",
    "robustness.adversarial_corpus",
    "embedding.continuous_hil",
    "library.qualified_redistributable_models",
    "platform.cross_platform_reproducibility",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)


def validate_competitive_gate(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a gate record and derive whether a claim is eligible."""

    if value.get("contract") != GATE_CONTRACT:
        raise ValueError(f"Competitive gate must use {GATE_CONTRACT}.")
    raw_gates = value.get("gates")
    if not isinstance(raw_gates, list):
        raise ValueError("Competitive gate must contain a gate array.")
    gates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_gates:
        if not isinstance(raw, Mapping):
            raise ValueError("Every competitive gate must be an object.")
        gate_id = str(raw.get("id", ""))
        if gate_id not in REQUIRED_GATES or gate_id in seen:
            raise ValueError("Competitive gates must be unique required entries.")
        seen.add(gate_id)
        status = str(raw.get("status", ""))
        if status not in {"passed", "blocked"}:
            raise ValueError(f"Competitive gate {gate_id} has an invalid status.")
        evidence = raw.get("evidence", [])
        if status == "passed":
            if not isinstance(evidence, list) or not evidence:
                raise ValueError(f"Passed competitive gate {gate_id} requires evidence.")
            for item in evidence:
                if (
                    not isinstance(item, Mapping)
                    or not str(item.get("artifact", "")).strip()
                    or _SHA256.fullmatch(str(item.get("sha256", ""))) is None
                ):
                    raise ValueError(
                        f"Passed gate {gate_id} requires artifact and SHA-256 evidence."
                    )
        gates.append(dict(raw))
    if seen != set(REQUIRED_GATES):
        missing = sorted(set(REQUIRED_GATES) - seen)
        raise ValueError(f"Competitive gate is missing required entries: {missing}.")

    passed = sum(item["status"] == "passed" for item in gates)
    eligible = passed == len(REQUIRED_GATES)
    expected_status = "passed" if eligible else "blocked"
    if value.get("status") != expected_status or value.get("claim_eligible") is not eligible:
        raise ValueError("Competitive status and eligibility must be derived from all gates.")
    expected_summary = {
        "required_gates": len(REQUIRED_GATES),
        "passed_gates": passed,
        "blocked_gates": len(REQUIRED_GATES) - passed,
    }
    if value.get("summary") != expected_summary:
        raise ValueError("Competitive gate summary does not match its gate records.")
    return dict(value) | {"gates": gates, "summary": expected_summary}


def load_competitive_gate(path: str | Path) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("Competitive gate document must be a JSON object.")
    return validate_competitive_gate(raw)


__all__ = [
    "GATE_CONTRACT", "REQUIRED_GATES", "load_competitive_gate",
    "validate_competitive_gate",
]
