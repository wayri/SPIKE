"""Fail-closed qualification for a deployable SPIKE power-integrity release.

Runtime parity and passing analytical tests are necessary but not sufficient.
Every required PI workflow must also have an evidence-bearing native owner in
the capability ledger.  This module deliberately does not infer readiness from
installed external tools or from UI availability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .capability_ledger import native_capability_ledger


PI_RELEASE_QUALIFICATION_CONTRACT = "spike/pi-release-qualification/v1"
REQUIRED_PI_WORKFLOWS = (
    "pi.dc_conduction",
    "pi.ac_rlcg",
    "pi.pdn_target_and_capacitor_optimization",
    "pi.geometry_transient",
    "circuit.spice_compatible_mna",
    "circuit.field_circuit_cosimulation",
)
_VALIDATED_STATES = {"reference_validated", "validated"}


def _workflow_blocking_reasons(
    *,
    benchmark_ok: bool,
    release_state: Any,
    validation_state: Any,
    validation_evidence: Any,
    release_qualification: Any,
    native_owner: Any,
    release_benchmarks: Any,
    benchmark_evidence: Mapping[str, Any],
) -> list[str]:
    """Return stable, machine-readable reasons a workflow cannot ship."""

    reasons: list[str] = []
    if not benchmark_ok:
        reasons.append("The global native benchmark corpus is not passing without skips.")
    if release_state not in _VALIDATED_STATES:
        reasons.append(f"Release state is {release_state!r}; validated or reference_validated is required.")
    if validation_state not in _VALIDATED_STATES:
        reasons.append(f"Validation state is {validation_state!r}; validated evidence is required.")
    if not isinstance(validation_evidence, list) or not validation_evidence:
        reasons.append("No validation evidence is registered for this workflow.")
    if not isinstance(release_qualification, Mapping):
        reasons.append("No digest-bound workflow qualification artifact is registered.")
    if not isinstance(native_owner, str) or not native_owner.startswith("spike.native."):
        reasons.append("A SPIKE native solver owner is not registered.")
    if not isinstance(release_benchmarks, list) or not release_benchmarks:
        reasons.append("No workflow-specific release benchmark is registered.")
    else:
        invalid = [benchmark_id for benchmark_id in release_benchmarks if not isinstance(benchmark_id, str)]
        if invalid:
            reasons.append("Workflow-specific release benchmark identifiers must be strings.")
        missing = [
            benchmark_id
            for benchmark_id in release_benchmarks
            if isinstance(benchmark_id, str) and benchmark_evidence.get(benchmark_id) != "passed"
        ]
        if missing:
            reasons.append("Release benchmarks are missing or not passing: " + ", ".join(missing) + ".")
    return reasons


def load_json_report(path: Path) -> dict[str, Any]:
    """Load a JSON report and require an object at its root."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read qualification input {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Qualification input {path} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Qualification input {path} must contain a JSON object.")
    return value


def _check(identifier: str, passed: bool, detail: str, evidence: Any = None) -> dict[str, Any]:
    result = {
        "id": identifier,
        "required": True,
        "status": "passed" if passed else "blocked",
        "detail": detail,
    }
    if evidence is not None:
        result["evidence"] = evidence
    return result


def qualify_pi_release(
    runtime_report: Mapping[str, Any] | None,
    benchmark_report: Mapping[str, Any] | None,
    ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate the stable PI release gate without weakening validity labels."""

    checks: list[dict[str, Any]] = []
    runtime = runtime_report if isinstance(runtime_report, Mapping) else {}
    runtime_summary = runtime.get("summary") if isinstance(runtime.get("summary"), Mapping) else {}
    runtime_ok = (
        runtime.get("contract") == "spike/release-runtime-qualification/v1"
        and runtime.get("status") == "passed"
        and int(runtime_summary.get("failed", -1)) == 0
        and runtime.get("source_snapshot_digest")
        and runtime.get("source_snapshot_digest") == runtime.get("packaged_snapshot_digest")
    )
    checks.append(_check(
        "runtime.packaged_parity",
        bool(runtime_ok),
        "Source and packaged workers must have identical, passing runtime snapshots.",
        {
            "contract": runtime.get("contract", "missing"),
            "status": runtime.get("status", "missing"),
            "failed": runtime_summary.get("failed", "missing"),
            "source_snapshot_digest": runtime.get("source_snapshot_digest", ""),
            "packaged_snapshot_digest": runtime.get("packaged_snapshot_digest", ""),
        },
    ))

    runtime_source = runtime.get("source") if isinstance(runtime.get("source"), Mapping) else {}
    qualified_benchmarks = (
        runtime_source.get("benchmarks")
        if isinstance(runtime_source.get("benchmarks"), Mapping)
        else {}
    )
    benchmarks = (
        benchmark_report
        if isinstance(benchmark_report, Mapping)
        else qualified_benchmarks
    )
    benchmark_summary = benchmarks.get("summary") if isinstance(benchmarks.get("summary"), Mapping) else {}
    benchmark_records = benchmarks.get("benchmarks")
    if not isinstance(benchmark_records, list):
        # Runtime qualification stores the normalized benchmark rows as
        # ``cases``. Direct benchmark reports retain the public
        # ``benchmarks`` field. Both shapes implement the same v1 contract.
        benchmark_records = benchmarks.get("cases")
    if not isinstance(benchmark_records, list):
        benchmark_records = []
    benchmark_by_name = {
        item.get("name"): item
        for item in benchmark_records
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    benchmark_ok = (
        benchmarks.get("contract") == "spike/solver-benchmark-report/v1"
        and benchmarks.get("status") == "passed"
        and int(benchmark_summary.get("failed", -1)) == 0
        and int(benchmark_summary.get("skipped", -1)) == 0
        and int(benchmark_summary.get("passed", 0)) > 0
    )
    checks.append(_check(
        "validation.native_benchmarks",
        bool(benchmark_ok),
        "The native benchmark corpus must pass with no failed or skipped fixture.",
        {
            "source": "explicit_report" if isinstance(benchmark_report, Mapping) else "qualified_runtime_snapshot",
            "contract": benchmarks.get("contract", "missing"),
            "status": benchmarks.get("status", "missing"),
            "summary": dict(benchmark_summary),
        },
    ))

    capability_ledger = ledger if isinstance(ledger, Mapping) else native_capability_ledger()
    workflow_records = {
        item.get("id"): item
        for item in capability_ledger.get("workflows", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    for workflow_id in REQUIRED_PI_WORKFLOWS:
        record = workflow_records.get(workflow_id, {})
        release_state = record.get("release_state", "missing")
        validation_state = record.get("validation_state", "missing")
        evidence = record.get("validation_evidence", [])
        release_qualification = record.get("release_qualification")
        release_benchmarks = record.get("release_benchmarks", [])
        native_owner = record.get("native_owner", "")
        benchmark_evidence = {
            benchmark_id: benchmark_by_name.get(benchmark_id, {}).get("status", "missing")
            for benchmark_id in release_benchmarks
            if isinstance(benchmark_id, str)
        } if isinstance(release_benchmarks, list) else {}
        workflow_benchmarks_pass = (
            isinstance(release_benchmarks, list)
            and bool(release_benchmarks)
            and len(benchmark_evidence) == len(release_benchmarks)
            and all(status == "passed" for status in benchmark_evidence.values())
        )
        blocking_reasons = _workflow_blocking_reasons(
            benchmark_ok=bool(benchmark_ok),
            release_state=release_state,
            validation_state=validation_state,
            validation_evidence=evidence,
            release_qualification=release_qualification,
            native_owner=native_owner,
            release_benchmarks=release_benchmarks,
            benchmark_evidence=benchmark_evidence,
        )
        ready = not blocking_reasons and workflow_benchmarks_pass
        checks.append(_check(
            f"workflow.{workflow_id}",
            ready,
            (
                "Validated native owner and workflow-specific benchmarks satisfy the stable PI release gate."
                if ready
                else " ".join(blocking_reasons)
            ),
            {
                "native_owner": native_owner or "missing",
                "release_state": release_state,
                "validation_state": validation_state,
                "validation_evidence": list(evidence) if isinstance(evidence, list) else [],
                "release_qualification": dict(release_qualification) if isinstance(release_qualification, Mapping) else None,
                "release_benchmarks": list(release_benchmarks) if isinstance(release_benchmarks, list) else [],
                "benchmark_status": benchmark_evidence,
                "blocking_reasons": blocking_reasons,
            },
        ))

    blocked = [item["id"] for item in checks if item["status"] != "passed"]
    return {
        "contract": PI_RELEASE_QUALIFICATION_CONTRACT,
        "status": "passed" if not blocked else "blocked",
        "deployable": not blocked,
        "policy": {
            "fail_closed": True,
            "external_engines_cannot_satisfy_native_release": True,
            "no_skipped_required_benchmarks": True,
            "required_workflows": list(REQUIRED_PI_WORKFLOWS),
        },
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(blocked),
            "blocked": len(blocked),
        },
        "blocked_checks": blocked,
        "checks": checks,
    }


__all__ = [
    "PI_RELEASE_QUALIFICATION_CONTRACT",
    "REQUIRED_PI_WORKFLOWS",
    "load_json_report",
    "qualify_pi_release",
]
