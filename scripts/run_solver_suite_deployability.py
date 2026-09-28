# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Print or atomically publish the SPIKE solver-suite deployability report."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.solver_suite_deployability import build_solver_suite_deployability


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the reviewed SPIKE solver-suite deployability ledger.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_solver_suite_deployability()
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    if args.output is None:
        sys.stdout.write(payload)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
        temporary.write_text(payload, encoding="ascii", newline="\n")
        os.replace(temporary, args.output)
    return 0 if report["deployable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
