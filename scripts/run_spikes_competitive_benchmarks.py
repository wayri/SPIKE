"""Run the accuracy-first SPIKES/ngspice/LTspice shared-subset checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.competitive_benchmark import run_competitive_benchmarks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_competitive_benchmarks(args.library, repetitions=args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Competitive subset checks: {report['status']}")
    print(f"Report: {args.output.resolve()}")
    return 0 if report["shared_subset_accuracy_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
