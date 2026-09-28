# SPDX-License-Identifier: Apache-2.0
"""Public process-boundary adapter for the private SPIKES native runtime.

Milestone 0 intentionally does not translate PCB DesignIR geometry into a
qualified physics model and does not launch a solver.  The bridge prepares the
versioned envelope only after a separate, integrity-bound physics-model
artifact exists, and maps bounded public result fields back to AnalysisResult.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue


ADAPTER_ID = "spike.spikes-native-process/v0.1"
MAX_ISSUES = 256
MAX_SUMMARY_ITEMS = 128
MAX_CAPABILITY_BYTES = 256 * 1024
CAPABILITY_TIMEOUT_SECONDS = 5.0


class SpikesNativeAdapterError(ValueError):
    """A public boundary contract was unsafe or unsupported."""


def capability_manifest() -> Dict[str, Any]:
    """Return the intentionally narrow public Milestone 0 capability."""
    return {
        "contract": "spike/native-capability/v1",
        "adapter": ADAPTER_ID,
        "status": "integration_pending",
        "abi_version": 1,
        "capabilities": ["probe", "self_test"],
        "verification_capabilities": [
            "reference_diffusion_1d_verification",
            "reference_diffusion_fem_2d_verification",
            "prepared_frequency_domain_maxwell_compact_verification",
            "prepared_modal_dtn_operator_sweep_verification",
            "prepared_rational_network_conditioning_verification",
        ],
        "physics": [],
        "process_interface": [
            "spike-native-solver",
            "--request",
            "<job>/request.json",
            "--result",
            "<job>/result.json",
        ],
    }


def resolve_runtime_executable(configured_path: str = "") -> str:
    """Resolve an explicitly configured or PATH-discovered SPIKES executable.

    A development checkout is intentionally never embedded in product code.
    Installers and developer settings may provide ``SPIKES_NATIVE_SOLVER`` or
    an absolute path; otherwise normal executable discovery is used.
    """
    candidate = configured_path.strip() if isinstance(configured_path, str) else ""
    if not candidate:
        candidate = os.environ.get("SPIKES_NATIVE_SOLVER", "").strip()
    if not candidate:
        candidate = shutil.which("spike-native-solver") or shutil.which("spike-native-solver.exe") or ""
    if not candidate:
        return ""
    path = Path(candidate).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return ""
    return str(resolved) if resolved.is_file() else ""


def _strict_json_object(data: bytes) -> Dict[str, Any]:
    if len(data) > MAX_CAPABILITY_BYTES:
        raise SpikesNativeAdapterError("native capability output exceeds the public bound")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SpikesNativeAdapterError(f"native capability contains duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SpikesNativeAdapterError("native capability output is not strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise SpikesNativeAdapterError("native capability output must be an object")
    return value


def _validate_runtime_manifest(value: Dict[str, Any]) -> Dict[str, Any]:
    required = {
        "contract", "abi_version", "engine", "engine_version", "scalar_type",
        "index_type", "execution", "backends", "contracts", "capabilities",
        "validation_state", "limitations",
    }
    if not required.issubset(value):
        raise SpikesNativeAdapterError("native capability output omits required fields")
    if value.get("contract") != "spike/native-capability/v1" or value.get("abi_version") != 1:
        raise SpikesNativeAdapterError("native capability contract or ABI is incompatible")
    if value.get("engine") != "spike-native-solver":
        raise SpikesNativeAdapterError("native capability engine identity is incompatible")
    if value.get("scalar_type") != "real64" or value.get("index_type") != "int64":
        raise SpikesNativeAdapterError("native scalar or index representation is incompatible")
    for field, limit in (("execution", 16), ("contracts", 64), ("capabilities", 64), ("limitations", 128)):
        items = value.get(field)
        if (
            not isinstance(items, list)
            or len(items) > limit
            or len(items) != len(set(items))
            or any(not isinstance(item, str) or not item for item in items)
        ):
            raise SpikesNativeAdapterError(f"native capability field {field} is outside the public bound")
    prepared = value.get("prepared_capabilities", [])
    if (
        not isinstance(prepared, list)
        or len(prepared) > 64
        or len(prepared) != len(set(prepared))
        or any(not isinstance(item, str) or not item for item in prepared)
    ):
        raise SpikesNativeAdapterError("native prepared capability declaration is invalid")
    if value.get("mpi", "none") not in {"none", "ms-mpi", "open-mpi"}:
        raise SpikesNativeAdapterError("native MPI declaration is invalid")
    build_identity = value.get("build_identity", {})
    if not isinstance(build_identity, dict) or len(build_identity) > 64 or any(
        not isinstance(key, str)
        or not key
        or not isinstance(item, (str, bool, int))
        for key, item in build_identity.items()
    ):
        raise SpikesNativeAdapterError("native build identity declaration is invalid")
    if value.get("validation_state") not in {"verification_only", "unvalidated", "qualified"}:
        raise SpikesNativeAdapterError("native capability validation state is unsupported")
    backends = value.get("backends")
    if not isinstance(backends, dict) or len(backends) > 64 or any(
        not isinstance(key, str) or not isinstance(enabled, bool) for key, enabled in backends.items()
    ):
        raise SpikesNativeAdapterError("native backend declaration is invalid")
    return value


def probe_runtime_capabilities(configured_path: str = "") -> Dict[str, Any]:
    """Probe one local runtime without granting it PCB-product eligibility."""
    executable = resolve_runtime_executable(configured_path)
    if not executable:
        return {
            "status": "not_found",
            "executable": "",
            "trust": "discovery_only",
            "product_physics_eligible": False,
            "reason": "No configured spike-native-solver executable was found.",
        }
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        with tempfile.TemporaryFile() as output:
            completed = subprocess.run(
                [executable, "--capabilities"],
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
                shell=False,
                timeout=CAPABILITY_TIMEOUT_SECONDS,
                creationflags=creationflags,
                check=False,
            )
            size = output.tell()
            if size > MAX_CAPABILITY_BYTES:
                raise SpikesNativeAdapterError("native capability output exceeds the public bound")
            output.seek(0)
            payload = output.read(MAX_CAPABILITY_BYTES + 1)
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "status": "probe_failed",
            "executable": executable,
            "trust": "discovery_only",
            "product_physics_eligible": False,
            "reason": str(exc)[:4096],
        }
    if completed.returncode != 0:
        return {
            "status": "probe_failed",
            "executable": executable,
            "trust": "discovery_only",
            "product_physics_eligible": False,
            "reason": f"Capability process exited with code {completed.returncode}.",
        }
    try:
        manifest = _validate_runtime_manifest(_strict_json_object(payload))
    except SpikesNativeAdapterError as exc:
        return {
            "status": "incompatible",
            "executable": executable,
            "trust": "discovery_only",
            "product_physics_eligible": False,
            "reason": str(exc),
        }
    return {
        "status": "available",
        "executable": executable,
        "trust": "discovery_only",
        "product_physics_eligible": False,
        "reason": "Runtime is available for declared verification workloads only; PCB physics is not qualified.",
        "manifest": manifest,
    }


def _artifact_reference(value: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"path", "sha256", "bytes"}
    if not isinstance(value, dict) or set(value) != allowed:
        raise SpikesNativeAdapterError("model artifact must contain exactly path, sha256, and bytes")
    path, digest, size = value["path"], value["sha256"], value["bytes"]
    normalized = path.replace("\\", "/") if isinstance(path, str) else ""
    parts = normalized.split("/")
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or any(part in ("", ".", "..") for part in parts):
        raise SpikesNativeAdapterError("model artifact path must be normalized and job-relative")
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise SpikesNativeAdapterError("model artifact SHA-256 must be lowercase hexadecimal")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1 or size > 64 * 1024 * 1024:
        raise SpikesNativeAdapterError("model artifact size is outside the Milestone 0 bound")
    return {"path": normalized, "sha256": digest, "bytes": size}


def prepare_job_envelope(
    design: DesignIR,
    spec: AnalysisSpec,
    model_artifact: Dict[str, Any],
    *,
    request_id: str,
) -> Dict[str, Any]:
    """Map public request identity/resources to the native job envelope.

    ``model_artifact`` must refer to an independently normalized
    ``spike/physics-model/v1`` document.  This adapter never claims that a PCB
    DesignIR is itself an executable finite-element model.
    """
    if not isinstance(design, DesignIR) or not isinstance(spec, AnalysisSpec):
        raise SpikesNativeAdapterError("DesignIR and AnalysisSpec instances are required")
    if not isinstance(request_id, str) or re.fullmatch(r"[a-z][a-z0-9._-]{1,127}", request_id) is None:
        raise SpikesNativeAdapterError("request_id is outside the public bound")
    options = spec.options if isinstance(spec.options, dict) else {}
    resources = options.get("native_resources", {})
    if not isinstance(resources, dict):
        raise SpikesNativeAdapterError("native_resources must be an object")
    ranks = resources.get("ranks", 1)
    threads = resources.get("threads", 1)
    memory = resources.get("max_memory_bytes", 512 * 1024 * 1024)
    wall = resources.get("max_wall_time_s", 600.0)
    for name, value, low, high in (
        ("ranks", ranks, 1, 65536),
        ("threads", threads, 1, 4096),
        ("max_memory_bytes", memory, 16 * 1024 * 1024, 1 << 50),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise SpikesNativeAdapterError(f"{name} is outside the native resource bound")
    if not isinstance(wall, (int, float)) or isinstance(wall, bool) or not 0 < float(wall) <= 604800:
        raise SpikesNativeAdapterError("max_wall_time_s is outside the native resource bound")
    study = options.get("native_study")
    if not isinstance(study, dict):
        raise SpikesNativeAdapterError(
            "integration_pending: AnalysisSpec requires an explicit reviewed options.native_study"
        )
    allowed_study = {"type", "integrator", "time_step", "steps"}
    if study.get("type") == "frequency_domain":
        # Frequencies, material coefficients, ports and prepared operators live
        # in the SHA-bound model, not unvalidated job-level override fields.
        if set(study) != {"type"}:
            raise SpikesNativeAdapterError("frequency_domain study accepts only type; bind all solver inputs in the model artifact")
    elif set(study) - allowed_study or study.get("type") not in ("stationary", "transient"):
        raise SpikesNativeAdapterError("native_study is outside the Milestone 0 vocabulary")
    requested_outputs = options.get("native_requested_outputs", ["summary", "issues"])
    output_allowlist = {"summary", "issues", "fields", "mesh", "convergence", "conservation", "profiling", "checkpoint"}
    if not isinstance(requested_outputs, list) or not requested_outputs or len(requested_outputs) > 64 or any(value not in output_allowlist for value in requested_outputs):
        raise SpikesNativeAdapterError("native_requested_outputs contains an unsupported value")
    return {
        "contract": "spike/solver-job/v1",
        "request_id": request_id,
        "model": _artifact_reference(model_artifact),
        "study": dict(study),
        "resources": {
            "max_memory_bytes": memory,
            "max_wall_time_s": float(wall),
            "ranks": ranks,
            "threads": threads,
        },
        "deterministic": bool(options.get("deterministic", True)),
        "requested_outputs": list(requested_outputs),
    }


def _safe_summary_items(summary: Dict[str, Any]) -> Iterable[tuple[str, Any]]:
    for index, (key, value) in enumerate(summary.items()):
        if index >= MAX_SUMMARY_ITEMS:
            break
        if isinstance(key, str) and isinstance(value, (str, int, float, bool)) and not isinstance(value, complex):
            yield key, value


def map_result_bundle(result: Dict[str, Any], spec: AnalysisSpec) -> AnalysisResult:
    """Map a bounded ``result-bundle/v2`` without trusting arbitrary payloads."""
    if not isinstance(result, dict) or result.get("contract") != "spike/result-bundle/v2":
        raise SpikesNativeAdapterError("native result must be spike/result-bundle/v2")
    issues = []
    raw_issues = result.get("issues", [])
    if not isinstance(raw_issues, list):
        raise SpikesNativeAdapterError("native result issues must be an array")
    for raw in raw_issues[:MAX_ISSUES]:
        if not isinstance(raw, dict):
            continue
        issues.append(ValidationIssue(
            code=str(raw.get("code", "SPIKES-ADAPTER-UNKNOWN"))[:128],
            severity=str(raw.get("severity", "error"))[:16],
            message=str(raw.get("message", "Native runtime issue"))[:4096],
            path=str(raw.get("path", ""))[:1024],
            suggestion=str(raw.get("suggestion", ""))[:4096],
        ))
    raw_summary = result.get("summary", {})
    if not isinstance(raw_summary, dict):
        raise SpikesNativeAdapterError("native result summary must be an object")
    provenance = result.get("provenance", {})
    if not isinstance(provenance, dict):
        raise SpikesNativeAdapterError("native result provenance must be an object")
    return AnalysisResult(
        analysis_id=spec.analysis_id,
        status=str(result.get("status", "failed")),
        mode=spec.mode,
        model_status=str(result.get("validation_state", "unsupported")),
        summary=dict(_safe_summary_items(raw_summary)),
        issues=issues,
        provenance={
            "adapter": ADAPTER_ID,
            "native_backend": str(provenance.get("backend", ""))[:256],
            "request_sha256": str(provenance.get("request_sha256", ""))[:64],
            "model_sha256": str(provenance.get("model_sha256", ""))[:64],
            "integration_status": "integration_pending",
        },
    )


__all__ = [
    "SpikesNativeAdapterError",
    "capability_manifest",
    "resolve_runtime_executable",
    "probe_runtime_capabilities",
    "prepare_job_envelope",
    "map_result_bundle",
]
