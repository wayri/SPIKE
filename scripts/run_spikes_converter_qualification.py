"""Generate deterministic coupled-reference converter qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spikes.converter_qualification import run_converter_reference_qualification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = run_converter_reference_qualification()
    payload = json.dumps(report, indent=2, allow_nan=False) + "\n"
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(f"Converter coupled-reference qualification: {report['status']}")
    print(f"Cases: {report['passed_case_count']}/{report['case_count']}")
    print(f"Report: {arguments.output.resolve()}")
    print(f"SHA-256: {digest}")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
