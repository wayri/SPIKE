"""Derive the fail-closed whole-product parity gate from executable evidence."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from .competitive_benchmark import REPORT_CONTRACT as BENCHMARK_CONTRACT
from .competitive_gate import GATE_CONTRACT, REQUIRED_GATES, validate_competitive_gate


QUALIFICATION_CONTRACT = "spikes/qualification-report/v1"
REPORT_CONTRACT = "spikes/parity-check-report/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: str | Path, contract: str) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).resolve(strict=True)
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("contract") != contract:
        raise ValueError(f"{resolved} must use {contract}")
    return resolved, value


def _subcheck(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": check_id, "passed": bool(passed), "detail": detail}


def _class_checks(
    present: set[str], required: Iterable[str], *, prefix: str = "corpus"
) -> list[dict[str, Any]]:
    return [
        _subcheck(
            f"{prefix}.{name}", name in present,
            f"Required evidence class '{name}' is {'present' if name in present else 'absent' }.",
        )
        for name in required
    ]


def _gate(
    gate_id: str,
    checks: list[dict[str, Any]],
    evidence: list[dict[str, str]],
) -> dict[str, Any]:
    passed = bool(checks) and all(item["passed"] for item in checks)
    result: dict[str, Any] = {
        "id": gate_id,
        "status": "passed" if passed else "blocked",
        "checks": checks,
        "blocking_checks": [item["id"] for item in checks if not item["passed"]],
        "evidence_checked": evidence,
    }
    if passed:
        result["evidence"] = evidence
    return result


def generate_parity_report(
    benchmark_path: str | Path,
    qualification_path: str | Path,
) -> dict[str, Any]:
    """Evaluate every mandatory parity gate from versioned evidence artifacts.

    Missing corpus classes block their gates.  Passing a small shared subset is
    retained as positive evidence but cannot implicitly stand in for a required
    analysis, device, switching, robustness, HIL, library, or platform class.
    """

    benchmark_file, benchmark = _load(benchmark_path, BENCHMARK_CONTRACT)
    qualification_file, qualification = _load(
        qualification_path, QUALIFICATION_CONTRACT
    )
    evidence = [
        {"artifact": str(benchmark_file), "sha256": _sha256(benchmark_file)},
        {"artifact": str(qualification_file), "sha256": _sha256(qualification_file)},
    ]
    classes = set(str(item) for item in benchmark.get("corpus", {}).get("classes", []))
    engines = {
        str(item.get("engine_id")): str(item.get("status"))
        for item in benchmark.get("engines", []) if isinstance(item, Mapping)
    }
    three_engine_accuracy = (
        benchmark.get("shared_subset_accuracy_passed") is True
        and all(engines.get(name) == "passed" for name in (
            "spikes.owned_cpp", "ngspice", "ltspice"
        ))
    )
    qualified = qualification.get("qualification", {})
    cases = {
        str(item.get("case_id"))
        for item in qualification.get("cases", []) if isinstance(item, Mapping)
    }
    platforms = set(str(item) for item in benchmark.get("platforms", []))
    host_system = str(benchmark.get("host", {}).get("system", "")).lower()
    if host_system:
        platforms.add(host_system)

    gates = [
        _gate(REQUIRED_GATES[0], [
            _subcheck(
                "shared_subset.three_engine_accuracy", three_engine_accuracy,
                "Owned SPIKES, ngspice, and LTspice must agree on the shared subset.",
            ),
            *_class_checks(classes, (
                "spice3_language", "hierarchy", "behavioral_sources", "model_cards"
            )),
        ], evidence),
        _gate(REQUIRED_GATES[1], _class_checks(classes, (
            "operating_point", "dc", "ac", "transient", "noise", "pole_zero",
            "distortion", "sensitivity", "temperature", "statistical",
        )), evidence),
        _gate(REQUIRED_GATES[2], _class_checks(classes, (
            "diode_bjt_jfet_mos", "wbg", "transmission_lines", "magnetics",
            "mixed_signal",
        )), evidence),
        _gate(REQUIRED_GATES[3], _class_checks(classes, (
            "compiled_models", "verilog_a_osdi", "xspice_code_models",
        )), evidence),
        _gate(REQUIRED_GATES[4], [
            _subcheck(
                "qualification.switching_cases",
                {"switching.pwm_resistive", "switching.synchronous_buck"} <= cases,
                "The internal native switching qualification cases must pass.",
            ),
            *_class_checks(classes, (
                "switching_ccm", "switching_dcm", "hard_switching", "soft_switching",
                "regenerative", "saturation", "electrothermal", "protection",
            )),
        ], evidence),
        _gate(REQUIRED_GATES[5], [
            _subcheck(
                "benchmark.comparable_timing",
                benchmark.get("timing_comparable") is True,
                "All engines must use a comparable timing and output scope.",
            ),
            _subcheck(
                "benchmark.performance_claim_eligible",
                benchmark.get("performance_claim_eligible") is True,
                "The benchmark policy must explicitly qualify the performance claim.",
            ),
            *_class_checks(classes, (
                "small", "medium", "large", "cold_warm", "peak_memory",
                "thread_scaling", "public_corpus",
            )),
        ], evidence),
        _gate(REQUIRED_GATES[6], _class_checks(classes, (
            "adversarial", "industry_derived", "restart", "convergence",
            "silent_corruption_audit",
        )), evidence),
        _gate(REQUIRED_GATES[7], [
            _subcheck(
                "qualification.interactive_replay",
                "interactive.native_control_replay" in cases,
                "Persistent lockstep checkpoint/restore must be qualified.",
            ),
            _subcheck(
                "qualification.hard_realtime",
                qualified.get("hard_realtime_qualified") is True,
                "Deterministic hard-real-time behavior must be independently qualified.",
            ),
            _subcheck(
                "qualification.hil",
                qualified.get("hil_qualified") is True,
                "Physical I/O latency, jitter, fault injection, and HIL hardware must pass.",
            ),
            *_class_checks(classes, ("physical_io_latency", "hil_hardware")),
        ], evidence),
        _gate(REQUIRED_GATES[8], _class_checks(classes, (
            "qualified_redistributable_models", "model_licenses", "model_provenance",
            "per_model_numerical_qualification",
        )), evidence),
        _gate(REQUIRED_GATES[9], [
            _subcheck(
                f"platform.{name}", name in platforms,
                f"A reproducible {name} build and numerical-agreement artifact is required.",
            ) for name in ("windows", "linux", "darwin")
        ], evidence),
    ]
    passed = sum(item["status"] == "passed" for item in gates)
    competitive_gate = {
        "contract": GATE_CONTRACT,
        "candidate": "SPIKES",
        "reference": "ngspice and LTspice",
        "evaluated_at_epoch_s": time.time(),
        "status": "passed" if passed == len(gates) else "blocked",
        "claim_eligible": passed == len(gates),
        "summary": {
            "required_gates": len(gates), "passed_gates": passed,
            "blocked_gates": len(gates) - passed,
        },
        "gates": gates,
    }
    validate_competitive_gate(competitive_gate)
    return {
        "contract": REPORT_CONTRACT,
        "status": competitive_gate["status"],
        "claim_eligible": competitive_gate["claim_eligible"],
        "summary": competitive_gate["summary"],
        "inputs": evidence,
        "competitive_gate": competitive_gate,
        "policy": "Whole-product parity is permitted only when all ten gates pass.",
    }


__all__ = ["REPORT_CONTRACT", "generate_parity_report"]
