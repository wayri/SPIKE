#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Evaluate the SPIKES public-release gate without publishing an artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.public_release_readiness import (  # noqa: E402
    BLOCKED_EXTERNAL,
    evaluate_public_release,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Optional gate report; parent must exist")
    arguments = parser.parse_args(argv)
    report = evaluate_public_release(ROOT, engine_report=arguments.engine_report)
    payload = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output:
        destination = arguments.output.resolve()
        if not destination.parent.is_dir():
            parser.error("--output parent directory must exist")
        destination.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    if report["status"] == "PASS":
        return 0
    return 2 if report["status"] == BLOCKED_EXTERNAL else 1


if __name__ == "__main__":
    raise SystemExit(main())
