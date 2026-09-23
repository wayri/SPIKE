"""Fail-closed qualification reporting for sparseLizard PCB workflows."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .sparselizard_runtime import detect_sparselizard_runtime


PLAN_CONTRACT = "spike/sparselizard-validation-plan/v1"
EVIDENCE_CONTRACT = "spike/sparselizard-validation-evidence/v1"
REPORT_CONTRACT = "spike/sparselizard-validation-report/v1"
ENGINE_ID = "external.sparselizard"


def _module_root() -> Path:
    return Path(__file__).resolve().parent


def _plan() -> Dict[str, Any]:
    payload = json.loads(
        (_module_root() / "validation_data" / "sparselizard-validation-plan-v1.json")
        .read_text(encoding="utf-8")
    )
    if payload.get("contract") != PLAN_CONTRACT or payload.get("engine_id") != ENGINE_ID:
        raise ValueError("The sparseLizard validation plan contract is invalid.")
    return payload


def _evidence_root(value: str | Path | None) -> Path:
    if value is not None:
        return Path(value).expanduser().resolve()
    configured = os.environ.get("SPIKE_SPARSELIZARD_VALIDATION", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    app_root = Path(os.environ.get("SPIKE_HOME", Path(__file__).resolve().parents[2])).expanduser().resolve()
    return app_root / "runtime" / "external" / "sparselizard" / "validation"


def _relative_error(measured: float, expected: float) -> float:
    return abs(measured - expected) / max(abs(expected), 1e-30)


def _read_evidence(path: Path) -> Dict[str, Any]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4 * 1024**2:
        raise ValueError("Evidence must be a bounded regular JSON file.")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("contract") != EVIDENCE_CONTRACT:
        raise ValueError(f"Expected {EVIDENCE_CONTRACT}.")
    if payload.get("engine_id") != ENGINE_ID or payload.get("status") != "completed":
        raise ValueError("Evidence requires the sparseLizard engine ID and completed status.")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict) or not all(
        provenance.get(key) for key in ("solver_version", "adapter_version", "runtime_sha256", "case_sha256", "result_sha256")
    ):
        raise ValueError("Evidence requires solver, adapter, runtime, case, and result provenance.")
    convergence = payload.get("convergence")
    if not isinstance(convergence, dict) or convergence.get("passed") is not True:
        raise ValueError("Evidence requires a passed convergence record.")
    return payload


def evaluate_sparselizard_validation(evidence_root: str | Path | None = None) -> Dict[str, Any]:
    """Evaluate every declared fixture without promoting absent evidence."""

    plan = _plan()
    root = _evidence_root(evidence_root)
    runtime = detect_sparselizard_runtime()
    outcomes: List[Dict[str, Any]] = []
    for fixture in plan["fixtures"]:
        fixture_id = str(fixture["id"])
        path = root / f"{fixture_id}.json"
        outcome: Dict[str, Any] = {
            "id": fixture_id,
            "physics": str(fixture["physics"]),
            "description": str(fixture["description"]),
            "evidence_path": str(path),
            "status": "blocked",
            "metrics": [],
            "reason": "No fixture evidence is installed.",
        }
        if path.is_file():
            try:
                evidence = _read_evidence(path)
                if evidence.get("fixture_id") != fixture_id:
                    raise ValueError("Evidence fixture_id does not match its file name.")
                levels = evidence.get("convergence", {}).get("levels", [])
                minimum_levels = int(fixture.get("minimum_convergence_levels", 3))
                if not isinstance(levels, list) or len(levels) < minimum_levels:
                    raise ValueError(f"Evidence requires at least {minimum_levels} convergence levels.")
                measured_values = evidence.get("metrics")
                if not isinstance(measured_values, dict):
                    raise ValueError("Evidence metrics must be an object.")
                metric_results = []
                for expected_metric in fixture.get("metrics", []):
                    name = str(expected_metric["name"])
                    measured = float(measured_values.get(name))
                    expected = float(expected_metric["expected"])
                    tolerance = float(expected_metric["relative_tolerance"])
                    if not all(math.isfinite(value) for value in (measured, expected, tolerance)) or tolerance <= 0:
                        raise ValueError(f"Metric {name} contains non-finite values or an invalid tolerance.")
                    error = _relative_error(measured, expected)
                    metric_results.append({
                        "name": name, "measured": measured, "expected": expected,
                        "relative_error": error, "relative_tolerance": tolerance,
                        "status": "passed" if error <= tolerance else "failed",
                    })
                outcome["metrics"] = metric_results
                outcome["status"] = "passed" if metric_results and all(item["status"] == "passed" for item in metric_results) else "failed"
                outcome["reason"] = "All fixture metrics and convergence gates passed." if outcome["status"] == "passed" else "One or more fixture metrics exceeded tolerance."
                outcome["provenance"] = evidence["provenance"]
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                outcome["status"] = "failed"
                outcome["reason"] = str(exc)
        outcomes.append(outcome)
    required = len(outcomes)
    passed = sum(item["status"] == "passed" for item in outcomes)
    failed = sum(item["status"] == "failed" for item in outcomes)
    backend = runtime.get("manifest", {}).get("backend", {}) if runtime.get("available") else {}
    mumps_registered = backend.get("mumps_registered") is True
    signature_verified = runtime.get("signature_verified") is True
    all_passed = bool(
        runtime.get("available") and signature_verified and mumps_registered
        and required and passed == required
    )
    return {
        "contract": REPORT_CONTRACT,
        "engine_id": ENGINE_ID,
        "status": "validated" if all_passed else "failed" if failed else "blocked",
        "runtime_available": bool(runtime.get("available")),
        "runtime_signature_verified": signature_verified,
        "mumps_registered": mumps_registered,
        "summary": {"required": required, "passed": passed, "failed": failed, "blocked": required - passed - failed},
        "fixtures": outcomes,
        "reason": (
            "All sparseLizard runtime, MUMPS, convergence, and PCB validation gates passed."
            if all_passed else
            "sparseLizard remains disabled until the native runtime, PETSc/MUMPS registration, and every PCB fixture pass."
        ),
    }
