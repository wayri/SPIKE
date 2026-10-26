# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Replay the unchanged analytical 10.3125 GBd gates through a frozen worker.

This is a numerical/process check, never a real-board compliance procedure.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_packaged_worker import _request
from scripts.qualify_serdes_reference import qualification_report


def verify(executable, *, request=_request):
    executable = Path(executable).resolve(strict=True)
    before = sha256(executable.read_bytes()).hexdigest()
    calls = []

    def run_workflow(value):
        response = request(executable, "run_si_workflow", {"request": value})
        if response.get("ok") is not True or not isinstance(response.get("result"), dict):
            raise RuntimeError("SERDES worker returned no successful workflow result")
        result = response["result"]
        calls.append(result.get("request_sha256"))
        return result

    report = qualification_report(run_workflow=run_workflow)
    after = sha256(executable.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError("Worker executable changed during the SERDES reference run")
    if report["status"] != "pass" or len(calls) != 11:
        raise RuntimeError("Frozen SERDES reference gates failed: " + json.dumps(report, sort_keys=True))
    return {"contract": "spike/serdes-worker-reference-evidence/v1", "status": "passed",
            "executable_sha256": after, "workflow_process_calls": len(calls),
            "qualification": report, "production_qualified": False,
            "board_qualification": "not_evaluated", "vendor_interoperability": "not_evaluated",
            "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                "scripts/verify_serdes_worker_reference.py", "scripts/qualify_serdes_reference.py",
                "scripts/build_packaged_worker.py", "python/spike_core/solvers/signal_integrity/receivers/si_workflow.py")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("A fresh output file is required")
    report = verify(args.executable)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ("status", "executable_sha256", "workflow_process_calls")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
