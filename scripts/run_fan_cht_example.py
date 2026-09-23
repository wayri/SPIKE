# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Run a verified local CHT case, preserving bounded logs and source identity."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam_multiregion_execution import run_multiregion_case
from python.spike_core.sparselizard_process import run_adapter_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    args = parser.parse_args()
    output = ROOT / "build" / ("fan-cht-run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    output.mkdir(parents=True)
    sources = list((ROOT / "python/spike_core").glob("openfoam*.py")) + [Path(__file__), ROOT / "python/spike_core/sparselizard_process.py"]
    def hashes():
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    before = hashes()
    count = 0
    def runner(command, **kwargs):
        nonlocal count
        count += 1
        print(f"Command {count}: {command}", flush=True)
        # Ten thousand transient steps produce verbose residual logs. Retain
        # them under an explicit finite budget without changing solver limits.
        kwargs["stream_limit_bytes"] = 128 * 1024**2
        result = run_adapter_process(command, **kwargs)
        (output / f"command-{count:02d}.json").write_text(json.dumps({"argv": command, **result}, indent=2), encoding="utf-8")
        print(f"Command {count} returned {result['return_code']}", flush=True)
        return result
    print(f"Evidence: {output}", flush=True)
    result = run_multiregion_case(args.case, timeout_s=900, runner=runner)
    report = {"result": result, "machine": platform.platform(), "python": sys.version,
              "source_hashes": before, "sources_unchanged": before == hashes(), "production_qualified": False}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result.get("summary"), "message": result.get("message"), "evidence": str(output)}), flush=True)
    return 0 if result["status"] in {"completed", "passed", "success"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
