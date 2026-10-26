# SPDX-License-Identifier: Apache-2.0
"""Run an explicit geometry model or authenticated native full-pad volume study."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.solvers.power_integrity.dc.dc_board_study import MODEL, SOURCE, solve_board_model, solve_source_board, validate_board_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path); parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists(): parser.error("Choose a fresh output path")
    if args.request.stat().st_size > 16*1024*1024: parser.error("Request exceeds16 MiB")
    raw = json.loads(args.request.read_text(encoding="utf-8"))
    if raw.get("contract") == MODEL: run = solve_board_model(raw); result = run
    elif raw.get("contract") == SOURCE: run = solve_source_board(raw); result = run["run"]
    else: parser.error("Unsupported board-volume contract")
    validate_board_run(result)
    args.output.write_text(json.dumps(run, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print("Experimental selected-volume DC verified; full-board PI/SI qualification remains open.")


if __name__ == "__main__": main()
