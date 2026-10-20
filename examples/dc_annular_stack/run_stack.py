# SPDX-License-Identifier: Apache-2.0
"""Run an explicit experimental annular DC stack offline."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.dc_annular_stack import solve_annular_stack
from python.spike_core.dc_annular_source import solve_source_annular_stack
from python.spike_core.dc_annular_evidence import validate_annular_stack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--authenticate-sources", action="store_true")
    args = parser.parse_args()
    if args.output.exists(): parser.error("Choose a fresh output path")
    if args.request.stat().st_size > 2*1024*1024: parser.error("Request exceeds2 MiB")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    result = solve_source_annular_stack(request) if args.authenticate_sources else solve_annular_stack(request)
    validate_annular_stack(result["result"] if args.authenticate_sources else result)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print("Verified experimental annular stack; full-board and production qualification remain false.")


if __name__ == "__main__": main()
