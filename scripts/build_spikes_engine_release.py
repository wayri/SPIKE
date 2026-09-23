#!/usr/bin/env python3
"""Build a local, integrity-bound SPIKES Windows engineering preview."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.release_bundle import build_engine_release
from python.spikes.version import ENGINE_VERSION


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=ENGINE_VERSION)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/releases")
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    package, archive, report = build_engine_release(
        root=ROOT, version=arguments.version, library=arguments.library,
        output_root=arguments.output_root, evidence=arguments.evidence,
    )
    report_path = arguments.report or arguments.output_root / f"SPIKES-{arguments.version}-release.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"SPIKES package: {package}")
    print(f"SPIKES archive: {archive}")
    print(f"Release report: {report_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
