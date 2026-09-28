# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Evaluate actual fixed-fixture study files; thresholds are not release gates."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case
from python.spike_core.openfoam_refinement_study import evaluate_refinement_study
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _load_run(root):
    run = json.loads((root / "report.json").read_text())
    if not run.get("sources_unchanged"):
        raise ValueError("Study source changed during execution")
    for relative, expected in run["source_hashes"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Execution source no longer matches the evidence snapshot")
    return run


def evaluate(root, extension=None):
    run = _load_run(root)
    specs = {name: (root, run) for name in ("mesh2", "base", "mesh8", "time4", "time2")}
    studies = (("mesh", ("mesh2", "base", "mesh8"), .02), ("time", ("time4", "time2", "base"), .005))
    if extension is not None:
        additional = _load_run(extension)
        specs = {name: (root, run) for name in ("base", "mesh8", "time4")}
        specs.update({name: (extension, additional) for name in ("mesh16", "time16", "time8")})
        studies = (("mesh", ("base", "mesh8", "mesh16"), .02), ("time", ("time16", "time8", "time4"), .005))
    levels = {}
    for name, (root, run) in specs.items():
        record = run["cases"][name]
        path, manifest = load_verified_runnable_case(root / name / "case")
        result = json.loads((root / name / "result.json").read_text())
        fixture = json.loads((root / name / "fixture.json").read_text())
        request = fixture["request"]
        # Regenerate the declared fixed geometry to prove comparability of all
        # admitted mesh/boundary/source dictionaries, not just a geometry label.
        with tempfile.TemporaryDirectory() as temporary:
            expected = build_fan_heated_fixture(Path(temporary) / "fixture", divisions=record["divisions"],
                delta_t_s=record["time_step_s"], end_time_s=run["end_time_s"],
                write_interval_steps=round(run["end_time_s"] / record["time_step_s"]))
            if expected["prepared"]["runnable_manifest"]["input_files"] != manifest["input_files"]:
                raise ValueError("Case is not the claimed fixed fixture")
        if result["status"] != "completed" or digest(result) != record["result_sha256"]:
            raise ValueError("Missing or modified executed result")
        export_path = path / manifest["field_export_path"]
        if hashlib.sha256(export_path.read_bytes()).hexdigest() != result["provenance"]["field_export_sha256"]:
            raise ValueError("Field export digest mismatch")
        export = json.loads(export_path.read_text())
        if float(export["result_time"]) != run["end_time_s"] or export["manifest_digest"] != manifest["manifest_digest"]:
            raise ValueError("Wrong result time or case identity")
        if fixture["board_count"] != 1 or record["board_count"] != 1:
            raise ValueError("Refinement comparison requires the one-board fixture")
        levels[name] = {
            "case_sha256": manifest["manifest_digest"], "result_sha256": record["result_sha256"],
            "geometry_sha256": digest({"fixture": "one-board-10mm-1.6mm-shared-8.4mm-duct"}),
            "material_sha256": digest(request["materials"]),
            "source_sha256": digest({"heat": request["heat_sources"], "environment": request["environment"],
                "flow_rate_m3_s": request["fans"][0]["flow_rate_m3_s"]}),
            "physical_time_s": float(export["result_time"]), "h_m": .01 / record["divisions"],
            "time_step_s": record["time_step_s"], "reference_temperature_k": 298.15,
            "temperature_k": max(t for region in export["regions"] for t in region["temperature_k"])}
    output = {"production_qualified": False, "scope": "single-board synthetic duct peak temperature rise", "studies": {}}
    # Fixed before execution: 2% mesh and 0.5% time change in temperature rise.
    for axis, names, threshold in studies:
        result = evaluate_refinement_study({"contract": "spike/openfoam-refinement-study/v1", "axis": axis,
                                            "levels": [levels[name] for name in names]})
        result["local_threshold"] = threshold
        result["local_change_check_passed"] = result["fine_relative_change"] is not None and result["fine_relative_change"] <= threshold
        output["studies"][axis] = result
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--extension", type=Path)
    args = parser.parse_args()
    report = evaluate(args.root, args.extension)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report, indent=2))
