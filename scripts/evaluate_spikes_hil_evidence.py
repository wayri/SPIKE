#!/usr/bin/env python3
"""Evaluate a hash-bound physical SPIKES HIL evidence package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.hil_certification import HilRequirements, evaluate_physical_hil_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--period-ns", type=int, required=True)
    parser.add_argument("--maximum-response-latency-ns", type=int, required=True)
    parser.add_argument("--maximum-absolute-jitter-ns", type=int, required=True)
    parser.add_argument("--minimum-cycles", type=int, default=100_000)
    parser.add_argument("--minimum-duration-s", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    evidence_path = arguments.evidence.resolve(strict=True)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HIL evidence root must be a JSON object")
    requirements = HilRequirements(
        period_ns=arguments.period_ns,
        maximum_response_latency_ns=arguments.maximum_response_latency_ns,
        maximum_absolute_jitter_ns=arguments.maximum_absolute_jitter_ns,
        minimum_cycles=arguments.minimum_cycles,
        minimum_duration_s=arguments.minimum_duration_s,
    )
    report = evaluate_physical_hil_evidence(
        payload, requirements, evidence_root=evidence_path.parent,
    )
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if arguments.output is None:
        sys.stdout.write(encoded)
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(encoded, encoding="utf-8")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
