"""Fail-closed declarative SI protocol-suite contracts and staged planning."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping


CONTRACT = "spike/si-protocol-suite/v1"
VALIDATION_CONTRACT = "spike/si-protocol-suite-validation/v1"
PLAN_CONTRACT = "spike/si-protocol-analysis-plan/v1"
FAMILIES = {
    "DDR", "GDDR", "SERDES", "LVDS", "PCI", "PCIE", "PXI",
    "DISPLAYPORT", "HDMI", "USB", "ETHERNET", "MIPI", "SATA",
    "CXL", "JESD204", "HBM", "CUSTOM",
}
ANALYSES = {
    "topology", "impedance", "rlgc", "s_parameters", "tdr_tdt",
    "insertion_return_loss", "next_fext", "mode_conversion", "skew_delay",
    "eye", "jitter", "pam4", "power_aware", "compliance_review",
}
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,95}$", re.ASCII)
_ROOT_KEYS = {
    "contract", "id", "name", "family", "revision", "description",
    "signaling", "encoding", "topology", "requiredInputs", "analyses",
    "rules", "provenance", "qualification", "custom",
}


class SiProtocolSuiteError(ValueError):
    """Raised when a protocol suite is malformed or makes a forbidden claim."""


def _text(value: Any, path: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise SiProtocolSuiteError(f"{path} must be non-empty text of at most {limit} characters.")
    return value.strip()


def _string_list(value: Any, path: str, *, maximum: int = 64) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise SiProtocolSuiteError(f"{path} must contain 1-{maximum} entries.")
    return [_text(item, f"{path}[{index}]", 300) for index, item in enumerate(value)]


def canonical_si_protocol_suite(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SiProtocolSuiteError("The protocol suite must be an object.")
    unknown = set(value) - _ROOT_KEYS
    missing = _ROOT_KEYS - set(value)
    if unknown or missing:
        raise SiProtocolSuiteError(
            f"Protocol suite keys are invalid; missing={sorted(missing)}, unknown={sorted(unknown)}."
        )
    if value.get("contract") != CONTRACT:
        raise SiProtocolSuiteError(f"contract must be {CONTRACT}.")
    suite_id = _text(value.get("id"), "id", 96)
    if _ID.fullmatch(suite_id) is None:
        raise SiProtocolSuiteError("id must use lowercase letters, numbers, dot, underscore, or dash.")
    family = value.get("family")
    if family not in FAMILIES:
        raise SiProtocolSuiteError("family is not supported by this contract revision.")
    signaling = value.get("signaling")
    if signaling not in {"single_ended", "differential", "parallel_bus", "mixed"}:
        raise SiProtocolSuiteError("signaling is not supported.")
    encoding = value.get("encoding")
    if encoding not in {"NRZ", "PAM4", "mixed", "user_defined"}:
        raise SiProtocolSuiteError("encoding is not supported.")
    qualification = value.get("qualification")
    if qualification not in {"setup_only", "experimental", "validated"}:
        raise SiProtocolSuiteError("qualification is not supported.")
    custom = value.get("custom")
    if not isinstance(custom, bool):
        raise SiProtocolSuiteError("custom must be boolean.")
    if custom and qualification == "validated":
        raise SiProtocolSuiteError("A custom suite cannot self-assert validated qualification.")

    raw_analyses = value.get("analyses")
    if not isinstance(raw_analyses, list) or not 1 <= len(raw_analyses) <= 32:
        raise SiProtocolSuiteError("analyses must contain 1-32 entries.")
    analyses: list[Dict[str, Any]] = []
    seen_analyses: set[str] = set()
    for index, raw in enumerate(raw_analyses):
        if not isinstance(raw, Mapping) or set(raw) != {"id", "name", "requiredCapabilities", "status"}:
            raise SiProtocolSuiteError(f"analyses[{index}] has invalid fields.")
        analysis_id = raw.get("id")
        if analysis_id not in ANALYSES or analysis_id in seen_analyses:
            raise SiProtocolSuiteError(f"analyses[{index}].id is unsupported or duplicated.")
        seen_analyses.add(str(analysis_id))
        capabilities = raw.get("requiredCapabilities")
        if not isinstance(capabilities, list) or len(capabilities) > 32:
            raise SiProtocolSuiteError(f"analyses[{index}].requiredCapabilities is invalid.")
        canonical_capabilities: list[str] = []
        for capability_index, capability in enumerate(capabilities):
            name = _text(capability, f"analyses[{index}].requiredCapabilities[{capability_index}]", 96)
            if _ID.fullmatch(name) is None:
                raise SiProtocolSuiteError(f"Capability {name!r} is not canonical.")
            canonical_capabilities.append(name)
        if len(set(canonical_capabilities)) != len(canonical_capabilities):
            raise SiProtocolSuiteError(f"analyses[{index}] repeats a capability.")
        status = raw.get("status")
        if status not in {"available_input_review", "solver_gated"}:
            raise SiProtocolSuiteError(f"analyses[{index}].status is unsupported.")
        analyses.append({
            "id": analysis_id,
            "name": _text(raw.get("name"), f"analyses[{index}].name", 160),
            "requiredCapabilities": canonical_capabilities,
            "status": status,
        })

    raw_rules = value.get("rules")
    if not isinstance(raw_rules, list) or len(raw_rules) > 256:
        raise SiProtocolSuiteError("rules must contain at most 256 entries.")
    rules: list[Dict[str, Any]] = []
    seen_rules: set[str] = set()
    allowed_rule_keys = {"id", "metric", "operator", "value", "maximum", "unit", "source", "note"}
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, Mapping) or set(raw) - allowed_rule_keys:
            raise SiProtocolSuiteError(f"rules[{index}] has invalid fields.")
        rule_id = _text(raw.get("id"), f"rules[{index}].id", 96)
        if _ID.fullmatch(rule_id) is None or rule_id in seen_rules:
            raise SiProtocolSuiteError(f"rules[{index}].id is invalid or duplicated.")
        seen_rules.add(rule_id)
        operator = raw.get("operator")
        if operator not in {"minimum", "maximum", "range", "informational"}:
            raise SiProtocolSuiteError(f"rules[{index}].operator is unsupported.")
        number = raw.get("value")
        upper = raw.get("maximum")
        if operator != "informational" and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number)):
            raise SiProtocolSuiteError(f"rules[{index}].value must be finite.")
        if operator == "range" and (isinstance(upper, bool) or not isinstance(upper, (int, float)) or not math.isfinite(upper) or upper < number):
            raise SiProtocolSuiteError(f"rules[{index}].maximum is invalid.")
        rules.append({key: deepcopy(raw[key]) for key in sorted(raw)})

    provenance = value.get("provenance")
    if not isinstance(provenance, Mapping) or set(provenance) != {"title", "locator", "access", "reviewedOn"}:
        raise SiProtocolSuiteError("provenance fields are invalid.")
    access = provenance.get("access")
    if access not in {"public_overview", "licensed_standard_required", "user_defined"}:
        raise SiProtocolSuiteError("provenance.access is unsupported.")
    canonical = {
        "contract": CONTRACT,
        "id": suite_id,
        "name": _text(value.get("name"), "name", 160),
        "family": family,
        "revision": _text(value.get("revision"), "revision", 80),
        "description": _text(value.get("description"), "description", 2000),
        "signaling": signaling,
        "encoding": encoding,
        "topology": _string_list(value.get("topology"), "topology"),
        "requiredInputs": _string_list(value.get("requiredInputs"), "requiredInputs"),
        "analyses": analyses,
        "rules": rules,
        "provenance": {
            "title": _text(provenance.get("title"), "provenance.title", 300),
            "locator": _text(provenance.get("locator"), "provenance.locator", 1000),
            "access": access,
            "reviewedOn": _text(provenance.get("reviewedOn"), "provenance.reviewedOn", 32),
        },
        "qualification": qualification,
        "custom": custom,
    }
    return canonical


def suite_digest(suite: Mapping[str, Any]) -> str:
    canonical = canonical_si_protocol_suite(suite)
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_si_protocol_suite(suite: Mapping[str, Any]) -> Dict[str, Any]:
    canonical = canonical_si_protocol_suite(suite)
    return {
        "contract": VALIDATION_CONTRACT,
        "status": "valid",
        "suite_id": canonical["id"],
        "suite_sha256": suite_digest(canonical),
        "qualification": canonical["qualification"],
        "compliance_claimed": False,
        "code_execution": "not_permitted_by_declarative_contract",
    }


def plan_si_protocol_analysis(suite: Mapping[str, Any], available_capabilities: Iterable[str]) -> Dict[str, Any]:
    canonical = canonical_si_protocol_suite(suite)
    available = {str(item) for item in available_capabilities}
    stages = []
    for analysis in canonical["analyses"]:
        missing = sorted(set(analysis["requiredCapabilities"]) - available)
        configurable = analysis["id"] == "topology"
        stages.append({
            "analysis_id": analysis["id"],
            "name": analysis["name"],
            "status": "configurable" if configurable else "blocked" if missing else "ready_for_experimental_execution",
            "missing_capabilities": missing,
            "compliance_claimed": False,
        })
    return {
        "contract": PLAN_CONTRACT,
        "suite_id": canonical["id"],
        "suite_sha256": suite_digest(canonical),
        "qualification": canonical["qualification"],
        "compliance_claimed": False,
        "stages": stages,
        "can_claim_protocol_compliance": False,
    }
