# SPDX-License-Identifier: Apache-2.0
"""Strict structured-workspace bridge to SPIKE's release-owned SPICE engine.

The bridge never accepts raw netlist text or a caller-selected executable/DLL.
It composes a reviewed visual workspace, verifies the exact netlist digest
reported by the owned kernel, bounds returned JSON, and removes host paths from
the public result.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Dict

from python.spikes.contracts import ProbeDescriptor
from python.spikes.netlist import parse_netlist

from .contracts import DesignIR
from .spice_workspace import compose_spice_workspace
from .spikes_runtime import engine_status, owned_library_path, run_netlist


REQUEST_CONTRACT = "spike/owned-spice-workspace-request/v1"
RESULT_CONTRACT = "spike/owned-spice-workspace-result/v1"
VALIDATION_CONTRACT = "spike/owned-spice-workspace-validation/v1"
MAX_NETLIST_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 64 * 1024 * 1024
MAX_PROBES = 256

_REQUEST_KEYS = {"contract", "request_id", "workspace", "probes", "resource_limits"}
_LIMIT_KEYS = {"maximum_netlist_bytes", "maximum_result_bytes", "maximum_probes"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _issue(code: str, message: str, path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": "error", "message": message, "path": path}


def _positive_integer(value: Any, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        return None
    return value


def _owned_engine_netlist(preview_netlist: str) -> str:
    """Remove only the composer's ngspice output-format hint.

    The owned parser has no file-output mode. Every other option directive is
    rejected so this compatibility step cannot become a general text filter.
    """
    output: list[str] = []
    for line in preview_netlist.splitlines():
        normalized = line.strip().lower()
        if normalized == ".options filetype=ascii":
            continue
        if normalized.startswith(".options"):
            raise ValueError("the structured workspace emitted an unsupported option directive")
        output.append(line)
    return "\n".join(output) + "\n"


def _engine_probe_bindings(
    probes: list[str], preview: Dict[str, Any],
) -> tuple[list[str], Dict[str, ProbeDescriptor]]:
    aliases = preview.get("node_aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError("the structured workspace did not provide node aliases")
    folded_aliases: Dict[str, str] = {}
    for source, destination in aliases.items():
        key = str(source).casefold()
        value = str(destination)
        if key in folded_aliases and folded_aliases[key] != value:
            raise ValueError("workspace node aliases are ambiguous under circuit-name normalization")
        folded_aliases[key] = value
    element_aliases = preview.get("element_aliases", {})
    if not isinstance(element_aliases, dict):
        raise ValueError("the structured workspace did not provide element aliases")
    folded_elements: Dict[str, str] = {}
    for source, destination in element_aliases.items():
        key = str(source).casefold()
        value = str(destination)
        if key in folded_elements and folded_elements[key] != value:
            raise ValueError("workspace element aliases are ambiguous under circuit-name normalization")
        folded_elements[key] = value

    engine_probes: list[str] = []
    bindings: Dict[str, ProbeDescriptor] = {}
    for expression in probes:
        requested = ProbeDescriptor.parse(expression)
        if requested.quantity == "node_voltage":
            translated_targets = []
            for target in requested.targets:
                translated = folded_aliases.get(target.casefold())
                if translated is None:
                    raise ValueError(f"probe references unknown workspace node {target!r}")
                translated_targets.append(translated)
            engine_expression = f"V({','.join(translated_targets)})"
        else:
            translated = folded_elements.get(requested.targets[0].casefold())
            if translated is None:
                raise ValueError(
                    f"probe references unknown workspace element {requested.targets[0]!r}"
                )
            prefix = "I" if requested.quantity == "element_current" else "P"
            engine_expression = f"{prefix}({translated})"
        engine_descriptor = ProbeDescriptor.parse(engine_expression)
        engine_probes.append(engine_descriptor.name)
        bindings[engine_descriptor.name] = requested
    return engine_probes, bindings


def _limits(request: Dict[str, Any]) -> tuple[Dict[str, int], list[Dict[str, str]]]:
    raw = request.get("resource_limits", {})
    issues: list[Dict[str, str]] = []
    if not isinstance(raw, dict) or set(raw) - _LIMIT_KEYS:
        return {}, [_issue(
            "SPIKE-BE-SPICE-E-0051",
            "resource_limits must contain only owned-SPICE byte and probe bounds.",
            "resource_limits",
        )]
    values = {
        "maximum_netlist_bytes": raw.get("maximum_netlist_bytes", MAX_NETLIST_BYTES),
        "maximum_result_bytes": raw.get("maximum_result_bytes", MAX_RESULT_BYTES),
        "maximum_probes": raw.get("maximum_probes", MAX_PROBES),
    }
    maxima = {
        "maximum_netlist_bytes": MAX_NETLIST_BYTES,
        "maximum_result_bytes": MAX_RESULT_BYTES,
        "maximum_probes": MAX_PROBES,
    }
    parsed: Dict[str, int] = {}
    for key, value in values.items():
        admitted = _positive_integer(value, maxima[key])
        if admitted is None:
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0051",
                f"{key} must be an integer from 1 to {maxima[key]}.",
                f"resource_limits.{key}",
            ))
        else:
            parsed[key] = admitted
    return parsed, issues


def validate_owned_spice_workspace_request(
    request: Dict[str, Any], design: DesignIR,
) -> Dict[str, Any]:
    issues: list[Dict[str, str]] = []
    if not isinstance(request, dict):
        issues.append(_issue("SPIKE-BE-SPICE-E-0050", "The owned-SPICE request must be an object."))
        request = {}
    unknown = sorted(set(request) - _REQUEST_KEYS)
    if unknown:
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0050", f"Unknown owned-SPICE request fields: {unknown}.",
        ))
    if request.get("contract") != REQUEST_CONTRACT:
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0050", f"Expected contract {REQUEST_CONTRACT}.", "contract",
        ))
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or _SAFE_ID.fullmatch(request_id) is None:
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0050", "request_id must be a bounded safe identifier.", "request_id",
        ))
    limits, limit_issues = _limits(request)
    issues.extend(limit_issues)

    probes = request.get("probes", [])
    if not isinstance(probes, list):
        issues.append(_issue("SPIKE-BE-SPICE-E-0050", "probes must be an array.", "probes"))
        probes = []
    maximum_probes = limits.get("maximum_probes", MAX_PROBES)
    if len(probes) > maximum_probes:
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0051", f"probes exceeds its admitted limit of {maximum_probes}.", "probes",
        ))
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for index, probe in enumerate(probes):
        if not isinstance(probe, str) or len(probe.encode("utf-8")) > 256:
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0050", "Probe descriptors must be unique bounded strings.", f"probes[{index}]",
            ))
            continue
        try:
            parsed_probe = ProbeDescriptor.parse(probe)
        except (TypeError, ValueError) as exc:
            issues.append(_issue("SPIKE-BE-SPICE-E-0050", str(exc), f"probes[{index}]"))
            continue
        probe_identity = (parsed_probe.quantity, parsed_probe.targets)
        if probe_identity in seen:
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0050",
                "Probe descriptors must be unique after canonicalization.",
                f"probes[{index}]",
            ))
            continue
        seen.add(probe_identity)

    workspace = request.get("workspace")
    if not isinstance(workspace, dict):
        issues.append(_issue("SPIKE-BE-SPICE-E-0050", "workspace must be an object.", "workspace"))
        preview = {"status": "blocked", "validation": {"can_run": False}}
    else:
        try:
            preview = compose_spice_workspace(workspace, design)
        except (KeyError, TypeError, ValueError) as exc:
            preview = {"status": "blocked", "validation": {"can_run": False}}
            issues.append(_issue("SPIKE-BE-SPICE-E-0052", str(exc), "workspace"))
    if preview.get("status") != "ready":
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0052", "The structured SPICE workspace did not compose successfully.", "workspace",
        ))
    else:
        try:
            owned_netlist = _owned_engine_netlist(str(preview["netlist"]))
        except ValueError as exc:
            issues.append(_issue("SPIKE-BE-SPICE-E-0052", str(exc), "workspace"))
            owned_netlist = ""
        if owned_netlist:
            try:
                engine_probes, _ = _engine_probe_bindings(probes, preview)
                parse_netlist(
                    owned_netlist,
                    source_name="<owned-workspace-validation>",
                    probes=tuple(ProbeDescriptor.parse(item) for item in engine_probes),
                    native_extensions=True,
                )
            except (TypeError, ValueError) as exc:
                issues.append(_issue("SPIKE-BE-SPICE-E-0052", str(exc), "probes"))
        netlist_bytes = len(owned_netlist.encode("utf-8"))
        if netlist_bytes > limits.get("maximum_netlist_bytes", MAX_NETLIST_BYTES):
            issues.append(_issue(
                "SPIKE-BE-SPICE-E-0051", "The composed netlist exceeds its admitted byte budget.", "workspace",
            ))

    status = engine_status()
    if not status.get("available"):
        issues.append(_issue(
            "SPIKE-BE-SPICE-E-0053", "The release-owned SPIKES circuit engine is unavailable.", "engine",
        ))
    return {
        "contract": VALIDATION_CONTRACT,
        "valid": not issues,
        "issues": issues,
        "workspace_validation": deepcopy(preview.get("validation", {})),
        "engine": {
            "available": bool(status.get("available")),
            "abi_version": status.get("abi_version"),
            "model_status": status.get("model_status", "experimental"),
            "execution_class": status.get("execution_class", "soft_realtime"),
        },
    }


def run_owned_spice_workspace(request: Dict[str, Any], design: DesignIR) -> Dict[str, Any]:
    validation = validate_owned_spice_workspace_request(request, design)
    if not validation["valid"]:
        return {
            "contract": RESULT_CONTRACT,
            "request_id": str(request.get("request_id", "")) if isinstance(request, dict) else "",
            "status": "blocked",
            "model_status": "unsupported",
            "issues": validation["issues"],
            "validation": validation,
            "circuit_result": None,
        }

    limits, _ = _limits(request)
    preview = compose_spice_workspace(request["workspace"], design)
    preview_netlist = str(preview["netlist"])
    netlist = _owned_engine_netlist(preview_netlist)
    engine_probes, probe_bindings = _engine_probe_bindings(
        list(request.get("probes", [])), preview,
    )
    encoded = netlist.encode("utf-8")
    if len(encoded) > limits["maximum_netlist_bytes"]:
        raise ValueError("composed netlist changed beyond its admitted byte budget")
    source_sha256 = hashlib.sha256(encoded).hexdigest()
    raw = run_netlist({"netlist": netlist, "probes": engine_probes})
    if not isinstance(raw, dict) or raw.get("contract") != "spikes/circuit-result/v1":
        raise RuntimeError("the owned engine returned an incompatible result contract")
    if raw.get("status") not in {"completed", "failed"}:
        raise RuntimeError("the owned engine returned an unsupported result status")
    if raw.get("model_status") != "experimental":
        raise RuntimeError("the owned engine returned an unsupported model status")
    for field in ("analysis", "data", "probes", "diagnostics", "measurements", "provenance"):
        if not isinstance(raw.get(field), dict):
            raise RuntimeError(f"the owned engine returned a malformed {field} field")
    if not isinstance(raw.get("issues"), list) or any(
        not isinstance(issue, dict) for issue in raw["issues"]
    ):
        raise RuntimeError("the owned engine returned a malformed issues field")
    provenance = raw.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("source_sha256") != source_sha256:
        raise RuntimeError("the owned engine result is not bound to the composed netlist")

    sanitized = deepcopy(raw)
    sanitized_probes: Dict[str, Any] = {}
    for engine_name, payload in sanitized["probes"].items():
        requested_probe = probe_bindings.get(engine_name)
        if requested_probe is None:
            raise RuntimeError("the owned engine returned an unrequested probe")
        rebound = deepcopy(payload)
        if not isinstance(rebound, dict):
            raise RuntimeError("the owned engine returned a malformed probe payload")
        rebound["descriptor"] = requested_probe.to_dict()
        sanitized_probes[requested_probe.name] = rebound
    if len(sanitized_probes) != len(probe_bindings):
        raise RuntimeError("the owned engine omitted a requested probe")
    sanitized["probes"] = sanitized_probes
    sanitized_provenance = dict(sanitized["provenance"])
    sanitized_provenance.pop("library", None)
    library = owned_library_path()
    sanitized_provenance.update({
        "library_origin": "release_owned",
        "library_name": library.name,
        "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "raw_netlist_accepted": False,
        "shell_invoked": False,
    })
    sanitized["provenance"] = sanitized_provenance
    canonical = json.dumps(
        sanitized, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if len(canonical) > limits["maximum_result_bytes"]:
        raise ValueError("owned engine result exceeds its admitted byte budget")
    return {
        "contract": RESULT_CONTRACT,
        "request_id": request["request_id"],
        "status": sanitized.get("status", "failed"),
        "model_status": sanitized.get("model_status", "experimental"),
        "issues": deepcopy(sanitized.get("issues", [])),
        "validation": validation,
        "netlist_sha256": source_sha256,
        "preview_netlist_sha256": hashlib.sha256(preview_netlist.encode("utf-8")).hexdigest(),
        "netlist_bytes": len(encoded),
        "result_bytes": len(canonical),
        "circuit_result": sanitized,
        "provenance": {
            "bridge": "python.spike_core.owned_spice_workspace",
            "workspace_contract": preview["validation"].get("contract", ""),
            "structured_workspace_only": True,
            "caller_selected_library": False,
            "filesystem_model_loading": False,
            "compatibility_normalization": "remove_exact_ngspice_ascii_filetype_hint",
        },
    }


__all__ = [
    "REQUEST_CONTRACT",
    "RESULT_CONTRACT",
    "VALIDATION_CONTRACT",
    "run_owned_spice_workspace",
    "validate_owned_spice_workspace_request",
]
