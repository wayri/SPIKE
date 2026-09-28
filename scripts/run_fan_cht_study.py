# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Reproducible local single/multiboard CHT refinement runs; not release approval."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
from python.spike_core.openfoam_multiregion_execution import run_multiregion_case, load_verified_runnable_case
from python.spike_core.sparselizard_process import run_adapter_process


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--end-time", type=float, default=10.0)
    parser.add_argument("--wsl-native-scratch", action="store_true")
    parser.add_argument("--cases", nargs="+", default=["mesh2", "base", "mesh8", "time4", "time2", "multiboard"])
    args = parser.parse_args()
    settings = {"mesh2": (2, .001, 1), "base": (4, .001, 1), "mesh8": (8, .001, 1),
                "time4": (4, .004, 1), "time2": (4, .002, 1), "multiboard": (4, .001, 2)}
    if any(name not in settings for name in args.cases) or len(set(args.cases)) != len(args.cases):
        parser.error("Case names must be unique and from the fixed study matrix")
    args.output.mkdir(parents=True, exist_ok=False)
    # Execution identity excludes independent analysis modules developed while
    # runs proceed: they are not imported by this runner or the solver.
    source_paths = [p for p in (ROOT / "python/spike_core").glob("openfoam*.py") if "validation" not in p.name and "refinement_study" not in p.name]
    source_paths += [Path(__file__), ROOT / "scripts/fan_wsl_scratch.py", ROOT / "python/spike_core/sparselizard_process.py"]
    def hashes():
        return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    sources = hashes()
    report = {"contract": "spike/fan-cht-study-run/v1", "machine": platform.platform(), "source_hashes": sources,
              "end_time_s": args.end_time, "production_qualified": False, "cases": {}}
    for name in args.cases:
        n, dt, boards = settings[name]
        root = args.output / name
        print(f"Preparing {name}: {n} divisions, dt={dt}, boards={boards}", flush=True)
        fixture = build_fan_heated_fixture(root, divisions=n, board_count=boards, delta_t_s=dt,
            end_time_s=args.end_time, write_interval_steps=round(args.end_time / dt))
        (root / "fixture.json").write_text(json.dumps(fixture, indent=2, allow_nan=False), encoding="utf-8")
        count = 0
        def runner(command, **kwargs):
            nonlocal count
            count += 1
            print(f"{name}: command {count}", flush=True)
            kwargs["stream_limit_bytes"] = 128 * 1024**2
            result = run_adapter_process(command, **kwargs)
            (root / f"command-{count:02d}.json").write_text(json.dumps({"argv": command, **result}, indent=2), encoding="utf-8")
            return result
        active_runner = runner
        if args.wsl_native_scratch:
            from scripts.fan_wsl_scratch import ScratchRunner
            active_runner = ScratchRunner(root / "case", runner)
        result = run_multiregion_case(root / "case", timeout_s=900, runner=active_runner)
        (root / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        report["cases"][name] = {"divisions": n, "time_step_s": dt, "board_count": boards,
            "case_sha256": load_verified_runnable_case(root / "case")[1]["manifest_digest"],
            "result_sha256": digest(result), "status": result["status"], "summary": result.get("summary"),
            "duration_s": result.get("duration_s"), "message": result.get("message")}
        if args.wsl_native_scratch:
            report["cases"][name]["retained_linux_scratch"] = active_runner.remote
        report["sources_unchanged"] = sources == hashes()
        (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"case": name, **report["cases"][name]}), flush=True)
        if result["status"] != "completed" or not report["sources_unchanged"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
