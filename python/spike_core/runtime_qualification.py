"""Deterministic source-versus-packaged worker release qualification.

The desktop bundle must not advertise a different numerical product than the
source runtime used to build it.  This module keeps that check independent of
PyInstaller so it can be exercised by tests, CI, and other package formats.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


QUALIFICATION_CONTRACT = "spike/release-runtime-qualification/v1"
SNAPSHOT_CONTRACT = "spike/worker-runtime-snapshot/v1"
QUALIFICATION_METHODS = (
    "health",
    "capabilities",
    "capability_ledger",
    "list_accelerators",
    "list_external_engines",
    "benchmarks",
)


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _without_reason(record: Mapping[str, Any]) -> dict[str, Any]:
    """Remove diagnostic prose while retaining executable capability state."""

    return {key: value for key, value in record.items() if key not in {"reason", "executable"}}


def normalize_runtime_results(
    results: Mapping[str, Any],
    *,
    collection_errors: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Reduce protocol responses to stable release-significant fields."""

    missing = [method for method in QUALIFICATION_METHODS if method not in results]
    if missing:
        raise ValueError(f"Runtime snapshot is missing methods: {', '.join(missing)}")
    health = results["health"]
    capabilities = results["capabilities"]
    accelerators = results["list_accelerators"]
    external = results["list_external_engines"]
    benchmarks = results["benchmarks"]
    plugins = sorted(
        (_without_reason(item) for item in capabilities.get("solver_plugins", [])),
        key=lambda item: str(item.get("id", "")),
    )
    accelerator_backends = sorted(
        (_without_reason(item) for item in accelerators.get("backends", [])),
        key=lambda item: str(item.get("id", "")),
    )
    external_engines = sorted(
        (
            {
                key: value
                for key, value in _without_reason(item).items()
                if key not in {"runtime_validation", "qualification"}
            }
            for item in external.get("engines", [])
        ),
        key=lambda item: str(item.get("id", "")),
    )
    return {
        "contract": SNAPSHOT_CONTRACT,
        "collection_errors": sorted(
            (dict(item) for item in collection_errors),
            key=lambda item: str(item.get("method", "")),
        ),
        "health": {
            key: health.get(key)
            for key in ("contract", "status", "worker_version", "analysis_contract", "protocol")
        },
        "product_capabilities": {
            key: capabilities.get(key)
            for key in (
                "contract",
                "version",
                "analyses",
                "imports",
                "geometry",
                "network_data",
                "models",
                "solver_runtime",
                "layout_automation",
                "extension_runtime",
            )
        },
        "solver_plugins": plugins,
        "capability_ledger": results["capability_ledger"],
        "accelerators": {
            "contract": accelerators.get("contract"),
            "backends": accelerator_backends,
        },
        "external_engines": {
            "contract": external.get("contract"),
            "engines": external_engines,
        },
        "benchmarks": {
            "contract": benchmarks.get("contract"),
            "status": benchmarks.get("status"),
            "summary": benchmarks.get("summary", {}),
            "cases": [
                {
                    "name": item.get("name"),
                    "status": item.get("status"),
                    "measured": item.get("measured"),
                    "expected": item.get("expected"),
                    "relative_error": item.get("relative_error"),
                    "tolerance": item.get("tolerance"),
                    "units": item.get("units"),
                }
                for item in benchmarks.get("benchmarks", [])
            ],
        },
    }


def collect_runtime_snapshot(
    command: Sequence[str],
    *,
    cwd: str | Path,
    timeout_seconds: int = 180,
    environment_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Query one JSON-line worker process and return a normalized snapshot."""

    requests = [
        json.dumps({"id": f"qualify-{method}", "method": method, "params": {}})
        for method in QUALIFICATION_METHODS
    ]
    environment = os.environ.copy()
    environment.update(
        {"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    )
    if environment_overrides:
        environment.update(environment_overrides)
    process = subprocess.run(
        list(command),
        cwd=str(cwd),
        input="\n".join(requests) + "\n",
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        env=environment,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"Worker qualification process exited with {process.returncode}: {process.stderr.strip()}"
        )
    lines = [line for line in process.stdout.splitlines() if line.strip()]
    if len(lines) != len(QUALIFICATION_METHODS):
        raise RuntimeError(
            f"Worker emitted {len(lines)} qualification responses; expected {len(QUALIFICATION_METHODS)}."
        )
    results: dict[str, Any] = {}
    collection_errors: list[dict[str, Any]] = []
    for method, line in zip(QUALIFICATION_METHODS, lines):
        response = json.loads(line)
        if response.get("ok") is not True:
            detail = response.get("error_detail") or {}
            collection_errors.append(
                {
                    "method": method,
                    "type": response.get("type"),
                    "error_code": response.get("error_code") or detail.get("code"),
                }
            )
            results[method] = {}
            continue
        results[method] = response.get("result", {})
    return normalize_runtime_results(results, collection_errors=collection_errors)


def _check(identifier: str, source: Any, packaged: Any) -> dict[str, Any]:
    passed = source == packaged
    return {
        "id": identifier,
        "required": True,
        "status": "passed" if passed else "failed",
        "source_digest": canonical_digest(source),
        "packaged_digest": canonical_digest(packaged),
    }


def qualify_runtime_snapshots(
    source: Mapping[str, Any], packaged: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare two normalized snapshots and create a release-gating report."""

    sections = (
        "collection_errors",
        "health",
        "product_capabilities",
        "solver_plugins",
        "capability_ledger",
        "accelerators",
        "external_engines",
        "benchmarks",
    )
    checks = [_check(f"runtime.{section}", source.get(section), packaged.get(section)) for section in sections]
    failures = [check for check in checks if check["status"] != "passed"]
    return {
        "contract": QUALIFICATION_CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if not failures else "failed",
        "summary": {"total": len(checks), "passed": len(checks) - len(failures), "failed": len(failures)},
        "source_snapshot_digest": canonical_digest(source),
        "packaged_snapshot_digest": canonical_digest(packaged),
        "checks": checks,
        "source": dict(source),
        "packaged": dict(packaged),
    }


__all__ = [
    "QUALIFICATION_CONTRACT",
    "QUALIFICATION_METHODS",
    "SNAPSHOT_CONTRACT",
    "canonical_digest",
    "collect_runtime_snapshot",
    "normalize_runtime_results",
    "qualify_runtime_snapshots",
]
