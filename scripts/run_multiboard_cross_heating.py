# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Execute synthetic two-board cross-heating; upper board has no source."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
from python.spike_core.openfoam_multiregion import prepare_runnable_multiregion_case
from python.spike_core.openfoam_multiregion_execution import load_verified_runnable_case, run_multiregion_case
from python.spike_core.openfoam import _parse_internal_field, _latest_time
from python.spike_core.sparselizard_process import run_adapter_process
from scripts.fan_wsl_scratch import ScratchRunner


def prepare(root):
    """Keep the source template immutable; bind a fresh unpowered-board case."""
    fixture = build_fan_heated_fixture(root / "template", board_count=2, divisions=4,
        delta_t_s=.001, end_time_s=10, write_interval_steps=10000)
    request = copy.deepcopy(fixture["request"])
    source = next(item for item in request["heat_sources"] if item["solid_region_id"] == "board2")
    source["power_w"] = 0.0
    source["fv_option"]["volumetric_power_w_m3"] = 0.0
    evidence_value = {"solid_region_id": "board2", "power_w": 0.0, "volumetric_power_w_m3": 0.0, "scope": "synthetic prescribed unpowered board"}
    source["evidence"] = {"id": "synthetic-fixture:unpowered-upper-board", "contract": "spike/component-power-table/v1",
        "sha256": hashlib.sha256(json.dumps(evidence_value, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "qualified": True}
    prepared = prepare_runnable_multiregion_case(request, root / "case", root / "template/meshes")
    if prepared["status"] != "prepared_runnable_case":
        raise ValueError("Cross-heating case preparation failed")
    return request, prepared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/multiboard-cross-heating-20260907")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source_paths = [p for p in (ROOT / "python/spike_core").glob("openfoam*.py") if "validation" not in p.name and "refinement_study" not in p.name]
    source_paths += [Path(__file__), ROOT / "scripts/fan_wsl_scratch.py", ROOT / "python/spike_core/sparselizard_process.py"]
    def hashes():
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    before = hashes()
    request, prepared = prepare(root)
    (root / "request.json").write_text(json.dumps(request, indent=2, allow_nan=False), encoding="utf-8")
    if args.prepare_only:
        print(json.dumps({"status": "prepared_runnable_case", "case": str(root / "case"), "executed_cfd": False}))
        return 0
    count = 0
    command_records = []
    def runner(command, **kwargs):
        nonlocal count
        count += 1
        kwargs["stream_limit_bytes"] = 128 * 1024**2
        print(f"Cross-heating command {count}", flush=True)
        record = {"argv": command, **run_adapter_process(command, **kwargs)}
        command_records.append(record)
        (root / f"command-{count:02d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record
    scratch = ScratchRunner(root / "case", runner)
    result = run_multiregion_case(root / "case", timeout_s=900, runner=scratch)
    (root / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    report = {"contract": "spike/multiboard-cross-heating-evidence/v1", "status": "failed",
        "source_hashes": before, "sources_unchanged": before == hashes(), "machine": platform.platform(),
        "case_manifest_sha256": load_verified_runnable_case(root / "case")[1]["manifest_digest"],
        "retained_linux_scratch": scratch.remote, "solver_status": result["status"], "production_qualified": False}
    if result["status"] == "completed" and report["sources_unchanged"]:
        latest = _latest_time(root / "case")
        if float(latest.name) != 10:
            raise ValueError("Expected final time 10s")
        fields = {region: _parse_internal_field(latest / region / "T", expected_count=64) for region in ("board", "board2", "air")}
        finite = all(len(values) == 64 and all(math.isfinite(value) for value in values) for values in fields.values())
        mean = {region: math.fsum(values) / len(values) for region, values in fields.items()}
        report["temperature_mean_k"] = mean
        report["field_sha256"] = {region: hashlib.sha256((latest / region / "T").read_bytes()).hexdigest() for region in fields}
        report["cross_heating_passed"] = finite and mean["board"] > mean["board2"] > 298.15 + 1e-6
        check = next((item for item in command_records if "checkMesh" in item["argv"] and "-help" not in item["argv"]), None)
        nonorth = re.findall(r"Mesh non-orthogonality Max:\s*([\d.eE+-]+)", check.get("stdout", "")) if check else []
        if check and check["return_code"] == 0 and len(nonorth) == 3 and all(float(value) <= 1e-10 for value in nonorth):
            from python.spike_core.openfoam_flow_energy_validation import validate_flow_energy
            report["energy"] = validate_flow_energy(root / "case", dpdt_enabled=True, orthogonal_constant_k=True, relative_tolerance=.001)
        report["status"] = "passed" if report["cross_heating_passed"] and report.get("energy", {}).get("passed", False) else "failed"
    report["scope"] = "Synthetic 2-board orthogonal laminar duct; lower board 0.1W, upper board 0W; not arbitrary CAD or release qualification"
    (root / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
