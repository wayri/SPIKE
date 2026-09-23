"""Run locally available engines over the staged equal-model corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.public_corpus import run_local_equal_model_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "benchmarks" / "public_equal_model")
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--ngspice", type=Path)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = run_local_equal_model_evidence(
        arguments.corpus, spikes_library=arguments.library,
        ngspice_executable=arguments.ngspice, repetitions=arguments.repetitions,
        timeout_s=arguments.timeout,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Local equal-model evidence: {report['status']}")
    print(f"Report: {arguments.output.resolve()}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
