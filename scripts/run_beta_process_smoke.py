# SPDX-License-Identifier: MIT
"""Probe SPIKE's public beta process boundaries without launching a solve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.beta_runtime_readiness import (  # noqa: E402
    BetaReadinessError,
    build_readiness_report,
)
from python.spikes.version import ENGINE_VERSION  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify beta-facing circuit, layout-scoring, and native-adapter "
            "process invariants. This does not qualify numerical physics."
        ),
    )
    parser.add_argument(
        "--native-solver", default="",
        help="Optional absolute path to spike-native-solver; PATH/environment discovery is used otherwise.",
    )
    parser.add_argument(
        "--require-circuit-worker", action="store_true",
        help="Fail unless the complete packaged circuit-worker inventory passes SHA-256 admission.",
    )
    parser.add_argument(
        "--require-native-runtime", action="store_true",
        help="Fail unless a compatible verification-only native runtime answers --capabilities.",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Optional JSON report path; the parent directory must already exist.",
    )
    args = parser.parse_args(argv)
    try:
        report = build_readiness_report(
            ROOT, native_solver=args.native_solver,
            require_circuit_worker=args.require_circuit_worker,
            require_native_runtime=args.require_native_runtime,
        )
    except (BetaReadinessError, OSError) as exc:
        report = {
            "contract": "spike/beta-runtime-readiness/v1", "product": "SPIKE",
            "version": "unknown", "engine_product": "SPIKES",
            "engine_version": ENGINE_VERSION,
            "status": "failed", "release_tier": "bounded_beta_candidate",
            "production_qualified": False, "components": {},
            "errors": [str(exc)[:4096]],
            "limitations": ["Readiness inspection failed before component admission."],
        }
    payload = json.dumps(report, allow_nan=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        output = args.output.resolve()
        if not output.parent.is_dir():
            parser.error("--output parent directory must already exist")
        output.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
