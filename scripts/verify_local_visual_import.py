"""Capture real staged imports using a frozen worker or the source worker."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--worker", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    command = [str(args.worker.resolve())] if args.worker else [sys.executable, "-m", "python.spike_core.service"]
    summaries = []
    for stage in ("layout", "board", "components"):
        request = {"id": f"verify-{stage}", "method": "prepare_visual_bundle", "params": {
            "board_path": str(args.board.resolve()), "stage": stage, "timeout_seconds": 600,
        }}
        started = time.perf_counter()
        process = subprocess.run(command, input=json.dumps(request) + "\n", capture_output=True, text=True,
                                 encoding="utf-8", timeout=630, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode:
            raise RuntimeError(process.stderr[-2000:] or f"Worker exit {process.returncode}")
        response = json.loads(process.stdout)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Import failed"))
        (args.output / f"{stage}-response.json").write_text(process.stdout, encoding="utf-8")
        result = response["result"]
        summary = {"stage": stage, "seconds": round(time.perf_counter() - started, 2),
                   "bytes": result["artifact_bytes"], "layers": len(result["layout"]["layers"]),
                   "missing": result["quality"].get("missing_references", []),
                   "board_includes_copper": result["quality"].get("board_includes_copper")}
        print(json.dumps(summary), flush=True)
        summaries.append(summary)
    (args.output / "verification.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
