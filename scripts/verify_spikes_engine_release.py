#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a SPIKES engine archive and perform an offline staging smoke."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.release_verifier import (  # noqa: E402
    ReleaseVerificationError,
    verify_engine_release,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Release report emitted by build_spikes_engine_release.py")
    parser.add_argument("--no-launch", action="store_true", help="Skip only the staged CLI launch smoke")
    parser.add_argument("--output", type=Path, help="Optional verification report; parent must exist")
    arguments = parser.parse_args(argv)
    try:
        result = verify_engine_release(arguments.report, launch_smoke=not arguments.no_launch)
    except (OSError, ReleaseVerificationError) as exc:
        result = {
            "contract": "spikes/engine-release-verification/v1",
            "status": "failed", "production_qualified": False,
            "error": str(exc)[:4096],
        }
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if arguments.output:
        destination = arguments.output.resolve()
        if not destination.parent.is_dir():
            parser.error("--output parent directory must exist")
        destination.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
