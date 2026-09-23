#!/usr/bin/env python3
"""Build the integrity-bound SPIKES engineering-preview readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.first_release import build_first_release_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.2.0")
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--parity", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--portable-dir", type=Path, required=True)
    parser.add_argument("--portable-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_first_release_report(
        version=args.version,
        benchmark_path=args.benchmark,
        qualification_path=args.qualification,
        parity_path=args.parity,
        runtime_path=args.runtime,
        portable_dir=args.portable_dir,
        portable_zip=args.portable_zip,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"First-release readiness: {report['status']} "
        f"({report['summary']['passed']}/{report['summary']['total']})"
    )
    print(f"Report: {args.output.resolve()}")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
