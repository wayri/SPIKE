# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Snapshot checks for the synthetic 4x4x4-cell, 10-second fan CHT fixture only."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam import _parse_internal_field


def verify(case):
    times = sorted((p for p in case.iterdir() if p.is_dir() and re.fullmatch(r"\d+(?:\.\d+)?", p.name)), key=lambda p: float(p.name))
    if not times or float(times[-1].name) != 10.0:
        raise ValueError("Fixture latest written time must be exactly 10 seconds")
    time = times[-1]
    paths = [time / "air/phi", time / "air/U", time / "air/T", time / "board/T"]
    def hashes():
        return {str(p.relative_to(case)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before = hashes()
    text = paths[0].read_text(encoding="utf-8")
    dimensions = re.search(r"\bdimensions\s*\[([^]]+)\]\s*;", text)
    if dimensions is None or dimensions.group(1).split() != ["1", "0", "-1", "0", "0", "0", "0"]:
        raise ValueError("phi must have mass-flux dimensions kg/s")
    flux = {}
    for patch in ("fan_in", "exhaust"):
        blocks = re.findall(r"\b" + patch + r"\s*\{([^{}]*)\}", text, re.S)
        if len(blocks) != 1:
            raise ValueError("Expected exactly one fixture inlet and outlet patch")
        match = re.search(r"value\s+nonuniform\s+List<scalar>\s+(\d+)\s*\((.*?)\)\s*;", blocks[0], re.S)
        if match is None:
            raise ValueError("Expected explicit nonuniform boundary flux")
        values = [float(item) for item in match.group(2).split()]
        if int(match.group(1)) != 16 or len(values) != 16 or not all(math.isfinite(item) for item in values):
            raise ValueError("Expected 16 finite boundary flux values")
        if (patch == "fan_in" and not all(item < 0 for item in values)) or (patch == "exhaust" and not all(item > 0 for item in values)):
            raise ValueError("Fixture requires inward inlet and outward exhaust on every face")
        flux[patch] = {"sum_kg_s": math.fsum(values), "minimum_kg_s": min(values), "maximum_kg_s": max(values)}
    inlet = flux["fan_in"]["sum_kg_s"]
    mismatch = abs(inlet + flux["exhaust"]["sum_kg_s"]) / abs(inlet)
    if mismatch >= 1e-8 or not math.isclose(inlet, -1.2e-5, rel_tol=1e-8, abs_tol=0):
        raise ValueError("Fixture mass balance or prescribed mass inflow failed")
    temperatures = {}
    for region in ("board", "air"):
        values = _parse_internal_field(time / region / "T", expected_count=64)
        if len(values) != 64 or not all(math.isfinite(item) and 298.14 <= item <= 310 for item in values):
            raise ValueError("Fixture temperature sanity bounds failed")
        temperatures[region] = {"minimum_k": min(values), "maximum_k": max(values), "mean_k": math.fsum(values) / len(values)}
    velocity = _parse_internal_field(time / "air/U", vector=True, expected_count=64)
    if len(velocity) != 64 or not all(len(row) == 3 and all(math.isfinite(item) for item in row) for row in velocity):
        raise ValueError("Expected 64 finite velocity vectors")
    speed = [math.hypot(*row) for row in velocity]
    if not all(0 < item < 1 for item in speed):
        raise ValueError("Fixture velocity sanity bounds failed")
    if hashes() != before:
        raise ValueError("Fields changed during verification")
    return {"contract": "spike/synthetic-fan-field-check/v1", "status": "passed", "time_s": 10,
            "case": str(case), "field_sha256": before, "mass_flux": flux, "relative_mass_mismatch": mismatch,
            "temperature": temperatures, "speed_m_s": {"minimum": min(speed), "maximum": max(speed)},
            "qualification": {"production_qualified": False, "energy_balance_validated": False,
                "mesh_time_convergence_validated": False, "scope": "synthetic fixture snapshot; range bounds are sanity checks, not analytical correlation"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    # Exclusive publication: never replace prior evidence.
    if args.output.exists():
        parser.error("Output must not already exist")
    try:
        report = verify(args.case.resolve())
    except (OSError, ValueError) as exc:
        report = {"status": "failed", "error": str(exc), "qualification": {"production_qualified": False}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
