"""Compare the source SPIKE worker with a packaged worker executable."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.runtime_qualification import (  # noqa: E402
    collect_runtime_snapshot,
    qualify_runtime_snapshots,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-python", required=True, type=Path)
    parser.add_argument("--packaged-worker", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    runtime_environment = {"SPIKE_HOME": str(ROOT)}
    source = collect_runtime_snapshot(
        [str(args.source_python), "-m", "python.spike_core.service"],
        cwd=ROOT,
        environment_overrides=runtime_environment,
    )
    packaged = collect_runtime_snapshot(
        [str(args.packaged_worker)], cwd=ROOT, environment_overrides=runtime_environment
    )
    report = qualify_runtime_snapshots(source, packaged)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"Runtime qualification {report['status']}: "
        f"{report['summary']['passed']}/{report['summary']['total']} checks passed"
    )
    print(f"Report: {args.output.resolve()}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
