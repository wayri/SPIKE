# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Verify executed, generated orthogonal fan fixtures and their energy histories."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
from python.spike_core.openfoam_flow_energy_validation import validate_flow_energy
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case


def evaluate(root):
    run = json.loads((root / "report.json").read_text())
    if not run.get("sources_unchanged"):
        raise ValueError("Execution source identity changed")
    for relative, expected in run["source_hashes"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Source identity no longer matches execution")
    records = {}
    for name, record in run["cases"].items():
        if record["status"] != "completed":
            raise ValueError("All cases must have completed field import")
        case, manifest = load_verified_runnable_case(root / name / "case")
        with tempfile.TemporaryDirectory() as temporary:
            expected = build_fan_heated_fixture(Path(temporary) / "fixture", divisions=record["divisions"],
                board_count=record["board_count"], delta_t_s=record["time_step_s"], end_time_s=run["end_time_s"],
                write_interval_steps=round(run["end_time_s"] / record["time_step_s"]))
            if manifest["input_files"] != expected["prepared"]["runnable_manifest"]["input_files"]:
                raise ValueError("Case differs from its fixed orthogonal source-zone fixture")
        check_path = root / name / "command-04.json"
        check = json.loads(check_path.read_text())
        nonorth = re.findall(r"Mesh non-orthogonality Max:\s*([\d.eE+-]+)", check["stdout"])
        if check["return_code"] != 0 or len(nonorth) != record["board_count"] + 1 or any(float(x) > 1e-10 for x in nonorth):
            raise ValueError("Actual checkMesh evidence does not prove orthogonal fixture regions")
        result = json.loads((root / name / "result.json").read_text())
        encoded = json.dumps(result, sort_keys=True, allow_nan=False).encode()
        if hashlib.sha256(encoded).hexdigest() != record["result_sha256"]:
            raise ValueError("Executed result changed")
        energy = validate_flow_energy(case, dpdt_enabled=True, orthogonal_constant_k=True, relative_tolerance=.001)
        energy["check_mesh_sha256"] = hashlib.sha256(check_path.read_bytes()).hexdigest()
        records[name] = energy
    return {"contract": "spike/fan-energy-study-evidence/v1", "cases": records,
            "all_local_energy_checks_passed": all(r["passed"] for r in records.values()),
            "scope": "generated orthogonal single/two-board constant-density laminar ducts; first timestep excluded",
            "production_qualified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(args.root)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({"passed": report["all_local_energy_checks_passed"],
        "relative_residuals": {k:v["relative_residual"] for k,v in report["cases"].items()}}))
