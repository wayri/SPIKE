# SPDX-License-Identifier: Apache-2.0
"""Isolated, bounded refinement attempts for explicit selected-volume DC models."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import sysconfig
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.solver_source_paths import solver_source_path

METHODS = ('scripts/benchmark_board_volume_scaling.py', *(solver_source_path(name).relative_to(ROOT).as_posix() for name in (
    'dc_board_study.py','dc_board_volume.py','dc_board_partition.py','dc_triangle_partition.py',
    'dc_tetra_rt0.py','dc_tetra_rt0_input.py','dc_tetra_sparse.py','dc_tetra_rt0_evidence.py',
    'dc_tetra_density.py','dc_rt0_density.py','dc_land_transition_evidence.py',
    'assembly_tetra_thermal_validation.py','tetra_aabb_candidates.py','numerical_runtime.py','compute_policy.py')))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def child(model_path, digest, solve):
    from python.spike_core.solvers.power_integrity.dc.dc_board_study import compile_model
    from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0 import solve_tetra_dc
    from python.spike_core.solvers.power_integrity.dc.dc_tetra_rt0_evidence import validate_tetra_dc
    from scripts.benchmark_pcb_mesher import _current_memory
    if sha(model_path) != digest: raise ValueError("Changed model before isolated admission")
    model = json.loads(model_path.read_text(encoding="utf-8")); start = time.perf_counter()
    report = {"model_sha256": digest, "status": "blocked", "stage_complete": False,
              "production_qualified": False, "target_mm": model["target_mm"], "timing_s": {}}
    methods = [ROOT/name for name in METHODS]
    report['methods_before'] = {p.relative_to(ROOT).as_posix(): sha(p) for p in methods}
    try:
        compiled = compile_model(model)
        report["timing_s"]["compile"] = time.perf_counter()-start
        report["counts"] = compiled["request"]["mesh"]["counts"]
        report["coverage"] = compiled["coverage"]
        path = model_path.parent/"tetra-request.json"
        path.write_text(json.dumps(compiled["request"], separators=(",", ":"), allow_nan=False), encoding="utf-8")
        report["tetra_request_sha256"] = sha(path)
        report["status"] = "compiled_only"
        if solve:
            (model_path.parent/'progress.json').write_text(json.dumps({'phase':'admitting_and_solving',
                'counts':report['counts'],'compile_s':report['timing_s']['compile']}), encoding='utf-8')
            before = time.perf_counter(); result = solve_tetra_dc(compiled["request"])
            report["timing_s"]["solve_including_admission"] = time.perf_counter()-before
            before = time.perf_counter(); validate_tetra_dc(result)
            report["timing_s"]["retained_validation"] = time.perf_counter()-before
            result_path = model_path.parent/"fields.json"
            result_path.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False), encoding="utf-8")
            report.update(status="discrete_fields_verified", fields_sha256=sha(result_path),
                joule_heat_w=result["joule_heat_w"], signed_terminal_work_w=result["signed_terminal_work_w"],
                contacts=result["contacts"], density=result["current_density_observable"], diagnostics=result["diagnostics"])
    except Exception as error:
        report.update(status='blocked', blocker=str(error), exception=type(error).__name__, traceback=traceback.format_exc())
    report["elapsed_s"] = time.perf_counter()-start
    report["native_memory"] = _current_memory()
    report["model_unchanged"] = sha(model_path) == digest
    report['methods_after'] = {p.relative_to(ROOT).as_posix(): sha(p) for p in methods}
    report['methods_unchanged'] = report['methods_before'] == report['methods_after']
    if not report['methods_unchanged']:
        report.update(status='blocked', blocker='Method source changed during run; no qualification accepted')
    (model_path.parent/"case-report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "blocker": report.get("blocker"), "counts": report.get("counts")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--targets", type=float, nargs="+", default=[4., 2., 1.])
    parser.add_argument("--solve", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--child-digest", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_digest:
        child(args.model.resolve(), args.child_digest, args.solve); return
    from python.spike_core.solvers.power_integrity.dc.dc_board_study import MODEL, SCALABLE_MODEL
    from python.spike_core.solvers.external_engines.sparselizard.sparselizard_process import run_adapter_process
    if args.output is None: parser.error("Fresh repository output directory required")
    folder = args.output.resolve()
    if folder.exists() or not folder.is_relative_to(ROOT): parser.error("Fresh repository output directory required")
    if not 1 <= args.timeout <= 600: parser.error("Timeout must be1..600 seconds")
    if not 1 <= len(args.targets) <= 4 or any(not 0 < t <= 1e6 for t in args.targets): parser.error("Invalid bounded refinement targets")
    source = args.model.resolve(); before = sha(source)
    model = json.loads(source.read_text(encoding="utf-8"))
    if model.get("contract") not in (MODEL, SCALABLE_MODEL): parser.error("Explicit board-volume model required")
    folder.mkdir(parents=True)
    summary = {"contract": "spike/board-volume-scaling-attempt/v1", "source_model": str(source),
        "source_model_sha256_before": before, "stage_complete": False, "production_qualified": False,
        "process_policy": {"memory_limit_mb": 4096, "timeout_s": args.timeout, "output_limit_bytes": 512*1024**2,
                           "blas_threads": 1}, "cases": []}
    for index, target in enumerate(args.targets):
        case = folder/str(index); case.mkdir()
        selected = dict(model, contract=SCALABLE_MODEL, max_cells=50000, target_mm=target)
        path = case/"model.json"; path.write_text(json.dumps(selected, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        # A Windows venv launcher spawns the base interpreter, conflicting with
        # the supervisor's one-process job limit. Enter that interpreter directly.
        entry = ("import sys,runpy,os;sys.path[:0]="+repr([str(ROOT),sysconfig.get_path("purelib")])+";"
                 "from python.spike_core.numerical_runtime import numerical_child_environment;"
                 "environment=numerical_child_environment(cpu_threads=1,blas_threads=1);"
                 "os.environ.pop('MKL_DOMAIN_NUM_THREADS',None);os.environ.update(environment);"
                 "runpy.run_path("+repr(str(Path(__file__).resolve()))+",run_name='__main__')")
        command = [getattr(sys, "_base_executable", sys.executable), "-B", "-c", entry,
                   "--model", str(path), "--child-digest", sha(path)]
        if args.solve: command.append("--solve")
        outcome = {"target_mm": target, "case": case.relative_to(ROOT).as_posix(), "model_sha256": sha(path)}
        print("Isolated target "+str(target)+" mm", flush=True)
        try:
            outcome["process"] = run_adapter_process(command, cwd=case, timeout_s=args.timeout, memory_limit_mb=4096,
                output_limit_bytes=512*1024**2, stream_limit_bytes=1024**2)
        except Exception as error:
            outcome.update(blocker=str(error), exception=type(error).__name__)
        report = case/"case-report.json"
        if report.exists():
            outcome["report_sha256"] = sha(report)
            data = json.loads(report.read_text()); outcome.update(status=data["status"], blocker=data.get("blocker"), counts=data.get("counts"))
        else: outcome["status"] = "process_failed_no_fields_accepted"
        summary["cases"].append(outcome)
        print(json.dumps({k: outcome.get(k) for k in ("target_mm", "status", "blocker", "counts")}), flush=True)
    summary["source_model_sha256_after"] = sha(source)
    summary["source_model_unchanged"] = before == summary["source_model_sha256_after"]
    (folder/"summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__": main()
