# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Admit downloaded primary measured data, without fabricating CFD predictions."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.cfd_reference_correlation import admit_nasa_backstep_cf, compare_backstep_cf


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prediction", type=Path)
    parser.add_argument("--maximum-absolute-error", type=float)
    args = parser.parse_args()
    if args.prediction:
        if args.maximum_absolute_error is None:
            parser.error("A predeclared maximum absolute Cf error is required")
        if args.prediction.stat().st_size > 8*1024**2:
            parser.error("Prediction control file exceeds 8 MiB")
        result = compare_backstep_cf(args.reference, json.loads(args.prediction.read_text()),
                                    maximum_absolute_error=args.maximum_absolute_error)
    else:
        result = admit_nasa_backstep_cf(args.reference)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": result["status"], "production_qualified": False,
                      "output": str(args.output)}))
