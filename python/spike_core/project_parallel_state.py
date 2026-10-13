# SPDX-License-Identifier: Apache-2.0
"""Offline admission of portable parallel drafts and execution history."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from typing import Any, Callable

from .parallel_pool import _digest, validate_batch

CONTRACT = "spike/parallel-workspace/v1"
REFERENCE = "spike/state-artifact-reference/v1"
MAX_BYTES = 96 * 1024 * 1024
STATUSES = {"completed", "completed_with_errors", "cancelled", "failed", "interrupted"}
_PRIVATE = re.compile(r"-----BEGIN [^-]*(?:PRIVATE KEY|CERTIFICATE)-----", re.I)
_FORBIDDEN = {
    "enrollment", "clusterenrollment", "clusterconfig", "host", "hostname",
    "address", "endpoint", "url", "privatekey", "keyfile", "keypath", "certfile", "certpath",
    "certificatepath", "cafile", "capath", "password", "passphrase", "secret", "token",
    "apikey", "accesstoken", "authorization", "credentials", "clientkey", "clientcert",
    "certificate", "trustcert", "servername",
}


def _forbidden_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in _FORBIDDEN or normalized.endswith(("password", "privatekey", "secret", "token", "certpath", "keypath"))


def empty_parallel_state() -> dict:
    return {"contract": CONTRACT, "draft": {"jobs_json": "[]", "concurrency": "1",
            "threads_per_job": "1", "timeout_s": "120"}, "runs": []}


def _check_tree(value: Any) -> None:
    """Bound depth, nodes and bytes before copying or encoding arbitrary metadata."""
    stack = [(value, 0)]
    nodes = size = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 2_000_000 or depth > 48:
            raise ValueError("Parallel workspace exceeds its structural limit.")
        if isinstance(item, dict):
            if len(item) > 4096 or any(not isinstance(key, str) for key in item):
                raise ValueError("Parallel workspace has invalid object keys.")
            for key, child in item.items():
                if _forbidden_key(key):
                    raise ValueError(f"Parallel workspace cannot contain credential or connection field {key!r}.")
                size += len(key.encode("utf-8"))
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            if len(item) > 1_000_000:
                raise ValueError("Parallel workspace array exceeds its limit.")
            stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            size += len(item.encode("utf-8"))
            if _PRIVATE.search(item) or item == "spike/cluster-enrollment/v1":
                raise ValueError("Parallel workspace cannot contain enrollment or PEM credentials.")
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("Parallel workspace numbers must be finite.")
        elif isinstance(item, int):
            if item.bit_length() > 1024:
                raise ValueError("Parallel workspace integer exceeds its limit.")
        elif item is not None:
            raise ValueError("Parallel workspace must contain only JSON values.")
        if size > MAX_BYTES:
            raise ValueError("Parallel workspace exceeds its 96 MiB limit.")


def _admit_result(request: dict, result: dict, status: str) -> None:
    _check_tree(result)
    contract = result.get("contract")
    cluster = contract == "spike/cluster-batch-result/v1"
    if not cluster and contract != "spike/parallel-batch-result/v1":
        raise ValueError("Parallel saved result has an unsupported contract.")
    if cluster and (result.get("execution") != "independent_jobs" or result.get("distributed_single_solve") != "unsupported"):
        raise ValueError("Parallel cluster result has invalid execution semantics.")
    lineage = result if cluster else result.get("provenance")
    if not isinstance(lineage, dict) or lineage.get("request_sha256") != _digest(request):
        raise ValueError("Parallel saved result request digest mismatch.")
    jobs = result.get("jobs" if cluster else "outcomes")
    if (not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs)
            or [job.get("id") for job in jobs] != [job["id"] for job in request["jobs"]]):
        raise ValueError("Parallel saved result job order or identity mismatch.")
    for job, expected in zip(jobs, request["jobs"]):
        if cluster and (not isinstance(job.get("node_id"), str) or not 1 <= len(job["node_id"]) <= 1024
                        or any(ord(char) < 32 for char in job["node_id"])):
            raise ValueError("Parallel cluster result has invalid node identity.")
        if cluster and job.get("state") == "unknown":
            if not isinstance(job.get("node_id"), str) or not isinstance(job.get("error"), str) or job.get("ok") is True:
                raise ValueError("Invalid unknown cluster outcome.")
            continue
        if cluster and (not isinstance(job.get("node_certificate_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", job["node_certificate_sha256"])):
            raise ValueError("Parallel cluster result has invalid certificate fingerprint.")
        provenance = job.get("provenance")
        if (job.get("method") != expected["method"] or type(job.get("ok")) is not bool
                or not isinstance(provenance, dict) or provenance.get("request_sha256") != _digest(expected)):
            raise ValueError("Parallel saved job request digest or method mismatch.")
        if job["ok"]:
            if job.get("status") != "completed":
                raise ValueError("Successful parallel outcome must be completed.")
            response = {"id": job["id"], "ok": True, "result": job.get("result"), "meta": job.get("worker_meta")}
            if provenance.get("response_sha256") != _digest(response):
                raise ValueError("Parallel saved job response digest mismatch.")
        else:
            if "result" in job or not isinstance(job.get("error"), dict) or job.get("status") not in {"failed", "cancelled", "timed_out"}:
                raise ValueError("Failed parallel outcome must contain an error and no result.")
            if "worker_meta" in job and "response_sha256" in provenance:
                response = {"id": job["id"], "ok": False, "error": job["error"], "meta": job["worker_meta"]}
                if provenance["response_sha256"] != _digest(response):
                    raise ValueError("Failed parallel job response digest mismatch.")
    expected_status = ("cancelled" if any(job.get("status") == "cancelled" for job in jobs)
                       else "completed_with_errors" if any(job.get("ok") is not True for job in jobs)
                       else "completed")
    if status != expected_status or (not cluster and result.get("status") != expected_status):
        raise ValueError("Parallel saved result status does not match its outcomes.")


def validate_parallel_state(value: Any, *, resolve: Callable[[str], bytes] | None = None) -> dict:
    """Validate without executing jobs; preserve complete result fields and references."""
    if value is None:
        return empty_parallel_state()
    _check_tree(value)
    if not isinstance(value, dict) or set(value) != {"contract", "draft", "runs"} or value["contract"] != CONTRACT:
        raise ValueError("Invalid parallel workspace contract or fields.")
    draft = value["draft"]
    if (not isinstance(draft, dict) or set(draft) != set(empty_parallel_state()["draft"])
            or any(not isinstance(item, str) for item in draft.values())
            or len(draft["jobs_json"].encode("utf-8")) > 4 * 1024 * 1024
            or any(len(draft[key]) > 128 for key in draft if key != "jobs_json")):
        raise ValueError("Invalid parallel workspace draft.")
    try:
        draft_json = json.loads(draft["jobs_json"])
    except json.JSONDecodeError:
        # Detect ordinary quoted credential keys even while their value is unfinished.
        for match in re.finditer(r'"((?:[^"\\]|\\.)*)"\s*:', draft["jobs_json"]):
            try:
                key = json.loads('"' + match.group(1) + '"')
            except json.JSONDecodeError:
                continue
            if _forbidden_key(key):
                raise ValueError("Parallel draft cannot contain credential or connection fields.")
    except (RecursionError, ValueError) as exc:
        raise ValueError("Parallel draft exceeds JSON parser limits.") from exc
    else:
        _check_tree(draft_json)
    runs = value["runs"]
    if not isinstance(runs, list) or len(runs) > 32:
        raise ValueError("Parallel workspace retains at most 32 runs.")
    seen = set()
    total_result_bytes = 0
    for run in runs:
        if (not isinstance(run, dict) or not {"id", "request", "result", "status"} <= set(run)
                or set(run) - {"id", "request", "result", "status", "error"}
                or not isinstance(run["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", run["id"])
                or run["id"] in seen or not isinstance(run["status"], str) or run["status"] not in STATUSES
                or ("error" in run and (not isinstance(run["error"], str) or len(run["error"]) > 4096))):
            raise ValueError("Invalid parallel workspace run.")
        seen.add(run["id"])
        request = validate_batch(run["request"], cpu_budget=256)
        result = run["result"]
        if result is None:
            if run["status"] not in {"interrupted", "failed", "cancelled"}:
                raise ValueError("Completed parallel run requires its result.")
            continue
        if not isinstance(result, dict):
            raise ValueError("Parallel run result must be an object or null.")
        if result.get("contract") == REFERENCE:
            if (set(result) != {"contract", "path", "sha256", "bytes"}
                    or not isinstance(result.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", result["sha256"])
                    or result.get("path") != f"state/artifacts/{result['sha256']}.json"
                    or type(result.get("bytes")) is not int or not 0 < result["bytes"] <= MAX_BYTES or resolve is None):
                raise ValueError("Parallel saved result reference is invalid or unavailable.")
            total_result_bytes += result["bytes"]
            if total_result_bytes > MAX_BYTES:
                raise ValueError("Parallel saved results exceed the 96 MiB limit.")
            data = resolve(result["path"])
            if len(data) != result["bytes"] or hashlib.sha256(data).hexdigest() != result["sha256"]:
                raise ValueError("Parallel saved result artifact digest mismatch.")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("Parallel saved result artifact must contain an object.")
        _admit_result(request, result, run["status"])
    if len(json.dumps(value, allow_nan=False).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Parallel workspace exceeds its 96 MiB limit.")
    return copy.deepcopy(value)


def admit_payload_parallel(payload: dict, *, resolve: Callable[[str], bytes] | None = None) -> None:
    """Normalize both canonical and desktop copies at package boundaries."""
    from .project_package import ProjectPackageError
    try:
        analyses = payload.setdefault("analyses", {})
        if not isinstance(analyses, dict):
            raise ValueError("Project analyses must be an object.")
        if "parallel_execution" in analyses:
            analyses["parallel_execution"] = validate_parallel_state(analyses["parallel_execution"], resolve=resolve)
        legacy = payload.get("extensions", {}).get("legacy")
        if isinstance(legacy, dict) and isinstance(legacy.get("analysis"), dict):
            analysis = legacy["analysis"]
            if "parallel_execution" in analysis:
                analysis["parallel_execution"] = validate_parallel_state(analysis["parallel_execution"], resolve=resolve)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        raise ProjectPackageError(f"Invalid parallel workspace: {exc}") from exc


def admit_archive_parallel(payload: dict, archive: Any, infos: dict, declared: dict) -> None:
    from .project_package import ProjectPackageError, _verify_member_stream
    def resolve(name: str) -> bytes:
        record = declared.get(name)
        if record is None or record.get("size", 0) > MAX_BYTES:
            raise ProjectPackageError("Parallel result artifact is missing or oversized.")
        return _verify_member_stream(archive, infos[name], expected_size=record["size"],
                                     expected_sha256=record["sha256"], retain=True) or b""
    admit_payload_parallel(payload, resolve=resolve)
